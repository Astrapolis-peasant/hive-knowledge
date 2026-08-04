---
id: claim.git-on-tigerfs-fails-the-gate
page_type: claim
status: active
owner: team.platform
visibility: public
confidence: high
summary: Measured 2026-08-04 — Git on TigerFS 0.7.0 fails on lockfile reuse. Tuning lifted 11/34 to 21/35; the remaining blocker is not tunable.
updated_at: 2026-08-04
sources:
  - source.git-on-tigerfs-gate-run-2026-08-04
  - source.git-on-tigerfs-tuned-gate-run-2026-08-04
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
**11 of 34 checks passed untuned; 21 of 35 after tuning and mitigations.** The residual
blocker is that Git cannot reuse a lockfile name, and no configuration fixes it.

The first measurement blamed the wrong things. Investigation separated four independent
causes, two of which are fixable and two of which are not.

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

### Cause 1 — client-side attribute caching. FIXED.

`attr_timeout` and `entry_timeout` default to **1s**. Git writes a file and immediately stats
it; within that window the stat lies, which is indistinguishable from corruption. Setting both
to `0s` fixed three checks outright: `rename()` replace-and-remove, truncate-then-append, and
close-to-open visibility.

### Cause 2 — macOS AppleDouble sidecars. NOT TigerFS. macOS-only.

Every `git fsck` failure was `._*` files, not damaged objects:

```text
error: refs/heads/._main: badRefName: invalid refname format
bad sha1 file: .git/objects/2a/._a9d9ca4a13e868ea52885fd18ebd8afd1c343e
error: non-monotonic index .git/objects/pack/._pack-cbefc990….idx
```

macOS stamps every file with a `com.apple.provenance` xattr. The mount cannot store xattrs, so
the kernel writes an AppleDouble sidecar beside each file — **40 of them inside one fresh
`.git`** — and Git reads them as refs, loose objects, and pack indexes. Delete them and
`git fsck --full --strict` exits 0. The object store was never corrupt.

`COPYFILE_DISABLE=1` does not prevent this; it only affects `cp` and `tar`. This is a
macOS-on-NFS artifact and would not occur on Linux.

### Cause 3 — a lockfile name cannot be reused. NOT FIXABLE by configuration. **The blocker.**

Create a file, delete it, create the same name in the same directory: **10 of 10 attempts fail
with `Input/output error`**, independent of any delay up to 2s. Server-side:
`Error applying attributes: No such file or directory: file does not exist` — TigerFS loses the
just-created file during the NFS CREATE+SETATTR sequence while a cache entry for the old name
survives.

This is precisely Git's lockfile pattern. `index.lock`, `HEAD.lock`, and `packed-refs.lock` are
created, used, and removed constantly, so real Git output is:

```text
fatal: Unable to create '.git/index.lock': Input/output error
error: Unable to create '.git/index.lock': File exists.
fatal: cannot lock ref 'HEAD': Unable to create '.git/HEAD.lock': File exists.
```

The first failure leaves a stale lock, and every later operation dies on it. That kills
cherry-pick, revert, worktree commits, worktree move, ref compare-and-swap, repack, gc, and
parallel worktree commits.

It traces to the server-side handle cache (`nfs_cache_idle_timeout`, default 5m), and tuning
cannot win: at **2s**, a recreate after a 3s gap succeeds but Git's sub-millisecond reuse still
fails; at **50ms** with a 10ms reaper, live handles are evicted mid-operation and the score
drops from 21/35 to **17/35** — even a 200-file commit fails. Long enough to keep handles alive
is long enough to poison name reuse. There is no setting that satisfies both.

### Cause 4 — reads pad UTF-8 text by one byte. Narrow, but real.

A file whose contents are valid UTF-8 and do **not** end with a newline reads back one byte
longer: `\n` with `trailing_newlines: true` (the default), `\x00` with `false`.

| written | read | exact |
|---|---|---|
| `abc` | 4 bytes, `abc\x00` | no |
| `abc\n` | 4 bytes | yes |
| binary with NUL, no newline | 66 bytes | yes |
| empty | 0 bytes | yes |
| 1MB random | 1048576 bytes | yes |

Binary content is stored base64 and is byte-exact, so Git's objects and packfiles are safe;
what is not safe is any text artifact lacking a trailing newline. This also means
`bin/kb ingest` must not be trusted with such a source on TigerFS — the hash check in
`bin/kb validate` would catch it, which is the point of having it.

### What passes

`O_EXCL` exclusive create, `fsync` on file and directory, 1MB binary round trip, `rename()`
replace, truncate-then-append, close-to-open visibility, `git init`, a 200-file commit, a
non-conflicting merge, `worktree add/list/remove/prune`, 8 concurrent ref creations, and — once
sidecars are stripped — **every single `fsck`**. TigerFS is a sound filesystem for whole-file
writes. It is not a Git host.

### Also learned

Only two workspace formats exist. TigerFS says so itself:
`supported formats: markdown, txt (optionally with ,history)`. There is no binary, blob, or
verbatim format — TigerFS is a text and structured-data filesystem by design, which is the
honest reason Git does not belong on it.

The config file takes **flat** keys (`port`, `attr_timeout`, `nfs_cache_idle_timeout`), not the
nested layout `tigerfs config show` prints. A nested file is silently ignored and every value
validates as zero, surfacing as `Error: invalid port: 0`. Env vars are flat too
(`TIGERFS_ATTR_TIMEOUT`, not `TIGERFS_FILESYSTEM_ATTR_TIMEOUT`).

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
