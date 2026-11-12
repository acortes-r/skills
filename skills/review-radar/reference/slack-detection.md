# Slack detection

Find the messages since `since` that ask me for a review, and pull the PR links
out of them. Values come from `config.yml`: `slack.me`, `slack.team_groups`,
`slack.include_dms`, `github.org`.

## Searches

Search with the connector's search tool (see the Slack operations table in
`SKILL.md`). Slack's `after:` filter takes a day and is exclusive, so pass the
day before `since` and drop every result whose `ts` is earlier than `since`.

| Search | Query | Why |
|---|---|---|
| Each team group | the group ID, e.g. `S0C022VG8MT` | the most precise query for group mentions |
| Direct mentions | `slack.me`, e.g. `U0774V5HCJF` | brings a lot of noise; the text check below filters it |
| DMs, when `include_dms` | `github.com/<org>` | PR links sent to me in DMs and group DMs |

Read every page each search returns.

## What counts

A message counts when it was not written by `slack.me` (even when it is
flagged as a bot) and at least one holds:

- its text contains `<@<slack.me>>`;
- its text contains a group of `team_groups` in either form, `<@S…>` or
  `<!subteam^S…>` (with or without a `|handle` suffix);
- it is in a DM with me, or a group DM I am in, and `include_dms` is true.

The search query matching is not enough; check the text.

## Links

Take every `github.com/<org>/<repo>/pull/<n>` in a counting message's text.
Slack wraps links as `<https://github.com/…/pull/12|texto>`; the URL part is
what matters.

A counting message that is a thread reply with no PR link: read its thread with
the read-thread tool and take the links from the parent message.

Keep links to any repository of the org: the gate answers
`repo no configurado` for the ones outside `github.repos`.

## Output

Write `${TMPDIR:-/tmp}/review-radar-slack.json`, `[]` when nothing counted:

```json
[{"url": "https://github.com/<org>/<repo>/pull/<n>", "requested_by": "<display name>"}]
```

`requested_by` is the message author's display name as the search result gives
it. One entry per (link, author); `radar.py candidates --slack` merges the rest.
