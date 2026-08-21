# review-changes

Non-blocking code review. Loads the project's own documented rules first,
verifies every finding adversarially, drops what other reviewers already said,
and publishes the rest as GitHub suggestions.

**It never approves and never requests changes.** Approval stays a human action.

## Install

```bash
npx skills add <your-github-user>/skills --skill review-changes
```

## Invoke

```text
Use review-changes on https://github.com/org/repo/pull/341
Use review-changes on the current diff
```

Or by command name in hosts that expose one: `/review-changes`.

## What it does differently

| | |
|---|---|
| **Project rules are first-class** | Reads `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` — including the nested ones in every directory the diff touches — plus `.cursor/rules`, `CONTRIBUTING.md`, and `docs/adr`. Rule findings quote the exact text and heading. Missing rule files are reported as a gap, not skipped silently. |
| **Adversarial verification** | A second pass tries to refute every candidate and can only confirm, adjust, or discard. It can never add a finding. |
| **Deduped against other reviewers** | Collects existing inline threads, PR-level comments, and bot summaries — CodeRabbit, Codacy, Sonar, Copilot, humans — and drops findings already covered. Resolved threads stay closed. |
| **Never blocks a merge** | One review with `event: COMMENT`. `APPROVE` and `REQUEST_CHANGES` are impossible by construction. |
| **Linters filter noise** | A finding the repository's configured and CI-enforced linter already reports is dropped and counted, not posted. |
| **Visible coverage** | Every pass reports `ran`, `skipped:<reason>`, or `not-run:<reason>`. What was not reviewed is stated. |

## Comment style

Posted comments are telegraphic Spanish: one line for what fails, one line for
the failing input, and a `suggestion` block when the fix replaces a line.
Two lines of prose, ceiling. See [reference/comment-form.md](reference/comment-form.md).

Posted text is independent of the session's conversation style.

## Publishing, and checking first with `--dry-run`

Nothing reaches a pull request without two gates: the skill prints the exact
comment bodies and waits for your go, and the publisher itself can be run
without sending anything.

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
post_review: inline=1 degraded=2 already-posted=1
```

Read that last line before publishing:

| Counter | Meaning |
|---|---|
| `inline` | anchored to a line inside a diff hunk |
| `degraded` | the target is not in the diff, so it moves into the review body instead of being dropped |
| `already-posted` | identical comment already on the PR, skipped so a retry cannot duplicate |

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

## Layout

```
review-changes/
├── SKILL.md                      # process and output contract
├── reference/
│   ├── project-rules.md          # rule discovery and precedence
│   ├── verify.md                 # adversarial pass, discards only
│   ├── existing-comments.md      # dedupe against other reviewers
│   ├── comment-form.md           # shape of posted text
│   ├── migrations.md             # persistence safety and necessity
│   ├── backend.md                # server correctness and contracts
│   ├── frontend.md               # client state, a11y, weight
│   └── security.md               # authz, injection, secrets
├── scripts/post_review.py        # deterministic publisher
├── evals/evals.json              # 8 scenarios
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
resolution. It stacks with other review tools by adding its own section rather
than replacing theirs.
