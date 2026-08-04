---
id: entity.postgresql
page_type: entity
status: active
owner: team.platform
visibility: public
confidence: medium
summary: The only durable store in the design; also where permission control becomes real rather than advisory.
updated_at: 2026-08-04
sources:
  - source.postgresql-mvcc-docs
  - source.ai-knowledge-base-architecture
related:
  - entity.tigerfs
  - topic.knowledge-base-foundations
  - concept.content-addressed-store
supersedes: []
---

# PostgreSQL

## Definition

PostgreSQL is the physical system of record. Every durable artifact — Git objects, raw source
bytes, control state — is ultimately a row in one PostgreSQL database, reached through
[[entity.tigerfs]].

## Current Understanding

Choosing PostgreSQL as the single durable store buys four things that would otherwise each
need their own component: ACID persistence, backup and point-in-time recovery, replication,
and role-based access control.

It is also where two of the four permission layers live (`db/schema.sql` is the reference
implementation):

- **Roles and grants** — one login role per agent, granted exactly one capability role.
  `REVOKE UPDATE, DELETE` on the raw table is what actually makes evidence immutable; a
  trigger states the same intent with a readable error.
- **Row-level security** — a task row is visible and mutable only to the agent that owns it,
  so one agent cannot steal another's lease.

What PostgreSQL gives us is **per-operation** atomicity: a single TigerFS file operation
either happens or does not. It does not give us a transaction spanning a fifteen-file wiki
update. That gap is filled by Git ref advancement, not by the database — see
[[concept.commit-pinned-read]].

Operational floor before ingesting anything worth keeping: base backups, WAL archiving, a
tested restore on a separate instance, and a scheduled `git fsck` plus raw checksum audit.
TigerFS history is not a backup.

## Disputed or Uncertain

Performance under a Git workload is unmeasured. Git creates many small objects and does
frequent metadata operations, and a database-backed FUSE path plausibly makes `status`,
checkout, worktree creation, and `gc` more latency-sensitive than local disk. The
architecture doc specifies benchmarks at 1k, 10k, and 100k pages; none have been run.

Confidence is medium because the PostgreSQL behaviour is well established but its behaviour
*in this configuration* is not, and the cited docs have not been captured as bytes.

## Evidence

- [source.postgresql-mvcc-docs](../../sources/manifests/source.postgresql-mvcc-docs.yaml) — transaction isolation and concurrency control; the basis for the per-operation-atomicity limit.
- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 5.1, 12, 13, 14 on persistence, concurrency, permissions, and recovery.
