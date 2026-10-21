---
name: spec
description: Diff-against-OpenSpec pass for `review-changes`, in both directions.
---

# Spec

Use this profile only inside `review-changes`. Activate when an OpenSpec change
governs the diff. It checks that the code does what the change promised, and
that it does nothing the change never asked for.

## Find the change

An OpenSpec change is a directory `openspec/changes/<name>/`, outside
`openspec/changes/archive/`. It governs the diff when any of these holds:

1. the diff touches files inside it
2. the PR body or a commit message names it, or links to it
3. the branch name contains `<name>`

No change found: record `skipped:no-openspec-change` and stop. Several found:
review against each, and name which one each finding comes from.

Read, when they exist: `proposal.md`, `tasks.md`, `design.md`, and every
`specs/**/spec.md` delta. On a PR, read them at the head commit: the diff may be
the one updating them.

## Forward: promised, not delivered

- A task marked `- [x]` in `tasks.md` whose work is in neither the diff nor the
  base branch
- A scenario (`#### Scenario:` with its WHEN/THEN) under an `ADDED` or
  `MODIFIED` requirement that the code contradicts: name the WHEN input and the
  result the code gives instead of the THEN
- A `REMOVED` requirement whose behavior the code still has

Unchecked tasks are unfinished work, not findings.

## Reverse: delivered, not promised

Behavior the diff introduces that no requirement, scenario, or task asks for:
a new validation, a dropped case, a changed default, a new endpoint or field.
Report it as a 🔵 suggestion whose failing input is the case that now behaves
differently, and whose fix is either adding it to the spec or removing it from
the code. It asks whether the behavior is intended; it never claims it is
wrong.

Refactors, logging, and internal structure are not behavior. Leave them out.

## Settled decisions

A decision recorded in `design.md` is settled. Pass each one to `verify.md`,
which discards a candidate that only prefers a different approach to a settled
decision. A real defect inside a settled approach keeps its severity.

## Severity

- 🟠 important: a contradicted scenario, a `[x]` task with no work behind it,
  or a removed requirement still in the code
- 🔵 suggestion: every reverse finding

## Output

Per finding: `path`, `line`, `severity`, `change` (the change's name),
`spec_quote` (the scenario, requirement, or task line, verbatim, with its file),
`failing_input`, `wrong_result`, `fix`, `confidence`. A `[x]` task with no work
anchors on the task line in `tasks.md` when that file is in the diff; otherwise
it goes in the round body.
