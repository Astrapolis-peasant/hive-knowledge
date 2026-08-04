---
id: question.retrieval-scale-threshold
page_type: question
status: active
owner: team.knowledge
visibility: internal
confidence: low
summary: At what page count does index-plus-grep navigation stop working, and what measurement should trigger building a derived index?
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
related:
  - concept.llm-wiki
  - topic.knowledge-base-foundations
supersedes: []
---

# Question: When Does Navigation Stop Scaling?

## Definition

Retrieval here is deliberately primitive: `wiki/index.md` as catalog, wikilinks, `git grep`,
then read the whole page. The architecture defers BM25 and vector search until measured
failure. The open question is what "measured failure" means, in numbers.

## Current Understanding

The staged plan is clear about the *shape* of the answer but not its threshold:

- Stage 1 — index-first navigation and exact lexical search. Current state, 10 pages.
- Stage 2 — a derived BM25 + vector + typed-link projection keyed by commit SHA, returning
  candidate page ids that are then read in full from that same commit.

What we would need to record before building Stage 2:

1. **Recall failures** — questions the wiki could have answered where navigation did not find
   the page. This requires logging query outcomes, which we do not do yet.
2. **Index legibility** — the point at which `wiki/index.md` is too long for an agent to scan
   cheaply. A one-line-per-page catalog is roughly 120 characters per page; a few thousand pages
   makes the index itself a large read.
3. **Synonym gap** — how often the right page exists under vocabulary the query did not use.
   This is the failure `grep` cannot fix and embeddings can, so it is the real trigger.

Working hypothesis, explicitly an inference and not a measurement: lexical navigation holds to
roughly the low hundreds of pages while the taxonomy stays small, and the synonym gap bites
before index size does.

## Disputed or Uncertain

The whole threshold. Also unresolved: whether recall failures should be logged automatically by
query agents (cheap, privacy-relevant, and it makes the read path write something) or reported
by hand (honest, sparse, and probably never done). Until one of those exists, "measure before
adding infrastructure" has no measurement to point at — which is itself the strongest argument
for adding the logging before adding the index.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 11 and 18 Phase 3 define the two stages and require measured failure before adding retrieval infrastructure.
