---
name: backend
description: Server-side correctness and contract pass for `review-changes`.
---

# Backend

Use this profile only inside `review-changes`. Activate when the diff changes
controllers, services, jobs, background workers, endpoints, serializers,
queries, or middleware.

## Scope

**Contract**
- Response shape or status code changed in a way existing clients do not expect
- A required request field added without a default or migration path
- Error responses that leak internals or lose the error class

**Correctness**
- Nil, empty-collection, and boundary cases on paths the diff introduces
- Off-by-one and inclusive/exclusive bounds in pagination, ranges, slicing
- Time zone and DST handling where a date crosses a boundary
- Float arithmetic on money
- Concurrency: read-modify-write without a lock, non-atomic counters, a check
  and its dependent action in separate statements

**Data access**
- A query inside a loop where a batched or joined form exists
- A new query path with no index behind its filter or sort
- Unbounded result sets: no limit, no pagination, `find_all` on a growing table

**Transactions**
- Non-atomic multi-write sequences that can leave partial state
- External calls, enqueues, or emails inside a transaction that can roll back
- Work that must be idempotent but keys on nothing stable — retried jobs,
  webhook handlers, payment callbacks

**Resilience**
- An external call with no timeout
- Retries with no cap or no backoff
- A swallowed exception that hides a failed write

## Flag only

- The path is reachable from the changed code
- A concrete input or interleaving produces the wrong result
- The diff introduces it, or makes an existing one materially more reachable

## Do not flag

- Style, naming, or layout the configured linter reports
- Missing tests — `review-changes` reports that from the diff, not here
- Frontend, migration, or security concerns owned by other profiles
- Architecture preferences with no failing input

## Output

Per finding: `path`, `line`, `severity`, `failing_input`, `wrong_result`, `fix`,
`confidence`.
