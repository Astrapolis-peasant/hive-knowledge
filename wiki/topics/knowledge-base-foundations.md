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
2. Never let a higher layer assume a lower layer's guarantee without testing it. The open
   case is [[claim.git-on-tigerfs-unverified]].

Reads are made coherent by [[concept.commit-pinned-read]]; evidence is made durable by
[[concept.content-addressed-store]].

## Disputed or Uncertain

Whether all four layers belong in one deployment is settled for this design but not
universally: the architecture doc itself notes that if Git-on-TigerFS fails its
compatibility gate, the Git repository moves to a certified filesystem and PostgreSQL keeps
only the raw and control stores. That fallback drops the single-physical-store property.
See [[claim.git-on-tigerfs-unverified]] and [[question.retrieval-scale-threshold]] for the
two open questions that could still change the shape of this stack.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 4 and 19 assign one authority per layer and record the decision rationale.
