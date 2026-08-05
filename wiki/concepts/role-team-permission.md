---
id: concept.role-team-permission
page_type: concept
status: active
owner: team.knowledge
visibility: public
confidence: high
summary: Write authority is the intersection of role and team, enforced in four layers because each layer catches a different class of failure.
updated_at: 2026-08-04
sources:
  - source.ai-knowledge-base-architecture
tags:
  - permissions
  - authority
  - enforcement
  - unreviewed
  - publication
related:
  - entity.postgresql
  - concept.content-addressed-store
  - topic.knowledge-base-foundations
  - synthesis.four-layer-separation
supersedes: []
---

# Role × Team Permission

## Definition

An agent may write a path only if **both** hold:

```text
may_write(actor, path) =
      path matches a write glob of the actor's ROLE          (what kind of work)
  AND (path is outside wiki/  OR  a TEAM of the actor owns it)   (which knowledge area)
```

Roles are declared in `governance/roles.yaml`, team ownership in `governance/owners.yaml`.
Six roles: `reader`, `ingest`, `compile`, `lint`, `release`, `admin`. An actor has exactly one
role and one or more teams. Unknown actors are refused — there is no default-allow.

## Current Understanding

Two axes are needed because they answer different questions. A role says *what kind of change*
an agent is competent and permitted to make: `ingest` captures evidence but must not
synthesize; `compile` writes pages but must not touch source manifests; `release` publishes but
does not author. A team says *which knowledge area* it is accountable for. Collapsing them
would mean either every compile agent can rewrite every page, or a page's owner also decides
what kind of work is allowed on it.

Stated as the guarantee a reader usually wants: **unreviewed knowledge cannot become published
knowledge.** An agent can write anything on its own branch; it cannot publish. Publication is a
separate role, gated on validation and review, and it is the only path by which a page reaches a
reader.

Two invariants have no exceptions:

- **Only `release` advances `refs/heads/main`.** The update is a compare-and-swap against the
  expected old SHA, so two concurrent releases cannot interleave — the loser re-runs rather
  than overwriting. See [[concept.commit-pinned-read]] for why publication must be atomic.
- **Raw source bytes are create-only.** Enforced by revoked `UPDATE`/`DELETE` grants plus a
  trigger, not by instructions. See [[concept.content-addressed-store]].

Four enforcement layers, because each catches a failure the others cannot:

| Layer | Mechanism | Catches |
|---|---|---|
| Instruction | `AGENTS.md` | a cooperative agent straying |
| Verification | `checks/validate-permissions`, pre-commit hook | an agent that drifts or errs |
| Filesystem | separate TigerFS workspaces, mount credentials | a compromised process |
| Database | PostgreSQL roles, RLS on `current_user`, immutability trigger | everything above being wrong |

Cross-team changes are legitimate and expected. The route is: make the change, mark the task
`review_required: true`, and let `release` merge it after a reviewer from the owning team
approves. Widening your own role is never the answer, and the failure is deliberately loud and
early — a commit-time error naming the owning team, rather than a merge surprise at release.

Two exemptions exist and both are principled. The **bootstrap commit** of a fresh repository
skips the branch check, because before any commit there is no `main` to protect. The
**generated indexes** (`wiki/index.md`, `sources/index.md`) skip the team check, because they
are a pure function of the pages and are verified byte-exact — ownership of them would only
stop other teams from reindexing.

**Identity is only authenticated at layer 4.** Each agent logs in as a PostgreSQL role named
exactly its actor id, so `current_user` *is* the actor: columns default to it and row-level
security compares it. Impersonation there requires actually authenticating as that role.
Verified 2026-08-05 against a live database — an agent inserting a task row attributed to
another actor is refused, and so is the same attempt after overriding a session variable.

An earlier version compared a `kb.actor` session setting, which any session can overwrite with
`SET kb.actor = 'someone.else'`. That made the policy decorative against precisely the case it
existed for. The rule it teaches generalises: **authenticate, do not ask.** An identity the
caller can set is not an identity.

## Disputed or Uncertain

**`KB_ACTOR` at layers 1–2 is still self-asserted.** The pre-commit hook verifies *intent*, not
identity — an agent can claim any actor id, or uninstall the hook. This is the largest
remaining gap in the model, and it is closed at the forge rather than in this repository: with
branch protection requiring a reviewed pull request, "only review advances `main`" is enforced
by something the contributor does not control, and the approval *is* the release role. Until
that is configured, treat the publish restriction as a strong convention rather than a
guarantee.

`visibility:` (`public` / `internal` / `restricted`) is **advisory in the Git layer**. Anyone who
can read the commit can read a restricted page; the field tells a well-behaved query agent not
to quote it. Real read control needs a separate workspace credential or row-level security. Do
not present frontmatter as access control.

Layers 3 and 4 are deployment configuration, not code in this repository — a deployment that
skips them is relying on layers 1 and 2, which stop mistakes but not a compromised process.
The pre-commit hook also does not survive `git clone`, so each clone must run
`bin/kb install-hooks`; enforcing that needs `core.hooksPath` or a server-side check.

## Evidence

- [source.ai-knowledge-base-architecture](../../sources/manifests/source.ai-knowledge-base-architecture.yaml) — sections 5.5, 9.4, and 13 define the roles, restrict `main` to the release path, and require enforcement below the prompt layer.
