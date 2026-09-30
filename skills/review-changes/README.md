# review-changes

Non-blocking code review. Loads the project's own documented rules first,
verifies every finding adversarially, drops what this skill and other reviewers
already said, and publishes the rest as GitHub suggestions.

**It never approves and never requests changes.** Approval stays a human action.

## Install

```bash
npx skills add <your-github-user>/skills --skill review-changes
```

## Invoke

```text
Use review-changes on https://github.com/org/repo/pull/341
Use review-changes on the current diff
Use review-changes on PR 341 --dry-run
```

Or by command name in hosts that expose one: `/review-changes`.

## What it does differently

| | |
|---|---|
| **Project rules are first-class** | Reads `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` — including the nested ones in every directory the diff touches — plus `.cursor/rules`, `CONTRIBUTING.md`, and `docs/adr`. Rule findings quote the exact text and heading. Missing rule files are reported as a gap, not skipped silently. |
| **Adversarial verification** | A second pass tries to refute every candidate and can only confirm, adjust, or discard. It can never add a finding. |
| **Never repeats itself** | On a re-review it finds its own earlier threads, reads what the author replied, and decides from that: fixed, does not apply, or still open. A comment it already made is never made again — not reworded, not at a new line after a rebase. |
| **Deduped against other reviewers** | Collects existing inline threads, PR-level comments, and bot summaries — CodeRabbit, Codacy, Sonar, Copilot, humans — and drops findings already covered. Resolved threads stay closed. |
| **Never blocks a merge** | One review with `event: COMMENT`. `APPROVE` and `REQUEST_CHANGES` are impossible by construction. |
| **Linters filter noise** | A finding the repository's configured and CI-enforced linter already reports is dropped and counted, not posted. |
| **Visible coverage** | Every pass reports `ran`, `skipped:<reason>`, or `not-run:<reason>`. What was not reviewed is stated. |

## Comment style

Posted comments are telegraphic Spanish: one line for what fails, one line for
the failing input, and a `suggestion` block when the fix replaces a line.
Two lines of prose, ceiling. See [reference/comment-form.md](reference/comment-form.md).

Posted text is independent of the session's conversation style.

## Re-reviewing a pull request

Run it again on the same PR and it reads its own earlier threads first. Each one
gets a disposition from what the author replied:

| Reply | Disposition | What happens |
|---|---|---|
| "ya quedó" / "fixed in abc123", and the problem is gone | `resuelto-confirmado` | silent, ledger count |
| explains why it does not apply, and the argument holds | `no-aplica-aceptado` | silent, and it keeps holding on later runs |
| thread resolved by anyone | `cerrado` | silent, ledger count |
| claims it is fixed, but the problem is still there | `dice-resuelto-sigue-presente` | local report only |
| argues it does not apply, but the argument does not hold | `refutado` | local report only, with why |
| asks us something | `pregunta-sin-responder` | local report, and an answer can be published |
| nothing, or an acknowledgement with no claim | `sin-atender` | local report only |

Only `pregunta-sin-responder` can produce new posted text, and only through the
same gate as a finding: printed first, sent after your go, as a reply on that
thread. Nothing else in this table ever reaches GitHub — no nudges, no "this is
still open", no reposts.

Nothing is remembered between runs. Every disposition is re-derived from the PR
itself, so an accepted rebuttal keeps being accepted without any local state.

A rebase that moves every line does not cause reposts: an already-posted comment
is matched by path and opening text, never by line number.

## Publishing, and checking first with `--dry-run`

Nothing reaches a pull request without two gates: the skill prints the exact
comment bodies and waits for your go, and the publisher itself can be run
without sending anything.

`--dry-run` works at both levels. Passed to the skill it makes the whole run
read-only — every pass still runs, nothing is ever sent, and that holds even if
you then say to go ahead:

```text
Use review-changes on PR 341 --dry-run
```

Passed to the publisher it shows the exact payload:

```bash
# 1. See the payload. No network write, no review created.
python3 scripts/post_review.py --repo owner/name --pr 341 \
  --findings findings.json --dry-run

# 2. Same command without the flag publishes it.
python3 scripts/post_review.py --repo owner/name --pr 341 \
  --findings findings.json
```

`--dry-run` still reads the PR — it fetches the diff and the existing comments —
so it reports the real outcome rather than a guess:

```
post_review: dry run. Payload that would be sent:
{
  "event": "COMMENT",
  "body": "3 comentarios. Ninguno bloquea el merge.",
  "comments": [
    { "path": "app/models/user.rb", "line": 11, "side": "RIGHT", "body": "🟠 ..." }
  ]
}
post_review: inline=1 degraded=2 replies=0 already-posted=1
```

Read that last line before publishing:

| Counter | Meaning |
|---|---|
| `inline` | anchored to a line inside a diff hunk |
| `degraded` | the target is not in the diff, so it moves into the review body instead of being dropped |
| `replies` | answers posted on our own earlier threads |
| `already-posted` | same path and opening text already on the PR, skipped so neither a retry nor a re-review can duplicate. The line number is not part of the match, so code that moved is still recognised |

A high `degraded` count usually means the findings point at context the diff did
not change — worth rechecking the line numbers before sending.

Whether or not you pass the flag, `event` is `COMMENT`. The script has no code
path that produces `APPROVE` or `REQUEST_CHANGES`.

### `findings.json`

```json
[
  {
    "path": "app/models/user.rb",
    "line": 11,
    "side": "RIGHT",
    "body": "🟠 `user` puede ser nil — `find_by` devuelve nil y `.email` levanta NoMethodError.\n\n```suggestion\n    return unless user\n```"
  }
]
```

`side` defaults to `RIGHT`. Omit `line` for a finding with no single-line
anchor; it goes to the review body. `body` should already be formatted by
[reference/comment-form.md](reference/comment-form.md).

An empty array publishes nothing and exits cleanly, which is the same outcome as
a clean review.

### `replies.json`

```json
[
  {
    "in_reply_to": 123456789,
    "body": "El retry viene del webhook de Stripe, no del cliente."
  }
]
```

`in_reply_to` is the id of the comment being answered; the reply lands on that
thread. Pass it with `--replies`, alone or together with `--findings`. A reply
whose text is already on the thread is skipped.

## Layout

```
review-changes/
├── SKILL.md                      # process and output contract
├── reference/
│   ├── project-rules.md          # rule discovery and precedence
│   ├── verify.md                 # adversarial pass, discards only
│   ├── prior-reviews.md          # our own earlier threads, and what the author replied
│   ├── existing-comments.md      # dedupe against other reviewers
│   ├── comment-form.md           # shape of posted text
│   ├── migrations.md             # persistence safety and necessity
│   ├── backend.md                # server correctness and contracts
│   ├── frontend.md               # client state, a11y, weight
│   └── security.md               # authz, injection, secrets
├── scripts/post_review.py        # deterministic publisher
├── evals/evals.json              # 16 scenarios
└── agents/openai.yaml            # host adapter
```

## Requirements

- `git`
- `python3` for the publisher — no `jq` needed
- `gh` 2.40+, authenticated, for pull-request features

Without `gh` the skill reviews the local diff and reports reduced context.
Publishing and deduplication are then recorded as `not-run:no-pr-context`.

## Scope

One target per run: one PR, one branch comparison, or one working tree. No
monorepo submodule walking, no PR stacks, no remediation plans, no thread
resolution. It answers a question on one of its own threads; it never opens a
discussion on someone else's. It stacks with other review tools by adding its own section rather
than replacing theirs.
