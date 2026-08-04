---
id: topic.knowledge-base-foundations
page_type: topic
status: active
owner: team.platform
visibility: public
confidence: high
summary: Map of the four foundations this knowledge base is built on and the one job each of them holds.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
related:
  - entity.tigerfs
  - entity.postgresql
  - entity.git
  - concept.llm-wiki
  - synthesis.four-layer-separation
supersedes: []
---

# Knowledge Base Foundations

## Definition

This knowledge base stands on four foundations, each holding exactly one job:

| Foundation | Job | Page |
|---|---|---|
| PostgreSQL | durable bytes, transactions, roles | [[entity.postgresql]] |
| TigerFS | file interface over those bytes | [[entity.tigerfs]] |
| Git | isolation, review, publication | [[entity.git]] |
| LLM Wiki | the knowledge model itself | [[concept.llm-wiki]] |

Start here, then read the foundation you need. The reasoning for the split is in
[[synthesis.four-layer-separation]].

## Current Understanding

The layers are ordered by what they are authoritative for, and that order is not negotiable:

- PostgreSQL is authoritative for **bytes**. If a byte is not in PostgreSQL, it is not
  durable.
- TigerFS is authoritative for **file semantics**. It decides what `open`, `rename`, and
  `fsync` mean over those bytes.
- Git is authoritative for **which bytes are published**. A commit on `main` is the wiki;
  anything else is a draft.
- The LLM Wiki is authoritative for **what we claim to know**. Raw sources are evidence, not
  knowledge.

Two derived rules follow, and most operational mistakes are a violation of one of them:

1. Never ask a lower layer to do a higher layer's job. TigerFS savepoints are not knowledge
   transactions; Git is not a backup; a search index is not a source of truth.
2. Never let a higher layer assume a lower layer's guarantee without testing it. This one was
   tested and failed: [[claim.git-on-tigerfs-fails-the-gate]]. Git runs on local disk;
   PostgreSQL and TigerFS keep the raw and control stores.

Reads are made coherent by [[concept.commit-pinned-read]]; evidence is made durable by
[[concept.content-addressed-store]].

## Disputed or Uncertain

The single-physical-store property is **gone**, and this is no longer hypothetical. The
architecture pre-committed to a fallback if Git-on-TigerFS failed its gate; it failed, so the
Git repository sits on local disk while PostgreSQL and TigerFS keep the raw and control
stores. Bytes are still durable and transactional in PostgreSQL; they are just not the *same*
bytes that hold the published wiki. See [[claim.git-on-tigerfs-fails-the-gate]].

Still open: whether Linux/FUSE would pass the same gate, and
[[question.retrieval-scale-threshold]].

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 4 and 19 assign one authority per layer and record the decision rationale.
