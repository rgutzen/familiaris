"""pi_call through its interface, against a fake `pi` first on PATH.

The fake is an executable, not a mock: it is what a real child sees -- its argv,
its environment, its cwd, and above all what its stdin is. `FAKE_PI` selects its
behaviour; every run writes what it saw to `$FAKE_PI_SEEN`.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

from harness import pi_call

FAKE = r'''#!{python}
import json, os, sys, time
mode = os.environ.get("FAKE_PI", "ok")
with open(os.environ["FAKE_PI_SEEN"], "w") as fh:
    json.dump({{"argv": sys.argv[1:], "stdin": os.readlink("/proc/self/fd/0"),
               "cwd": os.getcwd(), "no_color": os.environ.get("NO_COLOR"),
               "extra": os.environ.get("EXTRA")}}, fh)
if mode == "sleep": time.sleep(5)
if mode == "fail": sys.stderr.write("boom\n"); sys.exit(3)
if mode == "empty": sys.exit(0)
if mode == "ansi": print("\x1b[31mred\x1b[0m answer"); sys.exit(0)
print("models table" if sys.argv[1:] == ["--list-models"] else "the answer")
'''


@pytest.fixture
def fake(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "pi"
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(0o755)
    seen = tmp_path / "seen.json"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_PI_SEEN", str(seen))
    monkeypatch.delenv("FAKE_PI", raising=False)
    return lambda: json.loads(seen.read_text())


def test_stdin_is_never_inherited_even_from_an_open_pipe(fake):
    """The hazard this module exists for: run with this process's stdin an open
    pipe, as a pi extension's spawn hands one over, and the child must see
    /dev/null."""
    r, w = os.pipe()
    saved = os.dup(0)
    os.dup2(r, 0)
    try:
        assert pi_call.answer("hi", approve=False, session=None) == "the answer"
    finally:
        os.dup2(saved, 0)
        os.close(r), os.close(w), os.close(saved)
    assert fake()["stdin"] == "/dev/null"


def test_the_module_sets_no_color_and_the_caller_adds_env(fake):
    pi_call.answer("hi", approve=False, session=None, env_extra={"EXTRA": "x"})
    seen = fake()
    assert seen["no_color"] == "1" and seen["extra"] == "x"


def test_cwd_defaults_to_tmp_and_the_caller_may_move_it(fake, tmp_path):
    pi_call.answer("hi", approve=False, session=None)
    assert fake()["cwd"] == "/tmp"
    pi_call.answer("hi", approve=False, session=None, cwd=tmp_path)
    assert fake()["cwd"] == str(tmp_path)


def test_every_caller_choice_reaches_the_command_line(fake, tmp_path):
    s = pi_call.Session(tmp_path / "s", "abc")
    pi_call.answer("task", approve=True, session=s, model="ollama/x",
                   system_prompt=tmp_path / "sys.md", bare=True,
                   tools=("read", "grep"), thinking="high")
    a = fake()["argv"]
    assert a[:2] == ["-p", "task"]
    for pair in (["--system-prompt", str(tmp_path / "sys.md")], ["--tools", "read,grep"],
                 ["--model", "ollama/x"], ["--thinking", "high"],
                 ["--session-dir", str(tmp_path / "s")], ["--session-id", "abc"]):
        i = a.index(pair[0])
        assert a[i:i + 2] == pair
    assert {"-nc", "-ns", "--approve"} <= set(a)
    assert "--no-session" not in a and "--no-approve" not in a


def test_no_session_and_no_approve_and_no_tools(fake):
    pi_call.answer("t", approve=False, session=None, tools=())
    a = fake()["argv"]
    assert {"--no-session", "--no-approve", "--no-tools"} <= set(a)
    assert "--approve" not in a and "--session-dir" not in a


def test_approve_and_session_have_no_default():
    with pytest.raises(TypeError):
        pi_call.argv("t", session=None)            # approve missing
    with pytest.raises(TypeError):
        pi_call.argv("t", approve=False)            # session missing


@pytest.mark.parametrize("mode,match", [("fail", "boom"), ("empty", "empty response")])
def test_answer_maps_a_failure_to_one_error(fake, monkeypatch, mode, match):
    monkeypatch.setenv("FAKE_PI", mode)
    with pytest.raises(pi_call.PiError, match=match):
        pi_call.answer("t", approve=False, session=None)


def test_answer_maps_a_timeout_to_the_same_error(fake, monkeypatch):
    monkeypatch.setenv("FAKE_PI", "sleep")
    with pytest.raises(pi_call.PiError, match="timed out"):
        pi_call.answer("t", approve=False, session=None, timeout=0.5)


def test_run_reports_rather_than_raises(fake, monkeypatch):
    monkeypatch.setenv("FAKE_PI", "fail")
    r = pi_call.run("t", approve=False, session=None)
    assert r.returncode == 3 and "boom" in r.stderr
    monkeypatch.setenv("FAKE_PI", "sleep")
    r = pi_call.run("t", approve=False, session=None, timeout=0.5)
    assert r.timed_out and r.returncode == pi_call.TIMED_OUT


def test_run_writes_to_a_file_the_caller_names(fake, tmp_path):
    log = tmp_path / "log"
    with log.open("w") as fh:
        pi_call.run("t", approve=True, session=None, stdout=fh, stderr=subprocess.STDOUT)
    assert log.read_text().strip() == "the answer"


def test_ansi_is_stripped_from_an_answer(fake, monkeypatch):
    monkeypatch.setenv("FAKE_PI", "ansi")
    assert pi_call.answer("t", approve=False, session=None) == "red answer"


def test_wrap_transforms_the_argv_before_the_spawn(fake, tmp_path):
    """`eval`'s bubblewrap is a wrap: here a no-op prefix (`env`) proves the
    transform runs and that the child is still the module's spawn."""
    seen = {}

    def wrap(cmd, cwd):
        seen["cwd"] = cwd
        return ["env", *cmd]
    pi_call.answer("t", approve=False, session=None, cwd=tmp_path, wrap=wrap)
    assert seen["cwd"] == tmp_path and fake()["stdin"] == "/dev/null"


def test_list_models_shares_the_guards(fake, monkeypatch):
    assert pi_call.list_models() == "models table\n"
    assert fake()["stdin"] == "/dev/null" and fake()["argv"] == ["--list-models"]
    monkeypatch.setenv("FAKE_PI", "fail")
    with pytest.raises(pi_call.PiError, match="exited 3"):
        pi_call.list_models()


def test_pi_absent_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(pi_call.PiError):
        pi_call.answer("t", approve=False, session=None)
