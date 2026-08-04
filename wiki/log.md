# Change Log

Chronological record of accepted changes. The catalog of *what the wiki knows* is
[index.md](index.md); this file records *what happened and when*. Append one line per
accepted change, newest last.

Format — four pipe-separated fields, checked by `checks/validate --only log`:

```text
- <YYYY-MM-DD> | task:<task-id> | <actor-id> | <what changed and why>
```

- 2026-08-04 | task:t20260804-000001 | human.admin | Seeded the knowledge base: scaffold, role and team permission model, deterministic checks, and ten pages covering the four foundations.
- 2026-08-04 | task:t20260804-000002 | human.admin | Packaged the Claude Code plugin (kb skill, /kb-query, /kb-task) and added the TigerFS deployment path: ops/tigerfs.md, the Phase 0 compatibility gate at 34/34 on local disk, and .env.example.
