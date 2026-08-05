# Permission Model

Four layers. Each one alone is insufficient; an agent that ignores layer 1 is stopped by
layer 2, and a compromised process is stopped by layers 3 and 4.

| Layer | Mechanism | Stops | Where |
|---|---|---|---|
| 1. Instruction | `AGENTS.md` section 2 | a cooperative agent from straying | prompt |
| 2. Verification | `checks/validate-permissions` | a mistaken or drifting agent | pre-commit hook, `bin/kb validate`, release gate |
| 3. Filesystem | separate TigerFS workspaces + mount credentials | a process from reaching bytes it has no business with | mount |
| 4. Database | PostgreSQL roles, grants, RLS, immutability trigger | everything above being wrong | `db/schema.sql` |

Layer 1 and 2 ship in this repo and work today. Layers 3 and 4 are deployment
configuration; `db/schema.sql` is the reference implementation.

## Roles

Defined in [roles.yaml](roles.yaml). The grant is `role -> (writable path globs, allowed
branch patterns, raw-store capability)`. Six roles, deliberately: `reader`, `ingest`,
`compile`, `lint`, `release`, `admin`.

An actor is a named agent or human with exactly one role and one or more teams. Unknown
actors are refused — there is no default-allow.

## Teams

Defined in [owners.yaml](owners.yaml). A team owns path globs. A wiki page names its
accountable team in frontmatter `owner:`.

Write authority for a wiki path is the **intersection** of role and team:

```
may_write(actor, path) =
      path matches any glob in role.<actor.role>.write
  AND (path is outside wiki/  OR  path matches a glob of some team in actor.teams)
```

This is what makes the model useful for a team rather than a single operator: two compile
agents on different teams cannot silently overwrite each other's area, and the failure is a
validation error at commit time, not a merge surprise at release time.

Cross-team changes are legitimate and expected. The route is: write the change, mark the task
`review_required: true`, and let the release role merge it after a reviewer from the owning
team approves. Widening your own role is never the answer.

## Read control

Page frontmatter `visibility:` is `public`, `internal`, or `restricted`.

- `public` — may appear in answers to anyone.
- `internal` — may appear in answers to authenticated team members.
- `restricted` — a query agent must not quote it; it may only say a restricted page exists
  and name its id, unless the caller is in the owning team.

This is advisory in the git layer (everything in a commit is readable to anyone who can read
the commit). Enforce it for real by keeping `restricted` content in a separate TigerFS
workspace with its own mount credential, or by PostgreSQL RLS on the page table. Do not
pretend frontmatter alone is access control.

## The two hard boundaries

**Only `release` advances `main`.** Enforce with a distinct PostgreSQL role and mount
credential for the release worker, and a `pre-receive`-equivalent gate on `refs/heads/main`.
Compare-and-swap the ref against the expected old SHA so two releases cannot interleave.

**Raw bytes are create-only.** Enforce with `REVOKE UPDATE, DELETE` on the raw table plus a
trigger (`db/schema.sql`). Content-addressing makes the intent checkable: the stored bytes
must hash to the path they live at, and `checks/validate` verifies it whenever the bytes are
reachable.

## Identity

Three identities exist, and only one of them is authenticated:

| Identity | Set by | Trustworthy? |
|---|---|---|
| PostgreSQL `current_user` | database authentication | **yes** |
| git committer + `KB_ACTOR` | the agent, checked by the hook | asserted, but leaves a trail |
| a `kb.actor` session variable | anyone | **no — do not use** |

Layer 4 therefore compares `current_user`. Each agent logs in as a role named *exactly* its
actor id from `roles.yaml`, so the role name is the identity, columns default to
`current_user`, and RLS compares it. An earlier version trusted `current_setting('kb.actor')`,
which any session can overwrite with `SET kb.actor = 'someone.else'` — decorative against
precisely the case it was written for. It is gone; do not reintroduce a settable identity.

`KB_ACTOR` at layer 2 remains self-asserted, and that is a real limit: the hook verifies
*intent*, not identity. The publish path is where it matters, so protect it at the server:

```bash
gh api -X PUT repos/:owner/:repo/branches/main/protection \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F enforce_admins=true -F required_status_checks=null -F restrictions=null
```

With that in place, "only review advances `main`" is enforced by the forge rather than by a
hook the contributor controls, and the PR approval *is* the release role.

## Auditing

Every accepted change records actor id, role, task id, base commit, result commit, and
validation outcome. Git already holds most of this; the release step is responsible for the
actor and validation fields. Treat TigerFS `user_id` as audit metadata, not enforcement,
unless you have independently verified that it denies access.

## Installing layer 2

```bash
bin/kb install-hooks    # pre-commit: test + validate + validate-permissions
```

The hook runs the validator test suite first (about 3ms). Checks that gate every commit are
themselves worth testing — the glob matcher shipped with `agent/*` where it needed `agent/**`,
silently granting nothing, and a unit test would have caught it before anyone relied on it.

The hook reads `KB_ACTOR` from the environment and refuses any commit that does not have one:
an unattributed commit cannot be permission-checked or audited. The single exception is the
bootstrap commit of a fresh repository, where no `main` exists yet to protect — after that,
every commit carries an actor.
