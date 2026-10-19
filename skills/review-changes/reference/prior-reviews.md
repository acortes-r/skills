---
name: prior-reviews
description: Re-review pass over this skill's own earlier comments on the PR, for `review-changes`.
---

# Prior reviews

Use this profile only inside `review-changes`, after verification and before
`existing-comments.md`. Its purpose is to never say the same thing twice on the
same pull request, and to read what the author replied to what was already said.

`existing-comments.md` covers other reviewers. This file covers ours.

## Contents
- Identify our threads
- Collect
- Read the reply
- Dispositions
- Check whether the problem is still present
- Feed the round
- Answer a question
- Ledger

## Identify our threads

```bash
gh api user --jq .login    # the login this run publishes as
```

A thread is ours when both hold:

1. The first comment's author login equals that login.
2. That comment's body starts with a severity marker — `🔴`, `🟠`, or `🔵`.

The second condition matters. The same account also writes ordinary review
comments by hand; those are not ours and are not managed by this pass. Treat
them as another reviewer and let `existing-comments.md` handle them.

Command fails or returns no login: record `reduced-context:no-self-identity`,
treat no thread as ours, and let every finding fall through to the generic
dedupe. Never guess the identity from the comment bodies alone.

## Collect

The `reviewThreads` query in `existing-comments.md` already returns everything
this pass needs, including `comments(first:20)` per thread. Run it once and use
it for both passes. Do not issue a second query.

What this pass reads that the other one discards:

- `comments.nodes[1..]` — the replies. The other pass only looks at the first.
- `isResolved`, `isOutdated`, `path`, `line` — for the disposition.
- Each reply's `author.login` and `createdAt`.
- The thread `id` — the node id that resolving needs — and the first comment's
  `url` for the round body.

REST fallback (`/pulls/<n>/comments`) carries `in_reply_to_id` but no resolution
state. Replies are still readable; resolution is not. Record it and treat every
thread as unresolved.

## Read the reply

The relevant reply is the **last one whose author is not us**. Earlier replies
are context, not the verdict.

Read it semantically. "ya quedó", "lo saqué a otro PR", "fixed in abc123", "👍"
and "done" are one meaning. So are "no aplica porque ese endpoint es interno" and
a paragraph explaining the same thing. Never match on keywords.

A reply that only acknowledges without claiming anything ("buen punto", "lo veo
mañana") is not a claim. Classify the thread as `sin-atender`.

## Dispositions

Classify every thread of ours into exactly one:

| Disposition | Condition | Behavior |
|---|---|---|
| `resuelto-confirmado` | the problem is gone from the current code, whatever the reply says or with no reply at all | `resueltos`; the thread goes to `resolve.json` while it is open |
| `no-aplica-aceptado` | reply argues it does not apply **and** the argument holds against the code | `resueltos`, as `no aplica: <the author's reason>`. The finding is discarded this run and every later run, because the thread is re-read each time |
| `cerrado` | thread is resolved, by anyone | `resueltos` |
| `dice-resuelto-sigue-presente` | reply claims it is fixed **but** the problem is still in the current code | `pendientes`; local report says why the claim does not hold |
| `refutado` | reply argues it does not apply **but** the argument does not hold against the code | `pendientes`; local report says why the argument does not hold |
| `pregunta-sin-responder` | reply asks us something and we have not answered | `pendientes`; local report lists it first, and an answer may be published through step 7 |
| `sin-atender` | no reply, or no claim, and the problem is still present | `pendientes` |

`resuelto-confirmado` is checked first: once the problem is gone, the thread is
settled, and nothing the author wrote or did not write changes that.

No state file is kept. Every disposition is derived from the PR on each run, so
an accepted rebuttal keeps holding without anything being remembered locally.

`sin-atender` and `dice-resuelto-sigue-presente` describe a problem that is
still live. Both withhold the approval in the resumen block, the same way an
open thread from another reviewer does. `resuelto-confirmado`,
`no-aplica-aceptado` and `cerrado` are settled and leave it available.

## Check whether the problem is still present

For every open thread of ours: whether the problem is gone decides between
`resuelto-confirmado` and every live disposition. A resolved thread is `cerrado`
and needs no check.

The thread's stored `line` is where the comment was anchored when it was posted.
Code moves. Read the file at its current state and find the construct the comment
described, then report that line. `isOutdated` on the thread is a hint that it
moved, not proof that it was fixed.

Gone from the current diff but still in the file: the problem is still present.
The diff boundary governs what this skill *finds*, not whether an existing
finding was resolved.

## Feed the round

This pass hands step 7 two lists for `summary.json` and the ids for
`resolve.json`. Each list item is one line, shaped by the round-body section of
`comment-form.md`.

- **`pendientes`** — every live thread, every round, at its current line, with
  the first comment's `url`. A live problem stays visible until it is settled.
- **`resueltos`** — settled threads the author has not been told about yet. Read
  the bodies of our earlier rounds (`gh pr view <n> --json reviews`, already
  collected): a thread whose line already appears under `Resueltos` in one of
  them is left out. Round 1 has no earlier round, so it has no `resueltos`.
- **`resolve.json`** — the node `id` of every open `resuelto-confirmado` thread.
  The question in the resumen block names how many, and the publisher refuses
  any thread this account did not open with a severity marker.

The disposition names never reach the lists. The author reads what was found
and where, not how this pass classified it.

## Answer a question

A `pregunta-sin-responder` is the only disposition that can produce new posted
text. Conditions, both required:

- The answer was printed to the user with the findings, and the resumen block's
  question named the reply among what a yes authorizes.
- The text follows the reply section of `comment-form.md`.

The answer goes as a reply on that thread, carrying its comment id, never as a
new comment. One answer per thread per run.

On a docs-only diff the reply rides in the same publisher run as the approval;
the publisher sends it first.

## Ledger

One row, with the disposition counts:

```
| prior-reviews | ran | 7 hilos nuestros: 2 resueltos, 1 no-aplica, 3 sin atender, 1 pregunta |
```

The ledger row stays local. What the author sees of this pass is the round
body's `Resueltos` and `Pendientes` lists.
