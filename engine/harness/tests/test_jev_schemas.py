"""One question per item kind, and the hash that pins its wording (item 2c).

The exit criterion is coverage against the MOST RECENT REPORT, so this file both
computes that coverage from the real report and asserts the properties that make
coverage meaningful -- an undeclared kind errors, and a wording change changes
the hash.
"""
import pathlib
import re

import pytest

from harness import jev_schemas as S
from lib import roots

REPORT_DIR = roots.JOURNAL / "reports"


def _kinds_in_latest_report():
    """Every kind the report raises, read from its own numbered rows."""
    files = sorted(REPORT_DIR.glob("*_consolidation.full.md"))
    if not files:
        pytest.skip("no full report to read kinds from")
    text = files[-1].read_text()
    sect = text.split("## Needs a decision", 1)[1].split("## ", 1)[0]
    kinds = set()
    for line in sect.splitlines():
        m = re.match(r"\s*\d+\s+(\S+)\s+", line)
        if m:
            kinds.add(m.group(1))
    return kinds


# ── coverage: the exit criterion ─────────────────────────────────────────────

def test_every_kind_in_the_latest_report_has_a_question():
    """An undeclared kind is an error, not a default: a kind the report raises
    and this module cannot ask must fail loudly rather than be asked a generic
    question and answered anyway."""
    kinds = _kinds_in_latest_report()
    assert kinds, "the report parser found no kinds -- check the row shape"
    got = S.coverage(kinds)
    assert got["missing"] == [], (
        f"no question for these kinds raised by the report: {got['missing']}")
    assert got["needs_ontology"] == [], (
        f"these need the ontology class list: {got['needs_ontology']}")


def test_every_kind_either_has_a_schema_or_is_declared_awaiting_the_ontology():
    """The declared set and the implemented set must account for exactly the
    same kinds -- nothing implemented-but-undeclared, nothing declared-and-absent."""
    assert S.NEEDS_ONTOLOGY == () or all(k not in S.SCHEMAS for k in S.NEEDS_ONTOLOGY)


# ── the labelling questions (ontology SPECS O1n) ──────────────────────

def test_the_labelling_criteria_map_is_the_ontology_register_not_a_copy():
    """ONE ARTIFACT, TWO READERS, and `is` rather than `==` is the whole test: a
    copy that happens to match today is the drift this track exists to prevent."""
    from knowledge import ontology
    assert S.SCHEMAS["leaf-subject"]["question"]["criteria"] \
        is ontology.criteria("subject")
    assert S.SCHEMAS["entry-subject"]["question"]["criteria"] \
        is ontology.criteria("entry-subject")
    assert S.SCHEMAS["entry-area"]["question"]["criteria"] \
        is ontology.criteria("area")


def test_the_labelling_questions_cover_the_ontology_and_need_nothing_more():
    """The exit criterion: `coverage()` reports `needs_ontology: []`."""
    got = S.coverage(["leaf-subject", "entry-subject", "entry-area"])
    assert got["needs_ontology"] == []
    assert got["missing"] == []
    assert sorted(got["covered"]) == ["entry-area", "entry-subject",
                                       "leaf-subject"]


def test_entry_subject_offers_areas_as_a_terminal_and_entry_area_answers_it():
    """`areas` is not one of the registered subjects; it is the terminal that
    opens the second question, which is why the second question exists."""
    from knowledge import ontology
    entry = S.SCHEMAS["entry-subject"]["question"]["criteria"]
    assert "areas" in entry
    assert set(ontology.criteria("subject")) < set(entry)
    # The second question offers the Areas the PROFILE IN FORCE declares, and
    # that is what the generator reads -- so this is the half that has to hold
    # wherever the tree runs, including the published one, whose example
    # profile declares five of the sixteen letters.
    assert set(S.SCHEMAS["entry-area"]["question"]["criteria"]) == \
        set(ontology.criteria("area"))


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="this machine's profile declares all sixteen letters, so its Areas "
           "and the ontology's closed A-P domain happen to be the same set; "
           "the shipped example declares five, and only the invariant above "
           "holds there")
def test_the_instance_s_profile_fills_the_whole_area_domain():
    """The two sets coincide on this machine, which is what makes A-P a closed
    domain rather than a coincidence -- and it is a fact about the profile, not
    about the generator, so it is asserted apart from the generator's own rule."""
    from knowledge import ontology
    assert set(ontology.criteria("area")) == set(ontology.FACETS["area"].domain)


def test_a_kind_with_no_question_raises_rather_than_defaulting():
    with pytest.raises(S.UndeclaredKind) as exc:
        S.question("a-kind-nobody-declared")
    assert "not a default" in str(exc.value)


def test_coverage_reports_a_missing_kind_rather_than_raising():
    """A caller reports the gap in the report; it does not die on it. The pass
    must survive a stage that starts raising a new kind."""
    got = S.coverage(["dangling-link", "brand-new-kind"])
    assert got["missing"] == ["brand-new-kind"]
    assert got["covered"] == ["dangling-link"]


# ── every schema is a question the API will accept ───────────────────────────

def test_every_schema_has_a_type_and_instructions():
    for kind, entry in S.SCHEMAS.items():
        q = entry["question"]
        assert q.get("type") in (S.NOUL, S.CHOICE, S.SCORE), kind
        assert q.get("instructions"), kind


def test_a_choice_schema_carries_its_options_and_a_score_its_levels():
    """The API requires `criteria` for choice (`minProperties: 1`) and score
    (`minItems: 1`). A schema without them is a 422 at 03:00."""
    for kind, entry in S.SCHEMAS.items():
        q = entry["question"]
        if q["type"] == S.CHOICE:
            assert q.get("criteria"), f"{kind}: a choice with no options"
        if q["type"] == S.SCORE:
            assert len(q.get("criteria") or []) >= 2, f"{kind}: score needs >= 2 levels"


def test_a_noul_with_criteria_states_both_poles():
    """`criteria.true` and `criteria.false` are what make a noul interpreted the
    same way by us and by the model. One without the other invites a polarity
    flip, and a flipped noul is a confident wrong answer."""
    for kind, entry in S.SCHEMAS.items():
        q = entry["question"]
        if q["type"] == S.NOUL and "criteria" in q:
            assert set(q["criteria"]) == {"true", "false"}, kind


def test_every_schema_declares_what_an_accept_does():
    """The report shows the action; `decide` never reads it, but an item whose
    consequence is unstated is an item the user cannot judge."""
    for kind, entry in S.SCHEMAS.items():
        assert entry.get("action"), f"{kind} has no stated action"


# ── the hash is the validity envelope ────────────────────────────────────────

def test_the_hash_is_stable_across_calls():
    assert S.schema_hash("dangling-link") == S.schema_hash("dangling-link")


def test_two_kinds_do_not_share_a_hash():
    hashes = S.all_hashes().values()
    assert len(set(hashes)) == len(list(hashes))


def test_editing_a_question_wording_changes_its_hash(monkeypatch):
    """The property SPECS.md 2e depends on: a wording change must start a new
    calibration population rather than inherit the old threshold."""
    before = S.schema_hash("dangling-link")
    edited = dict(S.SCHEMAS)
    q = dict(S.SCHEMAS["dangling-link"]["question"])
    q["instructions"] = q["instructions"] + " (reworded)"
    edited["dangling-link"] = dict(S.SCHEMAS["dangling-link"], question=q)
    monkeypatch.setattr(S, "SCHEMAS", edited)
    assert S.schema_hash("dangling-link") != before


def test_key_order_is_not_mistaken_for_a_wording_change():
    """`sort_keys=True`: reordering the same object must NOT move the hash, or
    every incidental edit would silently start a new population."""
    import json
    q = S.SCHEMAS["dangling-link"]["question"]
    a = json.dumps({k: q[k] for k in sorted(q)}, sort_keys=True)
    b = json.dumps({k: q[k] for k in sorted(q, reverse=True)}, sort_keys=True)
    assert a == b


# ── the band rule's input (2d reads this) ────────────────────────────────────

def test_the_promoted_kinds_are_declared_as_such():
    """`trust:`, `supersedes:` and `contradicts:` are written only on an explicit
    accept, never on a band. Listed as data so 2d asserts against a list."""
    assert "supersede-leaf" in S.PROMOTED
    assert all(S.is_promotion(k) for k in S.PROMOTED)
    assert not S.is_promotion("dangling-link")


def test_a_promotion_kind_still_has_a_question():
    """It must be asked -- the recommendation is shown, it simply cannot band."""
    for kind in S.PROMOTED:
        assert S.question(kind)


def test_the_question_carries_no_state():
    """The payload goes in `criteria`/`instructions` and `state` stays at the
    item: that is what makes batching cheap without the accuracy loss."""
    for kind, entry in S.SCHEMAS.items():
        assert "state" not in entry["question"], kind
