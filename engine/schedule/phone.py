"""phone -- the scheduler's screens for the bot's commands (dev/remote R5b).

`familiar schedule sessions phone status|jobs|job <name>|budget` prints plain text
of at most ~25 lines, for `relay.yaml`'s registry: `/status` (below the relay's
own asks), `/jobs`, `/job <name>`, `/budget`. Read-only: nothing here writes a
record, and the budget comes through the cached probe (`conditions.read_budget`).
Closed jobs (cancelled, ended) appear only by name in `/job`; the lists show what
can still run.
"""
from __future__ import annotations

import datetime as dt
import json
import os

from schedule import chain as chain_mod
from schedule import conditions as conditions_mod
from schedule import sessions

MAX_JOBS = 15


def _hm(when) -> str:
    if not when:
        return ""
    if isinstance(when, str):
        when = dt.datetime.fromisoformat(when)
    return when.astimezone().strftime("%a %H:%M")


def _open_jobs(env) -> list:
    from schedule import dispatch                            # noqa: PLC0415 -- it imports sessions
    now = sessions.now_local()
    out = []
    for d, decl in sessions._decls(env):
        if decl.get("unreadable") or sessions.closed(decl):
            continue
        events = sessions.read_events(d)
        st = sessions._state(decl, events, now)
        # A one-off that is done will never run again: the dispatcher's own answer.
        if st["state"] in ("done", "missed") and dispatch.next_due(decl, events, now)[0] is None:
            continue
        out.append((d, decl, events, st))
    return out


def _last_ending(events: list) -> str:
    fin = next((e for e in reversed(events) if e.get("event") == "finished"), None)
    crashed = next((e for e in reversed(events) if e.get("event") == "crashed"), None)
    if not fin and not crashed:
        return "never ran"
    return f"{chain_mod.ended_why(fin, crashed)} ({_hm((fin or crashed).get('ts'))})"


def _deferred(events: list) -> str:
    """The condition names of the last `deferred` since the last start, or ''."""
    for e in reversed(events):
        if e.get("event") == "started":
            return ""
        if e.get("event") == "deferred":
            return ", ".join(e.get("holding") or {})
    return ""


def budget_lines(env) -> list:
    ctx = conditions_mod.Context(sessions.load_policy(), env=dict(env))
    conf = ctx.conf("budget")
    try:
        reading = conditions_mod.read_budget(ctx)
    except (OSError, ValueError) as exc:
        return [f"budget: the probe failed ({exc})"]
    caps = {"five_hour": conf.get("five_hour_max") or "1.0", "weekly": conf.get("weekly_max") or "1.0"}
    out = []
    for key, label in (("five_hour", "5-hour"), ("weekly", "weekly")):
        if key in reading:
            frac, resets = reading[key]
            cap = float(caps[key])
            flag = "  HOLDS jobs" if frac >= cap else ""
            when = f", resets {_hm(resets)}" if resets else " (window not started)"
            out.append(f"{label}: {frac:.0%} of {cap:.0%}{when}{flag}")
    return out


def last_tick(env) -> str:
    path = sessions.data_root(env) / "dispatch.jsonl"
    try:
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return "dispatcher: no tick on record"
    return (f"last tick {_hm(row['ts'])}: "
            + (f"started {row['started']}" if row.get("started") else "started nothing"))


def screen_status(env) -> list:
    jobs = _open_jobs(env)
    counts: dict = {}
    for _d, _decl, _ev, st in jobs:
        counts[st["state"]] = counts.get(st["state"], 0) + 1
    head = ", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "no open job"
    lines = [f"jobs: {head}"]
    for _d, decl, ev, st in jobs:
        held_back = _deferred(ev)
        if held_back and st["state"] in ("ready", "due", "repeating", "pending", "continuing"):
            lines.append(f"- {decl['name']}: {st['state']}, held back by {held_back}")
        if st["state"] in ("running", "waiting", "paused", "held", "LOST", "crashed"):
            lines.append(f"- {decl['name']}: {st['state']}"
                         + (f" -- {st['why']}" if st.get("why") else "")
                         + (f" until {_hm(st['until'])}" if st.get("until") else ""))
    return lines + budget_lines(env) + [last_tick(env)]


def screen_jobs(env) -> list:
    jobs = _open_jobs(env)
    if not jobs:
        return ["no open job"]
    lines = []
    for _d, decl, events, st in jobs[:MAX_JOBS]:
        job = sessions.job_of(decl)
        extra = (f" until {_hm(st['until'])}" if st.get("until") else
                 f" ({st['why']})" if st.get("why") else "")
        lines.append(f"{decl['name']} [{job['trigger']}{'/chain' if job['chain'] != 'none' else ''}]"
                     f" {st['state']}{extra}; last: {_last_ending(events)}")
    if len(jobs) > MAX_JOBS:
        lines.append(f"... and {len(jobs) - MAX_JOBS} more (`familiar schedule sessions list`)")
    return lines


def screen_job(env, name: str) -> list:
    d, decl = sessions._find(name, env)
    events = sessions.read_events(d)
    st = sessions._state(decl, events, sessions.now_local())
    job = sessions.job_of(decl)
    lines = [f"{decl['name']}: {st['state']}" + (f" -- {st['why']}" if st.get("why") else ""),
             f"{job['trigger']}, chain {job['chain']}, model {(decl.get('model') or {}).get('id', '?')}",
             f"last: {_last_ending(events)}"]
    fin = next((e for e in reversed(events) if e.get("event") == "finished"), None)
    if fin:
        prog = fin.get("progress") or {}
        if prog.get("ticks"):
            lines.append(f"ticked: {', '.join(prog['ticks'])}")
        commits = prog.get("commits") or []
        lines.append(f"commits: {len(commits)}")
        lines += [f"  {c}" for c in commits[:5]]
        report = (fin.get("report") or "").strip()
        if report:
            lines += ["report:", report[-600:]]
    if st["state"] == "paused":
        lines.append(f"/approve {decl['name']} lets it go on")
    return lines


def main(what: str, arg: str = "", env=os.environ) -> list:
    if what == "status":
        return screen_status(env)
    if what == "jobs":
        return screen_jobs(env)
    if what == "job":
        return screen_job(env, arg)
    if what == "budget":
        return budget_lines(env)
    raise sessions.SessionError(f"phone: {what!r}; one of status, jobs, job <name>, budget")
