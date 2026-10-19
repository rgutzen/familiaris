"""Stage 5b -- co-location link proposals, and their dismissal wiring.

5a (back-link repair, gated on conventions/**) and 5c (trigger promotion) are
untouched by this handoff and not covered here; this file is about whether a
dismissed link proposal is suppressed while the co-occurrence that produced it
still holds.
"""
import datetime as dt

import pytest

from consolidation import ledger, pass_ctx
from consolidation.stages import associate


@pytest.fixture
def ctx(tmp_path):
    agents = tmp_path / "agents"
    (agents / "knowledge").mkdir(parents=True)
    (agents / "skills").mkdir()
    return pass_ctx.Pass(agents, tmp_path / "data", False, dt.date(2026, 9, 8))


def _co_occur(base, a, b, cwd_prefix, n):
    """Pair skills `a` and `b` in `n` DISTINCT working dirs -- 5b counts a pair
    once per cwd where both appear, so the n>=3 threshold means 3 different
    cwds, not 3 lines in one."""
    for i in range(n):
        for s in (a, b):
            ledger.append(base, ledger.USAGE,
                         {"ts": "2026-09-07T00:00:00Z", "harness": "claude",
                          "skill": s, "session": "x", "cwd": f"{cwd_prefix}-{i}",
                          "signal": "model", "caller": "user", "terms": []})


def _pad(base, n):
    """Filler usage lines so the total clears MIN_SAMPLE without adding pairs."""
    for i in range(n):
        ledger.append(base, ledger.USAGE,
                     {"ts": "2026-09-07T00:00:00Z", "harness": "claude",
                      "skill": f"filler-{i}", "session": "y", "cwd": "/z",
                      "signal": "model", "caller": "user", "terms": []})


def test_a_frequent_pair_is_proposed_as_a_link(ctx):
    _co_occur(ctx.base, "alpha", "beta", "/proj", 3)
    _pad(ctx.base, 30)
    associate.run(ctx)
    links = [p for p in ctx.proposals if p.kind == "link"]
    assert links and links[0].target == "alpha ↔ beta"
    assert links[0].target_kind == "opaque"


def test_a_dismissed_link_is_not_reproposed_while_it_still_holds(ctx):
    _co_occur(ctx.base, "alpha", "beta", "/proj", 3)
    _pad(ctx.base, 30)
    ledger.record_dismissal(ctx.base, ctx.repo, "alpha ↔ beta", "link",
                            target_kind="opaque")
    associate.run(ctx)
    assert not [p for p in ctx.proposals if p.kind == "link"]
    notes = [n for n in ctx.notes if n.stage == "5b" and "suppressed" in n.text]
    assert len(notes) == 1 and "1 link proposal" in notes[0].text


def test_dismissing_one_pair_does_not_suppress_another(ctx):
    _co_occur(ctx.base, "alpha", "beta", "/proj", 3)
    _pad(ctx.base, 30)
    ledger.record_dismissal(ctx.base, ctx.repo, "gamma ↔ delta", "link",
                            target_kind="opaque")
    associate.run(ctx)
    assert [p.target for p in ctx.proposals if p.kind == "link"] == ["alpha ↔ beta"]
