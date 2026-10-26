"""chain -- the next run knows what the last one did (dev/schedule 1f).

WHY. 9a's only link between runs was the standing prompt's request that the agent
rewrite its handoff. A run that dies mid-item -- the common ending when the budget
is the trigger -- leaves the handoff stale, and the engine, which recorded the
exit, the commits and the transcript, passed none of it on (PLAN, cause 2). So:

* **SPECS are the chain's state** (decision 4): ticks are progress, no open item
  is done. A prompt chain says `status: done|blocked` in its front-matter.
* **The engine measures** each run -- ticks gained, commits made, a handoff
  written, the prompt's `status:` changed -- instead of taking the agent's word.
* **The carry-over block** prepends the previous run's ending to the next run's
  prompt: why it ended, its commits, what it left uncommitted, its handoff, its
  final report from the transcript. A handoff is then archived, so it is read once.
* **A chain ends or pauses by rule**: done; blocked; stalled after
  `chain.stall_after` runs in a row without progress (decision 5); review after
  ticking an item marked `review: yes` (decision 7). `resume` clears a pause, and
  so does editing the ask's source (its sha changes).
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess

from orchestration import specs as specs_mod

HANDOFF = "handoff.md"
REPORT_CHARS = 2000
HANDOFF_CHARS = 6000
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
_STATUS = re.compile(r"^status:\s*(\S+)\s*$", re.M)
PAUSES = ("blocked", "stalled", "review")


# --- reading the tree -----------------------------------------------------------

def git_head(cwd, *, run=subprocess.run) -> str:
    p = run(["git", "-C", str(cwd), "rev-parse", "HEAD"], capture_output=True, text=True)
    return (p.stdout or "").strip() if not getattr(p, "returncode", 1) else ""


def git_log(cwd, start: str, end: str, *, run=subprocess.run) -> list:
    if not start or not end or start == end:
        return []
    p = run(["git", "-C", str(cwd), "log", "--oneline", f"{start}..{end}"],
            capture_output=True, text=True)
    return (p.stdout or "").splitlines() if not getattr(p, "returncode", 1) else []


def front_status(text: str) -> str:
    """`status:` in a prompt's YAML front-matter, or ''."""
    m = _FRONT.match(text or "")
    if not m:
        return ""
    s = _STATUS.search(m.group(1))
    return s.group(1).strip().lower() if s else ""


def specs_state(path) -> dict:
    """{done: [ids], open: [ids], user_open: [ids], review: [ids]} of a SPECS file."""
    contract = specs_mod.load_contract()
    items = specs_mod.parse(pathlib.Path(path).read_text(encoding="utf-8"),
                            set(contract["fields"]))
    user = contract.get("user_model", "user")
    return {"done": [i.id for i in items if i.done],
            "open": [i.id for i in items if not i.done],
            "user_open": [i.id for i in items if not i.done
                          and i.fields.get("model", "").strip() == user],
            "review": [i.id for i in items if i.fields.get("review", "").strip() == "yes"]}


def snapshot(decl: dict, record: pathlib.Path, *, run=subprocess.run) -> dict:
    """What a run's progress is measured against, taken at its start and its end."""
    ask = decl.get("ask") or {}
    path = pathlib.Path(ask.get("path", ""))
    out = {"head": git_head(decl["cwd"], run=run), "status": "", "specs": None,
           "handoff_mtime": None}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    if ask.get("kind") == "specs" and text:
        out["specs"] = specs_state(path)
    elif text:
        out["status"] = front_status(text)
    handoff = record / HANDOFF
    if handoff.is_file():
        out["handoff_mtime"] = handoff.stat().st_mtime
    return out


def measure(before: dict, after: dict, decl: dict, *, run=subprocess.run) -> dict:
    """The run's progress, by the record and the tree -- never the agent's word."""
    commits = git_log(decl["cwd"], before.get("head", ""), after.get("head", ""), run=run)
    gained = []
    if before.get("specs") and after.get("specs"):
        gained = [i for i in after["specs"]["done"] if i not in before["specs"]["done"]]
    handoff = (after.get("handoff_mtime") is not None
               and after.get("handoff_mtime") != before.get("handoff_mtime"))
    status_changed = before.get("status", "") != after.get("status", "")
    return {"ticks": gained, "commits": commits, "handoff": handoff,
            "status": after.get("status", ""), "status_changed": status_changed,
            "any": bool(gained or commits or handoff or status_changed)}


def final_report(transcript) -> str:
    """The last assistant text in a pi transcript (`{"type": "message", "message":
    {"role": "assistant", "content": [{"type": "text", ...}]}}`), trimmed."""
    if not transcript:
        return ""
    last = ""
    try:
        lines = pathlib.Path(transcript).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        try:
            msg = (json.loads(line) or {}).get("message") or {}
        except ValueError:
            continue
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        text = content if isinstance(content, str) else "".join(
            c.get("text", "") for c in content or [] if c.get("type") == "text")
        if text.strip():
            last = text.strip()
    return last[-REPORT_CHARS:]


# --- how a run ended, and what the chain does next ------------------------------

def ended_why(finished: dict | None, crashed: dict | None = None) -> str:
    if crashed and not finished:
        return f"crashed before the session started ({crashed.get('error', '')})"
    if not finished:
        return "no finished row (LOST)"
    if finished.get("window_refused"):
        return "the window refused it"
    if finished.get("interrupted"):
        return "interrupted by the backstop"
    if finished.get("checkpoint_stop"):
        return f"a stop condition at a checkpoint ({finished['checkpoint_stop']})"
    if finished.get("exit") == 124:
        return "the timeout"
    if finished.get("exit") == 0:
        return "completed"
    return f"failed (exit {finished.get('exit')})"


def outcome(decl: dict, progress: dict, after: dict, history: list, *,
            stall_after: int) -> tuple:
    """(state, why) after a run: done | blocked | review | stalled | continue.
    `history` is the chain's earlier `chain` events, oldest first."""
    sp = after.get("specs")
    if sp is not None:
        if not sp["open"]:
            return "done", "no open SPECS item"
        if set(sp["open"]) <= set(sp["user_open"]):
            return "blocked", f"only the user's items remain: {', '.join(sp['open'])}"
        reviewed = [i for i in progress["ticks"] if i in sp["review"]]
        if reviewed:
            return "review", f"ticked {', '.join(reviewed)}, which asks for the user's review"
    else:
        if after.get("status") == "done":
            return "done", "the prompt says status: done"
        if after.get("status") == "blocked":
            return "blocked", "the prompt says status: blocked"
    if not progress["any"]:
        idle = 1
        for e in reversed(history):
            if e.get("refused"):
                continue                       # a refused window is a hold, not a stall
            if (e.get("progress") or {}).get("any"):
                break
            idle += 1
        if idle >= stall_after:
            return "stalled", f"{idle} runs in a row without progress"
    return "continue", "progress" if progress["any"] else "no progress yet"


def paused(events: list, current_sha: str) -> str:
    """Why the chain is paused, or ''. A `resumed` after the pause clears it, and so
    does an ask whose source changed since (the user edited it)."""
    for e in reversed(events):
        if e.get("event") == "resumed":
            return ""
        if e.get("event") == "paused":
            if e.get("ask_sha") and current_sha and e["ask_sha"] != current_sha:
                return ""
            return f"{e.get('state')}: {e.get('why')}"
    return ""


# --- the carry-over block -------------------------------------------------------

def carry_over(record: pathlib.Path, events: list) -> tuple:
    """(block, handoff path or None) from the previous run's events. Empty for a
    chain's first run."""
    starts = [i for i, e in enumerate(events) if e.get("event") == "started"]
    if not starts:
        return "", None
    since = events[starts[-1]:]
    started = since[0]
    finished = next((e for e in since if e.get("event") == "finished"), None)
    crashed = next((e for e in since if e.get("event") == "crashed"), None)
    link = next((e for e in reversed(since) if e.get("event") == "chain"), None)
    progress = (link or {}).get("progress") or (finished or {}).get("progress") or {}
    lines = ["## Carry-over from the previous run (written by the engine)", "",
             f"- **Run:** {started.get('run') or started.get('ts')}, started {started.get('ts')}",
             f"- **Ended by:** {ended_why(finished, crashed)}"
             + (f", exit {finished.get('exit')}" if finished else "")]
    if progress.get("ticks"):
        lines.append(f"- **SPECS ticked:** {', '.join(progress['ticks'])}")
    commits = progress.get("commits") or []
    lines.append(f"- **Commits:** {len(commits)}" + (":" if commits else ""))
    lines += [f"    {c}" for c in commits[:20]]
    left = (finished or {}).get("changed") or []
    lines.append("- **Left uncommitted:** " + (", ".join(left[:20]) if left else "nothing"))
    if link:
        lines.append(f"- **Chain:** {link.get('state')} -- {link.get('why')}")
    report = (finished or {}).get("report") or ""
    if report:
        lines += ["", "### Its final report", "", report]
    handoff = record / HANDOFF
    used = None
    if handoff.is_file():
        text = handoff.read_text(encoding="utf-8", errors="replace")[:HANDOFF_CHARS]
        lines += ["", f"### Its handoff ({handoff.name}, archived after this run starts)",
                  "", text.rstrip()]
        used = handoff
    lines += ["", "The SPECS ticks are the state; this block is context. Verify before "
              "you rely on it.", ""]
    return "\n".join(lines), used


def archive_handoff(handoff: pathlib.Path, run_id: str) -> pathlib.Path:
    dest = handoff.with_name(f"handoff-{run_id}.md")
    handoff.rename(dest)
    return dest


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")
