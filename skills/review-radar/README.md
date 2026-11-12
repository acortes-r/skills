# review-radar

Runs unattended in a Claude Code cloud routine. Finds the pull requests that
ask for my review, on GitHub and in Slack, decides which deserve one, and runs
[`review-changes --auto`](../review-changes/) on each. It also reports new
activity on my own pull requests and reminds me of what is pending. Everything
lands in one thread in my Slack DM.

It reviews no code and decides no approval: `review-changes` does. My own pull
requests are read-only.

## Set up the routine

1. Clone this repository and the repositories in `config.yml` into the routine's
   environment, with `gh` authenticated and the Slack connector enabled.
2. Add two triggers, both with the prompt `/review-radar`:
   - **Schedule:** `7 9-18 * * 1-5` in `America/Merida` (match `schedule` in
     `config.yml`; the window is computed from it).
   - **GitHub event:** pull request events on the configured repositories.
3. Leave `run.mode: dry` for the first days: it lists what it would review
   without calling `review-changes`. Switch to `live` once the list looks right.
4. Optional: fire the routine with a text that contains `resumen` to get the
   🗓️ Pendientes digest at any hour.

## Configuration

[`config.yml`](config.yml): who I am on GitHub and Slack, the repositories, the
team whose review requests are mine, the authors of my team, the schedule, the
mode, and the my-PRs options.

## What it does on each run

| Trigger | Does |
|---|---|
| Schedule or "Run now" | GitHub + Slack candidates → gate → reviews; my-PR events; daily digest on the first run of the day, or when the prompt says `resumen` |
| Pull request event | that PR only: candidate check → gate → review |

A run with nothing to review, no new activity on my PRs, and no digest due sends
nothing.

The **window** starts at the scheduled slot before this run, with no stored
state: Monday 9:07 covers from Friday 18:07, and a "Run now" at 20:00 covers
from 18:07.

The **gate** skips, in order: unconfigured repo, closed or merged, draft, my
own PR, an author outside my team I never reviewed (GitHub requests only), a
head I already reviewed, and new commits that are only merges from the base. A
reply on a thread does not count as a review.

In live mode, a **lock** keeps two overlapping runs off the same PR. Before
reviewing, a run posts `🔒 revisando … [rr:<owner>/<repo>#<n>@<sha>]` in its
thread; the line with the result carries the same token and frees it. Another
run that sees a live `🔒` skips the PR. When two runs claim it at once, the
older `🔒` wins. A `🔒` with no result frees itself after `run.lock_minutes`.
If the DM cannot be read, the PR is skipped.

## Tests

```bash
python3 skills/review-radar/tests/test_radar.py
```

`gh` is stubbed and no network is used.
