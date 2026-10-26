"""The account a job bills (dev/schedule wave 2): the declaration (2a), the child's
environment (2b), the per-account probe (2c) and the marker check (2d).

WHY. Measured 2026-10-22: a job added from a `pi-work` shell recorded
`"profile": "work"`, and `run` resolved the model under `profiles.active(env)`.
The dispatcher starts runs from `systemd --user`, which carries no `PI_PROFILE`,
so the job would have billed the personal Pro login while its record claimed the
company Team one. `claude-bridge` is the provider id in BOTH profiles, so nothing
in the old code could tell the two apart. These tests pin the four properties that
make the account visible and correct.
"""
from __future__ import annotations

import json
import os
import pathlib

import pytest

from orchestration import profiles
from schedule import conditions as C
from schedule import sessions


class Done:
    def __init__(self, code=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def args_for(*argv):
    return sessions._parser().parse_args(list(argv))


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    """The suite must not depend on the shell that runs it (as test_sessions.py)."""
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
                "DEEPSEEK_API_KEY_WORK", "MISTRAL_API_KEY_WORK"):
        monkeypatch.setenv(var, "test-placeholder")


@pytest.fixture
def env(tmp_path):
    return {"PAZRAS_DATA_DIR": str(tmp_path / "data"),
            "PAZRAS_SESSION_UNITS": str(tmp_path / "units"),
            "PI_CODING_AGENT_DIR": str(tmp_path / "pi-agent")}


@pytest.fixture
def prompt(tmp_path):
    path = tmp_path / "handoff.md"
    path.write_text("# A handoff\n\nDo the thing.\n")
    return path


@pytest.fixture
def marked(tmp_path):
    """A work tree that names its profile the way the dotfiles' `pi()` reads it."""
    tree = tmp_path / "company" / "repo"
    tree.mkdir(parents=True)
    (tmp_path / "company" / ".pi-profile").write_text("work\n")
    return tree


def add(env, prompt, cwd, *extra, profile=None):
    flags = ["--profile", profile] if profile else []
    a = args_for("add", "--name", "job", "--in", "10m", "--prompt", str(prompt),
                 "--model", "deepseek-flash", "--effort", "high", "--cwd", str(cwd),
                 "--no-systemctl", *flags, *extra)
    assert sessions.cmd_add(a, env=env) == 0
    d = sessions.session_dir("job", env)
    return d, json.loads((d / "schedule.json").read_text())


# --- 2a: the declaration ---------------------------------------------------------

def test_the_profile_is_written_even_when_nobody_names_it(env, prompt, tmp_path):
    _, decl = add(env, prompt, tmp_path)
    assert decl["profile"] == "private", "the caller's profile, made explicit"
    assert "profile" not in decl["model"], "one field, not two that can disagree"


def test_a_record_without_the_field_reads_as_the_config_default():
    assert profiles.declared({}) == profiles.load()["default"]
    assert profiles.declared({"profile": "work"}) == "work"
    with pytest.raises(profiles.ProfileError):
        profiles.declared({"profile": "nope"})


# --- 2b: the child's environment -------------------------------------------------

def test_the_account_environment_is_derived_from_the_declaration():
    private = profiles.account_env("private")
    assert private["PI_PROFILE"] == "private"
    assert private["CLAUDE_CONFIG_DIR"] is None, (
        "the primary home stays implicit: pointing Claude at ~/.claude makes it "
        "look for a login that is not there (pi-profile, measured)")
    work = profiles.account_env("work")
    assert work["PI_PROFILE"] == "work"
    assert work["CLAUDE_CONFIG_DIR"].endswith(".claude-work")
    assert work["DEEPSEEK_API_KEY"] is None, "a personal key must not reach a company call"
    assert "DEEPSEEK_API_KEY" not in private, "the private key is the personal one"


def test_the_child_environment_is_a_copy_not_the_callers(tmp_path):
    base = {"PATH": "/usr/bin", "DEEPSEEK_API_KEY": "personal", "KEEP": "1"}
    got = profiles.with_account(base, "work")
    assert got["KEEP"] == "1" and got["PATH"] == "/usr/bin"
    assert got["CLAUDE_CONFIG_DIR"].endswith(".claude-work")
    assert "DEEPSEEK_API_KEY" not in got, "the personal key is removed from the copy"
    assert base["DEEPSEEK_API_KEY"] == "personal", "and the caller's own env is untouched"


def test_the_run_gives_the_child_the_accounts_environment(env, prompt, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(sessions.profiles, "resolve",
                        lambda *a, **k: profiles.Resolution("claude-opus-5-5", "work",
                                                            provider="claude-bridge",
                                                            available=True))
    d, _decl = add(env, prompt, tmp_path, profile="work")

    def driver(argv, prompt, *, cwd, **kw):
        seen.update(kw)
        return {"exit": 0}

    a = args_for("run", "job")
    # A real dispatch hands the engine its own process environment plus the data
    # directory, which is what the child's environment is built from.
    assert sessions.cmd_run(a, env=dict(os.environ, **env), driver=driver, dirty=[]) == 0
    assert seen["env"]["PI_PROFILE"] == "work"
    assert seen["env"]["CLAUDE_CONFIG_DIR"].endswith(".claude-work")
    # A FULL environment, not a patch: `pi_call.env_for(base=...)` REPLACES what it
    # is given, so an overlay passed straight through starts `pi` with no PATH and
    # the run dies before it begins (measured 2026-10-22).
    assert "PATH" in seen["env"] and "HOME" in seen["env"]
    events = sessions.read_events(d)
    started = [e for e in events if e["event"] == "started"][-1]
    assert started["profile"] == "work", "the record says which account the run spent"
    assert [e for e in events if e["event"] == "finished"][-1]["exit"] == 0


def test_the_dry_run_says_which_account_the_child_would_get(env, prompt, tmp_path, monkeypatch):
    monkeypatch.setattr(sessions.profiles, "resolve",
                        lambda *a, **k: profiles.Resolution("claude-opus-5-5", "work",
                                                            provider="claude-bridge",
                                                            available=True))
    add(env, prompt, tmp_path, profile="work")
    a = args_for("run", "job", "--dry-run")
    said = []
    assert sessions.cmd_run(a, env=env, dirty=[], out=said.append) == 0
    shown = json.loads(said[0])
    assert shown["profile"] == "work"
    assert shown["account_env"]["PI_PROFILE"] == "work"
    assert shown["account_env"]["CLAUDE_CONFIG_DIR"].endswith(".claude-work")


def test_the_reset_note_names_the_account_the_run_spends(tmp_path, monkeypatch):
    calls = []

    def fake(ctx, profile=None):
        calls.append(profile)
        return C.Reading("work", "Team",
                         {"five_hour": (0.2, __import__("datetime").datetime(
                             2026, 10, 22, 23, 50, tzinfo=__import__("datetime").timezone(
                                 __import__("datetime").timedelta(hours=2))))})

    monkeypatch.setattr(C, "read_budget", fake)
    decl = {"name": "j", "model": {"pi_model": "claude-bridge/claude-opus-5-5"},
            "profile": "work"}
    note = sessions._window_reset(decl, {})
    assert calls == ["work"], "the probe is asked about the JOB's account"
    assert "work · Team" in note


# --- 2c: the probe ---------------------------------------------------------------

def _ctx(env, probe, clock=1000.0):
    return C.Context(sessions.load_policy(), env=env, procs=lambda: [],
                     probe=probe, clock=lambda: clock, tty_seen=lambda tty: clock)


def _limits(five=0.2):
    return {"tierLabel": "Team",
            "limits": [{"label": "Session (5-hour)", "percent": five,
                        "resetsAt": "2026-10-21T03:29:59+00:00"}]}


def test_two_accounts_never_share_a_reading(env, prompt, tmp_path):
    """The tool's own reuse window is ONE file with no account in its key (measured:
    a Work probe seconds after a personal one returned the personal numbers), so
    the engine's cache is keyed by profile and each probe gets its account's env."""
    seen = []

    def probe(argv, acct):
        seen.append((acct.get("CLAUDE_CONFIG_DIR"), argv, acct.get("XDG_CACHE_HOME")))
        return _limits()

    ctx = _ctx(env, probe)
    C.read_budget(ctx, "private")
    C.read_budget(ctx, "work")
    C.read_budget(ctx, "private")                     # cached: no third call
    assert [s[0] for s in seen] == [None, str(pathlib.Path.home() / ".claude-work")]
    assert "--force" in seen[0][1], "the reuse window would answer for the wrong account"
    # Each account also gets its OWN tool cache root: shared, a 429 falls back to
    # whatever account probed last and the reading says nothing about it.
    assert seen[0][2] != seen[1][2] and seen[0][2].endswith("/private")
    saved = json.loads((profiles.data_dir(env) / "sessions" / "budget.json").read_text())
    assert set(saved) == {"private", "work"}


def test_the_reason_says_which_account_was_read(env):
    v = C.budget({"name": "j", "cwd": "/tmp", "profile": "private",
                  "model": {"pi_model": "claude-bridge/claude-opus-5-5"}},
                 _ctx(env, lambda argv, acct: _limits()))
    assert "private · Team" in v.reason


def test_an_undeclared_profile_holds_instead_of_spending_something(env):
    v = C.budget({"name": "j", "cwd": "/tmp", "profile": "nope",
                  "model": {"pi_model": "claude-bridge/claude-opus-5-5"}},
                 _ctx(env, lambda argv, acct: _limits()))
    assert v.holds and "nope" in v.reason


# --- 2d: the marker --------------------------------------------------------------

def test_the_marker_is_the_nearest_one_at_or_above_the_tree(marked):
    name, path = profiles.marker(marked)
    assert name == "work" and path.name == ".pi-profile"
    assert profiles.marker(marked.parent.parent) == ("", None)


def test_add_refuses_a_tree_marked_for_another_profile(env, prompt, marked):
    with pytest.raises(sessions.SessionError) as e:
        add(env, prompt, marked)
    assert "work" in str(e.value) and "--profile work" in str(e.value)


def test_add_accepts_the_profile_the_tree_names(env, prompt, marked):
    _, decl = add(env, prompt, marked, profile="work")
    assert decl["profile"] == "work"


def test_a_run_refuses_when_the_tree_changed_its_mind(env, prompt, tmp_path, monkeypatch):
    monkeypatch.setattr(sessions.profiles, "resolve",
                        lambda *a, **k: profiles.Resolution("claude-opus-5-5", "private",
                                                            provider="claude-bridge",
                                                            available=True))
    d, decl = add(env, prompt, tmp_path)
    (tmp_path / ".pi-profile").write_text("work\n")
    called = []
    code = sessions.cmd_run(args_for("run", "job"), env=env, dirty=[],
                            driver=lambda *a, **k: called.append(a) or {"exit": 0})
    assert code == 2 and not called
    row = sessions.read_events(d)[-1]
    assert row["event"] == "refused" and "work" in row["reason"]


def test_check_reports_a_record_whose_tree_names_another_profile(env, prompt, tmp_path):
    d, decl = add(env, prompt, tmp_path)
    assert sessions.self_check(decl, d, env, run=lambda *a, **k: Done(0)) == []
    (tmp_path / ".pi-profile").write_text("work\n")
    findings = sessions.self_check(decl, d, env, run=lambda *a, **k: Done(0))
    assert any(k == "DRIFT" and what == "profile" for k, what, _ in findings), findings
