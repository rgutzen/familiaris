"""scheduled sessions (9a): the record, the renderer shared with the recurring
timers, and the refusals that keep an unattended run honest.

WHY THIS IS TESTED AND NOT TRUSTED. The night of 2026-10-14 produced three
hand-built jobs, two of them transient timers that a reboot would have erased
silently. The properties that make the mechanism worth having are exactly the
ones nothing else would report: that a run writes `started` BEFORE it spawns and
`finished` after (so a run that did not finish is visible), that a dirty tree
inside the session's own write scope refuses the run instead of quietly
committing someone else's work, and that the unit pair stays byte-identical to a
fresh render of the SAME `timers-gen.sh` the recurring timers use.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys

import pytest

from schedule import sessions
from orchestration import profiles



@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    """Placeholder keys, so a model's availability never depends on the shell
    that runs the suite: the nightly pass's snapshot runs it under systemd, which
    has no DEEPSEEK_API_KEY, and these tests failed there (2026-10-16)."""
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")

class Done:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def args_for(*argv):
    return sessions._parser().parse_args(list(argv))


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units"),
            "PI_CODING_AGENT_DIR": str(tmp_path / "pi-agent")}


def test_ask_user_is_passed_only_when_pi_would_not_discover_it(tmp_path):
    """2026-10-21: with the dotfiles' shim installed, `-e` the same file made pi
    refuse to start (`Tool "ask_user" conflicts`), and the first dispatched run
    died in 1.2 s."""
    agent = tmp_path / "agent"
    assert sessions.ask_user_extensions({"PI_CODING_AGENT_DIR": str(agent)}) == [sessions.ASK_USER]
    shim = agent / sessions.ASK_USER_SHIM
    shim.parent.mkdir(parents=True)
    shim.write_text("export { default } from '...';\n")
    assert sessions.ask_user_extensions({"PI_CODING_AGENT_DIR": str(agent)}) == []


@pytest.fixture
def prompt(tmp_path):
    path = tmp_path / "handoff.md"
    path.write_text("# A handoff\n\nRead this, do the thing.\n")
    return path


def as_driver(spawn):
    """The tests' spawn fakes, in front of the RPC driver's seam (R2a): a fake writes to
    the run log as `stdout` and returns an exit; the driver returns that exit."""
    def driver(argv, prompt, *, cwd, log, **kw):
        p = spawn(argv, cwd=cwd, stdout=log)
        return {"exit": getattr(p, "returncode", 0)}
    return driver


def add_smoke(env, prompt, *, name="smoke", extra=(), run=subprocess.run,
              no_systemctl=True):
    flags = ("--no-systemctl",) if no_systemctl else ()
    a = args_for("add", "--name", name, "--in", "10m", "--prompt", str(prompt),
                 "--model", "deepseek-flash", "--effort", "high", *flags, *extra)
    assert sessions.cmd_add(a, env=env, run=run) == 0, "the fixture's add must succeed"
    d = sessions.session_dir(name, env)
    return d, json.loads((d / "schedule.json").read_text())


# --- the declaration -----------------------------------------------------------

def test_add_writes_a_record_and_a_wrapper_and_no_unit(env, prompt, tmp_path):
    """Since 1d a job has no unit of its own: the dispatcher's one timer starts it."""
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return Done(0)

    d, decl = add_smoke(env, prompt, run=run, no_systemctl=False)
    assert calls == [], "add touches no systemd at all"
    assert decl["unit"] == "" and decl["on_calendar"] == ""
    assert not list(pathlib.Path(env["PAZRAS_SESSION_UNITS"]).glob("*")) \
        if pathlib.Path(env["PAZRAS_SESSION_UNITS"]).is_dir() else True
    assert decl["kind"] == "once" and decl["push"] == "never"
    assert decl["sandbox"] == "none", "the record says a session is not sandboxed"
    assert decl["ask"] == {"kind": "prompt", "path": str(prompt), "selector": "the file"}
    assert decl["model"]["pi_model"] == "deepseek/deepseek-flash"

    wrapper = d / "run.sh"
    assert wrapper.is_file() and wrapper.stat().st_mode & 0o111
    body = wrapper.read_text()
    assert ".config/bash/local.sh" in body, "the keys are sourced into the JOB's env"
    assert "schedule sessions run smoke" in body


def test_a_9a_record_keeps_the_unit_pair_it_was_given(env, prompt, legacy):
    d, decl = legacy(env, prompt, name="smoke")
    wrapper = d / "run.sh"
    units = pathlib.Path(env["PAZRAS_SESSION_UNITS"])
    timer = (units / "familiar-session-smoke.timer").read_text()
    assert f"OnCalendar={decl['on_calendar']}" in timer
    assert "Persistent=true" in timer, "a reboot makes a missed run a LATE one"
    assert "RandomizedDelaySec" not in timer, "the clock time IS the point"
    assert "AccuracySec=1s" in timer, ("systemd's default one-minute accuracy "
                                       "starts a session up to 59s late")
    assert "OnUnitActiveSec" not in timer, "a one-shot date is not an interval"
    service = (units / "familiar-session-smoke.service").read_text()
    assert f"ExecStart={wrapper}" in service, "the wrapper is what systemd starts"
    assert "OnFailure=notify@%n.service" in service
    assert "familiar schedule sessions cancel smoke" in timer, "the banner names the way out"


def test_a_row_without_accuracy_renders_none_so_the_declared_units_do_not_move(tmp_path):
    """The coalescing default is what a recurring nightly job wants; only a row
    that carries `accuracy` renders the line, which is why adding the field left
    all 11 declared units byte-identical (timers-gen.sh --check)."""
    out = tmp_path / "u"
    subprocess.run(["bash", str(sessions.GENERATOR), "--render-entry",
                    "nightly;on_calendar=*-*-* 03:30:00;exec=echo hi;randomized_delay=",
                    "--out", str(out)], check=True, capture_output=True)
    assert "AccuracySec" not in (out / "nightly.timer").read_text()


def test_add_refuses_a_name_taken(env, prompt):
    add_smoke(env, prompt)
    a = args_for("add", "--name", "smoke", "--in", "10m", "--prompt", str(prompt),
                 "--model", "deepseek-flash", "--no-systemctl")
    with pytest.raises(sessions.SessionError, match="already exists"):
        sessions.cmd_add(a, env=env)


def test_add_refuses_a_past_clock_time(env, prompt):
    a = args_for("add", "--name", "late", "--at", "2020-01-01 06:00",
                 "--prompt", str(prompt), "--model", "deepseek-flash", "--no-systemctl")
    with pytest.raises(sessions.SessionError, match="has passed"):
        sessions.cmd_add(a, env=env)


def test_the_delay_parser_speaks_the_shape_a_person_types():
    assert sessions.parse_delay("90m") == dt.timedelta(minutes=90)
    assert sessions.parse_delay("1h30m") == dt.timedelta(minutes=90)
    assert sessions.parse_delay("45") == dt.timedelta(seconds=45)
    with pytest.raises(sessions.SessionError):
        sessions.parse_delay("soon")


# --- the renderer is the timers one ------------------------------------------

def test_an_edited_unit_is_reported_as_drift(env, prompt, legacy):
    d, decl = legacy(env, prompt, name="smoke")
    unit = pathlib.Path(env["PAZRAS_SESSION_UNITS"]) / "familiar-session-smoke.timer"
    unit.write_text(unit.read_text() + "\n# hand-edited\n")
    findings = sessions.self_check(decl, d, env)
    assert ("DRIFT", "unit", "familiar-session-smoke.timer differs from a fresh render") in findings
    assert sessions.cmd_check(args_for("check"), env=env) == 3


def test_check_is_clean_right_after_add_and_reports_a_ghost_unit(env, prompt, legacy):
    add_smoke(env, prompt)
    legacy(env, prompt)
    assert sessions.cmd_check(args_for("check"), env=env) == 0
    ghost = pathlib.Path(env["PAZRAS_SESSION_UNITS"]) / "familiar-session-ghost.timer"
    ghost.write_text("[Unit]\nDescription=nothing declares me\n")
    assert sessions.cmd_check(args_for("check"), env=env) == 3


# --- the run -----------------------------------------------------------------

def test_run_writes_started_then_finished_with_the_transcript(env, prompt):
    d, decl = add_smoke(env, prompt)
    seen = {}

    def spawn(argv, **kw):
        seen["argv"], seen["cwd"] = list(argv), kw.get("cwd")
        sid = argv[argv.index("--session-id") + 1]
        sessions_dir = pathlib.Path(argv[argv.index("--session-dir") + 1])
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / f"{sid}.jsonl").write_text('{"type":"session"}\n')
        kw["stdout"].write("did the thing\n")
        return Done(0)

    code = sessions.cmd_run(args_for("run", "smoke"), env=env, driver=as_driver(spawn), dirty=[])
    assert code == 0
    events = sessions.read_events(d)
    # A one-off that finished tells the user (1g); the record says so first.
    assert [e["event"] for e in events] == ["started", "finished", "notified"], events
    assert events[-1]["state"] == "done"
    started, finished, _notified = events
    assert started["argv"][:3] == ["pi", "--mode", "rpc"], "RPC, so asks can reach the phone"
    assert started["argv"][started["argv"].index("--model") + 1] == "deepseek/deepseek-flash"
    assert started["argv"][started["argv"].index("--thinking") + 1] == "high"
    assert "--approve" in started["argv"] and "--no-approve" not in started["argv"]
    ext = pathlib.Path(started["argv"][started["argv"].index("-e") + 1])
    assert ext.name == "index.ts" and ext.parent.name == "pi-ask-user" and ext.is_file()
    assert "PI_CODING_AGENT_DIR" in env, "the fixture's pi has no shim, so -e is passed"
    assert seen["cwd"] == decl["cwd"]
    assert finished["exit"] == 0
    assert finished["transcript"].endswith(".jsonl")
    assert "did the thing" in "\n".join(finished["tail"])
    assert started["ask"]["sha256"] == sessions._sha(prompt.read_text())


def test_run_refuses_a_dirty_tree_inside_the_write_scope(env, prompt):
    d, _ = add_smoke(env, prompt, extra=("--touches", "engine/schedule/**"))
    called = []

    def spawn(argv, **kw):                       # must never be reached
        called.append(argv)
        return Done(0)

    code = sessions.cmd_run(args_for("run", "smoke"), env=env, driver=as_driver(spawn),
                            dirty=["engine/schedule/sessions.py"])
    assert code == 3 and not called
    events = sessions.read_events(d)
    assert events[-1]["event"] == "refused"
    assert events[-1]["dirty"] == ["engine/schedule/sessions.py"]
    # ... and dirt OUTSIDE the scope proceeds: this tree is often dirty with the
    # user's own work, and a blanket refuse would make the session useless.
    code = sessions.cmd_run(args_for("run", "smoke"), env=env, driver=as_driver(spawn),
                            dirty=["README.md"])
    assert code == 0 and called


def test_run_refuses_a_model_the_profile_cannot_serve(env, prompt, monkeypatch):
    d, _ = add_smoke(env, prompt)
    monkeypatch.setattr(sessions.profiles, "resolve",
                        lambda *a, **k: profiles.Resolution("deepseek-flash", "private",
                                                            reason="DEEPSEEK_API_KEY is not set"))
    called = []
    code = sessions.cmd_run(args_for("run", "smoke"), env=env, dirty=[],
                            driver=as_driver(lambda *a, **k: called.append(a) or Done(0)))
    assert code == 2 and not called
    row = sessions.read_events(d)[-1]
    assert row["event"] == "refused" and "DEEPSEEK_API_KEY" in row["reason"]


def test_git_dirty_reads_porcelain_and_a_non_repository_is_not_dirty(tmp_path):
    def porcelain(argv, **kw):
        return Done(0, " M engine/schedule/sessions.py\n?? new file.md\nR  old.py -> renamed.py\n")

    assert sessions.git_dirty(tmp_path, run=porcelain) == [
        "engine/schedule/sessions.py", "new file.md", "renamed.py"]

    def not_a_repo(argv, **kw):
        return Done(128, "", "fatal: not a git repository (or any of the parent directories): .git")

    assert sessions.git_dirty(tmp_path, run=not_a_repo) == []

    def broken(argv, **kw):
        return Done(128, "", "fatal: cannot change to '/nope': No such file or directory")

    with pytest.raises(sessions.SessionError):
        sessions.git_dirty("/nope", run=broken)


def test_run_holds_a_lock_so_two_runs_do_not_interleave(env, prompt):
    d, _ = add_smoke(env, prompt)
    with sessions.RunLock(d):
        with pytest.raises(sessions.SessionError, match="already in flight"):
            sessions.cmd_run(args_for("run", "smoke"), env=env, dirty=[], driver=as_driver(lambda *a, **k: None))
    assert sessions.RunLock(d).held() is False, "the lock is released when the run ends"


def test_a_started_row_without_finished_is_LOST_and_list_says_so(env, prompt, capsys):
    d, decl = add_smoke(env, prompt)
    old = (sessions.now_local() - dt.timedelta(hours=30)).isoformat(timespec="seconds")
    sessions.write_event(d, {"event": "started", "ts": old, "session": "smoke"})
    assert sessions.cmd_list(args_for("list"), env=env) == 0
    assert "LOST" in capsys.readouterr().out
    assert sessions.cmd_check(args_for("check"), env=env) == 0   # history warns, not drift


def test_cancel_removes_the_unit_and_keeps_the_record(env, prompt):
    d, decl = add_smoke(env, prompt)
    code = sessions.cmd_cancel(args_for("cancel", "smoke", "--no-systemctl"), env=env)
    assert code == 0
    units = pathlib.Path(env["PAZRAS_SESSION_UNITS"])
    assert not list(units.glob("familiar-session-smoke.*"))
    assert (d / "schedule.json").is_file(), "the record is the point; cancel keeps it"
    assert json.loads((d / "schedule.json").read_text())["cancelled"]
    assert sessions.cmd_check(args_for("check"), env=env) == 0
    # A cancelled session stays visible, and run refuses it.
    assert "cancelled" in capsys_text(sessions.cmd_list, args_for("list"), env=env)
    with pytest.raises(sessions.SessionError, match="cancelled"):
        sessions.cmd_run(args_for("run", "smoke"), env=env, dirty=[])


def test_a_cancelled_session_whose_source_is_gone_is_not_drift(env, prompt):
    d, decl = add_smoke(env, prompt)
    sessions.cmd_cancel(args_for("cancel", "smoke", "--no-systemctl"), env=env)
    pathlib.Path(decl["ask"]["path"]).unlink()
    assert sessions.cmd_check(args_for("check"), env=env) == 0


def test_cancel_refuses_to_stop_a_run_in_flight(env, prompt, legacy):
    d, _ = legacy(env, prompt, name="smoke")
    with sessions.RunLock(d):
        code = sessions.cmd_cancel(args_for("cancel", "smoke", "--no-systemctl"), env=env)
    assert code == 2
    assert (pathlib.Path(env["PAZRAS_SESSION_UNITS"]) / "familiar-session-smoke.timer").is_file()
    assert not json.loads((d / "schedule.json").read_text()).get("cancelled")


def capsys_text(fn, *a, **kw):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*a, **kw)
    return buf.getvalue()


# --- the ask: a prompt, or a SPECS wave/item ---------------------------------

SPECS = """# Track x -- the checklist

The preamble a session should see.

## Step 1

- [x] **1a · done.** already
  touches: a/**
  depends: —
  model: claude-opus-5-5
  verify: true
- [ ] **1b · the first open one.** do it
  touches: b/**
  depends: —
  model: claude-opus-5-5
  verify: true
- [ ] **1c · after 1b.** then this
  touches: b/**
  depends: 1b
  model: claude-opus-5-5
  verify: true
"""


def specs_ask(tmp_path, **selector):
    path = tmp_path / "SPECS.md"
    path.write_text(SPECS)
    ask = {"kind": "specs", "path": str(path), "selector": "", "item": "", "wave": "", "all": False}
    ask.update(selector)
    return sessions.resolve_ask({"ask": ask, "touches": []})


def test_the_specs_default_is_the_first_open_wave(tmp_path):
    got = specs_ask(tmp_path)
    assert got["items"] == ["1b"], "1c depends on 1b, so the first open wave is 1b alone"
    assert got["wave"] == 1
    assert "the first open one" in got["text"]
    assert "The preamble a session should see." in got["text"]
    assert "1a" not in got["text"], "a done item is not part of the ask"
    assert got["touches"] == ["b/**"]


def test_a_named_item_a_named_wave_and_everything_open(tmp_path):
    assert specs_ask(tmp_path, item="1c")["items"] == ["1c"]
    assert specs_ask(tmp_path, wave="2")["items"] == ["1c"]
    assert specs_ask(tmp_path, all=True)["items"] == ["1b", "1c"]
    with pytest.raises(sessions.SessionError, match="no open item"):
        specs_ask(tmp_path, item="1a")
    with pytest.raises(sessions.SessionError, match="open wave"):
        specs_ask(tmp_path, wave="9")


def test_a_specs_session_refuses_a_selector_that_names_nothing_at_add_time(env, tmp_path):
    path = tmp_path / "SPECS.md"
    path.write_text(SPECS)
    a = args_for("add", "--name", "none", "--in", "10m", "--specs", str(path),
                 "--item", "1z", "--model", "deepseek-flash", "--no-systemctl")
    with pytest.raises(sessions.SessionError, match="no open item"):
        sessions.cmd_add(a, env=env)


# --- model and effort --------------------------------------------------------

def test_effort_is_refused_for_a_model_that_does_not_think(tmp_path):
    cat = {"models": [{"id": "qwen3", "vendor": "ollama", "kind": "chat",
                       "jurisdiction": "local", "capabilities": {"thinking": "no"}}]}
    a = args_for("add", "--name", "x", "--in", "5m", "--prompt", str(tmp_path / "p.md"),
                 "--model", "qwen3", "--effort", "high")
    with pytest.raises(sessions.SessionError, match="does not think"):
        sessions.resolve_model(a, {}, tmp_path, cat=cat, caps={}, profile="private")


def test_the_default_model_is_the_catalogue_one_and_the_record_says_who_chose():
    defaults = sessions.load_config()
    a = args_for("add", "--name", "x", "--in", "5m", "--prompt", "/tmp/p.md")
    got = sessions.resolve_model(a, defaults, pathlib.Path.home())
    assert got["id"] == "claude-opus-5-5" and got["effort"] == "high"
    assert "config default" in got["source"]
    assert got["pi_model"].startswith("claude-bridge/") or got["pi_model"].startswith("none/")


def test_the_standing_prompt_is_named_in_config_and_reaches_the_child():
    defaults = sessions.load_config()
    assert defaults["standing_prompt"].endswith("session-prompt.md")
    assert "Never push" in sessions.standing_text(defaults)


# --- repeating sessions (2026-10-19) -----------------------------------------

def test_an_every_job_is_a_period_from_the_last_start_with_no_unit(env, prompt):
    """PLAN defect 1: `--every 5h --at 01:35` was a clock step, so 21:35 -> 01:35 was
    four hours. Now the first start is the next 01:35 and each next one is five hours
    after the previous START, which the dispatcher keeps."""
    a = args_for("add", "--name", "chain", "--every", "5h", "--at", "01:35",
                 "--prompt", str(prompt), "--model", "deepseek-flash")
    assert sessions.cmd_add(a, env=env) == 0
    d = sessions.session_dir("chain", env)
    decl = json.loads((d / "schedule.json").read_text())
    assert decl["trigger"] == "every" and decl["every"] == "5h" and decl["unit"] == ""
    first = dt.datetime.fromisoformat(decl["due"])
    assert (first.hour, first.minute) == (1, 35) and first > sessions.now_local()
    st = sessions._state(decl, [], sessions.now_local())
    assert st["state"] == "repeating"          # a period has no single due time to miss


def test_every_refuses_what_the_dispatcher_cannot_keep(env, prompt):
    def refuses(*extra):
        a = args_for("add", "--name", "x", *extra, "--prompt", str(prompt),
                     "--model", "deepseek-flash")
        with pytest.raises(sessions.SessionError):
            sessions.cmd_add(a, env=env)

    refuses("--every", "2m")                       # shorter than a tick
    refuses("--every", "5h", "--ready")            # two triggers
    refuses("--every", "soon")


# The window's refusal and its hold: test_jobs.py (dev/schedule 1a).


def test_a_repeating_session_runs_without_a_due_time_to_be_late_for(env, prompt):
    """2026-10-20: `late_seconds` parsed decl["due"], which a repeat never has, so the
    unit died before `pi` started -- twice, at two anchors, with an empty record."""
    a = args_for("add", "--name", "chain", "--every", "5h", "--at", "01:35",
                 "--prompt", str(prompt), "--model", "deepseek-flash", "--no-systemctl")
    assert sessions.cmd_add(a, env=env) == 0
    code = sessions.cmd_run(args_for("run", "chain"), env=env, dirty=[],
                            driver=as_driver(lambda argv, **kw: Done(0)),
                            run=lambda *a, **k: Done(0))
    assert code == 0
    d = sessions.session_dir("chain", env)
    events = sessions.read_events(d)
    assert [e["event"] for e in events] == ["started", "finished"]
    assert events[0]["late_seconds"] is None
    assert sessions._state(json.loads((d / "schedule.json").read_text()), events,
                           sessions.now_local())["state"] == "repeating"


def test_a_crash_before_the_session_starts_is_recorded_and_list_says_crashed(env, prompt,
                                                                           monkeypatch):
    d, decl = add_smoke(env, prompt, name="chain")

    def boom(*a, **k):
        raise RuntimeError("a defect in the runner")

    monkeypatch.setattr(sessions, "build_prompt", boom)
    assert sessions.cmd_run(args_for("run", "chain"), env=env, dirty=[]) == 2
    events = sessions.read_events(d)
    crashed = [e for e in events if e["event"] == "crashed"][-1]
    assert "RuntimeError" in crashed["error"]
    assert events[-1]["event"] == "notified" and events[-1]["state"] == "crashed"
    assert sessions._state(decl, events, sessions.now_local())["state"] == "crashed"


def test_an_unknown_name_says_what_is_scheduled_instead_of_crashing(env, prompt):
    """2026-10-20: the not-found message unpacked (path, decl) and read `.get` off the path."""
    add_smoke(env, prompt, name="smoke")
    with pytest.raises(sessions.SessionError, match="no session 'ghost'.*smoke"):
        sessions.cmd_run(args_for("run", "ghost"), env=env)
