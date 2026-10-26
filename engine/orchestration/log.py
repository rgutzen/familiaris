"""log -- one line per delegation (item 5c), the data 5d's verdict is read from.

WHY. Option B's floors (5d) are uptake, compression and the post-fire bytes, and
none of them is visible today: a `pi-agent` child ran with `--no-session`, so what
it read and what it cost were gone the moment it returned. Every delegation this
system makes passes through `pi-agent` -- a bare `pi-agent <role> "<task>"`,
`familiar orchestration bindings run`, a `bound_*` tool and a `/bound-*` command all
spawn it -- so `pi-agent` is the one writer, and it writes after the child exits.

ONE LINE PER DELEGATION, `<PAZRAS_DATA_DIR>/delegations.jsonl`:
  ts, role, model (what pi ran: the child log's last `model_change`), profile,
  effort, session (the child's log), exit,
  usage    the child's pools, as the eval counts them (input, output, cache_write,
           cache_read; frontier = the first three)
  bytes_read      the text of every tool result the child received -- what the
                  parent did NOT have to read
  bytes_returned  the child's final answer -- what the parent did read
  compression     bytes_read / bytes_returned (5d's "median compression >= 5x")
  parent          the parent session log, when the caller said which one (12a)
  used            whether the parent used the result: null when written, because
                  the child cannot know; `--write` fills it from the parent's log

EVERY FIELD BUT `ts`, `exit`, `parent` AND `used` COMES FROM THE CHILD'S OWN LOG,
so a replay reproduces the line: `line_for(child_log)` is what `pi-agent` appends
and what `replay` recomputes.

WHAT IS *NOT* A DELEGATION (12c). `pi-agent --no-log` runs the child and prints
its mark but writes no line: the reader calibration's attempts measure the READER,
they are not caused by the trigger, and no parent used or ignored them. A line for
each would enter 5d's uptake denominator as noise, so `eval --calibrate` passes the
flag and keeps its own rows in `calibration.jsonl`.

THE JOIN KEY HAS TWO FORMS (12a). The FIRST is the parent's own name, which
`pi-agent` now receives: `--parent-session <path>`, or the `PI_SESSION_FILE` /
`PI_SESSION_ID` pi puts in the environment of every command its `bash` tool runs.
The SECOND is the line `pi-agent: delegation role=<r> session=<path>` it prints to
stderr, which lands in the parent's transcript inside the tool result that ran it.
The mark alone was the whole join until 2026-10-21 and filled 9 of 17 lines; it
stays because an old transcript is still readable by it and because a call that
passes no parent has nothing else.

`--replay` RE-DERIVES A LINE FROM THE PARENT, `--write` STORES THE RESULT. Replay
recomputes every field from the child's log and judges `used` from what the parent
did next; `--write` upserts those rows into the log by `session` (one line per
delegation, so an updated line replaces rather than duplicates), under an flock
and an atomic replace -- several sessions can finish at once.

The session-end write is a pi hook (`trigger/pi-trigger/index.ts`), so uptake
stops depending on somebody remembering to replay. The hook skips a session
whose log does not exist -- pi writes the file lazily, so an empty session has
none, and there is nothing to close; this command keeps exit 2 for an explicit
`--parent` that names nothing, because for a manual caller that is a typo's
loud failure, not an empty session.

`used` IS A HEURISTIC, AND SAYS SO. The result counts as used when a `path` it
returned (`path:line`) or a URL it returned appears in a LATER tool call or
assistant message of the parent, or a returned line or quote of 24+ characters
appears verbatim in a later assistant message. A result that is read and silently relied
on is invisible to this, so `used: false` is a floor on uptake, never proof of
waste; `used: null` means the parent's log was not found.

EXIT CODES. 0 printed. 2 usage error or no parent log found.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import fcntl
import json
import math
import os
import pathlib
import re
import statistics
import sys

from orchestration import profiles
from orchestration.eval import POOLS, _entries, read_usage

LOG_NAME = "delegations.jsonl"
SESSIONS = pathlib.Path.home() / ".pi/agent/sessions"
PARENT_FILE_ENV = "PI_SESSION_FILE"   # pi sets both for every `bash` tool call
PARENT_ID_ENV = "PI_SESSION_ID"
CHILD_DIR = "pi-agent"                # pi-agent children's own logs; see `trigger`
MARK = re.compile(r"pi-agent: delegation role=(?P<role>\S+) session=(?P<session>\S+\.jsonl)")
REF = re.compile(r"(?P<path>[\w./~+-]+\.\w+|[\w./~+-]+/[\w.+-]+):\d+")
URL = re.compile(r"https?://[^\s)>\"'`]+")
QUOTE = re.compile(r'"([^"]+)"|`([^`]+)`')
MIN_LINE = 24


def log_path(env=os.environ) -> pathlib.Path:
    return profiles.data_dir(env) / LOG_NAME


def _texts(content) -> str:
    return "".join(p.get("text") or "" for p in content if isinstance(p, dict)
                   and p.get("type") == "text") if isinstance(content, list) else ""


def child_facts(path: pathlib.Path) -> dict:
    """What the child's own log says: the model that ran, its effort, what it read,
    and its final answer."""
    model, effort, read, answer = "", "", 0, ""
    for e in _entries(path):
        kind = e.get("type")
        if kind == "model_change":
            model = f"{e.get('provider')}/{e.get('modelId')}"
        elif kind == "thinking_level_change":
            effort = str(e.get("thinkingLevel") or "")
        m = e.get("message") if kind == "message" else None
        if not isinstance(m, dict):
            continue
        if m.get("role") == "toolResult":
            read += len(_texts(m.get("content")).encode())
        elif m.get("role") == "assistant":
            text = _texts(m.get("content"))
            if text.strip():
                answer = text
    return {"model": model, "effort": effort, "bytes_read": read, "answer": answer}


def _by_id(sid: str, root: pathlib.Path) -> pathlib.Path | None:
    """The parent log whose filename ends `_<sid>.jsonl`, newest if several.

    pi names a session file `<timestamp>_<id>.jsonl`, so an id alone resolves
    against the sessions root. `pi-agent/` is skipped for the reason `trigger`
    skips it: those are children's logs, and a child is never the parent of the
    delegation being logged.
    """
    root = pathlib.Path(root)
    found = [p for p in root.glob("*/*.jsonl")
             if p.name.endswith(f"_{sid}.jsonl")
             and CHILD_DIR not in p.relative_to(root).parts[:-1]]
    return max(found, key=lambda p: p.stat().st_mtime, default=None)


def resolve_parent(explicit: str | None = None, env=None,
                   root: pathlib.Path = SESSIONS) -> pathlib.Path | None:
    """The parent session log this delegation belongs to, or None.

    FOUR SOURCES, IN ORDER, and each one is checked rather than trusted: the
    caller's `--parent-session`, then `PI_SESSION_FILE`, then `PI_SESSION_ID`
    resolved against the sessions root. A source that names nothing on disk
    falls through to the next, and a call that passes nothing gets None -- the
    stderr mark is then the only join, exactly as before 12a. Guessing a parent
    would attribute one session's delegation to another.
    """
    env = os.environ if env is None else env
    if explicit:
        p = pathlib.Path(explicit).expanduser()
        if p.is_file():
            return p
    f = env.get(PARENT_FILE_ENV)
    if f:
        p = pathlib.Path(f).expanduser()
        if p.is_file():
            return p
    sid = env.get(PARENT_ID_ENV)
    return _by_id(sid, root) if sid else None


def line_for(child: pathlib.Path, role: str, *, profile: str = "", exit_code=None,
             now: datetime.datetime | None = None,
             parent: pathlib.Path | str | None = None) -> dict:
    """The delegation line for one child log. Deterministic in its inputs except
    `ts`, which is the caller's clock."""
    f = child_facts(child)
    pools = read_usage([child])
    returned = len(f["answer"].encode())
    return {
        "ts": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds"),
        "role": role,
        "model": f["model"],
        "profile": profile,
        "effort": f["effort"],
        "session": str(child),
        "exit": exit_code,
        "usage": dict(pools, frontier=sum(pools[k] for k in POOLS if k != "cache_read")),
        "bytes_read": f["bytes_read"],
        "bytes_returned": returned,
        "compression": round(f["bytes_read"] / returned, 2) if returned else None,
        "parent": str(parent) if parent else None,
        "used": None,
    }


def append(line: dict, path: pathlib.Path | None = None) -> pathlib.Path:
    path = path or log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, sort_keys=True) + "\n")
    return path


def upsert(rows: list, path: pathlib.Path | None = None) -> tuple[int, int]:
    """Put replayed rows into the log: one line per child session, (added, updated).

    The log's readers count lines, so a replayed line must REPLACE the line the
    child wrote rather than sit beside it -- appending corrections would make
    uptake a question about which of two lines a reader kept. The write is a
    read-modify-write under an flock on a sidecar file plus an atomic replace,
    because the session-end hook of several sessions can finish at once.
    """
    path = path or log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = read(path)
        index = {r.get("session"): i for i, r in enumerate(existing)}
        added = updated = 0
        for row in rows:
            key = row.get("session")
            if key is None or (i := index.get(key)) is None:
                if key is not None:
                    index[key] = len(existing)
                existing.append(row)
                added += 1
                continue
            merged = {**existing[i], "used": row.get("used"), "parent": row.get("parent")}
            updated += merged != existing[i]
            existing[i] = merged
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in existing),
                       encoding="utf-8")
        os.replace(tmp, path)
    return added, updated


def read(path: pathlib.Path | None = None) -> list:
    """The log's lines. A missing log is empty, a truncated line is dropped."""
    path = path or log_path()
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


# --- 12b: the one screen ------------------------------------------------------
#
# ONE COMMAND ANSWERS 5d, so the verdict is a reading rather than a session. It
# reads the TWO logs a session leaves: the parent transcripts under
# `~/.pi/agent/sessions/` (turns, tool bytes, the hint's own entries, and whether
# a hint was acted on) and `<PAZRAS_DATA_DIR>/delegations.jsonl` (what the
# children read and cost, and whether the parent used them). Nothing here
# re-counts the trigger: the turn splitter is `orchestration.trigger`'s, so a
# fire means the same thing in this report as in `trigger --replay`.
#
# THE WINDOW STARTS WHERE THE LOGS DO (`2026-10-15`, 5d's own date). `--since`
# moves it earlier or later; a delegation line is attributed to the window by its
# `parent` when it has one (12a) and by its date when it does not, which is what
# keeps the 17 lines written before the parent field readable.
#
# COMPRESSION IS A MEDIAN, so one 400 KB turn cannot decide it.
#
# THE POST-FIRE FLOOR IS A RANDOMISED COMPARISON (14a, ruled 2026-10-22). It was
# a ratio of two medians, delegated turns against undelegated ones, and that
# compared tasks rather than delegation: the agent picks which turns to delegate.
# The extension now withholds the hint on a random third of fires, so the arm is
# the instrument and delegation is what it moves. The effect on a delegating turn
# is the Wald (LATE) estimate on log bytes:
#     ratio = exp((mean log1p bytes_after | nudged - ... | withheld)
#                 / (P(delegated | nudged) - P(delegated | withheld)))
# which still reads "post-fire bytes, delegated against not" and keeps the 50%
# floor. Log, because a turn's post-fire bytes span 0.7 KB to 315 KB. The raw
# nudged/withheld ratio (the intent-to-treat effect) is printed beside it. The
# floor FAILS with its reason while either arm holds fewer than `MIN_ARM` fires
# or the uptake gap is under `MIN_GAP`, because the estimate divides by the gap.
# Its window opens at `ARMS_START`, the day 14a landed: every fire before it was
# nudged, and pooling those would bring back the bias the randomisation removes,
# so this floor has its own gate (45 fires or 60 sessions from that day).
#
# A floor whose number cannot be measured
# reads FAIL with the reason rather than PASS by default: an uptake of `null` is
# not an uptake of one. The gate is 5d's entry condition -- 30 fires or 60
# sessions -- printed as a count so nobody has to remember it.
#
# `--check` FOR THE HEALTHCHECK: it exits 1 when a floor that PASSED last time now
# FAILS. It does not fail on a floor that was already failing (that is 5d's open
# question, not a regression) and it does not fail on the first run.

WINDOW_START = "2026-10-15"          # the first day the delegation log has lines
GATE_FIRES = 30                      # 5d: the window opens at 30 fires
GATE_SESSIONS = 60                   # ... or 60 sessions, whichever comes first
FLOOR_UPTAKE = 0.50                  # 5d: uptake >= 50%
FLOOR_COMPRESSION = 5.0              # 5d: median compression >= 5x
FLOOR_BYTES = 0.50                   # 5d: post-fire bytes, delegated <= 50% of plain
ARMS_START = "2026-10-22"            # 14a landed: the first day a fire may be withheld
GATE_ARM_FIRES = 45                  # 14a: about 15 withheld at a third
MIN_ARM = 10                         # fires per arm before the estimate is read
MIN_GAP = 0.10                       # the uptake gap the estimate divides by
FLOOR_BYTES_NAME = "post-fire bytes <= 50%, randomised"
STATE_NAME = "report-last.json"      # the previous run's floors, for `--check`


def price_for(model: str, cat: dict | None = None) -> dict:
    """The catalogue's price block for a log line's model.

    The log holds what pi ran (`deepseek/deepseek-flash`); the catalogue is keyed
    by the vendor's id, so the provider prefix is stripped only when the whole
    string names nothing.
    """
    from orchestration import price
    return price.block(model, cat)


def window_rows(logs: list, since: str, path: pathlib.Path | None = None) -> list:
    """The delegation lines that belong to this window (see the section note)."""
    names = {str(p) for p in logs}
    day = since[:10]
    out = []
    for row in read(path):
        parent = row.get("parent")
        if parent:
            if parent in names:
                out.append(row)
        elif str(row.get("ts", ""))[:10] >= day:
            out.append(row)
    return out


@dataclasses.dataclass
class Window:
    """What the two logs say about one date window."""
    since: str
    logs: list = dataclasses.field(default_factory=list)
    skipped: list = dataclasses.field(default_factory=list)
    turns: int = 0
    tool_bytes: int = 0
    fires: int = 0
    nudges: int = 0
    acted: int = 0
    rows: list = dataclasses.field(default_factory=list)
    # 14a: fired turns on or after `arms_since`, per arm, as (bytes_after, delegated)
    arms_since: str = ARMS_START
    arms: dict = dataclasses.field(default_factory=lambda: {"nudged": [], "withheld": []})
    arm_fires: int = 0               # fires on or after `arms_since`, either arm or none
    arm_sessions: int = 0

    @property
    def gate(self) -> tuple[int, int, bool]:
        return (self.fires, self.sessions, self.fires >= GATE_FIRES
                or self.sessions >= GATE_SESSIONS)

    @property
    def arm_gate(self) -> tuple[int, int, bool]:
        return (self.arm_fires, self.arm_sessions, self.arm_fires >= GATE_ARM_FIRES
                or self.arm_sessions >= GATE_SESSIONS)

    def randomised(self) -> dict:
        """14a's estimate: the LATE ratio, the intent-to-treat ratio, and why not."""
        n, w = self.arms["nudged"], self.arms["withheld"]
        out = {"nudged": len(n), "withheld": len(w), "ratio": None, "itt": None,
               "gap": None, "why": ""}
        if len(n) < MIN_ARM or len(w) < MIN_ARM:
            out["why"] = f"needs {MIN_ARM} fires per arm"
            return out
        log_n = statistics.fmean(math.log1p(b) for b, _ in n)
        log_w = statistics.fmean(math.log1p(b) for b, _ in w)
        gap = (sum(d for _, d in n) / len(n)) - (sum(d for _, d in w) / len(w))
        out["itt"], out["gap"] = math.exp(log_n - log_w), gap
        if gap < MIN_GAP:
            out["why"] = f"uptake gap {gap:.2f} < {MIN_GAP}"
            return out
        out["ratio"] = math.exp((log_n - log_w) / gap)
        return out

    @property
    def sessions(self) -> int:
        return len(self.logs)

    def slots(self) -> list:
        """The three floors 5d is decided on: (name, value, target, result, note, shown).

        `None` is a number nothing measured, and it fails: the report answers a
        question about data, so missing data is not a passing answer.
        """
        known = [r for r in self.rows if r.get("used") is not None]
        uptake = (sum(r["used"] is True for r in known) / len(known)) if known else None
        sizes = [r["compression"] for r in self.rows
                 if r.get("compression") is not None]   # 0x is a measurement too
        median = statistics.median(sizes) if sizes else None
        r = self.randomised()
        ratio = r["ratio"]
        arms = f"{r['nudged']} nudged / {r['withheld']} withheld since {self.arms_since}"
        if r["itt"] is not None:
            arms += f"; ITT {_pct(r['itt'])}, uptake gap {r['gap']:.2f}"
        if r["why"]:
            arms += f"; {r['why']}"
        return [
            ("uptake >= 50%", uptake, FLOOR_UPTAKE,
             uptake is not None and uptake >= FLOOR_UPTAKE,
             f"{len(known)} line(s) with a verdict", _pct(uptake)),
            ("median compression >= 5x", median, FLOOR_COMPRESSION,
             median is not None and median >= FLOOR_COMPRESSION,
             f"{len(sizes)} line(s) with a size", _ratio(median)),
            (FLOOR_BYTES_NAME, ratio, FLOOR_BYTES,
             ratio is not None and ratio <= FLOOR_BYTES, arms, _pct(ratio)),
        ]

    def metrics(self) -> dict:
        known = [r for r in self.rows if r.get("used") is not None]
        read_ = sum(r.get("bytes_read") or 0 for r in self.rows)
        returned = sum(r.get("bytes_returned") or 0 for r in self.rows)
        return {
            "since": self.since,
            "until": max((trigger_date(p) for p in self.logs), default=""),
            "sessions": self.sessions,
            "turns": self.turns,
            "tool_bytes": self.tool_bytes,
            "fires": self.fires,
            "nudges": self.nudges,
            "acted": self.acted,
            "delegations": len(self.rows),
            "delegated_read": read_,
            "delegated_returned": returned,
            "delegations_without_verdict": len(self.rows) - len(known),
            "usd": round(sum(cost_of(r) for r in self.rows), 6),
            "floors": [{"floor": n, "value": v, "target": t, "ok": ok, "note": note,
                        "shown": shown}
                       for n, v, t, ok, note, shown in self.slots()],
            "gate": {"fires": self.fires, "sessions": self.sessions,
                     "fires_needed": max(0, GATE_FIRES - self.fires),
                     "sessions_needed": max(0, GATE_SESSIONS - self.sessions),
                     "open": self.gate[2]},
            "arm_gate": {"since": self.arms_since, "fires": self.arm_fires,
                         "sessions": self.arm_sessions,
                         "fires_needed": max(0, GATE_ARM_FIRES - self.arm_fires),
                         "sessions_needed": max(0, GATE_SESSIONS - self.arm_sessions),
                         "open": self.arm_gate[2]},
            "verdict_readable": self.gate[2] and self.arm_gate[2],
        }


def cost_of(row: dict, cat: dict | None = None) -> float:
    """One delegation line's $, at the catalogue's rates for its model AT ITS TIME
    (an off-peak line bills at the off-peak rate, 14c)."""
    from orchestration import price
    try:
        at = datetime.datetime.fromisoformat(str(row.get("ts") or ""))
    except ValueError:
        at = None
    return price.cost(price_for(row.get("model") or "", cat), row.get("usage") or {}, at)[0]


def trigger_date(path: pathlib.Path) -> str:
    """The `YYYY-MM-DD` in a session log's filename, or ''."""
    from orchestration import trigger
    return trigger.log_date(path)


def scan(since: str = WINDOW_START, root: pathlib.Path = SESSIONS,
         path: pathlib.Path | None = None, arms_since: str = ARMS_START) -> Window:
    """Read both logs over the window: the turns from the transcripts, the
    delegations from the log."""
    from orchestration import trigger
    w = Window(since=since[:10], arms_since=max(since[:10], arms_since[:10]))
    w.logs = trigger.since_date(trigger.recent_logs(1 << 20, root), since)
    for p in w.logs:
        in_arms = trigger_date(p) >= w.arms_since
        w.arm_sessions += in_arms
        try:
            turns = trigger.session_turns(p)
        except OSError as exc:
            w.skipped.append((p, exc.strerror or str(exc)))     # named, not dropped
            continue
        w.turns += len(turns)
        for t in turns:
            w.tool_bytes += t.bytes
            w.nudges += t.nudges
            w.acted += t.acted
            if t.fired:
                w.fires += 1
                if in_arms:
                    w.arm_fires += 1
                    if t.arm:
                        w.arms[t.arm].append((t.bytes_after, t.delegated))
    w.rows = window_rows(w.logs, since, path)
    return w


def _size(n: float) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def _pct(v) -> str:
    return "--" if v is None else f"{v * 100:.0f}%"


def _ratio(v) -> str:
    return "--" if v is None else f"x{v:.1f}"


def report(w: Window, out=print) -> None:
    """The six numbers, the three floors and the gate, on one screen."""
    m = w.metrics()
    fires, sessions, open_ = w.gate
    out(f"report -- the delegation window from {w.since}"
        + (f" to {m['until']}" if m["until"] else ""))
    out(f"  sessions  {sessions} read, {w.turns} turn(s), {_size(w.tool_bytes)} of tool output")
    out(f"  nudges    {w.nudges} sent, {w.acted} acted on in the same turn"
        + (f" ({w.acted / w.nudges * 100:.0f}%)" if w.nudges else ""))
    out(f"  delegated {len(w.rows)} line(s): {_size(m['delegated_read'])} read, "
        f"{_size(m['delegated_returned'])} returned, ${m['usd']:.4f} at the rates of their hour"
        + (f"; {m['delegations_without_verdict']} without `used`"
           if m["delegations_without_verdict"] else ""))
    out("  5d floors")
    for floor in m["floors"]:
        out(f"    {'PASS' if floor['ok'] else 'FAIL'}  {floor['floor']:<44} {floor['shown']:>7}"
            f"  ({floor['note']})")
    out(f"  gate      {fires}/{GATE_FIRES} fires, {sessions}/{GATE_SESSIONS} sessions: "
        + ("OPEN -- floors 1-2 are readable" if open_ else
           f"waiting on {max(0, GATE_FIRES - fires)} more fire(s) or "
           f"{max(0, GATE_SESSIONS - sessions)} more session(s)"))
    a_fires, a_sessions, a_open = w.arm_gate
    out(f"  gate 3    {a_fires}/{GATE_ARM_FIRES} fires, {a_sessions}/{GATE_SESSIONS} sessions "
        f"since {w.arms_since}: "
        + ("OPEN -- floor 3 is readable" if a_open else
           f"waiting on {max(0, GATE_ARM_FIRES - a_fires)} more fire(s) or "
           f"{max(0, GATE_SESSIONS - a_sessions)} more session(s)"))
    out("  verdict   " + ("READABLE -- both gates are open; record all three floors in "
                          "orchestrators.md" if open_ and a_open else
                          "HELD -- recorded whole once both gates are open (ruled 2026-10-22); "
                          "quote no floor before then"))
    for path, why in w.skipped:
        out(f"  skipped   {path}: {why}")


def state_path() -> pathlib.Path:
    return profiles.data_dir() / STATE_NAME


def regressions(now: list, before: list) -> list:
    """The floors that passed in `before` and fail in `now`."""
    was = {f["floor"]: f for f in before}
    return [f["floor"] for f in now if f["ok"] is False and (was.get(f["floor"]) or {}).get("ok") is True]


def report_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="familiar orchestration report",
        description="One screen for 5d: the window's numbers, its three floors, its gate.")
    ap.add_argument("--since", default=WINDOW_START, metavar="DATE",
                    help=f"the window's first day (default {WINDOW_START}, where the log starts)")
    ap.add_argument("--sessions", type=pathlib.Path, default=SESSIONS, metavar="DIR",
                    help=f"the sessions root (default {SESSIONS})")
    ap.add_argument("--path", type=pathlib.Path, metavar="FILE",
                    help=f"the delegation log (default {LOG_NAME} in the data directory)")
    ap.add_argument("--json", action="store_true", help="one JSON object instead of the report")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a floor that passed last run now fails")
    args = ap.parse_args(argv)
    if len(args.since) != 10:
        print("report: --since wants a YYYY-MM-DD date", file=sys.stderr)
        return 2
    w = scan(args.since, args.sessions, args.path)
    m = w.metrics()
    before = {}
    if state_path().is_file():
        try:
            before = json.loads(state_path().read_text(encoding="utf-8"))
        except ValueError:
            before = {}
    regressed = regressions(m["floors"], before.get("floors") or [])
    if args.json:
        print(json.dumps(dict(m, regressed=regressed), indent=2))
    else:
        report(w)
        for floor in regressed:
            print(f"  REGRESSED {floor}: it passed on {before.get('at', 'the previous run')}")
    try:
        state_path().parent.mkdir(parents=True, exist_ok=True)
        state_path().write_text(json.dumps(
            {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
             "since": args.since, "floors": m["floors"]}, indent=2), encoding="utf-8")
    except OSError as exc:                 # a report that cannot be cached still reports
        print(f"report: state not written: {exc}", file=sys.stderr)
    return 1 if args.check and regressed else 0


def _events(parent: pathlib.Path) -> list:
    """The parent's log flattened to (kind, text): a tool call's arguments, a tool
    result's text, an assistant message's text -- in order."""
    out = []
    for e in _entries(parent):
        m = e.get("message") if e.get("type") == "message" else None
        if not isinstance(m, dict):
            continue
        if m.get("role") == "toolResult":
            out.append(("result", _texts(m.get("content"))))
        elif m.get("role") == "assistant":
            for p in m.get("content") or []:
                if isinstance(p, dict) and p.get("type") == "toolCall":
                    out.append(("call", json.dumps(p.get("arguments"), ensure_ascii=False)))
            out.append(("text", _texts(m.get("content"))))
    return out


def used(answer: str, later: list) -> bool:
    """The heuristic in the module docstring."""
    paths = {m.group("path") for m in REF.finditer(answer)} | set(URL.findall(answer))
    quotes = [a or b for a, b in QUOTE.findall(answer)]
    lines = [s.strip() for s in answer.splitlines() + quotes if len(s.strip()) >= MIN_LINE]
    for kind, text in later:
        if kind == "result":
            continue
        if any(p in text for p in paths):
            return True
        if kind == "text" and any(s in text for s in lines):
            return True
    return False


def replay(parent: pathlib.Path) -> list:
    """Every delegation one parent session made, each recomputed from its child's
    log, with `used` judged from what the parent did afterwards."""
    events = _events(parent)
    lines = []
    for i, (kind, text) in enumerate(events):
        if kind != "result":
            continue
        for m in MARK.finditer(text):
            child = pathlib.Path(m.group("session"))
            if not child.is_file():
                continue
            ln = line_for(child, m.group("role"))
            ln["used"] = used(child_facts(child)["answer"], events[i + 1:])
            ln["parent"] = str(parent)
            lines.append(ln)
    return lines


def parents(n: int, root: pathlib.Path = SESSIONS) -> list:
    """The `n` most recent parent session logs (children live in `pi-agent/`)."""
    found = []
    for p in root.glob("*/*.jsonl"):
        if p.parent.name == "pi-agent":
            continue
        try:
            found.append((p.stat().st_mtime, p))
        except OSError:
            continue
    return [p for _m, p in sorted(found, reverse=True)[:n]]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration delegations",
                                 description="The delegation log (5c): read it, or replay "
                                             "parent sessions to recompute it with `used`.")
    ap.add_argument("--replay", type=int, metavar="N",
                    help="recompute the delegations of the N most recent parent sessions")
    ap.add_argument("--parent", type=pathlib.Path, metavar="PATH",
                    help="recompute the delegations of this parent session log")
    ap.add_argument("--write", action="store_true",
                    help="upsert the replayed lines into the log (`used` filled)")
    ap.add_argument("--root", type=pathlib.Path, default=SESSIONS)
    ap.add_argument("--json", action="store_true", help="one JSON line per delegation")
    args = ap.parse_args(argv)
    if args.replay is not None and args.parent is not None:
        print("delegations: --replay and --parent name the same thing", file=sys.stderr)
        return 2
    if args.replay is None and args.parent is None:
        rows = read(log_path())
    else:
        if args.parent is not None:
            if not args.parent.is_file():
                print(f"delegations: no session log at {args.parent}", file=sys.stderr)
                return 2
            ps = [args.parent]
        else:
            if args.replay < 1:
                print("delegations: --replay needs a positive count", file=sys.stderr)
                return 2
            ps = parents(args.replay, args.root)
            if not ps:
                print(f"delegations: no parent session under {args.root}", file=sys.stderr)
                return 2
        rows = [ln for p in ps for ln in replay(p)]
    if args.write:
        if args.replay is None and args.parent is None:
            print("delegations: --write needs --replay or --parent", file=sys.stderr)
            return 2
        added, updated = upsert(rows)
        # stderr: the hook that calls this at session end keeps no console, and a
        # manual run reads the one line it needs there either way.
        print(f"delegations: {added} line(s) written, {updated} updated in {log_path()}",
              file=sys.stderr)
        return 0
    if args.json:
        for r in rows:
            print(json.dumps(r, sort_keys=True))
        return 0
    print(f"delegations -- {len(rows)} line(s)"
          + (f" from the last {args.replay} parent session(s)" if args.replay else f" in {log_path()}"))
    for r in rows:
        u = {None: "?", True: "used", False: "unused"}[r.get("used")]
        print(f"  {r['ts'][:16]} {r['role']:9} {r['model'][:28]:28} "
              f"read {r['bytes_read']:>8} B  returned {r['bytes_returned']:>6} B  "
              f"x{r['compression'] or 0:<6} {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
