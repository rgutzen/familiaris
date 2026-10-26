"""notify (dev/schedule 1g): the user hears about it -- a notification and a brief line.

What must hold: the record is written BEFORE any channel is tried; a channel that
is down (no relay, no bus) is recorded and never raised; each state that needs
the user is told once; and the brief reads the same records.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess

import pytest

from schedule import notify, sessions


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units"),
            "XDG_RUNTIME_DIR": str(tmp_path / "run")}


def record(env, name="job", **decl):
    d = sessions.session_dir(name, env)
    sessions.write_decl(d, {"name": name, "kind": "once", "trigger": "at", "chain": "none",
                            "due": "", "unit": "", "timeout": "1h", **decl})
    return d


def test_the_record_is_written_before_any_channel_is_tried(env, monkeypatch):
    d = record(env)
    seen = []

    def desktop(title, text, urgency, env_):
        seen.append([e["event"] for e in sessions.read_events(d)])
        return ""

    monkeypatch.setattr(notify, "CHANNELS", {"desktop": desktop,
                                             "relay": lambda job, text, env_: ""})
    notify.send(d, "job", "blocked", "only the user's items remain", env=env)
    assert seen == [["notified"]]
    ev = sessions.read_events(d)[0]
    assert ev["state"] == "blocked" and "user's items" in ev["text"]


def test_a_channel_that_is_down_is_recorded_and_never_raised(env, monkeypatch):
    d = record(env)
    monkeypatch.setattr(notify, "CHANNELS", {
        "desktop": lambda *a: "", "relay": notify._relay})      # the real relay client
    errors = notify.send(d, "job", "done", "chain done", env=env)
    assert errors["desktop"] == "" and errors["relay"], "no relay socket in the test's runtime dir"
    failed = [e for e in sessions.read_events(d) if e["event"] == "notify_failed"]
    assert list(failed[0]["errors"]) == ["relay"]


def test_the_desktop_reaches_the_user_bus_from_a_unit_without_one(env, monkeypatch):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw["env"]))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(notify.subprocess, "run", run)
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    assert notify._desktop("familiar: job LOST", "never finished", "critical", {}) == ""
    argv, full = calls[0]
    assert argv[0] == "notify-send" and "--urgency=critical" in argv
    assert full["DBUS_SESSION_BUS_ADDRESS"].startswith("unix:path=/run/user/")


def test_a_lost_run_is_told_once_per_start(env, told):
    d = record(env)
    old = (sessions.now_local() - dt.timedelta(hours=3)).isoformat(timespec="seconds")
    sessions.write_event(d, {"event": "started", "ts": old})
    assert notify.sweep_lost(env) == ["job"]
    assert notify.sweep_lost(env) == [], "once per start, not once per tick"
    assert [t[0] for t in told] == ["desktop", "relay"] and "LOST" in told[0][1]
    newer = (sessions.now_local() - dt.timedelta(hours=2)).isoformat(timespec="seconds")
    sessions.write_event(d, {"event": "started", "ts": newer})
    assert notify.sweep_lost(env) == ["job"], "a second lost start is news again"


def test_a_one_off_that_finished_and_a_chain_that_paused_are_told(env, told, tmp_path,
                                                                 monkeypatch):
    prompt = tmp_path / "p.md"
    prompt.write_text("---\nstatus: open\n---\ndo it\n")
    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    monkeypatch.setattr(sessions, "_window_reset", lambda decl, env: "")
    for name, extra in (("once", ()), ("pc", ("--chain", "until-done"))):
        a = sessions._parser().parse_args(
            ["add", "--name", name, "--ready", "--prompt", str(prompt),
             "--model", "deepseek-flash", "--cwd", str(tmp_path), *extra])
        assert sessions.cmd_add(a, env=env) == 0

    def blocks(argv, prompt_text, *, cwd, log, **kw):
        prompt.write_text("---\nstatus: blocked\n---\ndo it\n")
        return {"exit": 0}

    for name in ("once", "pc"):
        sessions.cmd_run(sessions._parser().parse_args(["run", name]), env=env, dirty=[],
                         driver=blocks, run=lambda *a, **k: None)
    titles = [t[1] for t in told if t[0] == "desktop"]
    assert "familiar: once done" in titles and "familiar: pc blocked" in titles


def test_a_repeating_jobs_ordinary_run_is_not_news(env, told, tmp_path, monkeypatch):
    prompt = tmp_path / "p.md"
    prompt.write_text("do it\n")
    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    monkeypatch.setattr(sessions, "_window_reset", lambda decl, env: "")
    a = sessions._parser().parse_args(
        ["add", "--name", "rep", "--every", "5h", "--prompt", str(prompt),
         "--model", "deepseek-flash", "--cwd", str(tmp_path)])
    sessions.cmd_add(a, env=env)
    sessions.cmd_run(sessions._parser().parse_args(["run", "rep"]), env=env, dirty=[],
                     driver=lambda *a, **k: {"exit": 0}, run=lambda *a, **k: None)
    assert told == []


def test_brief_lines_name_the_state_the_runs_and_the_commits(env):
    d = record(env, name="track", chain="until-done", kind="chain", trigger="ready")
    today = sessions.now_local().date()
    for e in ({"event": "started", "ts": f"{today}T01:00:00+02:00"},
              {"event": "finished", "ts": f"{today}T02:00:00+02:00", "exit": 0,
               "progress": {"ticks": ["1b"], "commits": ["abc1234 1b"]}},
              {"event": "started", "ts": f"{today}T03:00:00+02:00"},
              {"event": "finished", "ts": f"{today}T03:05:00+02:00", "exit": 1,
               "window_refused": True, "progress": {}}):
        sessions.write_event(d, e)
    record(env, name="quiet",
           due=(sessions.now_local() + dt.timedelta(hours=1)).isoformat(timespec="seconds"))
    record(env, name="broken", trigger="at", due="")         # malformed: no due time
    lines = notify.brief_lines(env, since=today)
    assert [line.split("`")[1] for line in lines] == ["broken", "track"]
    lines = [line for line in lines if "`track`" in line]
    assert "2 run(s)" in lines[0] and "completed, the window refused it" in lines[0]
    assert "ticked 1b" in lines[0] and "1 commit(s) — abc1234 1b" in lines[0]
    json.dumps(lines)
