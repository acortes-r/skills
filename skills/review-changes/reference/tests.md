---
name: tests
description: Test-coverage pass for `review-changes`, on diffs that change runtime behavior.
---

# Tests

Use this profile only inside `review-changes`. Activate when the diff changes
runtime behavior: application code, not only tests, configuration, or
documentation.

The question is narrow: **which behavior this diff adds or changes would break
without any test going red?** Every finding names that behavior as a test case
someone can write.

## Before looking

- Find the repository's test suite and how it maps code to tests: the test
  directory, the naming convention, the runner in `package.json`, `Gemfile`,
  `Makefile`, or `pyproject.toml`. No test suite at all: record
  `skipped:no-test-suite` and stop.
- For each changed behavior, look for a test that exercises it, in the diff or
  already on the base branch. A test that already covers it ends the search.

## Scope

**Untested behavior**
- A new branch, guard, or error path with no test that reaches it
- A changed calculation, filter, or mapping whose existing test still passes
  against the old result
- A bug fix with no test that fails on the base branch

**Tests weakened by this diff**
- An assertion loosened to match the new output: an exact value turned into a
  `be_truthy`, a count turned into `> 0`, a snapshot regenerated wholesale
- An expected value changed in the same diff as the code that produces it, with
  nothing in the PR saying the old value was wrong

**Tests that cannot fail**
- A test with no assertion, or one that asserts on the mock it set up
- A test whose setup short-circuits the code path it names

## Flag only

- You can name the case: the input or state, and the result a test should
  expect
- No existing test, in the diff or on the base branch, already pins that result

A finding's failing input is that case, and its wrong result is the regression
that would ship with every test green. Its fix is the test to write, named by
file and case, never "add tests".

## Do not flag

- Pure refactors whose existing tests already pin the behavior
- Coverage percentages, or a missing test file for a file with no logic
- Skip markers, disabled CI steps, or test configuration — `gates.md` owns
  those
- More than one finding for the same untested behavior

## Severity

- 🟠 important: the untested behavior moves money, writes or deletes data, or
  guards access
- 🔵 suggestion: everything else

## Output

Per finding: `path`, `line`, `severity`, `case` (input and expected result),
`test_file` (where the test belongs), `confidence`. Anchor on the changed line
that introduces the behavior.
