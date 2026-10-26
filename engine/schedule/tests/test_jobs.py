"""the job model (dev/schedule 1a): a retry and a repeat are runs of ONE job.

WHY THESE PROPERTIES. 9a re-declared every refused run as `<root>-r<N>`: the cap
counted every retry ever made (PLAN defect 4), the retry had its own lock and so
could run beside the next anchor in the same repository (5), it waited a blind
+30 m though the refusal named its reset time (6), a lock refusal left no trace
(7), and a chain could not end itself because `cancel` saw its own run's lock (3).
Each test below holds one of those removals.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess

import pytest

from schedule import sessions


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")


class Done:
    def __init__(self, code=0):
        self.returncode, self.stdout, self.stderr = code, "", ""


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units")}


@pytest.fixture
def prompt(tmp_path):
    path = tmp_path / "handoff.md"
    path.write_text("# A handoff\n\nRead this, do the thing.\n")
    return path


@pytest.fixture
def calls():
    return []


@pytest.fixture
def run(calls):
    """The renderer runs for real (it writes into the test's unit directory);
    systemctl is recorded, never called."""
    def run(argv, **kw):
        if argv[0] == "bash":
            return subprocess.run(argv, **kw)
        calls.append(" ".join(argv))
        return Done(0)
    return run


def args_for(*argv):
    return sessions._parser().parse_args(list(argv))


def add(env, prompt, *when, name="job", cwd=None, extra=()):
    a = args_for("add", "--name", name, *(when or ("--in", "10m")), "--prompt", str(prompt),
                 "--model", "deepseek-flash", "--no-systemctl",
                 *(("--cwd", str(cwd)) if cwd else ()), *extra)
    assert sessions.cmd_add(a, env=env) == 0
    d = sessions.session_dir(name, env)
    return d, json.loads((d / "schedule.json").read_text())


def driver_saying(message, code=1):
    def driver(argv, prompt, *, cwd, log, **kw):
        log.write(message + "\n")
        return {"exit": code}
    return driver


DENIED = driver_saying("You've hit your session limit · resets 1:40am (Europe/Berlin)")


def events_of(d, kind):
    return [e for e in sessions.read_events(d) if e.get("event") == kind]


# --- the declaration ----------------------------------------------------------

def test_add_records_the_job_fields_with_the_configured_defaults(env, prompt):
    defaults = sessions.load_config()
    _, decl = add(env, prompt)
    assert decl["trigger"] == "at" and decl["chain"] == "none"
    assert decl["priority"] == int(defaults["priority"])
    assert decl["start_when"] == defaults["start_when"]
    assert decl["stop_when"] == defaults["stop_when"] == ["user_active", "conflict"]
    _, rep = add(env, prompt, "--every", "5h", "--at", "01:35", name="rep",
                 extra=("--chain", "until-done", "--priority", "3"))
    assert (rep["trigger"], rep["chain"], rep["priority"], rep["kind"]) == \
        ("every", "until-done", 3, "chain")


def test_a_9a_record_is_read_as_at_or_every_and_never_a_chain():
    defaults = {"priority": "50", "start_when": ["budget"], "stop_when": ["user_active"]}
    once = sessions.job_of({"kind": "once", "due": "2026-10-15T00:31:22+02:00"}, defaults)
    rep = sessions.job_of({"kind": "repeat", "on_calendar": "*-*-* 01/5:35:00"}, defaults)
    assert (once["trigger"], once["chain"], once["priority"]) == ("at", "none", 50)
    assert rep["trigger"] == "every" and rep["chain"] == "none"
    assert once["start_when"] == ["budget"] and once["stop_when"] == ["user_active"]


def test_a_ready_job_has_no_unit_and_check_is_clean(env, prompt):
    d, decl = add(env, prompt, "--ready")
    assert decl["trigger"] == "ready" and decl["unit"] == "" and decl["due"] == ""
    assert not list(pathlib.Path(env["PAZRAS_SESSION_UNITS"]).glob("familiar-session-job.*"))
    assert sessions._state(decl, [], sessions.now_local())["state"] == "ready"
    assert sessions.cmd_check(args_for("check"), env=env) == 0
    with pytest.raises(sessions.SessionError):
        add(env, prompt, "--ready", "--every", "5h", name="both")


# --- a refusal holds the SAME job ----------------------------------------------

def test_reset_time_reads_the_refusals_own_clock_as_the_next_such_time():
    now = dt.datetime(2026, 10, 21, 0, 30, tzinfo=dt.timezone.utc)
    assert sessions.reset_time(["… resets 1:40am (Europe/Berlin)"], now) == \
        now.replace(hour=1, minute=40)
    assert sessions.reset_time(["resets 1:40:00 AM: You've hit your limit"], now) == \
        now.replace(hour=1, minute=40)
    # A time already passed today is tomorrow's.
    assert sessions.reset_time(["resets 00:10"], now) == \
        now.replace(hour=0, minute=10) + dt.timedelta(days=1)
    assert sessions.reset_time(["no clock here"], now) is None


def test_a_refused_window_holds_the_same_job_until_the_reset_plus_a_minute(
        env, prompt, monkeypatch, run, calls):
    d, _ = add(env, prompt, name="chain")
    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    assert sessions.cmd_run(args_for("run", "chain"), env=env, driver=DENIED,
                            dirty=[], run=run) == 1
    held = events_of(d, "held")
    assert len(held) == 1 and held[0]["attempt"] == 1
    until = dt.datetime.fromisoformat(held[0]["until"])
    assert (until.hour, until.minute) == (1, 41), "the reset (1:40) + retry.after_reset (1m)"
    # No second declaration: the retry is the same job (defects 4, 5).
    assert [p.name for p in sessions.data_root(env).iterdir() if p.name != "locks"] == ["chain"]
    assert "dispatcher" in held[0]["fires"] and calls == []
    decl = json.loads((d / "schedule.json").read_text())
    assert sessions._state(decl, sessions.read_events(d), sessions.now_local())["state"] == "held"
    assert sessions.cmd_check(args_for("check"), env=env) == 0


def test_a_9a_at_record_has_its_own_unit_moved_to_the_hold(env, prompt, run, calls, legacy):
    d, decl = legacy(env, prompt, name="old")
    until = sessions.now_local() + dt.timedelta(hours=2)
    sessions.hold(d, decl, until, "test", env=env, run=run)
    decl = json.loads((d / "schedule.json").read_text())
    timer = (pathlib.Path(env["PAZRAS_SESSION_UNITS"]) / "familiar-session-old.timer").read_text()
    assert decl["due"] == until.isoformat(timespec="seconds")
    assert f"OnCalendar={decl['on_calendar']}" in timer
    assert any("restart familiar-session-old.timer" in c for c in calls)
    assert sessions.cmd_check(args_for("check"), env=env) == 0


def test_a_held_job_refuses_an_early_start_with_an_event_unless_told(env, prompt):
    d, decl = add(env, prompt, "--every", "5h", "--at", "01:35", name="rep")
    later = sessions.now_local() + dt.timedelta(hours=2)
    sessions.write_event(d, {"event": "held", "ts": sessions.now_local().isoformat(),
                             "until": later.isoformat(), "why": "test"})
    assert sessions.cmd_run(args_for("run", "rep"), env=env, dirty=[],
                            driver=driver_saying("ok", 0)) == 2
    assert "held until" in events_of(d, "refused")[-1]["reason"]
    assert sessions.cmd_run(args_for("run", "rep", "--ignore-hold"), env=env, dirty=[],
                            driver=driver_saying("ok", 0), run=lambda *a, **k: Done()) == 0
    assert sessions._state(decl, sessions.read_events(d), sessions.now_local())["state"] == "repeating", "an every job repeats after a run"


def test_without_a_reset_time_the_hold_is_the_configured_fallback(env, prompt, monkeypatch, run):
    d, _ = add(env, prompt, name="chain")
    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    before = sessions.now_local()
    sessions.cmd_run(args_for("run", "chain"), env=env, dirty=[], run=run,
                     driver=driver_saying("HTTP 429 rate limit"))
    held = events_of(d, "held")[0]
    wait = dt.datetime.fromisoformat(held["until"]) - before
    assert dt.timedelta(minutes=29) < wait < dt.timedelta(minutes=31)
    assert "no reset time" in held["why"]


def test_a_refused_run_that_changed_anything_is_not_held(env, prompt, monkeypatch, run):
    d, _ = add(env, prompt, name="chain")
    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: ["docs/touched.md"])
    assert sessions.cmd_run(args_for("run", "chain"), env=env, driver=DENIED,
                            dirty=[], run=run) == 1
    assert events_of(d, "held") == []


def test_the_cap_counts_holds_in_a_row_and_a_run_that_got_through_resets_it(
        env, prompt, run):
    d, decl = add(env, prompt, name="chain")
    cap = int(sessions.load_policy()["retry"]["max"])
    until = sessions.now_local() + dt.timedelta(hours=1)
    for _ in range(cap):
        assert sessions.hold(d, decl, until, "test", env=env, run=run) is not None
    assert sessions.hold(d, decl, until, "test", env=env, run=run) is None
    assert events_of(d, "retry_refused")[0]["cap"] == cap
    # Defect 4: a lifetime cap. A run the window let through starts the count over.
    sessions.write_event(d, {"event": "started", "ts": sessions.now_local().isoformat()})
    sessions.write_event(d, {"event": "finished", "ts": sessions.now_local().isoformat(),
                             "exit": 0, "window_refused": False})
    assert sessions.refusal_streak(sessions.read_events(d)) == 0
    assert sessions.hold(d, decl, until, "test", env=env, run=run) is not None


def test_a_9a_every_record_is_held_without_moving_its_anchors(env, prompt, run, calls,
                                                             legacy):
    d, decl = legacy(env, prompt, name="rep", kind="repeat")
    timer = pathlib.Path(env["PAZRAS_SESSION_UNITS"]) / "familiar-session-rep.timer"
    before = timer.read_text()
    sessions.hold(d, decl, sessions.now_local() + dt.timedelta(hours=1), "test",
                  env=env, run=run)
    assert timer.read_text() == before and calls == []
    assert "anchor" in events_of(d, "held")[0]["fires"]


# --- locks ---------------------------------------------------------------------

def test_a_job_lock_refusal_writes_an_event(env, prompt):
    d, _ = add(env, prompt)
    with sessions.RunLock(d):
        with pytest.raises(sessions.SessionError, match="already in flight"):
            sessions.cmd_run(args_for("run", "job"), env=env, dirty=[],
                             driver=driver_saying("ok", 0))
    refused = events_of(d, "refused")
    assert refused and refused[-1]["lock"] == "job"
    assert events_of(d, "started") == []


def test_two_jobs_in_one_working_directory_do_not_run_together(env, prompt, tmp_path, run):
    """Defect 5: a retry ran beside the next anchor in the same repository."""
    da, _ = add(env, prompt, name="a", cwd=tmp_path)
    db, _ = add(env, prompt, name="b", cwd=tmp_path)
    with sessions.cwd_lock(tmp_path, env, label="a"):
        with pytest.raises(sessions.SessionError, match="working directory"):
            sessions.cmd_run(args_for("run", "b"), env=env, dirty=[], run=run,
                             driver=driver_saying("ok", 0))
    assert events_of(db, "refused")[-1]["lock"] == "cwd"
    assert events_of(db, "held"), "the refused job is held, so it runs once the directory frees"
    assert events_of(db, "started") == []
    # A different directory is not blocked.
    dc, _ = add(env, prompt, name="c", cwd=tmp_path / "..")
    with sessions.cwd_lock(tmp_path, env, label="a"):
        assert sessions.cmd_run(args_for("run", "c"), env=env, dirty=[], run=run,
                                driver=driver_saying("ok", 0)) == 0


def test_a_refused_attempt_keeps_the_holders_pid_in_the_lock_file(tmp_path):
    with sessions.RunLock(tmp_path) as lock:
        with pytest.raises(sessions.SessionError):
            sessions.RunLock(tmp_path).__enter__()
        assert lock.holder() == os.getpid()


# --- a chain ends itself ---------------------------------------------------------

def test_cancel_from_inside_the_jobs_own_run_ends_the_job(env, prompt, run):
    """Defect 3: `cancel` from inside a run saw its own lock and refused."""
    d, decl = add(env, prompt)
    with sessions.RunLock(d):
        code = sessions.cmd_cancel(args_for("cancel", "job", "--no-systemctl"), env=env,
                                   lineage=lambda: [12345, os.getpid()])
    assert code == 0
    decl = json.loads((d / "schedule.json").read_text())
    assert decl["ended"] and not decl.get("cancelled")
    assert events_of(d, "ended")[0]["why"].startswith("cancel from inside")
    assert sessions._state(decl, sessions.read_events(d), sessions.now_local())["state"] == "ended"
    assert not list(pathlib.Path(env["PAZRAS_SESSION_UNITS"]).glob("familiar-session-job.*"))
    assert sessions.cmd_check(args_for("check"), env=env) == 0
    with pytest.raises(sessions.SessionError, match="ended"):
        sessions.cmd_run(args_for("run", "job"), env=env, dirty=[])


def test_cancel_from_another_process_still_refuses_a_run_in_flight(env, prompt):
    d, _ = add(env, prompt)
    with sessions.RunLock(d):
        assert sessions.cmd_cancel(args_for("cancel", "job", "--no-systemctl"), env=env,
                                   lineage=lambda: [12345]) == 2
    assert not json.loads((d / "schedule.json").read_text()).get("ended")


def test_a_job_that_ended_itself_in_a_refused_run_is_not_held(env, prompt, monkeypatch, run):
    d, _ = add(env, prompt, name="chain")
    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])

    def ends_then_denied(argv, prompt, *, cwd, log, **kw):
        sessions.cmd_cancel(args_for("cancel", "chain", "--no-systemctl"), env=env,
                            lineage=lambda: [os.getpid()])
        log.write("You've hit your session limit · resets 1:40am\n")
        return {"exit": 1}

    sessions.cmd_run(args_for("run", "chain"), env=env, driver=ends_then_denied,
                     dirty=[], run=run)
    assert events_of(d, "ended") and events_of(d, "held") == []


def test_ancestors_walks_the_real_process_tree():
    assert os.getppid() in sessions.ancestors()
    assert os.getpid() not in sessions.ancestors(), "strict ancestors only"


def test_a_real_child_of_the_run_ends_the_job_through_the_process_tree(env, prompt, run):
    """No seam: the driver starts a process (as pi starts a shell) that calls `cancel`;
    the run's pid is found among its ancestors in /proc."""
    d, _ = add(env, prompt)
    engine = pathlib.Path(sessions.__file__).resolve().parents[1]

    def child_cancels(argv, prompt, *, cwd, log, **kw):
        p = subprocess.run(
            ["python3", "-c", "import sys; from schedule import sessions; "
             "sys.exit(sessions.main(['cancel', 'job', '--no-systemctl']))"],
            cwd=engine, env={**os.environ, **env, "PYTHONPATH": str(engine)},
            capture_output=True, text=True)
        log.write(p.stdout + p.stderr)
        return {"exit": p.returncode}

    assert sessions.cmd_run(args_for("run", "job"), env=env, driver=child_cancels,
                            dirty=[], run=run) == 0
    assert events_of(d, "ended") and events_of(d, "finished")
