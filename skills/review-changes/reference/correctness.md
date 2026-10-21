---
name: correctness
description: Logic-error pass for `review-changes`, run on every diff that changes behavior.
---

# Correctness

Use this profile only inside `review-changes`. It runs on every diff that
changes behavior, whatever the files are. The other profiles own their stack;
this one owns the logic in between, which no file pattern routes.

Read each changed hunk as the author's claim of what the code now does, then
look for the input where the claim is false.

## Scope

**Logic**
- An inverted or incomplete condition: `&&` where `||` was meant, a negation
  dropped, a branch that can never run
- The wrong variable, field, or argument order on a call whose parameters share
  a type
- Nil, empty-collection, and boundary cases on paths the diff introduces
- Off-by-one and inclusive/exclusive bounds in loops, ranges, and slicing
- An early return, `break`, or `next` that skips work the rest of the function
  still owes

**Contracts with callers**
- A changed signature, return value, raised error, or default whose callers
  were not updated. Grep for every caller of each changed public function,
  method, or exported symbol; the diff alone does not show them.
- A function that now returns a different type or shape on one branch
- A renamed key, event name, or enum value still read by its old name somewhere

**State**
- A mutation of an argument, a shared constant, or a memoized value that the
  caller still uses afterwards
- A cache or memo keyed on less than the inputs that change its result

**Errors**
- A new rescue or catch that is wider than the failure it handles
- An error path that returns a success value, or a success path that leaves the
  error variable set

## Flag only

- A concrete input or call site produces the wrong result
- The path is reachable from the changed code or from a caller you found

A broken caller outside the diff is anchored on the changed line that broke it,
never on the caller itself.

## Do not flag

- Concerns owned by `backend.md`, `frontend.md`, `migrations.md`, or
  `security.md` when that profile is routed for the same file
- Naming, style, or layout
- A refactor preference with no failing input

## Output

Per finding: `path`, `line`, `severity`, `failing_input`, `wrong_result`, `fix`,
`confidence`. A broken caller adds `caller`: the `path:line` that breaks.

Completion: every changed public symbol has its callers checked. The ledger note
says how many.
