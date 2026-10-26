"""The window ping (item 8f's neighbour, 2026-10-14): one minimal Haiku call, its
argv as small as this system knows how to make it, and a log line either way."""
import json
import pathlib

import pytest

from orchestration import ping, profiles


from harness import pi_call


def Done(code=0, out=""):
    return pi_call.Result(code, out, "")


def test_ping_the_cheapest_claude_entry_is_the_one_it_calls():
    cat = {"models": [{"id": "claude-opus-5-5", "vendor": "anthropic", "kind": "chat",
                       "cost": {"in": "4", "out": "20"}},
                      {"id": "claude-haiku-5-5", "vendor": "anthropic", "kind": "chat",
                       "cost": {"in": "0.1", "out": "0.5"}},
                      {"id": "deepseek-flash", "vendor": "deepseek", "kind": "chat",
                       "cost": {"in": "0.3", "out": "1.2"}}]}
    assert ping.cheapest_claude(cat) == "claude-haiku-5-5"
    assert ping.cheapest_claude(ping.models.load()) == "claude-haiku-5-5", "the shipped catalogue"


def test_ping_the_call_is_as_small_as_this_system_can_make_it(monkeypatch):
    """`--system-prompt` replaces pi's own (the pi-agent measurement), `-nc`/`-ns`
    drop project context and the skills index, and `--no-session` leaves no
    transcript at all: a ping must not clutter what it protects."""
    seen = {}

    def spawn(argv, **kw):
        seen["argv"], seen["env"] = argv, kw.get("env") or {}
        return Done(0, "pong\n")

    row = ping.run_ping("claude-haiku-5-5", "claude-bridge/claude-haiku-5-5", spawn=spawn)
    argv = seen["argv"]
    assert argv[:3] == ["pi", "-p", "pong"]
    assert argv[argv.index("--system-prompt") + 1].endswith("system.md")
    for flag in ("-nc", "-ns", "--no-session", "--no-approve"):
        assert flag in argv
    assert argv[argv.index("--model") + 1] == "claude-bridge/claude-haiku-5-5"
    assert seen["env"]["NO_COLOR"] == "1", "the env is the module's"
    assert row["open"] is True and row["model"] == "claude-haiku-5-5"
    assert not pathlib.Path(argv[argv.index("--system-prompt") + 1]).exists(), \
        "the tiny prompt file is removed"


def test_ping_a_closed_window_is_information_not_a_failure():
    def spawn(argv, **kw):
        return Done(1, "Claude rate limit (five_hour) — resets 1:40:00 AM: "
                       "You've hit your session limit · resets 1:40am (Europe/Berlin)\n")
    row = ping.run_ping("claude-haiku-5-5", "claude-bridge/claude-haiku-5-5", spawn=spawn)
    assert row["open"] is False and row["reset"] == "1:40:00 AM"
    assert "the window is CLOSED, resets 1:40:00 AM" in ping.line(row)
    assert "answered" in ping.line({"open": True, "model": "m", "seconds": 1.0, "chars": 4})


def test_ping_a_timeout_is_unknown_not_closed():
    """2026-10-24 22:41: a 120 s hang was logged as `CLOSED`. A hang cannot be told
    from a refusal, so it is `None`, and what the child said before it hung is kept."""
    def spawn(argv, **kw):
        return pi_call.Result(pi_call.TIMED_OUT, "half a thought", "")
    row = ping.run_ping("claude-haiku-5-5", "x", spawn=spawn, timeout=0.001)
    assert row["open"] is None and row["say"].startswith("timeout after 0.001s: half a thought")


def test_ping_the_refusal_names_which_window_turned_it_away():
    def spawn(argv, **kw):
        return Done(1, "Claude quota exceeded — rate limit (seven_day) — resets 4:00:00 AM: "
                       "You've hit your weekly limit · resets 4am (Europe/Berlin)")
    row = ping.run_ping("claude-haiku-5-5", "x", spawn=spawn)
    assert row["open"] is False and row["limit"] == "seven_day" and row["reset"] == "4:00:00 AM"


def test_ping_an_unrecognised_failure_is_unknown():
    row = ping.run_ping("claude-haiku-5-5", "x", spawn=lambda argv, **kw: Done(1, "ECONNRESET"))
    assert row["open"] is None


def test_ping_the_log_is_one_json_line_per_run_and_last_reads_it(tmp_path, monkeypatch, capsys):
    """`run_ping` is the seam here, not `subprocess.run`: the default argument is
    bound at definition time, so patching the module attribute would make this a
    REAL call (learned the hard way, 2026-10-14)."""
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    row = {"ts": "t", "seconds": 1.0, "model": "claude-haiku-5-5",
           "pi_model": "claude-bridge/claude-haiku-5-5", "open": True,
           "reset": "", "chars": 4, "say": "pong"}
    monkeypatch.setattr(ping, "run_ping", lambda *a, **k: row)
    monkeypatch.setattr(ping, "read_budget", lambda fresh=False, env=None: ping.Budget(0.0, None, 0.1, None))
    monkeypatch.setattr(ping, "serve", lambda *a, **k: profiles.Resolution(
        "claude-haiku-5-5", "private", provider="claude-bridge", available=True))
    assert ping.main([]) == 0, "one unknown result is a retry, not an alarm"
    path = tmp_path / ping.APPROVALS
    assert path.is_file()
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["event"] == "unknown" and rows[0]["streak"] == 1
    assert ping.main(["--last", "1"]) == 0
    assert "result unknown" in capsys.readouterr().out
    assert ping.main(["--print"]) == 0
    assert "would call" in capsys.readouterr().out


def subprocess_module():
    import subprocess
    return subprocess


def test_ping_a_model_the_profile_cannot_serve_is_exit_2(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ping.profiles, "resolve",
                        lambda *a, **k: profiles.Resolution("claude-haiku-5-5", "p",
                                                            reason="no login file"))
    assert ping.main([]) == 2
    assert "unavailable" in capsys.readouterr().err


# ── 2026-10-25: the window is read, not predicted ─────────────────────────────
import datetime as dt

from orchestration.tests.test_profiles import _login, env as _env

UTC = dt.timezone.utc


def at(hh, mm=0, day=24):
    return dt.datetime(2026, 10, day, hh, mm, tzinfo=UTC)


def budget(five_end=None, weekly=0.1, weekly_end=None, five=0.0):
    return ping.Budget(five, five_end, weekly, weekly_end)


def answered(**kw):
    return {"ts": "t", "seconds": 1.0, "model": "claude-haiku-5-5", "open": True,
            "limit": "", "reset": "", "chars": 4, "say": "pong", **kw}


def test_the_gate_that_refused_the_00_56_ping_is_not_the_pings_gate(tmp_path, monkeypatch):
    """2026-10-25 00:56: `profiles.resolve` took the fuller of the two windows (weekly
    1.00) and refused at 0.98, so the ping exited 2 and fired OnFailure -- on a ping
    that was merely about to be turned away. `serve` is the same resolution without
    the quota gate: a missing key still blocks it, a spent window does not."""
    cfg = _login(tmp_path)
    e = _env(tmp_path)
    gated = profiles.resolve("claude-haiku-5-5", "private", e, cfg=cfg, window=1.0)
    assert not gated.available and "quota window is spent" in gated.reason, "the gate exists"
    monkeypatch.setattr(profiles, "_window", lambda *a, **k: 1.0)
    got = ping.serve("claude-haiku-5-5", "private", e, cfg=cfg)
    assert got.available, "the ping is not gated by the fuller window"
    cfg["profiles"]["private"]["vendors"]["anthropic"]["login"] = str(tmp_path / "gone.json")
    assert not ping.serve("claude-haiku-5-5", "private", e, cfg=cfg).available


def test_a_corrupt_state_file_reads_as_nothing_is_due(tmp_path, monkeypatch):
    """A corrupt state file is read as "nothing is due", not as a traceback every
    five minutes: an uncaught exception would fail the unit and fire `OnFailure=`."""
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    (tmp_path / ping.STATE).write_text("[1, 2]", encoding="utf-8")
    assert ping.load_state() == {}


def test_a_probe_end_past_the_windows_own_length_is_ignored_not_waited_for():
    """A 5-hour window cannot end more than 5 h from now and the weekly one cannot
    reset more than a week ahead. A reading past that is a broken probe, and waiting
    for it would stop the keeper for days with nothing said -- the silent failure
    this module exists to end. It is dropped, and the row carries the reason."""
    now = at(9)
    five = ping.decide(now, budget(five_end=now + dt.timedelta(hours=6)))
    assert five.event == "ping" and "past 5 h" in five.note
    wk = ping.decide(now, budget(weekly=1.0, weekly_end=now + dt.timedelta(days=8)))
    assert wk.event == "ping" and "past a week" in wk.note
    ok = ping.decide(now, budget(five_end=now + dt.timedelta(hours=4, minutes=59)))
    assert ok.event == "open" and not ok.note, "a real end is believed"


def test_decide_reads_the_two_windows_separately():
    now = at(22, 40)
    assert ping.decide(now, budget(weekly=1.0, weekly_end=at(23, 0, 25))) == \
        ping.Decision("weekly", at(23, 0, 25) + ping.MARGIN), "weekly spent: wait for the weekly reset"
    assert ping.decide(now, budget(five_end=at(23, 30), five=1.0, weekly=0.2)) == \
        ping.Decision("open", at(23, 30) + ping.MARGIN), "a 5-hour window is running (spent or not)"
    assert ping.decide(now, budget(five_end=at(22, 0))).event == "ping", "its end is past"
    assert ping.decide(now, budget()).event == "ping", "the probe prints no end when none runs"
    assert ping.decide(now, budget(weekly=1.0, weekly_end=at(22, 0))).event == "ping", "a weekly end in the past"


def test_a_tick_before_next_check_makes_no_call_and_no_probe():
    state = {"next_check": at(23).isoformat(), "streak": 0}

    def boom(*a):
        raise AssertionError("the network was touched")
    row, new = ping.tick(at(22, 55), state, probe=boom, call=boom)
    assert row is None and new == state


def test_a_running_window_sets_next_check_to_its_end_plus_two_minutes():
    row, new = ping.tick(at(8, 7), {}, probe=lambda fresh: budget(five_end=at(9, 58)), call=lambda: 1 / 0)
    assert row["event"] == "open" and new["next_check"] == (at(9, 58) + ping.MARGIN).isoformat()
    assert "already open until" in ping.line(row)


def test_the_weekly_limit_waits_for_the_weekly_reset_not_for_five_hours():
    """12:36, 17:39, 22:41 and 00:56 on 2026-10-24/25 were four calls into a spent
    weekly window. One reading replaces them, and the retry is the reset (+2 min)."""
    wk = dt.datetime(2026, 10, 25, 2, 0, tzinfo=UTC)
    row, new = ping.tick(at(10, 36), {}, probe=lambda fresh: budget(weekly=1.0, weekly_end=wk),
                         call=lambda: 1 / 0)
    assert row["event"] == "weekly" and new["next_check"] == (wk + ping.MARGIN).isoformat()
    assert "weekly limit is spent" in ping.line(row)


def test_a_refusal_that_names_its_reset_retries_at_that_reset_not_a_cycle_later():
    """2026-10-20 22:07: five_hour, resets 00:10. The next ping was 03:10."""
    end = dt.datetime(2026, 10, 21, 0, 10, tzinfo=UTC)
    reading = iter([budget(), budget(five_end=end, five=1.0)])
    refused = answered(open=False, limit="five_hour", reset="12:10:00 AM", say="Claude rate limit")
    now = dt.datetime(2026, 10, 20, 22, 7, tzinfo=UTC)
    row, new = ping.tick(now, {}, probe=lambda fresh: next(reading), call=lambda: refused)
    assert row["open"] is False and new["next_check"] == "2026-10-21T00:12:00+00:00"
    assert new["streak"] == 0


def test_a_timeout_is_unknown_backs_off_and_the_fourth_in_a_row_is_an_alarm():
    hang = answered(open=None, say="timeout after 120s")
    state, now, waits = {}, at(22, 41), []
    for _ in range(5):
        row, state = ping.tick(now, state, probe=lambda fresh: budget(), call=lambda: dict(hang), force=True)
        assert row["event"] == "unknown"
        waits.append((dt.datetime.fromisoformat(state["next_check"]) - now).seconds // 60)
        now = dt.datetime.fromisoformat(state["next_check"])
    assert waits == [5, 10, 20, 30, 30]
    assert state["streak"] == 5 >= ping.ALERT_AFTER


def test_a_failed_probe_is_unknown_not_a_crash():
    def down(fresh):
        raise OSError("omarchy-agent-usage-claude exited 1")
    row, new = ping.tick(at(3), {}, probe=down, call=lambda: 1 / 0)
    assert row["event"] == "unknown" and "usage probe" in row["why"] and new["streak"] == 1


def test_a_success_clears_the_streak():
    row, new = ping.tick(at(3), {"streak": 3, "next_check": at(2).isoformat()},
                         probe=lambda fresh: budget(five_end=at(8)) if fresh else budget(),
                         call=lambda: answered())
    assert row["event"] == "ping" and new["streak"] == 0
    assert new["next_check"] == (at(8) + ping.MARGIN).isoformat()
    assert row["five_hour_resets"] == at(8).isoformat()


def test_a_timeout_the_probe_shows_an_open_window_for_is_not_printed_closed():
    """2026-10-24 22:41: a hang whose call had in fact opened the window was printed
    "CLOSED". `open` is None here, the probe names the end, and the line says so."""
    end = at(23, 59)
    reading = iter([budget(), budget(five_end=end)])
    row, new = ping.tick(at(22, 41), {}, probe=lambda fresh: next(reading),
                         call=lambda: answered(open=None, say="timeout after 120s: half a thought"))
    assert row["open"] is None and row["event"] == "ping"
    assert new["next_check"] == (end + ping.MARGIN).isoformat()
    got = ping.line(row)
    assert "CLOSED" not in got and "result unknown" in got and "a window is open until" in got


class World:
    """A five-hour window that opens on the first call after it closed -- by a ping or by
    the user -- and a clock that can skip (a suspended laptop). Just enough to replay a day."""
    def __init__(self):
        self.end = None
        self.pings = []

    def running(self, now):
        return self.end is not None and self.end > now

    def use(self, now):
        if not self.running(now):
            self.end = now + dt.timedelta(hours=5)

    def probe(self, now):
        return lambda fresh: budget(five_end=self.end if self.running(now) else None)

    def call(self, now):
        def ping_():
            self.pings.append(now)
            self.use(now)
            return answered()
        return ping_


def drive(world, times, uses=(), state=None):
    state = state or {}
    for now in times:
        if now in uses:
            world.use(now)
        _row, state = ping.tick(now, state, probe=world.probe(now), call=world.call(now))
    return state


def every5(start, end):
    t = start
    while t < end:
        yield t
        t += dt.timedelta(minutes=5)


def test_the_schedule_survives_a_suspend():
    """Eleven hours of suspend (no ticks at all), as on 2026-10-23/24, broke the
    monotonic interval. The window is read on the first tick awake: a ping on that
    very tick, then the cadence follows the new window's end."""
    w = World()
    drive(w, list(every5(at(0), at(6))) + list(every5(at(17), at(21))))
    assert w.pings == [at(0), at(5, 5), at(17)], "first tick; first tick past 05:00+2; first tick awake"


def test_a_use_by_hand_moves_the_next_ping_with_the_window():
    """The user opens the window at 22:05, off the ping's grid (the cause of the 09:58
    window left unreopened on 2026-10-25): the next ping follows THAT window's end."""
    w = World()
    drive(w, list(every5(at(17), at(22, 10))))                # a ping at 17:00 -> window to 22:00
    assert w.pings == [at(17), at(22, 5)], "22:00 passes; the first tick after 22:02 pings"
    w2 = World()
    w2.use(at(22, 5))                                         # by hand, before any tick
    drive(w2, list(every5(at(22, 5), at(23, 55))) + list(every5(at(3, 0, 25), at(4, 0, 25))))
    assert w2.pings == [at(3, 10, 25)], "the window ends 03:05, due 03:07, first tick 03:10"


def test_audit_reports_the_lag_behind_the_window_end_it_followed():
    rows = [
        {"ts": "2026-10-25T03:58:00+00:00", "event": "ping", "open": True, "next_check": "2026-10-25T08:00:00+00:00"},
        {"ts": "2026-10-25T08:05:00+00:00", "event": "ping", "open": True, "next_check": "2026-10-25T13:07:00+00:00"},
        {"ts": "2026-10-25T14:00:00+00:00", "event": "unknown", "next_check": "2026-10-25T14:05:00+00:00"},
        {"ts": "2026-10-25T14:05:00+00:00", "event": "ping", "open": True, "next_check": "2026-10-25T19:07:00+00:00"},
    ]
    got = ping.audit(rows, dt.datetime(2026, 10, 25, tzinfo=UTC))
    assert got[0]["lag"] is None and got[1]["lag"] == 7.0 and got[1]["ok"]
    assert got[2]["lag"] == 60.0 and not got[2]["ok"], "an unknown row sets no end: the retry is late for 13:05"


def test_the_audit_names_the_third_verdict_and_reads_past_a_broken_line(tmp_path, monkeypatch,
                                                                       capsys):
    """The instrument the 24 h verification reads: a half-written line must not blind
    it, and a ping whose call is unknown is neither answered nor refused."""
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path))
    ts = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    good = {"ts": ts.isoformat(timespec="seconds"), "event": "ping", "open": None,
            "next_check": (ts + dt.timedelta(hours=5)).isoformat(timespec="seconds")}
    (tmp_path / ping.APPROVALS).write_text(json.dumps(good) + "\n{\"ts\": \"2026", encoding="utf-8")
    assert ping.main(["--audit", "24"]) == 0
    out = capsys.readouterr().out
    assert "unknown" in out and "refused" not in out
    assert "1 unreadable line" in out
