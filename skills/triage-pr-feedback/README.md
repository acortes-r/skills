# triage-pr-feedback

Reads the open feedback on a pull request (review threads, top-level comments, and the outside-diff comments bots like CodeRabbit put in their review bodies), checks each one against the code, and answers with one table: which items apply, which don't, and why, with the file and line that settles it.

It changes nothing. No edits, commits, replies, or resolved threads until you say which items to apply.

## Install

```bash
npx skills add <your-github-user>/skills --skill triage-pr-feedback
```

## Invoke

```text
/triage-pr-feedback
/triage-pr-feedback 123
/triage-pr-feedback https://github.com/acme/app/pull/123
revisa los comentarios del PR y dime cuáles aplican
```

## What you get

| # | Author | Level | Where | Comment | Applies? | Why |
|---|---|---|---|---|---|---|
| 1 | reviewer | Medium | `src/checkout/recover.js:48` | Refused default leaves an empty selection | ✅ yes | The reload falls back to `{}`; the next click pays with no method |
| 2 | reviewer | Medium | `src/checkout/recover.js:31` | Express wallet marks the card form | ❌ no | The wallet only renders when it is the selected method (`WalletForm.js:22`) |

Then the counts, the items one fix would close together, a recommendation for every "your call" row, and one question: what to apply.

## How it judges

[reference/rubric.md](reference/rubric.md) holds the rules. It starts from compound-engineering's `ce-resolve-pr-feedback` rubric (default to "applies", divert only on a concrete signal) and adds:

- verify the reviewer's premise in the code that produces the state, across repositories when the claim depends on a backend contract;
- weigh the failure direction: a dead end applies, a safe fallback rarely does;
- when the same block draws a third round of findings, say the rounds are not converging and recommend declining or moving the logic, instead of one more patch.

## Requirements

- An authenticated `gh`.
- Optional: the compound-engineering plugin. When its `ce-resolve-pr-feedback` fetch script is installed, the skill uses it for paginated fetching.
