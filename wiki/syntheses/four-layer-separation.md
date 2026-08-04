---
id: synthesis.four-layer-separation
page_type: synthesis
status: active
owner: team.knowledge
visibility: public
confidence: high
summary: Why four layers instead of one system: each holds a guarantee the others cannot provide, and every shortcut collapses two of them.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
  - source.karpathy-llm-wiki
related:
  - topic.knowledge-base-foundations
  - claim.git-on-tigerfs-fails-the-gate
  - concept.commit-pinned-read
  - concept.content-addressed-store
  - claim.git-on-tigerfs-unverified
supersedes: []
---

# Synthesis: Why the Layers Stay Separate

## Definition

A stack of four components looks like complexity to be optimized away. It is the opposite:
each layer exists because a specific guarantee cannot be obtained from the layers around it.
This page records why, so the separation is not casually undone by someone simplifying.

## Current Understanding

Read the stack as a chain of things that cannot be borrowed:

- **PostgreSQL cannot give you a knowledge transaction.** It makes one file operation atomic.
  A knowledge change touches fifteen pages. So Git supplies the multi-file boundary via ref
  advancement — [[concept.commit-pinned-read]].
- **Git cannot give you durability or access control.** It has no roles, no WAL, no
  point-in-time recovery. So PostgreSQL sits underneath — [[entity.postgresql]].
- **Neither gives agents a usable interface.** Agents already know files. So TigerFS presents
  database rows as files and the whole existing toolchain works unchanged —
  [[entity.tigerfs]].
- **None of them decides what is true.** Bytes, commits, and rows are indifferent to whether a
  claim is supported. So the wiki model carries the epistemics — [[concept.llm-wiki]].

The test of a layered design is what happens when you collapse a layer. Each shortcut here has
a specific failure:

| Shortcut | What breaks |
|---|---|
| Use TigerFS savepoints as knowledge transactions | No diff, no review, no conflict detection — every merge is a silent overwrite |
| Read from a mutable release worktree | Queries see half-published wikis and confidently answer from a contradiction |
| Store raw bytes in the Git tree | Every worktree copies every PDF; the object database grows permanently |
| Enable TigerFS history on `kb-git` | Every loose object, lockfile, and packfile rewrite versioned twice |
| Let a search index be the source of truth | Retrieval infrastructure becomes a competing truth store that cannot be rebuilt |
| Let any agent write `main` | Unreviewed knowledge becomes published knowledge |
| Enforce permissions in the prompt only | The first agent that drifts writes wherever it likes |

Each row is a decision someone will eventually propose as a simplification. The pattern
connecting them: **a lower layer's mechanism is being asked to carry a higher layer's meaning.**
That is the failure mode to watch for in any future change, including ones not on this list.

The permission model follows the same logic — instruction, verification, filesystem, database —
because each layer catches a different class of failure: a cooperative agent straying, a
drifting agent, a compromised process, and everything above being wrong.

## Disputed or Uncertain

The gate ran on 2026-08-04 and Git-on-TigerFS failed 23 of 34 checks
([[claim.git-on-tigerfs-fails-the-gate]]), so this is now a fact rather than a contingency:
Git lives on local disk, PostgreSQL and TigerFS keep the raw and control stores.

The layers did not collapse — the *physical* claim did. That distinction is the whole argument
of this page, and it is worth noticing that it survived contact with a real failure. Each
layer's job stayed put; only the question of which bytes sit underneath the Git layer changed.
Had the design fused publication into TigerFS savepoints, as the first row of the table below
warns against, the same filesystem failure would have taken the knowledge base with it instead
of costing one deployment decision.

What it does cost, honestly: the single-durable-store property is gone. Published wiki bytes
and evidence bytes now live in different places with different recovery procedures, so backup
and restore must cover both and be tested together.

Also open, and honestly: whether four layers is right for a knowledge base of this size. The
argument above is about where this goes at a thousand pages and many agents. At the current
size the machinery is larger than the content, and that is a defensible thing to dislike.

Unresolved for the stack itself: whether TigerFS on Linux with the FUSE backend would pass the
gate that the macOS NFS backend failed. If it did, the single-store property could come back.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 4, 12, and 19 give the authority split, concurrency mechanisms, and per-decision rationale.
- [source.karpathy-llm-wiki](../../sources/manifests/source.karpathy-llm-wiki.yaml) — the knowledge-model layer that the storage layers exist to serve.
