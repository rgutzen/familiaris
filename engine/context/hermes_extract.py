"""hermes_extract -- one Hermes session, converted to the line shape
`transcripts.py` already reads for Claude Code.

Hermes keeps sessions in its own SQLite store (`~/.hermes/state.db`) but
ships a first-class extractor for it already: `hermes sessions export
--session-id=ID --format=jsonl -` prints one JSON object per matched
session, `id`/`cwd`/`git_branch`/`started_at` at the top level and a
`messages` array underneath (verified against `hermes-agent`'s own test
fixture, `tests/hermes_cli/test_session_export.py::_sample_session`, and a
real export, 2026-09-07). Shelling out to the CLI -- rather than reading
`state.db` directly -- means this module tracks whatever Hermes's own schema
does, for free, and never risks writing to a store a live `hermes` process
has open.

Message shapes seen in that fixture, all handled below:
  - `content` is either a bare string or an already-block-shaped list
    (`[{"type": "text", "text": ...}]` -- the same shape Claude Code's
    `message.content` uses, not a coincidence worth re-deriving).
  - `role: "tool"` is a tool RESULT (`tool_name` + its output as `content`).
    Dropped entirely, same as Claude Code's `tool_result` blocks --
    transcripts.reduce() never had a case for a bare `tool` role and does not
    need one now.
  - `role: "assistant"` may carry `tool_calls`: `[{"type": "function",
    "function": {"name": ..., "arguments": ...}}]` (OpenAI's own shape).
    Converted to a `tool_use` block, name only -- `arguments` is dropped for
    the same reason Claude Code's `tool_use.input` is.
  - `reasoning` (a string) becomes a `thinking` block.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess


def _iso(epoch_seconds) -> str:
    try:
        return dt.datetime.fromtimestamp(float(epoch_seconds), tz=dt.timezone.utc) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def _blocks(content) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content.strip() else []
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _convert(session_obj: dict) -> tuple[dict, list[dict]]:
    sid = session_obj.get("id", "")
    cwd = session_obj.get("cwd") or ""
    branch = session_obj.get("git_branch") or ""
    rows = []
    for m in session_obj.get("messages") or []:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue                      # `tool` (a result) is dropped
        blocks = _blocks(m.get("content"))
        if role == "assistant":
            reasoning = m.get("reasoning")
            if reasoning and reasoning.strip():
                blocks.append({"type": "thinking", "thinking": reasoning})
            for tc in m.get("tool_calls") or []:
                fn = (tc or {}).get("function") or {}
                if fn.get("name"):
                    blocks.append({"type": "tool_use", "name": fn["name"]})
        if not blocks:
            continue
        ts = m.get("timestamp")
        rows.append({
            "type": role,
            "sessionId": sid,
            "cwd": cwd,
            "gitBranch": branch,
            "timestamp": _iso(ts) if ts is not None else "",
            "message": {"content": blocks},
        })
    meta = {"cwd": cwd, "branch": branch, "session": sid,
            "timestamp": _iso(session_obj.get("started_at"))}
    return meta, rows


def extract_session(session_id: str, *, hermes_bin: str = "hermes",
                    timeout: int = 20) -> tuple[dict, list[dict]] | None:
    """`(session_meta, rows)`, or None if the export failed or the session
    id does not resolve to anything Hermes knows about. `--session-id`
    accepts a unique prefix as well as a full id (hermes's own CLI); the
    capture hook always hands this a full id, but a caller passing a prefix
    that matches more than one session gets the first exact-`id` match, not
    an arbitrary one.
    """
    try:
        proc = subprocess.run(
            [hermes_bin, "sessions", "export", f"--session-id={session_id}",
             "--format=jsonl", "-"],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("id") == session_id:
            return _convert(obj)
    return None


def write_jsonl(rows: list[dict], dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
