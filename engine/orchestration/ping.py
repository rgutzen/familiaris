"""ping -- open a Claude window on purpose, two minutes after the last one ended
(2026-10-14, the user's request; rescheduled from the observed window 2026-10-25).

WHY THIS EXISTS. The Claude quota is a five-hour WINDOW: the first call opens it,
five hours later it closes, and a call made while it is closed fails with
`Claude rate limit (five_hour) -- resets <time>` rather than waiting. So a session
that starts at an unlucky moment loses an hour of work to a boundary it cannot
see -- measured twice on 2026-10-14, the second time killing four evaluation cells
mid-run. A ping just AFTER each window closes opens the next one and keeps the
budget continuously available. It does not create budget -- the rate is the
vendor's -- it makes the boundary predictable, which is what a schedule can do and
a session cannot.

WHY IT IS A TICK, NOT AN INTERVAL (2026-10-25). The first version ran on a systemd
`OnUnitActiveSec=5h 2m` and trusted that every ping lands two minutes after the
window it opened. The journal of 2026-10-20..25 refutes that: 11 of 24 intervals
were not 5h02m. A monotonic interval is anchored to nothing about the window --
`CLOCK_MONOTONIC` stops in suspend (measured: the timer's clock was 11h12m behind
the wall clock after one lid-closed night), a reboot re-arms `OnActiveSec`, any
extra start re-phases it, and a refused ping did not move the next one to the reset
time the refusal had just named (a 00:10 reset was pinged at 03:10). So the window
is read, not predicted. The timer fires every five minutes; each tick

  1. exits at once (no network, no output) while `next_check` in the state file is
     in the future;
  2. otherwise asks the usage probe for BOTH windows -- they are different: the
     5-hour one reopens by use, the weekly one only when it resets;
  3. weekly spent -> no call can work, wait for the weekly reset (+2 min);
     a 5-hour window open -> wait for its end (+2 min);
     none open -> ping, then probe again (forced) for the end of the window it
     opened, and wait for that.

A reported end further ahead than the window's own length (5 h, a week) cannot be
real -- a clock jump or a changed probe format -- and waiting for it would stop
the keeper silently for days, so it is ignored and the row says so.

A call that hangs or fails is UNKNOWN, not CLOSED: it backs off 5, 10, 20, 30 min
and is retried on a tick, never in a loop, and the fourth one in a row fails the
unit so `OnFailure=` tells a person. The model is called once per window, about
five times a day, and a tick before `next_check` costs one process start.

WHY IT COSTS ALMOST NOTHING. One call, `pong`, with the smallest prompt this
system knows how to build: `--system-prompt` REPLACES pi's own prompt (the
`pi-agent` measurement, 2026-09-06: 9,044 bytes of plugin payload against 1,001
for a replaced prompt), `-nc` drops project context and `-ns` the skills index, and `--no-session` leaves
no transcript behind at all -- the ping must not clutter the sessions it exists to
protect. The model is the cheapest Claude entry in the catalogue, resolved under
the active profile like every other call in this system (decision 25), so a
profile that cannot serve it says so instead of silently reaching elsewhere.

WHAT IT RECORDS. One JSON line per DECISION (not per tick) in
`<PAZRAS_DATA_DIR>/claude-window.jsonl`: `event` is `ping`, `open` (a window was
already running), `weekly` (spent), or `unknown`; with the end of each window as the
probe reported it and the `next_check` it set. `--audit` reads the lag of every ping
behind the window end that preceded it -- the evidence that the schedule works.
`claude-window-state.json` beside it holds `next_check` and the unknown-streak.

EXIT CODES. 0 whatever the window did (a closed window is information, not a
failure, and a timer that "fails" nightly teaches its reader to ignore it). 1 only
after `ALERT_AFTER` unknown results in a row. 2 a usage error, an unreadable config
or a profile that cannot serve the model (a missing key or login) -- NOT a spent
quota: the quota gate of `profiles.resolve` is bypassed here (see `serve`), because
the question "is the window spent" is this module's own, answered per window.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile

from harness import pi_call
from lib import _miniyaml
from lib import roots
from orchestration import models, profiles

CATALOGUE = roots.SUBAGENTS / "models.yaml"
APPROVALS = "claude-window.jsonl"
STATE = "claude-window-state.json"
PING = "pong"
SYSTEM = "You answer with one word."
# `resets 1:40:00 AM: You've hit your session limit · resets 1:40am (Europe/Berlin)`
# -- the clock time, not the sentence that follows it.
RESET = re.compile(r"resets?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)", re.I)
# `Claude rate limit (five_hour) -- ...`: which of the two windows turned the call away.
LIMIT = re.compile(r"\((five_hour|seven_day)\)")
REFUSED = re.compile(r"rate limit|quota exceeded|session limit|weekly limit|HTTP 429", re.I)
TIMEOUT = 120.0
# What one ping spends: the system line, the word, the word back (14c prices it).
PING_USAGE = {"input": 20, "output": 2}
#: After a window's end, before the ping: a call in the last second of a window
#: would be charged to the old one and open nothing.
MARGIN = datetime.timedelta(minutes=2)
#: Minutes to wait after an UNKNOWN result, by how many came in a row; the last repeats.
BACKOFF = (5, 10, 20, 30)
#: The unknown-streak at which the unit fails, so `OnFailure=` tells a person.
ALERT_AFTER = 4
#: The weekly fraction at which no call can work (the probe prints 1.00 when spent).
WEEKLY_SPENT = 0.995
#: `--audit`: a ping later than this behind the end of the window it follows is late.
LAG_OK = 10
#: A window cannot end later than its own length from now, nor the weekly one reset
#: later than a week; a reading past that (plus `SPAN_SLACK`) is a broken probe.
FIVE_SPAN = datetime.timedelta(hours=5)
WEEKLY_SPAN = datetime.timedelta(days=7)
SPAN_SLACK = datetime.timedelta(minutes=5)


@dataclasses.dataclass
class Budget:
    """The two windows as the usage probe reports them: a fraction and an end
    (None when no window is running -- the probe prints an empty `resetsAt`)."""
    five: float | None = None
    five_ends: datetime.datetime | None = None
    weekly: float | None = None
    weekly_ends: datetime.datetime | None = None


@dataclasses.dataclass
class Decision:
    event: str                          # `ping` | `open` | `weekly`
    due: datetime.datetime | None = None
    note: str = ""                      # a reading it refused to believe, for the log


def cheapest_claude(cat: dict) -> str:
    """The catalogue's cheapest callable Claude entry: the ping only needs the
    account to register a request, so it may as well be the smallest one."""
    from orchestration import price as _price                        # noqa: PLC0415
    best, price = "", None
    for e in cat.get("models") or []:
        if e.get("vendor") != "anthropic" or e.get("kind") != "chat":
            continue
        total = _price.cost(e.get("cost") or {}, PING_USAGE)[0]
        if price is None or total < price:
            best, price = e["id"], total
    if not best:
        raise profiles.ProfileError("the catalogue lists no callable Claude model")
    return best


def log_path(env=os.environ) -> pathlib.Path:
    return profiles.data_dir(env) / APPROVALS


def state_path(env=os.environ) -> pathlib.Path:
    return profiles.data_dir(env) / STATE


def record(row: dict, env=os.environ) -> None:
    path = log_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_state(env=os.environ) -> dict:
    """The state file, or `{}`. A corrupt one must not fail the unit every tick:
    `{}` means "nothing is due", which is the harmless reading."""
    try:
        state = json.loads(state_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def save_state(state: dict, env=os.environ) -> None:
    path = state_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def _when(text) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(text) if text else None
    except (TypeError, ValueError):
        return None


def _iso(t: datetime.datetime | None) -> str:
    return t.isoformat(timespec="seconds") if t else ""


def _clock(text) -> str:
    t = text if isinstance(text, datetime.datetime) else _when(text)
    return t.astimezone().strftime("%a %H:%M") if t else "?"


def read_budget(fresh: bool = False, env=None) -> Budget:
    """The probe's two windows. Imported late: `schedule.sessions` imports this module."""
    from schedule import conditions, sessions                       # noqa: PLC0415
    ctx = conditions.Context(sessions.load_policy(), env=dict(env if env is not None else os.environ))
    w = conditions.read_budget(ctx, fresh=fresh).windows
    five, weekly = w.get("five_hour") or (None, None), w.get("weekly") or (None, None)
    return Budget(five[0], five[1], weekly[0], weekly[1])


def decide(now: datetime.datetime, b: Budget) -> Decision:
    """What a due tick does, from the windows alone. The weekly window comes first:
    while it is spent no call works, and the 5-hour window cannot be opened early.

    An end further ahead than the window's own length cannot be real (`FIVE_SPAN`),
    so it is dropped rather than waited for, and `note` carries that to the log: a
    bad reading must not be able to stop the keeper without a trace."""
    note = ""
    five_ends, weekly_ends = b.five_ends, b.weekly_ends
    if weekly_ends and weekly_ends - now > WEEKLY_SPAN + SPAN_SLACK:
        note = f"the weekly reset reads {_clock(weekly_ends)}, past a week: ignored"
        weekly_ends = None
    if five_ends and five_ends - now > FIVE_SPAN + SPAN_SLACK:
        note += ("; " if note else "") + f"the 5-hour end reads {_clock(five_ends)}, past 5 h: ignored"
        five_ends = None
    if b.weekly is not None and b.weekly >= WEEKLY_SPENT and weekly_ends and weekly_ends > now:
        return Decision("weekly", weekly_ends + MARGIN, note)
    if five_ends and five_ends > now:
        return Decision("open", five_ends + MARGIN, note)
    return Decision("ping", None, note)


def backoff(streak: int) -> datetime.timedelta:
    return datetime.timedelta(minutes=BACKOFF[min(max(streak, 1), len(BACKOFF)) - 1])


def run_ping(model_id: str, pi_model: str, *, spawn=None,
             timeout: float = TIMEOUT, env=None) -> dict:
    """One minimal call. `spawn` is `pi_call.spawn`'s seam, which a test replaces;
    `None` is the module itself, looked up at call time.

    `open` is three-valued: True (answered), False (the window turned the call away:
    the output names a rate limit) and None (UNKNOWN -- a hang, a network error, any
    other failure). A timeout used to be recorded as a closed window (2026-10-24
    22:41), which it cannot be told from; the partial output is kept now."""
    prompt = pathlib.Path(tempfile.mkdtemp(prefix="ping-")) / "system.md"
    prompt.write_text(SYSTEM, encoding="utf-8")
    argv = pi_call.argv(PING, approve=False, session=None, model=pi_model,
                        system_prompt=prompt, bare=True)
    started = datetime.datetime.now(datetime.timezone.utc)
    try:
        r = (spawn or pi_call.spawn)(argv, timeout=timeout, env=pi_call.env_for(env))
        out = (r.stdout + r.stderr).strip()
        if r.timed_out:
            out, state = f"timeout after {timeout:g}s" + (f": {out[-200:]}" if out else ""), None
        elif r.returncode == 0:
            state = True
        else:
            state = False if REFUSED.search(out) or RESET.search(out) else None
    finally:
        prompt.unlink(missing_ok=True)
        shutil.rmtree(prompt.parent, ignore_errors=True)
    reset = RESET.search(out)
    limit = LIMIT.search(out)
    return {
        "ts": started.isoformat(timespec="seconds"),
        "seconds": round((datetime.datetime.now(datetime.timezone.utc) - started).total_seconds(), 1),
        "model": model_id,
        "pi_model": pi_model,
        "open": state,
        "limit": limit.group(1) if limit else "",
        "reset": " ".join(reset.group(1).split()) if reset else "",
        "chars": len(out),
        "say": out.splitlines()[-1][:120] if out else "",
    }


def line(row: dict) -> str:
    """One line per DECISION, for the journal and `--last`. `open` is three-valued,
    so a hang is never printed as a closed window (the 22:41 defect of 2026-10-24)."""
    event = row.get("event", "ping")
    nxt = f"next check {_clock(row.get('next_check', ''))}"
    if event == "unknown":
        return (f"ping: result unknown ({row.get('why', '')}) -- retry {_clock(row.get('next_check', ''))}"
                f", {row.get('streak', 1)} in a row")
    if event == "open":
        text = f"ping: a window is already open until {_clock(row.get('five_hour_resets', ''))} -- {nxt}"
    elif event == "weekly":
        text = f"ping: the weekly limit is spent, resets {_clock(row.get('weekly_resets', ''))} -- {nxt}"
    elif row.get("open") is None:
        # The call hung or failed in a way it cannot name. The probe may still have
        # seen a window open -- say that, rather than call it CLOSED.
        text = (f"ping: result unknown ({row.get('say', '')})"
                + (f", a window is open until {_clock(row['five_hour_resets'])}"
                   if row.get("five_hour_resets") else "")
                + f" -- {nxt}")
    elif row["open"]:
        text = (f"ping: {row['model']} answered -- the window is open "
                f"({row['seconds']:g}s, {row['chars']} chars back)"
                + (f", ends {_clock(row['five_hour_resets'])}, {nxt}" if row.get("five_hour_resets") else ""))
    else:
        text = (f"ping: the window is CLOSED"
                + (f", resets {row['reset']}" if row.get("reset") else "")
                + (f" [{row['limit']}]" if row.get("limit") else "")
                + f" ({row['say']})" + (f" -- {nxt}" if row.get("next_check") else ""))
    return text + (f" [{row['why']}]" if row.get("why") else "")


def _unknown(now, state: dict, why: str, row: dict | None = None) -> tuple[dict, dict]:
    streak = int(state.get("streak") or 0) + 1
    due = now + backoff(streak)
    row = dict(row or {"ts": _iso(now.astimezone(datetime.timezone.utc))})
    row.update(event="unknown", why=why[:120], streak=streak, next_check=_iso(due))
    return row, {"next_check": _iso(due), "streak": streak}


def tick(now: datetime.datetime, state: dict, *, probe, call, force: bool = False):
    """One timer tick -> `(row | None, new state)`. `probe(fresh)` returns a `Budget`;
    `call()` makes the ping and returns `run_ping`'s row. Both are seams.

    No row and an unchanged state while `next_check` is ahead: that is every tick but
    one or two per window, and it must not touch the network."""
    due = _when(state.get("next_check"))
    if due and now < due and not force:
        return None, state
    try:
        b = probe(False)
    except Exception as e:                                  # noqa: BLE001 -- the probe may fail any way
        return _unknown(now, state, f"usage probe: {e}")
    d = decide(now, b)
    stamp = {"ts": _iso(now.astimezone(datetime.timezone.utc)),
             "five_hour_resets": _iso(b.five_ends), "weekly_resets": _iso(b.weekly_ends)}
    if d.event != "ping":
        row = dict(stamp, event=d.event, next_check=_iso(d.due))
        if d.note:
            row["why"] = d.note
        return row, {"next_check": _iso(d.due), "streak": 0}
    row = call()
    row["event"] = "ping"
    try:
        after = probe(True)                                 # when does the window it opened end?
    except Exception as e:                                  # noqa: BLE001
        return _unknown(now, state, f"usage probe after the ping: {e}", row)
    row.update(five_hour_resets=_iso(after.five_ends), weekly_resets=_iso(after.weekly_ends))
    nxt = decide(now, after)
    if nxt.event == "ping":                                 # still no window, and the weekly is not spent
        why = "answered, but the probe shows no window" if row["open"] else row["say"]
        return _unknown(now, state, why + (f"; {nxt.note}" if nxt.note else ""), row)
    # Whatever the call said, the PROBE now names an end to wait for -- a hang that
    # opened the window, or a refusal by a window that is simply running, both land here.
    row["next_check"] = _iso(nxt.due)
    if nxt.note:
        row["why"] = nxt.note
    return row, {"next_check": _iso(nxt.due), "streak": 0}


def audit(rows: list[dict], since: datetime.datetime) -> list[dict]:
    """Every ping since `since`, with its lag behind the window end it waited for.
    The end is `next_check - MARGIN` of the last decision that set one for a window
    (`open`, `weekly`, or a ping that learned its own window's end); an `unknown`
    row sets none, so a retry is measured from the end it is late for."""
    out, end = [], None
    for r in rows:
        ts = _when(r.get("ts"))
        event = r.get("event", "ping")
        if event == "ping" and ts and ts >= since:
            lag = (ts - end).total_seconds() / 60 if end else None
            out.append({"ts": r["ts"], "lag": lag, "open": r.get("open"),
                        "ok": lag is not None and 0 <= lag <= LAG_OK})
        due = _when(r.get("next_check"))
        if due and (event in ("open", "weekly") or (event == "ping" and r.get("open"))):
            end = due - MARGIN
    return out


def serve(model_id: str, profile: str, env=os.environ, cfg: dict | None = None) -> profiles.Resolution:
    """Does the profile serve the model? WITHOUT the quota gate (15a): that gate
    answers "has this account room" with the fuller of the two windows at 0.98, and
    refused the 00:56 ping of 2026-10-25 with exit 2. Here the question is this
    module's, and answered per window (`decide`); only a missing key or login blocks."""
    return profiles.resolve(model_id, profile, env, cfg=cfg, window=None)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration ping",
                                 description="Open a Claude window on purpose. The timer ticks every "
                                             "5 min; a tick reads the state and acts only when the "
                                             "last window's end (+2 min) has passed.")
    ap.add_argument("--print", dest="just_print", action="store_true",
                    help="what would run and when the state says it is next due, without calling")
    ap.add_argument("--last", type=int, default=0, metavar="N",
                    help="print the last N log lines instead of pinging")
    ap.add_argument("--audit", nargs="?", type=float, const=24.0, metavar="HOURS",
                    help=f"every ping of the last HOURS (24) with its lag behind the window end it "
                         f"followed; late is more than {LAG_OK} min")
    ap.add_argument("--force", action="store_true",
                    help="act now even though the state says nothing is due yet")
    args = ap.parse_args(argv)
    try:
        if args.last or args.audit is not None:
            path = log_path()
            if not path.is_file():
                print(f"ping: no log at {path}")
                return 0
            rows, broken = [], 0
            for raw in path.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(raw))
                except ValueError:
                    broken += 1      # a half-written line must not blind the audit
            if args.audit is None:
                for r in rows[-args.last:]:
                    print(line(r))
                return 0
            since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=args.audit)
            got = audit(rows, since)
            for a in got:
                lag = "-" if a["lag"] is None else f"{a['lag']:+.0f} min"
                verdict = "answered" if a["open"] else "unknown" if a["open"] is None else "refused"
                print(f"{_clock(a['ts'])}  {verdict:<8}  lag {lag:>8}  "
                      f"{'ok' if a['ok'] else 'LATE' if a['lag'] is not None else 'no end on record'}")
            on = sum(1 for a in got if a["ok"])
            print(f"audit: {len(got)} ping(s) in {args.audit:g} h, {on} within {LAG_OK} min of a window end"
                  + (f", {broken} unreadable line(s) skipped" if broken else ""))
            return 0
        state = load_state()
        now = datetime.datetime.now().astimezone()
        due = _when(state.get("next_check"))
        if not args.just_print and not args.force and due and now < due:
            return 0                                        # the common tick: no catalogue, no network
        cat = models.load()
        model_id = cheapest_claude(cat)
        profile = profiles.active()
        res = serve(model_id, profile)
        if not res.available:
            print(f"ping: {model_id} unavailable in profile {profile}: {res.reason}",
                  file=sys.stderr)
            return 2
        if args.just_print:
            print(f"ping: would call {model_id} as {res.provider}/{res.model} "
                  f"({PING!r}, {len(SYSTEM)}-byte system prompt, --no-session); "
                  f"next check {_clock(state.get('next_check', '')) if due else 'now'}, "
                  f"unknown streak {state.get('streak', 0)}")
            return 0
        row, new = tick(now, state, probe=lambda fresh: read_budget(fresh),
                        call=lambda: run_ping(model_id, f"{res.provider}/{res.model}"),
                        force=args.force)
        if row is None:
            return 0
        record(row)
        save_state(new)
        print(line(row))
        return 1 if int(new.get("streak") or 0) == ALERT_AFTER else 0     # once, not every retry after
    except (_miniyaml.YamlError, profiles.ProfileError, OSError) as e:
        print(f"ping: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
