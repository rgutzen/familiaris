"""route (14g): lowest expected cost per verified result, a floor, bounded exploration.

WHAT IS PINNED.
  the quantity  E = cost of one attempt / P(verified), so a dearer model that
                passes more often can be the cheaper verified result.
  the floor     the greedy pick needs its lower bound at the floor; none passing
                ranks everyone and says so.
  exploration   a Thompson draw over members whose mean reaches the floor; the
                week's exploring spend stops it at the cap; every choice is a line.
  the shadow    `route_live: no` keeps the 14c price order exactly.
  the cascade   `model: class` in a class with a free checker runs the next option
                once when the answer fails the check, and prints the one that passed.
"""
import datetime
import importlib.machinery
import importlib.util
import json
import pathlib
import random

import pytest

from orchestration import costs, models, posterior as P, profiles, selection

CAT = {"models": [
    {"id": "cheap", "pool": "usd", "cost": {"in": "1", "out": "1"}},
    {"id": "dear", "pool": "usd", "cost": {"in": "3", "out": "3"}},
    {"id": "new", "pool": "usd", "cost": {"in": "0.5", "out": "0.5"}}]}
RULES = {"reference_usage": {"default": {"input": 1_000_000, "output": 0}},
         "route_floor": 0.5, "explore_budget": 1.0, "route_live": "yes"}
TIER = {"models": "cheap, dear", "_class": "edit", "_needs": []}
NOW = datetime.datetime(2026, 10, 22, 12, tzinfo=datetime.timezone.utc)


@pytest.fixture(autouse=True)
def _no_capabilities(monkeypatch):
    monkeypatch.setattr(P, "capability_pct", lambda *a: None)
    monkeypatch.setattr(models, "capability_scores", lambda *a: {})


def evidence(record):
    """`record`: {model: (successes, failures)} in class edit, effort default."""
    obs = [P.Outcome(m, "", "edit", ok, "label")
           for m, (s, f) in record.items() for ok in [True] * s + [False] * f]
    return costs.fit([]), obs


def test_route_a_dearer_model_that_passes_is_the_cheaper_verified_result():
    data = evidence({"cheap": (2, 8), "dear": (10, 0)})
    ids, why, choice = selection.route(CAT, {}, TIER, RULES, data=data)
    assert ids == ["dear", "cheap"], "$1 at P~0.3 is dearer than $3 at P~0.9 per verified result"
    by = {o["id"]: o for o in choice["options"]}
    assert by["cheap"]["e"] == pytest.approx(by["cheap"]["usd"] / by["cheap"]["mean"], rel=1e-5)
    assert choice["pick"] == choice["greedy"] == "dear" and not choice["explored"]


def test_route_the_floor_filters_the_greedy_pick_and_never_empties_the_tier():
    data = evidence({"cheap": (1, 2), "dear": (12, 0)})
    ids, why, _c = selection.route(CAT, {}, TIER, dict(RULES, route_floor=0.0), data=data)
    assert ids[0] == "cheap", "no floor: $1 at P 0.61 beats $3 at P 0.96"
    ids, why, _c = selection.route(CAT, {}, TIER, dict(RULES, route_floor=0.8), data=data)
    assert ids[0] == "dear", "1 of 3 leaves cheap's lower bound at 0.38, under the floor"
    ids, why, _c = selection.route(CAT, {}, TIER, dict(RULES, route_floor=0.99), data=data)
    assert ids and "all ranked" in why


def test_route_explores_by_drawing_and_records_the_choice(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    tier = dict(TIER, models="cheap, new")
    # cheap: 6 of 12 (mean 0.50, lower 0.34); new: no record (mean 0.50, lower 0.20).
    # At floor 0.3 only cheap may be the greedy pick; both may be drawn.
    data = evidence({"cheap": (6, 6)})
    picks = set()
    for seed in range(40):
        ids, why, c = selection.route(CAT, {}, tier, dict(RULES, route_floor=0.3), data=data,
                                      explore=True, record=True, rng=random.Random(seed),
                                      now=NOW)
        picks.add(c["pick"])
        assert c["greedy"] == "cheap"
    assert picks == {"cheap", "new"}, "the unjudged half-price member is drawn some of the time"
    rows = [json.loads(l) for l in (tmp_path / "route.jsonl").read_text().splitlines()]
    assert len(rows) == 40 and all(r["explored"] == (r["pick"] != r["greedy"]) for r in rows)
    assert selection.explored_spend(NOW, tmp_path / "route.jsonl") == pytest.approx(
        sum(r["usd"] for r in rows if r["explored"]))


def test_route_exploration_pauses_at_the_weekly_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    log = tmp_path / "route.jsonl"
    old = (NOW - datetime.timedelta(days=8)).isoformat()
    log.write_text(json.dumps({"ts": NOW.isoformat(), "explored": True, "usd": 0.7}) + "\n"
                   + json.dumps({"ts": old, "explored": True, "usd": 5}) + "\n")
    assert selection.explored_spend(NOW, log) == pytest.approx(0.7), "eight days ago is out"
    data = evidence({"cheap": (6, 6)})
    _ids, why, c = selection.route(CAT, {}, dict(TIER, models="cheap, new"),
                                   dict(RULES, explore_budget=0.5, route_floor=0.3), data=data,
                                   explore=True, now=NOW)
    assert not c["explored"] and "exploration paused: $0.70 of $0.50" in why


def test_route_the_shadow_keeps_the_price_order_exactly():
    data = evidence({"cheap": (2, 8), "dear": (10, 0)})
    off = dict(RULES, route_live="no")
    selection._EVIDENCE[str(profiles.data_dir())] = data       # what `evidence()` caches
    try:
        assert selection.cheapest(CAT, {}, TIER, off)[0] == ["cheap", "dear"]
        assert selection.cheapest(CAT, {}, TIER, RULES)[0] == ["dear", "cheap"]
    finally:
        selection._EVIDENCE.clear()


# --- the cascade ---------------------------------------------------------------

PATH = pathlib.Path(__file__).resolve().parents[1] / "pi-agent"


@pytest.fixture
def pi_agent(monkeypatch, tmp_path):
    loader = importlib.machinery.SourceFileLoader("pi_agent_route_test", str(PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    monkeypatch.delenv("PI_PROFILE", raising=False)
    return mod


def test_route_a_failed_check_runs_the_next_option_once(pi_agent, monkeypatch, tmp_path,
                                                        capsys):
    src = tmp_path / "a.py"
    src.write_text("x = 1\ny = 2\n")
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "class"
    monkeypatch.setattr(pi_agent, "class_route", lambda a, **kw: (
        [("claude-haiku-5-5", "low"), ("deepseek-flash", "low")], "read tier 1",
        {"cascade": {"read": "ref+quote"}}))
    monkeypatch.setattr(pi_agent, "pi_model", lambda m: (f"p/{m}", m))
    answers = {"claude-haiku-5-5": 'a.py:9 "nothing here"\n', "deepseek-flash": 'a.py:2 "y = 2"\n'}
    ran = []

    def spawn(agent, task, cwd, timeout, resolved, level, session, parent, log,
              capture=False, defer=False):
        mid = resolved.split("/", 1)[1]
        ran.append((mid, session, capture, defer))
        return 0, answers[mid]
    lines = []
    monkeypatch.setattr(pi_agent, "spawn", spawn)
    monkeypatch.setattr(pi_agent, "record", lambda role, sid, code, parent=None, write=True:
                        lines.append(sid))
    assert pi_agent.run(agent, "find y", str(tmp_path), 10, None, "h", None) == 0
    out = capsys.readouterr()
    assert [m for m, *_ in ran] == ["claude-haiku-5-5", "deepseek-flash"]
    assert ran[0][1] != ran[1][1], "each step is its own child session"
    assert all(d for *_, d in ran), "the cascade writes the line itself"
    assert out.out == 'a.py:2 "y = 2"\n' and "failed `ref+quote`" in out.err
    assert lines == [str(pi_agent.uuid.uuid5(pi_agent.NS, "explore:h:2"))], \
        "one delegation line, for the step whose answer the parent reads"
    rows = [json.loads(l) for l in (tmp_path / "pazras-data" / "cascade.jsonl")
            .read_text().splitlines()]
    assert [(r["model"], r["class"], r["ok"]) for r in rows] == [
        ("claude-haiku-5-5", "read", False), ("deepseek-flash", "read", True)]
    obs = P.outcomes(tmp_path / "pazras-data")
    assert [(o.model, o.ok, o.source) for o in obs] == [
        ("claude-haiku-5-5", False, "cascade"), ("deepseek-flash", True, "cascade")]


def test_route_a_class_without_a_checker_runs_one_child_and_inherits_its_output(
        pi_agent, monkeypatch, tmp_path):
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "class"
    monkeypatch.setattr(pi_agent, "class_route", lambda a, **kw: (
        [("claude-haiku-5-5", "low"), ("deepseek-flash", "low")], "read tier 1", {}))
    monkeypatch.setattr(pi_agent, "pi_model", lambda m: (f"p/{m}", m))
    ran = []
    monkeypatch.setattr(pi_agent, "spawn", lambda *a, capture=False, defer=False, **k:
                        ran.append(capture) or (0, ""))
    assert pi_agent.run(agent, "find y", str(tmp_path), 10, None, "h", None) == 0
    assert ran == [False]
