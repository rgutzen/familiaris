"""The scored tree -- the seam every stage crosses.

The contract worth holding: a loaded document is a SCORED document, the weakest
slice is taken by RANK rather than by an absolute threshold, and `rescore()`
exists for the one stage that writes the frontmatter R is derived from.
"""
import datetime as dt
import os

import pytest

from consolidation import ranking
from knowledge import tree

TODAY = dt.date(2026, 9, 3)
OLD = (TODAY - dt.timedelta(days=400))


def _leaf(path, *, verified=None, use_count=0, last_used=None, trust="trusted",
          authority="agent", stability="evolving"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: {path.stem}\n"
        f"authority: {authority}\n"
        f"trust: {trust}\n"
        f"last_verified: {verified or ''}\n"
        f"use_count: {use_count}\n"
        f"last_used: {last_used or ''}\n"
        f"stability: {stability}\n"
        "related: []\n"
        "---\n\n"
        f"# {path.stem}\n")
    # Age the file past the cold-start window: with no git history, `created`
    # falls back to mtime, and everything younger than 60 days is exempt.
    old = dt.datetime.combine(OLD, dt.time()).timestamp()
    os.utime(path, (old, old))


@pytest.fixture
def agents(tmp_path):
    a = tmp_path / "agents"
    (a / "knowledge").mkdir(parents=True)
    _leaf(a / "knowledge" / "fresh.md", verified=TODAY.isoformat(),
          use_count=10, last_used=TODAY.isoformat())
    _leaf(a / "knowledge" / "stale.md", verified="2024-01-01")
    _leaf(a / "knowledge" / "unverified.md")
    _leaf(a / "knowledge" / "human.md", verified=TODAY.isoformat(), authority="human")
    _leaf(a / "skills" / "system" / "practice" / "doer" / "SKILL.md", verified=TODAY.isoformat())
    # Excluded by SKIP_NAMES: a router is a derived artifact, not a leaf.
    (a / "knowledge" / "CONTEXT.md").write_text("---\ntitle: router\n---\n")
    (a / "knowledge" / "_leaf-template.md").write_text("---\ntitle: template\n---\n")
    return a


@pytest.fixture
def loaded(agents, tmp_path):
    return ranking.load(agents, tmp_path / "data", TODAY)


# ── loading ──────────────────────────────────────────────────────────────────

def test_a_loaded_document_is_a_scored_document(loaded):
    assert len(loaded) == 5
    assert all(d.scores for d in loaded), "unscored is not an observable state"


def test_routers_and_templates_are_not_leaves(loaded):
    assert {d.name for d in loaded.leaves()} == {"fresh", "stale", "unverified", "human"}


def test_skills_are_found_and_kept_apart_from_leaves(loaded):
    assert [d.name for d in loaded.skills()] == ["doer"]
    assert len(loaded.leaves()) + len(loaded.skills()) == len(loaded)


# ── scores ───────────────────────────────────────────────────────────────────

def test_scorable_is_ordered_weakest_first(loaded):
    rs = [d.scores["R"] for d in loaded.scorable()]
    assert rs == sorted(rs) and None not in rs


def test_exempt_and_scorable_partition_the_tree(loaded):
    assert len(loaded.scorable()) + len(loaded.exempt()) == len(loaded)
    assert not ({d.name for d in loaded.scorable()} & {d.name for d in loaded.exempt()})


def test_a_never_verified_leaf_is_exempt_and_findable_by_reason(loaded):
    assert [d.name for d in loaded.exempt_for("never-verified")] == ["unverified"]
    assert all(d.scores["R"] is None for d in loaded.exempt_for("never-verified"))


def test_bottom_takes_a_rank_slice_never_a_threshold(loaded):
    scorable = loaded.scorable()
    assert len(loaded.bottom(0.25)) == max(1, int(len(scorable) * 0.25))
    assert loaded.bottom(0.25)[0] is scorable[0], "the weakest, whatever its R"
    assert loaded.bottom(1.0) == scorable


def test_bottom_of_a_fully_exempt_tree_is_empty(agents, tmp_path):
    for p in (agents / "knowledge").glob("*.md"):
        if p.name not in tree.SKIP_NAMES:
            _leaf(p)                                   # no last_verified anywhere
    _leaf(agents / "skills" / "system" / "practice" / "doer" / "SKILL.md")
    t = ranking.load(agents, tmp_path / "data2", TODAY)
    assert t.scorable() == [] and t.bottom(0.25) == []
    assert len(t.exempt()) == len(t)


def test_ranked_puts_the_exempt_first_so_the_report_reads_that_way(loaded):
    ranked = loaded.ranked()
    scored_from = next(i for i, d in enumerate(ranked) if d.scores["R"] is not None)
    assert all(d.scores["R"] is None for d in ranked[:scored_from])


def test_human_authority_reaches_the_scores(loaded):
    human = next(d for d in loaded.leaves() if d.name == "human")
    assert human.scores["human"] is True


# ── the one mutation ─────────────────────────────────────────────────────────

def test_rescore_picks_up_frontmatter_a_stage_has_just_written(loaded):
    """Stage 2 writes use_count/last_used, then re-scores. Without this the rest
    of the pass would read the tree as it was BEFORE tonight's usage landed."""
    doc = next(d for d in loaded.leaves() if d.name == "stale")
    before = doc.scores["U"]
    doc.fm.update({"use_count": 10, "last_used": TODAY.isoformat()})
    assert doc.scores["U"] == before, "scores do not move until asked"
    loaded.rescore()
    assert doc.scores["U"] > before


def test_active_days_is_reported_not_just_used(loaded):
    # Stage 3 states the number in the report; an empty record must be visible
    # as empty rather than presented as a measurement.
    assert isinstance(loaded.active_days, frozenset)
