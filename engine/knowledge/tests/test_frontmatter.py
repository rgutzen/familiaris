"""The line-surgical frontmatter writer.

Why this is the most expensive module to get silently wrong: M1's provenance
backfill lives in trailing `# comments` ("no journal entry", session ids, commit
hashes) that a parse-then-reserialise cycle destroys and cannot reconstruct.
Every test below that asserts something is PRESERVED is guarding that.
"""
import pytest

from knowledge import frontmatter as fm

LEAF = """---
title: A leaf
origin: derived           # distilled by the consolidation pass
trust: trial
last_verified: 2026-08-01
promoted_from: []   # 06_SYSTEM session 2026-08-29, commit 186c643; no journal entry
related: [alpha, beta]
tags: []
---

# A leaf

Body text, with a --- line inside it.
"""


# ── reading ──────────────────────────────────────────────────────────────────

def test_parse_reads_scalars_lists_and_body():
    d = fm.parse(LEAF)
    assert d["title"] == "A leaf"
    assert d["related"] == ["alpha", "beta"]
    assert d["tags"] == []
    assert "Body text" in d["_body"]


def test_parse_strips_trailing_comments_from_values():
    assert fm.parse(LEAF)["origin"] == "derived"


def test_no_frontmatter_is_an_empty_dict_not_an_error():
    assert fm.parse("# just a heading\n") == {}


def test_split_list_honours_quoted_commas():
    # Trigger phrases and scope globs legitimately contain commas; a naive
    # split shreds them into fragments (found the hard way in M1).
    assert fm.split_list('a, "b, c", d') == ["a", "b, c", "d"]


def test_a_wrapped_flow_list_is_one_logical_line():
    text = "---\ntriggers: [one, two,\n  three, four]\nname: x\n---\nbody\n"
    d = fm.parse(text)
    assert d["triggers"] == ["one", "two", "three", "four"]
    assert d["name"] == "x"


# ── writing ──────────────────────────────────────────────────────────────────

def test_setting_a_key_preserves_its_trailing_provenance_comment():
    out = fm.set_fields(LEAF, {"promoted_from": ["journal/2026/09/x.md"]})
    assert "# 06_SYSTEM session 2026-08-29, commit 186c643; no journal entry" in out
    assert fm.parse(out)["promoted_from"] == ["journal/2026/09/x.md"]


def test_every_untouched_byte_survives():
    # `deprecated`, not `trusted`: promotion is refused at this write path
    # (memory/knowledge/meta/memory-poisoning-posture.md), so the byte-preservation
    # property is demonstrated with a
    # value a stage is actually allowed to write.
    out = fm.set_fields(LEAF, {"trust": "deprecated"})
    before, after = LEAF.split("\n"), out.split("\n")
    changed = [(b, a) for b, a in zip(before, after) if b != a]
    assert changed == [("trust: trial", "trust: deprecated")]
    assert len(before) == len(after)


def test_the_body_is_never_touched_even_when_it_contains_a_fence():
    assert fm.set_fields(LEAF, {"title": "New"}).endswith(
        "\n# A leaf\n\nBody text, with a --- line inside it.\n")


def test_an_absent_key_is_appended_inside_the_frontmatter():
    out = fm.set_fields(LEAF, {"use_count": 3})
    assert fm.parse(out)["use_count"] == "3"
    head = out.split("---\n")[1]
    assert head.rstrip().endswith("use_count: 3")


def test_none_means_leave_alone():
    assert fm.set_fields(LEAF, {"trust": None}) == LEAF


def test_a_list_value_is_written_as_one_physical_line():
    text = "---\nrelated: [one,\n  two]\nname: x\n---\nbody\n"
    out = fm.set_fields(text, {"related": ["one", "two", "three"]})
    assert "related: [one, two, three]\n" in out
    assert fm.parse(out)["name"] == "x"


def test_a_value_containing_a_comma_is_quoted_so_it_reads_back_whole():
    out = fm.set_fields(LEAF, {"related": ["a, b", "c"]})
    assert fm.parse(out)["related"] == ["a, b", "c"]


def test_writing_without_frontmatter_is_refused_not_guessed():
    with pytest.raises(ValueError):
        fm.set_fields("no frontmatter here\n", {"title": "x"})


# ── the file-level guard ─────────────────────────────────────────────────────

def test_update_reports_no_change_when_the_bytes_would_not_change(tmp_path):
    p = tmp_path / "leaf.md"
    p.write_text(LEAF)
    assert fm.update(p, {"trust": "trial"}) is False
    assert p.read_text() == LEAF


def test_dry_run_computes_the_change_without_writing_it(tmp_path):
    p = tmp_path / "leaf.md"
    p.write_text(LEAF)
    assert fm.update(p, {"trust": "deprecated"}, dry_run=True) is True
    assert p.read_text() == LEAF, "a dry run must leave the tree byte-identical"


# ── promotion is human-gated (memory-poisoning-posture.md) ───────────────────

def test_no_stage_may_promote_a_leaf_to_trusted():
    """The gate sits at the single write path, so it covers every stage at once
    rather than being asked for in each stage's prose."""
    for value in fm.PROMOTED_TRUST:
        with pytest.raises(fm.PromotionRefused):
            fm.set_fields(LEAF, {"trust": value})


def test_promotion_is_refused_before_anything_is_written(tmp_path):
    p = tmp_path / "leaf.md"
    p.write_text(LEAF)
    with pytest.raises(fm.PromotionRefused):
        fm.update(p, {"trust": "trusted"})
    assert p.read_text() == LEAF


def test_demotion_and_marking_stay_allowed():
    """The gate must not break stage 5d, whose whole job is marking a loser."""
    for value in ("trial", "deprecated", "quarantine"):
        assert f"trust: {value}" in fm.set_fields(LEAF, {"trust": value})


def test_the_gate_reads_the_value_not_the_key():
    """Unrelated fields are untouched by it; only `trust:` is gated."""
    assert "origin: trusted" in fm.set_fields(LEAF, {"origin": "trusted"})
