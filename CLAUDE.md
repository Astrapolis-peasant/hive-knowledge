# CLAUDE.md

Read [AGENTS.md](AGENTS.md) before writing anything in this repository. It is the operating
contract: what your role may touch, the page format, and the task workflow.

Short version:

- `bin/kb whoami` — confirm your role and writable scope. No `KB_ACTOR` means read-only.
- Never edit `main` or `wiki/index.md` (generated). Work in a task worktree from
  `bin/kb task start <slug>`.
- `bin/kb reindex && bin/kb validate` must pass before you commit.
- Reads pin one commit: `COMMIT=$(bin/kb pin)`, then `bin/kb show`/`bin/kb grep`.
- Cite sources by id. Label inference as inference. Say when the wiki does not know.
