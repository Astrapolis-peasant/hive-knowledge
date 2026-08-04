---
id: question.retrieval-scale-threshold
page_type: question
status: active
owner: team.knowledge
visibility: internal
confidence: low
summary: Ranked retrieval and miss-logging now exist; the open part is the threshold at which the synonym gap justifies embeddings.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
related:
  - concept.llm-wiki
  - concept.role-team-permission
  - topic.knowledge-base-foundations
supersedes: []
---

# Question: When Does Navigation Stop Scaling?

## Definition

The architecture defers vector search until measured failure. As of 2026-08-04 two of the three
things this question was blocked on exist: ranked retrieval (`bin/kb ask`) and measurement
(`bin/kb miss`, `bin/kb stats`). What remains open is the **threshold** — the number at which
the synonym gap justifies embeddings.

## Current Understanding

The staged plan is clear about the *shape* of the answer but not its threshold:

- Stage 1 — index-first navigation and exact lexical search. Current state, 10 pages.
- Stage 2 — a derived BM25 + vector + typed-link projection keyed by commit SHA, returning
  candidate page ids that are then read in full from that same commit.

**What now exists.** `bin/kb ask` scores pages with BM25 over id, title, summary, headings, and
body, then multiplies by `status` and `confidence` weights so a superseded or low-confidence
page cannot outrank an active one on lexical similarity alone. Filters (`--type`, `--owner`,
`--min-confidence`, `--status`) apply before ranking. There is no persistent index: scoring runs
in memory from the pinned commit, which at this scale is milliseconds and cannot go stale or
disagree with the wiki — so Stage 2's *candidate discovery* arrived without Stage 2's
infrastructure.

**What it fixed.** Topical queries that share no title words with the target now rank correctly:
"how do agents avoid seeing a half-updated wiki" returns [[concept.commit-pinned-read]] first,
which `git grep` on those words would not.

**What it did not fix, demonstrated.** "stop two writers clobbering each other" ranks the wrong
page first, because no page contains "clobbering" or "writers". That is the synonym gap, intact.
BM25 matches morphology, not meaning; only embeddings close it. So the earlier hypothesis holds
up: **the synonym gap bites before index size does.** Measured here, `wiki/index.md` is 229
bytes per page — a thousand pages is a ~230KB read, unpleasant but survivable, while the synonym
gap already costs answers at twelve pages.

**The three things now measured**, via `bin/kb stats`:

1. **Zero-hit rate** — queries where `ask` returned nothing. Logged automatically.
2. **Weak-top-score rate** — queries whose best score is under 1.0, the signature of "matched a
   couple of common words and nothing else". This is the synonym gap's fingerprint and the
   metric to watch.
3. **Recorded misses** — `bin/kb miss "<query>"`, an agent asserting the wiki should have
   answered. Deliberately manual: an automatic judgement of "should have known" would be the
   same unreliable inference the wiki exists to avoid.

Query logging writes to control state, never to the wiki, so the read path still does not
publish anything.

## Disputed or Uncertain

**The threshold itself is still unset**, and now for an honest reason rather than a missing
instrument: there is not enough traffic yet. A rate needs a denominator, and at a handful of
logged queries any percentage is noise.

Unresolved, and worth stating as a design tension: recorded misses depend on an agent choosing
to report failure, which is exactly the behaviour least likely under pressure to produce an
answer. The zero-hit and weak-score rates are automatic and therefore more trustworthy, but they
cannot distinguish "the wiki does not know this" from "the wiki knows it under other words" —
which is the very thing we are trying to count. Any threshold drawn from them will undercount.

A candidate trigger, offered as a starting point and not a measurement: build embeddings when
the weak-top-score rate exceeds ~20% over 100+ real queries, or when recorded misses that turn
out to have had a matching page exceed ~10%. Both numbers are guesses and should be replaced by
the first real distribution we see.

One thing retrieval measurement already proved it can do: it found a genuine *knowledge* gap
rather than a retrieval one. A question about the enforcement model returned nothing useful,
because that model existed only as a repository document and not as a page — it became
[[concept.role-team-permission]]. A retrieval failure and a knowledge gap look identical from
the outside, which argues for keeping a human in the loop on the trigger decision.

(A second artifact, noted for whoever tunes ranking next: a page that *discusses* a query tends
to outrank the page that *answers* it, because meta-discussion repeats the query's vocabulary.
Prose about retrieval is unusually prone to this.)

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 11 and 18 Phase 3 define the two stages and require measured failure before adding retrieval infrastructure.
