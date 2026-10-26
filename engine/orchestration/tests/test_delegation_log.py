"""The delegation log (item 5c): pi-agent writes one line per delegation, and a
replay of the parent session reproduces it -- with `used` filled in.

No pi is spawned: `subprocess.run` (which `harness/pi_call` calls) is replaced by a fake child that writes the
session log a real `pi -p --session-dir --session-id` would."""
import importlib.machinery
import importlib.util
import json
import pathlib

import pytest

from orchestration import log as delegations

PI_AGENT = pathlib.Path(__file__).resolve().parents[1] / "pi-agent"
ANSWER = ('engine/orchestration/bindings.py:39 "route_confident_at: 0.8"\n'
          "https://example.org/terms \"retention is 30 days for every account\"")
READ = "x" * 9000


def child_log(path: pathlib.Path, answer: str = ANSWER, read: str = READ) -> pathlib.Path:
    rows = [
        {"type": "session", "id": "c"},
        {"type": "model_change", "provider": "deepseek", "modelId": "deepseek-flash"},
        {"type": "thinking_level_change", "thinkingLevel": "low"},
        {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "name": "read", "arguments": {"path": "a.py"}}],
            "usage": {"input": 1000, "output": 50, "cacheRead": 200, "cacheWrite": 0}}},
        {"type": "message", "message": {"role": "toolResult", "toolName": "read",
                                        "content": [{"type": "text", "text": read}]}},
        {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "text", "text": answer}],
            "usage": {"input": 300, "output": 80, "cacheRead": 900, "cacheWrite": 10}}},
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def parent_log(path: pathlib.Path, result: str, *later) -> pathlib.Path:
    rows = [{"type": "message", "message": {"role": "assistant", "content": [
        {"type": "toolCall", "name": "bash", "arguments": {"command": "pi-agent explore 'x'"}}]}},
        {"type": "message", "message": {"role": "toolResult", "toolName": "bash",
                                        "content": [{"type": "text", "text": result}]}}]
    rows += [{"type": "message", "message": {"role": "assistant", "content": c}} for c in later]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_delegation_log_a_line_is_computed_from_the_child_s_own_log(tmp_path):
    ln = delegations.line_for(child_log(tmp_path / "c.jsonl"), "explore", profile="private",
                              exit_code=0)
    assert (ln["role"], ln["model"], ln["profile"], ln["effort"]) == \
        ("explore", "deepseek/deepseek-flash", "private", "low")
    assert ln["usage"] == {"input": 1300, "output": 130, "cache_write": 10,
                           "cache_read": 1100, "frontier": 1440}
    assert ln["bytes_read"] == 9000 and ln["bytes_returned"] == len(ANSWER.encode())
    assert ln["compression"] == round(9000 / len(ANSWER.encode()), 2)
    assert ln["used"] is None, "the child cannot know whether the parent used it"


@pytest.fixture
def pi_agent(monkeypatch, tmp_path):
    loader = importlib.machinery.SourceFileLoader("pi_agent_5c", str(PI_AGENT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    monkeypatch.setattr(mod, "SESSION_DIR", tmp_path / "sessions/pi-agent")
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("PI_PROFILE", raising=False)
    # 12a: pi sets both for every bash tool call, so a test run from inside pi
    # would otherwise attribute its fake delegations to the live session.
    monkeypatch.delenv("PI_SESSION_FILE", raising=False)
    monkeypatch.delenv("PI_SESSION_ID", raising=False)

    class Done:
        returncode = 0
        stdout = stderr = None

    def fake(cmd, **kw):
        sid = cmd[cmd.index("--session-id") + 1]
        child_log(pathlib.Path(cmd[cmd.index("--session-dir") + 1]) / f"2026-10-15T08-00-00-000Z_{sid}.jsonl")
        return Done()

    monkeypatch.setattr(mod.pi_call.subprocess, "run", fake)
    return mod


def test_delegation_log_pi_agent_writes_one_line_and_the_join_key(pi_agent, tmp_path, capsys):
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "deepseek-flash"   # the declared path; the shipped explore.md routes (14g)
    assert pi_agent.run(agent, "find it", str(tmp_path), 60, None, None) == 0
    lines = (tmp_path / "data" / delegations.LOG_NAME).read_text().splitlines()
    assert len(lines) == 1, "one delegation, one line -- and a child without --session counts too"
    ln = json.loads(lines[0])
    assert ln["role"] == "explore" and ln["exit"] == 0 and ln["profile"] == "private"
    err = capsys.readouterr().err
    m = delegations.MARK.search(err)
    assert m and m.group("session") == ln["session"]


def test_delegation_log_a_replayed_session_reproduces_its_line(pi_agent, tmp_path, capsys):
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "deepseek-flash"   # the declared path; the shipped explore.md routes (14g)
    pi_agent.run(agent, "find it", str(tmp_path), 60, None, None)
    written = json.loads((tmp_path / "data" / delegations.LOG_NAME).read_text())
    err = capsys.readouterr().err
    parent = parent_log(tmp_path / "sessions/--x--/p.jsonl", ANSWER + "\n" + err,
                        [{"type": "toolCall", "name": "read",
                          "arguments": {"path": "engine/orchestration/bindings.py"}}])
    [again] = delegations.replay(parent)
    for key in ("role", "model", "effort", "session", "usage", "bytes_read",
                "bytes_returned", "compression"):
        assert again[key] == written[key], key
    assert again["used"] is True, "the parent read the path the child returned"


def test_delegation_log_used_is_false_when_nothing_returned_reappears(tmp_path):
    child = child_log(tmp_path / "sessions/pi-agent/2026_c.jsonl")
    mark = f"pi-agent: delegation role=explore session={child}"
    parent = parent_log(tmp_path / "sessions/--x--/p.jsonl", ANSWER + "\n" + mark,
                        [{"type": "text", "text": "I will look elsewhere."}])
    [ln] = delegations.replay(parent)
    assert ln["used"] is False
    later = [("text", "as found: retention is 30 days for every account")]
    assert delegations.used(ANSWER, later), "a returned line quoted verbatim counts"
    assert delegations.used(ANSWER, [("call", '{"url": "https://example.org/terms"}')])
    assert not delegations.used(ANSWER, [("result", "engine/orchestration/bindings.py")]), \
        "a tool RESULT naming the path is not the parent using it"


def test_delegation_log_cli_replays_parents_and_skips_children(tmp_path, capsys):
    child = child_log(tmp_path / "pi-agent/2026_c.jsonl")
    parent_log(tmp_path / "--x--/p.jsonl", f"pi-agent: delegation role=review session={child}")
    assert delegations.main(["--replay", "5", "--root", str(tmp_path), "--json"]) == 0
    rows = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [r["role"] for r in rows] == ["review"]
    assert delegations.main(["--replay", "5", "--root", str(tmp_path / "none")]) == 2


# --- 12a: the parent's own id on the delegation line --------------------------

def test_delegation_log_parent_comes_from_the_flag_then_the_environment(tmp_path):
    parent = parent_log(tmp_path / "s/--x--/p.jsonl", "nothing")
    other = parent_log(tmp_path / "s/--y--/q.jsonl", "nothing")
    assert delegations.resolve_parent(str(parent), env={}) == parent
    assert delegations.resolve_parent(str(parent), env={"PI_SESSION_FILE": str(other)}) == parent, \
        "the caller's own word wins over the environment"
    assert delegations.resolve_parent(None, env={"PI_SESSION_FILE": str(other)}) == other
    assert delegations.resolve_parent(None, env={"PI_SESSION_FILE": str(tmp_path / "gone")}) is None
    assert delegations.resolve_parent(None, env={}) is None, "a call that passes nothing gets nothing"


def test_delegation_log_parent_resolves_an_id_against_the_sessions_root(tmp_path):
    parent = parent_log(tmp_path / "--x--/2026-10-21T10-00-00-000Z_abc123.jsonl", "nothing")
    child = child_log(tmp_path / "pi-agent/2026-10-21T10-00-01-000Z_abc123.jsonl")
    assert delegations.resolve_parent(None, env={"PI_SESSION_ID": "abc123"},
                                      root=tmp_path) == parent, \
        "a child log carrying the same id is never the parent"
    assert child.is_file()
    assert delegations.resolve_parent(None, env={"PI_SESSION_ID": "nope"}, root=tmp_path) is None


def test_delegation_log_pi_agent_writes_the_parent_it_was_given(pi_agent, tmp_path, capsys):
    parent = parent_log(tmp_path / "s/--x--/p.jsonl", "nothing")
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "deepseek-flash"   # the declared path; the shipped explore.md routes (14g)
    assert pi_agent.run(agent, "find it", str(tmp_path), 60, None, None,
                        parent=str(parent)) == 0
    line = json.loads((tmp_path / "data" / delegations.LOG_NAME).read_text())
    assert line["parent"] == str(parent)
    capsys.readouterr()


def test_delegation_log_no_log_keeps_the_mark_and_writes_no_line(pi_agent, tmp_path, capsys):
    """12c measures readers with `pi-agent --no-log`: the child still runs, its
    usage is still read from its own log, and 5d's uptake denominator stays the
    delegations a parent chose to make."""
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "deepseek-flash"   # the declared path; the shipped explore.md routes (14g)
    assert pi_agent.run(agent, "find it", str(tmp_path), 60, None, None,
                        log=False) == 0
    assert not (tmp_path / "data" / delegations.LOG_NAME).exists()
    err = capsys.readouterr().err
    assert delegations.MARK.search(err) and "(not logged)" in err


def test_delegation_log_write_fills_used_and_keeps_one_line_per_session(tmp_path):
    data = tmp_path / "data" / delegations.LOG_NAME
    child = child_log(tmp_path / "sessions/pi-agent/2026_c.jsonl")
    mark = f"pi-agent: delegation role=explore session={child}"
    parent = parent_log(tmp_path / "sessions/--x--/p.jsonl", ANSWER + "\n" + mark,
                        [{"type": "toolCall", "name": "read",
                          "arguments": {"path": "engine/orchestration/bindings.py"}}])
    wrote = delegations.line_for(child, "explore", exit_code=0)       # what pi-agent writes
    assert wrote["used"] is None
    delegations.append(wrote, data)
    rows = delegations.replay(parent)
    assert [r["used"] for r in rows] == [True]
    assert delegations.upsert(rows, data) == (0, 1), "one line, updated, not a second line"
    [line] = (json.loads(x) for x in data.read_text().splitlines())
    assert line["used"] is True and line["parent"] == str(parent)
    assert delegations.upsert(rows, data) == (0, 0), "a repeat writes nothing"
    assert len(data.read_text().splitlines()) == 1


def test_delegation_log_cli_writes_one_parent_session(tmp_path, capsys):
    data = delegations.log_path()       # the conftest's data directory
    child = child_log(tmp_path / "sessions/pi-agent/2026_c.jsonl")
    mark = f"pi-agent: delegation role=explore session={child}"
    parent = parent_log(tmp_path / "sessions/--x--/p.jsonl", ANSWER + "\n" + mark)
    assert delegations.main(["--parent", str(parent), "--write"]) == 0
    assert "1 line(s) written" in capsys.readouterr().err
    [line] = (json.loads(x) for x in data.read_text().splitlines())
    assert line["used"] is False, "nothing returned reappears later in this parent"
    assert delegations.main(["--parent", str(parent), "--write"]) == 0
    assert len(data.read_text().splitlines()) == 1
    assert delegations.main(["--parent", str(tmp_path / "no.jsonl"), "--write"]) == 2
    assert delegations.main(["--write"]) == 2, "--write without a parent has nothing to close"


def test_pi_agent_never_hands_its_stdin_to_pi(pi_agent, tmp_path, monkeypatch):
    """4e's bound children hung 900 s: `pi -p` read an inherited, never-closing
    socket. The child's stdin must be /dev/null whatever the caller passes.
    Behavioural since 2026-10-20: the spawn is `harness/pi_call`'s, so
    what is checked is what the spawn received, not this file's text."""
    import subprocess
    seen = {}

    class Done:
        returncode = 0
        stdout = stderr = None

    monkeypatch.setattr(pi_agent.pi_call.subprocess, "run",
                        lambda cmd, **kw: seen.update(kw) or Done())
    agent = next(a for a in pi_agent.load_all() if a.name == "explore")
    agent.model = "deepseek-flash"   # the declared path; the shipped explore.md routes (14g)
    pi_agent.run(agent, "find it", str(tmp_path), 60, None, None)
    assert seen["stdin"] is subprocess.DEVNULL
