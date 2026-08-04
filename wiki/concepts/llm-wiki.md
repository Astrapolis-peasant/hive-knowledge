---
id: concept.llm-wiki
page_type: concept
status: active
owner: team.knowledge
visibility: public
confidence: medium
summary: Compile sources into a maintained, interlinked wiki instead of re-deriving answers from raw chunks on every question.
updated_at: 2026-08-04
sources:
  - source.karpathy-llm-wiki
  - source.ai-knowledge-base-architecture
related:
  - topic.knowledge-base-foundations
  - question.retrieval-scale-threshold
  - synthesis.four-layer-separation
supersedes: []
---

# LLM Wiki

## Definition

An LLM Wiki is a knowledge base that an LLM *maintains* rather than merely searches. New
material is read, reconciled against what is already written, and compiled into a small number
of stable, interlinked pages. The wiki is the artifact; retrieval is a way to find pages in it.

The contrast is with plain RAG, which stores chunks and rebuilds an understanding from
scratch on every question. Chunks do not accumulate. Pages do.

## Current Understanding

Compilation happens at **ingest** time, not query time. When a source arrives, the agent
identifies the concepts and entities it touches, updates the affected pages, records
contradictions explicitly, and appends a log entry — all in one branch, reviewed as one diff.
Query time then becomes navigation and synthesis over maintained knowledge.

Three properties make this work in practice:

- **Stable page identity.** A page id (`concept.kv-cache`) never changes, even when the page
  moves directory or is rewritten. Ids are what links, citations, and indexes point at, so a
  page's identity must not depend on its current path.
- **Few, stable categories.** `concepts`, `entities`, `topics`, `claims`, `questions`,
  `syntheses`. Resisting new categories is what keeps the wiki navigable; a taxonomy that
  grows with every ingest is a filing cabinet with no drawers.
- **Epistemic separation.** Every page distinguishes source-reported fact, direct observation,
  user opinion, agent inference, disputed claim, and unknown. An agent must never silently
  promote an inference into a fact — the wiki's value is that its confidence means something.

Not knowing is a first-class result. If the wiki lacks a confident answer, the query agent
says so and may open a `question.*` page; what it must not do is file its own low-confidence
answer back as knowledge, which is how a wiki poisons itself.

## Disputed or Uncertain

The compile-on-ingest model trades ingest cost for query quality, and we have not measured
that trade at scale here. Two open tensions:

- **Cost.** Compiling is more expensive per source than embedding chunks. It pays off only if
  the same knowledge is queried repeatedly.
- **Drift.** A maintained page can quietly diverge from its sources as it is edited. Deterministic
  lint catches broken citations but not slow semantic decay; semantic lint is a judgement call
  and can produce false findings.

Confidence is medium: the source bytes for Karpathy's note have not been captured, and the
scaling claims are so far reasoning rather than measurement. See
[[question.retrieval-scale-threshold]].

## Evidence

- [source.karpathy-llm-wiki](../../sources/manifests/source.karpathy-llm-wiki.yaml) — the originating idea: an LLM-maintained wiki as a compounding artifact.
- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 4.2 and 8 apply it as this repository's knowledge model.
