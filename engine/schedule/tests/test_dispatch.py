"""the dispatcher (dev/schedule 1d): one tick decides what runs.

The tick replaces nine-and-counting per-job clocks with one decision every five
minutes. What must hold: a job starts only when it is due AND its start
conditions are clear; a hold, a run in flight or a run just dispatched keeps it
back; the lowest priority goes first and only one starts per tick; a backstop is
applied to the runs in flight; and a 9a record keeps being fired by its own unit.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from schedule import conditions as C
from schedule import dispatch, sessions


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units")}


@pytest.fixture
def prompt(tmp_path):
    path = tmp_path / "handoff.md"
    path.write_text("do it\n")
    return path


# The next whole minute: after every job a test adds (their `created` is the real
# clock), and on a minute boundary, as the timer's `*:0/5` is.
NOW = (sessions.now_local() + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)


def later(**kw):
    return NOW + dt.timedelta(**kw)


def add(env, prompt, name, *when, extra=()):
    a = sessions._parser().parse_args(
        ["add", "--name", name, *(when or ("--ready",)), "--prompt", str(prompt),
         "--model", "deepseek-flash", "--cwd", str(prompt.parent), *extra])
    assert sessions.cmd_add(a, env=env) == 0
    d = sessions.session_dir(name, env)
    return d, json.loads((d / "schedule.json").read_text())


def ctx_for(env, now=NOW, procs=(), five=0.1):
    policy = sessions.load_policy()
    policy["conditions"]["conflict"]["processes"] = {}
    return C.Context(policy, env=env, now=now, procs=lambda: list(procs),
                     probe=lambda a: {"limits": [{"label": "Session (5-hour)", "percent": five,
                                                  "resetsAt": later(hours=3).isoformat()}]},
                     tty_seen=lambda tty: None, clock=lambda: now.timestamp())


class Starter:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def __call__(self, d, decl):
        self.calls.append(decl["name"])
        return {"unit": f"familiar-run-{decl['name']}-x", "ok": self.ok,
                "error": "" if self.ok else "Failed to start"}


def tick(env, now=NOW, start=None, ctx=None, **kw):
    start = start or Starter()
    row = dispatch.tick(env, now=now, ctx=ctx or ctx_for(env, now), start=start, **kw)
    return row, start


def events_of(d, kind):
    return [e for e in sessions.read_events(d) if e.get("event") == kind]


# --- who starts -----------------------------------------------------------------

def test_a_due_job_with_clear_conditions_is_started_and_the_tick_is_logged(env, prompt):
    d, _ = add(env, prompt, "job")
    row, start = tick(env)
    assert start.calls == ["job"] and row["started"] == "job"
    assert events_of(d, "dispatched")[0]["unit"] == "familiar-run-job-x"
    logged = (sessions.data_root(env) / dispatch.LOG).read_text().splitlines()
    assert json.loads(logged[-1])["started"] == "job"


def test_a_job_not_yet_due_or_still_held_is_not_started(env, prompt):
    add(env, prompt, "future", "--in", "2h")
    d, _ = add(env, prompt, "held")
    sessions.write_event(d, {"event": "held", "ts": NOW.isoformat(),
                             "until": later(hours=1).isoformat(), "why": "test"})
    row, start = tick(env)
    assert start.calls == []
    assert row["jobs"]["future"].startswith("next at")
    assert row["jobs"]["held"].startswith("next at")
    _, start = tick(env, now=later(hours=1, minutes=1))
    assert start.calls == ["held"]


def test_a_start_condition_defers_the_job_and_records_it_once(env, prompt):
    d, _ = add(env, prompt, "job")
    busy = [C.Proc(11, 1, "pi", 34818, "pi")]
    for _ in range(3):
        row, start = tick(env, ctx=ctx_for(env, procs=busy))
        assert start.calls == [] and "user_active" in row["jobs"]["job"]
    assert len(events_of(d, "deferred")) == 1, "a night of ticks is not a night of rows"
    nightly = ctx_for(env)                                     # another reason: a conflict
    nightly.policy["conditions"]["conflict"]["processes"] = {
        "nightly": {"at": NOW.strftime("%H:%M"), "trees": [str(prompt.parent)], "lead": "30m"}}
    _, start = tick(env, ctx=nightly)
    assert len(events_of(d, "deferred")) == 2 and start.calls == []


def test_the_lowest_priority_starts_first_and_only_one_per_tick(env, prompt):
    add(env, prompt, "late", extra=("--priority", "90"))
    add(env, prompt, "urgent", extra=("--priority", "1"))
    add(env, prompt, "normal")
    row, start = tick(env)
    assert start.calls == ["urgent"]
    assert "goes first" in row["jobs"]["late"] and "goes first" in row["jobs"]["normal"]


def test_a_run_just_dispatched_or_in_flight_keeps_every_job_back(env, prompt):
    da, _ = add(env, prompt, "a", extra=("--priority", "1"))
    add(env, prompt, "b")
    _, start = tick(env)
    assert start.calls == ["a"]
    row, start = tick(env, now=later(minutes=5))              # a has not taken its lock yet
    assert start.calls == [] and row["jobs"]["a"] == "starting"
    assert "in flight" in row["jobs"]["b"]
    sessions.write_event(da, {"event": "started", "ts": later(minutes=6).isoformat()})
    with sessions.RunLock(da):
        row, start = tick(env, now=later(minutes=10))
    assert start.calls == [] and row["jobs"]["a"] == "running"


# --- when a job is due ----------------------------------------------------------

def test_a_one_off_is_done_after_a_run_the_window_let_through(env, prompt):
    d, decl = add(env, prompt, "once")
    refused = [{"event": "started", "ts": NOW.isoformat()},
               {"event": "finished", "ts": NOW.isoformat(), "exit": 1, "window_refused": True}]
    assert dispatch.next_due(decl, refused, NOW)[0] is not None, "a refusal is retried"
    ok = refused + [{"event": "started", "ts": NOW.isoformat()},
                    {"event": "finished", "ts": NOW.isoformat(), "exit": 1}]
    when, why = dispatch.next_due(decl, ok, NOW)
    assert when is None and why == "done (exit 1)", "a failed run is not repeated blindly"
    crashed = [{"event": "crashed", "ts": NOW.isoformat(), "error": "x"}]
    assert dispatch.next_due(decl, crashed, NOW)[0] is None


def test_every_is_a_period_from_the_last_start(env, prompt):
    _, decl = add(env, prompt, "rep", "--every", "5h")
    assert dispatch.next_due(decl, [], NOW)[0] <= NOW, "the first run is the next tick"
    events = [{"event": "started", "ts": (NOW - dt.timedelta(hours=4)).isoformat()}]
    when, _ = dispatch.next_due(decl, events, NOW)
    assert when == NOW + dt.timedelta(hours=1)


def test_a_refusal_with_no_hold_backs_off_instead_of_refusing_every_tick(env, prompt):
    _, decl = add(env, prompt, "dirty")
    events = [{"event": "refused", "ts": NOW.isoformat(), "reason": "dirty tree"}]
    when, _ = dispatch.next_due(decl, events, NOW)
    assert when == NOW + dt.timedelta(minutes=30)


def test_a_9a_record_is_left_to_its_own_unit(env, prompt, legacy):
    legacy(env, prompt, name="old")
    row, start = tick(env, now=later(hours=1))
    assert start.calls == [] and "old" not in row["jobs"]


def test_a_failed_start_is_a_refusal_on_the_record(env, prompt):
    d, _ = add(env, prompt, "job")
    row, _ = tick(env, start=Starter(ok=False))
    assert row["started"] is None and "start failed" in row["jobs"]["job"]
    assert "systemd-run" in events_of(d, "refused")[0]["reason"]


# --- backstops, the lock, the start itself ---------------------------------------

def test_a_backstop_that_is_due_interrupts_the_run_in_flight(env, prompt, tmp_path):
    d, decl = add(env, prompt, "job")
    policy = sessions.load_policy()
    policy["conditions"]["conflict"]["processes"] = {
        "nightly": {"at": NOW.strftime("%H:%M"), "trees": [str(tmp_path)], "lead": "30m"}}
    ctx = C.Context(policy, env=env, now=NOW, procs=lambda: [],
                    probe=lambda a: {"limits": []}, tty_seen=lambda t: None)
    hits = []
    with sessions.RunLock(d):
        row = dispatch.tick(env, now=NOW, ctx=ctx, start=Starter(),
                            interrupt=lambda d_, decl_, v: hits.append(v))
    assert hits and hits[0]["condition"] == "conflict" and hits[0]["pid"] == os.getpid()
    assert row["backstops"][0]["job"] == "job"


def test_two_ticks_at_once_do_not_both_decide(env, prompt):
    add(env, prompt, "job")
    with dispatch.TickLock(env):
        row, start = tick(env)
    assert row.get("skipped") and start.calls == []


def test_a_dry_run_decides_and_starts_nothing(env, prompt):
    d, _ = add(env, prompt, "job")
    row, start = tick(env, dry_run=True)
    assert start.calls == [] and row["jobs"]["job"] == "would start"
    assert sessions.read_events(d) == []


def test_the_run_starts_as_its_own_transient_service(env, prompt):
    d, decl = add(env, prompt, "job")
    seen = []

    def run(argv, **kw):
        seen.append(argv)
        return type("P", (), {"returncode": 0, "stderr": ""})()

    got = dispatch.start_detached(d, decl, run=run)
    argv = seen[0]
    assert argv[:3] == ["systemd-run", "--user", "--quiet"] and "--collect" in argv
    assert f"--unit={got['unit']}" in argv and got["unit"].startswith("familiar-run-job-")
    assert argv[-1] == decl["wrapper"], "the wrapper sources the keys, then calls run"
