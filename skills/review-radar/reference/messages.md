# Messages

Every message goes to `slack.notify_channel`, sent with
`unfurl_app_links: false` so GitHub links get no previews. A PR is always the
`link` that `radar.py` prints, `<https://github.com/<org>/<repo>/pull/<n>|<label>#<n>>`
(`platform-purchase` → `purchase`), in every section. People are their GitHub
login. Names are plain text, never `<@…>` or `<!subteam^…>`.

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
| dry, gate `review` | `🔍 <link> · <author> · revisaría` |
| live, claiming the PR | `🔒 revisando <link> @ <head> <token>` |
| `action: approved` | `✅ <link> · <author> · Ronda <round> (<head>) · <counts> · aprobado` |
| `action: commented` | `💬 <link> · <author> · Ronda <round> (<head>) · <counts> · comentarios publicados` |
| `action: summary-only` | `📝 <link> · <author> · Ronda <round> (<head>) · solo resumen: <reason>` |
| `action: nothing-sent` | `📭 <link> · <author> · nada nuevo` |
| `action: error`, missing block, checkout failure | `⚠️ <link> · <author> · error: <reason>` |
| over `max_reviews_per_run` | `⏳ <link> · <author> · queda para la siguiente corrida` |
| `radar.py lock` says `skip` | `⏭️ <link> · <author> · omitido: <lock reason>` |
| gate `skip` | `⏭️ <link> · <author> · omitido: <gate reason>` |
| gate `error` | `⚠️ <link> · error: <gate reason>` |

## 📬 Tus PRs

Runs where the digest is not due. One reply: `📬 Tus PRs`, then the `line` of
every PR in `my-prs` with `has_events: true`, as `radar.py` wrote it:
`<emoji> <link> · <facts>`. The emoji is the first that applies: `❌` CI
turned red, `🔁` someone asked for changes, `⚠️` conflicts, `✅` approved or
ready, `💬` comments or bot reviews, `📥` commits. Each person appears once,
with their reviews and comments counted; bots add up into one `bots: <n>`.

```
📬 Tus PRs
✅ <…/pull/2907|funnel#2907> · ana-r aprobó (4 reviews) · eli-r aprobó · cami-r comentó (2 reviews) · bots: 3 · listo para mergear
✅ <…/pull/3196|purchase#3196> · beto-r aprobó · CI verde · 2 hilos abiertos
💬 <…/pull/1490|integrations#1490> · dani-r: 3 comentarios · bots: 1
🔁 <…/pull/2910|funnel#2910> · angel-r pidió cambios · CI rojo en 9f3e21c
📥 <…/pull/3188|purchase#3188> · carlos-r subió 2 commits
```

## 📋 Tus PRs abiertos

When the digest is due (`first_run_of_day` and `my_prs.daily_digest`, or a run
that asked for `resumen`), this replaces `📬 Tus PRs`. One reply: `my-prs`
`digest.title`, then its `digest.lines`, in order.

Every open PR appears once: `<emoji> <link> · <main state> · <other states> ·
🆕 · <facts>`. The emoji and main state are the highest-priority state that
applies. The other states that also apply follow in the same order, each in
its short form. A PR that moved since `since` ends with `🆕` and the same facts
it would have had in `📬`.

| Order | State | Main | Short form |
|---|---|---|---|
| 1 | ready | `🚀 listo para mergear` | never has other states |
| 2 | red CI | `❌ CI rojo en <head>` | `CI rojo` |
| 3 | conflicts | `⚠️ tiene conflictos con la base` | `conflictos` |
| 4 | changes requested | `🔁 cambios pedidos por <logins>` | same |
| 5 | no review yet | `⏳ esperando review` | same |
| 6 | approved, not ready | `✅ aprobado, falta: <CI en curso / n hilos …>` | `aprobado` |
| 7 | draft | `📝 draft (<days> d)` | same |
| 8 | no activity for `stale_days` | `💤 sin movimiento (<days> d)` | `<days> d sin movimiento` |
| 9 | none of the above | `👀 en review` | never a short form |

```
📋 Tus PRs abiertos (5)
🚀 <…/pull/3201|purchase#3201> · listo para mergear · 🆕 · beto-r aprobó
❌ <…/pull/3142|purchase#3142> · CI rojo en 4c1e8d2 · aprobado · 72 d sin movimiento
❌ <…/pull/3177|purchase#3177> · CI rojo en 7e2a5f0 · aprobado · 🆕 · beto-r aprobó
⚠️ <…/pull/1533|integrations#1533> · tiene conflictos con la base · draft (43 d)
💤 <…/pull/1488|integrations#1488> · sin movimiento (4 d)
```

No open PRs: `📋 Tus PRs abiertos (0)` alone.
