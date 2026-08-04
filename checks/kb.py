"""Deterministic checks for the knowledge base.

    python3 checks/kb.py validate [--only frontmatter,links,sources,index,log] [--strict]
    python3 checks/kb.py reindex [--check]
    python3 checks/kb.py permissions --actor <id> [--paths ...] [--base <sha>] [--branch <n>]

Semantic review (contradictions, unsupported conclusions, stale claims) is a job for the
lint agent, not for this file. Everything here is mechanical and cheap.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

from kbcore import (
    BODY_SECTIONS, CONFIDENCE, DIR_FOR_TYPE, GENERATED_MARKER, KbError,
    OPTIONAL_MANIFEST_KEYS, OPTIONAL_PAGE_KEYS, PAGE_STATUS, PAGE_TYPES,
    REQUIRED_MANIFEST_KEYS, REQUIRED_PAGE_KEYS, ROOT, SOURCE_STATUS, TYPE_FOR_DIR,
    VISIBILITY, as_list, is_iso_date, is_iso_timestamp, load_governance, load_manifests,
    load_pages, path_matches, raw_path_for, render_sources_index, render_wiki_index,
    sha256_file,
)

WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
MDLINK = re.compile(r"\]\(([^)]+)\)")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
LOGLINE = re.compile(r"^- (\S+) \| ([^|]+) \| ([^|]+) \| (.+)$")


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.groups: dict[str, list[str]] = {}
        self.notes: dict[str, str] = {}

    def error(self, group: str, msg: str):
        self.errors.append(f"{group}: {msg}")
        self.groups.setdefault(group, []).append(msg)

    def warn(self, group: str, msg: str):
        self.warnings.append(f"{group}: {msg}")

    def note(self, group: str, msg: str):
        self.notes[group] = msg


# --------------------------------------------------------------------------- checks


def check_frontmatter(rep: Report, pages, teams, team_paths):
    seen_ids: dict[str, str] = {}
    for p in pages:
        m, rel = p.meta, p.rel
        missing = [k for k in REQUIRED_PAGE_KEYS if k not in m]
        if missing:
            rep.error("frontmatter", f"{rel}: missing {', '.join(missing)}")
        unknown = [k for k in m if k not in REQUIRED_PAGE_KEYS + OPTIONAL_PAGE_KEYS]
        if unknown:
            rep.error("frontmatter", f"{rel}: unknown key(s) {', '.join(sorted(unknown))}")

        ptype = m.get("page_type")
        if ptype not in PAGE_TYPES:
            rep.error("frontmatter", f"{rel}: page_type {ptype!r} not in {PAGE_TYPES}")
            continue

        parent = p.path.parent.name
        if TYPE_FOR_DIR.get(parent) != ptype:
            rep.error("frontmatter",
                      f"{rel}: page_type {ptype!r} belongs in wiki/{DIR_FOR_TYPE[ptype]}/")

        pid, slug = m.get("id"), p.path.stem
        if pid != f"{ptype}.{slug}":
            rep.error("frontmatter",
                      f"{rel}: id must be '{ptype}.{slug}' to match page_type and filename, "
                      f"got {pid!r}")
        if pid in seen_ids:
            rep.error("frontmatter", f"{rel}: id {pid!r} already used by {seen_ids[pid]}")
        else:
            seen_ids[pid] = rel

        for key, allowed in (("status", PAGE_STATUS), ("visibility", VISIBILITY),
                             ("confidence", CONFIDENCE)):
            if m.get(key) not in allowed:
                rep.error("frontmatter",
                          f"{rel}: {key} {m.get(key)!r} not in {tuple(allowed)}")

        if not is_iso_date(m.get("updated_at")):
            rep.error("frontmatter",
                      f"{rel}: updated_at must be YYYY-MM-DD, got {m.get('updated_at')!r}")

        summary = m.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            rep.error("frontmatter", f"{rel}: summary is required and must be one line")
        elif len(summary) > 160:
            rep.error("frontmatter", f"{rel}: summary is {len(summary)} chars (max 160)")

        owner = m.get("owner")
        if owner not in teams:
            rep.error("frontmatter", f"{rel}: owner {owner!r} is not a team in owners.yaml")
        elif not path_matches(rel, team_paths.get(owner, [])):
            rep.error("frontmatter",
                      f"{rel}: owner {owner} does not claim this path in owners.yaml")

        srcs = as_list(m.get("sources"))
        if not srcs and ptype != "question" and m.get("status") != "draft":
            rep.error("frontmatter",
                      f"{rel}: sources is empty (only question pages and drafts may cite none)")

        body = p.body
        if not re.search(r"^#\s+\S", body, re.MULTILINE):
            rep.error("frontmatter", f"{rel}: body has no H1 title")
        found = HEADING.findall(body)
        order = [s for s in found if s in BODY_SECTIONS]
        for want in BODY_SECTIONS:
            if want not in found:
                rep.error("frontmatter", f"{rel}: missing required section '## {want}'")
        if order != [s for s in BODY_SECTIONS if s in order]:
            rep.error("frontmatter",
                      f"{rel}: required sections out of order: {order}")
    rep.note("frontmatter", f"{len(pages)} pages")
    return seen_ids


def check_links(rep: Report, pages, page_ids):
    inbound: dict[str, int] = {pid: 0 for pid in page_ids}
    for p in pages:
        # HTML comments are template scaffolding and author notes, not content — the example
        # links inside them are illustrative and must not be resolved.
        body = HTML_COMMENT.sub("", p.body)
        for target in WIKILINK.findall(body):
            t = target.strip()
            if t not in page_ids:
                rep.error("links", f"{p.rel}: wikilink [[{t}]] resolves to no page id")
            else:
                inbound[t] += 1
        for key in ("related", "supersedes"):
            for ref in as_list(p.meta.get(key)):
                if ref == p.id:
                    rep.error("links", f"{p.rel}: {key} references itself")
                elif ref not in page_ids:
                    rep.error("links", f"{p.rel}: {key} references unknown page {ref!r}")
                else:
                    inbound[ref] += 1
        for href in MDLINK.findall(body):
            if href.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = (p.path.parent / href.split("#", 1)[0]).resolve()
            if not target.exists():
                rep.error("links", f"{p.rel}: relative link {href!r} does not exist")
    for pid, count in inbound.items():
        if count == 0:
            rep.warn("links", f"{pid} has no inbound links — reachable only via the index")


def check_sources(rep: Report, pages, manifests):
    by_id: dict[str, object] = {}
    for m in manifests:
        rel = m.rel
        missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in m.meta]
        if missing:
            rep.error("sources", f"{rel}: missing {', '.join(missing)}")
        unknown = [k for k in m.meta
                   if k not in REQUIRED_MANIFEST_KEYS + OPTIONAL_MANIFEST_KEYS]
        if unknown:
            rep.error("sources", f"{rel}: unknown key(s) {', '.join(sorted(unknown))}")

        if not str(m.id).startswith("source."):
            rep.error("sources", f"{rel}: id must start with 'source.', got {m.id!r}")
        if m.path.name != f"{m.id}.yaml":
            rep.error("sources", f"{rel}: filename must be '{m.id}.yaml'")
        if m.id in by_id:
            rep.error("sources", f"{rel}: duplicate source id {m.id!r}")
        by_id[m.id] = m

        status = m.meta.get("status")
        if status not in SOURCE_STATUS:
            rep.error("sources", f"{rel}: status {status!r} not in {SOURCE_STATUS}")
        if not is_iso_timestamp(m.meta.get("captured_at")):
            rep.error("sources",
                      f"{rel}: captured_at must be an ISO timestamp, "
                      f"got {m.meta.get('captured_at')!r}")

        sha = m.meta.get("sha256")
        if status == "active":
            if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)):
                rep.error("sources",
                          f"{rel}: status active requires a 64-char lowercase hex sha256")
            if not m.meta.get("raw_uri"):
                rep.error("sources", f"{rel}: status active requires raw_uri")
        if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha):
            raw = raw_path_for(sha)
            if raw and raw.is_file():
                actual = sha256_file(raw)
                if actual != sha:
                    rep.error("sources",
                              f"{rel}: raw bytes hash to {actual[:12]}… but manifest says "
                              f"{sha[:12]}… — raw store was mutated")
            elif raw:
                rep.warn("sources", f"{rel}: raw object not present at {raw} (not verified)")

    cited: set[str] = set()
    for p in pages:
        for sid in as_list(p.meta.get("sources")):
            cited.add(sid)
            if sid not in by_id:
                rep.error("sources", f"{p.rel}: cites {sid!r} with no manifest")
        if p.meta.get("confidence") == "high":
            strong = [s for s in as_list(p.meta.get("sources"))
                      if s in by_id and by_id[s].meta.get("status") == "active"]
            if not strong:
                rep.error("sources",
                          f"{p.rel}: confidence high requires at least one source with "
                          f"status active (captured bytes)")
    for sid in by_id:
        if sid not in cited:
            rep.warn("sources", f"{sid} is registered but no page cites it")
    rep.note("sources", f"{len(manifests)} manifests")


def check_index(rep: Report, pages, manifests):
    for rel, want in (("wiki/index.md", render_wiki_index(pages)),
                      ("sources/index.md", render_sources_index(manifests))):
        path = ROOT / rel
        if not path.is_file():
            rep.error("index", f"{rel} is missing — run `bin/kb reindex`")
            continue
        have = path.read_text(encoding="utf-8")
        if GENERATED_MARKER not in have:
            rep.error("index", f"{rel} lost its GENERATED marker — run `bin/kb reindex`")
        elif have != want:
            rep.error("index", f"{rel} is stale — run `bin/kb reindex`")


def check_log(rep: Report, actors):
    path = ROOT / "wiki" / "log.md"
    if not path.is_file():
        rep.error("log", "wiki/log.md is missing")
        return
    count = 0
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.startswith("- "):
            continue
        count += 1
        m = LOGLINE.match(line)
        if not m:
            rep.error("log", f"wiki/log.md:{lineno}: expected "
                             f"'- <date> | <task> | <actor> | <summary>'")
            continue
        when, task, actor, _ = m.groups()
        if not is_iso_date(when):
            rep.error("log", f"wiki/log.md:{lineno}: {when!r} is not a YYYY-MM-DD date")
        if not task.strip().startswith("task:"):
            rep.error("log", f"wiki/log.md:{lineno}: task field must be 'task:<id>'")
        if actor.strip() not in actors:
            rep.error("log", f"wiki/log.md:{lineno}: actor {actor.strip()!r} is not "
                             f"registered in governance/roles.yaml")
    rep.note("log", f"{count} entries")


# --------------------------------------------------------------------------- commands


def load_all(rep: Report):
    pages, page_errors = load_pages()
    manifests, manifest_errors = load_manifests()
    for e in page_errors:
        rep.error("frontmatter", e)
    for e in manifest_errors:
        rep.error("sources", e)
    return pages, manifests


def cmd_validate(args) -> int:
    rep = Report()
    only = set(args.only.split(",")) if args.only else None

    try:
        owners = load_governance("owners.yaml")
        roles = load_governance("roles.yaml")
    except KbError as e:
        print(f"FAIL  {e}")
        return 2

    teams = as_list(owners.get("teams"))
    team_paths = {t: as_list(owners.get(f"{t}.paths")) for t in teams}
    actors = set(as_list(roles.get("actors")))

    pages, manifests = load_all(rep)
    page_ids = {p.id for p in pages if p.id}

    def want(group):
        return only is None or group in only

    if want("frontmatter"):
        check_frontmatter(rep, pages, teams, team_paths)
    if want("links"):
        check_links(rep, pages, page_ids)
    if want("sources"):
        check_sources(rep, pages, manifests)
    if want("index"):
        check_index(rep, pages, manifests)
    if want("log"):
        check_log(rep, actors)

    groups = [g for g in ("frontmatter", "links", "sources", "index", "log") if want(g)]
    print("knowledge-base validation")
    for g in groups:
        failed = len(rep.groups.get(g, []))
        state = f"FAIL ({failed})" if failed else "PASS"
        print(f"  {g:<12} {state:<10} {rep.notes.get(g, '')}")
    print()

    for e in rep.errors:
        print(f"  error   {e}")
    if args.verbose or args.strict:
        for w in rep.warnings:
            print(f"  warn    {w}")

    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    print(f"\n{'FAIL' if failed else 'PASS'}  "
          f"{len(rep.errors)} errors, {len(rep.warnings)} warnings")
    return 1 if failed else 0


def cmd_reindex(args) -> int:
    rep = Report()
    pages, manifests = load_all(rep)
    if rep.errors:
        print("refusing to reindex: fix these parse errors first")
        for e in rep.errors:
            print(f"  error   {e}")
        return 1
    changed = []
    for rel, want in (("wiki/index.md", render_wiki_index(pages)),
                      ("sources/index.md", render_sources_index(manifests))):
        path = ROOT / rel
        have = path.read_text(encoding="utf-8") if path.is_file() else None
        if have == want:
            continue
        changed.append(rel)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(want, encoding="utf-8")
    if args.check:
        print("stale: " + ", ".join(changed) if changed else "indexes are current")
        return 1 if changed else 0
    print("rewrote: " + ", ".join(changed) if changed else "indexes already current")
    return 0


def git(*argv) -> str:
    return subprocess.run(["git", *argv], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()


def cmd_permissions(args) -> int:
    try:
        roles = load_governance("roles.yaml")
        owners = load_governance("owners.yaml")
    except KbError as e:
        print(f"FAIL  {e}")
        return 2

    actor = args.actor or os.environ.get("KB_ACTOR")
    if not actor:
        print("FAIL  no actor: pass --actor or set KB_ACTOR")
        return 2
    if actor not in set(as_list(roles.get("actors"))):
        print(f"FAIL  unknown actor {actor!r} — register it in governance/roles.yaml")
        return 2

    role = roles.get(f"actor.{actor}.role")
    teams = as_list(roles.get(f"actor.{actor}.teams"))
    if role not in as_list(roles.get("roles")):
        print(f"FAIL  actor {actor} has unknown role {role!r}")
        return 2

    writable = as_list(roles.get(f"role.{role}.write"))
    branches = as_list(roles.get(f"role.{role}.branches"))
    owned = [g for t in teams for g in as_list(owners.get(f"{t}.paths"))]

    paths = list(args.paths or [])
    if not paths:
        base = args.base or "HEAD"
        out = git("diff", "--name-only", base)
        staged = git("diff", "--cached", "--name-only")
        untracked = git("ls-files", "--others", "--exclude-standard")
        paths = sorted({p for p in (out + "\n" + staged + "\n" + untracked).splitlines() if p})

    violations = []
    branch = args.branch or git("rev-parse", "--abbrev-ref", "HEAD")
    # The bootstrap commit is the one exception: before any commit exists there is no
    # published main to protect and no release role to protect it. Applies once, ever.
    bootstrap = not git("rev-parse", "-q", "--verify", "HEAD")
    if bootstrap:
        print("  bootstrap: repository has no commits yet, branch checks skipped")
    else:
        if branch and branches and not path_matches(branch, branches):
            violations.append(f"branch {branch!r} is not allowed for role {role} "
                              f"(allowed: {', '.join(branches)})")
        if branch == "main" and role != "release":
            violations.append(f"role {role} must not commit on main — use `bin/kb task start`")

    for p in paths:
        if not path_matches(p, writable):
            violations.append(f"{p}: role {role} has no write grant for this path")
            continue
        if p.startswith("wiki/") and not path_matches(p, owned):
            violations.append(f"{p}: no team of {actor} ({', '.join(teams) or 'none'}) "
                              f"owns this path — mark the task review_required")

    print(f"permission check  actor={actor} role={role} teams={','.join(teams) or '-'} "
          f"branch={branch or '-'}")
    print(f"  {len(paths)} changed path(s)")
    for v in violations:
        print(f"  denied  {v}")
    print(f"\n{'FAIL' if violations else 'PASS'}  {len(violations)} violations")
    return 1 if violations else 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="checks/kb.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="deterministic checks over the whole KB")
    v.add_argument("--only", help="comma list: frontmatter,links,sources,index,log")
    v.add_argument("--strict", action="store_true", help="treat warnings as failures")
    v.add_argument("--verbose", "-v", action="store_true", help="show warnings")
    v.set_defaults(fn=cmd_validate)

    r = sub.add_parser("reindex", help="regenerate wiki/index.md and sources/index.md")
    r.add_argument("--check", action="store_true", help="report staleness, write nothing")
    r.set_defaults(fn=cmd_reindex)

    p = sub.add_parser("permissions", help="check changed paths against role and team")
    p.add_argument("--actor")
    p.add_argument("--paths", nargs="*")
    p.add_argument("--base", help="compare against this ref instead of HEAD")
    p.add_argument("--branch")
    p.set_defaults(fn=cmd_permissions)

    args = ap.parse_args()
    try:
        return args.fn(args)
    except KbError as e:
        print(f"FAIL  {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
