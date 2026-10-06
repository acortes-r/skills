---
name: start-task
description: Use when the user wants to start a new task — a Linear issue, feature, fix, or chore — in its own git worktree and branch opened as a Herdr workspace. Names the branch from the Linear issue or the task description. Requires running inside Herdr.
license: MIT
compatibility: Requires git and Herdr 0.9+, with the agent running inside a Herdr pane (HERDR_ENV=1). Reading Linear issues requires a Linear MCP connector; without one the branch name is derived from the issue ID and title the user gives.
allowed-tools: Read, Bash
metadata:
  version: 0.1.0
  branch_from_issue: Linear gitBranchName, verbatim
  branch_without_issue: <type>/<slug>
  worktree_path: <main clone>/.worktrees/<branch>
---

# Start task

Turn the context of a task into a well-named branch and a ready Herdr workspace,
hanging off the main clone of the current repository. The run is done when the user
has the absolute path of the worktree; the task itself starts in another session.

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

Show the proposed branch and label, and wait for the user's confirmation before step 2.

## 2. Create the workspace

Run the script in this skill's directory, from anywhere inside the repository:

```bash
scripts/start-worktree.sh <branch> <label>
```

The script finds the main clone (also when called from a linked worktree), takes the
base branch from `origin/HEAD`, fetches it, adds `.worktrees/` to
`.git/info/exclude`, and then:

- creates the worktree at `<main clone>/.worktrees/<branch>` from `origin/<base>`;
- reopens the branch instead when it already exists, locally or on the remote.

Herdr opens it as a workspace linked to the main clone and leaves the focus where it was.

When Herdr answers with a repository-trust error, show it to the user and ask before
retrying with `--trust-repository`.

## 3. Report

Read the JSON response and give the user:

- branch and base;
- absolute path of the worktree;
- Herdr workspace ID.

The workspace is left with its shell at the prompt; the user starts the task there.
