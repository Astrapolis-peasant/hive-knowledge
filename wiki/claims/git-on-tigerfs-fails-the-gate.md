---
id: claim.git-on-tigerfs-fails-the-gate
page_type: claim
status: active
owner: team.platform
visibility: public
confidence: high
summary: Measured 2026-08-04 — Git on TigerFS 0.7.0 failed 23 of 34 gate checks, including atomic rename and fsck integrity. Rule 2 applies.
updated_at: 2026-08-04
sources:
  - source.git-on-tigerfs-gate-run-2026-08-04
  - source.ai-knowledge-base-architecture
related:
  - claim.git-on-tigerfs-unverified
  - entity.tigerfs
  - entity.git
  - topic.knowledge-base-foundations
supersedes:
  - claim.git-on-tigerfs-unverified
---

# Claim: Git on TigerFS Fails the Compatibility Gate

## Definition

**Claim.** Running a Git repository inside TigerFS does not work. Measured on 2026-08-04:
**11 of 34 automated checks passed, 23 failed.** `git fsck --full --strict` reported
integrity errors after essentially every operation.

This resolves the open question in [[claim.git-on-tigerfs-unverified]], which this page
supersedes. The architecture's pre-decided **rule 2** now applies: keep the Git repository on
a filesystem with certified Git behaviour, and keep TigerFS/PostgreSQL for the raw and control
stores.

## Current Understanding

Configuration under test — the result is specific to it, and the scope matters:

| | |
|---|---|
| TigerFS | 0.7.0 (darwin/arm64), **NFS loopback backend** — macOS does not use FUSE |
| PostgreSQL | 17.9, plus a local `uuidv7()` shim (see below) |
| Git | 2.50.1 |
| Workspace | `plaintext`, history disabled, as the architecture specifies |

What failed, grouped by why it matters:

- **`rename()` does not replace-and-remove.** This is how Git makes a commit, a ref, and the
  index visible. Everything else downstream of it is unreliable by construction.
- **Close-to-open visibility failed.** A closed write was not visible to a separate process on
  the same mount, so two agents cannot see each other's work.
- **`git fsck` failed (exit 8) after commit, after merge/rebase/cherry-pick/revert, after the
  worktree lifecycle, after racing commits, after repack, and after gc.** Not a performance
  problem — reported object-store corruption.
- **Compare-and-swap ref update failed** (both attempts errored, rather than exactly one
  winning), which is the mechanism the release path depends on to publish safely.
- **Conflicting merge was not detected as a conflict.** The merge failed without staging the
  conflict, so the one safety property that stops two agents' incompatible conclusions from
  silently becoming one page did not hold.
- **An 8MB binary could not be committed**, and the blob did not read back byte-identical.
- **repack and gc both failed**, and 4 agents committing in parallel worktrees landed 0 of 4.

What passed, and is worth keeping: `O_EXCL` exclusive create, `fsync` on file and directory,
1MB binary round trip at the filesystem level, `git init`, a 200-file commit, a non-conflicting
merge, `worktree add/list/remove/prune`, and 8 concurrent ref creations. So TigerFS is not
broken as a filesystem — it is not adequate for Git specifically.

**The raw store, tested separately, works.** A source ingested through `bin/kb ingest` was
stored as a row in `tigerfs.kb_raw`, read back byte-identical through the mount, and its
SHA-256 verified against the manifest by `bin/kb validate`. Task records likewise round-tripped
through `tigerfs.kb_control`. This is why rule 2 is a partial retreat, not an abandonment:
content-addressed write-once blobs need none of the primitives Git needs — no rename, no
lockfile, no repack.

Operational findings from the same session, all reproducible:

- TigerFS 0.7.0 workspace DDL defaults its primary key to `uuidv7()`, which ships in
  **PostgreSQL 18+**. On 17.9 workspace creation fails with
  `function uuidv7() does not exist`. A local PL/pgSQL shim is enough to proceed, but the
  supported configuration is PG 18 or Tiger Cloud.
- The `history` feature requires the **TimescaleDB** extension. On plain PostgreSQL a
  workspace can only be created without it. This costs us nothing — history is deliberately
  off for `kb-git` and `kb-raw` — but `kb-control` cannot have it either.
- Binary bodies are stored **base64-encoded** (`encoding` column), so binary evidence carries
  roughly 33% storage amplification in PostgreSQL.
- macOS writes AppleDouble sidecars (`._name`) onto the mount, which TigerFS rejects with
  `unsupported format` and which still land as rows — 5,464 bytes of metadata per file.
  Set `COPYFILE_DISABLE=1`.
- Killing the `tigerfs` process while mounted leaves a **stale NFS mount that requires root to
  clear**, and because macOS keys NFS mounts by server spec (every TigerFS mount is
  `127.0.0.1:/`), the dead session swallows requests intended for a new mount: `stat` succeeds,
  `readdir` hangs, and the new server logs nothing. Always `tigerfs unmount` a healthy mount.

## Disputed or Uncertain

The result is narrow in two ways that a reader should not over-generalize:

- **macOS only.** TigerFS uses an NFS loopback backend here; Linux uses FUSE, which is a
  different code path with different semantics. This gate has never run on Linux. Several
  failures (`rename`, close-to-open) are exactly the kind an NFS layer produces and FUSE might
  not, so **Linux may pass** and deserves its own run before the architecture is judged.
- **PostgreSQL 17.9 with a shim**, not the supported PG 18+. The shim only supplies a UUID
  default and is unlikely to affect rename or visibility semantics, but it is not the
  vendor-supported configuration.

Also untested, and still open regardless of backend: the crash-injection and cross-host tests
the gate prints but cannot perform (killing TigerFS mid-ref-update, PostgreSQL restart
mid-write, a second host, a restore drill), and scale/latency at 1k–100k pages.

What would change this claim: a clean gate run on Linux + FUSE + PostgreSQL 18. Until someone
does that, "Git on TigerFS" should be treated as unsupported rather than merely unproven.

## Evidence

- [source.git-on-tigerfs-gate-run-2026-08-04](../../sources/manifests/source.git-on-tigerfs-gate-run-2026-08-04.yaml) — the captured gate output: 11 passed, 23 failed, with the per-check verdicts quoted above.
- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — section 16 defines the gate and states rule 2 as the pre-decided response to exactly this outcome.
