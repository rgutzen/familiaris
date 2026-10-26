"""`sessions prune`: the retention policy, measured on the archive, not trusted.

Prune MOVES a record under `<data>/sessions/archive/`; nothing is deleted. The
properties that matter: a dry run writes nothing, a record a live unit or an
active job still needs is kept, and an archived record is out of `list` but
still on disk.

Every age here is computed from the clock, never written as a date: a literal
stamp would make the suite pass today and fail in a month.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from schedule import sessions


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units")}


def ago(days: float) -> str:
    """A local timestamp `days` in the past, in the form a record writes."""
    return (sessions.now_local()
            - dt.timedelta(days=days)).isoformat(timespec="seconds")


def make_record(env, name, *, events=(), age_days=None, **decl_extra):
    """One record under the live data root, optionally aged on disk."""
    d = sessions.session_dir(name, env)
    d.mkdir(parents=True)
    sessions.write_decl(d, {"name": name, "trigger": "at", "created": "",
                            "due": (sessions.now_local()
                                    + dt.timedelta(days=1)).isoformat(timespec="seconds"),
                            **decl_extra})
    for e in events:
        sessions.write_event(d, e)
    if age_days is not None:
        old = (dt.datetime.now().astimezone()
               - dt.timedelta(days=age_days)).timestamp()
        os.utime(d / "schedule.json", (old, old))
        os.utime(d, (old, old))
    return d


def old_run(days=40):
    return {"event": "finished", "ts": ago(days), "exit": 0}


def prune(*argv, env):
    args = sessions._parser().parse_args(["prune", *argv])
    return sessions.cmd_prune(args, env=env)


def test_dry_run_writes_nothing(env, capsys):
    d = make_record(env, "old-closed", events=[old_run()], ended=ago(40), age_days=40)
    assert prune("--dry-run", env=env) == 0
    assert d.is_dir() and not (sessions.data_root(env) / "archive").exists()
    assert "pruned" not in (d / "runs.jsonl").read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "would archive old-closed" in out
    assert "1 would be archived" in out


def test_closed_old_record_is_archived_not_deleted(env):
    d = make_record(env, "gone", events=[old_run()], ended=ago(40), age_days=40)
    assert prune(env=env) == 0
    assert not d.exists()
    archived = sessions.data_root(env) / "archive" / "gone"
    assert archived.is_dir()
    # The record moves whole: the declaration and the event history ride along.
    assert json.loads((archived / "schedule.json").read_text())["name"] == "gone"
    events = [json.loads(line) for line in
              (archived / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [e["event"] for e in events] == ["finished", "pruned"]


def test_open_never_started_past_the_window_is_archived(env):
    # The land-* pile: a ready job whose time passed without a run.
    make_record(env, "stale-ready", trigger="ready", age_days=40)
    assert prune(env=env) == 0
    assert not sessions.session_dir("stale-ready", env).exists()


def test_open_job_that_has_run_is_kept(env):
    # A chain between runs is alive: prune has no claim on it.
    d = make_record(env, "chain-x", events=[{"event": "started", "ts": ago(40)}],
                    age_days=40)
    assert prune(env=env) == 0
    assert d.is_dir()


def test_recently_closed_record_is_kept(env):
    d = make_record(env, "fresh", events=[old_run(days=2)])
    assert prune(env=env) == 0
    assert d.is_dir()


def test_a_record_whose_unit_is_still_on_disk_is_kept(env, capsys):
    # Prunable but for the unit: the timer would fire into a directory that moved.
    d = make_record(env, "live-unit", events=[old_run()], ended=ago(40), age_days=40)
    units = sessions.units_dir(env)
    units.mkdir(parents=True)
    (units / "familiar-session-live-unit.timer").write_text("")
    (units / "familiar-session-live-unit.service").write_text("")
    assert prune(env=env) == 0
    assert d.is_dir()
    assert "cancel live-unit" in capsys.readouterr().out


def test_a_record_with_no_unit_field_and_no_unit_file_is_archived(env):
    # `unit: ""` is what `add` writes: the dispatcher starts the job, no unit exists.
    make_record(env, "dispatched", unit="", ended=ago(40), age_days=40)
    assert prune(env=env) == 0
    assert not sessions.session_dir("dispatched", env).exists()


def test_list_hides_a_closed_record_past_the_window_and_all_shows_it(env, capsys):
    make_record(env, "old-ended", ended=ago(40))
    make_record(env, "fresh")
    assert sessions.cmd_list(sessions._parser().parse_args(["list"]), env=env) == 0
    shown = capsys.readouterr().out
    assert "old-ended" not in shown
    assert "fresh" in shown
    # Hidden is not gone: the list says how many it left out.
    assert "1 closed record(s) past the 3d window hidden" in shown
    assert sessions.cmd_list(sessions._parser().parse_args(
        ["list", "--all"]), env=env) == 0
    shown = capsys.readouterr().out
    assert "old-ended" in shown and "hidden" not in shown


def test_the_list_window_is_shorter_than_the_retention_window(env, capsys):
    # Decided 2026-10-25: out of sight after 3d, on disk for 30d. A record closed
    # five days ago is the one case that separates the two, so it is the case
    # that states the decision.
    d = make_record(env, "five-days-gone", ended=ago(5), age_days=5)
    assert sessions.cmd_list(sessions._parser().parse_args(["list"]), env=env) == 0
    assert "five-days-gone" not in capsys.readouterr().out
    assert prune(env=env) == 0
    assert d.is_dir(), "hidden from the list, still inside the retention window"


def test_list_older_than_overrides_the_window(env, capsys):
    make_record(env, "old-ended", ended=ago(40))
    assert sessions.cmd_list(sessions._parser().parse_args(
        ["list", "--older-than", "90d"]), env=env) == 0
    assert "old-ended" in capsys.readouterr().out


def test_an_unreadable_closed_stamp_is_shown_not_hidden(env, capsys):
    # A hand-edited field must not make a record invisible.
    make_record(env, "garbled", ended="last tuesday")
    assert sessions.cmd_list(sessions._parser().parse_args(["list"]), env=env) == 0
    shown = capsys.readouterr().out
    assert "garbled" in shown and "hidden" not in shown
