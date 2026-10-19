"""hermes_extract: one Hermes session, converted to Claude Code's line shape.

The fixture below mirrors hermes-agent's own test fixture
(tests/hermes_cli/test_session_export.py::_sample_session, read 2026-09-07)
plus a real export's top-level fields (id/cwd/git_branch/started_at,
verified against a live session the same day).
"""
import io
import json
import stat
import textwrap

from cli import cli
from context import hermes_extract, transcripts
from lib import invocation

SESSION_OBJ = {
    "id": "20260907_100000_abcdef",
    "cwd": "/home/rg/06_SYSTEM",
    "git_branch": "main",
    "started_at": 1788768000,
    "messages": [
        {"id": 1, "role": "user", "content": "inspect the auth middleware",
         "timestamp": 1788768000},
        {"id": 2, "role": "assistant",
         "content": "I will inspect the auth middleware.",
         "reasoning": "let me check the redirect logic first",
         "tool_calls": [{"id": "call_1", "type": "function",
                         "function": {"name": "read_file", "arguments": "{\"path\": \"x\"}"}}],
         "timestamp": 1788768002},
        {"id": 3, "role": "tool", "tool_name": "read_file",
         "content": "def redirect_after_login(): pass", "timestamp": 1788768003},
        {"id": 4, "role": "user",
         "content": [{"type": "text", "text": "found it, thanks"}],
         "timestamp": 1788768004},
    ],
}


def _fake_hermes_bin(tmp_path, obj=SESSION_OBJ, exit_code=0):
    """A script standing in for `hermes sessions export ... --format=jsonl -`."""
    script = tmp_path / "fake-hermes"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        echo '{json.dumps(obj)}'
        exit {exit_code}
        """))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_extracts_meta_and_converts_messages(tmp_path):
    result = hermes_extract.extract_session(
        "20260907_100000_abcdef", hermes_bin=_fake_hermes_bin(tmp_path))
    assert result is not None
    meta, rows = result
    assert meta["cwd"] == "/home/rg/06_SYSTEM"
    assert meta["branch"] == "main"
    assert meta["session"] == "20260907_100000_abcdef"
    assert len(rows) == 3, "the `tool` role message is dropped"
    assert [r["type"] for r in rows] == ["user", "assistant", "user"]


def test_assistant_message_carries_text_thinking_and_tool_use(tmp_path):
    _, rows = hermes_extract.extract_session(
        "20260907_100000_abcdef", hermes_bin=_fake_hermes_bin(tmp_path))
    blocks = rows[1]["message"]["content"]
    assert {"type": "text", "text": "I will inspect the auth middleware."} in blocks
    assert {"type": "thinking", "thinking": "let me check the redirect logic first"} in blocks
    assert {"type": "tool_use", "name": "read_file"} in blocks
    # tool_calls[].function.arguments never appears -- dropped, same as
    # Claude Code's tool_use.input
    assert "path" not in json.dumps(blocks)


def test_a_block_shaped_content_list_passes_through(tmp_path):
    _, rows = hermes_extract.extract_session(
        "20260907_100000_abcdef", hermes_bin=_fake_hermes_bin(tmp_path))
    assert rows[2]["message"]["content"] == [{"type": "text", "text": "found it, thanks"}]


def test_tool_role_message_and_its_output_never_appear(tmp_path):
    _, rows = hermes_extract.extract_session(
        "20260907_100000_abcdef", hermes_bin=_fake_hermes_bin(tmp_path))
    assert "redirect_after_login" not in json.dumps(rows)


def test_a_session_id_that_does_not_match_the_export_returns_none(tmp_path):
    # the fake script always echoes SESSION_OBJ regardless of args, so this
    # simulates `--session-id` resolving to nothing matching by exact id
    assert hermes_extract.extract_session(
        "some-other-id", hermes_bin=_fake_hermes_bin(tmp_path)) is None


def test_a_nonzero_exit_is_treated_as_no_export(tmp_path):
    assert hermes_extract.extract_session(
        "20260907_100000_abcdef",
        hermes_bin=_fake_hermes_bin(tmp_path, exit_code=1)) is None


def test_hermes_binary_not_found_returns_none():
    assert hermes_extract.extract_session(
        "any", hermes_bin="/nonexistent/hermes-binary-xyz") is None


def test_write_jsonl_round_trips_through_the_shared_reducer(tmp_path):
    _, rows = hermes_extract.extract_session(
        "20260907_100000_abcdef", hermes_bin=_fake_hermes_bin(tmp_path))
    dest = tmp_path / "out.jsonl"
    hermes_extract.write_jsonl(rows, dest)
    m = transcripts.meta(dest)
    assert m["cwd"] == "/home/rg/06_SYSTEM"
    assert m["branch"] == "main"
    assert m["session"] == "20260907_100000_abcdef"
    out = transcripts.reduce(dest)
    assert "[USER] inspect the auth middleware" in out
    assert "[ASSISTANT] I will inspect the auth middleware." in out
    assert "[ASSISTANT(thinking)] let me check the redirect logic first" in out
    assert "[TOOL] read_file" in out
    assert "[USER] found it, thanks" in out


# ── cli.hermes_session_worker ────────────────────────────────────────────

def _inv(tmp_path, argv, spec=cli.HERMES_SESSION_WORKER):
    return invocation.parse(argv, spec, tmp_path / "data", tmp_path / "agents")


def test_worker_stages_a_transcript_and_logs_the_session(tmp_path, monkeypatch):
    monkeypatch.setattr(
        hermes_extract, "extract_session",
        lambda sid, **kw: ({"cwd": "/home/rg/06_SYSTEM"},
                           [{"type": "user", "sessionId": sid,
                             "message": {"content": [{"type": "text", "text": "hi"}]}}]))
    inv = _inv(tmp_path, ["--session=sess-1"])
    rc = cli.hermes_session_worker(inv)
    assert rc == 0
    staged = list((tmp_path / "data" / "transcripts").glob("*_hermes_sess-1.jsonl"))
    assert len(staged) == 1
    log = (tmp_path / "data" / "session.log").read_text()
    assert "hermes\tsess-1\t/home/rg/06_SYSTEM\t" in log


def test_worker_an_unresolved_session_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(hermes_extract, "extract_session", lambda sid, **kw: None)
    inv = _inv(tmp_path, ["--session=sess-nope"])
    rc = cli.hermes_session_worker(inv)
    assert rc == 0
    assert not (tmp_path / "data" / "transcripts").exists()


def test_worker_requires_a_session_id(tmp_path):
    assert cli.hermes_session_worker(_inv(tmp_path, [])) == 1


def test_hook_facing_command_hands_off_and_never_blocks(tmp_path, monkeypatch):
    """`hermes_session` (the synchronous half) must not itself do the
    extraction -- it only reads session_id off stdin and detaches a worker.
    """
    calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    inv = _inv(tmp_path, [], spec=cli.HERMES_SESSION)
    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"session_id": "sess-1", "cwd": "/home/rg/06_SYSTEM"})))
    rc = cli.hermes_session(inv)
    assert rc == 0
    assert len(calls) == 1
    argv = calls[0][0][0]
    assert "hermes-session-worker" in argv
    assert "--session=sess-1" in argv


def test_hook_facing_command_with_no_session_id_does_nothing(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    inv = _inv(tmp_path, [], spec=cli.HERMES_SESSION)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    rc = cli.hermes_session(inv)
    assert rc == 0
    assert calls == []
