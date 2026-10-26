"""conditions -- the named predicates that hold a job back or stop a run (dev/schedule 1b).

WHY NAMED. The user's decision 2: which conditions start and stop a run is
configuration, not code. A job lists names (`start_when`, `stop_when`); this
module evaluates each name to a `Verdict(holds, reason, until)`, where **holds
means "this condition is in the way"**: the budget is spent, the user is working,
a conflicting process is due, every slot is taken. `until` is when it stops
holding, if that is knowable.

THE FOUR, and what each reads:

* `budget` -- the account's five-hour and weekly fractions from the Omarchy probe
  (`omarchy-agent-usage-claude --limits-only`, 0.38 s, its own 15 s minimum
  interval), against `budget.five_hour_max`/`budget.weekly_max`. The probe is
  cached for that interval in the data directory. A probe that fails falls back
  to the last window refusal on record (a `held` event whose `until` lies ahead).
  It applies only to a job whose model is served by a listed provider: a
  DeepSeek job does not spend the Claude window. The engine never reads
  `~/.claude/.credentials.json`; the probe does that, not this module.
* `user_active` -- an interactive session in any harness (decision 9): a process
  whose `comm` is a listed harness, that has a controlling terminal, and that
  does not descend from `familiar schedule sessions run`. Measured 2026-10-21:
  an interactive pi is `comm=pi` with a tty; the hermes gateway is `comm=hermes`
  with none; a scheduled run under systemd has none. With `scope: job_cwd` (the
  default, decided 2026-10-21) only a session whose working directory is the
  job's `cwd` or inside it counts: a pi open in another project is not working
  in this job's tree. A session whose cwd cannot be read still counts.
* `conflict` -- a declared process (the nightly pass first) whose write trees
  overlap the job's working directory or its write scope, and which is due within
  its lead time or holds its lock (decision 3: no blackout hours, no collision).
* `slot` -- `max_parallel` runs already in flight (decision 6: serial for now),
  read from the per-job locks.

Every reader is a seam (`Context`), so a test never depends on the machine.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import fcntl
import json
import os
import pathlib
import subprocess
import time
from typing import Callable

from orchestration import profiles

NAMES = ("budget", "user_active", "conflict", "slot")
# The probe's labels: a format the tool prints, not a policy.
FIVE_HOUR, WEEKLY = "5-hour", "7-day"
SCHEDULED_RUN = "schedule sessions run"


class ConditionError(ValueError):
    """An unknown condition name, or a declaration this module cannot read."""


@dataclasses.dataclass
class Verdict:
    holds: bool
    reason: str
    until: dt.datetime | None = None

    def as_dict(self) -> dict:
        return {"holds": self.holds, "reason": self.reason,
                "until": self.until.isoformat(timespec="seconds") if self.until else None}


@dataclasses.dataclass
class Proc:
    pid: int
    ppid: int
    comm: str
    tty: int
    cmdline: str
    #: `/proc/<pid>/cwd`; empty when unreadable.
    cwd: str = ""


def _read_procs() -> list:
    out = []
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            stat = (p / "stat").read_text(encoding="utf-8", errors="replace")
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        try:
            cwd = os.readlink(p / "cwd")
        except OSError:
            cwd = ""
        head, _, tail = stat.rpartition(")")
        fields = tail.split()
        comm = head.split("(", 1)[1] if "(" in head else ""
        # stat after `)`: state ppid pgrp session tty_nr ...
        out.append(Proc(int(p.name), int(fields[1]), comm, int(fields[4]), cmd.strip(), cwd))
    return out


def tty_path(tty_nr: int) -> pathlib.Path | None:
    """`/proc/<pid>/stat`'s tty_nr as a device path: major 136-143 is a pty
    (`34818` -> major 136, minor 2 -> `/dev/pts/2`), major 4 a virtual console."""
    major = (tty_nr >> 8) & 0xFFF
    minor = (tty_nr & 0xFF) | ((tty_nr >> 12) & 0xFFF00)
    if 136 <= major <= 143:
        return pathlib.Path(f"/dev/pts/{(major - 136) * 256 + minor}")
    if major == 4:
        return pathlib.Path(f"/dev/tty{minor}")
    return None


def _tty_seen(tty_nr: int) -> float | None:
    """The last I/O on a terminal: its atime is the last input, its mtime the last
    output (measured 2026-10-21; `w`'s IDLE column reads the same device)."""
    path = tty_path(tty_nr)
    try:
        st = path.stat() if path else None
    except OSError:
        return None
    return max(st.st_atime, st.st_mtime) if st else None


def _run_probe(argv: list, env: dict | None = None) -> dict:
    """The probe, under the account's environment (2c). `env` is a FULL
    environment (`profiles.with_account`), passed to the child rather than set on
    this process, so a tick that gates several accounts never leaves one of them
    behind in the dispatcher's own environment."""
    p = subprocess.run(argv, capture_output=True, text=True, timeout=30,
                       env=dict(env) if env else None)
    if p.returncode:
        raise OSError(f"{argv[0]} exited {p.returncode}: {(p.stderr or '').strip()[:200]}")
    return json.loads(p.stdout)


@dataclasses.dataclass
class Context:
    """What the predicates read. Every field has a real default and is replaced in
    a test: `now`, the process table, the probe, and the session records."""
    policy: dict
    env: dict = dataclasses.field(default_factory=lambda: dict(os.environ))
    now: dt.datetime | None = None
    procs: Callable[[], list] = _read_procs
    probe: Callable[..., dict] = _run_probe
    clock: Callable[[], float] = time.time
    tty_seen: Callable[[int], float | None] = _tty_seen

    def when(self) -> dt.datetime:
        return self.now or dt.datetime.now().astimezone()

    def conf(self, name: str) -> dict:
        return (self.policy.get("conditions") or {}).get(name) or {}


def _delay(text: str, default: float) -> float:
    from schedule import sessions                            # noqa: PLC0415 -- a cycle
    try:
        return sessions.parse_delay(text).total_seconds() if text else default
    except sessions.SessionError:
        return default


# --- budget --------------------------------------------------------------------

@dataclasses.dataclass
class Reading:
    """One account's windows, and whose they are: `windows` is
    `{'five_hour': (fraction, resets|None), 'weekly': (...)}`. It answers the dict
    interface it replaced, so a caller that only wants the fractions is unchanged."""
    profile: str
    tier: str
    windows: dict

    def __getitem__(self, key):
        return self.windows[key]

    def __contains__(self, key):
        return key in self.windows

    def get(self, key, default=None):
        return self.windows.get(key, default)

    def items(self):
        return self.windows.items()

    def values(self):
        return self.windows.values()

    def keys(self):
        return self.windows.keys()

    def account(self) -> str:
        """`private · Pro` -- the profile, and the tier the probe reports for it."""
        return self.profile + (f" · {self.tier}" if self.tier else "")


def read_budget(ctx: Context, profile: str | None = None, fresh: bool = False) -> Reading:
    """The windows of ONE account -- the job's (2c) -- from the probe, cached for
    its minimum interval so a tick and a checkpoint in the same 15 s share one
    call. The cache is keyed by profile: the tool's own reuse window is ONE file
    with no account in its key, so a shared reading here would gate a Work job on
    whichever account probed last (measured 2026-10-22). `fresh` skips the cache: the
    window ping asks again right after it opened a window, to learn when it ends
    (`--force` too: the tool's own 15 s reuse window would hand back the old reading)."""
    conf = ctx.conf("budget")
    profile = profile or profiles.active(ctx.env)
    acct = profiles.with_account(ctx.env, profile)
    # The tool's cache root is `$XDG_CACHE_HOME/omarchy/agent-usage`, and its limits
    # reuse window AND its fallback for a refused probe both come from there. Shared,
    # they carry one account's numbers into another's reading: measured 2026-10-22, a
    # Work probe answered 429 fell back to the personal 91%/90% (with the Team tier
    # label on top), and nothing in the output said so. One cache per account makes the
    # fallback that account's own last reading, or none at all.
    acct["XDG_CACHE_HOME"] = str(profiles.data_dir(ctx.env) / "sessions" / "probe-cache"
                                / profile)
    cache = profiles.data_dir(ctx.env) / "sessions" / "budget.json"
    interval = _delay(conf.get("probe_interval") or "15s", 15.0)
    data = None
    try:
        saved = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if saved.get("at") is not None or saved.get("data") is not None:
        # A flat file, as the engine wrote it before 2c: the machine's own account.
        saved = {profiles.load()["default"]: saved}
    entry = saved.get(profile) or {}
    if not fresh and ctx.clock() - float(entry.get("at", 0)) < interval:
        data = entry.get("data")
    if data is None:
        argv = list(conf.get("probe") or ["omarchy-agent-usage-claude", "--limits-only"])
        if fresh and "--force" not in argv:
            argv.append("--force")          # the tool keeps its OWN 15 s reuse window
        data = ctx.probe(argv, acct)
        saved[profile] = {"at": ctx.clock(), "data": data}
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(saved), encoding="utf-8")
    out = {}
    for lim in data.get("limits") or []:
        label = str(lim.get("label", ""))
        key = "five_hour" if FIVE_HOUR in label else "weekly" if WEEKLY in label else ""
        if not key:
            continue
        resets = None
        if lim.get("resetsAt"):
            resets = dt.datetime.fromisoformat(lim["resetsAt"]).astimezone()
        out[key] = (float(lim.get("percent") or 0.0), resets)
    if "five_hour" not in out and "weekly" not in out:
        raise ValueError("the probe printed no five-hour or weekly limit")
    return Reading(profile, str(data.get("tierLabel") or ""), out)


def _last_refusal(ctx: Context) -> dt.datetime | None:
    """The latest future hold any job recorded after a window refusal."""
    from schedule import sessions                            # noqa: PLC0415
    best = None
    for d, _decl in sessions._decls(ctx.env):
        for e in sessions.read_events(d):
            if e.get("event") != "held" or "window refused" not in str(e.get("why", "")):
                continue
            try:
                until = dt.datetime.fromisoformat(e["until"])
            except (KeyError, ValueError):
                continue
            if until > ctx.when() and (best is None or until > best):
                best = until
    return best


def budget(job: dict, ctx: Context) -> Verdict:
    conf = ctx.conf("budget")
    provider = str((job.get("model") or {}).get("pi_model", "")).split("/", 1)[0]
    providers = list(conf.get("providers") or [])
    if providers and provider not in providers:
        return Verdict(False, f"{provider or 'no provider'} does not spend the Claude window")
    try:
        profile = profiles.declared(job)
    except profiles.ProfileError as exc:
        return Verdict(True, f"{exc}; nothing may spend an undeclared account")
    try:
        reading = read_budget(ctx, profile)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        until = _last_refusal(ctx)
        if until:
            return Verdict(True, f"probe failed ({exc}); the last refusal holds until "
                                 f"{until.isoformat(timespec='minutes')}", until)
        return Verdict(False, f"probe failed ({exc}); no refusal on record, so not holding")
    caps = {"five_hour": float(conf.get("five_hour_max") or 1.0),
            "weekly": float(conf.get("weekly_max") or 1.0)}
    spent = [(k, f, r) for k, (f, r) in reading.items() if f >= caps[k]]
    parts = [f"{k.replace('_', '-')} {f:.0%} of {caps[k]:.0%}" for k, (f, _) in reading.items()]
    if not spent:
        return Verdict(False, "; ".join(parts) + f" [{reading.account()}]")
    # The binding limit is the one that frees LAST.
    until = max((r for _, _, r in spent if r), default=None)
    return Verdict(True, f"spent [{reading.account()}]: " + "; ".join(parts), until)


# --- user_active ---------------------------------------------------------------

def interactive_sessions(ctx: Context, job: dict | None = None) -> list:
    """The processes that count as the user working: a listed harness on a terminal,
    not inside a scheduled run, whose terminal saw input or output within
    `idle_after` (empty: any open session counts). Measured 2026-10-21: a pi left
    open since the afternoon would otherwise hold every job all night."""
    conf = ctx.conf("user_active")
    harnesses = set(conf.get("harnesses") or [])
    idle = _delay(conf.get("idle_after") or "", 0.0)
    procs = ctx.procs()
    by_pid = {p.pid: p for p in procs}

    def scheduled(p: Proc) -> bool:
        seen = set()
        while p and p.pid not in seen and p.pid > 1:
            if SCHEDULED_RUN in p.cmdline:
                return True
            seen.add(p.pid)
            p = by_pid.get(p.ppid)
        return False

    def recent(p: Proc) -> bool:
        if not idle:
            return True
        seen = ctx.tty_seen(p.tty)
        return seen is None or ctx.clock() - seen < idle

    scope = conf.get("scope") or "job_cwd"
    if scope not in ("job_cwd", "any"):
        raise ConditionError(f"user_active.scope must be job_cwd or any, not {scope!r}")
    root = _expand(job["cwd"]) if scope == "job_cwd" and job and job.get("cwd") else None

    def here(p: Proc) -> bool:
        # Inside the job's tree, not merely above it: a pi in ~ is not working in
        # ~/01_PROJECTS/X. An unreadable cwd counts, the safe direction.
        if root is None or not p.cwd:
            return True
        cwd = pathlib.Path(p.cwd)
        return cwd == root or root in cwd.parents

    found = [p for p in procs if p.comm in harnesses and p.tty != 0
             and not scheduled(p) and recent(p) and here(p)]
    # One session is often a harness inside a harness (this very session: pi -> claude);
    # report the outermost one.
    pids = {p.pid for p in found}
    return [p for p in found if p.ppid not in pids]


def user_active(job: dict, ctx: Context) -> Verdict:
    found = interactive_sessions(ctx, job)
    if not found:
        scoped = (ctx.conf("user_active").get("scope") or "job_cwd") == "job_cwd"
        where = f" in {job.get('cwd')}" if scoped and job.get("cwd") else ""
        return Verdict(False, f"no interactive session{where}")
    def seen(p: Proc) -> str:
        t = ctx.tty_seen(p.tty)
        return f", I/O {ctx.clock() - t:.0f}s ago" if t is not None else ""

    # The age of each terminal's last I/O is the evidence `idle_after` judged by.
    names = ", ".join(f"{p.comm} (pid {p.pid}{seen(p)})" for p in found[:4])
    return Verdict(True, f"interactive: {names}")


# --- conflict ------------------------------------------------------------------

def _expand(path: str) -> pathlib.Path:
    return pathlib.Path(os.path.expanduser(path)).resolve()


def _overlap(a: pathlib.Path, b: pathlib.Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _next_daily(at: str, now: dt.datetime) -> dt.datetime:
    hh, mm = (int(x) for x in at.split(":", 1))
    when = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return when if when >= now else when + dt.timedelta(days=1)


def _lock_held(path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    with path.open("r") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return False
        except OSError:
            return True


def _job_paths(job: dict) -> list:
    cwd = _expand(job.get("cwd") or "~")
    out = [cwd]
    for t in job.get("touches") or []:
        head = t.split("*", 1)[0].rstrip("/") or "."
        p = pathlib.Path(os.path.expanduser(head))
        out.append((p if p.is_absolute() else cwd / p).resolve())
    return out


def conflict(job: dict, ctx: Context) -> Verdict:
    now = ctx.when()
    paths = _job_paths(job)
    clear = []
    for name, decl in (ctx.conf("conflict").get("processes") or {}).items():
        trees = [_expand(t) for t in decl.get("trees") or []]
        if not any(_overlap(p, t) for p in paths for t in trees):
            continue
        lock = decl.get("lock") or ""
        if lock:
            lp = pathlib.Path(os.path.expanduser(lock))
            lp = lp if lp.is_absolute() else profiles.data_dir(ctx.env) / lp
            if _lock_held(lp):
                return Verdict(True, f"{name} is running (holds {lp.name})")
        if decl.get("at"):
            due = _next_daily(decl["at"], now)
            lead = dt.timedelta(seconds=_delay(decl.get("lead") or "30m", 1800.0))
            if due - now <= lead:
                return Verdict(True, f"{name} is due at {due.strftime('%H:%M')} "
                                     f"(lead {decl.get('lead') or '30m'})", due)
            clear.append(f"{name} overlaps, due {due.strftime('%H:%M')} "
                         f"(outside its {decl.get('lead') or '30m'} lead)")
        else:
            clear.append(f"{name} overlaps and is not running")
    return Verdict(False, "; ".join(clear) or "no declared process overlaps this job")


# --- slot ----------------------------------------------------------------------

def running_jobs(ctx: Context, exclude: str = "") -> list:
    from schedule import sessions                            # noqa: PLC0415
    return [decl.get("name", d.name) for d, decl in sessions._decls(ctx.env)
            if decl.get("name") != exclude and sessions.RunLock(d).held()]


def slot(job: dict, ctx: Context) -> Verdict:
    cap = int(ctx.conf("slot").get("max_parallel") or 1)
    running = running_jobs(ctx, exclude=job.get("name", ""))
    if len(running) >= cap:
        return Verdict(True, f"{len(running)} of {cap} slot(s) taken: {', '.join(running)}")
    return Verdict(False, f"{len(running)} of {cap} slot(s) taken")


PREDICATES = {"budget": budget, "user_active": user_active, "conflict": conflict,
              "slot": slot}


def evaluate(name: str, job: dict, ctx: Context) -> Verdict:
    try:
        return PREDICATES[name](job, ctx)
    except KeyError:
        raise ConditionError(f"unknown condition {name!r}; known: {', '.join(NAMES)}") from None


def evaluate_all(names: list, job: dict, ctx: Context) -> dict:
    return {n: evaluate(n, job, ctx) for n in names}


def blocking(names: list, job: dict, ctx: Context) -> list:
    """The (name, verdict) pairs among `names` that hold, in the order named."""
    return [(n, v) for n, v in evaluate_all(names, job, ctx).items() if v.holds]


def validate(names: list) -> None:
    unknown = [n for n in names if n not in PREDICATES]
    if unknown:
        raise ConditionError(f"unknown condition(s) {', '.join(unknown)}; "
                             f"known: {', '.join(NAMES)}")
