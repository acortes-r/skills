---
name: gates
description: Silent-pass pass for `review-changes`, on diffs that touch what decides whether CI goes green.
---

# Gates

Use this profile only inside `review-changes`. Activate when the diff touches a
**gate**: anything that decides whether a change is allowed through. Size does
not matter here. A one-line gate change can let every later bug through.

A gate fails in one direction that hurts: it goes green while the thing it
guards is red. That is a **silent pass**, and it is the only thing this profile
looks for.

## What counts as a gate

- CI and deploy definitions: `.github/workflows/**`, `.gitlab-ci.yml`,
  `.circleci/**`, `Jenkinsfile`, `buildkite/**`, deploy scripts
- Test runner and coverage configuration: `jest.config.*`, `vitest.config.*`,
  `.rspec`, `spec_helper.rb`, `rails_helper.rb`, `pytest.ini`, `conftest.py`,
  `.simplecov`, `codecov.yml`, coverage thresholds in `package.json`
- Linter and type-checker configuration, when the diff disables or narrows it
- Test helpers, shared mocks, stubs, fixtures, and factories that many tests
  load
- Skip markers added in test files: `skip`, `xit`, `xdescribe`, `pending`,
  `.only`, `@pytest.mark.skip`, `t.Skip`

## Scope

**Steps that no longer fail**
- `continue-on-error: true`, `|| true`, `set +e`, `allow_failure`, an exit code
  swallowed in a pipe
- A required check removed, renamed, or moved behind an `if:` that is false on
  pull requests
- A path filter, matrix, or test selection that no longer includes code this
  diff or the repository changes

**Tests that no longer run**
- A skip marker or `.only` added, or a test file moved out of the runner's glob
- A retry or flaky-test quarantine that masks a deterministic failure
- A timeout raised until a hang counts as a pass

**Checks that no longer check**
- A coverage threshold lowered, or files added to the coverage ignore list
- A linter or type-checker rule disabled globally to quiet one file
- A shared mock or stub that now replaces the code under test, or returns a
  success the real dependency would not
- A fixture or factory changed so that a validation the tests relied on never
  fires

## Flag only

- You can name the real failure that would now go green: what breaks, and which
  check used to catch it
- The weakening comes from this diff

## Do not flag

- A gate made stricter
- A skip with a linked issue and a reason, when the project rules allow it
- Pipeline speed or cost

## Severity

- 🔴 critical: a required check on the default branch can no longer fail
- 🟠 important: any other silent pass

## Output

Per finding: `path`, `line`, `severity`, `failure_that_passes` (what breaks
and the check that would have caught it), `fix`, `confidence`.
