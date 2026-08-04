---
id: concept.commit-pinned-read
page_type: concept
status: active
owner: team.platform
visibility: public
confidence: high
summary: Resolve main once per request and read only that commit, so a release in flight can never produce a half-updated answer.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
related:
  - entity.git
  - topic.knowledge-base-foundations
supersedes: []
---

# Commit-Pinned Read

## Definition

A query resolves `refs/heads/main` exactly once, at the start of the request, and reads every
page from that one immutable commit for the rest of the request.

```bash
COMMIT=$(bin/kb pin)
bin/kb show "$COMMIT" wiki/index.md
bin/kb grep "$COMMIT" "worktree"
```

## Current Understanding

This is the design's answer to a problem it otherwise could not solve: a single knowledge
change touches many pages, but the storage layer only guarantees atomicity per file
operation (see [[entity.postgresql]]). Reading a mutable working directory during a release
would therefore let a query see page A updated and page B not — a wiki that contradicts
itself, assembled by the reader.

Git closes the gap without a cross-file transaction. Objects are written first; the branch ref
moves last. A commit is a complete tree or it does not exist, so pinning one gives snapshot
isolation for free.

Three consequences worth stating plainly:

- **Never mix commits in one answer.** Two pages from two commits can be individually correct
  and jointly false.
- **Derived indexes must record their commit SHA.** An index built from commit A used against
  pages from commit B is the same bug wearing a different hat, which is why indexes here are
  disposable projections keyed by SHA rather than a store of record.
- **Reading is not writing.** If a query produces a durable synthesis, it opens a normal task
  branch. Writing during a read is how a read path acquires the ability to publish
  unreviewed knowledge.

## Disputed or Uncertain

Pinning trades freshness for coherence: a long-running request answers from the commit it
started with and will not see a release that lands mid-request. That is the intended trade,
but it means "the wiki says X" is always relative to a commit — so answers should cite the
pinned SHA when the distinction could matter.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 4.4, 10.2, and 12 define the pinned-read rule and the concurrency cases it covers.
