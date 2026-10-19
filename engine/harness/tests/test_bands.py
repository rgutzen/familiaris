"""The band rule: one rule per primitive, and promotion never bands (item 2d).

The exit criterion is one test per primitive plus a test asserting the promoted
kinds cannot be banded AT ANY THRESHOLD -- the second is the load-bearing one,
because it is the property that stops a probability writing `trust:`.
"""
import pytest

from harness import bands, jev_schemas


# ── the triple itself ────────────────────────────────────────────────────────

def test_a_triple_refuses_cuts_that_cross():
    with pytest.raises(ValueError):
        bands.Triple(accept_at=0.3, drop_below=0.7)


def test_a_triple_refuses_values_outside_zero_to_one():
    with pytest.raises(ValueError):
        bands.Triple(accept_at=1.5, drop_below=0.0)
    with pytest.raises(ValueError):
        bands.Triple(accept_at=0.5, drop_below=-0.1)


def test_a_kind_without_its_own_triple_uses_the_shared_one():
    assert bands.triple("dangling-link") is bands.DEFAULT


def test_a_per_kind_triple_overrides_the_shared_one(monkeypatch):
    monkeypatch.setitem(bands.TRIPLES, "dangling-link",
                        bands.Triple(accept_at=0.9, drop_below=0.1))
    assert bands.triple("dangling-link").accept_at == 0.9
    assert bands.triple("other").accept_at == bands.DEFAULT.accept_at


# ── one rule per primitive ───────────────────────────────────────────────────

def test_a_noul_thresholds_on_its_probability():
    """A Noul returns one number and nothing else, so this is the only rule it
    admits -- not a simplification that could later gain a second axis."""
    kind = "dangling-link"
    high = bands.of_answer(kind, {"type": "noul", "noul": 0.95})
    low = bands.of_answer(kind, {"type": "noul", "noul": 0.05})
    mid = bands.of_answer(kind, {"type": "noul", "noul": 0.5})
    assert high["band"] == bands.ACCEPT and high["value"] == 0.95
    assert low["band"] == bands.DROP and low["value"] == 0.05
    assert mid["band"] == bands.ASK
    assert high["axis"] == "probability"


def test_a_choice_thresholds_on_the_winning_option():
    kind = "new-leaf"
    got = bands.of_answer(kind, {"type": "choice", "choice": "a",
                                 "probabilities": {"a": 0.9, "b": 0.1},
                                 "confidence": 0.7})
    assert got["band"] == bands.ACCEPT and got["value"] == 0.9
    assert got["axis"] == "choice_probability"
    # a spread-out answer is ask, not a coin-flip accept
    spread = bands.of_answer(kind, {"type": "choice", "choice": "a",
                                    "probabilities": {"a": 0.4, "b": 0.35, "c": 0.25}})
    assert spread["band"] == bands.ASK


def test_a_score_thresholds_on_the_mass_of_action_bearing_levels():
    """A Score has ordered levels: `how much does this matter` is the mass at or
    above the level where the action happens, not the average."""
    kind = "stability"
    answer = {"type": "score", "score": 1.2,
              "probabilities": {"0": 0.05, "1": 0.15, "2": 0.80},
              "levels": {"0": 0, "1": 1, "2": 2},
              "action_from": 2}
    got = bands.of_answer(kind, answer)
    assert got["value"] == pytest.approx(0.80)
    assert got["band"] == bands.ACCEPT and got["axis"] == "score_mass"


def test_a_score_without_an_action_level_gets_no_band():
    """Without `action_from` nobody has said what the score means, so there is
    no band to give -- and a guessed band would be a decision nobody took."""
    got = bands.of_answer("stability", {"type": "score", "score": 1.2,
                                        "probabilities": {"0": 0.5, "1": 0.5}})
    assert got["band"] == bands.ASK and got["value"] is None


def test_an_unreadable_answer_is_ask_not_a_drop():
    """An answer this code cannot read is not evidence for either decision, and
    `ask` is the state that means a human should look."""
    for answer in ({"type": "noul"}, {}, {"type": "choice", "probabilities": {}}):
        got = bands.of_answer("dangling-link", answer)
        assert got["band"] == bands.ASK and got["value"] is None


# ── promotion can never band: the load-bearing property ──────────────────────

@pytest.mark.parametrize("kind", jev_schemas.PROMOTED)
def test_a_promoted_kind_cannot_be_banded_at_any_threshold(monkeypatch, kind):
    """`trust:`, `supersedes:` and `contradicts:` are written only on an explicit
    accept. A band that wrote itself would be a write authority smuggled in
    behind a probability -- so this must hold even with the thresholds pushed to
    their extremes, which is the case a per-kind override could otherwise open."""
    monkeypatch.setitem(bands.TRIPLES, kind, bands.Triple(accept_at=0.0, drop_below=0.0))
    for value in (0.0, 0.5, 0.99, 1.0):
        got = bands.of_answer(kind, {"type": "noul", "noul": value})
        assert got["band"] == bands.ASK, f"{kind} banded at {value}"
    # ...and the same with a threshold that would accept anything
    monkeypatch.setitem(bands.TRIPLES, kind, bands.Triple(accept_at=0.0, drop_below=0.0))
    got = bands.of_answer(kind, {"type": "noul", "noul": 1.0})
    assert got["band"] == bands.ASK


def test_the_promoted_set_is_not_empty_and_is_the_schemas_own_list():
    """The two must not drift: a kind promoted in the schemas but not here would
    be bandable."""
    assert jev_schemas.PROMOTED
    for kind in jev_schemas.PROMOTED:
        assert bands._is_promotion(kind)
    assert not bands._is_promotion("dangling-link")


def test_every_promoted_kind_has_a_question_so_a_recommendation_is_still_shown():
    """Ask-only means the recommendation is DISPLAYED and cannot be defaulted
    away -- not that the item is unasked."""
    for kind in jev_schemas.PROMOTED:
        assert jev_schemas.question(kind)


# ── the band is recorded with the number it was taken on ─────────────────────

def test_the_result_carries_the_value_and_the_triple_it_used():
    """SPECS.md 2e: the record must let the decision be re-derived, not trusted."""
    got = bands.of_answer("dangling-link", {"type": "noul", "noul": 0.9})
    assert got["value"] == 0.9
    assert got["triple"] == {"accept_at": bands.DEFAULT.accept_at,
                             "drop_below": bands.DEFAULT.drop_below}


# ── ordering (the report's band order) ───────────────────────────────────────

def test_accept_sorts_before_ask_and_ask_before_drop():
    def it(band):
        return {"recommendation": {"band": band}}
    items = [it(bands.DROP), it(bands.ASK), it(bands.ACCEPT)]
    assert [i["recommendation"]["band"] for i in sorted(items, key=bands.order_key)] \
        == [bands.ACCEPT, bands.ASK, bands.DROP]


def test_an_unjudged_item_sorts_with_ask_not_with_drop():
    """Nothing has judged it, which must not be mistaken for a refusal."""
    judged = {"recommendation": {"band": bands.ASK}}
    unjudged = {}
    assert bands.order_key(unjudged) == bands.order_key(judged)


def test_ordering_is_stable_within_a_band():
    def it(band, target):
        return {"recommendation": {"band": band}, "target": target}
    items = [it(bands.ASK, "b"), it(bands.ASK, "a")]
    assert [i["target"] for i in sorted(items, key=bands.order_key)] == ["b", "a"]


# ── the constants are declared, not tuned by intuition ───────────────────────

def test_the_thresholds_are_reported_as_unvalidated():
    """Same contract as `ranking.unvalidated`: a first estimate is declared so it
    is not mistaken for a measured number."""
    out = bands.unvalidated()
    assert any("bands.DEFAULT" in line for line in out)
