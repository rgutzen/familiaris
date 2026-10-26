"""The evaluation layer: the registry's contract, the two adapters, the review's
judgement, and the record (leaf system/checks/component-evaluation.md).

The adapters are fed fixtures, never the live logs: the claim under test is
what a reading says about a given window, not what this machine did this week.
"""
import datetime
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import evaluation  # noqa: E402
from orchestration import log  # noqa: E402

TODAY = datetime.date(2026, 10, 25)


def entry(**kw):
    e = {"kind": "mechanism", "owner": "dev", "question": "q?", "since": "2026-10-15",
         "design": "observational", "instrument": "labels", "source": "s",
         "metrics": ["uptake"], "lands": "dev", "review": "monthly"}
    e.update(kw)
    return e


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    return tmp_path


# --- the registry --------------------------------------------------------------

shipped = pytest.mark.skipif(not evaluation.REGISTRY.is_file(),
                             reason="a generated tree carries no registry (publish.yaml: omit)")


@shipped
def test_the_shipped_registry_holds():
    reg = evaluation.load()
    assert reg, "config/checks/components.yaml is missing or empty"
    assert evaluation.findings(reg) == []


@shipped
def test_the_shipped_registry_names_every_gap():
    reg = evaluation.load()
    gaps = {n for n, e in reg.items() if e["instrument"] == "none"}
    assert {"rtk", "skills-library", "deepen", "nightly-pass"} <= gaps
    assert {n for n, e in reg.items() if e["instrument"] != "none"} == {"delegation-nudge", "dispatch"}


@pytest.mark.parametrize("change, finding", [
    ({"metrics": ["accuracy"]}, "metric 'accuracy' is not in the vocabulary"),
    ({"design": "vibes"}, "design 'vibes'"),
    ({"kind": "plugin"}, "kind 'plugin'"),
    ({"instrument": "oracle"}, "instrument 'oracle' has no adapter"),
    ({"floors": ["first_pass >= 0.5"]}, "names a metric the entry does not declare"),
    ({"floors": ["uptake ~ 0.5"]}, "operator '~'"),
    ({"lands": "memory/no-such-leaf.md"}, "lands 'memory/no-such-leaf.md' does not exist"),
    ({"since": "last week"}, "since 'last week'"),
    ({"review": "daily"}, "review 'daily'"),
    ({"min_n": "0"}, "min_n must be at least 1"),
    ({"question": ""}, "missing `question`"),
    ({"floors": "uptake >= 0.5"}, "`floors` must be a block list"),
])
def test_a_broken_entry_is_named(change, finding):
    found = evaluation.findings({"x": entry(**change)})
    assert any(finding in f for f in found), found


def test_a_floor_parses_with_and_without_a_qualifier():
    assert evaluation.parse_floor("uptake >= 0.50") == evaluation.Floor("uptake", ">=", 0.5)
    assert evaluation.parse_floor("effect <= 0.5 late").qualifier == "late"
    with pytest.raises(ValueError):
        evaluation.parse_floor("uptake >= half")
    fl = evaluation.parse_floor("effect <= 0.5 late n>=150")
    assert (fl.qualifier, fl.min_n, str(fl)) == ("late", 150, "effect <= 0.5 late n>=150")
    for bad in ("uptake >= 0.5 n>=0", "uptake >= 0.5 n>=many"):
        with pytest.raises(ValueError):
            evaluation.parse_floor(bad)


def test_a_floors_own_n_holds_it_alone():
    rule = entry(metrics=["uptake", "effect"], min_n="10",
                 floors=["uptake >= 0.5", "effect <= 0.5 late n>=150"])
    j = evaluation.judge(rule, [r("uptake", 0.7, n=20), r("effect", 0.3, n=20, method="late")])
    assert [s for _, s, _, _ in j["floors"]] == ["PASS", "HELD"] and j["status"] == "HELD"
    assert "n 20 < min_n 150" in j["floors"][1][3]


def test_wilson_matches_the_plan_and_refuses_n_zero():
    assert evaluation.wilson(8, 12) == pytest.approx([0.3906, 0.8619], abs=1e-3)
    assert evaluation.wilson(0, 10)[1] == pytest.approx(0.2775, abs=1e-3)
    assert evaluation.wilson(0, 0) is None


def test_a_reading_refuses_an_undeclared_metric():
    with pytest.raises(ValueError):
        evaluation.reading("accuracy", 1, 1, method="m", gate=True, window={})


# --- adapter 1: the delegation window ------------------------------------------

def window(withheld=11):
    logs = [pathlib.Path(f"/s/2026-10-{d}T10-00-00-000Z_a.jsonl") for d in (16, 16, 22, 23)]
    rows = ([{"used": True, "compression": 12.0}] * 8 + [{"used": False, "compression": 4.0}] * 4
            + [{"used": None, "compression": 20.0}] * 56)
    return log.Window(since="2026-10-15", logs=logs, turns=300, fires=64, rows=rows,
                      arms={"nudged": [(1000, True)] * 25 + [(50000, False)] * 0,
                            "withheld": [(40000, False)] * withheld},
                      arm_fires=38, arm_sessions=60)


@pytest.fixture
def scanned(monkeypatch):
    got = {}

    def scan(since):
        got["since"] = since
        return window()
    monkeypatch.setattr(evaluation, "_report_window", scan)
    monkeypatch.setattr(evaluation, "log_day", lambda p: p.name[:10])
    return got


def test_report_turns_the_window_into_readings(scanned):
    rs = {(r["metric"], r["method"]): r
          for r in evaluation.report_readings("delegation-nudge", entry(since="2026-10-15"), TODAY)}
    up = rs[("uptake", "wilson95")]
    assert (up["value"], up["n"], up["n_all"]) == (pytest.approx(8 / 12), 12, 68)
    assert up["interval"] == pytest.approx([0.3906, 0.8619], abs=1e-3)
    assert up["gate"] is True                         # 64 fires >= 30
    assert rs[("compression", "median")]["value"] == 20.0
    late = rs[("effect", "late")]
    assert late["n"] == 11 and late["n_all"] == 36 and late["gate"] is True   # 60 sessions
    assert late["value"] is not None and late["window"]["since"] == "2026-10-22"
    assert rs[("exposure", "per-active-day")]["value"] == pytest.approx(64 / 3)
    assert scanned["since"] == "2026-10-15"


def test_report_says_why_an_effect_has_no_value(monkeypatch):
    monkeypatch.setattr(evaluation, "_report_window", lambda since: window(withheld=3))
    monkeypatch.setattr(evaluation, "log_day", lambda p: p.name[:10])
    late = next(r for r in evaluation.report_readings("d", entry(), TODAY) if r["method"] == "late")
    assert late["value"] is None and "needs 10 fires per arm" in late["note"]


def test_the_adapter_never_writes_the_reports_state(data, monkeypatch):
    """`report_main` rewrites report-last.json, which the weekly healthcheck's
    `report --check` compares against; the adapter must only scan."""
    monkeypatch.setattr(log, "scan", lambda since, *a, **k: window())
    monkeypatch.setattr(log, "report_main", lambda *a: pytest.fail("report_main was called"))
    monkeypatch.setattr(evaluation, "log_day", lambda p: p.name[:10])
    evaluation.report_readings("delegation-nudge", entry(), TODAY)
    assert not (data / log.STATE_NAME).exists()


# --- adapter 2: the labels ------------------------------------------------------

def label(model, passed, attempt=1, source="verify", verdict="own", ts="2026-10-20T10:00:00+00:00",
          tokens=1_000_000):
    return {"source": source, "ran_model": model, "passed": passed, "attempt": attempt,
            "verdict": verdict, "ts": ts,
            "usage": {"input": tokens, "output": 0, "cache_write": 0, "cache_read": 0}}


@pytest.fixture
def priced(monkeypatch):
    from orchestration import price
    monkeypatch.setattr(price, "block", lambda m: {} if "unpriced" in m else {"in": 1})
    monkeypatch.setattr(price, "cost", lambda block, usage, at=None: (usage["input"] / 1e6, 0.0))


def test_labels_price_each_verified_result(monkeypatch, priced):
    rows = [label("p/m1", True), label("p/m1", False), label("p/m1", True, attempt=2),
            label("p/m1", True, verdict="shared"),
            label("p/m1", True, source="eval"),                     # a campaign, not usage
            label("p/m1", True, ts="2026-10-01T00:00:00+00:00"),    # before `since`
            label("unpriced-model", True), label("p/m1", True, tokens=0)]
    monkeypatch.setattr(evaluation, "_labels", lambda: rows)
    got = evaluation.labels_readings("dispatch", entry(since="2026-10-15", min_n="3"), TODAY)
    total = {r["metric"]: r for r in got if r["arm"] is None}
    # own first attempts: m1 pass, m1 fail, unpriced pass, zero-usage pass
    assert total["first_pass"]["value"] == pytest.approx(3 / 4) and total["first_pass"]["n"] == 4
    assert total["verified_share"]["value"] == pytest.approx(5 / 6)     # one shared of six
    usd = total["usd_per_verified"]
    assert usd["value"] == pytest.approx(3.0 / 2)    # $1 x 3 priced attempts / 2 passes
    assert "1 model not priced" in usd["note"] and "1 no usage recorded" in usd["note"]
    per = {(r["arm"], r["metric"]) for r in got}
    assert ("m1", "first_pass") in per and ("unpriced-model", "usd_per_verified") in per


def test_labels_no_pass_is_no_value_not_infinity(monkeypatch, priced):
    monkeypatch.setattr(evaluation, "_labels", lambda: [label("p/m1", False)])
    usd = next(r for r in evaluation.labels_readings("d", entry(), TODAY)
               if r["metric"] == "usd_per_verified" and r["arm"] is None)
    assert usd["value"] is None and usd["gate"] is False


# --- the review's judgement ----------------------------------------------------

def r(metric, value, n=40, gate=True, method="m", arm=None, n_all=None):
    return {"metric": metric, "value": value, "n": n, "gate": gate, "method": method,
            "arm": arm, "n_all": n_all, "note": ""}


def test_judge_states():
    rule = entry(metrics=["uptake", "effect"], floors=["uptake >= 0.5", "effect <= 0.5 late"],
                 min_n="10")
    assert evaluation.judge(entry(instrument="none"), [])["status"] == "GAP"
    assert evaluation.judge(rule, [])["status"] == "NEVER READ"
    assert evaluation.judge(entry(), [r("uptake", 0.9)])["status"] == "NO RULE"
    keep = [r("uptake", 0.6), r("effect", 0.3, method="late"), r("effect", 0.9, method="itt")]
    assert evaluation.judge(rule, keep)["status"] == "READABLE: proposed keep"
    fail = [r("uptake", 0.4), r("effect", 0.3, method="late")]
    assert evaluation.judge(rule, fail)["status"] == "READABLE: proposed change or drop"
    for held in ([r("uptake", 0.6, gate=False), r("effect", 0.3, method="late")],
                 [r("uptake", 0.6, n=5), r("effect", 0.3, method="late")],
                 [r("uptake", 0.6), r("effect", None, method="late")],
                 [r("uptake", 0.6)]):
        assert evaluation.judge(rule, held)["status"] == "HELD"


def test_a_floor_reads_the_total_not_a_per_model_arm():
    rule = entry(metrics=["first_pass"], floors=["first_pass >= 0.8"], min_n="1")
    rows = [r("first_pass", 0.2, arm="m1"), r("first_pass", 0.9)]
    assert evaluation.judge(rule, rows)["status"] == "READABLE: proposed keep"


def test_a_malformed_floor_is_held_not_raised():
    j = evaluation.judge(entry(floors=["uptake ~ 0.5"]), [r("uptake", 0.9)])
    assert j["status"] == "HELD" and "operator '~'" in j["floors"][0][3]


def test_coverage_is_flagged_below_the_share():
    j = evaluation.judge(entry(), [r("uptake", 0.67, n=12, n_all=68)])
    assert j["coverage"] == (pytest.approx(12 / 68), 12, 68)
    assert evaluation.judge(entry(), [r("uptake", 0.67, n=60, n_all=68)])["coverage"] is None


# --- the record: read, review, verdict -----------------------------------------

def reg_one(instrument="fake"):
    return {"x": entry(instrument=instrument, metrics=["uptake"], floors=["uptake >= 0.5"],
                       min_n="1")}


def test_read_appends_one_stamped_batch_and_dry_run_writes_nothing(data, monkeypatch, capsys):
    monkeypatch.setattr(evaluation, "load", lambda: reg_one())
    monkeypatch.setitem(evaluation.ADAPTERS, "fake", lambda n, e, t: [
        evaluation.reading("uptake", 0.7, 20, method="wilson95", gate=True, window={})])
    assert evaluation.main(["read", "--dry-run"]) == 0
    assert not (data / evaluation.LEDGER).exists()
    assert evaluation.main(["read"]) == 0
    rows = [json.loads(x) for x in (data / evaluation.LEDGER).read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["kind"] == "reading" and rows[0]["component"] == "x"
    assert rows[0]["batch"] and rows[0]["registry"] == evaluation.registry_hash()


def test_a_failing_adapter_is_named_and_the_rest_still_read(data, monkeypatch, capsys):
    reg = {**reg_one("fake"), "y": entry(instrument="broken")}
    monkeypatch.setattr(evaluation, "load", lambda: reg)
    monkeypatch.setitem(evaluation.ADAPTERS, "fake", lambda n, e, t: [
        evaluation.reading("uptake", 0.7, 20, method="m", gate=True, window={})])

    def broken(n, e, t):
        raise OSError("no log")
    monkeypatch.setitem(evaluation.ADAPTERS, "broken", broken)
    assert evaluation.main(["read"]) == 1
    assert "y: the adapter failed: OSError: no log" in capsys.readouterr().err
    assert len((data / evaluation.LEDGER).read_text().splitlines()) == 1


def test_a_registry_that_does_not_parse_exits_1(data, monkeypatch, capsys):
    bad = data / "components.yaml"
    bad.write_text("components:\n  x:\n    metrics: [uptake]\n", encoding="utf-8")
    real = evaluation.load
    monkeypatch.setattr(evaluation, "load", lambda: real(bad))
    assert evaluation.main(["list", "--check"]) == 1
    assert "flow collections" in capsys.readouterr().err


def test_a_non_mapping_entry_neither_stops_read_nor_review(data, monkeypatch, capsys):
    reg = {**reg_one("fake"), "y": "oops"}
    monkeypatch.setattr(evaluation, "load", lambda: reg)
    monkeypatch.setitem(evaluation.ADAPTERS, "fake", lambda n, e, t: [
        evaluation.reading("uptake", 0.7, 20, method="m", gate=True, window={})])
    assert evaluation.main(["read"]) == 1
    assert "y: the adapter failed: not a mapping" in capsys.readouterr().err
    assert evaluation.main(["review"]) == 0


def test_verdict_lands_in_the_ledger_and_as_a_decision(data, monkeypatch, capsys):
    monkeypatch.setattr(evaluation, "load", lambda: reg_one())
    monkeypatch.setitem(evaluation.ADAPTERS, "fake", lambda n, e, t: [
        evaluation.reading("uptake", 0.7, 20, method="m", gate=True, window={})])
    evaluation.main(["read"])
    assert evaluation.main(["verdict", "x", "keep", "--why", "floors pass"]) == 0
    out = capsys.readouterr().out
    assert "| x | **keep**" in out
    rows = [json.loads(x) for x in (data / evaluation.LEDGER).read_text().splitlines()]
    v = rows[-1]
    assert v["kind"] == "verdict" and v["verdict"] == "keep" and v["readings"]
    decisions = [json.loads(x) for x in (data / "decisions.jsonl").read_text().splitlines()]
    assert decisions[-1]["id"] == v["decision"] and "x: keep" in decisions[-1]["text"]
    assert evaluation.main(["verdict", "nope", "keep", "--why", "w"]) == 2


def test_review_proposes_then_shows_the_verdict_and_its_expiry(data, monkeypatch):
    reg = reg_one()
    rows = [{"kind": "reading", "batch": "2026-10-20T00:00:00+00:00", "component": "x",
             **r("uptake", 0.7, n=20)}]
    rep = evaluation.review(reg, rows, TODAY, out=lambda *_: None)
    assert rep[0]["status"] == "READABLE: proposed keep" and rep[0]["due"] == "a verdict is due"
    rows.append({"kind": "verdict", "ts": "2026-07-01T00:00:00+00:00", "component": "x",
                 "verdict": "keep", "review_by": "2026-10-01"})
    rep = evaluation.review(reg, rows, TODAY, out=lambda *_: None)
    assert rep[0]["verdict"] == "keep" and "past review_by" in rep[0]["due"]


def test_review_reads_only_the_newest_batch():
    rows = [{"kind": "reading", "batch": "2026-10-01", "component": "x", **r("uptake", 0.1)},
            {"kind": "reading", "batch": "2026-10-20", "component": "x", **r("uptake", 0.9)}]
    assert [x["value"] for x in evaluation.newest(rows, "x", "reading")] == [0.9]
