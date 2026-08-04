---
name: kb
description: Query or update a hive-knowledge base — a git-published markdown wiki with role and team permission control. Use when the user asks what we know about a topic, asks you to record or write down knowledge, cites a page id like concept.x or a source id like source.y, mentions the knowledge base / hive / wiki, or asks to ingest a source. Also use before answering a question the team's knowledge base plausibly already covers.
---

# Hive Knowledge Base

A knowledge base several agents maintain concurrently. Reads pin one git commit; writes go
through an isolated task worktree; write authority is role × team. Everything is markdown and
one CLI — there is no API to learn.

## 1. Locate the knowledge base

In order, stop at the first that works:

1. `$KB_HOME` if set.
2. The current directory, if `AGENTS.md` and `bin/kb` both exist — you are already inside it.
3. Ask the user for the path, or offer to clone:
   `git clone git@github.com:Astrapolis-peasant/hive-knowledge.git && cd hive-knowledge && bin/kb init`

Run every command below from that directory. Prefix with `cd "$KB_HOME" &&` when you are
working in a different project. If no knowledge base is reachable, say so — do not answer
from memory and present it as what the knowledge base says.

## 2. Read path (default — use this unless asked to write)

```bash
COMMIT=$(bin/kb pin)                                   # pin ONE commit for the whole request
bin/kb show "$COMMIT" wiki/index.md                    # catalog: id, summary, owner, confidence
bin/kb grep "$COMMIT" "<term>"                         # exact lexical search
bin/kb show "$COMMIT" wiki/concepts/<slug>.md          # read the WHOLE page
```

Rules that change your answer:

- **Never mix commits.** Two pages from two commits can each be right and jointly wrong.
- **Read whole pages**, not grep lines. A matching line is a pointer, not evidence.
- **Report the page's own confidence.** `confidence: low`, or anything under
  `## Disputed or Uncertain`, means hedge and say why — do not launder it into a clean answer.
- **Cite page ids and source ids** (`concept.kv-cache`, `source.tigerfs-spec`).
- **Say when it does not know.** A gap is a real answer. Offer to open a `question.*` page.
- **Reading never writes.** If the user wants the finding kept, switch to the write path.

## 3. Write path

Requires an actor: `export KB_ACTOR=<id>` from `governance/roles.yaml` (`bin/kb whoami` shows
role, teams, and writable globs). No actor means read-only, and the pre-commit hook refuses
unattributed commits.

```bash
bin/kb task start <slug>          # branch + worktree + pinned base; prints the worktree path
cd <that worktree>                # work ONLY here — never edit main or another worktree
bin/kb new-page <concept|entity|topic|claim|question|synthesis> <slug> "<one-line summary>"
# edit the page, then:
bin/kb reindex && bin/kb validate # index is generated; validation must pass
git add -A && git commit -m "task: <what changed>"
bin/kb task submit                # queues for the release role
```

To register a source (role `ingest`), which hashes and stores the bytes create-only:

```bash
bin/kb ingest --file <path> --title "<title>" --type <web|paper|repo|conversation|note> [--url <u>]
```

Publishing is a separate role and is not yours unless you were given it:
`KB_ACTOR=svc.release bin/kb release <branch>`.

## 4. Page rules

Frontmatter is required and validated: `id`, `page_type`, `status`, `owner`, `visibility`,
`confidence`, `summary`, `updated_at`, `sources`. Body sections, in order: `## Definition`,
`## Current Understanding`, `## Disputed or Uncertain`, `## Evidence`. Keep every section —
write "None known." rather than deleting one.

Epistemic rules, which are the point of the whole system:

- Label how you know something: source-reported, observed, user's opinion, your inference,
  disputed, unknown. Never silently promote an inference into a fact.
- `confidence: high` requires a cited source with `status: active` (bytes captured and hashed).
  Validation enforces this — you cannot claim certainty on evidence nobody has.
- Never file an answer you produced from weak retrieval back into the wiki.

YAML is a strict subset: flat `key: value`, `key:` plus `  - item` lists, `[]`, `#` comments.
No nested maps, no multi-line strings. A parse error fails validation.

## 5. When something is refused

`bin/kb validate` and the pre-commit hook fail with a precise reason. Read it and act:

| Message | What to do |
|---|---|
| `no team of <actor> owns this path` | Your team does not own it. Split the change, or set `review_required: true` and let the owning team review. Never widen your own role. |
| `role <r> must not commit on main` | Use `bin/kb task start`. Only `release` publishes. |
| `<file> is stale — run bin/kb reindex` | The index is generated; never hand-edit it. |
| `confidence high requires ... status active` | Lower the confidence or ingest the source. |
| `wikilink [[x]] resolves to no page id` | Create the page or fix the link. |
| `KB_ACTOR is unset` | Export an actor id from `governance/roles.yaml`. |

Full contract: `AGENTS.md` in the knowledge base. Permission model:
`governance/permissions.md`. Architecture: `AI_Knowledge_Base_Architecture.md`.
