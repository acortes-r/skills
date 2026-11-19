# review-radar

Runs unattended in a Claude Code cloud routine. Finds the pull requests that
ask for my review, on GitHub and in Slack, decides which deserve one, and runs
[`review-changes --auto`](../review-changes/) on each. It also reports new
activity on my own pull requests and reminds me of what is pending. Everything
lands in one thread in my Slack DM.

It reviews no code and decides no approval: `review-changes` does. My own pull
requests are read-only.

## Set up the routine

1. Pick **Sonnet** as the routine's model. Only the reviews run on Opus: each
   one goes to a subagent on `run.review_model` (see [Models](#models)).
2. Under **Repositories**, add every repository in `github.repos`, and
   `acortes-r/skills` always last. Turn on `gh` and the Slack connector.
3. Add two triggers, both with the prompt `/review-radar`:
   - **Schedule:** `CRON_TZ=America/Merida 7 9-17/2 * * 1-5`, every 2 hours:
     9:07, 11:07, 13:07, 15:07 and 17:07, Monday to Friday. It must match
     `schedule` in `config.yml`; the window is computed from it.
   - **GitHub event:** pull request events on the configured repositories.
4. For the ping (`notify.ping`), create a Slack workflow with a webhook trigger
   that takes one text variable, `mensaje`, and sends it to me. Put its URL in
   the routine environment's `SLACK_PING_WEBHOOK` (the `notify.ping_env` name),
   and allow its host (`hooks.slack.com`) in the environment's network access.
   Without the variable, runs work as before and skip the ping.
5. Leave `run.mode: dry` for the first days: it lists what it would review
   without calling `review-changes`. Switch to `live` once the list looks right.

## Configuration

[`config.yml`](config.yml): who I am on GitHub and Slack, the repositories and
their short names, the team whose review requests are mine, the authors of my
team, the schedule, the mode, the review model, and the my-PRs options.

### Add a repository

1. Add it to `github.repos` in `config.yml`. It must belong to `github.org`
   (`reservamos`).
2. If what follows its last hyphen is unclear or already taken, give it a short
   name in `github.repo_labels`. A config where two repos get the same short
   name fails to load and names both.
3. Add it to the routine's **Repositories**, before `acortes-r/skills`, which
   stays last.

Until both are done, its PRs show up as `⏭️ … omitido: repo no configurado`:
the routine has no access to it (GitHub answers 403), so it never reads it.

### GitHub search

Every search runs only inside `github.org`: each query carries
`org:reservamos`, never `repo:` qualifiers, other orgs, or personal repos, and
`radar.py` refuses a query without `org:`. The results are filtered in Python
to `github.repos`; a result from another owner is dropped.

### Models

The routine itself runs on Sonnet. `radar.py review-call` prints the subagent
call for each review with `model: <run.review_model>` (`opus`), so every
`review-changes --auto` runs on Opus. A session without the Agent tool reviews
inline, on the session's model, and the result line says
`(review sin subagente: modelo de la sesión)`.

## What it does on each run

| Trigger | Does |
|---|---|
| Schedule or "Run now" | GitHub + Slack candidates → gate → reviews; my-PR events; `📋` digest of every open PR of mine on the first run of the day |
| Pull request event | that PR only: candidate check → gate → review |

A run with nothing to review, no new activity on my PRs, and no digest due sends
nothing. A run that sent something ends with a **ping**: one line from a Slack
workflow webhook, so Slack notifies me (messages the connector sends to my own
DM do not). It links to the run's thread; a failed ping is noted at the end of
the thread and never fails the run.

The **window** starts at the scheduled slot before this run, with no stored
state: 11:07 covers from 9:07, Monday 9:07 covers from Friday 17:07, and a
"Run now" at 20:00 covers from 17:07. Up to `run.max_reviews_per_run` (5)
reviews run per run; the rest wait for the next one.

The **gate** skips, in order: unconfigured repo, closed or merged, my own PR,
an author outside my team I never reviewed (GitHub requests only), draft, a
head I already reviewed, and new commits that are only merges from the base.
The author rule goes before draft, so a draft's reason says whether it will be
reviewed once it is ready. A reply on a thread does not count as a review.

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
