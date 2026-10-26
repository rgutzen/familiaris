"""The cadence is a property of the registry, and the registry holds its promises.

A tier is a promise about cost and dependence: `daily` and `pre-commit` do not
reach the network, start a model or a harness, or take minutes. The promise is
declared on each entry (`effects`) and held here, so an entry cannot be moved to
a faster tier than it can afford, nor quietly start fetching in one.
"""
import pathlib
import re
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import checks  # noqa: E402

REPO = checks.REPO


def test_a_check_is_in_at_most_one_timer_tier():
    for c in checks.CHECKS:
        assert len(c.gates & set(checks.TIERS)) <= 1, c.id


def test_a_higher_tier_includes_the_lower_ones():
    daily = {c.id for c in checks.tier_checks("daily")}
    weekly = {c.id for c in checks.tier_checks("weekly")}
    monthly = {c.id for c in checks.tier_checks("monthly")}
    assert daily < weekly < monthly


@pytest.mark.parametrize("gate", [checks.GATE_PRE_COMMIT, checks.GATE_DAILY])
def test_the_fast_gates_hold_their_promise(gate):
    """Nothing in `pre-commit` or `daily` fetches, spends, or starts a harness."""
    for c in checks.CHECKS:
        if gate in c.gates:
            assert not c.effects & checks.FORBIDDEN_IN_FAST, (gate, c.id, sorted(c.effects))


def test_nothing_is_paid():
    assert not [c.id for c in checks.CHECKS if "paid" in c.effects and c.gates & set(checks.TIERS)]


def test_the_export_gate_is_unchanged_by_the_tiers():
    """The export is `pre-commit` minus its exclusions; a tier never joins it."""
    export = {c.id for c in checks.gate_checks(checks.GATE_EXPORT)}
    assert export == {c.id for c in checks.CHECKS
                      if checks.GATE_PRE_COMMIT in c.gates} - checks.EXPORT_EXCLUDED


def test_a_check_with_a_timer_of_its_own_is_run_by_no_gate():
    own = [c for c in checks.CHECKS if c.owner == checks.TIMERS]
    assert own, "the timer-owned entries are the point of the field"
    for c in own:
        assert not checks.runs_here(c, checks.GATE_MANUAL), c.id
        assert not c.gates & set(checks.TIERS), c.id


def test_a_gate_does_not_run_what_its_owner_runs():
    owned = [c for c in checks.CHECKS if c.owner == checks.HEALTHCHECK]
    assert owned
    for c in owned:
        assert not checks.runs_here(c, checks.GATE_DAILY), c.id
        assert checks.runs_here(c, checks.GATE_MANUAL), c.id


def test_every_tier_names_a_timer_that_the_master_config_declares():
    config = checks.owner_path(checks.TIMERS).read_text()
    for tier, unit in checks.TIER_TIMER.items():
        assert re.search(rf'\["{re.escape(unit)}"\]=', config), (tier, unit)


def test_the_owner_and_tier_claims_hold():
    assert checks.owner_findings() == []
    assert checks.tier_findings() == []


def test_a_section_without_its_due_line_is_caught(monkeypatch):
    ghost = checks.Check("hc-ghost", "d", (checks.HEALTHCHECK, "--only", "hc-ghost"),
                         frozenset({checks.GATE_DAILY}), owner=checks.HEALTHCHECK)
    monkeypatch.setattr(checks, "CHECKS", (*checks.CHECKS, ghost))
    assert any("hc-ghost" in p and "no `due hc-ghost` line" in p
               for p in checks.tier_findings())


def test_an_owned_check_in_no_tier_is_caught(monkeypatch):
    orphan = checks.Check("hc-stow", "d", (checks.HEALTHCHECK, "--only", "hc-stow"),
                          frozenset({checks.GATE_MANUAL}), owner=checks.HEALTHCHECK)
    monkeypatch.setattr(checks, "CHECKS", (orphan,))
    assert any("in no tier" in p for p in checks.tier_findings())


def test_due_prints_the_tier_and_those_below_it():
    out = subprocess.run([sys.executable, str(HERE / "checks.py"), "--due", "weekly"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert "relay-status" in out and "updates" in out and "context-route" not in out


def test_tier_info_gives_period_stale_bound_and_unit():
    out = subprocess.run([sys.executable, str(HERE / "checks.py"), "--tier-info", "daily"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out == ["86400", "172800", "familiar-healthcheck-daily"]


def test_an_advisory_failure_does_not_fail_the_gate(monkeypatch, tmp_path):
    bad = checks.Check("bad", "d", (sys.executable, "-c", "raise SystemExit(3)"),
                       frozenset({checks.GATE_DAILY}), advisory="a reason that is five words")
    monkeypatch.setattr(checks, "CHECKS", (bad,))
    out = tmp_path / "r.json"
    assert checks.run_gate("daily", str(out)) == 0
    assert '"advisory": true' in out.read_text()


def test_a_real_failure_fails_the_gate(monkeypatch):
    bad = checks.Check("bad", "d", (sys.executable, "-c", "raise SystemExit(3)"),
                       frozenset({checks.GATE_DAILY}))
    monkeypatch.setattr(checks, "CHECKS", (bad,))
    assert checks.run_gate("daily") == 1


def test_an_unknown_effect_or_a_bare_advisory_is_refused():
    with pytest.raises(ValueError):
        checks.Check("x", "d", ("a",), frozenset(), effects=frozenset({"magic"}))
    with pytest.raises(ValueError):
        checks.Check("x", "d", ("a",), frozenset(), advisory="short")
