---
description: Record knowledge in the base through a task worktree, validated and submitted
argument-hint: <what to record>
---

Record this in the hive-knowledge base: $ARGUMENTS

Use the `kb` skill. Write path.

1. Confirm the actor first: `bin/kb whoami`. If `KB_ACTOR` is unset, stop and ask which actor
   from `governance/roles.yaml` to use — unattributed commits are refused.
2. `bin/kb task start <slug>`, then work only inside the worktree it prints.
3. Read `wiki/index.md` before writing: prefer updating existing pages over adding near
   duplicates, and reconcile rather than contradict.
4. Create or edit pages with `bin/kb new-page` / normal edits. Cite source ids. Mark your own
   inferences as inferences, and put genuine conflicts under `## Disputed or Uncertain`.
   Do not set `confidence: high` without a source whose bytes are captured.
5. `bin/kb reindex && bin/kb validate` until clean, then commit and `bin/kb task submit`.
6. Report the branch and what a reviewer should look at. Do not attempt to publish — releasing
   to `main` is the `release` role's job.
