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
| `resuelto-confirmado` | reply claims it is fixed **and** the problem is gone from the current diff | silent; ledger count only |
| `no-aplica-aceptado` | reply argues it does not apply **and** the argument holds against the code | silent; ledger count only. The finding is discarded this run and every later run, because the thread is re-read each time |
| `cerrado` | thread is resolved, by anyone | silent; ledger count only |
| `dice-resuelto-sigue-presente` | reply claims it is fixed **but** the problem is still in the current diff | local report; never published |
| `refutado` | reply argues it does not apply **but** the argument does not hold against the code | local report, with why it does not hold; never published |
| `pregunta-sin-responder` | reply asks us something and we have not answered | local report, listed first; an answer may be published through step 7 |
| `sin-atender` | no reply, or no claim, and the problem is still present | local report; never published |

No state file is kept. Every disposition is derived from the PR on each run, so
an accepted rebuttal keeps holding without anything being remembered locally.

## Check whether the problem is still present

Only for threads that need it: `resuelto-confirmado` vs `dice-resuelto-sigue-presente`,
and `sin-atender`. Never for all of them.

The thread's stored `line` is where the comment was anchored when it was posted.
Code moves. Read the file at its current state and find the construct the comment
described, then report that line. `isOutdated` on the thread is a hint that it
moved, not proof that it was fixed.

Gone from the current diff but still in the file: the problem is still present.
The diff boundary governs what this skill *finds*, not whether an existing
finding was resolved.

## Answer a question

A `pregunta-sin-responder` is the only disposition that can produce new posted
text. Conditions, both required:

- The answer was printed to the user with the findings, and the resumen block's
  question named the reply among what a yes authorizes.
- The text follows the reply section of `comment-form.md`.

The answer goes as a reply on that thread, carrying its comment id, never as a
new comment. One answer per thread per run.

On a docs-only diff the reply is sent in its own publisher run, before the
approval: `--approve` refuses `--replies`.

## Ledger

One row, with the disposition counts:

```
| prior-reviews | ran | 7 hilos nuestros: 2 resueltos, 1 no-aplica, 3 sin atender, 1 pregunta |
```

Never post any of this. The author does not need to know a re-review ran.
