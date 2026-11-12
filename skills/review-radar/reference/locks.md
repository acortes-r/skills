# Locks

Live mode only. Two runs can overlap: a scheduled run still reviewing when the
next one starts, or a GitHub event arriving mid-run. Each run claims a PR with
a `🔒` line in its own thread before reviewing it; `radar.py lock` decides from
the lines you collect here.

## Collect the lines

1. Read my DM's history with the read-channel tool: `channel_id` is
   `slack.notify_channel`, `oldest` is now minus `2 × run.lock_minutes`
   (default 90, so 3 h) as epoch seconds. Read every page. If the user ID is
   rejected, use the `channel` the send tool returned for this run's start
   message.
2. Keep the radar's start messages: their text begins with `🔎 Review radar`.
   This run's own start message is one of them.
3. Read each one's thread with the read-thread tool.
4. Write `${TMPDIR:-/tmp}/review-radar-locks.json` with every reply whose text
   contains `[rr:`, `[]` when none:

```json
[{"ts": "<reply ts>", "thread": "<start message ts>", "text": "<reply text>"}]
```

Copy `ts` and `text` as Slack returns them. `radar.py` keeps only the lines
newer than `lock_minutes`, matches a release to the `🔒` of the same thread,
and breaks ties by the older `ts`.

## When a read fails

Any read above fails, or the read-channel tool is missing: write
`{"error": "<what failed>"}` to the file. `radar.py lock` then answers `skip`
with `candados ilegibles`, and the PR waits for a run that can read them.
