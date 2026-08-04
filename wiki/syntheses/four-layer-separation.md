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

The separation costs something real: four components to operate, and one of them
([[claim.git-on-tigerfs-unverified]]) unvalidated. If the Git-on-TigerFS gate fails, the layers
do not collapse — the *physical* claim does, and Git moves to a certified filesystem while
PostgreSQL keeps the raw and control stores. Worth stating clearly: that outcome would refute
the single-durable-store decision, not this synthesis.

Also open, and honestly: whether four layers is right for a knowledge base of ten pages. The
argument above is about where this goes at a thousand pages and many agents. At the current
size the machinery is larger than the content, and that is a defensible thing to dislike.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 4, 12, and 19 give the authority split, concurrency mechanisms, and per-decision rationale.
- [source.karpathy-llm-wiki](../../sources/manifests/source.karpathy-llm-wiki.yaml) — the knowledge-model layer that the storage layers exist to serve.
