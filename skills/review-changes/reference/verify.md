---
name: verify
description: Adversarial verification pass for `review-changes`. Discards only.
---

# Verify

Use this profile only inside `review-changes`, after candidates exist.

Your job is to try to refute each candidate. Confirm, adjust severity with
evidence, or discard. **Never add a finding.** A candidate you cannot support
is dropped, not softened.

## Input

Per candidate: `path:line`, the claimed failing input, the claimed wrong
result, the proposed fix, the severity, the source profile, and the diff.

## Discard when

- No concrete input produces the described behavior. A mechanism with no
  triggering input is speculation.
- The problem already existed on the base branch and this diff does not make it
  worse or more reachable.
- The failure depends on a fact the repository does not establish — table size,
  traffic, deployment topology, a library that is not a dependency, a database
  version that is not declared. Name the missing fact in the discard reason.
- A configured and CI-enforced linter, formatter, or type checker already
  reports it.
- The fix contradicts a quoted project rule.
- The candidate recommends splitting work into separate branches. When it also
  carries an independently evidenced technical risk, keep only the risk and
  drop the branch advice.

## Adjust severity when

- The failing path is real but reachable only through a state the diff makes
  unlikely: lower it.
- The failing path destroys or corrupts stored data, or removes an
  authorization boundary: raise it to `critical` and say which.

Severity moves need the same evidence standard as the finding.

## Confidence

Score each survivor `0-100`.

- Below 70: drop to `suggestion`, or discard if it was already `suggestion`.
- A rule-compliance finding without an exact quote and heading scores below 70
  by definition.

## Output

Per candidate:

- `verdict`: `confirmed | adjusted | discarded`
- `confidence`: `0-100`
- `reason`: one line. For a discard, name the specific check that failed.
- `severity`: final level for confirmed and adjusted candidates

Return counts: candidates in, confirmed, adjusted, discarded. The `review-changes`
ledger row `verify` uses them.
