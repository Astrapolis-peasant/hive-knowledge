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
- 2026-08-04 | task:t20260804-090957 | agent.ingest-01 | Registered the Git-on-TigerFS gate output as evidence, captured into the TigerFS raw store.
- 2026-08-04 | task:t20260804-091040 | agent.compile-01 | Recorded the measured gate result: new claim.git-on-tigerfs-fails-the-gate supersedes claim.git-on-tigerfs-unverified; reconciled the TigerFS, Git, and foundations pages.
- 2026-08-04 | task:t20260804-091259 | human.admin | Exempted the generated indexes from the team-ownership check, which had made reindexing impossible for any team but one.
- 2026-08-04 | task:t20260804-091418 | agent.compile-02 | Reconciled synthesis.four-layer-separation with the gate result; the layers held, the single-store property did not.
- 2026-08-04 | task:t20260804-091454 | human.admin | Deployed on PostgreSQL 17.9 + TigerFS 0.7.0 and recorded the operational findings in ops/tigerfs.md and README.
- 2026-08-04 | task:t20260804-094203 | agent.ingest-01 | Registered the tuned Git-on-TigerFS gate run as evidence.
- 2026-08-04 | task:t20260804-094218 | agent.compile-01 | Separated the four causes behind the gate failure: caching (fixed), macOS AppleDouble (not TigerFS), lockfile-name reuse (the blocker, not tunable), and one-byte text padding.
- 2026-08-04 | task:t20260804-094329 | human.admin | Documented the flat-key config trap, the tuning table, and the working config as ops/tigerfs-config.yaml.
- 2026-08-04 | task:t20260804-095239 | human.admin | Added retrieval and health capability: kb ask (BM25 with trust weighting), kb links, kb lint, kb miss/stats measurement; taught the read path in AGENTS.md and the plugin skill.
- 2026-08-05 | task:t20260805-013257 | human.admin | Authenticated layer-4 identity on current_user and removed the forgeable kb.actor session variable; added a 43-test suite for the validators, wired into the pre-commit hook.
- 2026-08-07 | task:t20260807-053259 | human.admin | Stated the company-knowledge-base scope: twelve boundaries a company KB must guarantee, what this repository currently meets, the gaps, and what is open. Added COMPANY_KB.md.
