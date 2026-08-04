---
id: entity.git
page_type: entity
status: active
owner: team.platform
visibility: public
confidence: high
summary: Supplies the collaboration semantics TigerFS does not have — isolation, review, conflict, publication — one branch and worktree per task.
updated_at: 2026-08-04
sources:
  - source.git-worktree-docs
  - source.ai-knowledge-base-architecture
related:
  - entity.tigerfs
  - concept.commit-pinned-read
  - topic.knowledge-base-foundations
supersedes: []
---

# Git

## Definition

Git is the logical publication and collaboration layer. It answers questions the filesystem
cannot: who changed what, against which base, reviewed by whom, and which version is
published.

## Current Understanding

The repository is **bare and shared**, with one linked worktree per write task. Bare, because
no ordinary agent should be able to edit a checked-out `main`. Shared, because linked
worktrees reuse one object database instead of duplicating it per agent.

Naming is mechanical so that permission checks can be mechanical too:

```text
main                                  the published wiki
agent/<agent-id>/<task-id>-<slug>     ingest and compile work
lint/<task-id>-<slug>                 lint findings
repair/<task-id>-<slug>               repairs awaiting review
```

Each write task gets a branch, its own worktree, a pinned base commit, and a lease. Two rules
have no exceptions:

1. **One worktree per agent.** A branch alone is not isolation — the index, the checkout
   state, and uncommitted files are all worktree state, so a shared worktree means agents
   corrupt each other's work in ways the diff will not explain.
2. **Only the release role advances `refs/heads/main`.** The update is a compare-and-swap
   against the expected old SHA, so two concurrent releases cannot interleave; the loser
   re-runs rather than silently overwriting.

Branches are drafts. There is no `drafts/` directory, because two draft mechanisms means two
sets of merge semantics. Branches should live minutes to hours: a week-old knowledge branch
is reasoning about a wiki that no longer exists, and should be regenerated rather than merged.

Publication is atomic in the only sense that matters. Git writes objects first and moves the
ref last, so a crash mid-write leaves unreachable objects rather than a half-published wiki.

## Disputed or Uncertain

Git's guarantees are inherited from the filesystem beneath it, and that dependency turned out
to be decisive: on TigerFS, Git failed 23 of 34 gate checks, so **the repository runs on local
disk** ([[claim.git-on-tigerfs-fails-the-gate]]). Everything on this page — branches,
worktrees, compare-and-swap publication — was verified working there, and none of it survived
on TigerFS.

Textual merge success is also not semantic merge success: two conflict-free edits can still
change the same conclusion in incompatible ways, which is why release requires review and not
just a clean merge.

## Evidence

- [source.git-worktree-docs](../../sources/manifests/source.git-worktree-docs.yaml) — linked worktree mechanics, shared object database, worktree metadata.
- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 9, 10.4, and 12 on the branch model, release queue, and concurrency table.
