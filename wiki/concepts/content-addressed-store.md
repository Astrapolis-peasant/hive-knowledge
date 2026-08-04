---
id: concept.content-addressed-store
page_type: concept
status: active
owner: team.platform
visibility: public
confidence: high
summary: Raw source bytes live once under their SHA-256, create-only and outside Git, with the manifest as the stable citation.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
related:
  - entity.postgresql
  - topic.knowledge-base-foundations
supersedes: []
---

# Content-Addressed Raw Store

## Definition

Every raw source is stored once, at a path derived from the SHA-256 of its bytes, and is never
updated or deleted:

```text
kb-raw/sha256/ab/cd/abcd…<full-sha256>
```

The bytes are the evidence. A Git-tracked manifest (`sources/manifests/<id>.yaml`) holds the
metadata and is what wiki pages cite.

## Current Understanding

Splitting identity from interpretation is the point. Bytes are immutable, so the hash is a
permanent name for a specific artifact. Metadata and our reading of it improve over time, so
the manifest is versioned in Git. A page cites `source.tigerfs-spec`, not a hash, and stays
correct when the manifest is corrected.

**Why immutability is enforced below the agent layer.** `REVOKE UPDATE, DELETE` plus a trigger
on the raw table (`db/schema.sql`) is what makes evidence immutable; the instruction in
`AGENTS.md` only makes a cooperative agent aware of it. Content-addressing then makes the
invariant *checkable*: stored bytes must hash to the path they occupy, so any mutation is
detectable by audit rather than being taken on trust. `bin/kb validate` performs exactly that
comparison whenever the bytes are reachable.

**Why raw bytes stay out of the Git tree.** Linked worktrees materialize tracked files, so a
100 MB PDF in the tree is copied into every agent's worktree and made permanent in the object
database. Keeping it in `kb-raw` means one copy, referenced by hash. Small text sources may
live in Git when uniformity is worth less than simplicity — the manifest remains the citation
either way.

A manifest with `status: active` must carry both a hash and a `raw_uri`; one with
`status: reference-only` records something we have pointed at but not captured. That
distinction is load-bearing: `confidence: high` on a page requires at least one active source,
so a page cannot claim certainty on evidence nobody has.

## Disputed or Uncertain

Hashing gives integrity, not authenticity. It proves bytes have not changed since capture; it
proves nothing about whether the capture was faithful to the origin, or whether the URL served
the same content to someone else. Signed capture or an independent second fetch would close
that gap, and neither is implemented.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 7.1, 8.1, and 13 on raw storage, manifests, and enforced immutability.
