---
id: entity.tigerfs
page_type: entity
status: active
owner: team.platform
visibility: public
confidence: medium
summary: Timescale's PostgreSQL-backed filesystem; here it is the file interface that lets ordinary agent tools reach database bytes.
updated_at: 2026-08-04
sources:
  - source.tigerfs-spec
  - source.tigerfs-file-first
  - source.ai-knowledge-base-architecture
related:
  - entity.postgresql
  - entity.git
  - topic.knowledge-base-foundations
  - claim.git-on-tigerfs-unverified
supersedes: []
---

# TigerFS

## Definition

TigerFS exposes rows in a PostgreSQL database as files and directories. In this knowledge
base it is the interface layer: it is why an agent can use `read`, `write`, `git`, and `grep`
instead of a bespoke knowledge API.

## Current Understanding

We run TigerFS in **file-first mode**, which stores user files as file bodies rather than as
parsed structures, and we use three separate workspaces because they have different write
patterns:

| Workspace | Holds | TigerFS history |
|---|---|---|
| `kb-git` | the bare Git repository and linked worktrees | disabled |
| `kb-raw` | immutable content-addressed source bytes | disabled |
| `kb-control` | tasks, leases, audit notes | optional |

History is disabled for `kb-git` deliberately. Git already versions its own content; letting
TigerFS also version every loose object, lockfile, ref update, and packfile rewrite doubles
the write volume and buys no better branch semantics (inference from the architecture doc's
reasoning, not a measured result).

The same mount path must be used on every host that shares linked worktrees. Git worktree
metadata records the path to its common Git directory, so inconsistent mount points break
worktrees in a way that looks like corruption.

What TigerFS deliberately does **not** provide: branches, merges, diffs, or cross-file
transactions. Those are [[entity.git]]'s job. Treat the TigerFS `user_id` field as audit
metadata, not as access enforcement, unless you have verified that it actually denies access.

## Disputed or Uncertain

The whole design rests on TigerFS implementing the filesystem primitives Git relies on —
exclusive lockfile creation, atomic rename, close-to-open visibility, correct binary round
trips, `fsync` semantics. TigerFS publishes no formal Git compatibility guarantee, and we
have not run the gate ourselves. This is tracked as [[claim.git-on-tigerfs-unverified]] and
is the single largest risk in the stack.

Confidence on this page is medium, not high: the source bytes for the TigerFS specification
have not been captured, and the project is under active development.

## Evidence

- [source.tigerfs-spec](../../sources/manifests/source.tigerfs-spec.yaml) — workspace and format model, dotfile handling, binary encoding.
- [source.tigerfs-file-first](../../sources/manifests/source.tigerfs-file-first.yaml) — the file-first mode this design assumes.
- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — section 5.2 workspace split and the history-disabled decision.
