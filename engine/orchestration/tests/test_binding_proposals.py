"""6d's analysis: what the two logs say about the model a binding names.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  the evidence   Own-verdict labels make a rate; SHARED labels (one verifier over
                 several items) make nothing. A rate built from a shared verdict
                 would read as a per-item pass rate and is the mistake `labels.py`
                 exists to prevent.
  the thresholds Both are floors on a COUNT, never a tuned score: fewer than three
                 own-verdict labels is not a rate, and under three of four the model
                 is not an alternative.
  the price      The alternative is the cheapest judged model, ties to the more
                 labelled one, and the ratio is carried INTO the proposal --
                 including when it is dearer. Refusing a dearer alternative would
                 hide the trade a person has to ratify.
  the class      14h: a binding is judged on its role's class only. An unjudged
                 model there is a note, a failing one is proposed against a model
                 judged IN THE SAME CLASS, and the shipped config proposes nothing
                 today (code-review runs as `bash`, class batch, which has no record).
  the silence    Every binding left alone returns a note. A report that looks the
                 same whether the bindings were checked or skipped is the failure
                 mode this stage's evidence exists to avoid.

Nothing here writes `bindings.yaml`, and nothing here needs a `Pass`: the stage
that wraps this is `consolidation/stages/bindings.py`, tested beside it.
"""
import json
import pathlib

import pytest

from orchestration import bindings, models

DATA = pathlib.Path(__file__).resolve().parents[3] / "dev/orchestration"


def label(model, passed=True, verdict="own", attempt=1):
    return {"ran_model": model, "passed": passed, "verdict": verdict, "attempt": attempt}


def delegation(role, model_, compression=None, used=None):
    return {"role": role, "model": model_, "compression": compression, "used": used}


def table(*rows):
    return {"bindings": [dict(on=on, role=role, model=mid) for on, role, mid in rows]}


def catalogue(*rows):
    return {"models": [dict(id=mid, cost={"in": str(i), "out": str(o)}) for mid, i, o in rows],
            "candidates": []}


# --- the evidence -------------------------------------------------------------

def test_bindings_own_verdicts_make_a_rate_and_shared_ones_do_not():
    ev = bindings.evidence(
        [label("deepseek/deepseek-flash", True), label("deepseek/deepseek-flash", False),
         label("deepseek/deepseek-flash", True, verdict="shared"),
         label("claude-bridge/claude-opus-5-5", False)],
        [])
    row = ev["models"]["deepseek-flash"]
    assert (row["labels"], row["own"], row["passed"]) == (3, 2, 1)
    assert bindings.rate(row) == 0.5
    assert ev["models"]["claude-opus-5-5"]["own"] == 1


def test_bindings_delegations_summarise_a_role_and_never_choose_a_model():
    ev = bindings.evidence([], [delegation("explore", "deepseek/deepseek-flash", 10.0, True),
                                delegation("explore", "deepseek/deepseek-flash", 4.0, False),
                                delegation("explore", "deepseek/deepseek-flash", 20.0)])
    row = ev["roles"][("explore", "deepseek-flash")]
    assert (row["calls"], row["median_compression"], row["used"]) == (3, 10.0, 1)


def test_bindings_an_item_checked_twice_counts_once():
    """3f's grain is the item: a rerun and a second `verify:` are not new items.
    Counting rows instead reported 16 of 19 where `labels --report` said 13 of 16
    for the same model -- two numbers for one fact."""
    ev = bindings.evidence([label("deepseek/deepseek-flash", True),
                            label("deepseek/deepseek-flash", False, attempt=2),
                            label("deepseek-flash", True)], [])
    row = ev["models"]["deepseek-flash"]
    assert (row["own"], row["passed"]) == (2, 2), \
        "the rerun is dropped, and the two spellings of one id are one model"


def test_bindings_three_labels_are_the_floor_and_three_of_four_is_useable():
    assert not bindings.judged({"own": 2, "passed": 2})
    assert bindings.judged({"own": 4, "passed": 3})
    assert not bindings.judged({"own": 4, "passed": 2})
    assert not bindings.judged(None)
    assert bindings.MIN_LABELS == 3 and bindings.MIN_PASS == 0.75


# --- the rule (per class since 14h) ------------------------------------------

CLASSES = {"research": "read", "explore": "read", "bash": "batch"}


def test_bindings_an_unjudged_model_gets_a_note_not_a_proposal():
    """14h: no evidence in the binding's class is a reason to collect some, not to
    swap on numbers from elsewhere."""
    t = table(("tool:fetch", "research", "model-a"))
    cat = catalogue(("model-a", 1, 1), ("model-b", 2, 2))
    ev = bindings.evidence([dict(label("model-b"), **{"class": "read"})] * 4
                           + [dict(label("model-a"), **{"class": "edit"})] * 9, [], tasks={})
    proposals, notes = bindings.proposal_for(t, cat, ev, CLASSES)
    assert proposals == []
    assert "model-a is unjudged in read (0 own verdict(s)); no proposal" in notes[0]


def test_bindings_no_evidence_crosses_classes():
    """6d's own defect: 14/17 IMPLEMENTATION items once proposed a code-review model."""
    t = table(("skill:code-review", "bash", "model-a"))
    cat = catalogue(("model-a", 1, 1), ("model-b", 1, 1))
    ev = bindings.evidence([dict(label("model-b"), **{"class": "edit"})] * 17
                           + [dict(label("model-a", False), **{"class": "batch"})] * 4,
                           [], tasks={})
    proposals, notes = bindings.proposal_for(t, cat, ev, CLASSES)
    assert proposals == [] and "no model the batch record judges" in notes[0]


def test_bindings_a_judged_model_is_left_alone_with_its_numbers():
    t = table(("tool:read", "explore", "model-a"))
    cat = catalogue(("model-a", 1, 1), ("model-b", 1, 1))
    ev = bindings.evidence([dict(label("model-a"), **{"class": "read"})] * 4, [], tasks={})
    proposals, notes = bindings.proposal_for(t, cat, ev, CLASSES)
    assert proposals == []
    assert "judged in read -- 4/4 first-pass, nothing to propose" in notes[0]


def test_bindings_a_failing_model_is_proposed_within_its_class_and_the_dearer_price_is_named():
    t = table(("tool:verify", "bash", "model-a"))
    cat = catalogue(("model-a", 1, 1), ("model-b", 3, 3), ("model-c", 2, 2))
    ev = bindings.evidence([dict(label("model-a", False), **{"class": "batch"})] * 4
                           + [dict(label("model-b"), **{"class": "batch"})] * 4
                           + [dict(label("model-c"), **{"class": "edit"})] * 4, [], tasks={})
    proposals, _notes = bindings.proposal_for(t, cat, ev, CLASSES)
    assert [(p["model"], p["to"], p["class"], p["price"]["ratio"]) for p in proposals] == \
        [("model-a", "model-b", "batch", 3.0)], "model-c is judged in edit, not in batch"


def test_bindings_routed_and_classless_bindings_get_a_note_not_a_proposal():
    t = table(("tool:explore", "explore", "route"), ("tool:x", "nobody", "model-a"))
    proposals, notes = bindings.proposal_for(t, catalogue(("model-a", 1, 1)),
                                             bindings.evidence([], [], tasks={}), CLASSES)
    assert proposals == []
    assert any("`model: route`" in n for n in notes)
    assert any("role nobody declares no class" in n for n in notes)


def test_bindings_the_shipped_config_proposes_nothing_today():
    """The real `bindings.yaml`: code-review runs as `bash` (class batch), where no
    model has a record, so 6d's old proposal is a note now."""
    ev = bindings.evidence([dict(label("deepseek/deepseek-flash", i < 16), **{"class": "edit"})
                            for i in range(19)], [], tasks={})
    proposals, notes = bindings.proposal_for(bindings.load(), models.load(), ev)
    assert proposals == []
    assert any(n.startswith("skill:code-review: claude-haiku-5-5 is unjudged in batch")
               for n in notes)
    assert any("`model: route`" in n for n in notes)


def test_bindings_no_log_reads_as_no_proposal_and_no_crash():
    proposals, notes = bindings.proposal_for(bindings.load(), models.load(),
                                             bindings.evidence([], [], tasks={}))
    assert proposals == []
    # One note per shipped binding, counted off the table itself: a hard number here
    # made every new binding edit an unrelated test file (1c added `role:deepen`).
    assert len(notes) == len(bindings.load()["bindings"])


def test_bindings_a_class_record_counts_what_the_router_counts():
    """14h: calibration attempts (read) and `used` delegations (the role's class)
    are verdicts too, so 6d and 14g read one record."""
    ev = bindings.evidence(
        [], [delegation("explore", "deepseek/deepseek-flash", 10.0, True),
             delegation("explore", "deepseek/deepseek-flash", 10.0, None)],
        tasks={}, classes={"explore": "read"},
        calibration=[{"model": "deepseek-flash", "verified": 8, "total": 8},
                     {"model": "deepseek-flash", "verified": 7, "total": 8},
                     {"model": "deepseek-flash", "ran": False, "verified": 0, "total": 8}])
    row = ev["by_class"][("deepseek-flash", "read")]
    assert (row["own"], row["passed"]) == (3, 2), "a `used: None` and a child that never ran wait"
