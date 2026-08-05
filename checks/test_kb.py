"""Tests for the code that gates every commit.

    checks/test          # or: python3 -m unittest discover -s checks -p 'test_*.py'

Stdlib `unittest`, no pytest, no fixtures directory — the same portability constraint as the
validators themselves. Nothing here touches git, PostgreSQL, or repository state, so it runs
anywhere `python3` does.

Every test named `test_regression_*` encodes a bug that actually shipped. Read those first if
you are changing the matching, parsing, or ranking code.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kb
import kbcore
import kbquery
from kb import LOGLINE
from kbcore import KbError


class TestGlobMatching(unittest.TestCase):
    """`*` stays inside one path segment, `**` crosses them. Everything in the permission
    model depends on that distinction being right."""

    def test_regression_single_star_does_not_cross_slash(self):
        # Shipped bug: roles.yaml granted `agent/*`, but real branches are
        # `agent/<actor>/<task>-<slug>`, so no branch ever matched and the grant was dead.
        self.assertFalse(kbcore.path_matches("agent/agent.compile-01/t1-add-page", ["agent/*"]))
        self.assertTrue(kbcore.path_matches("agent/agent.compile-01/t1-add-page", ["agent/**"]))

    def test_single_star_matches_within_one_segment(self):
        self.assertTrue(kbcore.path_matches("sources/manifests/source.x.yaml",
                                            ["sources/manifests/*.yaml"]))
        self.assertFalse(kbcore.path_matches("sources/manifests/sub/source.x.yaml",
                                             ["sources/manifests/*.yaml"]))

    def test_double_star_matches_nested_and_flat(self):
        self.assertTrue(kbcore.path_matches("wiki/page.md", ["wiki/**"]))
        self.assertTrue(kbcore.path_matches("wiki/a/b/c.md", ["wiki/**"]))

    def test_top_level_pattern_does_not_match_nested(self):
        self.assertTrue(kbcore.path_matches("README.md", ["*.md"]))
        self.assertFalse(kbcore.path_matches("docs/README.md", ["*.md"]))

    def test_exact_path_pattern(self):
        self.assertTrue(kbcore.path_matches("wiki/entities/tigerfs.md",
                                            ["wiki/entities/tigerfs.md"]))
        self.assertFalse(kbcore.path_matches("wiki/entities/git.md",
                                             ["wiki/entities/tigerfs.md"]))

    def test_admin_wildcard_matches_everything(self):
        for p in ("bin/kb", "wiki/a/b.md", "db/schema.sql", "x"):
            self.assertTrue(kbcore.path_matches(p, ["**"]), p)

    def test_no_patterns_denies(self):
        self.assertFalse(kbcore.path_matches("anything", []))
        self.assertFalse(kbcore.path_matches("anything", None))

    def test_metacharacters_are_literal(self):
        # A '.' in a pattern must not behave as regex 'any character'.
        self.assertFalse(kbcore.path_matches("wiki/entities/tigerfsXmd",
                                             ["wiki/entities/tigerfs.md"]))


class TestPermissionDecision(unittest.TestCase):
    """role glob AND (outside wiki/ OR an owning team). Pure decision, no git."""

    ROLE_COMPILE = ["wiki/**"]
    OWNED_KNOWLEDGE = ["wiki/concepts/**", "wiki/index.md"]

    def test_allowed_when_role_and_team_both_match(self):
        v = kb.path_violations(["wiki/concepts/x.md"], self.ROLE_COMPILE,
                               self.OWNED_KNOWLEDGE, "agent.compile-02", "compile",
                               ["team.knowledge"])
        self.assertEqual(v, [])

    def test_denied_when_team_does_not_own_the_path(self):
        v = kb.path_violations(["wiki/syntheses/x.md"], self.ROLE_COMPILE,
                               self.OWNED_KNOWLEDGE, "agent.compile-01", "compile",
                               ["team.platform"])
        self.assertEqual(len(v), 1)
        self.assertIn("no team of agent.compile-01", v[0])
        self.assertIn("review_required", v[0])       # the message must name the remedy

    def test_denied_when_role_has_no_write_grant(self):
        v = kb.path_violations(["wiki/concepts/x.md"], ["sources/manifests/*.yaml"],
                               self.OWNED_KNOWLEDGE, "agent.ingest-01", "ingest",
                               ["team.knowledge"])
        self.assertEqual(len(v), 1)
        self.assertIn("no write grant", v[0])

    def test_non_wiki_path_skips_the_team_check(self):
        v = kb.path_violations(["db/schema.sql"], ["**"], [], "human.admin", "admin", [])
        self.assertEqual(v, [])

    def test_regression_generated_index_exempt_from_team_check(self):
        # Shipped bug: `kb reindex` rewrites wiki/index.md on any page change, but owners.yaml
        # gave that file to one team, so every other team was blocked from reindexing.
        v = kb.path_violations(["wiki/index.md"], ["wiki/**"], ["wiki/claims/**"],
                               "agent.compile-01", "compile", ["team.platform"])
        self.assertEqual(v, [])

    def test_generated_index_still_needs_a_role_grant(self):
        # Exempt from the team check is not exempt from the role check.
        v = kb.path_violations(["wiki/index.md"], ["sources/**"], ["wiki/**"],
                               "agent.ingest-01", "ingest", ["team.knowledge"])
        self.assertEqual(len(v), 1)
        self.assertIn("no write grant", v[0])

    def test_generated_paths_are_the_expected_two(self):
        self.assertEqual(set(kbcore.GENERATED_PATHS), {"wiki/index.md", "sources/index.md"})

    def test_reports_every_offending_path(self):
        v = kb.path_violations(["wiki/a.md", "wiki/b.md"], ["wiki/**"], [], "x", "compile", [])
        self.assertEqual(len(v), 2)


class TestYamlSubset(unittest.TestCase):
    """The parser must accept the documented subset and refuse everything else loudly —
    a silent misparse of frontmatter is worse than a failed commit."""

    def test_scalars_lists_and_comments(self):
        data = kbcore.parse_yaml_subset(
            "# a comment\n"
            "id: concept.kv-cache\n"
            "count: 3\n"
            "sources:\n"
            "  - source.a\n"
            "  - source.b\n"
            "empty:\n"
        )
        self.assertEqual(data["id"], "concept.kv-cache")
        self.assertEqual(data["count"], "3")            # values stay strings; callers coerce
        self.assertEqual(data["sources"], ["source.a", "source.b"])
        self.assertEqual(data["empty"], [])

    def test_inline_comment_stripped_from_unquoted_value(self):
        self.assertEqual(kbcore.parse_yaml_subset("k: value # trailing")["k"], "value")

    def test_quotes_preserve_hash_and_colon(self):
        self.assertEqual(kbcore.parse_yaml_subset('k: "a # b: c"')["k"], "a # b: c")

    def test_unquoted_value_keeps_internal_colon(self):
        self.assertEqual(kbcore.parse_yaml_subset("url: https://example.com/x")["url"],
                         "https://example.com/x")

    def test_literals(self):
        d = kbcore.parse_yaml_subset("a: null\nb: ~\nc: true\nd: false\ne: []\nf: [x, y]\n")
        self.assertIsNone(d["a"])
        self.assertIsNone(d["b"])
        self.assertIs(d["c"], True)
        self.assertIs(d["d"], False)
        self.assertEqual(d["e"], [])
        self.assertEqual(d["f"], ["x", "y"])

    def test_rejects_nested_mapping(self):
        with self.assertRaises(KbError):
            kbcore.parse_yaml_subset("outer:\n  inner: 1\n")

    def test_rejects_duplicate_key(self):
        with self.assertRaises(KbError):
            kbcore.parse_yaml_subset("k: 1\nk: 2\n")

    def test_rejects_list_item_without_key(self):
        with self.assertRaises(KbError):
            kbcore.parse_yaml_subset("  - orphan\n")

    def test_rejects_unterminated_quote(self):
        with self.assertRaises(KbError):
            kbcore.parse_yaml_subset("k: 'unterminated\n")

    def test_rejects_line_without_colon(self):
        with self.assertRaises(KbError):
            kbcore.parse_yaml_subset("this is not yaml\n")

    def test_rejects_list_under_a_scalar_key(self):
        with self.assertRaises(KbError):
            kbcore.parse_yaml_subset("k: scalar\n  - item\n")

    def test_error_names_the_line(self):
        try:
            kbcore.parse_yaml_subset("ok: 1\nbroken\n", where="page.md")
        except KbError as e:
            self.assertIn("page.md:2", str(e))
        else:
            self.fail("expected KbError")


class TestFrontmatter(unittest.TestCase):
    def test_splits_frontmatter_from_body(self):
        meta, body = kbcore.split_frontmatter("---\nid: concept.x\n---\n# Title\n\ntext\n", "p")
        self.assertEqual(meta["id"], "concept.x")
        self.assertIn("# Title", body)

    def test_requires_opening_fence(self):
        with self.assertRaises(KbError):
            kbcore.split_frontmatter("# Title\n", "p")

    def test_requires_closing_fence(self):
        with self.assertRaises(KbError):
            kbcore.split_frontmatter("---\nid: x\n# Title\n", "p")


class TestLogFormat(unittest.TestCase):
    def test_accepts_a_well_formed_entry(self):
        m = LOGLINE.match("- 2026-08-04 | task:t1 | human.admin | did a thing")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "2026-08-04")
        self.assertEqual(m.group(3).strip(), "human.admin")

    def test_rejects_a_missing_field(self):
        self.assertIsNone(LOGLINE.match("- 2026-08-04 | task:t1 | did a thing"))


class TestSearchRanking(unittest.TestCase):
    """Relevance is not the only input: a page's trustworthiness is part of its usefulness."""

    def make(self, pid, body, **meta):
        base = {"id": f"concept.{pid}", "summary": "", "status": "active", "confidence": "medium",
                "page_type": "concept", "owner": "team.knowledge"}
        base.update(meta)
        return kbquery.Doc(f"wiki/concepts/{pid}.md", base, body)

    def test_stopwords_and_stemming(self):
        toks = kbquery.tokens("How do the caches work when committing?")
        self.assertNotIn("how", toks)
        self.assertNotIn("do", toks)
        self.assertIn("cach", toks)          # caches -> cach
        self.assertIn("commit", toks)        # committing -> commit

    def test_short_tokens_dropped(self):
        self.assertEqual(kbquery.tokens("a b cd"), ["cd"])

    def test_matching_page_outranks_unrelated_page(self):
        docs = [self.make("a", "kv cache and prefill behaviour"),
                self.make("b", "backups and restore drills")]
        ranked = kbquery.score(docs, "kv cache")
        self.assertEqual(ranked[0][1].id, "concept.a")

    def test_regression_superseded_page_is_demoted(self):
        # Shipped behaviour: a superseded page could outrank the page that replaced it purely
        # on lexical similarity, which is the wrong answer to hand a reader.
        body = "identical text about commit pinned reads"
        docs = [self.make("old", body, status="superseded"),
                self.make("new", body, status="active")]
        ranked = kbquery.score(docs, "commit pinned reads")
        self.assertEqual(ranked[0][1].id, "concept.new")

    def test_confidence_breaks_ties(self):
        body = "identical text about worktrees"
        docs = [self.make("low", body, confidence="low"),
                self.make("high", body, confidence="high")]
        ranked = kbquery.score(docs, "worktrees")
        self.assertEqual(ranked[0][1].id, "concept.high")

    def test_summary_outweighs_body(self):
        # The summary is the curated one-liner; a body mention is weaker evidence of aboutness.
        docs = [self.make("insummary", "unrelated prose", summary="leases and expiry"),
                self.make("inbody", "leases and expiry mentioned once in passing")]
        ranked = kbquery.score(docs, "leases")
        self.assertEqual(ranked[0][1].id, "concept.insummary")

    def test_no_query_terms_returns_nothing(self):
        self.assertEqual(kbquery.score([self.make("a", "text")], "the and of"), [])

    def test_outbound_links_collected_from_body_and_frontmatter(self):
        d = self.make("a", "see [[concept.b]] for more", related=["concept.c"],
                      supersedes=["concept.d"])
        self.assertEqual(d.outbound, {"concept.b", "concept.c", "concept.d"})

    def test_html_comments_excluded_from_links(self):
        d = self.make("a", "<!-- [[concept.example]] in a template -->real text")
        self.assertEqual(d.outbound, set())


class TestIndexRendering(unittest.TestCase):
    def test_render_is_deterministic_and_ordered(self):
        class FakePage:
            def __init__(self, pid, ptype):
                self.id = f"{ptype}.{pid}"
                self.page_type = ptype
                self.meta = {"summary": "s", "owner": "team.knowledge",
                             "confidence": "high", "visibility": "public",
                             "status": "active", "id": self.id}

            def link_from_wiki(self):
                return f"{self.page_type}s/{self.id}.md"

        pages = [FakePage("b", "concept"), FakePage("a", "concept"), FakePage("z", "entity")]
        first = kbcore.render_wiki_index(pages)
        self.assertEqual(first, kbcore.render_wiki_index(pages))          # deterministic
        self.assertLess(first.index("[concept.a]"), first.index("[concept.b]"))   # id order
        self.assertLess(first.index("## Concepts"), first.index("## Entities"))   # type order
        self.assertIn(kbcore.GENERATED_MARKER, first)


if __name__ == "__main__":
    unittest.main(verbosity=2)
