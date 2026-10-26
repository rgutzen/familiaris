"""conditions (dev/schedule 1b): named predicates, composed in configuration.

Every predicate reads the machine through a `Context` seam -- the probe, the
process table, the terminal's last I/O, the clock -- so these tests hold the
properties without depending on who is logged in or what the account has spent.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import pathlib

import pytest

from schedule import conditions as C
from schedule import sessions

TZ = dt.timezone(dt.timedelta(hours=2))
NOW = dt.datetime(2026, 10, 21, 1, 0, tzinfo=TZ)
CLAUDE = {"pi_model": "claude-bridge/claude-opus-5-5"}


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units")}


def limits(five=0.2, week=0.3):
    return {"limits": [
        {"label": "Session (5-hour)", "percent": five, "resetsAt": "2026-10-21T03:29:59+00:00"},
        {"label": "Weekly (7-day)", "percent": week, "resetsAt": "2026-10-25T02:59:59+00:00"}]}


def ctx_for(env, *, policy=None, probe=None, procs=(), seen=None, clock=1000.0):
    policy = policy or sessions.load_policy()
    return C.Context(policy, env=env, now=NOW, procs=lambda: list(procs),
                     probe=probe or (lambda argv, env=None: limits()), clock=lambda: clock,
                     tty_seen=seen or (lambda tty: clock))


def job(**kw):
    return {"name": "j", "cwd": "/tmp/somewhere", "model": CLAUDE, "touches": [], **kw}


# --- budget ----------------------------------------------------------------------

def test_budget_is_clear_under_the_caps_and_says_both_readings(env):
    v = C.budget(job(), ctx_for(env))
    assert not v.holds and "five-hour 20%" in v.reason and "weekly 30%" in v.reason


def test_budget_holds_at_the_cap_until_the_binding_window_resets(env):
    v = C.budget(job(), ctx_for(env, probe=lambda a, e=None: limits(five=1.0)))
    assert v.holds and v.until == dt.datetime(2026, 10, 21, 3, 29, 59, tzinfo=dt.timezone.utc)
    # Both spent: the one that frees LAST binds.
    v = C.budget(job(), ctx_for(env, probe=lambda a, e=None: limits(five=1.0, week=1.0),
                                clock=2000.0))         # past the probe's cache
    assert v.until == dt.datetime(2026, 10, 25, 2, 59, 59, tzinfo=dt.timezone.utc)


def test_the_caps_are_settings(env):
    policy = sessions.load_policy()
    policy["conditions"]["budget"]["five_hour_max"] = "0.15"
    assert C.budget(job(), ctx_for(env, policy=policy)).holds


def test_the_probe_is_cached_for_its_minimum_interval(env):
    calls, seen_env = [], []

    def probe(argv, env=None):
        calls.append(argv)
        seen_env.append(env)
        return limits()

    C.budget(job(), ctx_for(env, probe=probe, clock=1000.0))
    C.budget(job(), ctx_for(env, probe=probe, clock=1010.0))
    assert len(calls) == 1
    C.budget(job(), ctx_for(env, probe=probe, clock=1016.0))
    assert len(calls) == 2
    assert calls[0] == ["omarchy-agent-usage-claude", "--limits-only", "--force"], (
        "account-true only with --force: the tool's reuse window has no account in its key")


def test_a_failed_probe_falls_back_to_the_last_refusal_on_record(env):
    def broken(argv, env=None):
        raise OSError("no such tool")

    assert not C.budget(job(), ctx_for(env, probe=broken)).holds
    d = sessions.session_dir("other", env)
    sessions.write_decl(d, {"name": "other"})
    until = NOW + dt.timedelta(hours=1)
    sessions.write_event(d, {"event": "held", "until": until.isoformat(),
                             "why": "the window refused the run (the refusal's reset time)"})
    v = C.budget(job(), ctx_for(env, probe=broken))
    assert v.holds and v.until == until and "probe failed" in v.reason


def test_a_model_that_does_not_spend_the_claude_window_is_never_held_by_it(env):
    v = C.budget(job(model={"pi_model": "deepseek/deepseek-flash"}),
                 ctx_for(env, probe=lambda a, e=None: limits(five=1.0)))
    assert not v.holds and "does not spend" in v.reason


# --- user_active -----------------------------------------------------------------

def P(pid, ppid, comm, tty=34818, cmd=""):
    return C.Proc(pid, ppid, comm, tty, cmd or comm)


def test_tty_nr_decodes_to_the_terminal_device():
    assert C.tty_path(34818) == pathlib.Path("/dev/pts/2")      # measured: this session's pi
    assert C.tty_path(0) is None


def test_an_interactive_harness_on_a_terminal_is_the_user_working(env):
    v = C.user_active(job(), ctx_for(env, procs=[P(10, 1, "bash"), P(11, 10, "pi")]))
    assert v.holds and "pi (pid 11, I/O 0s ago)" in v.reason


def test_a_daemon_and_a_scheduled_run_are_not(env):
    procs = [P(20, 1, "hermes", tty=0, cmd="python -m hermes_cli.main gateway run"),
             P(30, 1, "python3", cmd="python3 familiar schedule sessions run chain"),
             P(31, 30, "pi", cmd="pi --mode rpc")]
    assert not C.user_active(job(), ctx_for(env, procs=procs)).holds


def test_a_harness_inside_a_harness_is_one_session(env):
    procs = [P(11, 1, "pi"), P(12, 11, "claude")]
    v = C.user_active(job(), ctx_for(env, procs=procs))
    assert v.reason == "interactive: pi (pid 11, I/O 0s ago)"


def test_an_idle_terminal_is_not_the_user_working_unless_idle_is_off(env):
    procs = [P(11, 1, "pi")]
    stale = lambda tty: 1000.0 - 3600                    # an hour without input or output
    assert not C.user_active(job(), ctx_for(env, procs=procs, seen=stale)).holds
    policy = sessions.load_policy()
    policy["conditions"]["user_active"]["idle_after"] = ""
    assert C.user_active(job(), ctx_for(env, policy=policy, procs=procs, seen=stale)).holds


def test_only_a_session_in_the_jobs_own_tree_holds_it(env):
    elsewhere = C.Proc(11, 1, "pi", 34818, "pi", "/home/u/other-project")
    above = C.Proc(12, 1, "pi", 34819, "pi", "/tmp")
    inside = C.Proc(13, 1, "pi", 34820, "pi", "/tmp/somewhere/sub")
    v = C.user_active(job(), ctx_for(env, procs=[elsewhere, above]))
    assert not v.holds and v.reason == "no interactive session in /tmp/somewhere"
    v = C.user_active(job(), ctx_for(env, procs=[elsewhere, inside]))
    assert v.holds and "pid 13" in v.reason and "pid 11" not in v.reason


def test_an_unreadable_cwd_counts_and_scope_any_restores_the_old_rule(env):
    assert C.user_active(job(), ctx_for(env, procs=[P(11, 1, "pi")])).holds
    policy = sessions.load_policy()
    policy["conditions"]["user_active"]["scope"] = "any"
    far = C.Proc(11, 1, "pi", 34818, "pi", "/home/u/other-project")
    assert C.user_active(job(), ctx_for(env, policy=policy, procs=[far])).holds
    policy["conditions"]["user_active"]["scope"] = "nearby"
    with pytest.raises(C.ConditionError, match="scope"):
        C.user_active(job(), ctx_for(env, policy=policy, procs=[far]))


# --- conflict --------------------------------------------------------------------

def conflict_policy(tree, **extra):
    policy = sessions.load_policy()
    policy["conditions"]["conflict"]["processes"] = {
        "nightly": {"at": "03:30", "trees": [str(tree)], "lead": "30m",
                    "lock": "consolidation.lock", **extra}}
    return policy


def test_a_declared_process_due_within_its_lead_holds_an_overlapping_job(env, tmp_path):
    policy = conflict_policy(tmp_path)
    at = lambda h, m: C.Context(policy, env=env, now=NOW.replace(hour=h, minute=m))
    v = C.conflict(job(cwd=str(tmp_path / "sub")), at(3, 10))
    assert v.holds and v.until == NOW.replace(hour=3, minute=30)
    v = C.conflict(job(cwd=str(tmp_path)), at(1, 0))
    assert not v.holds and "outside its 30m lead" in v.reason
    v = C.conflict(job(cwd="/elsewhere"), at(3, 10))
    assert not v.holds and "no declared process" in v.reason


def test_a_job_elsewhere_whose_write_scope_reaches_the_tree_also_conflicts(env, tmp_path):
    policy = conflict_policy(tmp_path)
    ctx = C.Context(policy, env=env, now=NOW.replace(hour=3, minute=10))
    assert C.conflict(job(cwd="/elsewhere", touches=[f"{tmp_path}/memory/**"]), ctx).holds


def test_a_running_process_holds_through_its_lock(env, tmp_path):
    policy = conflict_policy(tmp_path)
    lock = pathlib.Path(env["PAZRAS_DATA_DIR"]) / "consolidation.lock"
    lock.parent.mkdir(parents=True)
    ctx = C.Context(policy, env=env, now=NOW)                  # 01:00, far from 03:30
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        v = C.conflict(job(cwd=str(tmp_path)), ctx)
    assert v.holds and "is running" in v.reason
    assert not C.conflict(job(cwd=str(tmp_path)), ctx).holds


# --- slot ------------------------------------------------------------------------

def test_a_run_in_flight_takes_the_one_slot_but_not_from_itself(env):
    d = sessions.session_dir("busy", env)
    sessions.write_decl(d, {"name": "busy"})
    ctx = ctx_for(env)
    assert not C.slot(job(), ctx).holds
    with sessions.RunLock(d):
        v = C.slot(job(), ctx)
        assert v.holds and "busy" in v.reason
        assert not C.slot(job(name="busy"), ctx).holds


# --- composition -----------------------------------------------------------------

def test_an_unknown_name_is_refused_in_config_and_on_the_command_line(env, tmp_path):
    with pytest.raises(C.ConditionError):
        C.evaluate("moon_phase", job(), ctx_for(env))
    prompt = tmp_path / "p.md"
    prompt.write_text("do it\n")
    base = ["add", "--name", "x", "--in", "10m", "--prompt", str(prompt),
            "--model", "deepseek-flash", "--no-systemctl"]
    with pytest.raises(sessions.SessionError, match="moon_phase"):
        sessions.cmd_add(sessions._parser().parse_args(base + ["--start-when", "moon_phase"]),
                         env=env)
    assert sessions.cmd_add(sessions._parser().parse_args(
        base + ["--start-when", "budget,slot", "--stop-when", "none"]), env=env) == 0
    decl = json.loads((sessions.session_dir("x", env) / "schedule.json").read_text())
    assert decl["start_when"] == ["budget", "slot"] and decl["stop_when"] == []


def test_every_configured_default_is_a_known_condition():
    defaults = sessions.load_config()
    C.validate(defaults["start_when"])
    C.validate(defaults["stop_when"])
    assert set(sessions.load_policy()["conditions"]) == set(C.NAMES)


def test_the_conditions_verb_prints_each_value_and_which_list_names_it(env):
    lines = []
    args = sessions._parser().parse_args(["conditions", "--json"])
    assert sessions.cmd_conditions(args, env=env, out=lines.append,
                                   ctx=ctx_for(env, procs=[P(11, 1, "pi")])) == 0
    rows = {r["condition"]: r for r in json.loads(lines[0])["conditions"]}
    assert set(rows) == set(C.NAMES)
    assert rows["user_active"]["holds"] and rows["user_active"]["role"] == ["start", "stop"]
    assert rows["budget"]["role"] == ["start"] and not rows["budget"]["holds"]
    assert rows["conflict"]["role"] == ["start", "stop"]
