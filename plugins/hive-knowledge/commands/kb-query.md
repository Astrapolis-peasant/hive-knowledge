---
description: Answer a question from the knowledge base, pinned to one commit, with citations
argument-hint: <question>
---

Answer this from the hive-knowledge base: $ARGUMENTS

Use the `kb` skill. Read path only — do not write anything.

1. Locate the knowledge base (`$KB_HOME`, or the current directory if it has `AGENTS.md` and
   `bin/kb`). If none is reachable, say so instead of answering from memory.
2. `COMMIT=$(bin/kb pin)` — use that one commit for every read in this request.
3. Start from `wiki/index.md`, then `bin/kb grep` for the terms, then read whole candidate
   pages.
4. Answer with page ids and source ids cited, and carry each page's own `confidence` and any
   `## Disputed or Uncertain` content into your answer rather than smoothing it away.
5. If the knowledge base does not cover it, say that plainly and offer to open a `question.*`
   page or ingest a source.
