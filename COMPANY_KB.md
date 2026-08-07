# Company Knowledge Base — Scope and Status

This repository is an exploration of one question: **can a company knowledge base be built out
of markdown, git, and deterministic checks, with no dedicated knowledge service?**

It is shaped as a prototype and shipped as a Claude Code plugin, so a platform can mount it
rather than replace what it already has. This document states what a company knowledge base has
to guarantee, where this implementation currently stands against those guarantees, and what is
still open. It is written for people about to build or extend a company knowledge layer — here
or elsewhere.

**Section 1 deliberately contains no implementation requirements.** It says what must be true,
not how. Section 2 is one way to satisfy it, and the choices there are ours, not the boundary.

Design rationale for the current implementation: [AI_Knowledge_Base_Architecture.md](AI_Knowledge_Base_Architecture.md).
Operating contract for agents: [AGENTS.md](AGENTS.md).

---

## 1. What a company knowledge base must guarantee

Twelve boundaries in four groups. Each is a property that has to hold; how it holds is open.

### Authority — who gets to say what is true

**A1. Every published statement has a named accountable owner.**
Not an author, an owner: the party answerable for the statement still being true. Anonymous
knowledge cannot be audited, corrected, or retired, because nobody is on the hook for it.

**A2. Publication authority is separable from authoring authority.**
Whoever writes must not be the same authority that publishes. The gap between the two is where
review lives, and it is the only structural defense against an agent promoting its own output
into organizational truth.

**A3. Write scope is bounded and denied by default.**
An unknown actor gets nothing. A known actor gets a stated, enumerable scope. "What may this
actor change?" must be answerable before the change, not discovered after it.

### Evidence — how a conclusion is supported

**E1. Synthesized knowledge and source evidence are stored separately, and evidence is
immutable.**
Conclusions get rewritten as understanding improves; the material they were drawn from must not.
Collapsing the two means a revised conclusion silently rewrites its own justification.

**E2. Citations are stable identities, not copied text.**
A citation must survive the cited thing being reorganized, and must let a reader reach the
original bytes. A pasted excerpt is a snapshot that quietly drifts from what it claims to quote.

**E3. Confidence is declared and earned.**
A page states how sure it is, and the strongest confidence level requires real captured
evidence behind it. An assertion produced from weak retrieval must not be filed back as
knowledge at full confidence.

**E4. Disagreement has a structural home.**
Contradiction is a normal state of organizational knowledge, not an error. If the format has no
place to record "these two things conflict, here is both sides," the system will flatten
conflicts into whichever side was written last.

### Reading — what a consumer gets

**R1. One answer draws from one consistent version of the knowledge base.**
Two statements can each be correct at different versions and jointly wrong when mixed. A read
must be pinned to a single point in time for its whole duration.

**R2. Retrieval returns identities; consumers read whole units.**
Search hands back candidate pages, not prose fragments. A matching snippet is a pointer, never
evidence — answering directly from ranked excerpts is how retrieval systems produce confident
nonsense.

**R3. Trustworthiness participates in relevance.**
A superseded or low-confidence page can be the best lexical match and still be the wrong answer
to give. Ranking that ignores status will surface retired knowledge at the top.

**R4. "The knowledge base does not know" is a first-class answer.**
There must be a way to record an open question, and returning a gap must be an acceptable
outcome rather than pressure to guess.

### Health — knowing when it is rotting

**H1. Read control is either enforced or declared advisory.**
Whatever the visibility model is, the system must state plainly where it is actually enforced.
A metadata field that looks like access control but is not is worse than no field at all.

**H2. Derived artifacts are disposable and never authoritative.**
Indexes, caches, embeddings, graphs, and projections must be rebuildable from the canonical
content, and must never become a second source of truth. When a derived layer starts holding
facts the canonical layer lost, the knowledge base has quietly forked.

**H3. Decay is observable, and infrastructure decisions are evidence-driven.**
Orphaned pages, stale drafts, unanswered questions, near-duplicates, and retrieval failures must
all be measurable. Heavier retrieval infrastructure is justified by measured failure, not by
anticipation — and the measurement has to exist before the failure does.

**H4. Mechanical checks own form; models and people own meaning.**
Schema, references, scope, and integrity are machine-decidable and should be hard-enforced.
Whether a conclusion is sound, a claim is stale, or two pages contradict is a judgment call —
those belong in advisory findings routed to review, never in automatic edits to published pages.

---

## 2. Where this repository currently stands

Roughly 2,100 lines of stdlib-only Python and bash, no dependencies, over 12 wiki pages and 8
source manifests. `bin/kb validate` passes with zero warnings; the validator suite is 43 tests.

| Boundary | Status | How, in this implementation |
|---|---|---|
| A1 owner | met | Every page declares an accountable team; validation rejects a team that does not claim the path |
| A2 publish ≠ author | met | Only the release role advances `main`, via compare-and-swap on the ref; authors commit to task branches |
| A3 bounded scope | met | Write authority is the intersection of role and team, checked at commit time |
| E1 evidence separate + immutable | met | Content-addressed create-only store outside the repo; hashes verified against manifests |
| E2 stable citations | met | Source manifests are the citation identity; pages cite ids, never inline copies |
| E3 confidence earned | met | Highest confidence requires at least one active source with captured bytes |
| E4 disagreement | met | A required page section, kept even when the answer is "none known" |
| R1 pinned reads | met | One commit resolved per request; all reads served from it |
| R2 identity not prose | met | Ranked search returns page ids and summaries only |
| R3 trust in ranking | met | Status and confidence weight the relevance score |
| R4 gaps | met | Question pages are a first-class type, exempt from the citation requirement |
| H1 read control | **partial, declared** | Visibility is metadata and advisory in the git layer. Documented as such; real enforcement is a deployment concern |
| H2 derived disposable | met | Generated indexes are verified byte-exact against their inputs; derived retrieval state is excluded from the repo |
| H3 measurable decay | **partial** | Health findings and retrieval-miss logging exist; the accumulated measurement is still thin |
| H4 form vs meaning | met | Deterministic checks are hard gates; semantic findings are report-only and land on a separate branch |

**Known gaps, stated plainly:**

- **Actor identity at the commit layer is self-asserted.** The commit hook verifies intent, not
  identity. Real identity requires an authenticated layer underneath, or forge-side branch
  protection where the review approval *is* the release authority.
- **The database and filesystem enforcement layers are reference material, not wired.** The
  schema in `db/` is not referenced by any code path; the CLI runs entirely on files today.
- **There is no automatic learning.** Knowledge enters only when someone deliberately opens a
  task and writes a page. Nothing is distilled from conversations or runs.
- **Scale is unproven.** The machinery is currently larger than the content it serves. The
  design argument is about a thousand pages and many agents; that has not been tested.

---

## 3. In progress and open

- **Storage substrate.** A compatibility gate against a database-backed filesystem failed on one
  platform for a reason that is not tunable, so the deployed shape is currently split: git on
  local disk, database-backed storage for evidence and control state. Re-running the gate on a
  different backend is one experiment that decides whether the single-store shape is
  recoverable. See `wiki/claims/` and `ops/`.
- **Retrieval threshold.** Ranked retrieval and miss-logging exist; the open part is at what
  point a vocabulary gap justifies heavier infrastructure. Deliberately blocked on measurement
  rather than on opinion — see `wiki/questions/retrieval-scale-threshold.md`.
- **Read control that is real.** H1 is the largest honest gap. Enforcing visibility for real
  needs an authority layer below the markdown, and the design for that is not settled.
- **Manual gate items.** Cross-host visibility, crash injection, and a restore drill are
  described but not yet performed.
- **Ingestion surface.** Sources enter through one CLI path today. What a governed ingestion
  path looks like when material arrives from many places is not designed.

---

## 4. What this is not

Scope discipline matters more here than feature count, so this is explicit:

- **Not an agent's own memory.** Agent memory is private, high-frequency, and automatically
  written. This repository's model — deliberate authoring, review before publication, atomic
  releases — is a poor fit for that, and trying to serve both would break the parts that work.
- **Not a personal knowledge base.** Everything here is owned by a team. There is no
  individual-scoped authority, and adding one would be a different design.
- **Not a policy enforcement plane.** Policy text can live here and be cited; rules that must
  actually constrain behavior have to be enforced where the effect happens, not in a document an
  agent is trusted to search for.
- **Not a replacement for an existing knowledge service.** It ships as a plugin so it can be
  mounted alongside one. The plugin carries the interface, never the content.

The properties in section 1 are the useful export. If a different implementation satisfies them
better, that is a good outcome for this exploration.

---

## 5. Where to start

Read [AGENTS.md](AGENTS.md) first — it is short, and it is the operating contract. Then:

```bash
bin/kb whoami                  # your role and writable scope
bin/kb ask "<a question>"      # the read path
bin/kb validate                # what the mechanical layer actually checks
bin/kb lint                    # what it deliberately leaves to judgment
```

The highest-value contributions right now are against the gaps in section 2 and the open items
in section 3, in that order. Disagreement with section 1 is more valuable still: a boundary that
turns out to be wrong is worth more than another feature satisfying a boundary that was never
needed.
