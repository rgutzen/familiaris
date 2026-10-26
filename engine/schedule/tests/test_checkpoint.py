"""checkpoint (dev/schedule 1c): a run stops at an item boundary when a stop condition holds.

The checkpoint is the agent's own question before each item; the backstop is the
dispatcher's answer when the agent does not stop in time and the condition says
it must (a conflict's due time). Both write the record first.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess

import pytest

from schedule import conditions as C
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
def job(env, tmp_path):
    prompt = tmp_path / "handoff.md"
    prompt.write_text("do it\n")
    a = sessions._parser().parse_args(
        ["add", "--name", "job", "--in", "10m", "--prompt", str(prompt),
         "--model", "deepseek-flash", "--cwd", str(tmp_path), "--no-systemctl"])
    assert sessions.cmd_add(a, env=env) == 0
    d = sessions.session_dir("job", env)
    return d, json.loads((d / "schedule.json").read_text())


def run_fake(argv, **kw):
    if argv[0] == "bash":
        return subprocess.run(argv, **kw)
    return Done(0)


def P(pid, ppid, comm, tty=34818):
    return C.Proc(pid, ppid, comm, tty, comm)


def ctx_with(env, procs=(), now=None, policy=None):
    return C.Context(policy or sessions.load_policy(), env=env, now=now,
                     procs=lambda: list(procs), probe=lambda a: {"limits": []},
                     tty_seen=lambda tty: None)


def checkpoint(env, ctx, lines, *extra, lineage=lambda: [os.getpid()]):
    args = sessions._parser().parse_args(["checkpoint", "--job", "job", *extra])
    return sessions.cmd_checkpoint(args, env=env, out=lines.append, ctx=ctx, lineage=lineage)


def events_of(d, kind):
    return [e for e in sessions.read_events(d) if e.get("event") == kind]


# --- the checkpoint ---------------------------------------------------------------

def test_no_stop_condition_holding_means_continue_and_the_boundary_is_recorded(env, job):
    d, _ = job
    lines = []
    with sessions.RunLock(d):
        assert checkpoint(env, ctx_with(env), lines, "--item", "1b") == 0
    assert lines[-1].startswith("continue")
    cp = events_of(d, "checkpoint")[-1]
    assert cp["stop"] is False and cp["item"] == "1b"
    assert cp["checked"] == ["user_active", "conflict"]


def test_the_user_starting_to_work_stops_the_run_at_its_next_item(env, job):
    d, _ = job
    lines = []
    with sessions.RunLock(d):
        code = checkpoint(env, ctx_with(env, procs=[P(11, 1, "pi")]), lines)
    assert code == sessions.STOP == 10
    assert any("user_active" in line and "pi (pid 11)" in line for line in lines)
    cp = events_of(d, "checkpoint")[-1]
    assert cp["stop"] is True and "user_active" in cp["holding"]


def test_checkpoint_refuses_outside_a_run_of_its_job(env, job):
    d, _ = job
    with pytest.raises(sessions.SessionError, match="not inside a run"):
        checkpoint(env, ctx_with(env), [])                    # no run holds the lock
    with sessions.RunLock(d):
        with pytest.raises(sessions.SessionError, match="not inside a run"):
            checkpoint(env, ctx_with(env), [], lineage=lambda: [12345])
    args = sessions._parser().parse_args(["checkpoint"])
    with pytest.raises(sessions.SessionError, match=sessions.JOB_ENV):
        sessions.cmd_checkpoint(args, env=env, out=print)
    assert events_of(d, "checkpoint") == []


def test_the_run_names_its_job_to_its_children(env, job, monkeypatch):
    seen = {}

    def driver(argv, prompt, *, cwd, log, **kw):
        seen.update({k: os.environ.get(k) for k in (sessions.JOB_ENV, sessions.RUN_ENV)})
        return {"exit": 0}

    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    assert sessions.cmd_run(sessions._parser().parse_args(["run", "job"]), env=env,
                            dirty=[], driver=driver, run=run_fake) == 0
    assert seen[sessions.JOB_ENV] == "job" and seen[sessions.RUN_ENV]
    assert sessions.JOB_ENV not in os.environ, "restored after the run"


def test_a_real_checkpoint_from_inside_a_run_finds_its_job_by_the_environment(env, job,
                                                                           monkeypatch):
    """No seam: a child process the run starts calls `checkpoint` with no flag."""
    d, _ = job
    engine = __import__("pathlib").Path(sessions.__file__).resolve().parents[1]
    codes = []

    def driver(argv, prompt, *, cwd, log, **kw):
        p = subprocess.run(
            ["python3", "-c", "import sys; from schedule import sessions; "
             "sys.exit(sessions.main(['checkpoint', '--item', '1x']))"],
            cwd=engine, env={**os.environ, **env, "PYTHONPATH": str(engine)},
            capture_output=True, text=True)
        codes.append(p.returncode)
        log.write(p.stdout + p.stderr)
        return {"exit": 0}

    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    sessions.cmd_run(sessions._parser().parse_args(["run", "job"]), env=env, dirty=[],
                     driver=driver, run=run_fake)
    cp = events_of(d, "checkpoint")
    assert codes and codes[0] in (0, sessions.STOP), codes
    assert cp and cp[0]["item"] == "1x"


def test_a_run_that_stopped_at_a_checkpoint_says_so_in_its_finished_row(env, job, monkeypatch):
    d, _ = job

    def driver(argv, prompt, *, cwd, log, **kw):
        checkpoint(env, ctx_with(env, procs=[P(11, 1, "pi")]), [])
        return {"exit": 0}

    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    sessions.cmd_run(sessions._parser().parse_args(["run", "job"]), env=env, dirty=[],
                     driver=driver, run=run_fake)
    assert "user_active" in events_of(d, "finished")[-1]["checkpoint_stop"]


# --- the backstop -----------------------------------------------------------------

def conflict_policy(tree):
    policy = sessions.load_policy()
    policy["conditions"]["conflict"]["processes"] = {
        "nightly": {"at": "03:30", "trees": [str(tree)], "lead": "30m"}}
    return policy


TZ = dt.datetime.now().astimezone().tzinfo


def at(h, m):
    return dt.datetime(2026, 10, 21, h, m, tzinfo=TZ)


def test_the_users_activity_never_interrupts_a_run(env, job):
    d, decl = job
    with sessions.RunLock(d):
        assert sessions.backstop(d, decl, ctx_with(env, procs=[P(11, 1, "pi")])) is None


def test_a_conflict_interrupts_the_run_at_its_due_time_and_not_before(env, job, tmp_path):
    d, decl = job
    policy = conflict_policy(tmp_path)
    with sessions.RunLock(d):
        early = sessions.backstop(d, decl, ctx_with(env, now=at(3, 10), policy=policy),
                                  now=at(3, 10))
        due = sessions.backstop(d, decl, ctx_with(env, now=at(3, 30), policy=policy),
                                now=at(3, 30))
    assert early is None
    assert due["condition"] == "conflict" and due["pid"] == os.getpid()
    # No run in flight, nothing to interrupt.
    assert sessions.backstop(d, decl, ctx_with(env, now=at(3, 30), policy=policy),
                             now=at(3, 30)) is None


def test_a_delay_backstop_counts_from_when_the_run_first_saw_the_condition(env, job):
    d, decl = job
    policy = sessions.load_policy()
    policy["conditions"]["user_active"]["hard_stop"] = "20m"
    sessions.write_event(d, {"event": "started", "ts": at(1, 0).isoformat()})
    ctx = lambda now: ctx_with(env, procs=[P(11, 1, "pi")], now=now, policy=policy)
    with sessions.RunLock(d):
        assert sessions.backstop(d, decl, ctx(at(1, 5)), now=at(1, 5)) is None
        assert events_of(d, "stop_held")[0]["ts"] == at(1, 5).isoformat()
        assert sessions.backstop(d, decl, ctx(at(1, 20)), now=at(1, 20)) is None
        hit = sessions.backstop(d, decl, ctx(at(1, 25)), now=at(1, 25))
    assert hit and hit["condition"] == "user_active"
    assert len(events_of(d, "stop_held")) == 1


def test_interrupt_writes_the_event_before_it_signals(env, job):
    d, decl = job
    order = []

    def kill(pid):
        order.append(("kill", pid, [e["event"] for e in sessions.read_events(d)]))

    sessions.interrupt(d, decl, {"pid": 4242, "condition": "conflict", "reason": "due",
                                 "until": None}, kill=kill)
    assert order == [("kill", 4242, ["backstop"])]


def test_an_interrupted_run_is_recorded_and_held_on_the_same_job(env, job, monkeypatch):
    d, _ = job

    def driver(argv, prompt, *, cwd, log, **kw):
        sessions.write_event(d, {"event": "backstop", "ts": sessions.now_local().isoformat(),
                                 "condition": "conflict", "reason": "nightly due 03:30"})
        raise KeyboardInterrupt

    monkeypatch.setattr(sessions, "git_dirty", lambda cwd: [])
    code = sessions.cmd_run(sessions._parser().parse_args(["run", "job"]), env=env, dirty=[],
                            driver=driver, run=run_fake)
    assert code == 130
    fin = events_of(d, "finished")[-1]
    assert fin["interrupted"] is True and fin["exit"] == 130
    held = events_of(d, "held")[-1]
    assert "backstop" in held["why"] and "conflict" in held["why"]
    assert not sessions.RunLock(d).held(), "the locks are released"


def test_every_condition_declares_its_hard_stop():
    policy = sessions.load_policy()
    for name in C.NAMES:
        hard = policy["conditions"][name].get("hard_stop")
        assert hard in ("none", "due") or sessions.parse_delay(hard), name
    assert policy["conditions"]["user_active"]["hard_stop"] == "none"
    assert policy["conditions"]["conflict"]["hard_stop"] == "due"
