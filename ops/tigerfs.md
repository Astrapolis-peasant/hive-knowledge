# Deploying on the TigerFS backend

The knowledge base runs on a local filesystem today. This is how it moves to the intended
production substrate: PostgreSQL for bytes, TigerFS presenting them as files.

**Read this first — the gate has been run, and Git-on-TigerFS failed it.** On 2026-08-04, on
macOS with TigerFS 0.7.0, Git failed 23 of 34 checks including atomic rename and `git fsck`
integrity ([wiki/claims/git-on-tigerfs-fails-the-gate.md](../wiki/claims/git-on-tigerfs-fails-the-gate.md)).
The fallback in step 7 is therefore the **current deployment**, not a contingency: Git on local
disk, TigerFS and PostgreSQL for the raw and control stores, both of which were measured
working. Linux with the FUSE backend is untested and could change this — rerun the gate there
before assuming otherwise.

## Topology

```text
PostgreSQL (one instance, WAL archiving on)
├── TigerFS mount, same path on every agent host
│   ├── kb_raw/      plaintext   content-addressed immutable sources   VERIFIED WORKING
│   └── kb_control/  markdown    tasks and leases                      VERIFIED WORKING
└── local disk
    └── knowledge.git  bare repo + linked worktrees                    (Git fails on TigerFS)
```

Workspace names use underscores: they become PostgreSQL table names in the `tigerfs` schema
(`tigerfs.kb_raw`), and a hyphen there is awkward to quote.

Three workspaces because they have different write patterns. History is **off** for `kb-git`:
Git already versions its content, and versioning every loose object, lockfile, and packfile
rewrite doubles the write volume for nothing.

## 1. PostgreSQL

**Use PostgreSQL 18 or newer.** TigerFS 0.7.0's workspace DDL defaults its primary key to
`uuidv7()`, which arrived in PG 18. On 17.9 workspace creation fails with
`function uuidv7() does not exist (SQLSTATE 42883)`.

```bash
createdb ai_kb
psql -d ai_kb -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"   # for kb.audit_raw_hashes()
psql -v ON_ERROR_STOP=1 -d ai_kb -f db/schema.sql
```

On PG 17 a shim is enough to proceed, though it is not a supported configuration:

```sql
CREATE OR REPLACE FUNCTION public.uuidv7() RETURNS uuid
LANGUAGE plpgsql VOLATILE AS $$
DECLARE b bytea; ms bigint;
BEGIN
  ms := (extract(epoch from clock_timestamp()) * 1000)::bigint;
  b  := uuid_send(gen_random_uuid());
  b  := overlay(b placing substring(int8send(ms) from 3 for 6) from 1 for 6);
  b  := set_byte(b, 6, (get_byte(b, 6) & 15) | 112);   -- version 7
  b  := set_byte(b, 8, (get_byte(b, 8) & 63) | 128);   -- variant 10
  RETURN encode(b, 'hex')::uuid;
END $$;
```

Then create one login role per agent, granted exactly one capability role, and set `kb.actor`
so RLS and the audit trail agree with `governance/roles.yaml`:

```bash
psql -d ai_kb <<'SQL'
CREATE ROLE "agent.compile-01" LOGIN PASSWORD 'change-me' IN ROLE kb_author;
ALTER ROLE "agent.compile-01" SET kb.actor = 'agent.compile-01';
CREATE ROLE "svc.release"     LOGIN PASSWORD 'change-me' IN ROLE kb_release;
ALTER ROLE "svc.release"      SET kb.actor = 'svc.release';
SQL
```

The release role gets its own credential and its own mount. That is what makes "only release
advances `main`" true at layer 3 rather than merely instructed.

Before ingesting anything you would be unhappy to lose: enable WAL archiving, take a base
backup, and **restore it onto a separate instance once** to prove recovery works.

## 2. TigerFS

```bash
curl -fsSL https://install.tigerfs.io | sh
tigerfs mount postgres://localhost/ai_kb /mnt/ai-kb
```

Create the three workspaces by declaring format and features in `.build/`. Adding `history`
opts a workspace into versioning; omit it to keep it off:

```bash
export COPYFILE_DISABLE=1                              # see the macOS notes below
echo "plaintext" > /mnt/ai-kb/.build/kb_raw            # history off, bytes are immutable
echo "markdown"  > /mnt/ai-kb/.build/kb_control        # tasks and leases
```

`history` requires the **TimescaleDB** extension; on plain PostgreSQL the write fails with
`history requires TimescaleDB extension`. That costs the design nothing, since history is
deliberately off for the byte stores anyway.

Verify a workspace really exists — the write can report success while the DDL behind it fails,
so check both sides:

```bash
ls -la /mnt/ai-kb/                                            # kb_raw, kb_control present?
psql -d ai_kb -c "\dt tigerfs.*"                              # matching tables present?
tail -f /path/to/tigerfs.log | grep -i error                  # the DDL error, if any
```

### Configuration: the file takes FLAT keys

This wasted an hour, so it goes first. `tigerfs config show` prints a **nested** layout
(`filesystem:` / `nfs:` / `connection:`), but the config file is parsed with **flat** keys. A
nested file is silently ignored, every field validates as zero, and you get:

```text
Error: invalid port: 0 (must be 1-65535)
```

which looks like a port problem and is not. Environment variables are flat too:
`TIGERFS_ATTR_TIMEOUT` works, `TIGERFS_FILESYSTEM_ATTR_TIMEOUT` does not. The file must also
supply every validated field, or validation fails on the next zero it finds.

A working file is committed here as [tigerfs-config.yaml](tigerfs-config.yaml); copy it to
`~/.config/tigerfs/config.yaml` (the path is fixed — `--config-dir` does not move it) and
confirm with `tigerfs config validate && tigerfs config show`.

### Tuning that measurably helps

| Setting | Default | Use | Why |
|---|---|---|---|
| `attr_timeout` | `1s` | `0s` | Git stats a file it just wrote; a 1s cache makes the stat lie |
| `entry_timeout` | `1s` | `0s` | Same, for directory entries — fixes `rename()` and close-to-open |
| `trailing_newlines` | `true` | `false` | Documented as "append newline to file reads" |
| `metadata_refresh_interval` | `10s` | `1s` | Staleness during rapid create/remove |
| `nfs_cache_idle_timeout` | `5m` | **leave at `5m`** | See the warning below |

**Do not lower `nfs_cache_idle_timeout`.** It is tempting, because a long handle cache is what
makes a deleted filename un-reusable. But at `50ms` with a `10ms` reaper, live handles are
evicted mid-operation and results get *worse* — a 200-file commit starts failing and the gate
drops from 21/35 to 17/35. Long enough to keep handles alive is long enough to poison name
reuse; there is no value that satisfies both.

### macOS notes

- TigerFS on macOS uses an **NFS loopback backend**, not FUSE — the log says
  `Using NFS backend for macOS`. macFUSE is not a prerequisite.
- Every mount advertises itself as `127.0.0.1:/`, and macOS keys NFS mounts by server spec.
  **Killing the `tigerfs` process leaves a stale mount that needs root to clear**, and until it
  is cleared, a *new* mount inherits the dead session: `stat` works, `readdir` hangs, and the
  new server logs no incoming requests. Always `tigerfs unmount <path>` while the mount is
  healthy. To recover: `sudo umount -f <path>`.
- Run the mount process in a way that lets it hold the foreground (`--foreground`, own terminal
  or supervisor). Piping its output into another command blocks that command indefinitely.
- macOS writes AppleDouble sidecars (`._name`) onto the mount — 5,464 bytes of metadata per
  file, and **40 of them inside one fresh `.git`**. macOS stamps files with a
  `com.apple.provenance` xattr, the mount cannot store xattrs, so the kernel writes a sidecar
  instead. Git then reads them as refs, loose objects, and pack indexes, and `git fsck` reports
  corruption that does not exist. `COPYFILE_DISABLE=1` does **not** stop this — it only affects
  `cp` and `tar`. This is the single largest reason Git looks broken here, and it is a
  macOS-on-NFS artifact rather than a TigerFS defect.
- `ops/gate-git-on-tigerfs` accepts `GATE_STRIP_APPLEDOUBLE=1`, which deletes sidecars before
  every git call. It is a diagnostic that approximates a filesystem without the AppleDouble
  shim; it is not a supported way to run a repository.
- Binary bodies are stored **base64-encoded** (the `encoding` column), so budget roughly 33%
  storage amplification for binary evidence.

Use the **same mount path on every host**. Git worktree metadata stores an absolute path to
its common git dir, so a host that mounts at a different path sees what looks like corruption.

Config lives at `~/.config/tigerfs/config.yaml` (`tigerfs config show`); every option also
takes a `TIGERFS_`-prefixed environment variable.

## 3. Gate: run it before trusting anything to the mount

```bash
mkdir -p /tmp/gate-control && ops/gate-git-on-tigerfs /tmp/gate-control   # control: must pass
ops/gate-git-on-tigerfs /mnt/ai-kb/kb_git                                 # the real gate
```

Results on 2026-08-04 (macOS, TigerFS 0.7.0, PG 17.9 + shim, git 2.50.1):

| Configuration | Score |
|---|---|
| Defaults | 11 / 34 |
| Tuned + `GATE_STRIP_APPLEDOUBLE=1` | **21 / 35** |
| Tuned but `nfs_cache_idle_timeout=50ms` | 17 / 35 |

Tuning fixed `rename()`, truncate-then-append, and close-to-open visibility. Stripping sidecars
fixed **every** `fsck`. What remains is one defect that no setting addresses: a deleted filename
cannot be recreated (10/10 `Input/output error`), which is exactly how Git uses `index.lock`,
`HEAD.lock`, and `packed-refs.lock`. The first attempt fails, leaves a stale lock, and every
later operation dies with `File exists`. Full analysis:
[claim.git-on-tigerfs-fails-the-gate](../wiki/claims/git-on-tigerfs-fails-the-gate.md).

Also worth knowing before designing around TigerFS: it supports exactly two workspace formats,
`markdown` and `txt`. There is no binary or verbatim format — it is a text and structured-data
filesystem by design.

34 automated checks: the primitives Git depends on (`O_EXCL`, atomic rename, binary round
trip, truncate/append, `fsync` on file and directory, close-to-open), then Git itself (200-file
commits, 8MB blobs through repack, merge/rebase/cherry-pick/revert, conflict *detection*),
worktree lifecycle, concurrency (ref compare-and-swap, 8 racing ref creations, 4 agents
committing in parallel worktrees), and `git fsck --full --strict` after everything destructive.

Run it at the size and agent count you expect, not at toy scale. The gate prints six **manual**
tests it cannot perform — cross-host visibility, killing TigerFS mid-ref-update, restarting
PostgreSQL mid-write, shared worktree paths, scale/latency at 1k–100k pages, and a restore
drill. The gate is not complete until those are done by hand. Record the outcome on the claim
page and promote or refute it.

## 4. Point the knowledge base at the mount

`bin/kb` takes its locations from the environment — no code changes:

```bash
export KB_GIT_DIR=/srv/kb/knowledge.git     # local disk
export KB_WORKTREES=/srv/kb/worktrees        # local disk
export KB_RAW=/mnt/ai-kb/kb_raw              # TigerFS -> PostgreSQL
export KB_CONTROL=/mnt/ai-kb/kb_control      # TigerFS -> PostgreSQL
export KB_ACTOR=agent.compile-01
export COPYFILE_DISABLE=1                    # macOS only
```

See [.env.example](../.env.example); load it with `set -a; . ./.env; set +a`.

Set all four explicitly. The defaults are repo-relative and convenient for local work, but on
a real deployment you want the raw store and control state on their own workspaces, not
wherever a worktree happens to sit.

## 5. Create the shared bare repository

```bash
# Git on local disk — it does not survive on TigerFS (step 3)
git clone --bare git@github.com:Astrapolis-peasant/hive-knowledge.git /srv/kb/knowledge.git
mkdir -p /srv/kb/worktrees
mkdir -p /mnt/ai-kb/kb_raw/sha256 /mnt/ai-kb/kb_control/{queue,leases,submitted}
```

Bare, because no ordinary agent should be able to edit a checked-out `main`. Shared, because
linked worktrees reuse one object database instead of copying it per agent.

Raw bytes do not come from git — `.raw/` is gitignored by design. Re-ingest the sources you
need on the new deployment, or copy the raw store across; the SHA-256 in each manifest is what
proves you got the same bytes, and `bin/kb validate` checks it.

## 6. Operational schedule

| Cadence | Task |
|---|---|
| continuous | WAL archiving |
| daily | base backup; `bin/kb validate` |
| weekly | `git fsck --full --strict` on the bare repo; `SELECT * FROM kb.audit_raw_hashes()` |
| weekly | `SELECT kb.expire_leases();` to release leases held by crashed agents |
| quarterly | restore drill onto a separate instance |

## 7. If the gate fails — this is the current state

Decided in advance, so nobody improvised during the incident. The gate failed, so option two
below is what is deployed:

- **Correctness passes, performance is weak** — add ephemeral local object caches keyed by
  commit SHA, or keep fewer persistent worktrees. Do not add infrastructure before measuring.
- **Correctness fails** — move the bare Git repository to a filesystem with certified Git
  behaviour and keep TigerFS/PostgreSQL as the raw and control store. Do **not** try to repair
  Git semantics in the agent layer; an agent cannot make a non-atomic rename atomic.

The second option changes the single-durable-store decision, so it needed an explicit
architecture review rather than a quiet config change — recorded in
[claim.git-on-tigerfs-fails-the-gate](../wiki/claims/git-on-tigerfs-fails-the-gate.md) and
[synthesis.four-layer-separation](../wiki/syntheses/four-layer-separation.md).

Everything else in the design was unaffected, which was the point of keeping the layers
separate: the full lifecycle — ingest to the TigerFS raw store, task worktree, hook-enforced
commit, compare-and-swap release, pinned-commit query — was exercised end-to-end on the hybrid
deployment with no changes to the wiki model, the branch workflow, or the permission layers.

The cost is real, though: published bytes and evidence bytes now live in two places with two
recovery procedures. Back up and restore-test both together.
