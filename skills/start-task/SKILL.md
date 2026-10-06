---
name: start-task
description: Use when the user wants to start a new task — a Linear issue, feature, fix, or chore — in its own git worktree and branch opened as a Herdr workspace, with a Claude agent there that receives the task context. Names the branch from the Linear issue or the task description. Requires running inside Herdr.
license: MIT
compatibility: Requires git and Herdr 0.9+, with the agent running inside a Herdr pane (HERDR_ENV=1). Reading Linear issues requires a Linear MCP connector; without one the branch name is derived from the issue ID and title the user gives.
allowed-tools: Read, Bash
metadata:
  version: 0.2.0
  branch_from_issue: Linear gitBranchName, verbatim
  branch_without_issue: <type>/<slug>
  worktree_path: <main clone>/.worktrees/<branch>
  base_branch: proposed from origin/HEAD, confirmed by the user
  agent: claude, in the workspace's first pane, prompted with the task brief
---

# Start task

Turn the context of a task into a well-named branch, a Herdr workspace hanging off
the main clone of the current repository, and a Claude agent in that workspace that
already holds the task context. The run is done when that agent has started working
on the brief; the task itself continues in that session, not this one.

## 1. Resolve the branch name

The argument is either a Linear issue (an ID like `INT3-150`, or its URL) or a free
description of the task.

**With a Linear issue:**

1. Read the issue through the Linear MCP connector (`get_issue`).
2. Use its `gitBranchName` verbatim. Example: `int3-144-reserve-default-type`.
3. With no Linear connector available, build the name the way Linear does: the issue
   ID in lowercase, a hyphen, the title in kebab-case without accents, ~60 characters
   at most.
4. Label: the issue ID (`INT3-150`).

**Without an issue:**

1. Infer the type from the description: `feat`, `fix`, `chore`, `refactor`, `docs`,
   or `test`. Ask when it is ambiguous.
2. Name: `<type>/<slug>`, the slug in English kebab-case, 3 to 6 words naming the
   what. Example: `fix/rapidoochoa-discount-null`.
3. Label: the slug.

## 2. Choose the base branch

Run the script in this skill's directory, from anywhere inside the repository:

```bash
scripts/start-worktree.sh --bases
```

It fetches and prints the base candidates, one per line: the repository default
(`origin/HEAD`) first, then the long-lived branches the remote has (`main`, `master`,
`develop`, …). Propose the first line as the base and list the rest as alternatives.
The user can also name any other branch, such as a parent branch to stack on.

When the user already named a base in the request, use it and skip the proposal.

## 3. Confirm

Show the proposed branch, label, and base together, and wait for the user's
confirmation. A correction to any of the three is applied and shown again.

## 4. Create the workspace

```bash
scripts/start-worktree.sh <branch> <label> <base>
```

The script finds the main clone (also when called from a linked worktree), fetches
the base, adds `.worktrees/` to `.git/info/exclude`, and then:

- creates the worktree at `<main clone>/.worktrees/<branch>` from `origin/<base>`,
  or from the local `<base>` when it exists only locally;
- reopens the branch instead when it already exists, locally or on the remote; the
  base does not apply then, and the report says the branch was reopened.

Herdr opens it as a workspace linked to the main clone and leaves the focus where it was.
Keep the workspace ID from the response (`.result.workspace.workspace_id`) for step 5.

When Herdr answers with a repository-trust error, show it to the user and ask before
retrying with `--trust-repository`.

## 5. Hand the task to an agent

Write a **brief** to a temporary file, outside the repository. The agent in the new
workspace starts with nothing but this file and the repository, so the brief carries
everything this session learned:

1. The user's request, verbatim, including what they asked the agent to do and
   anything they said they will send later.
2. The context gathered: issue ID, title, URL, the description in short, the comments
   that change the picture, related PRs and branches with their state, and what this
   session concluded from them.
3. Where it runs: worktree path, branch, base.

Then run:

```bash
scripts/start-agent.sh <workspace-id> <label> <brief-file>
```

The script takes the workspace's first pane. It reuses an idle Claude already in that
pane, or starts one in the shell, names it after the label, and sends the brief as
the first prompt. It returns once the agent starts working, without waiting for the
turn to end.

When the script refuses because the pane is busy, or the agent comes back `blocked`
(a trust or permission dialog), report it and leave the answer to the user in that
workspace.

## 6. Report

Give the user:

- branch and base;
- absolute path of the worktree;
- Herdr workspace ID and agent name;
- one line on what the brief asked the agent to do.
