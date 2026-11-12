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

Severity counts come from `review-result.comments`: the non-zero ones as
`<n> 🔴`, `<n> 🟠`, `<n> 🔵`, joined by ` · `; `sin comentarios` when all are 0.

| Case | Line |
|---|---|
| dry, gate `review` | `🔍 <label>#<n> · <author> · revisaría` |
| `action: approved` | `✅ <label>#<n> · <author> · Ronda <round> (<head>) · <counts> · aprobado` |
| `action: commented` | `💬 <label>#<n> · <author> · Ronda <round> (<head>) · <counts> · comentarios publicados` |
| `action: summary-only` | `📝 <label>#<n> · <author> · Ronda <round> (<head>) · solo resumen: <reason>` |
| `action: nothing-sent` | `📭 <label>#<n> · <author> · nada nuevo` |
| `action: error`, missing block, checkout failure | `⚠️ <label>#<n> · <author> · error: <reason>` |
| over `max_reviews_per_run` | `⏳ <label>#<n> · <author> · queda para la siguiente corrida` |
| gate `skip` | `⏭️ <label>#<n> · <author> · omitido: <gate reason>` |
| gate `error` | `⚠️ <label>#<n> · error: <gate reason>` |

## 📬 Tus PRs

One line per PR with `has_events: true`: `<emoji> <label>#<n> · <facts>`.

Facts, in this order, joined by ` · `, each only when present:

| From | Fact |
|---|---|
| `events.reviews` | `<author> aprobó` · `<author> pidió cambios` · `<author> comentó` |
| `events.reviews`, the bots entry | `<count> reviews de <logins without [bot]>` (`1 review de …`) |
| `events.comments`, first person entry | `<count> comentarios nuevos de <author>` (`1 comentario nuevo de …`) |
| `events.comments`, later entries | `<count> de <author>`; the bots entry names its `logins` without `[bot]` |
| `events.commits` | `<author> subió <count> commits` (`1 commit`) |
| `events.ci_failed` | `CI rojo en <sha>` |
| `conflicts` | `tiene conflictos con la base` |
| `approved` and `ci` is `success` | `CI verde` |
| `ready` | `listo para mergear` |
| `approved`, not ready, `threads.open` > 0 | `<n> hilos abiertos` |
| `approved`, not ready, `threads.unverified` > 0 | `<n> hilos sin verificar` |

The emoji is the first that applies: `❌` CI failed, `🔁` changes requested in
this window, `⚠️` conflicts, `✅` approved in this window or ready, `💬`
comments or bot reviews, `📥` commits. Only people's reviews count for `🔁` and
`✅`; `approved`, `changes_requested`, and `ready` already ignore bots.

```
✅ purchase#3196 · carlos-r aprobó · CI verde · listo para mergear
✅ purchase#3201 · carlos-r aprobó · CI verde · 2 hilos sin verificar
💬 integrations#1490 · 3 comentarios nuevos de jaz-r · 1 de coderabbitai
🔁 funnel#2907 · angel-r pidió cambios · CI rojo en 9f3e21c
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
