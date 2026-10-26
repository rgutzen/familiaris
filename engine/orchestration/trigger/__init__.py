"""trigger -- item 5b: option B's count trigger, replayed over the real pi logs.

WHY THIS EXISTS. The track opened with a measurement: across 112 pi sessions, and
300 sessions in three harnesses, **no session delegated real work**
(`dev/orchestration/2026-10-12-delegation-usage.md`). One explanation the record
leaves standing is explanation 1 -- *delegation is a judgement call the parent
never makes*. An always-on sentence ("Offload bulk recon ... with `pi-agent`") is
not a trigger, so B replaces the judgement with a count. This module is the count,
replayed against the logs it was calibrated on, so the number in `PLAN.md` can be
re-measured instead of believed.

THE TRIGGER. Inside ONE USER TURN, `>= 6` distinct files read AND `>= 80 KB` of
tool output. It is evaluated at each tool result and fires ONCE per turn, at the
first result where both floors hold. The candidate replays are the table in
`2026-10-12-delegation-usage.md` §the table at lines ~40-70; the chosen row is
`>= 6 files & >= 80 KB` -- 27% of turns, 84% precision, 97% recall, 39% of all
tool-output bytes at or after a fire. Precision outranks the 9 points of headroom
the looser rows add: an advisory hint that is wrong a third of the time is a hint
the parent learns to ignore.

A TURN is a `message` entry whose `message.role` is `user`, up to the next one.
Not pi's `turn_start`/`turn_end` (one assistant response and its tool results):
there are several of those per user prompt, and the cost B exists to bound -- the
transcript every later request re-reads as cached input -- is per user turn.
Extension-sent content is not a user message, so the hint this item adds cannot
move its own denominator.

WHAT IS COUNTED AS A FILE -- the deviation, stated first. `read_paths` is the
reading-tool rule the item names: the arguments of `read`, `grep`, `find` and
`ls`, and nothing else. On these logs that rule fires on **2 of 108 turns
(1.9%)**, because the model here reads through the shell: 11,167 `bash` calls
against 532 four-tool calls across all 154 logs, and 3,903 against 94 in the last
thirty. The 2026-10-12 replay counted `read` paths **and** `cat`/`sed -n`/`head`/
`tail` inside bash, so a replay of the four tools alone measures a different
trigger than the one whose 27% is the target -- and an extension carrying that
rule would fire almost never, which is a property of the counting, not of the
workload. `bash_read_paths` therefore implements the record's own bash rule, and
the trigger's file set is the union of the two. Both rates are printed on every
run, and a test pins each rule separately. Replayed 2026-10-14: union 31/108
(28.7%) over the last 30 logs and 91/365 (24.9%) over the last 112, against the
record's 27% -- so the union is the comparable method and stays the default.

Exactly which argument names a file, per rule:

  read   `path`          the file itself
  grep   `path`, `glob`  the search root, and the filter it restricts to
  find   `path`          the search root; never `pattern`, a glob is not a file
  ls     `path`          the directory listed; an absent `path` is the process's
                         cwd, which names no file, so absent counts nothing
  bash   the non-flag arguments of `cat`, `sed`, `head`, `tail`, per command
                         segment, `sed`'s first one excluded as its script
                         (`SCRIPT_ARG`) along with a redirect operator and its
                         target, keeping tokens that contain `/` or `.`

Two limits, named rather than hidden. A shell command is not parseable exactly:
`bash_read_paths` is a token rule, so `xargs cat`, a path built in a variable, and
a command inside an unbalanced quote are missed, while a redirect target can be a
false positive. Distinctness is by the exact string the model wrote, so the same
path read four times counts one file, and a relative and an absolute spelling of
one file count two: a path the model wrote is what the replay counts, and per-entry
cwd is not in the log.

A TURN's bytes are the `len(text)` of every text block of every `toolResult`
message in the turn (`tool_output_bytes`), which is the record's "all tool-result
text" -- characters, not the file size on disk; the logs are UTF-8 and near-ASCII,
so the two differ by under a percent. `len` is Python's: the live extension counts
UTF-16 code units, so the two disagree by a few characters on a non-BMP character
-- measured 2026-10-14 across 7,469 real results, 56 of them (0.8%), never near
the 80 KB floor.

WHERE THE NUMBERS LIVE. In this module, as named constants carrying their source.
They are **replayed parameters, not a policy**: `config/orchestration/` holds the
track's directives, and a directive is read and ratified by the user, while a
trigger floor is an estimate whose only credential is the replay that produced it.
An estimate belongs beside the code that re-measures it. A threshold change is a
**re-calibration under a new wording or a new method** -- it moves the precision
and the recall in the record, so it has to be replayed and re-recorded like this
one was, never tuned.

`pi-agent/` under the sessions root holds pi-agent CHILDREN's own logs: a child
runs from the child's cwd, so its slug is a second directory, and a child's reads
are already inside the parent's `bash` tool call. Counting them would double-count
a delegation in the session that delegated, and 5d measures uptake in parents.
`recent_logs` skips that directory by name; a test pins it.

Paths must be passed after `--` (or as plain filenames): a session directory slug
starts with `--`, so without the separator argparse reads it as a flag.

Usage:
  familiar orchestration trigger [--replay N] [--since DATE] [--json]
                        [--sessions DIR] [-- LOG...]

Exit: 0 when it can report, 2 on a usage error (a bad flag, `--replay 0`, or a
sessions root that does not exist). One unreadable log never fails the run: it is
named on stderr, counted in `skipped`, and the replay continues -- 5b's exit is a
reading, so a replay that refuses to report cannot be quoted.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import shlex
import sys
from collections.abc import Iterable, Iterator

# --- the replayed parameters, and where each one comes from -----------------
# `config/orchestration/` is the track's directive folder and is deliberately not
# read here: these are the numbers of a measurement, not a rule. Sources:
# dev/orchestration/2026-10-12-delegation-usage.md §the table at lines ~40-70
# (the row `>= 6 files & >= 80 KB`), digested in dev/orchestration/PLAN.md
# §"Option B, decided -- the trigger and its floor".

MIN_FILES = 6                      # the row's file floor
MIN_BYTES = 80 * 1024              # the row's byte floor, 80 KB of tool output
RECORDED_RATE = 0.27               # the row's fire rate, 112 sessions, 2026-10-12
RATE_TOLERANCE = 0.20              # 5b's exit: within +-20% of the recorded rate
RECORDED_PRECISION = 0.84          # turns that fired and ended >= 100 KB
RECORDED_RECALL = 0.97             # turns >= 100 KB that fired
RECORDED_BYTES_SHARE = 0.39        # tool-output bytes at/after a fire, upper bound
RECORDED_SESSIONS = 112            # the recorded replay's window, 2026-09-06..10-12
RECORDED_ON = "2026-10-12"

# The role 5a wrote (`config/orchestration/explore.md`, model `deepseek-flash`),
# and the command a parent delegates with. The hint names both; the report only
# names them, because a replay must not write anything.
ROLE = "explore"
DELEGATE = 'pi-agent explore "<task>"'

DEFAULT_REPLAY = 30                # 5b's exit runs `--replay 30`
SESSIONS = pathlib.Path.home() / ".pi" / "agent" / "sessions"
PI_AGENT_LOGS = "pi-agent"         # pi-agent children's own logs; see the docstring

# The reading-tool rule: which argument of which tool call names a file it reads.
# One small table, consumed by `read_paths`, so "which arguments are counted" is
# answerable by reading four lines rather than by tracing a parser.
FILE_ARGS = {
    "read": ("path",),
    "grep": ("path", "glob"),
    "find": ("path",),
    "ls": ("path",),
}

# The record's bash rule: the commands that dump a file's contents into the tool
# result, exactly as `2026-10-12-delegation-usage.md`'s reproduce block lists
# them. `bat`, `nl`, `less` and the search commands are NOT added: they are the
# same act, but the record did not count them, and a re-calibration is a replayed
# change, not a silent widening.
BASH_READ_COMMANDS = ("cat", "sed", "head", "tail")
_BASH_SEGMENT = re.compile(r"[;&|]{1,2}|\n")

# `sed`'s first non-flag argument is its script (`sed -n '1,200p' file`,
# `sed -i '/re/d' file`), never a file: without this rule a quoted script
# containing `/` is counted as a path, which is how `sed -i '/"eval": …/d'` read
# as a file in the 2026-10-14 replay before the rule was added.
SCRIPT_ARG = {"sed": 1}

# The nudge's own marker (12b), and what a delegation looks like in a tool call.
NUDGE_TYPE = "explore-trigger"
WITHHELD_TYPE = "explore-trigger-withheld"   # 14a: pi-trigger's WITHHELD_TYPE
PI_AGENT_CALL = re.compile(r"(?:^|[\s;&|(])pi-agent(?![\w-])")


def read_paths(name, arguments) -> list[str]:
    """The file arguments one reading-tool call names, per `FILE_ARGS`.

    Not a resolver: a relative and an absolute spelling of one file are two files
    here, as in the record, because resolving needs the cwd the entry does not
    carry.
    """
    keys = FILE_ARGS.get(name)
    if not keys or not isinstance(arguments, dict):
        return []
    return [v for k in keys
            if isinstance(v := arguments.get(k), str) and v]


def bash_read_paths(command) -> set[str]:
    """The files a bash command reads, per `BASH_READ_COMMANDS`.

    The record's rule, and deliberately a token rule: the command is split at
    `;` `&&` `||` `|` and newline, each segment is tokenized with `shlex.split`,
    and a segment whose first token (basename) is a reading command contributes
    its non-flag arguments -- minus `SCRIPT_ARG`'s script argument, minus a
    redirect operator and its target -- when they contain `/` or `.`. Anything
    else is not a path: `echo a.b`, a flag, a bare word. A shell is not parseable
    exactly, so this is a lower bound with false positives (a redirect target,
    `cat > x.md`) and false negatives (`xargs cat`, a path in a variable, an
    untokenizable quote); the module docstring says so where the number is
    compared.
    """
    if not isinstance(command, str):
        return set()
    found = set()
    for segment in _BASH_SEGMENT.split(command):
        try:
            argv = shlex.split(segment.strip())
        except ValueError:
            continue
        if not argv:
            continue
        name = argv[0].rsplit("/", 1)[-1]
        if name not in BASH_READ_COMMANDS:
            continue
        scripts = SCRIPT_ARG.get(name, 0)
        skip_next = False
        for token in argv[1:]:
            if skip_next:
                skip_next = False
                continue
            if token.startswith((">", "<")):
                skip_next = len(token) == 1
                continue
            if token.startswith("-"):
                continue
            if scripts:
                scripts -= 1
                continue
            if "/" in token or "." in token:
                found.add(token)
    return found


def tool_output_bytes(message) -> int:
    """`len(text)` over a toolResult message's text blocks, and nothing else.

    0 for any other shape: an image block, a missing `content`, or a result a
    handler replaced. The record's "bytes are all tool-result text".
    """
    content = message.get("content")
    if not isinstance(content, list):
        return 0
    return sum(len(b["text"]) for b in content
               if isinstance(b, dict) and b.get("type") == "text"
               and isinstance(b.get("text"), str))


@dataclasses.dataclass
class Turn:
    """One user turn, with the counters the trigger reads and where it fired.

    `files` is what the trigger counts -- reading tools plus the bash rule;
    `files_tools` is the reading tools alone, kept so the deviation in the module
    docstring is a measured number on every run rather than a claim in prose.

    `nudges` AND `acted` ARE THE HINT'S OWN COUNT (12b), not the trigger's: a
    `custom_message` entry of type `explore-trigger` inside the turn, and how many
    of those were followed by a delegation (`pi-agent` in a bash call, or a
    `bound_*` call) before the turn closed. The report prints both beside the
    fires, so "did anybody act on the hint" is read from the transcript rather
    than remembered. `waiting` is the nudge count not yet acted on in this turn.

    `withheld` IS 14a's OTHER ARM: a `custom` entry of type
    `explore-trigger-withheld`, which the extension appends instead of the hint
    on a random share of fires. `arm` names the turn's arm from the two counts,
    and is None for a turn whose fire predates 14a (no entry of either type).
    """
    index: int                       # 1-based within its session
    start: str                       # the user entry's ISO 8601 timestamp
    files: set = dataclasses.field(default_factory=set)
    files_tools: set = dataclasses.field(default_factory=set)
    bytes: int = 0                   # every toolResult's text, the whole turn
    results: int = 0                 # tool results seen, the fire's position
    fired_at: int | None = None      # the 1-based tool result that crossed both
    fired_at_tools: int | None = None
    bytes_after: int = 0             # tool output at or after `fired_at`
    nudges: int = 0                  # explore-trigger hints sent in this turn
    acted: int = 0                   # ... of those, followed by a delegation here
    waiting: int = 0                 # nudges with no delegation yet
    withheld: int = 0                # 14a: fires recorded with no hint sent
    delegated: bool = False          # any pi-agent / bound_* call in this turn

    @property
    def fired(self) -> bool:
        return self.fired_at is not None

    @property
    def arm(self) -> str | None:
        """`nudged`, `withheld`, or None when the turn carries neither entry."""
        if self.nudges:
            return "nudged"
        return "withheld" if self.withheld else None


def delegating(name, arguments) -> bool:
    """Whether one tool call is a delegation: `pi-agent` on a command line, or a
    bound tool the bindings extension registered (both spawn `pi-agent`)."""
    if isinstance(name, str) and name.startswith("bound_"):
        return True
    return (name == "bash" and isinstance(arguments, dict)
            and isinstance(arguments.get("command"), str)
            and PI_AGENT_CALL.search(arguments["command"]) is not None)


def read_entries(path) -> Iterator[dict]:
    """The JSONL entries of one session log, line by line.

    A line that is not a JSON object is dropped, not fatal: a log truncated
    mid-write is still readable up to the truncation, and the alternative -- a
    replay that dies on the session it was reading -- hides every other session.
    The caller owns `OSError`; an unreadable file is skipped, not fatal.
    """
    with pathlib.Path(path).open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict):
                yield entry


def split_turns(entries: Iterable, min_files: int = MIN_FILES,
                min_bytes: int = MIN_BYTES) -> Iterator[Turn]:
    """Split entries into user turns, evaluating the trigger at each result.

    A turn opens at a `message` entry with `message.role == "user"` and closes at
    the next one; entries before the first user message belong to no turn, and a
    session with no user message yields nothing. Files are accumulated from
    assistant `toolCall` blocks and bytes from `toolResult` messages, so the fire
    is decided at each result: a turn that crosses both at its sixth result fires
    there, and a turn whose last result crosses the file floor never fires.
    """
    turn: Turn | None = None
    index = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        if kind == "custom_message":
            if turn is not None and entry.get("customType") == NUDGE_TYPE:
                turn.nudges += 1
                turn.waiting += 1
            continue
        if kind == "custom":
            if turn is not None and entry.get("customType") == WITHHELD_TYPE:
                turn.withheld += 1
            continue
        if kind != "message":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "user":
            if turn is not None:
                yield turn
            index += 1
            turn = Turn(index=index, start=str(entry.get("timestamp", "")))
            continue
        if turn is None:
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if role == "assistant":
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "toolCall"):
                    continue
                name, arguments = block.get("name"), block.get("arguments")
                if delegating(name, arguments):
                    turn.delegated = True
                    turn.acted += turn.waiting      # a nudge acted on, in its own turn
                    turn.waiting = 0
                found = read_paths(name, arguments)
                turn.files_tools.update(found)
                turn.files.update(found)
                if name == "bash" and isinstance(arguments, dict):
                    turn.files.update(bash_read_paths(arguments.get("command")))
        elif role == "toolResult":
            size = tool_output_bytes(message)
            turn.bytes += size
            turn.results += 1
            crossed_bytes = turn.bytes >= min_bytes
            if turn.fired_at is None and crossed_bytes \
                    and len(turn.files) >= min_files:
                turn.fired_at = turn.results
            if turn.fired_at_tools is None and crossed_bytes \
                    and len(turn.files_tools) >= min_files:
                turn.fired_at_tools = turn.results
            if turn.fired_at is not None:
                turn.bytes_after += size
    if turn is not None:
        yield turn


def session_turns(path, min_files: int = MIN_FILES,
                  min_bytes: int = MIN_BYTES) -> list[Turn]:
    """The turns of one log file. Raises `OSError` if the file cannot be read."""
    return list(split_turns(read_entries(path), min_files, min_bytes))


def _mtime(path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def log_date(path: pathlib.Path) -> str:
    """The `YYYY-MM-DD` a session log's filename starts with, or ''. The layout is
    `<timestamp>_<uuid>.jsonl` with the time's colons as dashes, so the first ten
    characters sort correctly against a date. A file that does not match gets '',
    which every date comparison treats as older than any window."""
    name = pathlib.Path(path).name
    head = name[:10]
    return head if len(head) == 10 and head[4] == "-" and head[7] == "-" else ""


def since_date(paths: list[pathlib.Path], since: str) -> list[pathlib.Path]:
    """Only the logs dated on or after `since` (a `YYYY-MM-DD` or any longer
    prefix of it). This is what turns a live window into one command: 5d's floor
    counts the fires that happened AFTER the trigger was installed, and the
    newest-N scan alone would count fires from the calibration session too."""
    day = since[:10]
    return [p for p in paths if log_date(p) >= day]


def recent_logs(n: int, root=SESSIONS) -> list[pathlib.Path]:
    """The `n` most recently written session logs under `root`, newest first.

    One level deep and named `*.jsonl`, matching the layout the logs have:
    `<cwd-slug>/<timestamp>_<uuid>.jsonl`. `pi-agent/` is skipped -- those are
    children's own logs, and counting them would double-count a delegation in the
    parent that delegated (see the module docstring).
    """
    logs = [p for p in pathlib.Path(root).glob("*/*.jsonl")
            if PI_AGENT_LOGS not in p.relative_to(root).parts[:-1]]
    logs.sort(key=_mtime, reverse=True)
    return logs[:n]


@dataclasses.dataclass
class Fire:
    """One fired turn, with the evidence the report prints."""
    session: pathlib.Path
    slug: str
    turn: int
    start: str
    files: list
    bytes: int
    bytes_after: int
    results: int

    def row(self) -> dict:
        return {"session": str(self.session), "slug": self.slug, "turn": self.turn,
                "start": self.start, "files": self.files, "bytes": self.bytes,
                "bytes_after": self.bytes_after, "results": self.results}


@dataclasses.dataclass
class Replay:
    """A replay's result: the logs it read, what it skipped, and the fires."""
    logs: list = dataclasses.field(default_factory=list)
    skipped: list = dataclasses.field(default_factory=list)   # (path, reason)
    turns: int = 0
    fires: list = dataclasses.field(default_factory=list)
    fires_tools: int = 0           # fires if only read/grep/find/ls counted
    bytes_total: int = 0
    bytes_after: int = 0

    @property
    def rate(self) -> float:
        return len(self.fires) / self.turns if self.turns else 0.0

    @property
    def rate_tools(self) -> float:
        return self.fires_tools / self.turns if self.turns else 0.0

    @property
    def bytes_share(self) -> float:
        return self.bytes_after / self.bytes_total if self.bytes_total else 0.0

    @property
    def band(self) -> tuple[float, float]:
        return (RECORDED_RATE * (1 - RATE_TOLERANCE),
                RECORDED_RATE * (1 + RATE_TOLERANCE))

    @property
    def within_band(self) -> bool:
        low, high = self.band
        return low <= self.rate <= high

    def row(self) -> dict:
        low, high = self.band
        return {
            "sessions": [str(p) for p in self.logs],
            "skipped": [{"path": str(p), "reason": str(r)} for p, r in self.skipped],
            "turns": self.turns,
            "fires": [f.row() for f in self.fires],
            "rate": round(self.rate, 4),
            "fires_tools_only": self.fires_tools,
            "rate_tools_only": round(self.rate_tools, 4),
            "bytes_total": self.bytes_total,
            "bytes_after": self.bytes_after,
            "bytes_share": round(self.bytes_share, 4),
            "recorded_rate": RECORDED_RATE,
            "band": [round(low, 4), round(high, 4)],
            "within_band": self.within_band,
            "role": ROLE,
            "command": DELEGATE,
        }


def run_replay(paths: Iterable, min_files: int = MIN_FILES,
               min_bytes: int = MIN_BYTES) -> Replay:
    """Replay the trigger over logs, in the order given.

    An unreadable log is named in `skipped` and the run continues -- one broken
    session must not cost the other twenty-nine.
    """
    out = Replay()
    for path in paths:
        path = pathlib.Path(path)
        out.logs.append(path)
        try:
            turns = session_turns(path, min_files, min_bytes)
        except OSError as exc:
            out.skipped.append((path, exc.strerror or str(exc)))
            continue
        out.turns += len(turns)
        for turn in turns:
            out.bytes_total += turn.bytes
            out.bytes_after += turn.bytes_after
            if turn.fired_at_tools is not None:
                out.fires_tools += 1
            if turn.fired:
                out.fires.append(Fire(
                    session=path, slug=path.parent.name, turn=turn.index,
                    start=turn.start, files=sorted(turn.files), bytes=turn.bytes,
                    bytes_after=turn.bytes_after, results=turn.results))
    return out


def _size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def report(replay: Replay, sessions=SESSIONS, since: str = "") -> str:
    """The plain report: the counts, the verdict, every fired turn, and the
    reading-tools-only rate, so the method's cost is visible on every run.

    `sessions` is the root the logs were selected from, or None when the paths
    were named on the command line -- then no exclusion happened and the header
    must not claim one.
    """
    low, high = replay.band
    where = (f"most recent under {sessions} (newest first, {PI_AGENT_LOGS}/ excluded)"
             if sessions else "log(s) named on the command line")
    window = f"; on or after {since[:10]}" if since else ""
    lines = [
        f"trigger replay -- {MIN_FILES} files & {_size(MIN_BYTES)} of tool output "
        f"in one user turn",
        f"  sessions  {len(replay.logs)} {where}{window}",
        f"  turns     {replay.turns}",
        f"  fires     {len(replay.fires)} ({replay.rate * 100:.1f}% of turns)",
        f"  files     read/grep/find/ls arguments + {'/'.join(BASH_READ_COMMANDS)} "
        f"inside bash (the record's rule); the four tools alone fire on "
        f"{replay.fires_tools} ({replay.rate_tools * 100:.1f}%)",
        f"  recorded  {RECORDED_RATE * 100:.1f}% over {RECORDED_SESSIONS} sessions "
        f"({RECORDED_ON}; {RECORDED_PRECISION:.0%} precision, "
        f"{RECORDED_RECALL:.0%} recall; {RECORDED_BYTES_SHARE:.0%} of bytes after "
        f"a fire)",
        f"  verdict   within +-{RATE_TOLERANCE:.0%} of {RECORDED_RATE:.0%} "
        f"({low * 100:.1f}% - {high * 100:.1f}%): "
        f"{'YES' if replay.within_band else 'NO'}",
        f"  bytes     {_size(replay.bytes_total)} of tool output in those turns; "
        f"{replay.bytes_share * 100:.0f}% ({_size(replay.bytes_after)}) at or after "
        f"a fire",
        f"  role      {ROLE} -- {DELEGATE} returns `path:line` + a verbatim quote",
    ]
    for path, why in replay.skipped:
        lines.append(f"  skipped   {path}: {why}")
    if replay.fires:
        lines.append("  fires")
        lines.append(f"    {'#':>3}  {'turn':>4}  {'files':>5}  {'bytes':>8}  "
                     f"{'after':>8}  {'start':<20}  slug")
        for i, fire in enumerate(replay.fires, 1):
            lines.append(f"    {i:>3}  {fire.turn:>4}  {len(fire.files):>5}  "
                         f"{_size(fire.bytes):>8}  {_size(fire.bytes_after):>8}  "
                         f"{fire.start[:19]:<20}  {fire.slug}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="familiar orchestration trigger",
        description="Replay option B's trigger over the last pi session logs.")
    parser.add_argument("paths", nargs="*", metavar="LOG",
                        help="session logs to replay instead of scanning "
                             "--sessions; pass after `--`, a slug starts with `--`")
    parser.add_argument("--replay", type=int, default=DEFAULT_REPLAY, metavar="N",
                        help=f"how many of the most recent logs to read "
                             f"(default {DEFAULT_REPLAY})")
    parser.add_argument("--sessions", type=pathlib.Path, default=SESSIONS,
                        metavar="DIR", help=f"the sessions root (default {SESSIONS})")
    parser.add_argument("--since", default="", metavar="DATE",
                        help="count only logs dated on or after DATE (YYYY-MM-DD); "
                             "the newest-N scan still runs first, so raise --replay "
                             "to reach past older sessions")
    parser.add_argument("--json", action="store_true",
                        help="one JSON object instead of the report")
    args = parser.parse_args(argv)
    if args.replay < 1:
        parser.error("--replay needs a count of at least 1")
    if args.paths:
        paths = [pathlib.Path(p) for p in args.paths]
        root = None
    else:
        root = args.sessions
        if not root.is_dir():
            print(f"trigger: no sessions root at {root}", file=sys.stderr)
            return 2
        paths = recent_logs(args.replay, root)
        if args.since:
            paths = since_date(paths, args.since)
    replay = run_replay(paths)
    for path, why in replay.skipped:
        print(f"trigger: skipped {path}: {why}", file=sys.stderr)
    print(json.dumps(replay.row(), indent=2) if args.json
          else report(replay, root, args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
