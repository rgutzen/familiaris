"""opencode_extract -- one session's rows out of opencode.db, converted to
the same line shape `transcripts.py` already reads for Claude Code.

opencode has no per-session transcript file (module docstring on
engine/boundaries/opencode-plugin/index.js's `captureSessionIdle`): sessions
live in a single SQLite DB (`~/.local/share/opencode/opencode.db`, 512+ MB as
of 2026-09-07). Reading the whole file is not an option; every query here is
scoped to one `session_id` and rides the existing `message_session_time_created_id_idx`
/ `part_session_idx` indexes, so it stays fast regardless of DB size.

Read-only, on purpose: this module never writes to opencode.db, and opens it
in SQLite's `mode=ro` URI form so a concurrent WAL writer (the running
opencode process) is never blocked or risked. Converting AT SOURCE, into
Claude Code's shape, means `transcripts.py` needs no third branch of its own
-- one converter here beats a permanent special case in the shared reducer.

Kept out of `capture.py` deliberately (that module's docstring: import-light,
stdlib only, no exceptions carved out for one harness) -- this is a separate,
heavier extraction path, invoked as its own CLI subcommand.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sqlite3

DEFAULT_DB = pathlib.Path.home() / ".local/share/opencode/opencode.db"

# part.type values that carry no reducible prose or tool identity -- see the
# module-level count in the handoff: step-start/step-finish bracket every
# turn (10k+ rows each) and carry only cost/token bookkeeping; `patch` and
# `file` are diff/attachment artifacts, `compaction` is opencode's own
# context-compaction marker. None of them are "what was done, what was
# decided" -- transcripts.reduce()'s job, not this module's, but there is no
# point converting rows the reducer would drop anyway.
_SKIP_PART_TYPES = {"step-start", "step-finish", "patch", "file", "compaction"}

# The `state.input` keys that name what a call touched -- kept so that
# `transcripts.tool_calls()` and `pointers.touched_paths()` can read opencode
# the way they read Claude Code. Bodies (`content`, `oldString`, `newString`)
# and `state.output` stay dropped: they are text, not evidence of a path, and
# would make a staged session as large as the files it edited.
_KEEP_INPUT_KEYS = ("filePath", "path", "pattern", "command", "workdir", "url")


def _iso(ms) -> str:
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, tz=dt.timezone.utc) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return ""


def _connect(db: pathlib.Path) -> sqlite3.Connection:
    # `mode=ro` -- refuses to open (and never creates) a DB that isn't
    # already there; a live WAL writer is unaffected by a read-only reader.
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def extract_session(db: pathlib.Path, session_id: str) -> tuple[dict, list[dict]] | None:
    """`(session_meta, rows)` in Claude Code's per-line shape, or None if the
    session id is unknown to this DB (closed before it was ever written, or a
    session_id string that never existed -- both are the caller's problem to
    report, not this module's to guess about).
    """
    if not db.is_file():
        return None
    conn = _connect(db)
    try:
        conn.row_factory = sqlite3.Row
        srow = conn.execute(
            "select directory, time_created from session where id = ?",
            (session_id,)).fetchone()
        if srow is None:
            return None
        cwd, sess_created = srow["directory"], srow["time_created"]

        rows: list[dict] = []
        for mrow in conn.execute(
            "select id, time_created, data from message where session_id = ? "
            "order by time_created, id", (session_id,)):
            try:
                mdata = json.loads(mrow["data"])
            except ValueError:
                continue
            role = mdata.get("role")
            if role not in ("user", "assistant"):
                continue
            blocks = []
            for prow in conn.execute(
                "select data from part where message_id = ? "
                "order by time_created, id", (mrow["id"],)):
                try:
                    pdata = json.loads(prow["data"])
                except ValueError:
                    continue
                ptype = pdata.get("type")
                if ptype in _SKIP_PART_TYPES:
                    continue
                if ptype == "text":
                    text = pdata.get("text") or ""
                    if text.strip():
                        blocks.append({"type": "text", "text": text})
                elif ptype == "tool":
                    # Name and the path-naming input keys. reduce() drops the
                    # input anyway; tool_calls() is the reader that needs it.
                    raw = (pdata.get("state") or {}).get("input")
                    keep = {k: raw[k] for k in _KEEP_INPUT_KEYS
                            if isinstance(raw, dict) and isinstance(raw.get(k), str)}
                    blocks.append({"type": "tool_use",
                                   "name": pdata.get("tool", "?"),
                                   "input": keep})
            if not blocks:
                continue
            rows.append({
                "type": role,
                "sessionId": session_id,
                "cwd": cwd or "",
                "timestamp": _iso(mrow["time_created"]),
                "message": {"content": blocks},
            })
        meta = {"cwd": cwd or "", "session": session_id,
                "timestamp": _iso(sess_created)}
        return meta, rows
    finally:
        conn.close()


def write_jsonl(rows: list[dict], dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
