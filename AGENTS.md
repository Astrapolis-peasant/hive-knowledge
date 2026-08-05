# AGENTS.md — Operating Contract

You are working in a multi-agent knowledge base. This file is the contract. Read it before
writing anything. It is short on purpose.

Architecture rationale: [AI_Knowledge_Base_Architecture.md](AI_Knowledge_Base_Architecture.md).
Permission model: [governance/permissions.md](governance/permissions.md).

## 1. The rule that explains everything else

> Raw sources preserve evidence. The wiki preserves synthesized knowledge. Git preserves
> intent and publication history. PostgreSQL/TigerFS preserve bytes.

Never collapse these. Do not paste a source into a wiki page and call it knowledge. Do not
delete evidence because a page now summarizes it.

## 2. What you may touch

Your role is passed to you as `KB_ACTOR` (an id in `governance/roles.yaml`). If it is unset,
assume `role: reader` and write nothing.

| Role | May write | May not |
|---|---|---|
| `reader` | nothing | everything |
| `ingest` | `sources/**`, raw store | `wiki/**` outside cited pages |
| `compile` | `wiki/**` within your team's owned paths | `sources/manifests/**` |
| `lint` | `wiki/**` on a `lint/*` branch, report-only | direct fixes to disputed content |
| `release` | `refs/heads/main` | authoring content |
| `admin` | `governance/**`, `schemas/**`, `checks/**` | — |

Two hard boundaries, enforced outside this file (git hook, PostgreSQL role, mount
credential — see `governance/permissions.md`):

1. **Only the release role advances `main`.** You commit to a task branch. Always.
2. **Raw source bytes are immutable.** Create-only. No update, no delete, ever.

Team ownership of wiki paths lives in `governance/owners.yaml`. If you need to change a page
your team does not own, write the change and mark it `review_required: true` in the task
record — do not merge it yourself.

## 3. Before you write

```bash
bin/kb whoami                 # confirm your role and writable scope
bin/kb task start <slug>      # creates branch + worktree, pins your base commit
```

`task start` prints your worktree path. Work only there. Never edit a checkout you did not
create, and never share a worktree with another agent.

## 4. How to write a page

```bash
bin/kb new-page concept kv-cache "What a KV cache is and why it bounds context cost"
```

Every page carries this frontmatter. All fields except `related`, `supersedes`, and `tags`
are required:

```yaml
---
id: concept.kv-cache          # <page_type>.<slug>, must match filename
page_type: concept            # concept|entity|topic|claim|question|synthesis
status: active                # draft|active|superseded|deprecated
owner: team.platform          # a team in governance/owners.yaml
visibility: internal          # public|internal|restricted
confidence: medium            # high|medium|low
summary: One line. Shown in the index; keep it scannable.
updated_at: 2026-08-04
sources:                      # source ids; every one needs a manifest
  - source.tigerfs-spec
related:
  - concept.prefill
supersedes: []
---
```

Body sections, in this order. Keep every section, even if the answer is "none known":

```markdown
# Title

## Definition
## Current Understanding
## Disputed or Uncertain
## Evidence
```

**YAML subset.** The validators are stdlib-only. Frontmatter and manifests support exactly:
`key: value`, `key:` followed by `  - item` lines, `[]`, `# comments`. No nested maps, no
multi-line strings, no anchors. A parse error is a validation failure, not a warning.

## 5. Epistemic discipline

Label what you know by how you know it. Never silently promote across these lines:

- source-reported fact → cite the source id
- direct observation → say what was run and when
- user preference or opinion → attribute it
- your own inference → mark it as inference
- disputed → put it under `## Disputed or Uncertain`, with both sides
- unknown → open a `question.*` page instead of guessing

`confidence: high` requires at least one `status: active` source with captured bytes.
An answer you produced from weak retrieval is not knowledge. Do not file it back.

## 6. Finish a task

```bash
bin/kb test                   # validator test suite (also runs in the pre-commit hook)
bin/kb validate               # deterministic checks; must pass
bin/kb reindex                # wiki/index.md is generated — never hand-edit it
git add -A && git commit -m "task(<id>): <what changed>"
bin/kb task submit            # queues for the release role
```

`bin/kb validate` also runs the permission check against your role. If it fails on scope,
you touched something you do not own — split the change, do not widen your role.

Append one line to `wiki/log.md` per accepted change. It is the chronological record;
`wiki/index.md` is the catalog. They are not interchangeable.

## 7. How to answer a question (read path)

```bash
COMMIT=$(bin/kb pin)                    # resolve main once, pin it for the whole request
bin/kb ask "why do queries pin a commit"    # ranked candidates — start here
bin/kb show "$COMMIT" wiki/concepts/commit-pinned-read.md   # read the WHOLE page
bin/kb links concept.commit-pinned-read     # what points here, what it cites
```

`kb ask` ranks pages by BM25 over id, title, summary, headings, and body, then weights the
score by `status` and `confidence` — a superseded page is a worse answer than an active one
even when it matches better. Filters (`--type`, `--owner`, `--min-confidence`, `--status`)
apply *before* ranking, which is the cheapest way to cut context noise.

Reach for `bin/kb grep "$COMMIT" "<exact string>"` when you need an exact string rather than a
topic — an error message, a flag name, an id.

Rules:

- Pin one commit per request. Never mix pages from two commits in one answer.
- Search returns candidate *page identities*. Read the whole page before using it.
- Cite page ids and source ids. Say when the wiki does not know.
- Reading is not writing. If the answer produces a durable synthesis, open a normal task.
- **If retrieval fails on something the wiki should know, record it:** `bin/kb miss "<query>"`.
  That is the only evidence that would justify building heavier retrieval, and nobody else is
  collecting it. `bin/kb stats` shows what has accumulated.

## 8. Do not

- edit `main`, or any worktree you did not create
- hand-edit `wiki/index.md` (generated) or anything under `.derived/` (disposable)
- store secrets, tokens, or keys anywhere in this repo
- add a vector DB, queue, or cache to solve a problem you have not measured
- keep a branch alive for days — rebase or regenerate the proposal instead
- treat a search snippet as evidence
