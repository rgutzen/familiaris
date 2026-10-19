"""opencode_extract: one session's rows out of a synthetic opencode.db,
converted to Claude Code's line shape. The schema mirrors the real DB
(`~/.local/share/opencode/opencode.db`, verified 2026-09-07): `session`,
`message`, `part`, each `data` column a JSON blob, `part` keyed to `message`
by `message_id`.
"""
import json
import sqlite3

import pytest

from cli import cli
from lib import invocation
from context import opencode_extract, transcripts


def _make_db(path, session_id="ses_abc", cwd="/home/rg/06_SYSTEM",
             sess_created=1788593600000):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE session (id text PRIMARY KEY, directory text, time_created integer);
        CREATE TABLE message (id text PRIMARY KEY, session_id text, time_created integer, data text);
        CREATE TABLE part (id text PRIMARY KEY, message_id text, session_id text,
                            time_created integer, data text);
    """)
    conn.execute("INSERT INTO session VALUES (?, ?, ?)", (session_id, cwd, sess_created))

    def msg(mid, role, t):
        conn.execute("INSERT INTO message VALUES (?, ?, ?, ?)",
                     (mid, session_id, t, json.dumps({"role": role, "time": {"created": t}})))

    def part(pid, mid, t, data):
        conn.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                     (pid, mid, session_id, t, json.dumps(data)))

    msg("m1", "user", sess_created)
    part("p1", "m1", sess_created, {"type": "text", "text": "investigate the failing unit"})

    msg("m2", "assistant", sess_created + 1000)
    part("p2a", "m2", sess_created + 1000, {"type": "step-start"})
    part("p2b", "m2", sess_created + 1001,
         {"type": "tool", "tool": "bash", "callID": "c1",
          "state": {"status": "completed", "input": {"command": "pytest"}, "output": "..."}})
    part("p2b2", "m2", sess_created + 1001,
         {"type": "tool", "tool": "edit", "callID": "c2",
          "state": {"status": "completed", "output": "...",
                    "input": {"filePath": "engine/x.py",
                              "oldString": "OLD-BODY", "newString": "NEW-BODY"}}})
    part("p2c", "m2", sess_created + 1002, {"type": "text", "text": "found the cause, fixed it"})
    part("p2d", "m2", sess_created + 1003, {"type": "step-finish", "tokens": {"total": 1}})

    conn.commit()
    conn.close()


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "opencode.db"
    _make_db(p)
    return p


def test_extracts_meta_and_rows(db):
    meta, rows = opencode_extract.extract_session(db, "ses_abc")
    assert meta["cwd"] == "/home/rg/06_SYSTEM"
    assert meta["session"] == "ses_abc"
    assert len(rows) == 2
    assert rows[0]["type"] == "user"
    assert rows[0]["message"]["content"] == [
        {"type": "text", "text": "investigate the failing unit"}]
    assert rows[1]["type"] == "assistant"


def test_drops_step_and_bookkeeping_parts_keeps_text_tool_name_and_paths(db):
    _, rows = opencode_extract.extract_session(db, "ses_abc")
    blocks = rows[1]["message"]["content"]
    assert blocks == [
        {"type": "tool_use", "name": "bash", "input": {"command": "pytest"}},
        {"type": "tool_use", "name": "edit", "input": {"filePath": "engine/x.py"}},
        {"type": "text", "text": "found the cause, fixed it"},
    ]
    # state.output, status and edit bodies never reach the converted output
    dumped = json.dumps(rows)
    assert "completed" not in dumped
    assert "OLD-BODY" not in dumped and "NEW-BODY" not in dumped


def test_staged_paths_reach_tool_calls(db, tmp_path):
    _, rows = opencode_extract.extract_session(db, "ses_abc")
    dest = tmp_path / "s.jsonl"
    opencode_extract.write_jsonl(rows, dest)
    assert list(transcripts.tool_calls(dest)) == [
        ("bash", {"command": "pytest"}), ("edit", {"filePath": "engine/x.py"})]


def test_unknown_session_id_returns_none(db):
    assert opencode_extract.extract_session(db, "ses_nope") is None


def test_missing_db_file_returns_none(tmp_path):
    assert opencode_extract.extract_session(tmp_path / "absent.db", "ses_abc") is None


def test_a_message_with_only_bookkeeping_parts_is_dropped(tmp_path):
    """A message whose every part reduces to nothing (only step-start/finish)
    must not produce an empty content block -- transcripts.reduce() would skip
    it anyway, but an empty row is a row this module should not manufacture."""
    p = tmp_path / "opencode.db"
    conn = sqlite3.connect(p)
    conn.executescript("""
        CREATE TABLE session (id text PRIMARY KEY, directory text, time_created integer);
        CREATE TABLE message (id text PRIMARY KEY, session_id text, time_created integer, data text);
        CREATE TABLE part (id text PRIMARY KEY, message_id text, session_id text,
                            time_created integer, data text);
    """)
    conn.execute("INSERT INTO session VALUES ('ses_x', '/home/rg', 1)")
    conn.execute("INSERT INTO message VALUES ('m1', 'ses_x', 1, ?)",
                 (json.dumps({"role": "assistant"}),))
    conn.execute("INSERT INTO part VALUES ('p1', 'm1', 'ses_x', 1, ?)",
                 (json.dumps({"type": "step-start"}),))
    conn.commit()
    conn.close()
    meta, rows = opencode_extract.extract_session(p, "ses_x")
    assert rows == []


def test_write_jsonl_round_trips_through_the_shared_reducer(db, tmp_path):
    """The point of converting at source: transcripts.py needs no third
    branch of its own -- meta() and reduce() already understand this output."""
    _, rows = opencode_extract.extract_session(db, "ses_abc")
    dest = tmp_path / "out.jsonl"
    opencode_extract.write_jsonl(rows, dest)
    m = transcripts.meta(dest)
    assert m["cwd"] == "/home/rg/06_SYSTEM"
    assert m["session"] == "ses_abc"
    out = transcripts.reduce(dest)
    assert "[USER] investigate the failing unit" in out
    assert "[TOOL] bash" in out
    assert "[ASSISTANT] found the cause, fixed it" in out


# ── cli.opencode_session ─────────────────────────────────────────────────

def _inv(tmp_path, argv):
    return invocation.parse(argv, cli.OPENCODE_SESSION, tmp_path / "data", tmp_path / "agents")


def test_cli_stages_a_transcript_and_logs_the_session(db, tmp_path):
    inv = _inv(tmp_path, [f"--session=ses_abc", f"--db={db}"])
    rc = cli.opencode_session(inv)
    assert rc == 0
    staged = list((tmp_path / "data" / "transcripts").glob("*_opencode_ses_abc.jsonl"))
    assert len(staged) == 1
    log = (tmp_path / "data" / "session.log").read_text()
    assert "opencode\tses_abc\t/home/rg/06_SYSTEM\t" in log


def test_cli_an_unknown_session_writes_nothing_and_exits_clean(db, tmp_path):
    inv = _inv(tmp_path, ["--session=ses_nope", f"--db={db}"])
    rc = cli.opencode_session(inv)
    assert rc == 0
    assert not (tmp_path / "data" / "transcripts").exists()
    assert not (tmp_path / "data" / "session.log").exists()


def test_cli_requires_a_session_id(tmp_path):
    inv = _inv(tmp_path, [])
    assert cli.opencode_session(inv) == 1
