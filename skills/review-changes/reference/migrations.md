---
name: migrations
description: Database and migration safety pass for `review-changes`.
---

# Migrations

Use this profile only inside `review-changes`. Activate whenever the diff
changes a persistent data contract: migration or DDL files, schema snapshots,
tables, columns, indexes, constraints, triggers, partitions, extensions, data
backfills, dual writes, or ORM model changes that imply stored-data transition.

Do not activate for query-only changes that leave the stored contract intact —
those belong to `backend.md`. Do not activate because a DTO, JSON schema, API
schema, or validation schema changed.

## Required context

Inspect the smallest supporting context that shows how the migration executes:

- migration-safety tooling in the dependency manifest: `strong_migrations`,
  `zero_downtime_migrations`, `django-safemigrate`, `atlas`, `squawk`
- the declared database engine and version — lock behavior and online DDL
  differ per engine and version
- prior migrations and the current schema, to spot duplicate or conflicting state
- the application consumers of the changed columns or tables
- deploy ordering and rollout flags stated in the repository

Do not assume table size, traffic, or deploy strategy the repository does not
establish. When production impact depends on a missing fact, name the fact and
lower confidence instead of asserting a blocker.

## Safety

- Operations the project's migration-safety tool rejects, and overrides that
  bypass it
- Lock acquisition and duration: table rewrites, full scans, long transactions
  that block reads or writes
- Index or constraint creation in blocking form where the engine supports a
  concurrent, online, or validate-later sequence
- `NOT NULL`, foreign key, unique, and check constraints added without safe
  population and validation ordering
- Drops, renames, and type changes performed before every deployed application
  version stopped using the old contract
- Application and migration deploy ordering that violates expand/contract
- Backfills that are unbounded, unbatched, non-idempotent, non-resumable,
  memory-heavy, or coupled to mutable application code
- Transformations that can truncate, coerce, duplicate, orphan, or lose data
- Missing verification, observability, or forward-fix path on a risky operation

Prefer a concrete safe sequence over a warning: expand, deploy compatible
readers and writers, backfill in bounded batches, verify, validate or enforce
the constraint, cut over, contract later.

## Necessity

Trace each new table, column, or index to a changed consumer, a named
requirement, or a demonstrated integrity or performance need.

A necessity finding needs positive evidence that the change is unused,
duplicates existing capability, or adds materially more persistence machinery
than the requirement needs. Undocumented rationale is not evidence. Absent that
evidence, return no necessity finding.

## Severity guidance

| Level | Condition |
|---|---|
| critical | credible data loss or corruption; an operation likely to block production immediately |
| important | tooling or policy incompatibility, unsafe destructive sequencing, long blocking operation, non-recoverable transition |
| suggestion | bounded hardening with limited production impact |

## Output

Per finding: `path`, `line`, `severity`, `category` (`safety` or `necessity`),
`operation`, `evidence`, `production_impact`, `fix` including rollout sequence
when relevant, `confidence`.

No findings: return empty and state which persistence changes were checked.
