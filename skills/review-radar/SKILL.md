---
name: review-radar
description: Use when running as an unattended routine — on a schedule or on a GitHub pull request event — to find the pull requests waiting for my review in GitHub and Slack, decide which deserve one, run review-changes --auto on them, report new activity and pending items on my own pull requests, and send a short summary to my Slack DM. Reviews no code itself and decides no approval; review-changes owns that.
license: MIT
compatibility: Built for a Claude Code cloud routine. Requires python3, an authenticated GitHub CLI (gh) used over REST only, the review-changes skill installed next to this one, a Slack connector (search, read channel, read thread, send message), and the configured repositories cloned in the session.
allowed-tools: Read, Grep, Glob, Bash, Skill, Agent
metadata:
  version: 0.2.0
  writes: my Slack DM (slack.notify_channel) only; GitHub only through review-changes
  modes: dry (lists what it would review) | live (runs review-changes --auto)
  posted_language: es
---

# Review radar

An orchestrator for unattended runs. It finds pull requests that ask for my
review, filters them through a **gate**, hands each one that passes to
`review-changes --auto`, watches my own pull requests (read-only), and reports
everything in one thread in my Slack DM.

`radar.py` is `scripts/radar.py` next to this file; `config.yml` sits beside
it. Every `radar.py` subcommand prints JSON and holds the deterministic rules:
time window, candidates, gate, my-PR events. Run it; do not reimplement its
rules in the conversation.

```bash
R="python3 <skill dir>/scripts/radar.py"; C="--config <skill dir>/config.yml"
```

## Invariants

- GitHub is read over REST only: `radar.py`, `gh api …`, and
  `post_review.py pr|diff|threads`. Cloud sessions answer GraphQL with 403.
- GitHub receives writes only from `review-changes`. Everything about my own
  pull requests is read-only.
- Slack receives writes only in `slack.notify_channel`: the start message and
  replies in its own thread.
- Every person and group in those messages is plain text that notifies no one:
  `Carlos Castro`, a GitHub login, `@core`, `@merchant-services`. The DM never
  carries `<@U…>` or `<!subteam^…>`.
- One PR's failure is one `⚠️` line; every other PR is still processed.

## Slack operations

The skill needs four Slack operations. Use the connector tool whose name ends
in the suffix below; the prefix varies by host (`mcp__Slack__`,
`mcp__claude_ai_Slack__`, …).

| Operation | Tool name ends in |
|---|---|
| Search messages in channels, DMs, and group DMs | `slack_search_public_and_private` |
| Read my DM's history (live mode, for locks) | `slack_read_channel` |
| Read a thread (the parent of a reply, a run's thread) | `slack_read_thread` |
| Send to my DM, or reply in that message's thread (`unfurl_app_links: false`) | `slack_send_message` |

No search tool: skip Slack detection and add `Slack: sin conector` to the start
message. No send tool: print the messages in the session output and stop.

## Steps

### 1. Window and trigger

Read `config.yml`. Run `$R since $C`; keep `since`, `first_run_of_day`, and
`now_local`.

The run is an **event run** when the routine's prompt carries a GitHub
`pull_request` event (a payload with `pull_request` and `repository`, or the
PR URL it names). Anything else (the schedule, "Run now", a fired trigger)
is a **scheduled run**.

The **digest is due** when `first_run_of_day` and `my_prs.daily_digest` hold,
or when a scheduled run's prompt or fire payload contains `resumen` (any case):
that run sends `📋 Tus PRs abiertos` whatever the hour.

### 2. Event run

1. `$R candidates $C --pr <owner>/<repo>#<n>`. No candidate → end silently.
2. `$R gate $C --pr <owner>/<repo>#<n> --source github`.
3. Continue at step 4 with this one PR. Slack detection, my PRs, and the
   digest stay out of an event run, and it runs outside office hours too.

### 3. Scheduled run

1. **Slack.** Follow [reference/slack-detection.md](reference/slack-detection.md)
   to find PR links that ask for my review since `since`, and write them to
   `${TMPDIR:-/tmp}/review-radar-slack.json`.
2. **Candidates.** `$R candidates $C --slack ${TMPDIR:-/tmp}/review-radar-slack.json`.
   It merges GitHub and Slack into one entry per PR, with `sources`,
   `requested_by`, and `gate_source`.
3. **Gate.** For every candidate: `$R gate $C --pr <pr> --source <gate_source>`.
   Exit code 1 with `decision: error` is that PR's `⚠️` line.
4. **My PRs.** When `my_prs.enabled`: `$R my-prs $C --since <since>`.

### 4. Early exit

End without sending anything, and without loading `review-changes`, when all
three hold:

- no gate answered `review`;
- no PR in `my-prs` has `has_events: true`;
- the digest is not due.

### 5. Start message

Send the start message to `notify_channel` and keep its `ts`: every later
message is a reply in its thread. Formats for this and every line below:
[reference/messages.md](reference/messages.md).

### 6. Reviews

The PRs whose gate said `review`, in candidate order.

- **`run.mode: dry`.** Invoke nothing and take no lock. Reply once in the
  thread: the `🔍 … revisaría` lines, then the `⏭️` skipped lines, then the
  gate errors.
- **`run.mode: live`.** Take the first `run.max_reviews_per_run`; the rest get
  a `⏳` line and wait for the next run. Reply once with the `⏳`, `⏭️`, and
  gate-error lines. Then, for each PR to review, one at a time, every line is
  its own reply in the thread, sent as soon as it is known. `<head>` is the
  gate's `head`; `<token>` is the `token` that `radar.py lock` prints.
  1. **Locks.** Read them into `${TMPDIR:-/tmp}/review-radar-locks.json`
     following [reference/locks.md](reference/locks.md), then
     `$R lock $C --lines <file> --pr <pr> --sha <head>`. `skip` →
     `⏭️ … omitido: <reason>`, next PR.
  2. **Claim.** Reply `🔒 revisando <link> @ <head> <token>` and keep
     its `ts`.
  3. **Confirm.** Read the locks again and run the same `lock` with
     `--mine <ts>`. `skip` (another run claimed it first) →
     `⏭️ … omitido: <reason> <token>`, next PR.
  4. Find its clone: the directory in the session whose `origin` remote points
     at `github.com/<owner>/<repo>`. None → `⚠️ … error: repo no clonado`.
  5. Check out the head without GraphQL:
     `git -C <dir> fetch origin pull/<n>/head && git -C <dir> checkout --detach FETCH_HEAD`.
     (`gh pr checkout` uses GraphQL.)
  6. From `<dir>`, run `review-changes --auto <PR url>`. When the Agent tool
     exists, run it in a subagent whose prompt asks for the `review-changes`
     skill with exactly those arguments, from `<dir>`, and for the final
     `review-result` block back verbatim; otherwise invoke the skill inline.
  7. Parse the `review-result` JSON block. Missing or unparsable →
     `⚠️ … error: sin review-result`.

  From step 2 on, the line that ends the PR, result or `⚠️` or `⏭️`, ends with
  `<token>`: that releases the lock. A `🔒` left without it blocks the PR for
  `run.lock_minutes`.

### 7. My PRs and digest

One more reply in the thread, only when it has content:

- digest due: `📋 Tus PRs abiertos`, every open PR once, `🆕` on the ones
  that moved; no `📬` section;
- otherwise: `📬 Tus PRs`, one line per PR with `has_events: true`.

Errors that `candidates` or `my-prs` returned in `errors` go at the end of the
reply they belong to, one `⚠️` line each.

The run is done when every gated PR has exactly one final line in the thread,
every `🔒` it posted has a later line with the same token, and every
`has_events` PR has its line in `📬` or `📋`.
