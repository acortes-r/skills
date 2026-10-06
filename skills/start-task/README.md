# start-task

Starts a task in its own git worktree, opened as a Herdr
workspace. Give it a Linear issue or a short description of the work; it names the
branch, creates the worktree off the repository's default branch, and hands back
the absolute path.

It sets up the place to work and stops there. The task itself starts in the new
workspace.

## Install

```bash
npx skills add <your-github-user>/skills --skill start-task
```

## Invoke

```text
/start-task INT3-150
/start-task https://linear.app/acme/issue/INT3-150/reserve-default-type
/start-task fix: rapidoochoa returns a null commercial discount
```

## Branch names

| Input | Branch | Workspace label |
|---|---|---|
| Linear issue | Linear's `gitBranchName`, verbatim: `int3-150-reserve-default-type` | `INT3-150` |
| Linear issue, no Linear connector | same shape, built from the ID and title | `INT3-150` |
| Description | `<type>/<slug>`: `fix/rapidoochoa-discount-null` | `rapidoochoa-discount-null` |

Using Linear's own name means Linear links the branch, and the PR opened from it,
to the issue without any extra step. Types for the no-issue case follow
Conventional Commits: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`.

The proposed branch is always shown first. Nothing is created until you confirm it.

## What the script does

`scripts/start-worktree.sh <branch> <label>` holds every step that must not vary
between runs:

1. Refuses to run outside a Herdr pane (`HERDR_ENV=1`) or with an invalid branch name.
2. Finds the main clone, also when called from inside a linked worktree.
3. Reads the base branch from `origin/HEAD` (`main`, `master`, `develop` — whatever
   the repository uses) and fetches it.
4. Adds `.worktrees/` to `.git/info/exclude`, so worktrees never show up in
   `git status` and the tracked `.gitignore` stays untouched.
5. Opens the workspace:

| Branch state | Action |
|---|---|
| new | `herdr worktree create` at `<main clone>/.worktrees/<branch>` from `origin/<base>`, then drops the inherited upstream |
| local, no worktree | `git worktree add` at the standard path, then `herdr worktree open` |
| local, with a worktree | `herdr worktree open` on the existing path |
| remote only | tracking branch at the standard path, then `herdr worktree open` |

The workspace opens with `--no-focus`: your view stays where it was.

**Why the upstream is dropped.** A branch created from `origin/main` tracks
`origin/main`. A bare `git push` then fails with a name mismatch and `git pull`
pulls the base into your branch. With no upstream, the first
`git push -u origin <branch>` sets the right one.

## Tests

```bash
bash skills/start-task/tests/test_start_worktree.sh
```

Each case builds throwaway repositories and stubs `herdr`, so no real session or
network is touched. They cover the four branch states, calling from a linked
worktree, the exclude line written once, the dropped upstream, and both refusals.

`evals/evals.json` describes what the agent should do around the script. The
repository has no eval runner, so the evals are read, not executed.

## Layout

```
start-task/
├── SKILL.md                      # naming rules and the three steps
├── scripts/start-worktree.sh     # deterministic worktree + workspace creation
├── tests/test_start_worktree.sh  # 18 checks, herdr stubbed
├── evals/evals.json              # agent-level scenarios
└── agents/openai.yaml            # host adapter
```

## Requirements

- `git` 2.20+
- Herdr 0.9+, with the agent running inside a Herdr pane
- A Linear MCP connector to read issues (optional; without it the name is built
  from the ID and title you give)

## Scope

One task, one worktree, one workspace per run. It does not start an agent in the
new workspace, push the branch, open a PR, or remove worktrees: Herdr's
`worktree remove` covers cleanup.
