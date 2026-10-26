"""notify -- the user hears about a job: a notification and a brief line (dev/schedule 1g).

WHEN. A job reaches a state the user must act on or would want to know: `done`,
`blocked`, `stalled`, `review` (a chain's pause, 1f), `crashed` (the runner
failed before the session started) or `LOST` (a run started and never finished).
A repeating job's ordinary run is not news.

HOW. The record first: a `notified` event is written BEFORE anything is sent, so
the brief and `show` know even when every channel is down. Then two channels,
each best effort -- a failure is recorded, never raised:

* the desktop, `notify-send` on the user session's bus (a unit started by the
  dispatcher has no `DBUS_SESSION_BUS_ADDRESS`; the bus is at
  `/run/user/<uid>/bus`);
* the phone, the relay's `notify` (dev/remote). With no relay running the
  request fails at once; nothing waits on it (HANDOFF: "notify must degrade").

THE BRIEF. `brief_lines` reads the records for the nightly brief's section: each
job with runs since the last pass, how they ended, its state and its commits.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess

from schedule import chain as chain_mod
from schedule import sessions

STATES = ("done", "blocked", "stalled", "review", "crashed", "LOST")
URGENT = ("crashed", "LOST", "blocked")


def _desktop(title: str, text: str, urgency: str, env) -> str:
    """'' on success, else the error."""
    full = dict(os.environ)
    full.update(env or {})
    full.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{os.getuid()}/bus")
    try:
        p = subprocess.run(["notify-send", "--app-name=familiar", f"--urgency={urgency}",
                            title, text], env=full, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    return "" if p.returncode == 0 else (p.stderr or f"exit {p.returncode}").strip()[:200]


def _relay(job: str, text: str, env) -> str:
    try:
        from relay import client                              # noqa: PLC0415
        reply = client.request({"op": "notify", "session": job, "text": text},
                               env=env or os.environ, timeout=3)
    except Exception as exc:                                  # noqa: BLE001 -- best effort
        return f"{type(exc).__name__}: {exc}"[:200]
    return "" if (reply or {}).get("ok", True) else str(reply)[:200]


#: The channels, replaced in a test so the suite never pops a notification.
CHANNELS = {"desktop": _desktop, "relay": _relay}


def send(d, job: str, state: str, text: str, *, env=None, extra: dict | None = None) -> dict:
    """Record, then tell. Returns {channel: error or ''}."""
    sessions.write_event(d, {"event": "notified", "ts": sessions.now_local().isoformat(
        timespec="seconds"), "session": job, "state": state, "text": text, **(extra or {})})
    urgency = "critical" if state in URGENT else "normal"
    errors = {"desktop": CHANNELS["desktop"](f"familiar: {job} {state}", text, urgency, env),
              "relay": CHANNELS["relay"](job, f"{job}: {state} -- {text}", env)}
    failed = {k: v for k, v in errors.items() if v}
    if failed:
        sessions.write_event(d, {"event": "notify_failed", "ts": sessions.now_local().isoformat(
            timespec="seconds"), "session": job, "state": state, "errors": failed})
    return errors


def sweep_lost(env=os.environ, *, now: dt.datetime | None = None) -> list:
    """Notify each LOST run once (the tick calls this): a `started` with no
    `finished` past the job's timeout, not yet notified for that start."""
    now = now or sessions.now_local()
    told = []
    for d, decl in sessions._decls(env):
        if decl.get("unreadable"):
            continue
        events = sessions.read_events(d)
        st = sessions._state(decl, events, now)
        if st["state"] != "LOST":
            continue
        start = (st.get("started") or {}).get("ts", "")
        if any(e.get("event") == "notified" and e.get("state") == "LOST"
               and e.get("started") == start for e in events):
            continue
        send(d, decl["name"], "LOST", f"started {start} and never finished", env=env,
             extra={"started": start})
        told.append(decl["name"])
    return told


# --- the brief ------------------------------------------------------------------

def brief_lines(env=os.environ, *, since: dt.date, now: dt.datetime | None = None) -> list:
    """One bullet per job that ran since `since`, or whose state needs the user."""
    now = now or sessions.now_local()
    out = []
    for d, decl in sessions._decls(env):
        if decl.get("unreadable"):
            continue
        events = sessions.read_events(d)
        runs = [e for e in events if e.get("event") == "finished" and e.get("ts", "")[:10]
                >= since.isoformat()]
        try:
            st = sessions._state(decl, events, now)
        except (KeyError, ValueError, TypeError) as exc:
            # One malformed record is one line, not a brief section that failed.
            out.append(f"- `{decl.get('name', d.name)}` — its record could not be read: {exc}")
            continue
        state = st["state"]
        if not runs and state not in ("paused", "LOST", "crashed", "held"):
            continue
        ended = [chain_mod.ended_why(r) for r in runs]
        commits = [c for r in runs for c in (r.get("progress") or {}).get("commits") or []]
        ticks = [t for r in runs for t in (r.get("progress") or {}).get("ticks") or []]
        line = f"- `{decl['name']}` — **{state}**"
        if st.get("why"):
            line += f" ({st['why']})"
        line += f"; {len(runs)} run(s) since {since.isoformat()}"
        if ended:
            line += ": " + ", ".join(ended[-3:])
        if ticks:
            line += f"; ticked {', '.join(ticks)}"
        line += f"; {len(commits)} commit(s)"
        if commits:
            line += " — " + "; ".join(c for c in commits[:3])
        out.append(line)
    return out
