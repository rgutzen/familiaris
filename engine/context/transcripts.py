"""transcripts -- stage the verbatim tier and reduce it to something distillable.

Staged transcripts reach 5.4 MB. Feeding one raw to a model is not chunking, it
is burning the budget on `cat` output: most of the bytes are `tool_result`
blocks the assistant already summarised in prose two lines later.

REDUCTION: keep user text, assistant text and thinking, and the NAMES of tools
called. Drop tool_result bodies and tool_use inputs. What a journal entry needs
-- what was done, what was decided, what failed -- lives entirely in the prose.
"""
from __future__ import annotations

import json
import pathlib

PER_BLOCK = 2000          # chars kept per prose block
TOTAL_BUDGET = 60000      # chars handed to the model, after reduction


def staged(base: pathlib.Path) -> list[pathlib.Path]:
    d = base / "transcripts"
    return sorted(d.glob("*.jsonl")) if d.is_dir() else []


def transcript_id(path: pathlib.Path) -> str:
    """The citation key. Stable, and resolvable back to the verbatim file."""
    return path.name


def meta(path: pathlib.Path) -> dict:
    """cwd / branch / date, read from the first lines that carry them.

    Two shapes so far. Claude Code puts `cwd` / `sessionId` on every top-level
    line. Pi puts them once, on a single `{"type": "session", "id": ...}`
    line -- `id` there is the session id; the same key on a `type: "message"`
    line is a per-message id and must not be mistaken for it.
    """
    out = {"cwd": "", "branch": "", "date": "", "session": ""}
    try:
        with path.open() as fh:
            for i, line in enumerate(fh):
                if i > 200:
                    break
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                for k, key in (("cwd", "cwd"), ("gitBranch", "branch"),
                               ("sessionId", "session")):
                    if not out[key] and o.get(k):
                        out[key] = o[k]
                if not out["date"] and o.get("timestamp"):
                    out["date"] = str(o["timestamp"])[:10]
                if o.get("type") == "session" and not out["session"] and o.get("id"):
                    out["session"] = o["id"]
    except OSError:
        pass
    return out


def _turns(path: pathlib.Path):
    """`(role, content_blocks)` for every turn in one transcript, in order.

    BOTH HARNESS SHAPES, READ ONCE. Claude Code puts the role directly on
    `type` (`"user"` / `"assistant"`) with content nested under `message`; Pi
    wraps every turn in a `type: "message"` envelope and puts the role under
    `message.role` instead. `reduce()` and `tool_calls()` both need this walk,
    and a second copy of it fails SILENTLY -- a harness whose blocks a reader
    does not recognise looks exactly like a session that touched nothing.
    """
    try:
        fh = path.open()
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            otype = o.get("type")
            if otype == "message":
                msg = o.get("message") or {}
                role, content = msg.get("role"), msg.get("content")
            elif otype in ("user", "assistant"):
                role, content = otype, (o.get("message") or {}).get("content")
            else:
                continue
            if role not in ("user", "assistant"):
                continue
            if isinstance(content, str):
                blocks = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                blocks = [b for b in content if isinstance(b, dict)]
            else:
                blocks = []
            yield role, blocks


def tool_calls(path: pathlib.Path):
    """`(name, input)` for every tool call in one transcript, in order.

    The payloads `reduce()` drops on purpose -- it is building a prompt, and a
    `tool_result` body is `cat` output -- kept because they are the only record
    of what a session TOUCHED (`ontology SPECS` O5b, C2). Both spellings
    of both things: `tool_use`/`input` for Claude Code, `toolCall`/`arguments`
    for Pi.

    EMPTY FOR A TRANSCRIPT THAT STAGING ALREADY REDUCED. `hermes_extract`, and
    `opencode_extract` before 2026-10-09, keep the tool NAME and drop the
    arguments on the way in, so a caller that reads nothing cannot tell that
    from a session that touched nothing -- count the transcripts that yielded
    calls, and say so. `opencode_extract` now keeps the path-naming keys.
    """
    for _role, blocks in _turns(path):
        for b in blocks:
            if b.get("type") not in ("tool_use", "toolCall"):
                continue
            payload = b.get("input")
            if not isinstance(payload, dict):
                payload = b.get("arguments")
            yield str(b.get("name") or ""), (payload if isinstance(payload, dict) else {})


def reduce(path: pathlib.Path, budget: int = TOTAL_BUDGET) -> str:
    """Each turn as `[TAG] text`, with tool names kept and their inputs and
    results dropped (see the module docstring). The PROMPT in
    stages/replay.py does not know or care which harness a transcript came
    from -- `_turns` is where that difference is read.
    """
    parts, used = [], 0
    for role, blocks in _turns(path):
        for b in blocks:
            t = b.get("type")
            if t in ("text", "thinking"):
                txt = (b.get("text") or b.get("thinking") or "").strip()
                if not txt:
                    continue
                txt = txt[:PER_BLOCK]
                tag = "USER" if role == "user" else (
                    "ASSISTANT(thinking)" if t == "thinking" else "ASSISTANT")
                parts.append(f"[{tag}] {txt}")
                used += len(txt)
            elif t in ("tool_use", "toolCall"):
                parts.append(f"[TOOL] {b.get('name', '?')}")
                used += 20
            # tool_result bodies are dropped on purpose -- see module docstring
        if used > budget:
            parts.append("[... transcript truncated at the reduction budget ...]")
            break
    return "\n\n".join(parts)
