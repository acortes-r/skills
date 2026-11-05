# Verdict rubric

Adapted from compound-engineering's `ce-resolve-pr-feedback` evaluation rubric, plus lessons from real triage runs.

## Default to "applies"

Most review feedback, nits included, is correct and worth fixing. Mark an item ✅ (applies) unless reading the code gives you a **concrete signal** to divert. "I'm uneasy" or "it's out of the ticket's scope" is not a signal; "I read the callers and this breaks X" is. Small real improvements still apply; the bar for ❌ is "no benefit" or "the claim is false", never "minor".

Judge on the merits whoever wrote it: a bot can be right and a senior reviewer wrong.

## Verify the premise

A reviewer, especially a bot, sees the diff, not the system. Before accepting a failure scenario, confirm that its premise can happen:

- **Read where the claimed state comes from.** A scenario like "the buyer pays with an express wallet while the card is selected" stands or falls on whether that UI path exists. Find the component that renders it.
- **Follow the contract across repositories.** When the claim depends on what the backend sends or accepts, read the backend code (the open PR or the deployed branch), not your memory of it. Name the file and method that decides it.
- **Check git history for intent.** `git log`/`git blame` on deliberate-looking code, and the PR description, before overriding it.

A premise you could not confirm or refute is 🔎, with what you checked and what would settle it.

## Verdicts

| Verdict | When | Evidence the row must carry |
|---|---|---|
| ✅ yes | The issue exists at the PR head and the fix is bounded | The line that shows it; the fix in a few words |
| ⚠️ partly | Real, but only part is worth doing here, or only on some tenants/flows | Which part applies and why the rest waits |
| ❌ no | The premise is false, the code already handles it, the concern no longer exists at this head, or the fix would make the code worse | The file and line that refutes it, or the rule the fix would break |
| 🔎 your call | A product or business call, a cross-team contract you cannot confirm, or a fix whose risk you cannot bound after reading the callers | The options, the trade-off, and your lean |

Out of scope is not ❌ by itself: say "applies, follow-up" with the reason (it changes every flow of X, it needs another team) so the user can open a ticket.

## Reasoning across items

- **Cluster by root assumption.** If one source is wrong on one premise, re-check its sibling findings for the same premise.
- **Converging asks are a strong signal.** The same change from two independent reviewers rarely deserves ❌.
- **Fix the class.** When an accepted finding has twins this PR introduced (another caller with the same rethrow, another branch with the same gap), list them in the same row so one fix closes them all. Leave out pre-existing occurrences the PR did not touch.
- **Check that the PR's own fixes are not the regression.** A new finding often lands on code the previous round added. Say so in the row; the user wants to know.

## Failure direction

Ask which way a gap fails:

- **Dead end**: the user is left stuck with no message, a broken selection, a redirect to the wrong place. These apply.
- **Safe fallback**: the code shows the generic error or the old behavior, and the user can recover. A finding that only turns a safe fallback into a nicer outcome is usually ❌ or a follow-up, unless it is cheap and contained.

## Repeated rounds on one block

When this is the third round of findings on the same function or block, each fix copying one more rule from elsewhere (another filter, another mapping), stop recommending patches. Mark the new item with the failure direction it has, and recommend either declining it (when it already fails safe) or moving the logic to the place that owns it, as a follow-up. Say plainly that the rounds are not converging.

## Outdated threads

When a thread is outdated, look for the concern at the current location (line, then an anchor from the comment, searched once in the same file). Gone → ❌ "no longer at this head" with what you searched. Moved to another file → 🔎.
