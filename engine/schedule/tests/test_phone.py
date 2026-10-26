"""The scheduler's phone screens and the hold by hand (dev/remote R5b, R5e)."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from schedule import phone, sessions


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")
    monkeypatch.setattr(phone, "budget_lines", lambda env: ["5-hour: 10% of 100%"])


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units"),
            "PI_CODING_AGENT_DIR": str(tmp_path / "pi")}


def add(env, tmp_path, name, *extra):
    prompt = tmp_path / "p.md"
    prompt.write_text("do it\n")
    a = sessions._parser().parse_args(["add", "--name", name, "--ready", "--prompt", str(prompt),
                                       "--model", "deepseek-flash", "--cwd", str(tmp_path), *extra])
    assert sessions.cmd_add(a, env=env) == 0
    return sessions.session_dir(name, env)


def test_status_names_what_holds_a_ready_job_back_and_skips_finished_one_offs(env, tmp_path):
    d = add(env, tmp_path, "waits")
    sessions.write_event(d, {"event": "deferred", "ts": sessions.now_local().isoformat(),
                             "holding": {"user_active": "pi"}})
    done = add(env, tmp_path, "over")
    for e in ({"event": "started"}, {"event": "finished", "exit": 0}):
        sessions.write_event(done, {"ts": sessions.now_local().isoformat(), **e})
    lines = phone.main("status", env=env)
    assert lines[0] == "jobs: 1 ready"
    assert "- waits: ready, held back by user_active" in lines
    assert not any("over" in l for l in phone.main("jobs", env=env)), "a finished one-off is gone"


def test_a_paused_chain_says_how_to_approve_it(env, tmp_path):
    d = add(env, tmp_path, "ch", "--chain", "until-done")
    sessions.write_event(d, {"event": "paused", "ts": sessions.now_local().isoformat(),
                             "state": "review", "why": "ticked 1a"})
    lines = phone.main("job", "ch", env=env)
    assert lines[0] == "ch: paused -- review: ticked 1a"
    assert lines[-1] == "/approve ch lets it go on"


def test_a_hold_by_hand_holds_and_never_counts_as_a_refusal(env, tmp_path, capsys):
    d = add(env, tmp_path, "job")
    assert sessions.cmd_hold(sessions._parser().parse_args(["hold", "job", "30m"]), env=env) == 0
    until = sessions.hold_until(sessions.read_events(d))
    assert dt.timedelta(minutes=29) < until - sessions.now_local() <= dt.timedelta(minutes=30)
    assert sessions.refusal_streak(sessions.read_events(d)) == 0
    assert sessions._state(json.loads((d / "schedule.json").read_text()),
                           sessions.read_events(d), sessions.now_local())["state"] == "held"


def test_a_chain_between_runs_is_continuing_not_done(env, tmp_path):
    """2026-10-21: `/status` said `jobs: 1 done` for 1i's chain after its first run."""
    d = add(env, tmp_path, "ch", "--chain", "until-done")
    for e in ({"event": "started"}, {"event": "finished", "exit": 0},
              {"event": "deferred", "holding": {"budget": "spent"}}):
        sessions.write_event(d, {"ts": sessions.now_local().isoformat(), **e})
    lines = phone.main("status", env=env)
    assert lines[0] == "jobs: 1 continuing"
    assert "- ch: continuing, held back by budget" in lines
