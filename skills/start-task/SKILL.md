---
name: start-task
description: Use when the user wants to start a new task — a Linear issue, feature, fix, or chore — in its own git worktree and branch opened as a Herdr workspace, with a coding agent there (Claude by default, or Codex, Cursor, or another the user names) that receives the task context. Names the branch from the Linear issue or the task description. Requires running inside Herdr, the TUI or the app.
license: MIT
compatibility: Requires git, python3, the chosen agent's CLI on PATH, and either Herdr TUI 0.9+ (the agent in a pane, HERDR_ENV=1) or the Herdr app with herdr-app and hc on PATH (the agent in an app terminal, HC_TERMINAL_ID set). Reading Linear issues requires a Linear MCP connector; without one the branch name is derived from the issue ID and title the user gives.
allowed-tools: Read, Bash
metadata:
  version: 0.4.0
  branch_from_issue: Linear gitBranchName, verbatim
  branch_without_issue: <type>/<slug>
  worktree_path: <main clone>/.worktrees/<branch>
  base_branch: proposed from origin/HEAD, confirmed by the user
  brief: <worktree>/.task-brief.md, kept out of git through info/exclude
  agent: the kind the user names, else $START_TASK_AGENT, else claude; in the workspace's first pane, prompted to read the brief
  backends: Herdr TUI (workspace, pane) or Herdr app (space, terminal), detected by the scripts
---

# Start task

Turn the context of a task into a well-named branch, a Herdr workspace hanging off
the main clone of the current repository, and a coding agent in that workspace that
already holds the task context. The run is done when that agent has started working
on the brief; the task itself continues in that session, not this one.

Herdr comes in two kinds, and the scripts detect which one this session runs in:
**Herdr TUI** (`herdr`, `HERDR_ENV=1`), where the workspace is a Herdr workspace with
panes, and the **Herdr app** (`herdr-app` over `hc`, `HC_TERMINAL_ID` set), where it
is a space with terminals. The steps are the same in both; only what step 5 opens and
step 7 reports differs.

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

## 3. Choose the agent

The agent is a Herdr agent kind: `claude`, `codex`, `cursor`, … (`herdr agent` lists
them all). Take the first that applies:

1. The kind the user named in the request (`con codex`, `with cursor`).
2. The value of `$START_TASK_AGENT`.
3. `claude`.

## 4. Confirm

Show the proposed branch, label, base, and agent together, and wait for the user's
confirmation. A correction to any of the four is applied and shown again.

## 5. Create the workspace

```bash
scripts/start-worktree.sh <branch> <label> <base>
```

The script finds the main clone (also when called from a linked worktree), fetches
the base, adds `.worktrees/` to `.git/info/exclude`, and then:

- creates the worktree at `<main clone>/.worktrees/<branch>` from `origin/<base>`,
  or from the local `<base>` when it exists only locally;
- reopens the branch instead when it already exists, locally or on the remote; the
  base does not apply then, and the report says the branch was reopened.

In Herdr TUI, Herdr opens it as a workspace linked to the main clone. In the app, git
creates the worktree and the app shows it as a space named after the label, or reuses
the space already showing that folder. Either way the user's view stays where it was.
Keep the ID from the response (`.result.workspace.workspace_id`, a workspace in the
TUI, a space in the app) for step 6.

When Herdr TUI answers with a repository-trust error, show it to the user and ask before
retrying with `--trust-repository`.

## 6. Hand the task to the agent

Write a **brief** to `<worktree>/.task-brief.md`; `info/exclude` keeps it out of git.
The agent in the new workspace starts with nothing but this file and the repository,
so the brief carries everything this session learned:

1. The user's request, verbatim, including what they asked the agent to do and
   anything they said they will send later.
2. The context gathered: issue ID, title, URL, the description in short, the comments
   that change the picture, related PRs and branches with their state, and what this
   session concluded from them.
3. Where it runs: worktree path, branch, base.

Then run:

```bash
scripts/start-agent.sh <workspace-id> <label> <worktree>/.task-brief.md <kind>
```

The script takes the workspace's first pane (the space's first terminal in the app). It
reuses an idle agent of that kind already there, or starts one in the shell, and gives it
a one-line prompt to read the brief. In the TUI it also names the agent after the label;
in the app the space carries the label and the agent is addressed by its terminal (`t9`).
It returns once the agent takes the prompt up, without waiting for the turn to end, and
prints the agent with its status (`agent_status` in the TUI, `status.state` in the app):

- `working` or `done`: the agent is on the task.
- `blocked`: a trust or permission dialog is waiting. The prompt is already queued;
  report it and leave the answer to the user in that workspace.

When the script refuses because the pane is busy or runs another kind of agent,
report it the same way.

## 7. Report

Give the user:

- branch and base;
- absolute path of the worktree;
- Herdr kind (TUI or app), workspace or space ID, agent kind, and agent name or terminal;
- one line on what the brief asked the agent to do.
