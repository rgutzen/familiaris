"""Stage 5d — conflict resolution: deterministic, and quiet when there is none.

The tests that earn their keep here are the ones covering the ways a
deterministic resolver goes wrong:

  * DIRECTION. `supersedes:` runs superseder -> superseded. Wiring the finding
    builder the other way inverts every message, and the inverted text reads
    perfectly plausibly ("X supersedes this leaf" printed on the leaf X is
    replaced BY). A dedicated test pins the direction, because the prose cannot.
  * IDEMPOTENCE. This runs nightly. A check that compares a raw string against a
    rel path never matches, so it re-applies the same marking forever; a check
    that keeps reporting a conflict it already resolved is the unread report
    `consolidation-cycle.md` names as the failure mode this design is most
    exposed to. Both are tested by running twice.
  * QUIET. The live tree's two skill supersessions are already consistent and
    the module must find nothing there. A resolver that cries wolf is worse
    than no resolver, because it poisons the channel that reports real ones.
  * WRITE SCOPE. Exactly `superseded_by`, `supersedes` and `trust`, only inside
    the frontmatter, never on a directive path.
"""
import datetime as dt
import pathlib

import pytest

from consolidation import pass_ctx
from consolidation.stages import conflict


def _doc(root, rel, *, title=None, trust="trusted", verified="2026-09-01",
         supersedes="", superseded_by="", contradicts="", authority="agent",
         summary=None, triggers=None, tags=None):
    """Write one frontmatter-carrying document the way the tree writes them."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = [
        f"title: {title or pathlib.PurePosixPath(rel).stem}",
        f"summary: {summary or 'A leaf about ' + pathlib.PurePosixPath(rel).stem}",
        "origin: authored",
        f"authority: {authority}",
        f"trust: {trust}",
        f"last_verified: {verified}",
        "use_count: 0",
        f"supersedes: {supersedes}",
        f"superseded_by: {superseded_by}",
        f"contradicts: {contradicts}",
        "related: []",
        f"tags: [{', '.join(tags or [])}]",
        f"triggers: [{', '.join(triggers or [])}]",
        "stability: evolving",
    ]
    if rel.startswith("skills/"):
        fm.append(f"name: {pathlib.PurePosixPath(rel).parent.name}")
    p.write_text("---\n" + "\n".join(fm) + "\n---\n\n# Body\n\nThe body of the leaf.\n")
    return p


@pytest.fixture
def root(tmp_path):
    a = tmp_path / "agents"
    (a / "knowledge" / "meta").mkdir(parents=True)
    (a / "knowledge" / "CONTEXT.md").write_text("# router\n")
    return a


def _kinds(p, kind=None):
    return [f for f in p.findings if kind is None or f.kind == kind]


# ── direction ────────────────────────────────────────────────────────────────

def test_the_superseded_leaf_is_the_one_marked_not_the_superseder(root):
    """The regression that matters. `new.md` says `supersedes: old`; `old` is
    the leaf that must be marked, and `new` must not be."""
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    p = conflict.plan(root)
    marked = {f.rel for f in p.writes}
    assert marked == {"knowledge/meta/old.md"}
    f = _kinds(p, "missing-supersession-backlink")[0]
    assert f.rel == "knowledge/meta/old.md"
    assert "knowledge/meta/new.md" in f.what


# ── supersedes: the mechanical closure ──────────────────────────────────────

def test_an_unmarked_supersession_is_marked_and_backlinked(root):
    """Read through `pending()`, not `f.updates`: two findings name `old.md`
    (one for the back-pointer, one for the mark) and the pass writes them as ONE
    merged edit, which is what a reader of the plan needs to see."""
    _doc(root, "knowledge/meta/old.md", trust="trusted")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    pending = conflict.plan(root).pending()
    updates, reasons = pending["knowledge/meta/old.md"]
    assert updates == {"superseded_by": ["new"], "trust": "deprecated"}
    assert len(reasons) == 2


def test_the_back_pointer_is_written_as_a_bare_name_like_related(root):
    """The live tree already spells these `superseded_by: diagnosing-bugs`. A
    rel path would resolve too, and two spellings for one field is how the next
    reader concludes the entries mean different things."""
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    updates, _ = conflict.plan(root).pending()["knowledge/meta/old.md"]
    assert updates["superseded_by"] == ["new"]


def test_a_rel_path_reference_resolves_as_well_as_a_bare_name(root):
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md",
         supersedes="knowledge/meta/old.md")
    assert not _kinds(conflict.plan(root), "dangling-supersession")


def test_an_already_consistent_supersession_produces_nothing(root):
    """The live tree's shape: the superseder declares it, the superseded leaf is
    deprecated and carries the bare-name back-pointer. Nothing to do, and
    nothing to say."""
    _doc(root, "knowledge/meta/old.md", trust="deprecated", verified="2026-08-28",
         superseded_by="new")
    _doc(root, "knowledge/meta/new.md", supersedes="old", verified="2026-09-02")
    p = conflict.plan(root)
    assert p.findings == [] and p.writes == []


def test_applying_twice_changes_nothing_the_second_time(root):
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    assert len(conflict.plan(root).writes) == 2
    conflict.plan(root).apply()
    assert conflict.plan(root).findings == [], "the marking did not settle"


def test_the_marked_file_keeps_every_other_byte(root):
    path = _doc(root, "knowledge/meta/old.md")
    before = path.read_text()
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    conflict.plan(root).apply()
    after = path.read_text()
    for line in before.split("\n"):
        if not line.startswith(("trust:", "superseded_by:")):
            assert line in after, f"line lost: {line!r}"


def test_dangling_supersession_is_reported_and_never_written(root):
    """A reference INSIDE the tree that names nothing: the leaf was renamed, or
    was never written. Reported, never written."""
    _doc(root, "knowledge/meta/a.md", supersedes="knowledge/meta/elsewhere.md")
    p = conflict.plan(root)
    assert p.findings and p.writes == []
    assert _kinds(p, "dangling-supersession")[0].level == "warn"


def test_an_external_supersession_is_not_dangling_and_derives_no_backlink(root):
    """O1d. A target OUTSIDE the memory tree is a real thing: the claim is true
    and the edge's range was too narrow, so there is no finding -- and, stated
    rather than left to be discovered, no `superseded_by:` back-pointer either,
    because there is nothing in this tree to write one into."""
    _doc(root, "knowledge/meta/a.md", supersedes="02_AREAS/elsewhere.md")
    p = conflict.plan(root)
    assert not _kinds(p, "dangling-supersession")
    assert p.findings == [] and p.writes == [] and p.pending() == {}


def test_self_supersession_is_reported(root):
    _doc(root, "knowledge/meta/a.md", supersedes="a")
    assert _kinds(conflict.plan(root), "self-supersession")


def test_a_cycle_is_an_error_and_nothing_in_it_is_marked(root):
    _doc(root, "knowledge/meta/a.md", supersedes="b")
    _doc(root, "knowledge/meta/b.md", supersedes="a")
    p = conflict.plan(root)
    cyc = _kinds(p, "supersession-cycle")
    assert cyc and cyc[0].level == "error"
    assert p.writes == [], "no leaf in a loop can be the current one"


def test_a_declaration_the_dates_contradict_is_reported_not_applied(root):
    _doc(root, "knowledge/meta/old.md", verified="2026-09-05", trust="deprecated",
         superseded_by="new")
    _doc(root, "knowledge/meta/new.md", supersedes="old", verified="2026-08-01")
    p = conflict.plan(root)
    f = _kinds(p, "declaration-outranks-dates")[0]
    assert f.rel == "knowledge/meta/new.md" and f.updates is None


def test_a_backlink_with_no_claim_behind_it_is_reported_not_reasserted(root):
    """`superseded_by:` is derived, so a missing claim is a withdrawn one or a
    lost one — and re-asserting a withdrawn claim would deprecate a live leaf.
    The conservative error is to report."""
    _doc(root, "knowledge/meta/old.md", trust="trial", superseded_by="new")
    _doc(root, "knowledge/meta/new.md", trust="trusted")
    p = conflict.plan(root)
    f = _kinds(p, "unclaimed-supersession-backlink")[0]
    assert f.rel == "knowledge/meta/old.md" and f.updates is None


def test_a_directive_superseded_leaf_is_never_written(root):
    _doc(root, "knowledge/meta/old.md", authority="human")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    p = conflict.plan(root)
    assert p.writes == []
    assert _kinds(p, "human-owned-superseded")


# ── contradicts: ISO-8601 precedence ────────────────────────────────────────

def test_the_later_verification_wins_and_the_loser_is_marked(root):
    _doc(root, "knowledge/meta/early.md", verified="2026-08-01",
         contradicts="late")
    _doc(root, "knowledge/meta/late.md", verified="2026-09-10")
    pending = conflict.plan(root).pending()
    assert pending["knowledge/meta/early.md"][0] == {
        "superseded_by": ["late"], "trust": "deprecated"}
    assert pending["knowledge/meta/late.md"][0] == {"supersedes": ["early"]}


def test_the_precedence_is_symmetric_whichever_side_declared_it(root):
    """`contradicts:` is not directional, so the same pair declared from the
    other end must resolve the same way."""
    _doc(root, "knowledge/meta/early.md", verified="2026-08-01")
    _doc(root, "knowledge/meta/late.md", verified="2026-09-10",
         contradicts="early")
    pending = conflict.plan(root).pending()
    assert pending["knowledge/meta/early.md"][0]["trust"] == "deprecated"


def test_a_tie_cannot_be_ordered_and_needs_a_person(root):
    _doc(root, "knowledge/meta/a.md", verified="2026-09-01",
         contradicts="b")
    _doc(root, "knowledge/meta/b.md", verified="2026-09-01")
    p = conflict.plan(root)
    assert _kinds(p, "contradiction-tied") and p.writes == []


def test_a_missing_date_makes_the_contradiction_undecidable(root):
    _doc(root, "knowledge/meta/a.md", verified="", contradicts="b")
    _doc(root, "knowledge/meta/b.md", verified="2026-09-01")
    p = conflict.plan(root)
    assert _kinds(p, "contradiction-undecidable") and p.writes == []


def test_a_resolved_contradiction_does_not_report_itself_again(root):
    _doc(root, "knowledge/meta/early.md", verified="2026-08-01",
         contradicts="late")
    _doc(root, "knowledge/meta/late.md", verified="2026-09-10")
    assert conflict.plan(root).writes
    conflict.plan(root).apply()
    assert conflict.plan(root).findings == [], "a settled conflict must go quiet"


def test_a_directive_side_of_a_contradiction_is_reported_only(root):
    _doc(root, "knowledge/meta/a.md", verified="2026-08-01", authority="human",
         contradicts="b")
    _doc(root, "knowledge/meta/b.md", verified="2026-09-10")
    p = conflict.plan(root)
    assert p.writes == []
    assert _kinds(p, "human-owned-contradiction")


# ── overlap: candidates, explicitly not contradictions ──────────────────────

def test_overlapping_leaves_are_reported_as_candidates_never_marked(root):
    shared = ["the", "backup", "restic", "prune", "snapshot", "retention"]
    _doc(root, "knowledge/meta/one.md", triggers=shared)
    _doc(root, "knowledge/meta/two.md", triggers=shared)
    p = conflict.plan(root)
    f = _kinds(p, "overlapping-leaf")[0]
    assert f.level == "note" and f.updates is None
    assert "NOT a detected contradiction" in f.why


def test_unrelated_leaves_produce_no_overlap_finding(root):
    _doc(root, "knowledge/meta/one.md", triggers=["backup", "restic"])
    _doc(root, "knowledge/meta/two.md", triggers=["vulkan", "moe", "llama"])
    assert _kinds(conflict.plan(root), "overlapping-leaf") == []


def test_a_declared_conflict_is_not_also_reported_as_overlap(root):
    shared = ["backup", "restic", "prune", "snapshot", "retention"]
    _doc(root, "knowledge/meta/one.md", triggers=shared, verified="2026-08-01",
         contradicts="two")
    _doc(root, "knowledge/meta/two.md", triggers=shared, verified="2026-09-10")
    p = conflict.plan(root)
    assert _kinds(p, "contradiction-resolved")
    assert _kinds(p, "overlapping-leaf") == []


# ── write scope ──────────────────────────────────────────────────────────────

def test_nothing_outside_the_writable_keys_is_ever_written(root):
    _doc(root, "knowledge/meta/a.md", verified="2026-08-01", contradicts="b")
    _doc(root, "knowledge/meta/b.md", verified="2026-09-10")
    _doc(root, "knowledge/meta/c.md", supersedes="d")
    _doc(root, "knowledge/meta/d.md")
    for f in conflict.plan(root).writes:
        assert set(f.updates) <= set(conflict.WRITABLE)


def test_a_leaf_without_the_key_gets_it_added_inside_the_frontmatter(root):
    """The production shape: `_leaf-template.md` only gained `superseded_by:`
    and `contradicts:` in 2026-09, so every leaf written before that has neither
    key at all. `set_fields` appends an absent key at the end of the frontmatter,
    and the test proves it lands there rather than in the body."""
    old = root / "knowledge/meta/old.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("---\ntitle: Old\ntrust: trusted\nlast_verified: 2026-09-01\n"
                   "---\n\n# Old\n\nBody text that must stay in the body.\n")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    assert conflict.plan(root).apply()
    text = old.read_text()
    fm = text.split("---\n")[1]
    assert "superseded_by: [new]" in fm
    assert "trust: deprecated" in fm
    assert "# Old\n\nBody text that must stay in the body." in text.split("---\n", 2)[2]


def test_a_skill_is_in_the_population_because_stage_6_already_reads_it(root):
    _doc(root, "skills/system/practice/old/SKILL.md")
    _doc(root, "skills/system/practice/new/SKILL.md", supersedes="old")
    assert {f.rel for f in conflict.plan(root).writes} == \
        {"skills/system/practice/old/SKILL.md"}


def test_the_population_matches_the_thing_stage_3_scores(root):
    """`tree.SKIP_NAMES` is imported, not re-derived -- an index and a resolver
    that disagree about the denominator is how a check silently under-reports."""
    from knowledge import tree
    _doc(root, "knowledge/meta/real.md")
    for skip in ("CONTEXT.md", "INDEX.md", "_leaf-template.md"):
        (root / "knowledge" / skip).write_text("---\ntitle: not a leaf\n---\n\nx\n")
    rels = {n.rel for n in conflict.plan(root).nodes}
    assert "knowledge/meta/real.md" in rels
    assert not any(pathlib.PurePosixPath(r).name in tree.SKIP_NAMES for r in rels)


# ── CLI and stage ────────────────────────────────────────────────────────────

def test_check_exits_three_when_marking_is_pending(root, monkeypatch):
    monkeypatch.setattr(conflict, "DEFAULT_ROOT", root)
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    assert conflict.main(["--check"]) == 3
    assert "trust: trusted" in (root / "knowledge/meta/old.md").read_text(), \
        "--check must write nothing"


def test_check_exits_zero_on_a_consistent_tree(root, monkeypatch):
    monkeypatch.setattr(conflict, "DEFAULT_ROOT", root)
    _doc(root, "knowledge/meta/only.md")
    assert conflict.main(["--check"]) == 0


def test_the_cli_is_a_report_by_default(root, monkeypatch, capsys):
    monkeypatch.setattr(conflict, "DEFAULT_ROOT", root)
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    assert conflict.main([]) == 0
    assert "trust: trusted" in (root / "knowledge/meta/old.md").read_text()
    assert "APPLY" in capsys.readouterr().out


def test_the_cli_applies_only_under_apply(root, monkeypatch):
    monkeypatch.setattr(conflict, "DEFAULT_ROOT", root)
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    assert conflict.main(["--apply"]) == 0
    assert "trust: deprecated" in (root / "knowledge/meta/old.md").read_text()


def test_a_dry_run_stage_writes_nothing(root, tmp_path):
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    before = (root / "knowledge/meta/old.md").read_text()
    ctx = pass_ctx.Pass(root, tmp_path / "data", True, dt.date(2026, 9, 11))
    conflict.run(ctx)
    assert (root / "knowledge/meta/old.md").read_text() == before
    assert ctx.actions == []
    assert any("pending" in n.text for n in ctx.notes)


def test_the_stage_acts_on_a_real_run_and_proposes_the_rest(root, tmp_path):
    _doc(root, "knowledge/meta/old.md")
    _doc(root, "knowledge/meta/new.md", supersedes="old")
    _doc(root, "knowledge/meta/dangling.md", supersedes="nowhere.md")
    ctx = pass_ctx.Pass(root, tmp_path / "data", False, dt.date(2026, 9, 11))
    conflict.run(ctx)
    assert [a.target for a in ctx.actions] == ["knowledge/meta/old.md"]
    assert [p.kind for p in ctx.proposals] == ["dangling-supersession"]
    assert "trust: deprecated" in (root / "knowledge/meta/old.md").read_text()
