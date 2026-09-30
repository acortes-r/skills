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
- Praise, greetings, sign-offs, emoji beyond the single severity marker.
- Advice to split the work into separate branches.
- Anything about a re-review having run: disposition names, thread counts,
  "ya comenté esto antes", or a nudge that an earlier comment is still open.

## Review body

The review's top-level body is one line naming the count and the highest
severity present, for example:

```
4 comentarios (1 critical, 3 suggestion). Ninguno bloquea el merge.
```

No hallazgos means no review body, because no review is created.
