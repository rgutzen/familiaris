"""Every `familiar` check mode is in the registry, or excluded with a reason.

This is the test that keeps the registry equal to the route table. Ten check
modes were added to `engine/familiar` over a few sessions and none to
`checks.py`; no gate ran them and nothing said so. Now a route that gains a
`--check` fails here, on the commit that adds it.

The first test is the real one. The rest prove the test can fail: a coverage
check that cannot go red is the thing it was written to replace.
"""
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import checks  # noqa: E402
import check_coverage as coverage  # noqa: E402


def test_every_check_mode_is_registered_or_excluded():
    assert coverage.findings() == []


def test_the_discovery_finds_the_modes_the_task_named():
    found = {(s, v, m) for (s, v), modes in coverage.discovered(coverage.front_door().ROUTES).items()
             for m in modes}
    for expect in [("context", "loadout", "--check"), ("context", "links", "--check"),
                   ("context", "tree", "--check"), ("skills", "scan", "--check"),
                   ("skills", "index", "--check"), ("orchestration", "scout", "--check"),
                   ("orchestration", "models", "--check"), ("orchestration", "dispatch", "--gate"),
                   ("relay", "status", "--check"), ("schedule", "sessions", "--check"),
                   ("checks", "updates", "--check")]:
        assert expect in found, expect


def _routes(**verbs):
    return {"fake": {verb: ("py", "cli.updates:main", "", "argv", "x") for verb in verbs}}


def test_a_new_check_mode_with_no_entry_is_a_finding(monkeypatch):
    monkeypatch.setattr(coverage, "_flags_of", lambda route, verb: {"--check"})
    problems = coverage.findings(_routes(drift=1), registry=())
    assert any("familiar fake drift --check" in p and "no registry entry" in p for p in problems)


def test_an_entry_clears_it(monkeypatch):
    monkeypatch.setattr(coverage, "_flags_of", lambda route, verb: {"--check"})
    entry = checks.Check("fake-drift", "d", ("engine/familiar", "fake", "drift", "--check"),
                         frozenset({checks.GATE_DAILY}))
    assert not [p for p in coverage.findings(_routes(drift=1), registry=(entry,))
                if "fake drift" in p]


def test_an_exclusion_for_a_mode_that_is_gone_is_a_finding(monkeypatch):
    monkeypatch.setitem(coverage.NOT_REGISTERED, ("fake", "gone", "--check"),
                        "a reason that is a reason")
    assert any("NOT_REGISTERED names" in p for p in coverage.findings())


def test_an_entry_running_a_verb_that_is_not_a_route_is_a_finding():
    entry = checks.Check("ghost", "d", ("engine/familiar", "checks", "ghost", "--check"),
                         frozenset({checks.GATE_DAILY}))
    assert any("ghost" in p and "not a route" in p
               for p in coverage.findings(registry=(*checks.CHECKS, entry)))


def test_a_declared_word_mode_that_left_the_usage_is_a_finding(monkeypatch):
    monkeypatch.setitem(coverage.VERB_MODES, ("harness", "jev"), ("vanished",))
    assert any("vanished" in p for p in coverage.findings())
