# Deploying on the TigerFS backend

The knowledge base runs on a local filesystem today. This is how it moves to the intended
production substrate: PostgreSQL for bytes, TigerFS presenting them as files.

**Read this first:** step 3 is a gate, not a formality. Git-on-TigerFS is an untested
assumption ([wiki/claims/git-on-tigerfs-unverified.md](../wiki/claims/git-on-tigerfs-unverified.md)),
and if it fails you deploy the fallback in step 7 rather than working around it.

## Topology

```text
PostgreSQL (one instance, WAL archiving on)
└── TigerFS mount, same path on every agent host
    ├── kb-git/      plaintext, history OFF   bare repo + linked worktrees
    ├── kb-raw/      plaintext, history OFF   content-addressed immutable sources
    └── kb-control/  markdown,  history opt.  tasks and leases
```

Three workspaces because they have different write patterns. History is **off** for `kb-git`:
Git already versions its content, and versioning every loose object, lockfile, and packfile
rewrite doubles the write volume for nothing.

## 1. PostgreSQL

```bash
createdb ai_kb
psql -v ON_ERROR_STOP=1 -d ai_kb -f db/schema.sql
psql -d ai_kb -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"   # for kb.audit_raw_hashes()
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
echo "plaintext"        > /mnt/ai-kb/.build/kb-git       # history OFF, deliberately
echo "plaintext"        > /mnt/ai-kb/.build/kb-raw       # history OFF, bytes are immutable
echo "markdown,history" > /mnt/ai-kb/.build/kb-control   # history optional here
```

Use the **same mount path on every host**. Git worktree metadata stores an absolute path to
its common git dir, so a host that mounts at a different path sees what looks like corruption.

Config lives at `~/.config/tigerfs/config.yaml` (`tigerfs config show`); every option also
takes a `TIGERFS_`-prefixed environment variable.

## 3. Gate: run it before trusting anything to the mount

```bash
mkdir -p /tmp/gate-control && ops/gate-git-on-tigerfs /tmp/gate-control   # control: must pass
ops/gate-git-on-tigerfs /mnt/ai-kb/kb-git                                 # the real gate
```

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
export KB_GIT_DIR=/mnt/ai-kb/kb-git/knowledge.git
export KB_WORKTREES=/mnt/ai-kb/kb-git/worktrees
export KB_RAW=/mnt/ai-kb/kb-raw
export KB_CONTROL=/mnt/ai-kb/kb-control
export KB_ACTOR=agent.compile-01
```

See [.env.example](../.env.example); load it with `set -a; . ./.env; set +a`.

Set all four explicitly. The defaults are repo-relative and convenient for local work, but on
a real deployment you want the raw store and control state on their own workspaces, not
wherever a worktree happens to sit.

## 5. Create the shared bare repository

```bash
git clone --bare git@github.com:Astrapolis-peasant/hive-knowledge.git \
  /mnt/ai-kb/kb-git/knowledge.git
mkdir -p /mnt/ai-kb/kb-git/worktrees /mnt/ai-kb/kb-raw/sha256 \
         /mnt/ai-kb/kb-control/{queue,leases,submitted}
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

## 7. If the gate fails

Decided in advance, so nobody improvises during an incident:

- **Correctness passes, performance is weak** — add ephemeral local object caches keyed by
  commit SHA, or keep fewer persistent worktrees. Do not add infrastructure before measuring.
- **Correctness fails** — move the bare Git repository to a filesystem with certified Git
  behaviour and keep TigerFS/PostgreSQL as the raw and control store. Do **not** try to repair
  Git semantics in the agent layer; an agent cannot make a non-atomic rename atomic.

The second option changes the single-durable-store decision, so it needs an explicit
architecture review rather than a quiet config change. Everything else in the design —
the wiki model, the branch workflow, the permission layers — is unaffected either way.
