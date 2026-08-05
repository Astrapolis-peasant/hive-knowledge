"""Retrieval, navigation, and knowledge-health capability.

    python3 checks/kbquery.py ask <query> [--commit SHA] [--type t] [--owner team.x]
                                         [--status s] [--min-confidence low|medium|high]
                                         [--limit N] [--no-log]
    python3 checks/kbquery.py links <page-id> [--commit SHA]
    python3 checks/kbquery.py lint [--commit SHA]
    python3 checks/kbquery.py miss <query> [--note "..."]
    python3 checks/kbquery.py stats

Three principles this file follows, taken from the architecture:

1. **Retrieval finds pages; pages provide evidence.** `ask` returns candidate page identities
   and never prints body prose. The agent then reads whole pages.
2. **No new infrastructure until measured.** There is no persistent index: scoring is done in
   memory from a pinned commit on every call. At a few thousand pages that is milliseconds, and
   it cannot go stale or disagree with the wiki. `stats` is the measurement that would justify
   building something heavier.
3. **Disposable and commit-keyed.** Everything here is derived from one commit and thrown away.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from math import log

from kbcore import (
    CONFIDENCE, KbError, PAGE_TYPES, ROOT, as_list, is_iso_date, load_manifests,
    load_pages, main_root, split_frontmatter,
)

WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
WORD = re.compile(r"[a-z0-9]+")

# Deliberately short. A long stopword list starts discarding real query terms — "index",
# "state", and "history" all matter here.
STOPWORDS = frozenset("""
a an the and or but if then than that this these those is are was were be been being
of in on at to from by for with as it its into about over under not no
how what when where why which who whom whose do does did done doing
can could should would will shall may might must have has had having
i we you they he she it them us me my our your their there here
all any some more most such so too very just also only other same each both few own
up out off again further once get gets got make makes made use used using need needs
""".split())

# Ranking multipliers. A page's trustworthiness is part of its relevance: a superseded page
# can still be the best lexical match while being the wrong answer to give.
STATUS_WEIGHT = {"active": 1.0, "draft": 0.75, "deprecated": 0.35, "superseded": 0.3}
CONFIDENCE_WEIGHT = {"high": 1.1, "medium": 1.0, "low": 0.9}

FIELD_WEIGHTS = {"id": 3.0, "title": 2.5, "summary": 3.0, "tags": 2.0, "headings": 1.5, "body": 1.0}
K1, B = 1.4, 0.72          # standard BM25 knobs
CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def git(*argv, binary=False, stdin=None):
    r = subprocess.run(["git", *argv], cwd=ROOT, input=stdin,
                       capture_output=True, text=not binary)
    return r.stdout


def stem(word: str) -> str:
    """Crude suffix stripping. Enough to bridge cache/caches and commit/commits/committing.

    English doubles the final consonant before -ing/-ed ("commit" -> "committing"), so undo
    that too; without it a query for "commit" misses a page that says "committing".
    """
    for suffix in ("ing", "edly", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            base = word[: -len(suffix)]
            if (len(base) > 3 and base[-1] == base[-2]
                    and base[-1] not in "aeiou" and base[-1] not in "ls"):
                base = base[:-1]          # committ -> commit, stopp -> stop
            return base
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in WORD.findall(text.lower()) if w not in STOPWORDS and len(w) > 1]


class Doc:
    """One page, reduced to weighted term counts plus the metadata a filter needs."""

    def __init__(self, path: str, meta: dict, body: str):
        self.path = path
        self.meta = meta
        self.id = meta.get("id") or path
        clean = HTML_COMMENT.sub("", body)
        title = re.search(r"^#\s+(.+)$", clean, re.MULTILINE)
        headings = " ".join(re.findall(r"^#{2,}\s+(.+)$", clean, re.MULTILINE))
        fields = {
            "id": self.id.replace(".", " ").replace("-", " "),
            "title": title.group(1) if title else "",
            "summary": str(meta.get("summary") or ""),
            "tags": " ".join(str(t) for t in as_list(meta.get("tags"))),
            "headings": headings,
            "body": clean,
        }
        self.tf: Counter = Counter()
        for field, text in fields.items():
            weight = FIELD_WEIGHTS[field]
            for term in tokens(text):
                self.tf[term] += weight
        self.length = sum(self.tf.values()) or 1
        self.outbound = {t.strip() for t in WIKILINK.findall(clean)} | {
            r for r in as_list(meta.get("related"))} | {
            r for r in as_list(meta.get("supersedes"))}


def load_docs(commit: str | None) -> list[Doc]:
    """Read pages from a pinned commit, or the working tree when commit is None.

    One `git cat-file --batch` call for the whole wiki, so this stays fast enough that a
    persistent index would be premature.
    """
    if commit is None:
        pages, errors = load_pages()
        if errors:
            raise KbError(errors[0])
        return [Doc(p.rel, p.meta, p.body) for p in pages]

    listing = git("ls-tree", "-r", "--name-only", commit, "--", "wiki/")
    paths = [p for p in listing.splitlines()
             if p.endswith(".md") and p not in ("wiki/index.md", "wiki/log.md")]
    if not paths:
        return []
    stdin = "".join(f"{commit}:{p}\n" for p in paths).encode()
    raw = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, input=stdin,
                         capture_output=True).stdout
    docs, pos = [], 0
    for path in paths:
        nl = raw.index(b"\n", pos)
        header = raw[pos:nl].decode()
        pos = nl + 1
        parts = header.split()
        if len(parts) != 3 or parts[1] != "blob":
            raise KbError(f"unexpected cat-file header for {path}: {header}")
        size = int(parts[2])
        blob = raw[pos:pos + size].decode("utf-8")
        pos += size + 1
        try:
            meta, body = split_frontmatter(blob, path)
        except KbError:
            continue
        docs.append(Doc(path, meta, body))
    return docs


# --------------------------------------------------------------------------- ask


def score(docs: list[Doc], query: str) -> list[tuple[float, Doc, list[str]]]:
    qterms = tokens(query)
    if not qterms:
        return []
    n = len(docs)
    df = Counter()
    for d in docs:
        for t in set(qterms):
            if d.tf.get(t):
                df[t] += 1
    avg = sum(d.length for d in docs) / max(n, 1)
    out = []
    for d in docs:
        total, matched = 0.0, []
        for t in qterms:
            f = d.tf.get(t, 0)
            if not f:
                continue
            idf = log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            total += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * d.length / avg))
            matched.append(t)
        if total > 0:
            total *= STATUS_WEIGHT.get(str(d.meta.get("status")), 1.0)
            total *= CONFIDENCE_WEIGHT.get(str(d.meta.get("confidence")), 1.0)
            out.append((total, d, sorted(set(matched))))
    out.sort(key=lambda r: (-r[0], r[1].id))
    return out


def cmd_ask(args) -> int:
    commit = None if args.commit == "WORKTREE" else (args.commit or git("rev-parse", "refs/heads/main").strip() or None)
    docs = load_docs(commit)

    # Filters before ranking — the context-noise control from the architecture, section 11.3.
    def keep(d: Doc) -> bool:
        if args.type and d.meta.get("page_type") != args.type:
            return False
        if args.owner and d.meta.get("owner") != args.owner:
            return False
        if args.status and d.meta.get("status") != args.status:
            return False
        if args.min_confidence:
            have = CONF_RANK.get(str(d.meta.get("confidence")), -1)
            if have < CONF_RANK[args.min_confidence]:
                return False
        return True

    pool = [d for d in docs if keep(d)]
    ranked = score(pool, args.query)[: args.limit]

    print(f"query    {args.query!r}")
    print(f"commit   {commit or 'WORKTREE'}   searched {len(pool)} of {len(docs)} pages")
    if not ranked:
        print("\nno candidate pages matched.")
        print("This is a recall failure worth recording:")
        print(f'  bin/kb miss "{args.query}"')
    else:
        print()
        for rank, (s, d, matched) in enumerate(ranked, 1):
            m = d.meta
            flags = [str(m.get("confidence", "?")), str(m.get("owner", "?"))]
            if m.get("status") != "active":
                flags.append(f"status: {m.get('status')}")
            if m.get("visibility") == "restricted":
                flags.append("RESTRICTED — do not quote")
            print(f"{rank}. {d.id}   score {s:.2f}   [{' · '.join(flags)}]")
            print(f"   {m.get('summary', '')}")
            print(f"   {d.path}   matched: {', '.join(matched)}")
        print("\nRead the whole page before using it. Do not answer from these lines.")

    if not args.no_log:
        log_event("query", {"query": args.query, "commit": commit,
                            "hits": len(ranked), "top": ranked[0][1].id if ranked else None,
                            "top_score": round(ranked[0][0], 3) if ranked else 0.0})
    return 0


# --------------------------------------------------------------------------- links


def cmd_links(args) -> int:
    commit = None if args.commit == "WORKTREE" else (args.commit or git("rev-parse", "refs/heads/main").strip() or None)
    docs = load_docs(commit)
    by_id = {d.id: d for d in docs}
    if args.page_id not in by_id:
        print(f"no such page: {args.page_id}")
        return 1
    target = by_id[args.page_id]
    inbound = sorted(d.id for d in docs if args.page_id in d.outbound and d.id != args.page_id)
    outbound = sorted(t for t in target.outbound if t != args.page_id)

    print(f"page     {target.id}")
    print(f"         {target.meta.get('summary','')}")
    print(f"\ninbound  ({len(inbound)}) — pages that point here")
    for i in inbound or ["(none — reachable only via the index)"]:
        print(f"  {i}" + (f"   {by_id[i].meta.get('summary','')[:70]}" if i in by_id else ""))
    print(f"\noutbound ({len(outbound)})")
    for o in outbound or ["(none)"]:
        mark = "" if o in by_id else "   [UNRESOLVED]"
        print(f"  {o}{mark}" + (f"   {by_id[o].meta.get('summary','')[:70]}" if o in by_id else ""))
    print(f"\nevidence ({len(as_list(target.meta.get('sources')))})")
    for s in as_list(target.meta.get("sources")) or ["(none)"]:
        print(f"  {s}")
    return 0


# --------------------------------------------------------------------------- lint


def cmd_lint(args) -> int:
    """Knowledge-health findings. Report-only, by design: these are judgement calls that
    belong on a lint/* branch for review, not automatic edits to published pages."""
    commit = None if args.commit == "WORKTREE" else (args.commit or git("rev-parse", "refs/heads/main").strip() or None)
    docs = load_docs(commit)
    manifests, _ = load_manifests()
    src = {m.id: m for m in manifests}
    by_id = {d.id: d for d in docs}
    inbound = Counter()
    for d in docs:
        for t in d.outbound:
            inbound[t] += 1

    findings: list[tuple[str, str, str]] = []          # (severity, check, message)

    def add(sev, check, msg):
        findings.append((sev, check, msg))

    today = date.today()
    for d in docs:
        m = d.meta
        pid = d.id
        if m.get("status") == "superseded":
            continue

        if inbound[pid] == 0:
            add("warn", "orphan", f"{pid} has no inbound links — only the index reaches it")
        if not d.outbound:
            add("info", "isolated", f"{pid} links to nothing — is it really unrelated?")

        for s in as_list(m.get("sources")):
            if s in src and src[s].meta.get("status") == "deprecated":
                add("warn", "deprecated-source", f"{pid} cites deprecated source {s}")

        # A page is only as fresh as the evidence under it.
        if is_iso_date(m.get("updated_at")):
            age = (today - date.fromisoformat(m["updated_at"])).days
            if m.get("status") == "draft" and age > 14:
                add("warn", "stale-draft", f"{pid} has been a draft for {age} days")
            if m.get("page_type") == "question" and age > 90:
                add("warn", "stale-question", f"{pid} unanswered for {age} days")
            if m.get("confidence") == "high" and age > 365:
                add("info", "aging-certainty", f"{pid} claims high confidence, untouched {age} days")

        if m.get("page_type") == "claim" and m.get("confidence") == "low":
            add("info", "weak-claim",
                f"{pid} is a claim at low confidence — resolve it or reframe it as a question")

    # Near-duplicate detection on summaries: cheap proxy for two pages drifting apart.
    ids = sorted(by_id)
    for i, a in enumerate(ids):
        ta = set(tokens(str(by_id[a].meta.get("summary", ""))))
        if len(ta) < 4:
            continue
        for b in ids[i + 1:]:
            tb = set(tokens(str(by_id[b].meta.get("summary", ""))))
            if len(tb) < 4:
                continue
            j = len(ta & tb) / len(ta | tb)
            if j >= 0.5:
                add("warn", "near-duplicate",
                    f"{a} and {b} have {int(j*100)}% overlapping summaries — merge or differentiate")

    # A superseded page should not be cited as current by an active page.
    for d in docs:
        if d.meta.get("status") == "superseded":
            successors = [s.id for s in docs if d.id in as_list(s.meta.get("supersedes"))]
            for other in docs:
                if other.meta.get("status") == "superseded" or other.id in successors:
                    continue          # the successor itself need not point at itself
                if d.id in other.outbound:
                    if successors and not any(s in other.outbound for s in successors):
                        add("warn", "superseded-reference",
                            f"{other.id} points at superseded {d.id} without also pointing at "
                            f"{successors[0]}")

    for s in src:
        if not any(s in as_list(d.meta.get("sources")) for d in docs):
            add("info", "unused-source", f"{s} is registered but no page cites it")

    # Index legibility: the measurement question.retrieval-scale-threshold asks for.
    index_bytes = len((ROOT / "wiki" / "index.md").read_text(encoding="utf-8")) if (ROOT / "wiki" / "index.md").is_file() else 0
    per_page = index_bytes / max(len(docs), 1)
    if index_bytes > 32768:
        add("warn", "index-size",
            f"wiki/index.md is {index_bytes//1024}KB — an agent pays this on every query")

    order = {"warn": 0, "info": 1}
    findings.sort(key=lambda f: (order[f[0]], f[1], f[2]))
    print(f"knowledge-health lint   commit {commit or 'WORKTREE'}   {len(docs)} pages")
    print(f"index {index_bytes} bytes ({per_page:.0f} bytes/page)\n")
    if not findings:
        print("no findings.")
    for sev, check, msg in findings:
        print(f"  {sev:<5} {check:<22} {msg}")
    warns = sum(1 for f in findings if f[0] == "warn")
    print(f"\n{warns} warnings, {len(findings)-warns} informational")
    print("Findings are advisory. Fix them on a lint/* or repair/* branch, never on main.")
    return 0


# --------------------------------------------------------------------------- measurement


def control_dir():
    env = os.environ.get("KB_CONTROL")
    base = env if env else str(main_root() / ".kb")
    d = os.path.join(base, "retrieval")
    os.makedirs(d, exist_ok=True)
    return d


def log_event(kind: str, payload: dict):
    """Append one JSON line. This is the only thing the read path writes, and it writes to
    control state — never to the wiki."""
    payload = dict(payload)
    payload["kind"] = kind
    payload["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload["actor"] = os.environ.get("KB_ACTOR", "anonymous")
    try:
        with open(os.path.join(control_dir(), f"{kind}.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, sort_keys=True) + "\n")
    except OSError:
        pass          # measurement must never break a query


def read_events(kind: str) -> list[dict]:
    path = os.path.join(control_dir(), f"{kind}.jsonl")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def cmd_miss(args) -> int:
    log_event("miss", {"query": args.query, "note": args.note or ""})
    print(f"recorded recall failure: {args.query!r}")
    print("This is the evidence question.retrieval-scale-threshold asks for.")
    print("Consider opening a question.* page, or ingesting a source that answers it.")
    return 0


def cmd_stats(args) -> int:
    queries, misses = read_events("query"), read_events("miss")
    print("retrieval measurement")
    print(f"  queries recorded   {len(queries)}")
    print(f"  zero-hit queries   {sum(1 for q in queries if not q.get('hits'))}")
    print(f"  recorded misses    {len(misses)}")
    if queries:
        rate = 100 * sum(1 for q in queries if not q.get("hits")) / len(queries)
        print(f"  zero-hit rate      {rate:.1f}%")
        weak = [q for q in queries if q.get("hits") and float(q.get("top_score") or 0) < 1.0]
        print(f"  weak top score     {len(weak)} queries scored under 1.0")
    terms = Counter()
    for e in queries + misses:
        if not e.get("hits"):
            terms.update(tokens(str(e.get("query", ""))))
    if terms:
        print("\n  terms that found nothing:")
        for term, c in terms.most_common(10):
            print(f"    {c:>3}  {term}")
    print("""
How to read this. The architecture defers BM25/vector infrastructure until navigation
measurably fails. The signal to watch is the zero-hit rate and the recorded misses: those are
questions the wiki could plausibly answer but retrieval did not surface. Build Stage 2 when
that rate stops being noise, not before.""")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="checks/kbquery.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="rank candidate pages for a question")
    a.add_argument("query")
    a.add_argument("--commit", help="pinned commit, or WORKTREE for the checkout")
    a.add_argument("--type", choices=PAGE_TYPES)
    a.add_argument("--owner")
    a.add_argument("--status")
    a.add_argument("--min-confidence", choices=list(CONFIDENCE))
    a.add_argument("--limit", type=int, default=5)
    a.add_argument("--no-log", action="store_true")
    a.set_defaults(fn=cmd_ask)

    l = sub.add_parser("links", help="inbound and outbound links for one page")
    l.add_argument("page_id")
    l.add_argument("--commit")
    l.set_defaults(fn=cmd_links)

    li = sub.add_parser("lint", help="knowledge-health findings, report-only")
    li.add_argument("--commit")
    li.set_defaults(fn=cmd_lint)

    m = sub.add_parser("miss", help="record that retrieval failed to find a known answer")
    m.add_argument("query")
    m.add_argument("--note")
    m.set_defaults(fn=cmd_miss)

    s = sub.add_parser("stats", help="retrieval measurement summary")
    s.set_defaults(fn=cmd_stats)

    args = ap.parse_args()
    try:
        return args.fn(args)
    except KbError as e:
        print(f"FAIL  {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
