"""transcripts.meta()/reduce() must understand both line shapes staged today:
Claude Code's (`type: "user"|"assistant"`, content under `message`) and Pi's
(`type: "message"` envelope, role under `message.role`, `toolCall` blocks
instead of `tool_use`). Neither replay.py nor the model prompt should need to
know which harness a transcript came from -- these tests pin that.
"""
import json

from context import transcripts

CLAUDE_ROWS = [
    {"type": "user", "cwd": "/home/rg/06_SYSTEM", "gitBranch": "main",
     "sessionId": "sess-claude", "timestamp": "2026-09-03T10:00:00Z",
     "message": {"content": "investigate the failing unit"}},
    {"type": "assistant", "sessionId": "sess-claude",
     "message": {"content": [
         {"type": "thinking", "thinking": "let me look at the traceback"},
         {"type": "text", "text": "found the cause, fixed it"},
         {"type": "tool_use", "name": "bash", "input": {"command": "pytest"}},
     ]}},
]

PI_ROWS = [
    {"type": "session", "version": 3, "id": "sess-pi",
     "timestamp": "2026-09-05T19:18:55.096Z", "cwd": "/home/rg/06_SYSTEM"},
    {"type": "model_change", "id": "m1", "parentId": None,
     "timestamp": "2026-09-05T19:18:56Z", "provider": "ollama", "modelId": "x"},
    {"type": "message", "id": "u1", "parentId": "m1",
     "timestamp": "2026-09-05T19:18:57Z",
     "message": {"role": "user", "content": [
         {"type": "text", "text": "investigate the failing unit"}]}},
    {"type": "message", "id": "a1", "parentId": "u1",
     "timestamp": "2026-09-05T19:19:00Z",
     "message": {"role": "assistant", "content": [
         {"type": "text", "text": "found the cause, fixed it"},
         {"type": "toolCall", "id": "call1", "name": "bash",
          "arguments": {"command": "pytest"}},
     ]}},
]


def _write(tmp_path, name, rows):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_meta_reads_claude_shape(tmp_path):
    p = _write(tmp_path, "claude.jsonl", CLAUDE_ROWS)
    m = transcripts.meta(p)
    assert m == {"cwd": "/home/rg/06_SYSTEM", "branch": "main",
                 "date": "2026-09-03", "session": "sess-claude"}


def test_meta_reads_pi_shape(tmp_path):
    p = _write(tmp_path, "pi.jsonl", PI_ROWS)
    m = transcripts.meta(p)
    assert m["cwd"] == "/home/rg/06_SYSTEM"
    assert m["date"] == "2026-09-05"
    assert m["session"] == "sess-pi"


def test_meta_does_not_mistake_a_pi_message_id_for_the_session_id(tmp_path):
    # The "id" key on a `type: "message"` line is a per-message id, not the
    # session id -- only the `type: "session"` line's "id" counts.
    p = _write(tmp_path, "pi.jsonl", PI_ROWS[1:])  # drop the session line
    m = transcripts.meta(p)
    assert m["session"] == ""


def test_reduce_extracts_prose_and_tool_names_from_claude_shape(tmp_path):
    p = _write(tmp_path, "claude.jsonl", CLAUDE_ROWS)
    out = transcripts.reduce(p)
    assert "[USER] investigate the failing unit" in out
    assert "[ASSISTANT(thinking)] let me look at the traceback" in out
    assert "[ASSISTANT] found the cause, fixed it" in out
    assert "[TOOL] bash" in out


def test_reduce_extracts_prose_and_tool_names_from_pi_shape(tmp_path):
    p = _write(tmp_path, "pi.jsonl", PI_ROWS)
    out = transcripts.reduce(p)
    assert "[USER] investigate the failing unit" in out
    assert "[ASSISTANT] found the cause, fixed it" in out
    assert "[TOOL] bash" in out
    # session / model_change / thinking_level_change lines are ignored, not
    # mistaken for a turn
    assert "model_change" not in out


def test_reduce_two_shapes_yield_equivalent_output(tmp_path):
    """Same conversation, two harnesses, same reduction -- the model prompt
    in stages/replay.py must not be able to tell them apart."""
    claude = transcripts.reduce(_write(tmp_path, "c.jsonl", CLAUDE_ROWS))
    pi = transcripts.reduce(_write(tmp_path, "p.jsonl", PI_ROWS))
    assert "[USER] investigate the failing unit" in claude
    assert "[USER] investigate the failing unit" in pi
    assert "[TOOL] bash" in claude and "[TOOL] bash" in pi


# ── tool_calls: the inputs reduce() drops (C2) ──────────────────────────────

def test_tool_calls_keeps_the_inputs_both_shapes_carry(tmp_path):
    """`reduce()` throws the inputs away because it is building a prompt.
    `touches:` is built from them, so the walk is shared (`_turns`) and only
    the payload differs between harnesses: `input` vs `arguments`."""
    claude = list(transcripts.tool_calls(_write(tmp_path, "c.jsonl", CLAUDE_ROWS)))
    pi = list(transcripts.tool_calls(_write(tmp_path, "p.jsonl", PI_ROWS)))
    assert claude == [("bash", {"command": "pytest"})]
    assert pi == [("bash", {"command": "pytest"})]


def test_tool_calls_yields_nothing_for_a_transcript_with_no_calls(tmp_path):
    rows = [{"type": "user", "message": {"content": "just prose"}},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "and no tools"}]}}]
    assert list(transcripts.tool_calls(_write(tmp_path, "t.jsonl", rows))) == []


def test_tool_calls_is_empty_when_staging_dropped_the_arguments(tmp_path):
    """`opencode_extract` and `hermes_extract` keep the tool name and drop the
    arguments, so a reduced transcript yields calls with an empty input. The
    caller must be able to tell this from a session that ran no tools -- it is
    the same `(name, {})` either way, and that is why `run` reports the count of
    entries that carry no `touches:` rather than treating silence as a fact."""
    rows = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "bash"}]}}]
    assert list(transcripts.tool_calls(_write(tmp_path, "o.jsonl", rows))) == [("bash", {})]
