# Messages

Every message goes to `slack.notify_channel`. Lines use the PR's `label`
(`platform-purchase` → `purchase`), `#<number>`, and the GitHub login. Names
are plain text, never `<@…>` or `<!subteam^…>`.

## Start message

```
🔎 Review radar · <now_local> [· modo prueba]
Busqué en GitHub (<github.me>, @<request_teams>) y Slack (@<group names>, DMs)
<N> PRs encontrados · reviso <R> · omito <O>
```

- `· modo prueba` when `run.mode` is `dry`.
- Group names come from `slack.team_group_names`; a group without a name is
  written as its ID. `, DMs` only when `include_dms`.
- `N` candidates, `R` with gate `review`, `O` the rest (skip and error). In live
  mode with more than `max_reviews_per_run`, append ` · <D> para la siguiente`.
- No candidates: send only the first two lines.
- An event run writes `Busqué en GitHub (evento de PR)` as line 2.

## Review lines

`(vía Slack: <requested_by, comma-separated>)` goes at the end of a line when
the PR's `sources` include `slack`.

In live mode, every line after a PR's `🔒` that ends that PR (✅ 💬 📝 📭 ⚠️,
or the `⏭️` of a lost tie-break) ends with the same `<token>`,
`[rr:<owner>/<repo>#<n>@<head>]`, after the `vía Slack` part. The token
releases the lock; see [locks.md](locks.md).

Severity counts come from `review-result.comments`: the non-zero ones as
`<n> 🔴`, `<n> 🟠`, `<n> 🔵`, joined by ` · `; `sin comentarios` when all are 0.

| Case | Line |
|---|---|
| dry, gate `review` | `🔍 <label>#<n> · <author> · revisaría` |
| live, claiming the PR | `🔒 revisando <label>#<n> @ <head> <token>` |
| `action: approved` | `✅ <label>#<n> · <author> · Ronda <round> (<head>) · <counts> · aprobado` |
| `action: commented` | `💬 <label>#<n> · <author> · Ronda <round> (<head>) · <counts> · comentarios publicados` |
| `action: summary-only` | `📝 <label>#<n> · <author> · Ronda <round> (<head>) · solo resumen: <reason>` |
| `action: nothing-sent` | `📭 <label>#<n> · <author> · nada nuevo` |
| `action: error`, missing block, checkout failure | `⚠️ <label>#<n> · <author> · error: <reason>` |
| over `max_reviews_per_run` | `⏳ <label>#<n> · <author> · queda para la siguiente corrida` |
| `radar.py lock` says `skip` | `⏭️ <label>#<n> · <author> · omitido: <lock reason>` |
| gate `skip` | `⏭️ <label>#<n> · <author> · omitido: <gate reason>` |
| gate `error` | `⚠️ <label>#<n> · error: <gate reason>` |

## 📬 Tus PRs

One line per PR with `has_events: true`: `<emoji> <label>#<n> · <facts>`.

Facts, in this order, joined by ` · `, each only when present. `radar.py`
already gives one entry per person: a reviewer's comments sit in their review
entry, so nobody appears twice.

The parenthesis lists the non-zero counts (`1 review`, `2 reviews`,
`1 comentario`, `3 comentarios`) and is left out at 1 review and 0 comments:
`ana-r aprobó (4 reviews)`, `beto-r pidió cambios`, `cami-r comentó (2 reviews,
3 comentarios)`, `dani-r: 3 comentarios`.

| From | Fact |
|---|---|
| `events.reviews`, one per person, in the order given | `<author> aprobó` · `<author> pidió cambios` · `<author> comentó`, by `state`, plus `(<reviews> reviews, <comments> comentarios)` |
| `events.comments`, people | `<author>: <count> comentarios` (`1 comentario`) |
| the bots entries of `events.reviews` and `events.comments` | one fact, `bots: <sum of both counts>` |
| `events.commits` | `<author> subió <count> commits` (`1 commit`) |
| `events.ci_failed` | `CI rojo en <sha>` |
| `conflicts` | `tiene conflictos con la base` |
| `approved`, `ci` is `success`, not `ready` | `CI verde` (`listo para mergear` already implies it) |
| `ready` | `listo para mergear` |
| `approved`, not ready, `threads.open` > 0 | `<n> hilos abiertos` |
| `approved`, not ready, `threads.unverified` > 0 | `<n> hilos sin verificar` |

The emoji is the first that applies: `❌` CI failed, `🔁` changes requested in
this window, `⚠️` conflicts, `✅` approved in this window or ready, `💬`
comments or bot reviews, `📥` commits. Only people's reviews count for `🔁` and
`✅`; `approved`, `changes_requested`, and `ready` already ignore bots.

```
✅ funnel#2907 · ana-r aprobó (4 reviews) · eli-r aprobó · cami-r comentó (2 reviews) · bots: 3 · listo para mergear
✅ purchase#3196 · beto-r aprobó · CI verde · 2 hilos abiertos
✅ purchase#3201 · beto-r aprobó · CI verde · 2 hilos sin verificar
💬 integrations#1490 · dani-r: 3 comentarios · bots: 1
🔁 funnel#2910 · angel-r pidió cambios · CI rojo en 9f3e21c
📥 purchase#3188 · carlos-r subió 2 commits
```

## 🗓️ Pendientes

Only when `first_run_of_day` and `my_prs.daily_digest`. Over every open PR
`my-prs` returned, whether or not it had events. Skip an empty group; when all
are empty, write `🗓️ Pendientes: nada`.

```
🗓️ Pendientes
📝 Drafts: <label>#<n> (<draft_days> d), …
💤 Sin movimiento: <label>#<n> (<idle_days> d), …     ← stale and not draft
⏳ Sin review: <label>#<n>, …                          ← needs_review
⚠️ Con conflictos: <label>#<n>, …                      ← conflicts
```
