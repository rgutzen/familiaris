"""sessions -- schedule ONE session, once, at a clock time or after a delay (9a).

WHY THIS EXISTS. On 2026-10-14 three jobs were built by hand in one evening: the
4e continuation (01:45), the post-4e handoff session (06:00) and the Claude-window
ping. Each was a shell script plus -- for the first two -- a `systemd-run`
transient timer, and none of them was a *mechanism*: no listing, no cancellation,
no reuse, and no record of what a session had been asked or where its transcript
went. The evidence is `dev/orchestration/handoff-scheduled-sessions.md`; the plan
is step 9 of `dev/orchestration/SPECS.md`.

WHERE IT LIVES. The subject that owns units owns their firing, so the surface is
`familiar schedule sessions`. The model is chosen the Loom's way, so this module
imports `orchestration.profiles` and `orchestration.selection` and never a raw
`vendor/model` string. The unit pair is rendered by `timers-gen.sh
--render-entry` -- the SAME renderer `familiar schedule timers` uses -- because
the failure this mechanism exists to remove is the one-shot and the recurring
schedule drifting apart; sharing the format is not enough, so they share the
renderer.

WHAT A SESSION IS NOT. It is not an evaluation cell: only a cell runs under 8f's
`bwrap` mask, and a session that must commit code needs a writable repository.
Its safety is the permission system, the prompt it is given, and the gate before
each commit; the record says `sandbox: none` instead of leaving that implied, and
the standing prompt forbids a push. `--approve` is pi's project-trust flag (the
same one the 06:00 hand-off job used), not a permission bypass.

THE TRAPS THIS CARRIES, MEASURED ON 2026-10-14 (do not rediscover them):

* A TRANSIENT timer dies with a reboot; a DECLARED one does not. 9a's `add` wrote
  a unit pair per session for that reason; since 1d no job has a unit -- the ONE
  declared `familiar-dispatch.timer` reads the records, so a reboot loses nothing
  that is not in a record. A 9a record keeps its unit, which still fires it.
* A child session cannot run `bash -ic` ("requires approval, but no interactive
  UI is available"), so the per-session wrapper sources `~/.config/bash/local.sh`
  into the JOB's own environment before `pi` starts; plain `bash` inside the
  session is then enough, and an ask that needs a UI still fails.
* 9a wrote a recurring session as a systemd hour step (`--every 5h --at 01:35` ->
  `*-*-* 01/5:35:00`): a 24-hour day with a 5-hour step, so 21:35 -> 01:35 was a
  4-hour gap and the night's first run landed in a window already used (PLAN
  defect 1). Since 1d `--every` is a period from the last START, kept by the tick.
* Two runs must not share a results file, and the nightly pass at 03:30 commits
  the working tree. A session therefore holds a lock while it runs, and the
  standing prompt says to leave the tree safe for the nightly pass.
* The machine's compiled boundaries are writable by anything that runs
  `engine/boundaries/compile.py`; the standing prompt forbids it, and the gate's
  `boundaries-compile` check is the backstop.

THE RECORD IS APPEND-ONLY and is the point. `$PAZRAS_DATA_DIR/sessions/<slug>/`
holds `schedule.json` (the declaration, written by `add`), `runs.jsonl` (one
JSON object per event), `run-<ts>.log` (the child's own output), and the pi
transcript under `transcript/`. `run` appends a `started` row BEFORE the spawn
and a `finished` row with the exit and the transcript path after, so a later
session can tell whether it ran and what it did. A `started` with no `finished`
is LOST; a due time in the past with no `started` is MISSED. `list` and `--check`
read the record alone -- systemd is touched only by `cancel` and a hold of a 9a
record, and the dispatcher's `systemd-run` (`dispatch.py`) -- so both work in a
container and in a test.

A JOB (dev/schedule 1a). The declaration is a job: a `trigger` (`at`, `every`,
`ready`), a `chain` (`none`, `until-done`), a `priority` and the named conditions
`start_when`/`stop_when`, copied from config at `add`. A 9a record reads as
`at`/`every` and `none` (`job_of`). A retry is a run of the SAME job: a child that
exits non-zero with the rate-limit message **and** leaves the tree untouched is
HELD -- a `held` event until the refusal's reset time + `retry.after_reset` -- and
so is a run refused by another run's working-directory lock. The cap counts holds
in a row (`retry.max`). A session that half-committed is never repeated blindly.
One run per job AND per working directory; every lock refusal writes `refused`.
`cancel` called from inside the job's own run (its pid an ancestor) ENDS the job:
that is how a chain stops itself.

EXIT CODES. 0 ok. 1 usage. 2 refused before anything ran (unknown model, no such
session, a lock held, a hold not yet over). 3 drift
(`--check`) or a refused dirty tree. `run` otherwise returns the child's exit.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from lib import _miniyaml, roots
from harness import pi_call
from orchestration import models, profiles
from orchestration import selection as selection_mod
from orchestration import ping, specs, waves
from schedule import chain as chain_mod
from schedule import conditions as conditions_mod
from schedule import rpc

CONFIG = roots.CONFIG / "schedule" / "sessions.yaml"
ASK_USER = roots.ENGINE / "relay" / "pi-ask-user" / "index.ts"
# The dotfiles' loader shim for the same tool, which pi discovers by itself.
ASK_USER_SHIM = pathlib.Path("extensions") / "familiar-ask-user" / "index.ts"
GENERATOR = roots.ENGINE / "schedule" / "timers-gen.sh"
UNIT_PREFIX = "familiar-session-"
# Two windows, because they answer two questions. `LIST_WINDOW` is how long a
# finished job stays in `list` -- how much history is worth reading on a screen.
# `RETENTION` is how long its bytes are kept -- when `prune` archives it. A record
# closed 5 days ago is out of the list and still on disk, which is the point.
LIST_WINDOW = "3d"
RETENTION = "30d"
DEFAULT_UNITS = pathlib.Path.home() / ".config/systemd/user"
DEFAULT_TIMEOUT = "12h"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
_DELAY = re.compile(r"(\d+(?:\.\d+)?)\s*([smhd])")
_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}
# The dispatcher's tick (1d): `familiar-dispatch.timer` fires `*:0/5`.
DISPATCH_PRECISION = 300
# The run tells its children which job they belong to, so `checkpoint` needs no flag.
JOB_ENV, RUN_ENV = "FAMILIAR_SESSION_JOB", "FAMILIAR_SESSION_RUN"
# `checkpoint`'s answer when a stop condition holds; 0 is "continue".
STOP = 10
# A due time closer than this is "now": systemd would fire it immediately under
# `Persistent=true`, and a session asked for "now" is what `run` is for.
NOW_EPSILON = 30


class SessionError(ValueError):
    """A request that is refused before anything is written or spawned; exit 2."""


# --- where things live -------------------------------------------------------

def data_root(env=os.environ) -> pathlib.Path:
    return profiles.data_dir(env) / "sessions"


def session_dir(name: str, env=os.environ) -> pathlib.Path:
    return data_root(env) / name


def units_dir(env=os.environ) -> pathlib.Path:
    """Where the one-shot unit pair is written. Overridable so a test never
    touches the user's real systemd; the default is the user manager's own
    directory, which is also where `mantis-option-snapshots.timer` lives --
    a foreign unit beside the stowed ones is not a new kind of thing here."""
    return pathlib.Path(env.get("PAZRAS_SESSION_UNITS") or DEFAULT_UNITS).expanduser()


def load_policy(path: pathlib.Path = CONFIG) -> dict:
    """The whole file: `defaults` and `retry`."""
    return _miniyaml.load(path.read_text(encoding="utf-8"))


def load_config(path: pathlib.Path = CONFIG) -> dict:
    return load_policy(path).get("defaults") or {}


TRIGGERS = ("at", "every", "ready")
CHAINS = ("none", "until-done")


def job_of(decl: dict, defaults: dict | None = None) -> dict:
    """The job fields of a declaration (1a), with a 9a record read as what it was:
    `kind: repeat` is `trigger: every`, anything else `trigger: at`, never a chain.
    A 9a record carries no condition lists, so it gets the configured defaults."""
    if defaults is None:
        defaults = load_config()
    trigger = decl.get("trigger") or ("every" if decl.get("kind") == "repeat" else "at")
    return {
        "trigger": trigger,
        "chain": decl.get("chain") or "none",
        "priority": int(decl.get("priority", defaults.get("priority") or 50)),
        "start_when": list(decl.get("start_when", defaults.get("start_when") or [])),
        "stop_when": list(decl.get("stop_when", defaults.get("stop_when") or [])),
    }


def closed(decl: dict) -> str:
    """Why this job will never run again ('' while it may): cancelled by the user,
    or ended from inside its own run (defect 3)."""
    if decl.get("ended"):
        return f"ended at {decl['ended']}"
    if decl.get("cancelled"):
        return f"cancelled at {decl['cancelled']}"
    return ""


def closed_at(decl: dict) -> dt.datetime | None:
    """When the record closed, or None while it may still run. A stamp that is not a
    time reads as None, so a hand-edited field can neither hide a record from `list`
    nor archive it: it is shown and kept, and `show` prints the raw value."""
    for key in ("ended", "cancelled"):
        when = _when(decl.get(key))
        if when is not None:
            return when
    return None


def standing_text(defaults: dict) -> str:
    rel = defaults.get("standing_prompt") or f"{roots.CONFIG_REL}/schedule/session-prompt.md"
    path = roots.REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


# --- time --------------------------------------------------------------------

def _when(text) -> dt.datetime | None:
    """A record's own timestamp as an aware datetime, so it can be subtracted from
    the clock; None when the text is not a time at all. A stamp without an offset
    (a hand-written one) is read as local time."""
    try:
        when = dt.datetime.fromisoformat(str(text or "").strip().replace(" ", "T"))
    except ValueError:
        return None
    return when if when.tzinfo else when.astimezone()


def _span(span: dt.timedelta) -> str:
    """A duration as a person reads it: `40d`, `6h`, `12m` -- the largest unit that
    is at least one."""
    for unit, seconds in (("d", 86400), ("h", 3600), ("m", 60)):
        if span >= dt.timedelta(seconds=seconds):
            return f"{span.total_seconds() / seconds:.0f}{unit}"
    return f"{span.total_seconds():.0f}s"


def parse_delay(text: str) -> dt.timedelta:
    """`90m`, `2h`, `1h30m`, `45`, `30s` -- the shape a person types, not cron."""
    text = (text or "").strip()
    if not text:
        raise SessionError("--in needs a delay, e.g. 90m or 1h30m")
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        total = dt.timedelta(seconds=float(text))
    else:
        pos, total = 0, dt.timedelta()
        for m in _DELAY.finditer(text):
            if m.start() != pos:
                raise SessionError(f"--in {text!r}: cannot read {text[pos:]!r}; "
                                   f"use e.g. 2h, 90m, 1h30m")
            total += dt.timedelta(seconds=float(m.group(1)) * _UNITS[m.group(2)])
            pos = m.end()
        if pos != len(text):
            raise SessionError(f"--in {text!r}: cannot read {text[pos:]!r}; "
                               f"use e.g. 2h, 90m, 1h30m")
    if total <= dt.timedelta(0):
        raise SessionError("--in must be positive")
    return total


def parse_at(text: str, now: dt.datetime | None = None) -> dt.datetime:
    """A local clock time, `YYYY-MM-DD HH:MM[:SS]` (a `T` separator is fine).
    Refused when it has passed: `run <name>` is the honest way to say "now", and
    a Persistent timer whose elapse is already in the past has no defined
    semantic here (measured on nothing; not worth the experiment)."""
    text = " ".join((text or "").split())
    when = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            when = dt.datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if when is None:
        raise SessionError(f"--at {text!r}: give a local 'YYYY-MM-DD HH:MM[:SS]'")
    when = when.replace(tzinfo=(now or now_local()).tzinfo)
    if when <= (now or now_local()) - dt.timedelta(seconds=NOW_EPSILON):
        raise SessionError(f"--at {text!r} has passed; use `--in` for the future "
                           f"or `run <name>` to run it now")
    return when


def calendar_of(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M:%S")


def parse_first(text: str, now: dt.datetime | None = None) -> dt.datetime:
    """A repeating job's first start: `HH:MM` is its next occurrence, a full date is
    `parse_at`'s."""
    now = now or now_local()
    m = ANCHOR.match((text or "").strip())
    if not m:
        return parse_at(text, now)
    hh, mm = int(m.group(1)), int(m.group(2))
    if not 0 <= hh < 24 or not 0 <= mm < 60:
        raise SessionError(f"{text!r} is not a clock time")
    when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return when if when > now else when + dt.timedelta(days=1)


#: A recurring session's anchors are HOURS apart and start at a fixed clock time, which
#: systemd writes as an hour step: `*-*-* 01/5:35:00` is 01:35, 06:35, 11:35, 16:35, 21:35.
ANCHOR = __import__("re").compile(r"^(\d{1,2}):(\d{2})$")
#: A refused run is one the Claude window turned away. Matched against the child's own
#: output; the same message `familiar orchestration ping` prints (five_hour / session limit).
DENIED = __import__("re").compile(
    r"session limit|rate limit|five_hour|resets \d{1,2}:\d{2}|HTTP 429", __import__("re").I
)


def reset_time(lines: list, now: dt.datetime) -> dt.datetime | None:
    """The window's reset as the next local time it names (`resets 1:40am`), read with
    `ping.RESET` from the LAST line that carries one. The refusal's own zone suffix
    (`(Europe/Berlin)`) is not parsed: the clock time is taken as this machine's."""
    found = None
    for line in reversed(lines):
        found = ping.RESET.search(line)
        if found:
            break
    if not found:
        return None
    text = "".join(found.group(1).split()).upper()
    for fmt in ("%I:%M:%S%p", "%I:%M%p", "%H:%M:%S", "%H:%M"):
        try:
            clock = dt.datetime.strptime(text, fmt).time()
            break
        except ValueError:
            continue
    else:
        return None
    when = now.replace(hour=clock.hour, minute=clock.minute, second=clock.second,
                       microsecond=0)
    return when if when > now else when + dt.timedelta(days=1)


def parse_timeout(text: str) -> int:
    if not text:
        return 12 * 3600
    try:
        return int(parse_delay(text).total_seconds())
    except SessionError:
        return 12 * 3600


# --- model resolution (the Loom's way) ---------------------------------------

def resolve_model(args, defaults: dict, cwd: pathlib.Path, *, cat: dict | None = None,
                  caps: dict | None = None, sel: dict | None = None,
                  profile: str | None = None) -> dict:
    """(id, effort, who chose, and the pi model that profile serves). A catalogue
    id through `profiles.resolve`, or a `selection.yaml` class through its tier and
    cheapest member -- never a raw vendor/model string (decision 25/26). The effort
    is validated with `models.effort_reason`: a level a model does not have is
    refused, never clamped (the qwen3:4b rule). The profile is the job's own (2a),
    passed in; it is not read from the environment here."""
    model_arg = getattr(args, "model", None)
    klass = getattr(args, "klass", None)
    if model_arg and klass:
        raise SessionError("--model and --class are alternatives; name one")
    cat = cat or models.load()
    caps = caps or models.load_capabilities()
    profile = profile or profiles.active()
    if klass:
        sel = sel or selection_mod.with_needs(selection_mod.load(), caps)
        tier, idx, why = selection_mod.pick(sel, klass, getattr(args, "difficulty", None))
        from orchestration import dispatch as _dispatch       # noqa: PLC0415
        ids, note = selection_mod.cheapest(cat, caps, tier,
                                           # a record outlives the window: no 14d weight
                                           _dispatch.load_config(caps)["rules"],
                                           selection_mod._allowed(cat, str(cwd)))
        if not ids:
            raise SessionError(f"class {klass}: no available model{note}")
        model_id = ids[0]
        effort = getattr(args, "effort", "") or selection_mod.effort_of(tier, model_id)
        source = f"class {klass} tier {idx + 1} ({why})"
    else:
        model_id = model_arg or defaults.get("model") or ""
        if not model_id:
            raise SessionError("name a model: --model <catalogue id> or --class <class>")
        effort = getattr(args, "effort", "") or defaults.get("effort") or ""
        source = "--model" if model_arg else f"config default ({CONFIG.name})"
    why = models.effort_reason(cat, model_id, effort)
    if why:
        raise SessionError(why)
    # A RECORD OUTLIVES THE WINDOW (15a): the same reason the pick above is made
    # without 14d's quota weight. A session added now may run after the window
    # resets, so a spent window must not refuse it at ADD time -- the fire refuses
    # (1229) if it is still spent when the job actually starts.
    res = profiles.resolve(model_id, profile, cat=cat, window=None)
    if not res.available:
        raise SessionError(f"{model_id}: unavailable in profile {profile}: {res.reason}")
    return {"id": model_id, "effort": effort, "source": source,
            "pi_model": f"{res.provider}/{res.model}", "privacy": res.privacy,
            "pool": res.pool}


# --- the ask (a prompt file, or a SPECS item/wave) ---------------------------

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _touches_of(items: list) -> list:
    out = []
    for it in items:
        for raw in specs._split(it.fields.get("touches", "")):
            if raw not in out:
                out.append(raw)
    return out


def resolve_ask(decl: dict) -> dict:
    """The ask AS IT IS AT RUN TIME. `add` records the SELECTOR (`--specs` with
    no `--item` means "the next open wave"), and the wave is resolved here,
    because the next open wave at 06:00 is not the one that was next at 23:00.
    The record then names the resolved items and hashes the source it read."""
    ask = decl["ask"]
    path = pathlib.Path(ask["path"])
    if not path.is_file():
        raise SessionError(f"{path}: the ask's source is gone")
    text = path.read_text(encoding="utf-8")
    out = {"kind": ask["kind"], "path": str(path), "selector": ask.get("selector", ""),
           "sha256": _sha(text), "bytes": len(text.encode("utf-8")),
           "items": [], "wave": 0, "touches": list(decl.get("touches") or []),
           "text": text}
    if ask["kind"] == "prompt":
        return out
    contract = specs.load_contract()
    items = specs.parse(text, set(contract["fields"]))
    plan = waves.build(items, contract["none"])
    if ask.get("item"):
        chosen = [it for it in items if it.id == ask["item"] and not it.done]
        if not chosen:
            raise SessionError(f"{path}: no open item {ask['item']!r}")
    elif ask.get("all"):
        chosen = [it for it in items if not it.done]
        if not chosen:
            raise SessionError(f"{path}: no open items")
    else:
        open_waves = [[it for it in w if not it.done] for w in plan]
        open_waves = [w for w in open_waves if w]
        if not open_waves:
            raise SessionError(f"{path}: no open wave")
        idx = int(ask.get("wave") or 1) - 1
        if not 0 <= idx < len(open_waves):
            raise SessionError(f"{path}: --wave {idx + 1}; there are "
                               f"{len(open_waves)} open wave(s)")
        chosen, out["wave"] = open_waves[idx], idx + 1
    preamble, blocks = _prompt_parts(text, items)
    body = "\n\n".join(blocks[it.id] for it in chosen)
    out["items"] = [it.id for it in chosen]
    out["text"] = preamble.strip() + "\n\n" + body
    for raw in _touches_of(chosen):
        if raw not in out["touches"]:
            out["touches"].append(raw)
    return out


def _prompt_parts(text: str, items: list) -> tuple:
    """(preamble, {id: the item's own text}). The same span rule `specs.parse`
    reads fields by, so an item carries its own prose and fields and nothing of
    its neighbours'; imported lazily because `eval` is a heavy module and this
    mechanism does not need it to `add` or `list`."""
    from orchestration import eval as _eval                  # noqa: PLC0415
    return _eval.prompt_parts(text, items)


def describe_ask(ask: dict) -> str:
    tail = (f", {ask['bytes']} bytes, sha256 {ask['sha256'][:12]}"
            if ask.get("bytes") is not None else "")
    if ask["kind"] == "prompt":
        return f"the file {ask['path']}{tail}"
    which = (f"item(s) {', '.join(ask['items'])}" if ask["items"]
             else f"wave {ask['wave']}")
    return f"{ask['path']} ({which}{tail})"


def build_prompt(decl: dict, ask: dict, defaults: dict, started: dt.datetime, *,
                 notes: tuple = (), carry: str = "") -> str:
    """What the child receives: the generated header (the ask, the scope, the
    record, the model), the standing rules from config, then the task text."""
    model = decl["model"]
    branch = decl.get("branch") or "(the branch the tree is on)"
    lines = [
        "# A scheduled session",
        "",
        f"This session was started by `familiar schedule sessions` at "
        f"{started.isoformat(timespec='seconds')} with nobody at the terminal.",
        f"**Asked:** {describe_ask(ask)}",
        f"**Working directory:** {decl['cwd']}  (branch {branch})",
        f"**Write scope:** {', '.join(ask['touches']) or '(the prompt is the only scope)'}",
        f"**Model:** {model['id']} at effort {model['effort'] or 'off'} "
        f"({model['source']}, profile {profiles.declared(decl)}) "
        f"-- the account this run spends.",
        f"**Commit:** {decl['commit']} on {branch}; never a push; "
        f"`python3 {roots.ENGINE_REL}/checks/checks.py --run pre-commit` before each commit.",
        f"**Record:** {decl['record']}/schedule.json -- this run appends a row to "
        f"`{decl['record']}/runs.jsonl` and keeps its log and transcript beside it.",
        "**Not sandboxed.** Your safety is the permission system, these rules and "
        "the gate; there is no `bwrap` mask around a session.",
        "",
        *notes,
        "",
        standing_text(defaults),
        "",
        "---",
        "",
    ]
    if carry:
        lines += [carry, "---", ""]
    return "\n".join(lines) + ask["text"].rstrip() + "\n"


# --- the record --------------------------------------------------------------

def read_decl(d: pathlib.Path) -> dict:
    path = d / "schedule.json"
    if not path.is_file():
        raise SessionError(f"no session at {d} (no schedule.json)")
    return json.loads(path.read_text(encoding="utf-8"))


def write_decl(d: pathlib.Path, decl: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "schedule.json").write_text(json.dumps(decl, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8")


def read_events(d: pathlib.Path) -> list:
    path = d / "runs.jsonl"
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"event": "unreadable", "raw": line})
    return out


def write_event(d: pathlib.Path, row: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    with (d / "runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class RunLock:
    """One run per session at a time. The evaluation's trap was two writers on
    one results file; a session's transcript and tree are the same kind of
    resource, so a second `run` refuses instead of interleaving.

    The file says which process holds it (`pid N`): `cancel` reads that to tell its
    own run from someone else's. It is opened WITHOUT truncation and rewritten only
    once the lock is taken -- a refused attempt used to erase the holder's line."""

    def __init__(self, d: pathlib.Path | None, *, path: pathlib.Path | None = None,
                 refusal: str = "", label: str = ""):
        self.path = path or d / "run.lock"
        self.refusal = refusal or f"{self.path.parent.name}: a run is already in flight"
        self.label = label
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = self.path.open("a+")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise SessionError(self.refusal) from None
        self.fh.seek(0)
        self.fh.truncate()
        self.fh.write(f"pid {os.getpid()}\n" + (f"job {self.label}\n" if self.label else ""))
        self.fh.flush()
        return self

    def holder(self) -> int | None:
        """The pid the lock file names, or None."""
        try:
            text = self.path.read_text(encoding="utf-8")
        except OSError:
            return None
        m = re.search(r"^pid (\d+)$", text, re.M)
        return int(m.group(1)) if m else None

    def held(self) -> bool:
        """Would a new run refuse? Read from a DIFFERENT handle, so asking does
        not take the lock (used by `cancel` and `list`)."""
        if not self.path.is_file():
            return False
        with self.path.open("r+") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
                return False
            except OSError:
                return True

    def __exit__(self, *exc):
        if self.fh:
            self.fh.close()
        return False


def cwd_lock(cwd, env=os.environ, *, label: str = "") -> RunLock:
    """One run per WORKING DIRECTORY at a time, beside the per-job lock: two jobs in
    one repository race for its index and commit each other's files (defect 5)."""
    key = _sha(str(pathlib.Path(cwd).expanduser().resolve()))[:16]
    return RunLock(None, path=data_root(env) / "locks" / f"{key}.lock", label=label,
                   refusal=f"{cwd}: another scheduled run holds this working directory")


def ancestors(pid: int | None = None) -> list:
    """The strict ancestors of this process (parent first), from `/proc/<pid>/stat`.
    A run's own agent calls `cancel` from a shell pi started, so the run's pid is
    among them; the same check from another terminal finds nothing."""
    out = []
    pid = os.getppid() if pid is None else pid
    while pid > 1 and pid not in out:
        out.append(pid)
        try:
            stat = pathlib.Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            break
        pid = int(stat.rsplit(")", 1)[1].split()[1])
    return out


def hold_until(events: list) -> dt.datetime | None:
    """The time the job is held until: the last `held` event, unless a run started
    after it (a held job that ran is no longer held)."""
    for e in reversed(events):
        if e.get("event") == "started":
            return None
        if e.get("event") == "held":
            try:
                return dt.datetime.fromisoformat(e["until"])
            except (KeyError, ValueError):
                return None
    return None


def refusal_streak(events: list) -> int:
    """How many holds since the last run the window let through. Defect 4 was a
    LIFETIME count (every `-rN` ever made); this one resets on a run that was not
    refused, so a job that worked yesterday is not capped today."""
    n = 0
    for e in reversed(events):
        if e.get("event") == "finished" and not e.get("window_refused"):
            break
        if e.get("event") == "held" and e.get("why") != "held by hand":
            n += 1
    return n


def _state(decl: dict, events: list, now: dt.datetime) -> dict:
    """The one-word state `list` prints, read from the record alone."""
    if decl.get("ended"):
        return {"state": "ended", "last": None, "finished": None}
    if decl.get("cancelled"):
        return {"state": "cancelled", "last": None, "finished": None}
    why = chain_mod.paused(events, _ask_sha(decl)) if decl.get("chain", "none") != "none" else ""
    if why:
        return {"state": "paused", "last": None, "finished": None, "why": why}
    until = hold_until(events)
    if until is not None:
        held = [e for e in events if e.get("event") == "held"][-1]
        return {"state": "held", "last": held, "finished": None, "until": until,
                "why": held.get("why", "")}
    started = [e for e in events if e.get("event") == "started"]
    finished = [e for e in events if e.get("event") == "finished"]
    last_finished = finished[-1] if finished else None
    last_started = started[-1] if started else None
    def _when(e):
        try:
            return dt.datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError):
            return dt.datetime.fromtimestamp(0, dt.timezone.utc)
    if last_finished and (not last_started or _when(last_finished) >= _when(last_started)):
        # Only a one-off is DONE after a run. A chain between runs continues and a
        # repeating job repeats (2026-10-21: `/status` called a chain mid-way "done").
        job = job_of(decl, {})
        state = ("continuing" if job["chain"] != "none" else
                 "repeating" if job["trigger"] == "every" else "done")
        return {"state": state, "last": last_finished, "finished": last_finished,
                "started": last_started}
    crashed = [e for e in events if e.get("event") == "crashed"]
    if crashed and (not last_started or _when(crashed[-1]) >= _when(last_started)):
        return {"state": "crashed", "last": crashed[-1], "finished": crashed[-1],
                "started": last_started, "error": crashed[-1].get("error", "")}
    if last_started:
        # An ask with no answer after the last start: the run waits for the owner, which
        # is neither work nor loss -- the timeout does not count it (rpc.py).
        since = events[events.index(last_started):]
        open_asks = ({e["ask"] for e in since if e.get("event") == "ask"}
                     - {e["ask"] for e in since if e.get("event") == "answer"})
        if open_asks:
            return {"state": "waiting", "last": last_started, "finished": None,
                    "started": last_started, "asks": sorted(open_asks)}
        waited = sum(float(e.get("waited_s") or 0) for e in since if e.get("event") == "answer")
        age = (now - dt.datetime.fromisoformat(last_started["ts"])).total_seconds() - waited
        budget = parse_timeout(decl.get("timeout", DEFAULT_TIMEOUT))
        return {"state": "running" if age < budget else "LOST",
                "last": last_started, "finished": None, "started": last_started}
    trigger = job_of(decl, {})["trigger"]
    if trigger == "every":
        # A clock-step unit has no single due time: it is waiting for its next anchor.
        return {"state": "repeating", "last": None, "finished": None}
    if trigger == "ready":
        return {"state": "ready", "last": None, "finished": None}
    due = dt.datetime.fromisoformat(decl["due"])
    if due < now:
        # A 9a unit that passed its time without a run MISSED it; a job the dispatcher
        # starts is merely DUE until a tick finds its conditions clear.
        return {"state": "missed" if decl.get("unit", "x") else "due",
                "last": None, "finished": None}
    return {"state": "pending", "last": None, "finished": None}


# --- units (one renderer, from timers-gen.sh) --------------------------------

def _homed(p) -> str:
    """Under $HOME, the form the unit renderer writes as `%h/<rel>` -- a home
    rename then keeps working. Outside it, absolute, which the renderer takes as
    written (a test, or a relocated PAZRAS_DATA_DIR)."""
    try:
        return str(pathlib.Path(p).resolve().relative_to(pathlib.Path.home()))
    except ValueError:
        return str(p)


def render_units(name: str, decl: dict, out_dir: pathlib.Path, *,
                 run=subprocess.run) -> None:
    """The unit pair, through `timers-gen.sh --render-entry`. The row's fields
    are the SAME `key=value;` dialect PAZRAS_TIMERS uses, so the pairing of
    `OnActiveSec`/`OnUnitActiveSec`, the `Persistent` rule, the PATH line and
    the notify wiring are the ones already tested in test_timers_gen.py."""
    unit = f"{UNIT_PREFIX}{name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = _row(unit, {
        "on_calendar": decl["on_calendar"],
        "exec": _homed(decl["wrapper"]),
        "desc": f"scheduled session {name}: {decl['ask']['kind']} {decl['ask']['path']}",
        "persistent": "true",
        "randomized_delay": "",
        "notify": "true",
        "accuracy": decl.get("accuracy", "1s"),
        "nice": str(decl.get("nice", "15")),
        "timeout_start": decl.get("timeout", DEFAULT_TIMEOUT),
        "doc": _homed(f"{decl['record']}/schedule.json"),
    })
    p = run(["bash", str(GENERATOR), "--render-entry", entry, "--out", str(out_dir)],
            capture_output=True, text=True)
    if getattr(p, "returncode", 0):
        raise SessionError(f"the unit renderer refused {unit}: "
                           f"{(p.stderr or p.stdout or '').strip()}")


def _row(unit: str, fields: dict) -> str:
    parts = [unit]
    for key, value in fields.items():
        if ";" in str(value) or "\n" in str(value):
            raise SessionError(f"{unit}: {key} contains ';' or a newline, which the "
                               f"PAZRAS_TIMERS dialect cannot carry")
        parts.append(f"{key}={value}")
    return ";".join(parts)


def write_wrapper(d: pathlib.Path, name: str, decl: dict, *, env=os.environ) -> pathlib.Path:
    """The job's own environment. systemd starts a service with almost nothing;
    the keys live in `~/.config/bash/local.sh` and a CHILD cannot run `bash -ic`,
    so they are sourced here, before `pi` exists -- the boundary stays intact
    (an ask that needs a UI still fails)."""
    rel_install = roots.INSTALL.relative_to(pathlib.Path.home())
    sh = d / "run.sh"
    sh.write_text(f"""#!/usr/bin/env bash
# GENERATED by `familiar schedule sessions` (step 9a) -- do not hand-edit.
# record: {decl['record']}/schedule.json
#
# The keys are sourced into THIS job's environment because a session cannot run
# `bash -ic` (the permission system answers "requires approval, but no
# interactive UI is available"). Plain bash inside the session is then enough.
set -u
export PATH="$HOME/.local/share/mise/shims:$HOME/bin:$HOME/.local/bin:$PATH"
source "$HOME/.config/bash/local.sh" 2>/dev/null || \\
  echo "[familiar] ~/.config/bash/local.sh is missing; keys may be absent" >&2
exec "$HOME/{rel_install}/{roots.ENGINE_REL}/familiar" schedule sessions run {name}
""", encoding="utf-8")
    sh.chmod(0o755)
    return sh


# --- git state ---------------------------------------------------------------

def git_dirty(cwd: str | pathlib.Path, *, run=subprocess.run) -> list:
    """The work tree's uncommitted paths, from `git status --porcelain`.

    A directory that is not a repository has no uncommitted work to protect and
    no commits to make, so it is not "dirty" -- a session may legitimately work
    outside git. A git that fails for any OTHER reason is refused rather than
    read as clean: an unreadable tree is not an empty one."""
    p = run(["git", "-C", str(cwd), "status", "--porcelain"],
            capture_output=True, text=True)
    if getattr(p, "returncode", 0):
        err = (p.stderr or "").strip()
        if "not a git repository" in err:
            return []
        raise SessionError(f"{cwd}: {err or 'git status failed'}")
    out = []
    for line in (p.stdout or "").splitlines():
        line = line.rstrip()
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.append(path.strip('"'))
    return out


def scope_hits(dirty: list, touches: list) -> list:
    """The dirty paths that fall inside the session's declared write scope. Only
    those refuse the run: this tree is often dirty with the user's own work, and
    a blanket refuse would make an unattended session useless, while a blanket
    proceed could commit work that is not the session's."""
    return [p for p in dirty if any(waves.overlaps(p, t) for t in touches)]


# --- the verbs ---------------------------------------------------------------

def _validate_new(name: str, d: pathlib.Path) -> None:
    if not SLUG.match(name):
        raise SessionError(f"{name!r}: a session name is lower-case letters, digits "
                           f"and dashes, starting with one of the first two")
    if (d / "schedule.json").is_file():
        raise SessionError(f"session {name} already exists ({d}/schedule.json); "
                           f"cancel it, or pick another name")


def _names(flag: str | None, default) -> list:
    """A job's condition list: `--start-when a,b` overrides the config default; `none`
    is the empty list. Every name is checked against the predicates that exist."""
    if flag is None:
        names = list(default or [])
    elif flag.strip() == "none":
        names = []
    else:
        names = [n.strip() for n in flag.split(",") if n.strip()]
    try:
        conditions_mod.validate(names)
    except conditions_mod.ConditionError as e:
        raise SessionError(str(e)) from None
    return names


def cmd_add(args, *, env=os.environ, run=subprocess.run, out=print) -> int:
    defaults = load_config()
    cwd = pathlib.Path(args.cwd or defaults.get("cwd") or roots.INSTALL).expanduser().resolve()
    if args.in_ and args.at:
        raise SessionError("--at and --in are alternatives; name one")
    if bool(args.prompt) == bool(args.specs):
        raise SessionError("name the ask: exactly one of --prompt FILE or --specs FILE")
    for flag, val in (("--item", args.item), ("--wave", args.wave), ("--all", args.all)):
        if val and not args.specs:
            raise SessionError(f"{flag} needs --specs")
    if args.wave and args.item:
        raise SessionError("--item and --wave are alternatives")
    now = now_local()
    every = getattr(args, "every", "") or ""
    ready = bool(getattr(args, "ready", False))
    if ready and (every or args.at or args.in_):
        raise SessionError("--ready is its own trigger: no --at, --in or --every with it")
    priority = getattr(args, "priority", None)
    if priority is None:
        priority = int(defaults.get("priority") or 50)
    # 2a: the account is part of the declaration. `--profile` names it; without the
    # flag it is the profile the caller's environment already runs under, written out
    # so the record never depends on who reads it.
    wanted = getattr(args, "profile", None) or profiles.active(env)
    try:
        profile = profiles.declared({"profile": wanted})
    except profiles.ProfileError as exc:
        raise SessionError(str(exc)) from None
    marked, marker_file = profiles.marker(cwd)
    if marked and marked != profile:
        raise SessionError(
            f"{cwd} is marked {marked} by {marker_file}: schedule it with --profile {marked} "
            f"(the run would bill {profile} otherwise)")
    period = None
    if every:
        # A period from the LAST START (1d), not a clock step: `--every 5h` is five hours
        # after the previous run began, whatever the hour (PLAN defects 1, 2).
        period = parse_delay(every)
        if period < dt.timedelta(seconds=DISPATCH_PRECISION):
            raise SessionError(f"--every {every!r}: the dispatcher ticks every "
                               f"{DISPATCH_PRECISION // 60} minutes; a shorter period "
                               f"cannot be kept")
    if ready:
        due = None
    elif args.in_:
        due = now + parse_delay(args.in_)
    elif args.at:
        due = parse_first(args.at, now) if every else parse_at(args.at, now)
    elif every:
        due = now                                 # the first run at the next tick
    else:
        raise SessionError("say when: --at 'YYYY-MM-DD HH:MM', --in 90m, "
                           "--every 5h [--at HH:MM], or --ready")
    trigger = "ready" if ready else ("every" if every else "at")
    chain = getattr(args, "chain", None) or "none"
    name = args.name or ("ready-" + now.strftime("%Y%m%d-%H%M") if ready else
                         ("every-" if every else "") + due.strftime("%Y%m%d-%H%M"))
    source = pathlib.Path(args.prompt or args.specs).expanduser()
    if not source.is_absolute():
        source = cwd / source
    source = source.resolve()
    if not source.is_file():
        raise SessionError(f"{source}: no such file")
    if args.specs:
        selector = (f"item {args.item}" if args.item else
                    (f"wave {args.wave or 1}" if not args.all else "every open item"))
        ask = {"kind": "specs", "path": str(source), "selector": selector,
               "item": args.item or "", "wave": args.wave or "", "all": bool(args.all)}
    else:
        ask = {"kind": "prompt", "path": str(source), "selector": "the file"}
    model = resolve_model(args, defaults, cwd, profile=profile)
    touches = [t.strip() for t in (args.touches or "").split(",") if t.strip()]
    d = session_dir(name, env)
    _validate_new(name, d)
    decl = {
        "name": name,
        "created": now.isoformat(timespec="seconds"),
        "kind": "chain" if chain != "none" else ("repeat" if every else "once"),
        "trigger": trigger,
        "chain": chain,
        "priority": priority,
        "start_when": _names(getattr(args, "start_when", None), defaults.get("start_when")),
        "stop_when": _names(getattr(args, "stop_when", None), defaults.get("stop_when")),
        "due": due.isoformat(timespec="seconds") if due else "",
        "on_calendar": "",
        "every": every if every else "",
        "anchor": "",
        "ask": ask,
        "touches": touches,
        "model": model,
        "profile": profile,
        "cwd": str(cwd),
        "branch": args.branch if args.branch is not None else (defaults.get("branch") or ""),
        "commit": args.commit or defaults.get("commit") or "per-item",
        "push": "never",
        "sandbox": "none",
        "nice": str(defaults.get("nice") or "15"),
        "timeout": defaults.get("timeout") or DEFAULT_TIMEOUT,
        # No unit of its own (1d): the dispatcher's tick starts every job.
        "unit": "",
        "record": str(d),
        "wrapper": str(d / "run.sh"),
    }
    # Resolve the selector ONCE at add time too, so a `--item` that names
    # nothing is refused now rather than at 06:00, and an unreadable prompt is
    # not discovered by the dispatcher. The run re-resolves it: the next open
    # wave at 06:00 is not the one that was next at 23:00.
    resolved = resolve_ask(decl)
    if args.dry_run:
        out(json.dumps({"would_write": decl, "ask": describe_ask(resolved)},
                       indent=2, ensure_ascii=False))
        return 0
    d.mkdir(parents=True, exist_ok=True)
    decl["wrapper"] = str(write_wrapper(d, name, decl, env=env))
    write_decl(d, decl)
    when = ("when its conditions allow" if ready else
            f"every {every} from the last start, first at {decl['due']}" if every else
            f"at {decl['due']}")
    out(f"session {name}: {decl['kind']} {when} (priority {priority}) -- "
        f"{describe_ask(resolved)}")
    out(f"  model    {model['id']} at effort {model['effort'] or 'off'} "
        f"({model['source']}, profile {profile})")
    out(f"  record   {d}/schedule.json")
    out(f"  started by the dispatcher (`familiar schedule sessions tick`, every "
        f"{DISPATCH_PRECISION // 60} min) when start_when "
        f"({', '.join(decl['start_when']) or 'nothing'}) allows")
    out(f"a later session reads it with: familiar schedule sessions show {name}")
    return 0


def _decls(env=os.environ) -> list:
    root = data_root(env)
    out = []
    for path in sorted(root.glob("*/schedule.json")):
        try:
            out.append((path.parent, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            out.append((path.parent, {"name": path.parent.name, "unreadable": str(path)}))
    return out


def _find(name: str, env=os.environ) -> tuple:
    for d, decl in _decls(env):
        if decl.get("name") == name:
            return d, decl
    raise SessionError(f"no session {name!r}; scheduled: "
                       f"{', '.join(x.get('name', p.name) for p, x in _decls(env)) or 'none'}")


def cmd_list(args, *, env=os.environ, out=print) -> int:
    now = now_local()
    defaults = load_config()
    window_text = getattr(args, "older_than", None) or LIST_WINDOW
    window = parse_delay(window_text)
    show_all = getattr(args, "all", False)
    rows, hidden = [], 0
    for d, decl in _decls(env):
        # A closed record past the window is what `prune` archives; until then
        # `list --all` shows it. Counted, so the list never looks complete
        # when it is not.
        if not show_all:
            ended = closed_at(decl)
            if ended is not None and now - ended > window:
                hidden += 1
                continue
        if decl.get("unreadable"):
            rows.append({"name": decl["name"], "state": "unreadable",
                         "error": decl["unreadable"]})
            continue
        events = read_events(d)
        st = _state(decl, events, now)
        job = job_of(decl, defaults)
        due = (st["until"].isoformat(timespec="seconds") if st.get("until") else
               decl.get("due") or decl.get("on_calendar") or job["trigger"])
        rows.append({
            "name": decl["name"], "kind": decl.get("kind", "once"),
            **job,
            "due": due, "state": st["state"],
            "last": (st["last"] or {}).get("ts", ""),
            "exit": (st["finished"] or {}).get("exit"),
            "model": (decl.get("model") or {}).get("id", ""),
            "effort": (decl.get("model") or {}).get("effort", ""),
            "commit": decl.get("commit", ""),
            "transcript": (st["finished"] or {}).get("transcript", ""),
            "record": str(d / "schedule.json"),
        })
    if args.json:
        out(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    if not rows:
        out("no scheduled sessions" + (f" ({_hidden_note(hidden, window_text)})" if hidden else ""))
        return 0
    head = ("NAME", "STATE", "DUE", "LAST RUN", "EXIT", "MODEL", "TRANSCRIPT")
    table = []
    for r in rows:
        table.append((r["name"], r["state"], r["due"][:19], (r["last"] or "-")[:19],
                      "-" if r["exit"] is None else str(r["exit"]),
                      f"{r['model']}{('/' + r['effort']) if r['effort'] else ''}",
                      r["transcript"] or "-"))
    width = [max(len(h), *(len(str(t[i])) for t in table)) for i, h in enumerate(head)]
    width[-1] = min(width[-1], 60)
    def fmt(row):
        return "  ".join(str(v)[:width[i]].ljust(width[i]) for i, v in enumerate(row))
    out(fmt(head))
    for t in table:
        out(fmt(t))
    if hidden:
        out(f"\n{_hidden_note(hidden, window_text)}.")
    out("\n`familiar schedule sessions show <name>` for the ask, the runs and the log.")
    return 0


def _hidden_note(hidden: int, window_text: str) -> str:
    """What the retention window took out of the list, in one clause."""
    return (f"{hidden} closed record(s) past the {window_text} window hidden; "
            f"`list --all` shows them")


def profile_line(decl: dict) -> str:
    """The account a record spends, and where it disagrees with the tree (2d).
    `implicit` means the record predates the field and reads as the config default."""
    declared = ""
    try:
        declared = profiles.declared(decl)
        line = f"profile: {declared}" + ("" if decl.get("profile") else " (implicit)")
    except profiles.ProfileError as exc:
        return f"profile: UNDECLARED -- {exc}"
    marked, marker_file = profiles.marker(decl.get("cwd") or "")
    if marked and marked != declared:
        line += f"  MISMATCH: {marker_file} names {marked}"
    return line


def cmd_show(args, *, env=os.environ, out=print) -> int:
    d, decl = _find(args.name, env)
    events = read_events(d)
    st = _state(decl, events, now_local())
    out(json.dumps(decl, indent=2, ensure_ascii=False))
    job = job_of(decl)
    out(f"\njob: trigger {job['trigger']}, chain {job['chain']}, priority {job['priority']}, "
        f"start_when {','.join(job['start_when']) or '-'}, "
        f"stop_when {','.join(job['stop_when']) or '-'}")
    out(profile_line(decl))
    out(f"state: {st['state']}" + (f" until {st['until'].isoformat(timespec='seconds')} "
                                    f"({st['why']})" if st.get("until") else ""))
    out(f"\nevents: {len(events)} in {d / 'runs.jsonl'}")
    for e in events:
        line = f"  {e.get('ts', '?')}  {e.get('event', '?')}"
        for key in ("exit", "seconds", "reason", "late_seconds", "until", "why"):
            if e.get(key) is not None:
                line += f"  {key}={e[key]}"
        if e.get("transcript"):
            line += f"  transcript={e['transcript']}"
        out(line)
    if not events:
        out(f"  state: {st['state']} (nothing has run)")
    if args.log:
        path = (st["finished"] or {}).get("log") or (st["last"] or {}).get("log") or ""
        if path and pathlib.Path(path).is_file():
            lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
            out(f"\n--- {path} (last {args.log})")
            for line in lines[-args.log:]:
                out(line)
        else:
            out("\nno run log yet")
    return 0


def cmd_cancel(args, *, env=os.environ, run=subprocess.run, out=print,
               lineage=ancestors) -> int:
    """Disable a job's unit and mark it closed. From inside the job's OWN run -- the
    run's pid is an ancestor of this process -- it marks the job `ended` instead of
    refusing (defect 3): that is how a chain ends itself. The run is not stopped;
    it finishes and records its `finished` as usual."""
    targets = []
    if args.all:
        targets = [(d, decl) for d, decl in _decls(env)
                   if not closed(decl) and not decl.get("unreadable")]
    else:
        if not args.name:
            raise SessionError("name a session, or pass --all")
        targets = [_find(args.name, env)]
    if not targets:
        out("nothing to cancel")
        return 0
    units = units_dir(env)
    for d, decl in targets:
        if closed(decl):
            out(f"{decl['name']}: already {closed(decl)}")
            continue
        lock = RunLock(d)
        own = False
        if lock.held():
            own = lock.holder() in lineage()
            if not own and not args.force:
                out(f"{decl['name']}: a run is in flight; refusing to stop it "
                    f"(pass --force to stop it anyway)", file=sys.stderr)
                return 2
        unit = f"{UNIT_PREFIX}{decl['name']}"
        if decl.get("unit") and not args.no_systemctl:
            run(["systemctl", "--user", "disable", "--now", f"{unit}.timer"],
                capture_output=True, text=True)
        for ext in ("timer", "service"):
            (units / f"{unit}.{ext}").unlink(missing_ok=True)
        if decl.get("unit") and not args.no_systemctl:
            run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
            run(["systemctl", "--user", "reset-failed", f"{unit}.timer", f"{unit}.service"],
                capture_output=True, text=True)
        ts = now_local().isoformat(timespec="seconds")
        if own:
            decl["ended"] = ts
            write_decl(d, decl)
            write_event(d, {"event": "ended", "ts": ts, "session": decl["name"],
                            "why": "cancel from inside the job's own run",
                            "record": str(d)})
            out(f"ended {decl['name']}: called from its own run, which finishes as usual; "
                f"record kept at {d}/schedule.json")
            continue
        decl["cancelled"] = ts
        write_decl(d, decl)
        write_event(d, {"event": "cancelled", "ts": ts,
                        "session": decl["name"], "record": str(d)})
        out(f"cancelled {decl['name']}: unit removed, record kept at {d}/schedule.json")
    return 0


def hold(d, decl: dict, until: dt.datetime, why: str, *, env=os.environ,
         run=subprocess.run, out=print) -> dt.datetime | None:
    """Requeue the SAME job: append a `held` event, so it does not run before `until`.

    It replaces 9a's `<root>-r<N>` re-declaration, which had a lifetime cap (defect 4)
    and its own lock, so it could run beside the next anchor (defect 5). The cap is
    now `retry.max` CONSECUTIVE holds (`refusal_streak`); past it the record says so
    and the job is left alone.

    The dispatcher (1d) reads the hold. A 9a record still has its own unit: an `at`
    one is re-rendered to fire at `until`; an `every` one runs at its first anchor
    after `until` (an earlier anchor is refused with an event).

    Returns the hold time, or None when the cap refused it."""
    policy = load_policy().get("retry") or {}
    cap = int(policy.get("max") or 6)
    now = now_local()
    streak = refusal_streak(read_events(d))
    if streak >= cap:
        write_event(d, {"event": "retry_refused", "ts": now.isoformat(timespec="seconds"),
                        "session": decl["name"], "why": f"{streak} holds in a row; {why}",
                        "cap": cap})
        out(f"{decl['name']}: {why}; retry cap ({cap}) reached, not held again")
        return None
    trigger = job_of(decl)["trigger"]
    row = {"event": "held", "ts": now.isoformat(timespec="seconds"),
           "session": decl["name"], "until": until.isoformat(timespec="seconds"),
           "why": why, "attempt": streak + 1}
    if trigger == "at" and decl.get("unit"):
        decl["due"] = row["until"]
        decl["on_calendar"] = calendar_of(until)
        render_units(decl["name"], decl, units_dir(env), run=run)
        write_decl(d, decl)
        run(["systemctl", "--user", "daemon-reload"], capture_output=True, text=True)
        p = run(["systemctl", "--user", "restart", f"{decl['unit']}.timer"],
                capture_output=True, text=True)
        row["fires"] = "its own unit, moved to the hold time"
        row["enabled"] = not getattr(p, "returncode", 0)
    elif trigger == "every" and decl.get("unit"):
        row["fires"] = "its first anchor after the hold time"
    else:
        row["fires"] = "the dispatcher's first tick after the hold time"
    write_event(d, row)
    out(f"{decl['name']}: {why}; held until {row['until']} (attempt {streak + 1} of {cap})")
    return until


def hold_after_refusal(lines: list, now: dt.datetime) -> tuple:
    """(until, how it was found): the refusal's reset + `retry.after_reset`, else now +
    `retry.fallback` (defect 6 was a blind +30 m though the message named the time)."""
    policy = load_policy().get("retry") or {}
    reset = reset_time(lines, now)
    if reset is not None:
        return reset + parse_delay(policy.get("after_reset") or "1m"), "the refusal's reset time"
    return now + parse_delay(policy.get("fallback") or "30m"), "no reset time in the refusal"


def cmd_run(args, *, env=os.environ, driver=rpc.drive, out=print,
            dirty=None, run=subprocess.run) -> int:
    d, decl = _find(args.name, env)
    try:
        return _cmd_run(args, d, decl, env=env, driver=driver, out=out, dirty=dirty, run=run)
    except SessionError:
        raise
    except Exception as exc:                      # noqa: BLE001 -- the record must show it
        # A defect in THIS module used to leave the record empty while systemd showed a
        # failure (2026-10-20, `late_seconds` on a repeat session, two anchors lost).
        write_event(d, {"event": "crashed", "ts": now_local().isoformat(timespec="seconds"),
                        "session": decl.get("name", args.name),
                        "error": f"{type(exc).__name__}: {exc}"})
        _tell(d, decl.get("name", args.name), "crashed", f"{type(exc).__name__}: {exc}", env)
        out(f"{args.name}: the run crashed before the session started: "
            f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _cmd_run(args, d, decl, *, env=os.environ, driver=rpc.drive, out=print,
             dirty=None, run=subprocess.run) -> int:
    if closed(decl):
        raise SessionError(f"{decl['name']} was {closed(decl)}")
    now = now_local()
    until = hold_until(read_events(d))
    if (until is not None and not getattr(args, "ignore_hold", False)
            and now < until - dt.timedelta(seconds=NOW_EPSILON)):
        row = {"event": "refused", "ts": now.isoformat(timespec="seconds"),
               "session": decl["name"], "reason": f"held until {until.isoformat()}"}
        write_event(d, row)
        out(f"{decl['name']}: refused -- {row['reason']} (`run --ignore-hold` to run now)",
            file=sys.stderr)
        return 2
    ask = resolve_ask(decl)
    try:
        profile = profiles.declared(decl)
    except profiles.ProfileError as exc:
        raise SessionError(str(exc)) from None
    # 2d: the work tree's own `.pi-profile` is a CHECK on the declaration, never a
    # source of it. A tree that changed its mind since the add refuses instead of
    # billing an account nobody declared.
    marked, marker_file = profiles.marker(decl.get("cwd") or "")
    if marked and marked != profile:
        row = {"event": "refused", "ts": now.isoformat(timespec="seconds"),
               "session": decl["name"],
               "reason": f"{marker_file} names {marked}, the record declares {profile}"}
        write_event(d, row)
        out(f"{decl['name']}: refused -- {row['reason']}", file=sys.stderr)
        return 2
    try:
        res = profiles.resolve(decl["model"]["id"], profile)
    except (OSError, ValueError) as e:                        # ProfileError
        raise SessionError(f"{decl['model']['id']}: {e}") from None
    if not res.available:
        row = {"event": "refused", "ts": now.isoformat(timespec="seconds"),
               "session": decl["name"], "reason": f"profile {profile}: {res.reason}",
               "model": decl["model"]["id"]}
        write_event(d, row)
        out(f"{decl['name']}: refused -- {row['reason']}", file=sys.stderr)
        return 2
    dirty_paths = dirty if dirty is not None else git_dirty(decl["cwd"])
    hits = scope_hits(dirty_paths, ask["touches"])
    if hits:
        row = {"event": "refused", "ts": now.isoformat(timespec="seconds"),
               "session": decl["name"], "reason": "dirty tree inside the write scope",
               "dirty": hits}
        write_event(d, row)
        out(f"{decl['name']}: refused -- the tree is dirty inside the session's own "
            f"write scope: {', '.join(hits)}", file=sys.stderr)
        return 3
    is_chain = job_of(decl)["chain"] != "none"
    events_before = read_events(d)
    carry, handoff_used = (chain_mod.carry_over(d, events_before) if is_chain else ("", None))
    notes = []
    if is_chain:
        notes.append(f"**Handoff:** if your context grows long, or a checkpoint says stop, "
                     f"write `{d / chain_mod.HANDOFF}` for the next run, then end.")
    reset = _window_reset(decl, env)
    if reset:
        notes.append(f"**The Claude window** resets at {reset}; the run may be refused "
                     f"before then, which the engine holds and resumes.")
    prompt = build_prompt(decl, ask, load_config(), now, notes=tuple(notes), carry=carry)
    transcript_dir = d / "transcript"
    sid = now.strftime("%Y%m%dT%H%M%S")
    log = d / f"run-{sid}.log"
    # RPC, not `-p`: under `-p` every permission ask fails for want of a UI; under RPC
    # each dialog reaches the relay and waits for the owner (dev/remote R2a). The prompt
    # travels on stdin, so the argv stays short enough to record; `--approve` trusts the
    # session's own checkout, and the transcript is the record's own session.
    # `ask_user` by flag: a scheduled run can ask the owner, and no interactive session
    # gets the tool until its loader shim is installed (dev/remote R2b).
    argv = pi_call.argv_rpc(approve=True, session=pi_call.Session(transcript_dir, sid),
                            model=f"{res.provider}/{res.model}",
                            thinking=decl["model"]["effort"] or None,
                            extensions=ask_user_extensions(env))
    if args.dry_run:
        out(json.dumps({"session": decl["name"], "ask": {k: ask[k] for k in
                        ("kind", "path", "selector", "items", "wave", "sha256", "bytes")},
                        "model": decl["model"], "pi_model": f"{res.provider}/{res.model}",
                        # The account the child will spend (2b): the overlay, which
                        # holds paths and unsets only -- no secret is ever printed.
                        "profile": profile, "account_env": profiles.account_env(profile),
                        "argv": argv, "prompt_chars": len(prompt),
                        "cwd": decl["cwd"], "log": str(log),
                        "transcript_dir": str(transcript_dir)},
                       indent=2, ensure_ascii=False))
        return 0
    # Only a one-off has a time to be late for: a repeating job's `due` is its first.
    due = (dt.datetime.fromisoformat(decl["due"])
           if decl.get("due") and job_of(decl)["trigger"] == "at" else None)
    started_row = {
        "event": "started", "ts": now.isoformat(timespec="seconds"),
        "session": decl["name"], "unit": decl.get("unit", ""),
        "late_seconds": round((now - due).total_seconds(), 1) if due else None,
        "ask": {k: ask[k] for k in ("kind", "path", "selector", "items", "wave",
                                    "sha256", "bytes")},
        "touches": ask["touches"],
        "model": decl["model"],
        "pi_model": f"{res.provider}/{res.model}",
        "profile": profile,
        "cwd": decl["cwd"], "branch": decl.get("branch", ""),
        "commit": decl.get("commit", ""), "push": "never", "sandbox": "none",
        "dirty": dirty_paths,
        "argv": argv,
        "log": str(log),
        "transcript_dir": str(transcript_dir),
        "run": sid,
        "carry_over": bool(carry),
    }
    with contextlib.ExitStack() as locks:
        _take_locks(locks, d, decl, now, env=env, run=run, out=out)
        started_row["before"] = chain_mod.snapshot(decl, d)
        write_event(d, started_row)
        if handoff_used is not None:
            # Read once: the next run gets this run's handoff, not the last one's again.
            prev = [e for e in events_before if e.get("event") == "started"]
            chain_mod.archive_handoff(handoff_used, (prev[-1].get("run") if prev else "")
                                      or now.strftime("%Y%m%dT%H%M%S"))
        t0 = time.monotonic()
        transcript_dir.mkdir(parents=True, exist_ok=True)
        asked = describe_ask(ask)
        with log.open("w", encoding="utf-8") as fh, _run_env(decl["name"], sid):
            # The driver owns the conversation and the clock: it counts only time spent
            # working, not waiting for the owner (rpc.py). A pi that does not start
            # raises `PiError`, which `cmd_run` records as `crashed`. A SIGINT is the
            # dispatcher's backstop (1c): the run is recorded as interrupted and held.
            try:
                result = driver(argv, prompt, cwd=decl["cwd"], log=fh, session=decl["name"],
                                run_id=sid, asked=f"asked: {asked}",
                                env=profiles.with_account(env, profile),
                                write_event=lambda row: write_event(
                                    d, {"ts": now_local().isoformat(timespec="seconds"),
                                        "session": decl["name"], **row}),
                                timeout_s=parse_timeout(decl.get("timeout")))
            except KeyboardInterrupt:
                fh.write("[familiar] interrupted (SIGINT) -- the backstop, or a person\n")
                result = {"exit": 130, "interrupted": True}
        code = result["exit"]
        seconds = round(time.monotonic() - t0, 1)
        transcript = _newest(transcript_dir)
        tail = _tail(log, 20)
        after = None
        try:
            after = git_dirty(decl["cwd"])
        except SessionError:
            pass
        changed = sorted(set(after or []) - set(dirty_paths))
        refused = code != 0 and any(DENIED.search(line) for line in _tail(log, 60))
        snap = chain_mod.snapshot(decl, d)
        progress = chain_mod.measure(started_row["before"], snap, decl)
        write_event(d, {
            "event": "finished", "ts": now_local().isoformat(timespec="seconds"),
            "session": decl["name"], "exit": code, "seconds": seconds,
            "waited_s": result.get("waited_s", 0), "asks": result.get("asks", 0),
            "late_seconds": started_row["late_seconds"],
            "log": str(log), "transcript": str(transcript) if transcript else "",
            "dirty": after,
            "changed": changed,
            "window_refused": refused,
            "interrupted": bool(result.get("interrupted")),
            "checkpoint_stop": _checkpoint_stop(read_events(d)),
            "progress": progress,
            "report": chain_mod.final_report(transcript),
            "tail": tail,
        })
        if is_chain and not closed(read_decl(d)):
            _chain_step(d, refused, progress, snap, env)
        elif (not is_chain and job_of(decl)["trigger"] != "every" and not refused
              and not result.get("interrupted")):
            # A one-off is over: tell the user how (a repeating job's runs are not news).
            _tell(d, decl["name"], "done",
                  f"exit {code}; {len(progress['commits'])} commit(s), "
                  f"ticked {', '.join(progress['ticks']) or 'nothing'}", env)
        if result.get("interrupted") and not closed(read_decl(d)):
            until, why = _after_backstop(read_events(d), now_local())
            hold(d, read_decl(d), until, why, env=env, run=run, out=out)
        # A refused window and an untouched tree: hold the same job until the reset.
        # The untouched tree is what makes a repeat safe at all -- a run that
        # half-committed is never repeated blindly. A job that ended itself is not held.
        if refused and not changed and not closed(read_decl(d)):
            until, how = hold_after_refusal(_tail(log, 60), now_local())
            hold(d, read_decl(d), until, f"the window refused the run ({how})",
                 env=env, run=run, out=out)
    out(f"{decl['name']}: exit {code} in {seconds:g}s -- "
        f"transcript {transcript or '(none)'}")
    out(f"  log {log}")
    return code


def ask_user_extensions(env=os.environ) -> list:
    """`-e` the `ask_user` tool only when pi does not discover it already. Since the
    dotfiles ship its loader shim, passing it again makes pi refuse to start: `Tool
    "ask_user" conflicts with ...` (measured 2026-10-21, the first dispatched run)."""
    agent = pathlib.Path(env.get("PI_CODING_AGENT_DIR")
                         or pathlib.Path.home() / ".pi" / "agent")  # not-a-root: pi's own dir
    return [] if (agent / ASK_USER_SHIM).is_file() else [ASK_USER]


def _window_reset(decl: dict, env) -> str:
    """The five-hour window's reset from the probe, for the job's OWN account (2c),
    named with the account so the prompt says what the run will spend."""
    policy = load_policy()
    providers = list(((policy.get("conditions") or {}).get("budget") or {}).get("providers")
                     or [])
    provider = str((decl.get("model") or {}).get("pi_model", "")).split("/", 1)[0]
    if providers and provider not in providers:
        return ""
    try:
        profile = profiles.declared(decl)
        reading = conditions_mod.read_budget(
            conditions_mod.Context(policy, env=dict(env)), profile)
    except (OSError, ValueError, profiles.ProfileError,
            subprocess.SubprocessError):
        return ""
    resets = (reading.get("five_hour") or (0, None))[1]
    if not resets:
        return ""
    return f"{resets.strftime('%H:%M %Z').strip()} [{reading.account()}]"


def _tell(d, job: str, state: str, text: str, env) -> None:
    from schedule import notify                              # noqa: PLC0415 -- it imports us
    notify.send(d, job, state, text, env=dict(env))


def _chain_step(d, refused: bool, progress: dict, snap: dict, env=os.environ) -> None:
    """After a chain's run: a `chain` event with the outcome, then `ended` (done) or
    `paused` (blocked, stalled, review). A refused window is a hold, not a step."""
    decl = read_decl(d)
    ts = now_local().isoformat(timespec="seconds")
    if refused:
        write_event(d, {"event": "chain", "ts": ts, "session": decl["name"],
                        "state": "held", "why": "the window refused the run",
                        "refused": True, "progress": progress})
        return
    history = [e for e in read_events(d) if e.get("event") == "chain"]
    stall_after = int((load_policy().get("chain") or {}).get("stall_after") or 2)
    state, why = chain_mod.outcome(decl, progress, snap, history, stall_after=stall_after)
    write_event(d, {"event": "chain", "ts": ts, "session": decl["name"], "state": state,
                    "why": why, "progress": progress})
    if state == "done":
        decl["ended"] = ts
        write_decl(d, decl)
        write_event(d, {"event": "ended", "ts": ts, "session": decl["name"],
                        "why": f"chain done: {why}"})
        _tell(d, decl["name"], "done", f"chain done: {why}", env)
    elif state in chain_mod.PAUSES:
        write_event(d, {"event": "paused", "ts": ts, "session": decl["name"],
                        "state": state, "why": why, "ask_sha": _ask_sha(decl)})
        _tell(d, decl["name"], state, f"{why}; when it may go on: /approve "
                                      f"{decl['name']} (or `familiar schedule sessions "
                                      f"resume {decl['name']}`)", env)


def _ask_sha(decl: dict) -> str:
    try:
        return _sha(pathlib.Path(decl["ask"]["path"]).read_text(encoding="utf-8"))
    except (OSError, KeyError):
        return ""


def _quiet_since(d: pathlib.Path, events: list, now: dt.datetime) -> dt.timedelta | None:
    """How long nothing has happened in a record: the newest of its event stamps and
    the declaration file's own mtime (written once, at `add`). None when neither
    can be read -- a record of unknown age is kept."""
    stamps = [s for s in (_when(e.get("ts")) for e in events) if s is not None]
    try:
        stamps.append(dt.datetime.fromtimestamp(
            (d / "schedule.json").stat().st_mtime).astimezone())
    except OSError:
        pass
    return now - max(stamps) if stamps else None


def cmd_hold(args, *, env=os.environ, out=print) -> int:
    """A hold by hand (the bot's `/hold`): a `held` event, as a refusal writes, but
    outside the retry cap -- a person's decision is not a refusal."""
    d, decl = _find(args.name, env)
    if closed(decl):
        raise SessionError(f"{decl['name']} was {closed(decl)}")
    now = now_local()
    until = now + parse_delay(args.delay)
    write_event(d, {"event": "held", "ts": now.isoformat(timespec="seconds"),
                    "session": decl["name"], "until": until.isoformat(timespec="seconds"),
                    "why": "held by hand", "fires": "the dispatcher's first tick after it"})
    out(f"{decl['name']}: held until {until.strftime('%a %H:%M')}")
    return 0


def cmd_resume(args, *, env=os.environ, out=print) -> int:
    d, decl = _find(args.name, env)
    why = chain_mod.paused(read_events(d), _ask_sha(decl))
    if not why:
        out(f"{decl['name']}: not paused")
        return 0
    write_event(d, {"event": "resumed", "ts": now_local().isoformat(timespec="seconds"),
                    "session": decl["name"], "was": why})
    out(f"{decl['name']}: resumed (was {why}); the next tick may start it")
    return 0


def cmd_prune(args, *, env=os.environ, out=print, now=None) -> int:
    """Archive closed or never-started records; NOTHING is deleted. A record is
    prunable when it is closed (ended or cancelled), or when it never started a
    run, and nothing has happened to it for --older-than. One whose unit files are
    still on disk is kept: `cancel` owns the unit, prune only archives."""
    now = now or now_local()
    window = parse_delay(args.older_than)
    archive = data_root(env) / "archive"
    units = units_dir(env)
    verb = "would archive" if args.dry_run else "archived"
    done = "would be archived" if args.dry_run else "archived"
    moved = kept = 0
    for d, decl in _decls(env):
        name = decl.get("name") or d.name
        events = read_events(d)
        quiet = _quiet_since(d, events, now)
        if quiet is None or quiet < window or RunLock(d).held():
            kept += 1                      # too recent, unknown age, or a run in flight
            continue
        if not closed(decl) and any(e.get("event") == "started" for e in events):
            kept += 1                      # open and has run: an active job
            continue
        live = [f"{UNIT_PREFIX}{name}.{ext}" for ext in ("timer", "service")
                if (units / f"{UNIT_PREFIX}{name}.{ext}").exists()]
        if live:
            out(f"kept {name}: {', '.join(live)} still on disk; "
                f"`cancel {name}` owns the unit")
            kept += 1
            continue
        target = archive / name
        if target.exists():
            target = archive / f"{name}-{now.strftime('%Y%m%dT%H%M%S')}"
        if args.dry_run:
            out(f"{verb} {name} (quiet {_span(quiet)}) -> {target}")
        else:
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(d), str(target))
            # The row lands in the archive with the record: the live store is where
            # this command is allowed to leave no trace of a record it already moved.
            write_event(target, {"event": "pruned",
                                 "ts": now.isoformat(timespec="seconds"),
                                 "session": name,
                                 "why": f"archived by prune (quiet {_span(quiet)} past "
                                        f"{args.older_than})",
                                 "record": str(target)})
            out(f"archived {name} (quiet {_span(quiet)}) -> {target}")
        moved += 1
    out(f"prune: {moved} {done}, {kept} kept (window {args.older_than})")
    return 0


@contextlib.contextmanager
def _run_env(name: str, sid: str):
    """The job's name and run id in the environment the child inherits, and the
    default SIGINT handler (a process started in the background may have SIGINT
    ignored, and the backstop relies on it)."""
    saved = {k: os.environ.get(k) for k in (JOB_ENV, RUN_ENV)}
    os.environ[JOB_ENV], os.environ[RUN_ENV] = name, sid
    try:
        old = signal.signal(signal.SIGINT, signal.default_int_handler)
    except ValueError:                            # not the main thread
        old = None
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if old is not None:
            signal.signal(signal.SIGINT, old)


def _since_start(events: list) -> list:
    starts = [i for i, e in enumerate(events) if e.get("event") == "started"]
    return events[starts[-1]:] if starts else []


def _checkpoint_stop(events: list) -> str:
    """The reason the last run stopped at a checkpoint, or ''."""
    for e in reversed(_since_start(events)):
        if e.get("event") == "checkpoint" and e.get("stop"):
            return "; ".join(f"{k}: {v}" for k, v in (e.get("holding") or {}).items())
    return ""


def _after_backstop(events: list, now: dt.datetime) -> tuple:
    """(until, why) for a run the backstop interrupted: the condition's own end when
    it is known (a conflict's due time is not its end, so the fallback), else
    `retry.fallback`."""
    policy = load_policy().get("retry") or {}
    fallback = now + parse_delay(policy.get("fallback") or "30m")
    for e in reversed(_since_start(events)):
        if e.get("event") == "backstop":
            return fallback, f"interrupted by the backstop ({e.get('condition')}: {e.get('reason')})"
    return fallback, "interrupted (SIGINT)"


def _take_locks(stack, d, decl: dict, now: dt.datetime, *, env, run, out) -> None:
    """The job's lock, then its working directory's. Every refusal writes a `refused`
    event (defect 7); a working-directory refusal also holds the job, because the
    run that holds the directory will end and this one should then run."""
    def refused(lock: str, exc: SessionError) -> None:
        write_event(d, {"event": "refused", "ts": now.isoformat(timespec="seconds"),
                        "session": decl["name"], "reason": str(exc), "lock": lock})

    try:
        stack.enter_context(RunLock(d, label=decl["name"]))
    except SessionError as exc:
        refused("job", exc)
        raise
    try:
        stack.enter_context(cwd_lock(decl["cwd"], env, label=decl["name"]))
    except SessionError as exc:
        refused("cwd", exc)
        until, _ = hold_after_refusal([], now)
        hold(d, decl, until, "another run holds the working directory",
             env=env, run=run, out=out)
        raise


def _newest(d: pathlib.Path) -> pathlib.Path | None:
    if not d.is_dir():
        return None
    files = sorted((p for p in d.rglob("*.jsonl") if p.is_file()),
                   key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _tail(path: pathlib.Path, n: int) -> list:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-n:]


# --- conditions ----------------------------------------------------------------

def cmd_conditions(args, *, env=os.environ, out=print, ctx=None) -> int:
    """Every condition's current value with its reason. With a job, the job's own
    working directory, model and write scope, and which of its lists names each one;
    without, the configured defaults stand in for a job."""
    policy = load_policy()
    defaults = policy.get("defaults") or {}
    if args.name:
        _d, decl = _find(args.name, env)
        job = {**decl, **job_of(decl, defaults)}
    else:
        model = {"pi_model": ""}
        try:
            res = profiles.resolve(defaults.get("model") or "", profiles.active(env))
            model = {"pi_model": f"{res.provider}/{res.model}"}
        except (OSError, ValueError):
            pass
        job = {"name": "", "cwd": defaults.get("cwd") or str(roots.INSTALL), "model": model,
               "touches": [], **job_of({}, defaults)}
    ctx = ctx or conditions_mod.Context(policy, env=dict(env))
    rows = []
    for name in conditions_mod.NAMES:
        v = conditions_mod.evaluate(name, job, ctx)
        role = [r for r, key in (("start", "start_when"), ("stop", "stop_when"))
                if name in job[key]]
        rows.append({"condition": name, "role": role, **v.as_dict()})
    if args.json:
        out(json.dumps({"job": job.get("name") or "(defaults)", "conditions": rows},
                       indent=2, ensure_ascii=False))
        return 0
    out(f"conditions for {args.name or 'a job with the configured defaults'} "
        f"(cwd {job['cwd']}):")
    for r in rows:
        out(f"  {r['condition']:<12} {'HOLDS' if r['holds'] else 'clear':<6} "
            f"{('/'.join(r['role']) or '-'):<11} {r['reason']}"
            + (f"  until {r['until']}" if r["until"] else ""))
    return 0


# --- the dispatcher (1d) ----------------------------------------------------------

def cmd_tick(args, *, env=os.environ, out=print, **kw) -> int:
    from schedule import dispatch, notify                    # noqa: PLC0415 -- they import us
    row = dispatch.tick(env, dry_run=args.dry_run, **kw)
    if not args.dry_run and not row.get("skipped"):
        row["lost"] = notify.sweep_lost(env)
    if args.json:
        out(json.dumps(row, indent=2, ensure_ascii=False))
        return 0
    if row.get("skipped"):
        out(f"tick: {row['skipped']}")
        return 0
    for b in row["backstops"]:
        out(f"backstop  {b['job']}: {b['condition']} -- {b['reason']}")
    for name, what in sorted(row["jobs"].items()):
        out(f"{name:<28} {what}")
    out(f"tick {row['ts']}: " + (f"started {row['started']}" if row["started"] else
                                 "started nothing") + (" (dry run)" if args.dry_run else ""))
    return 0


# --- checkpoint and backstop (1c) ------------------------------------------------

def _inside(name: str, env, lineage) -> tuple:
    """(d, decl) of the job whose run this process belongs to; refused otherwise. The
    job lock's pid among this process's ancestors -- the same proof `cancel` uses."""
    d, decl = _find(name, env)
    lock = RunLock(d)
    if not lock.held() or lock.holder() not in lineage():
        raise SessionError(f"not inside a run of {name}: checkpoint is called by the "
                           f"agent of a scheduled run, before each item")
    return d, decl


def cmd_checkpoint(args, *, env=os.environ, out=print, ctx=None, lineage=ancestors) -> int:
    """Continue (0) or stop (10) at an item boundary: the job's `stop_when` conditions,
    each evaluated now. A `checkpoint` event is appended either way, so the record
    shows every boundary the run crossed and why it stopped."""
    name = getattr(args, "job", None) or env.get(JOB_ENV)
    if not name:
        raise SessionError(f"checkpoint runs inside a scheduled run; {JOB_ENV} is not set")
    d, decl = _inside(name, env, lineage)
    job = {**decl, **job_of(decl)}
    ctx = ctx or conditions_mod.Context(load_policy(), env=dict(env))
    holding = {n: v for n, v in conditions_mod.evaluate_all(job["stop_when"], job, ctx).items()
               if v.holds}
    stop = bool(holding)
    write_event(d, {"event": "checkpoint", "ts": now_local().isoformat(timespec="seconds"),
                    "session": decl["name"], "run": env.get(RUN_ENV, ""),
                    "item": getattr(args, "item", "") or "", "stop": stop,
                    "holding": {n: v.reason for n, v in holding.items()},
                    "checked": job["stop_when"]})
    if stop:
        for n, v in holding.items():
            out(f"stop: {n} -- {v.reason}")
        out("Write the handoff, commit what is finished, and end the session.")
        return STOP
    out(f"continue: none of {', '.join(job['stop_when']) or '(no stop conditions)'} holds")
    return 0


def backstop(d, decl: dict, ctx, *, now: dt.datetime | None = None) -> dict | None:
    """Should the dispatcher interrupt this job's run now? A stop condition with a
    `hard_stop` (config, per condition) that has held that long:

    * `none` -- never (the user's own activity: the run stops at its next item);
    * `due` -- at the condition's own `until` (a conflict: the pass's start time);
    * a delay -- that long after the run first saw the condition hold, read from its
      `checkpoint` events or a `stop_held` event this function writes the first time.

    Returns {pid, condition, reason, until} or None. Only a run in flight qualifies."""
    lock = RunLock(d)
    if not lock.held():
        return None
    now = now or now_local()
    job = {**decl, **job_of(decl)}
    since_start = _since_start(read_events(d))
    for name in job["stop_when"]:
        hard = str(ctx.conf(name).get("hard_stop") or "none")
        if hard == "none":
            continue
        v = conditions_mod.evaluate(name, job, ctx)
        if not v.holds:
            continue
        if hard == "due":
            at = v.until or now
        else:
            seen = [dt.datetime.fromisoformat(e["ts"]) for e in since_start
                    if e.get("event") in ("checkpoint", "stop_held")
                    and name in (e.get("holding") or {}) and e.get("ts")]
            if not seen:
                write_event(d, {"event": "stop_held", "ts": now.isoformat(timespec="seconds"),
                                "session": decl["name"], "holding": {name: v.reason}})
                seen = [now]
            at = min(seen) + parse_delay(hard)
        if now >= at:
            return {"pid": lock.holder(), "condition": name, "reason": v.reason,
                    "until": v.until.isoformat(timespec="seconds") if v.until else None}
    return None


def _sigint(pid: int) -> None:
    """SIGINT to the run's process GROUP when the run leads one (systemd and the
    dispatcher both start it so), which reaches pi too; else to the run alone --
    never to a group the run merely belongs to, which may be a person's shell."""
    try:
        if os.getpgid(pid) == pid:
            os.killpg(pid, signal.SIGINT)
            return
    except ProcessLookupError:
        return
    os.kill(pid, signal.SIGINT)


def interrupt(d, decl: dict, verdict: dict, *, kill=_sigint) -> None:
    """Apply a backstop: the event first, then the signal (the record must say why
    the run ended even when the signal is the last thing that happens)."""
    write_event(d, {"event": "backstop", "ts": now_local().isoformat(timespec="seconds"),
                    "session": decl["name"], **verdict})
    if verdict.get("pid"):
        kill(int(verdict["pid"]))


# --- --check -----------------------------------------------------------------

def self_check(decl: dict, d: pathlib.Path, env, *, run=subprocess.run) -> list:
    """Findings for ONE declaration, in the shape `timers-gen.sh --check` uses:
    (structural, kind, message). A structural finding means the record and the
    live units disagree; a warning is history (a run that did not finish)."""
    out = []
    source = pathlib.Path(decl.get("ask", {}).get("path", ""))
    # A cancelled session will never read its source again, so a source that went away
    # afterwards (a /tmp smoke prompt, 2026-10-20) is history, not drift.
    if not closed(decl) and not source.is_file():
        out.append(("DRIFT", "source", f"{source}: the ask's source is gone"))
    wrapper = pathlib.Path(decl.get("wrapper", ""))
    if not closed(decl) and not wrapper.is_file():
        out.append(("DRIFT", "wrapper", f"{wrapper}: the wrapper is gone"))
    unit = decl.get("unit") or f"{UNIT_PREFIX}{decl.get('name', d.name)}"
    units = units_dir(env)
    # A `ready` job records `unit: ""`: the dispatcher starts it, so no unit is rendered.
    has_unit = decl.get("unit", unit) != ""
    if closed(decl) or not has_unit:
        # Closed, or a `ready` job: any unit file is stale.
        for ext in ("timer", "service"):
            if (units / f"{unit}.{ext}").exists():
                out.append(("DRIFT", "stale", f"{unit}.{ext} survived cancel"
                            if closed(decl) else
                            f"{unit}.{ext} for a job the dispatcher starts"))
        if closed(decl):
            return out
    if decl.get("model", {}).get("id"):
        cat_ids = {e.get("id") for e in models.load().get("models") or []}
        if decl["model"]["id"] not in cat_ids:
            out.append(("DRIFT", "model", f"{decl['model']['id']}: not a callable "
                                         f"catalogue id any more"))
    if not closed(decl):
        # 2d: a job whose tree names another profile would bill the wrong account.
        # A record without the field reads as the config default, so this is also
        # how the defect of 2026-10-22 gets reported.
        try:
            declared = profiles.declared(decl)
        except profiles.ProfileError as exc:
            out.append(("DRIFT", "profile", str(exc)))
        else:
            marked, marker_file = profiles.marker(decl.get("cwd") or "")
            if marked and marked != declared:
                out.append(("DRIFT", "profile",
                            f"declares {declared} but {marker_file} names {marked}"))
    if has_unit:
        with tempfile.TemporaryDirectory(prefix="sessions-check-") as tmp:
            try:
                render_units(decl["name"], decl, pathlib.Path(tmp), run=run)
            except SessionError as e:
                out.append(("DRIFT", "unit", str(e)))
            else:
                for ext in ("timer", "service"):
                    live = units / f"{unit}.{ext}"
                    fresh = pathlib.Path(tmp) / f"{unit}.{ext}"
                    if not live.is_file():
                        out.append(("DRIFT", "missing", f"{unit}.{ext} is not written"))
                    elif live.read_text(encoding="utf-8") != fresh.read_text(encoding="utf-8"):
                        out.append(("DRIFT", "unit", f"{unit}.{ext} differs from a fresh render"))
    events = read_events(d)
    st = _state(decl, events, now_local())
    if st["state"] == "LOST":
        out.append(("WARN", "lost", f"started {st['started']['ts']}, no finished row"))
    if st["state"] == "missed":
        out.append(("WARN", "missed", f"was due {decl['due']} and no run recorded"))
    return out


def cmd_check(args, *, env=os.environ, run=subprocess.run, out=print) -> int:
    drift = warn = 0
    names = set()
    for d, decl in _decls(env):
        if decl.get("unreadable"):
            out(f"UNREADABLE {decl['unreadable']}")
            drift += 1
            continue
        names.add(decl["name"])
        for kind, what, msg in self_check(decl, d, env, run=run):
            out(f"{kind:<5}{what:<8}{decl['name']}: {msg}")
            if kind == "DRIFT":
                drift += 1
            else:
                warn += 1
    units = units_dir(env)
    if units.is_dir():
        for path in sorted(units.glob(f"{UNIT_PREFIX}*.timer")):
            name = path.name[len(UNIT_PREFIX):-len(".timer")]
            if name not in names:
                out(f"STALE unit {path.name} (no session record for {name!r})")
                drift += 1
    out(f"sessions --check: {len(names)} record(s), {drift} drift finding(s), "
        f"{warn} warning(s)")
    return 3 if drift else 0


# --- the CLI -----------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="familiar schedule sessions",
                                 description="One session, once: a declared unit, a "
                                             "record, and a model the Loom resolves.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="schedule one session (a unit pair + a record)")
    add.add_argument("--name", help="the session's name (default: from the due time)")
    when = add.add_mutually_exclusive_group()
    when.add_argument("--at", metavar="WHEN", help="local 'YYYY-MM-DD HH:MM[:SS]'")
    when.add_argument("--in", dest="in_", metavar="DELAY", help="e.g. 90m, 2h, 1h30m")
    when.add_argument("--ready", action="store_true",
                      help="no clock: the job runs when its conditions allow (the dispatcher, "
                           "1d); until then `run <name>`")
    add.add_argument("--chain", choices=CHAINS,
                     help="until-done: each run continues the last (default none)")
    add.add_argument("--priority", type=int, metavar="N",
                     help="lower runs first when several jobs are ready (default from config)")
    add.add_argument("--start-when", metavar="NAMES",
                     help="conditions that hold the job back, comma-separated, or none "
                          "(default from config)")
    add.add_argument("--stop-when", metavar="NAMES",
                     help="conditions that end a run at its next item boundary "
                          "(default from config)")
    add.add_argument("--every", metavar="DELAY",
                     help="repeat: a period from the last start (5h, 90m); --at 'HH:MM' or "
                          "--in sets the first start (default: the next tick)")
    ask = add.add_mutually_exclusive_group()
    ask.add_argument("--prompt", metavar="FILE", help="a handoff-style prompt file")
    ask.add_argument("--specs", metavar="FILE", help="a SPECS.md; the ask is resolved")
    add.add_argument("--item", metavar="ID", help="with --specs: one named item")
    add.add_argument("--wave", metavar="N", help="with --specs: the Nth open wave")
    add.add_argument("--all", action="store_true", help="with --specs: every open item")
    add.add_argument("--model", metavar="ID", help="a catalogue id (the Loom resolves it)")
    add.add_argument("--profile", metavar="NAME",
                     help="the billing profile the job spends (default: the caller's, "
                          "written into the record; a tree's .pi-profile must agree)")
    add.add_argument("--class", dest="klass", metavar="CLASS",
                     help="a selection.yaml class; its tier picks the model and effort")
    add.add_argument("--difficulty", type=float, help="with --class: a 0..1 reading")
    add.add_argument("--effort", metavar="LEVEL", help="off|minimal|low|medium|high|xhigh|max")
    add.add_argument("--cwd", metavar="DIR", help="where the session works")
    add.add_argument("--branch", help="the branch it is told to commit on (default: the tree's)")
    add.add_argument("--commit", choices=("per-item", "none"), help="may it commit")
    add.add_argument("--touches", metavar="GLOBS",
                     help="comma-separated write scope; a dirty tree inside it refuses the run")
    add.add_argument("--no-systemctl", action="store_true",
                     help="no effect since 1d: a job has no unit of its own")
    add.add_argument("--dry-run", action="store_true", help="resolve and print; write nothing")

    ls = sub.add_parser("list", help="what is scheduled, and what happened")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--all", action="store_true",
                    help="also the closed records the retention window hides")
    ls.add_argument("--older-than", default=LIST_WINDOW,
                    help=f"how long a closed record stays hidden (default {LIST_WINDOW})")

    sh = sub.add_parser("show", help="one session: the ask, the runs, the log")
    sh.add_argument("name")
    sh.add_argument("--log", type=int, default=0, metavar="N",
                    help="also print the last N lines of its run log")

    ca = sub.add_parser("cancel", help="disable the unit, remove it, keep the record; "
                                       "from inside the job's own run it ends the job")
    ca.add_argument("name", nargs="?")
    ca.add_argument("--all", action="store_true")
    ca.add_argument("--force", action="store_true", help="stop a run that is in flight")
    ca.add_argument("--no-systemctl", action="store_true")

    rn = sub.add_parser("run", help="run it now (this is what the unit calls)")
    rn.add_argument("name")
    rn.add_argument("--dry-run", action="store_true",
                    help="resolve and print the pi argv; call nothing")
    rn.add_argument("--ignore-hold", action="store_true",
                    help="run even though the job is held (a refusal's reset time)")

    cp = sub.add_parser("checkpoint", help="inside a run, before each item: exit 0 to "
                                           "continue, 10 to stop (a stop condition holds)")
    cp.add_argument("--item", metavar="ID", help="the item about to start, for the record")
    cp.add_argument("--job", help=f"the job (default: ${JOB_ENV}, which the run sets)")

    pr = sub.add_parser("prune", help="archive closed or never-started records quiet "
                                      "past --older-than (never deletes)")
    pr.add_argument("--older-than", default=RETENTION,
                    help=f"how long a record must have been quiet (default {RETENTION})")
    pr.add_argument("--dry-run", action="store_true",
                    help="print what would move; write nothing")

    rs = sub.add_parser("resume", help="clear a chain's pause (blocked, stalled, review)")
    rs.add_argument("name")

    ho = sub.add_parser("hold", help="hold a job: the dispatcher starts nothing of it until then")
    ho.add_argument("name")
    ho.add_argument("delay", nargs="?", default="2h", help="e.g. 2h, 90m (default 2h)")

    ph = sub.add_parser("phone", help="a phone-sized screen for the bot: status | jobs | "
                                      "job <name> | budget")
    ph.add_argument("what", choices=("status", "jobs", "job", "budget"))
    ph.add_argument("arg", nargs="?", default="")

    tk = sub.add_parser("tick", help="the dispatcher: start the job that is due and "
                                     "whose conditions allow (the timer calls this)")
    tk.add_argument("--dry-run", action="store_true", help="decide and print; start nothing")
    tk.add_argument("--json", action="store_true")

    co = sub.add_parser("conditions", help="each condition's current value and why")
    co.add_argument("name", nargs="?", help="a job: its own cwd, model and lists")
    co.add_argument("--json", action="store_true")

    sub.add_parser("check", help="records, units and sources agree [--check]")
    return ap


def main(argv: list[str]) -> int:
    if argv[:1] == ["--check"]:
        argv = ["check"] + argv[1:]
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "add":
            return cmd_add(args)
        if args.cmd == "list":
            return cmd_list(args)
        if args.cmd == "show":
            return cmd_show(args)
        if args.cmd == "cancel":
            return cmd_cancel(args)
        if args.cmd == "run":
            return cmd_run(args)
        if args.cmd == "check":
            return cmd_check(args)
        if args.cmd == "conditions":
            return cmd_conditions(args)
        if args.cmd == "checkpoint":
            return cmd_checkpoint(args)
        if args.cmd == "tick":
            return cmd_tick(args)
        if args.cmd == "resume":
            return cmd_resume(args)
        if args.cmd == "prune":
            return cmd_prune(args)
        if args.cmd == "hold":
            return cmd_hold(args)
        if args.cmd == "phone":
            from schedule import phone                       # noqa: PLC0415 -- it imports us
            print("\n".join(phone.main(args.what, args.arg)))
            return 0
    except (SessionError, profiles.ProfileError, selection_mod.SelectionError,
            waves.DependencyError) as e:
        print(f"sessions: {e}", file=sys.stderr)
        return 2
    except (_miniyaml.YamlError, OSError) as e:
        print(f"sessions: {e}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
