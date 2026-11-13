# start-task

Starts a task in its own git worktree, opened as a Herdr
workspace: a workspace in Herdr TUI, a space in the Herdr app. Give it a Linear issue or a short description of the work; it names the
branch, asks which base to branch from, creates the worktree, and hands back the
absolute path.

Then it opens a coding agent in that workspace (Claude by default; Codex, Cursor,
or any other Herdr agent kind on request) and hands it a brief with
everything the session learned about the task, so the work continues there
without retelling it.

## Install

```bash
npx skills add <your-github-user>/skills --skill start-task
```

## Invoke

```text
/start-task INT3-150
/start-task https://linear.app/acme/issue/INT3-150/reserve-default-type
/start-task fix: rapidoochoa returns a null commercial discount
/start-task INT3-152 from develop
/start-task INT3-153 con codex
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

## Base branch

The base is proposed, never assumed. The skill runs
`scripts/start-worktree.sh --bases`, which fetches and lists the candidates:

```
master     # origin/HEAD, proposed
develop    # other long-lived branches the remote has
```

Accept the first, pick another, or name any branch: a parent feature branch to
stack on works too, even one that exists only locally. Naming the base in the
request (`from develop`) skips the proposal.

Branch, label, and base are shown together, and nothing is created until you
confirm them.

## The agent and its brief

The agent kind is the first of:

1. the one named in the request (`con codex`, `with cursor`);
2. `$START_TASK_AGENT`, for a standing preference (`export START_TASK_AGENT=codex`);
3. `claude`.

Any kind Herdr knows works: `herdr agent` lists them. It is shown with the branch,
label, and base, and confirmed with them.

Before handing off, the skill writes a brief to `<worktree>/.task-brief.md`, which
`.git/info/exclude` keeps out of `git status`:

1. Your request, verbatim: what you asked for, and anything you said you would
   send later.
2. The context it gathered: the issue, the comments that matter, related PRs and
   branches, and its own conclusions.
3. Worktree path, branch, and base.

`scripts/start-agent.sh <workspace-id> <label> <brief-file> [kind]` then puts the
agent in the workspace's first pane with a one-line prompt: `Read the task brief in <path>
and start on it.` The brief stays a file, so its line breaks never reach the
terminal, and the agent can reread it later:

| First pane | Action |
|---|---|
| shell at the prompt | `herdr agent start <name> --kind <kind> -- "<prompt>"`: the prompt rides on the command line |
| idle agent of that kind | renamed to `<name>` and reused, never a second one, then prompted |
| busy agent, or another agent kind | refuses; nothing is sent |

In the Herdr app the first pane is the space's first terminal. A shell there gets the
launch typed in with `hc send` (`claude 'Read the task brief in …'`), and an idle agent
gets the prompt the same way. herdr-core reports Claude Code as `claude-code`; other
kinds by their own name. The agent is not renamed: the space carries the label, and
the agent is addressed by its terminal (`t9`).

The agent is named after the label, normalized to Herdr's rules (`MER-63` →
`mer-63`), with `-2`, `-3`, … on a clash. The script returns as soon as the agent
is `working`, `done`, or `blocked`; it does not wait for the turn to end. If the
agent stops on a trust or permission dialog, the prompt waits behind it: the skill
reports it and leaves the answer to you.

## What the worktree script does

`scripts/start-worktree.sh <branch> <label> [base]` holds every step that must not
vary between runs:

1. Refuses to run outside Herdr (neither `HERDR_ENV=1` from the TUI nor
   `HC_TERMINAL_ID` from the app), with an invalid branch
   name, or with a base that exists neither on `origin` nor locally.
2. Finds the main clone, also when called from inside a linked worktree.
3. Fetches the base: `origin/<base>` when the remote has it, the local branch
   otherwise. With no base given, it uses `origin/HEAD`.
4. Adds `.worktrees/` and `/.task-brief.md` to `.git/info/exclude`, so worktrees
   and their briefs never show up in `git status` and the tracked `.gitignore`
   stays untouched.
5. Opens the workspace:

| Branch state | Action |
|---|---|
| new | `herdr worktree create` at `<main clone>/.worktrees/<branch>` from the base, then drops the inherited upstream |
| local, no worktree | `git worktree add` at the standard path, then `herdr worktree open` |
| local, with a worktree | `herdr worktree open` on the existing path |
| remote only | tracking branch at the standard path, then `herdr worktree open` |

An existing branch keeps its history: the base only applies to a new one.

The workspace opens with `--no-focus`: your view stays where it was.

**In the Herdr app.** The app has no worktree command, so git does every row of the
table (a new branch with `git worktree add --no-track`), and the app shows the result
as a space: `herdr-app do space.new --name <label> --folder <worktree>`. A space
already showing that folder is reused instead. `space.new` brings the new space
forward, so the script selects the caller's space again right after. The response
keeps the TUI's shape, with the space ID in `.result.workspace.workspace_id`.

`scripts/backend.sh` picks the kind: `HERDR_ENV=1` means the TUI and wins when both
are set; otherwise `HC_TERMINAL_ID` plus `herdr-app` and `hc` on `PATH` mean the app.
The two run separate servers and share no workspaces or agents.

**Why the upstream is dropped.** A branch created from `origin/main` tracks
`origin/main`. A bare `git push` then fails with a name mismatch and `git pull`
pulls the base into your branch. With no upstream, the first
`git push -u origin <branch>` sets the right one.

## Tests

```bash
bash skills/start-task/tests/test_start_worktree.sh
bash skills/start-task/tests/test_start_agent.sh
```

Both stub `herdr`, `herdr-app` and `hc`, so no real session or network is touched.

`test_start_worktree.sh` builds throwaway repositories. They cover the four branch states, calling from a linked
worktree, the exclude lines written once, the dropped upstream, an explicit,
local-only, and missing base, the `--bases` listing, and the refusals. In the app:
the new space and the view handed back, a reused space, a tracked remote branch, and
the TUI winning when both are set.

`test_start_agent.sh` covers starting in a shell with the prompt on the command
line, reusing an idle agent of the asked kind, the kind from the argument,
`$START_TASK_AGENT`, or the `claude` default, the brief sent as an absolute path and never as
text, name normalization and clashes, and refusing a busy pane, another agent kind, a malformed kind, an empty
brief, or a run outside Herdr. In the app: typing the launch into a shell, prompting
an idle agent, and refusing a busy terminal, a foreign program, another kind, or an
unknown space.

`evals/evals.json` describes what the agent should do around the script. The
repository has no eval runner, so the evals are read, not executed.

## Layout

```
start-task/
├── SKILL.md                      # naming rules, base choice, and the run
├── scripts/start-worktree.sh     # deterministic worktree + workspace creation
├── scripts/start-agent.sh        # the agent in the workspace, pointed at the brief
├── scripts/backend.sh            # Herdr TUI or Herdr app, sourced by both scripts
├── tests/test_start_worktree.sh  # 44 checks, herdr, herdr-app and hc stubbed
├── tests/test_start_agent.sh     # 36 checks, herdr, herdr-app and hc stubbed
├── evals/evals.json              # agent-level scenarios
└── agents/openai.yaml            # host adapter
```

## Requirements

- `git` 2.20+
- `python3`, to read Herdr's JSON
- The agent's CLI on `PATH`: Claude Code by default, or Codex, Cursor, …
- Herdr, either kind, with the agent running inside it:
  - Herdr TUI 0.9+, in a pane. The scripts call the `herdr` CLI directly; the
    separate `herdr` skill is not needed.
  - The Herdr app, in one of its terminals, with `herdr-app` and `hc` on `PATH`.
- A Linear MCP connector to read issues (optional; without it the name is built
  from the ID and title you give)

## Scope

One task, one worktree, one workspace, one agent per run. It does not push the
branch, open a PR, or remove worktrees: Herdr's `worktree remove` covers cleanup.
