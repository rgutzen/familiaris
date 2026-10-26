"""dispatch -- one tick decides what runs (dev/schedule 1d).

WHY ONE TICK. 9a gave every session its own timer, so the trigger was a clock and
there were as many clocks as jobs: the 24-hour day with a 5-hour step (PLAN
defect 1), the ping and the anchors drifting apart (2). The intent is a resource
event -- "the budget is free" -- so one unit (`familiar-dispatch.timer`, every
five minutes, decision 10) reads every record and decides:

1. **Backstops first.** A run whose stop condition has a `hard_stop` that is due
   is interrupted (1c's `backstop`/`interrupt`: the event, then SIGINT).
2. **Who is due.** A job's trigger (`at`, `every` from its last start, `ready`),
   minus a hold that lies ahead, a run in flight, or a run just dispatched.
3. **Who may start.** Each due job's `start_when` conditions; one that holds
   defers it, with the reason.
4. **One start.** The lowest `priority`, then the oldest; at most one per tick
   (decision 6: serial). It starts DETACHED through `systemd-run --user` as its
   own transient service: a child of the tick's oneshot service would be killed
   when the tick exits (systemd's default `KillMode=control-group`).

Every tick appends one line to `$PAZRAS_DATA_DIR/sessions/dispatch.jsonl` -- what
was due, what held it, what started -- and a job's own record gains `deferred`
only when its reasons change, so a night of five-minute ticks is not a night of
identical rows. A 9a record with its own unit is skipped: its unit fires it.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import pathlib
import subprocess

from schedule import chain as chain_mod
from schedule import conditions as conditions_mod
from schedule import sessions

LOG = "dispatch.jsonl"
LOCK = "dispatch.lock"
#: A run dispatched this recently with no event since is still starting: do not
#: start it again, and start nothing else beside it (serial).
STARTING = dt.timedelta(minutes=10)
RUN_UNIT = "familiar-run-"


def _ts(e: dict) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(e["ts"])
    except (KeyError, ValueError, TypeError):
        return None


def _last(events: list, *kinds: str) -> dict | None:
    for e in reversed(events):
        if e.get("event") in kinds:
            return e
    return None


def starting(events: list, now: dt.datetime) -> bool:
    """Dispatched within STARTING and nothing recorded since: the run has not taken
    its lock yet."""
    if not events or events[-1].get("event") != "dispatched":
        return False
    t = _ts(events[-1])
    return bool(t and now - t < STARTING)


def next_due(decl: dict, events: list, now: dt.datetime) -> tuple:
    """(when, why) this job is next due, or (None, why) when it never runs again.

    * `at`/`ready`: once. A `finished` the window did not refuse and no backstop
      interrupted is the end of it (a failed run is not repeated blindly), and so
      is a `crashed` -- a defect in the runner would otherwise restart every tick.
    * `every`: its period after the last start (or crash), else its first time.
    * a chain: the next tick after its last run, until `chain.py` ends or pauses it.
    * A `refused` (dirty tree, unavailable model) with no hold after it backs off
      `retry.fallback` instead of refusing again every five minutes."""
    job = sessions.job_of(decl, {})
    if sessions.closed(decl):
        return None, sessions.closed(decl)
    if decl.get("unit"):
        return None, "fired by its own unit (a 9a record)"
    first = decl.get("due") or decl.get("created")
    when = dt.datetime.fromisoformat(first) if first else now
    if job["chain"] != "none":
        # A chain continues at the next tick after a run (or after its period, for
        # `every`) until its own rule ends or pauses it (1f).
        why = chain_mod.paused(events, sessions._ask_sha(decl))
        if why:
            return None, f"paused -- {why}; `resume` it"
        last = _last(events, "finished", "crashed")
        if last and last.get("event") == "crashed":
            return None, "the runner crashed; `run` it by hand once fixed"
        start = _last(events, "started")
        if job["trigger"] == "every" and start and _ts(start):
            when = _ts(start) + sessions.parse_delay(decl.get("every") or "5h")
        elif last and _ts(last):
            when = max(when, _ts(last))
    elif job["trigger"] in ("at", "ready"):
        for e in events:
            if e.get("event") == "crashed":
                return None, "the runner crashed; `run` it by hand once fixed"
            if (e.get("event") == "finished" and not e.get("window_refused")
                    and not e.get("interrupted")):
                return None, f"done (exit {e.get('exit')})"
    else:
        last = _last(events, "started", "crashed")
        if last and _ts(last):
            when = _ts(last) + sessions.parse_delay(decl.get("every") or "5h")
    refused = _last(events, "refused", "held", "started")
    if refused and refused.get("event") == "refused" and _ts(refused):
        policy = sessions.load_policy().get("retry") or {}
        back = _ts(refused) + sessions.parse_delay(policy.get("fallback") or "30m")
        when = max(when, back)
    until = sessions.hold_until(events)
    if until:
        when = max(when, until)
    return when, "due" if when <= now else f"next at {when.isoformat(timespec='minutes')}"


def start_detached(d: pathlib.Path, decl: dict, *, run=subprocess.run) -> dict:
    """The job's wrapper as a transient user service of its own, so it outlives the
    tick. The wrapper sources the keys and calls `familiar schedule sessions run`."""
    unit = f"{RUN_UNIT}{decl['name']}-{sessions.now_local().strftime('%Y%m%dT%H%M%S')}"
    argv = ["systemd-run", "--user", "--quiet", "--collect", f"--unit={unit}",
            f"--working-directory={decl['cwd']}",
            f"--property=Nice={decl.get('nice') or 15}",
            "--property=IOSchedulingClass=idle", decl["wrapper"]]
    p = run(argv, capture_output=True, text=True)
    return {"unit": unit, "ok": not getattr(p, "returncode", 0),
            "error": (getattr(p, "stderr", "") or "").strip()[:300]}


class TickLock:
    """Two ticks at once (the timer and a person) would both start the same job."""

    def __init__(self, env):
        self.path = sessions.data_root(env) / LOCK
        self.fh = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = self.path.open("a+")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            self.fh = None
        return self

    @property
    def taken(self) -> bool:
        return self.fh is not None

    def __exit__(self, *exc):
        if self.fh:
            self.fh.close()
        return False


def tick(env=os.environ, *, now: dt.datetime | None = None, ctx=None,
         start=start_detached, interrupt=sessions.interrupt, dry_run: bool = False) -> dict:
    """One decision. Returns the row it logged."""
    now = now or sessions.now_local()
    ctx = ctx or conditions_mod.Context(sessions.load_policy(), env=dict(env), now=now)
    row = {"ts": now.isoformat(timespec="seconds"), "started": None, "backstops": [],
           "jobs": {}, "dry_run": dry_run}
    with TickLock(env) as lock:
        if not lock.taken:
            row["skipped"] = "another tick holds the dispatch lock"
            return row
        records = [(d, decl) for d, decl in sessions._decls(env) if not decl.get("unreadable")]
        busy = []
        # 1. backstops for the runs in flight
        for d, decl in records:
            if sessions.RunLock(d).held():
                busy.append(decl["name"])
                verdict = sessions.backstop(d, decl, ctx, now=now)
                if verdict:
                    row["backstops"].append({"job": decl["name"], **verdict})
                    if not dry_run:
                        interrupt(d, decl, verdict)
        # 2-3. who is due, and who may start
        ready = []
        for d, decl in records:
            name = decl["name"]
            events = sessions.read_events(d)
            if name in busy:
                row["jobs"][name] = "running"
                continue
            if starting(events, now):
                row["jobs"][name] = "starting"
                busy.append(name)
                continue
            when, why = next_due(decl, events, now)
            if when is None or when > now:
                if when is not None:
                    row["jobs"][name] = why
                continue
            job = {**decl, **sessions.job_of(decl)}
            holding = conditions_mod.blocking(job["start_when"], job, ctx)
            if holding:
                reasons = {n: v.reason for n, v in holding}
                row["jobs"][name] = "deferred: " + "; ".join(f"{n}: {r}" for n, r in reasons.items())
                last = sessions_last_deferred(events)
                if not dry_run and (last is None or sorted(last) != sorted(reasons)):
                    sessions.write_event(d, {"event": "deferred", "ts": row["ts"],
                                             "session": name, "holding": reasons})
                continue
            ready.append((job["priority"], decl.get("created", ""), d, decl))
        # 4. one start, serial
        if ready and busy:
            for _p, _c, _d, decl in ready:
                row["jobs"][decl["name"]] = f"waiting: {', '.join(busy)} in flight"
        elif ready:
            ready.sort(key=lambda r: (r[0], r[1]))
            _p, _c, d, decl = ready[0]
            for _p2, _c2, _d2, other in ready[1:]:
                row["jobs"][other["name"]] = f"waiting: {decl['name']} goes first (priority)"
            if dry_run:
                row["jobs"][decl["name"]] = "would start"
            else:
                got = start(d, decl)
                sessions.write_event(d, {"event": "dispatched" if got["ok"] else "refused",
                                         "ts": row["ts"], "session": decl["name"],
                                         "unit": got["unit"],
                                         **({} if got["ok"] else
                                            {"reason": f"systemd-run: {got['error']}"})})
                row["jobs"][decl["name"]] = "started" if got["ok"] else f"start failed: {got['error']}"
                row["started"] = decl["name"] if got["ok"] else None
    if not dry_run:
        path = sessions.data_root(env) / LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def sessions_last_deferred(events: list) -> list | None:
    """The condition names of the last `deferred` since the last start, or None."""
    for e in reversed(events):
        if e.get("event") == "started":
            return None
        if e.get("event") == "deferred":
            return list((e.get("holding") or {}).keys())
    return None
