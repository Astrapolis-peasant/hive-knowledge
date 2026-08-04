# Knowledge Base

A multi-agent knowledge base: PostgreSQL for bytes, TigerFS for file access, Git for isolation
and publication, and a Karpathy-style LLM Wiki as the knowledge model.

Markdown all the way down. No vector database, no queue, no custom API, no Python packages —
the validators are stdlib-only, so any agent with `python3`, `git`, and `bash` can work here.

- **Agents start at [AGENTS.md](AGENTS.md)** — the operating contract.
- Design rationale: [AI_Knowledge_Base_Architecture.md](AI_Knowledge_Base_Architecture.md)
- Permissions: [governance/permissions.md](governance/permissions.md)
- What the wiki knows: [wiki/index.md](wiki/index.md) · what happened: [wiki/log.md](wiki/log.md)

## 60-second tour

```bash
bin/kb init                              # git repo, raw store, control dirs, pre-commit hook
export KB_ACTOR=agent.compile-01         # an actor in governance/roles.yaml
bin/kb whoami                            # role, teams, writable paths

bin/kb task start add-attention-paper    # branch + worktree + pinned base commit
cd .worktrees/t*-add-attention-paper
bin/kb new-page concept kv-cache "What a KV cache is and why it bounds context cost"
bin/kb reindex && bin/kb validate        # deterministic checks, must pass
git add -A && git commit -m "task: add kv-cache"
bin/kb task submit

KB_ACTOR=svc.release bin/kb release <branch>   # only this role can advance main
```

Reading is separate and never writes:

```bash
COMMIT=$(bin/kb pin)                     # pin one commit for the whole request
bin/kb show "$COMMIT" wiki/index.md
bin/kb grep "$COMMIT" "worktree"
```

## Layout

```text
AGENTS.md                the contract agents must follow
wiki/                    the knowledge base
  index.md               generated catalog — never hand-edit
  log.md                 chronological record of accepted changes
  concepts/ entities/ topics/ claims/ questions/ syntheses/
sources/
  index.md               generated
  manifests/             one YAML per source; the stable citation identity
governance/
  roles.yaml             roles, capability grants, registered actors
  owners.yaml            teams and the paths they own
  permissions.md         how the four enforcement layers fit together
checks/                  deterministic validators (stdlib only)
schemas/                 JSON Schema, for editors and humans
templates/               page and manifest skeletons
db/schema.sql            PostgreSQL roles, raw immutability, task leases
ops/
  tigerfs.md             deploying onto PostgreSQL + TigerFS
  gate-git-on-tigerfs    Phase 0 compatibility gate — run before trusting a mount
bin/kb                   the only CLI an agent needs
plugins/hive-knowledge/  the Claude Code plugin (skill + slash commands)
```

Not in Git, and deliberately: `.raw/` (immutable source bytes, content-addressed),
`.worktrees/` (task checkouts), `.kb/` (tasks and leases), `.derived/` (disposable retrieval
indexes). In production these are separate TigerFS workspaces — see
[wiki/entities/tigerfs.md](wiki/entities/tigerfs.md).

## Permission control in one table

Write authority is the intersection of **role** (what kind of work) and **team** (which
knowledge area). Four layers enforce it, because each catches a different failure:

| Layer | Mechanism | Ships here |
|---|---|---|
| Instruction | `AGENTS.md` | yes |
| Verification | `checks/validate-permissions`, pre-commit hook | yes |
| Filesystem | separate TigerFS workspaces + mount credentials | deployment |
| Database | PostgreSQL roles, RLS, create-only raw table | `db/schema.sql` |

Two invariants have no exceptions: **only the release role advances `main`** (compare-and-swap
on the ref), and **raw source bytes are create-only** (revoked grants plus a trigger, with
content-addressing making the invariant auditable).

## Use it from another project

This repo is also a Claude Code plugin marketplace, so agents working in other codebases can
query and update the knowledge base:

```
/plugin marketplace add Astrapolis-peasant/hive-knowledge
/plugin install hive-knowledge@hive-knowledge
```

That adds a `kb` skill (Claude invokes it when a question looks like something the knowledge
base covers) plus `/kb-query <question>` and `/kb-task <what to record>`. Point it at your
clone with `export KB_HOME=/path/to/hive-knowledge`.

The plugin is the interface, not the data — it carries no wiki content. Permission control
stays with `KB_ACTOR` and the checks in the clone; a skill can guide an agent but cannot grant
it anything.

## Deploying on PostgreSQL + TigerFS

[ops/tigerfs.md](ops/tigerfs.md) is the deployment path: schema, roles, workspaces, mount, and
the env vars that point `bin/kb` at them (`.env.example`). Step 3 is a gate, not a formality:

```bash
mkdir -p /tmp/gate-control && ops/gate-git-on-tigerfs /tmp/gate-control   # control
ops/gate-git-on-tigerfs /mnt/ai-kb/kb-git                                 # the real thing
```

34 automated checks — the primitives Git depends on, then Git itself, then worktrees,
concurrency, and `fsck` after everything destructive — plus six manual tests it prints and
cannot perform for you.

## Status

The scaffold, checks, permission model, and seed wiki work today on a local filesystem —
`bin/kb validate` passes with zero warnings.

The compatibility gate is written and passes 34/34 on local disk, which makes it a trustworthy
control — but **it has never been run against TigerFS**, because nothing here has been deployed
on it yet. Until it is, treat
[claim.git-on-tigerfs-unverified](wiki/claims/git-on-tigerfs-unverified.md) as the open blocker
for production it says it is.

Then, in order: PostgreSQL deployment with `db/schema.sql` and per-agent roles, the six manual
gate tests (cross-host visibility, crash injection, restore drill), and retrieval measurement
([question.retrieval-scale-threshold](wiki/questions/retrieval-scale-threshold.md)) before any
index gets built.
