---
id: claim.git-on-tigerfs-unverified
page_type: claim
status: active
owner: team.platform
visibility: public
confidence: high
summary: Running Git inside TigerFS is a tested deployment assumption, not an established guarantee, and it is this stack's largest single risk.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
  - source.tigerfs-spec
related:
  - entity.tigerfs
  - entity.git
  - topic.knowledge-base-foundations
supersedes: []
---

# Claim: Git-on-TigerFS Is Unverified

## Definition

**Claim.** The correctness of this knowledge base depends on TigerFS faithfully implementing
the filesystem primitives Git relies on, and that dependency has not been verified.

**Status.** Open. Blocks production use. Confidence in the *claim* is high — the architecture
doc states it explicitly as an unresolved risk. Confidence in Git-on-TigerFS *working* is
unknown, which is the whole point.

## Current Understanding

TigerFS documents that dotfiles and directories such as `.git/` are permitted, that user files
are storable in file-first mode, and that binary bodies can be encoded for PostgreSQL. What it
does not publish is a Git compatibility guarantee or a Git workload benchmark. Those are
different things, and the gap between them is where data loss lives.

Git depends on primitives that FUSE-over-database layers commonly get subtly wrong:

- exclusive lockfile creation (`O_EXCL`) — how Git serializes ref updates
- atomic rename and replace — how a commit becomes visible
- close-to-open visibility across mounts — whether another agent sees your write
- correct binary round trips for loose objects and packfiles
- truncation and append behaviour
- `fsync` and crash semantics
- concurrent ref updates
- `worktree add/move/remove/prune`, and `gc`/repack

The gate must run at expected repository size, agent count, network latency, and PostgreSQL
configuration, with `git fsck` clean after every injected failure — including database restart
mid-write and TigerFS termination during a ref update.

**Two decision rules, decided in advance so nobody improvises during an incident:**

1. If correctness passes but performance is weak — use ephemeral local object caches or fewer
   persistent worktrees. Do not add infrastructure before measuring.
2. If correctness fails — move the bare repository to a filesystem with certified Git
   behaviour and keep TigerFS/PostgreSQL for the raw and control stores. Do **not** attempt to
   repair Git semantics in the agent layer; an agent cannot make a non-atomic rename atomic.

Rule 2 changes the single-physical-store decision and therefore requires an explicit
architecture review, not a quiet config change.

## Disputed or Uncertain

Everything about the outcome. No test in the matrix has been run in this repository, so we
cannot say whether the failure mode is "works fine", "works slowly", or "silently corrupts
packfiles under concurrent gc". Until the gate runs, treat any claim that this stack is
production-ready as unsupported.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — section 16 states the gate, the test matrix, and both fallback rules; section 18 makes it Phase 0 with `git fsck` as the exit criterion.
- [source.tigerfs-spec](../../sources/manifests/source.tigerfs-spec.yaml) — documents what TigerFS does support, and by omission what it does not promise.
