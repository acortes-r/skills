# review-changes

Non-blocking code review. Loads the project's own documented rules first,
verifies every finding adversarially, drops what this skill and other reviewers
already said, and publishes the rest as GitHub suggestions.

**It never requests changes.** It approves exactly one thing: a diff that
changes no behavior, and only after you say to send it.

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
| **Never blocks a merge** | `REQUEST_CHANGES` is impossible by construction. The default event is `COMMENT`. |
| **Docs-only diffs get approved, not peppered** | A change that alters no behavior — documentation, OpenSpec markdown, a comment-only edit to a code file — gets one `APPROVE` with the notes in its body instead of a wall of inline suggestions. Nothing worth saying means a bare approval, no body. It asks you first, every time. |
| **The summary states the count and the question** | Every run reports how many comments there are by severity, whether the PR can be approved, and asks for the one thing a yes would authorise. |
| **Linters filter noise** | A finding the repository's configured and CI-enforced linter already reports is dropped and counted, not posted. |
| **Visible coverage** | Every pass reports `ran`, `skipped:<reason>`, or `not-run:<reason>`. What was not reviewed is stated. |

## The resumen block

Every run ends with the same three lines, printed before the comment bodies and
repeated at the top of the report:

```
7 comentarios: 1 🔴 critical, 2 🟠 important, 4 🔵 suggestion.
Se puede aprobar: no — hay 1 critical.
¿Publico los 7 comentarios?
```

```
0 comentarios. Solo documentación, sin notas.
Se puede aprobar: sí.
¿Apruebo el PR sin comentario?
```

```
0 comentarios.
Se puede aprobar: sí, pero lo apruebas tú — este skill no aprueba código.
Nada que enviar.
```

The third line is a question whenever something would be sent, and it names
exactly what a yes authorises. Under `--dry-run` it says `Dry run: no se envía
nada.` instead, because there is no go to give.

## Comment style

Posted comments are telegraphic Spanish: one line for what fails, one line for
the failing input, and a `suggestion` block when the fix replaces a line.
Two lines of prose, ceiling. See [reference/comment-form.md](reference/comment-form.md).

Posted text is independent of the session's conversation style.

## Docs-only diffs

Some pull requests change nothing that runs. Peppering them with inline
suggestions is noise, so they take a different path: one review, `event:
APPROVE`, every note inside the body.

A diff qualifies when **every** changed file is either documentation, or a code
file whose every added and removed line is a comment or a docstring.

| Counts as documentation | Does not, and disqualifies the diff |
|---|---|
| `*.md`, `*.mdx`, `*.rst`, `*.adoc`, `*.txt` | `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.cursor/rules/*`, `CONTRIBUTING.md`, `docs/adr/**` — rule contracts, not prose |
| `openspec/**`, `docs/**` | `.github/workflows/*.yml`, `Dockerfile`, `Makefile`, `*.sql`, `package.json`, lockfiles, `.env*` |
| `README*`, `CHANGELOG*`, `LICENSE*` | a comment that is a directive: `# rubocop:disable`, `// @ts-ignore`, `# noqa`, build tags |

One file failing both conditions sends the whole diff back to the normal
`COMMENT` review. When the classification is uncertain, it is a behavior change:
an unnecessary comment is cheaper than an approval nobody read.

The approval is never automatic. The body is printed first, it says plainly that
sending it approves the PR, and it waits for a go that covers the approval.
`--dry-run` forbids it outright, and the same head commit is never approved
twice.

The prose is still reviewed. A docs-only diff can document an endpoint that does
not exist or leave an OpenSpec task claiming something the code never did; those
become notes in the approval body.

A clean review of a diff that *does* change behavior still ends in the clean
message, for a human to approve. Approving code is not something this skill does.

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

Without `--approve`, `event` is `COMMENT`. The script has no code path that
produces `REQUEST_CHANGES` at all.

### Approving a docs-only diff

```bash
python3 scripts/post_review.py --repo owner/name --pr 402 \
  --approve --notes notes.json --dry-run   # inspect first
python3 scripts/post_review.py --repo owner/name --pr 402 \
  --approve --notes notes.json             # then approve
```

`notes.json` is a JSON array of already-formatted one-line strings:

```json
[
  "🔵 `openspec/specs/pagos.md` — el endpoint `POST /refunds` no existe en el código.",
  "🔵 `README.md` — el badge apunta al repo anterior."
]
```

Omit `--notes` to approve with no body at all. A docs-only diff with nothing
wrong in it gets an approval and silence — a comment announcing that there is
nothing to comment is still noise on the pull request.

`--approve` refuses `--findings` and `--replies`: the mode creates no inline
comments, so an approval can never carry a code finding along with it. An answer
owed to the author goes in its own run, before the approval. The approval also
pins the head commit it approved, and the script refuses to approve that same
commit twice.

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
│   ├── docs-only.md              # diffs that change no behavior, and the approve flow
│   ├── prior-reviews.md          # our own earlier threads, and what the author replied
│   ├── existing-comments.md      # dedupe against other reviewers
│   ├── comment-form.md           # shape of posted text
│   ├── migrations.md             # persistence safety and necessity
│   ├── backend.md                # server correctness and contracts
│   ├── frontend.md               # client state, a11y, weight
│   └── security.md               # authz, injection, secrets
├── scripts/post_review.py        # deterministic publisher
├── evals/evals.json              # 28 scenarios
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
discussion on someone else's. It approves only a diff that changes no behavior,
never code. It stacks with other review tools by adding its own section rather
than replacing theirs.
