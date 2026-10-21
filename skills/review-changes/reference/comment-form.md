---
name: comment-form
description: Shape of text this skill posts to GitHub, for `review-changes`.
---

# Comment form

Use this profile only inside `review-changes`, at publish time. It governs text
that reaches GitHub. It does not govern the local report.

## The shape

Every posted comment IS these parts, in this order:

1. Severity emoji, then what fails — **one line**
2. The concrete input and its wrong result — **one line**
3. A ```suggestion block, when the fix is a line replacement

Ceiling: two lines of prose plus the block.

## Language

Spanish. Telegraphic: no preamble, no hedging, no restating the code, no
explaining why the reader should care. Complete sentences with normal grammar —
the reader may not know how this text was produced, and dropped articles read
as broken Spanish rather than as brevity.

Direct verb. The snippet replaces the explanation.

## Example

````markdown
🟠 `user` puede ser nil — `find_by` devuelve nil y `.email` levanta NoMethodError.

```suggestion
    return unless user
    notify(user.email)
```
````

## Rule violations

Quote the rule and name its file:

````markdown
🟠 `CLAUDE.md` · Error handling: "toda llamada externa lleva timeout explícito".
Este `Faraday.get` no lo tiene.

```suggestion
    Faraday.get(url) { |r| r.options.timeout = 5 }
```
````

## Missing tests

Line 1 names the behavior no test pins. Line 2 is the case to write: input,
expected result, and the test file it belongs in. No ```suggestion block: the
test lives in another file.

````markdown
🟠 Ningún test cubre el reembolso parcial que agrega este `if`.
Caso: reembolso de 300 sobre un cargo de 1000 deja `refunded_amount` en 300; va en `spec/services/refund_spec.rb`.
````

## Suggestion blocks

- Use one when the fix replaces the commented line or range, and the
  replacement compiles on its own.
- Match the surrounding indentation exactly — GitHub applies the block
  verbatim.
- Omit it when the fix spans files, needs a new file, or needs a decision. Then
  the second line states the fix in words.

## Replies to the author

A reply answers a question the author asked on one of our threads. It is not a
finding and does not use the finding shape.

- No severity emoji. The severity lives on the original comment.
- Answer only what was asked. Do not restate the finding, do not re-argue it,
  and do not add a second finding to the thread.
- Three lines of prose, ceiling.
- A ```suggestion block only when the answer *is* a line replacement.
- The author's question stands on its own terms. If the question shows the
  finding was wrong, say so in one line and stop.

````markdown
El retry viene del webhook de Stripe, no del cliente: Stripe reintenta el
mismo `event.id` hasta 3 veces en 24 h y cada intento entra a este método.
Con la idempotency key el segundo intento es un no-op.
````

Wrong finding:

````markdown
Tienes razón, `charge!` ya corre dentro de la transacción. El hallazgo no
aplica.
````

## Never in posted text

- Session style directives of any kind, or text written in a compressed
  conversational style. Posted comments are independent of session style.
- Severity language that reads as a merge block: "no mergear", "blocker",
  "cambios requeridos". Findings are suggestions; the merge is not gated.
- Pass names, confidence scores, evidence trails, ledger rows, dedupe counts.
- Praise, greetings, sign-offs, emoji beyond the single severity marker. The
  markers of the resumen block — 💬 ✅ ⚠️ 🚫 🔒 ❔ ❓ 📭 — are local only and
  never appear in posted text.
- Advice to split the work into separate branches.
- Re-review talk outside the round body: disposition names, "ya comenté esto
  antes", or a reply nudging that an earlier comment is still open. The round
  body's `Pendientes` list is the one place an open item is named again.

## Round body

Every review this skill publishes carries the round body, built by
`scripts/post_review.py` from its inputs. One heading line, then up to three
lists, each left out when empty:

```markdown
Ronda 2. 2 comentarios nuevos, ninguno bloquea el merge.

Nuevos:
- `app/models/booking.rb:42` — importante: el monto negativo pasa la validación
- `app/services/refund.rb:18` — sugerencia: sacar el cálculo de la tarifa a un método

Resueltos desde la ronda anterior:
- `app/controllers/trips_controller.rb:30` — N+1 al listar asientos
- `app/jobs/sync_job.rb:12` — no aplica: el job es idempotente

Pendientes:
- `app/models/seat.rb:77` — race condition al reservar el asiento (https://github.com/…)
- `app/services/fare.rb:20` — redondeo con float, ya señalado por coderabbit (https://github.com/…)
```

- The heading names the round and the count of new comments. Nothing new:
  `Sin comentarios nuevos.`; nothing in any list: `Sin comentarios.` Reduced
  coverage adds `(revisión parcial: <qué no corrió>)` after the number.
- Each item is `` `path:line` — `` and one clause, at the code's current line.
  Severity is a word — `crítico`, `importante`, `sugerencia` — never the
  emoji: the item is a summary, not the finding.
- A `Nuevos` item comes from the finding's `summary`: what fails, in the
  finding's own terms, without the failing input or the fix. Those live in the
  inline comment.
- A `Resueltos` item says what the problem was, not who fixed it. A rebuttal the
  code confirms reads `no aplica: <the reason>`.
- A `Pendientes` item carries the link to its thread, and `ya señalado por
  <source>` when the thread is someone else's.

## Approve body

An approval carries the same round body. With nothing new, nothing resolved and
no notes, it goes in bare: the green check already says the code was reviewed.

A docs-only diff puts its notes after the heading, one line per note, each
`path` · what is wrong, keeping its severity marker. No ```suggestion blocks:
the approval already went through, and a suggestion block invites a change the
merge no longer waits for.

```markdown
Ronda 1. Solo documentación. 3 notas, ninguna bloquea.

🔵 `openspec/specs/pagos.md` — el endpoint `POST /refunds` documentado no existe en el código.
🔵 `docs/deploy.md` — la variable `REDIS_URL` quedó con el nombre viejo.
🔵 `README.md` — el badge apunta al repo anterior.
```

When the approval carries 🔵 findings inline, they are listed under `Nuevos`
like any round, and the inline comments keep their normal shape.

Nothing in the body hints that the review approved. The green check already
says it, and a comment explaining the approval is noise.
