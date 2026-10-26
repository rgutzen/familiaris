"""selection.yaml and the arithmetic inside a tier (decision 27, 2026-10-14).

The policy is a judgement a person writes; this file pins the RULE that reads it:
which tier a difficulty selects, how the models inside a tier are ordered, what a
missing benchmark does (nothing), and what `--check` refuses. Hermetic: every
policy below is built in the test, and one test reads the shipped file to prove it
loads and validates.
"""
import pytest

from orchestration import models, selection


def policy(tiers, **kw):
    sel = {"classes": {"edit": tiers, "unknown": [{"models": "dear", "reason": "the default"}]}}
    sel.update(kw)
    return sel


TIERS = [{"models": "cheap, dear", "up_to_difficulty": "0.5", "reason": "the ordinary case"},
         {"models": "dear", "reason": "the hard case"}]

CAPS = {"task_classes": {"edit": {"capabilities": ["coding"]}}}
CAT = {"models": [{"id": "dear", "kind": "chat", "cost": {"in": "5", "out": "20"}},
                  {"id": "cheap", "kind": "chat", "cost": {"in": "0.1", "out": "0.5"}},
                  {"id": "twin", "kind": "chat", "cost": {"in": "0.1", "out": "0.5"}},
                  {"id": "blind", "kind": "chat", "cost": {"in": "0", "out": "0"}}]}
RULES = {"reference_usage": {"default": {"input": 1000000, "output": 1000000}}, "suggest_kinds": ["chat"],
         "route_floor": 0.0}  # the price and tie order, with no record to filter on


# --- which tier -----------------------------------------------------------------

def test_selection_no_difficulty_reading_takes_the_first_tier():
    """A pre-selection is the baseline: with nothing measured, the class's
    ordinary case applies, not its hardest."""
    tier, idx, why = selection.pick(policy(TIERS), "edit", None)
    assert (selection.models_of(tier), idx) == (["cheap", "dear"], 0)
    assert why == "no difficulty reading, first tier"


def test_selection_the_difficulty_picks_the_first_tier_that_admits_it():
    sel = policy(TIERS)
    assert selection.pick(sel, "edit", 0.2)[1] == 0
    assert selection.pick(sel, "edit", 0.5)[1] == 0, "the boundary is inclusive"
    assert selection.pick(sel, "edit", 0.51)[1] == 1
    assert selection.pick(sel, "edit", 1.0)[1] == 1, "the last tier catches everything"


def test_selection_a_forcing_answer_raises_one_tier_and_is_capped():
    sel = policy(TIERS)
    assert selection.pick(sel, "edit", 0.2, raises=1)[1] == 1
    assert selection.pick(sel, "edit", 0.2, raises=9)[1] == 1, "capped at the last tier"
    assert "raise it to tier 2" in selection.pick(sel, "edit", 0.2, raises=1)[2]


def test_selection_an_unknown_class_is_an_error_not_a_default():
    with pytest.raises(selection.SelectionError, match="no class 'docs'"):
        selection.pick(policy(TIERS), "docs")
    assert selection.pick(policy(TIERS), "unknown")[1] == 0


# --- the order inside a tier ----------------------------------------------------

def test_selection_cheapest_first_ties_by_measured_score_then_the_tier_order(monkeypatch):
    """Price first, then the measured mean, then the tier's own order. The free
    model wins on price INSIDE a tier that named it: membership was judged by a
    person, so there is no way for a free model to win its way in by being free."""
    pct = {"dear": 90, "cheap": 60, "twin": 80, "blind": None}
    monkeypatch.setattr(models, "capability_scores",
                        lambda mid, cat, caps: {"coding": (pct[mid], 1, 1)})
    tier = {"models": "dear, twin, cheap, blind", "_needs": ["coding"]}
    ids, note = selection.cheapest(CAT, CAPS, tier, RULES)
    assert ids == ["blind", "twin", "cheap", "dear"]
    assert note == ""
    # twin and cheap cost the same; the tier's own order decides a score tie.
    pct["twin"] = 60
    assert selection.cheapest(CAT, CAPS, tier, RULES)[0] == ["blind", "twin", "cheap", "dear"]
    # ... and with the tier written the other way round, cheap goes first.
    assert selection.cheapest(CAT, CAPS, {"models": "cheap, twin", "_needs": ["coding"]},
                              RULES)[0] == ["cheap", "twin"]


def test_selection_a_missing_benchmark_never_disqualifies(monkeypatch):
    """The settled correction: a score may order a tier, never gate it."""
    monkeypatch.setattr(models, "capability_scores",
                        lambda mid, cat, caps: {"coding": (None, 0, 0)})
    ids, _ = selection.cheapest(CAT, CAPS, {"models": "dear, cheap", "_needs": ["coding"]}, RULES)
    assert ids == ["cheap", "dear"], "both stay eligible; price still orders them"


def test_selection_a_model_outside_the_catalogue_or_the_privacy_is_dropped_by_name(monkeypatch):
    ids, note = selection.cheapest(CAT, CAPS, {"models": "cheap, ghost"}, RULES)
    assert ids == ["cheap"] and "ghost: not a callable catalogue id" in note
    ids, note = selection.cheapest(CAT, CAPS, {"models": "cheap, dear"}, RULES,
                                   allowed={"dear"})
    assert ids == ["dear"] and "cheap: outside the declared privacy" in note
    assert selection.cheapest(CAT, CAPS, {"models": "cheap"}, RULES, allowed=set()) == (
        [], " (dropped: cheap: outside the declared privacy)")


# --- scope ----------------------------------------------------------------------

def test_selection_scope_is_the_longest_matching_prefix(tmp_path):
    (tmp_path / "a/b").mkdir(parents=True)
    sel = {"scope": {"~": {"egress": "cloud"},
                     str(tmp_path / "a"): {"privacy": "EU-no-training"},
                     str(tmp_path / "a/b"): {"privacy": "local"}}}
    assert selection.scope_of(sel, tmp_path / "a/b/c") == {"privacy": "local"}
    assert selection.scope_of(sel, tmp_path / "a/x") == {"privacy": "EU-no-training"}
    assert selection.scope_of(sel, "/srv") == {}


# --- check ----------------------------------------------------------------------

def test_selection_check_refuses_each_kind_of_bad_policy():
    bad = {"classes": {
        "edit": [{"models": "cheap", "reason": ""},
                 {"models": "ghost, ghost", "up_to_difficulty": "0.9",
                  "reason": "x"}],
        "elsewhere": [{"models": "cheap", "reason": "x"}]},
        "scope": {"relative/path": {"nonsense": "y"}}}
    found = selection.check(bad, CAT, CAPS)
    assert "classes: 'unknown' is declared in capabilities.yaml and not here" in found
    assert "classes: 'elsewhere' is not a task class in capabilities.yaml" in found
    assert "edit tier 1: no reason" in found
    assert "edit tier 2: 'ghost' is not a callable catalogue id" in found
    assert "edit tier 2: the same model twice" in found
    assert ("edit tier 2: unreachable, because edit tier 1 carries no up_to_difficulty "
            "and catches everything") in found
    assert "scope 'relative/path': not an absolute or ~ path" in found
    assert "scope 'relative/path': unknown key 'nonsense'" in found


def test_selection_check_refuses_a_last_tier_that_excludes_the_hardest_work():
    found = selection.check(policy(TIERS), CAT, CAPS)
    assert found == [], "TIERS is a well-formed policy: its last tier catches everything"
    found = selection.check(policy([{"models": "cheap", "up_to_difficulty": "0.5",
                                     "reason": "x"}]), CAT, CAPS)
    assert "edit: the last tier has an up_to_difficulty, so an item above it has no tier" in found


def test_selection_the_shipped_policy_loads_and_checks_clean():
    sel = selection.load()
    cat, caps = models.load(), models.load_capabilities()
    assert selection.check(sel, cat, caps) == []
    for name in ("read", "edit", "test", "docs", "batch", "unknown"):
        ids, _ = selection.cheapest(cat, caps, selection.pick(
            selection.with_needs(sel, caps), name)[0], dispatch_rules())
        assert ids, f"{name}: the shipped policy names no available model"
    scope = selection.scope_of(sel, "~/06_SYSTEM/dev")
    assert scope["egress"] == "cloud" and scope.get("reason")
    assert selection.scope_of(sel, "/tmp") == {}


def dispatch_rules():
    from orchestration import dispatch
    return dispatch.load_config(dispatch.models.load_capabilities())["rules"]
