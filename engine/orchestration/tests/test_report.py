"""report (12b): one screen for 5d -- the window's numbers, its three floors, its
gate -- read from the two logs a session leaves.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  the sources    The turns come from the transcripts and the sizes come from the
                 delegation log, so a fixture where the two DISAGREE shows which
                 number came from where. Nothing here re-counts the trigger: the
                 fires are the splitter's.
  the attribution A delegation line belongs to the window by its `parent` (12a),
                 and by its date only when it has none -- the 17 lines written
                 before the parent field must not be counted twice or lost.
  unmeasured     A floor with no data FAILS and prints `--`. An uptake of `null`
                 is not an uptake of one, and a report that passes on no data is
                 the failure mode a verdict cannot survive.
  the ratios     Compression is a median, so one huge turn cannot decide it.
  the arms       The post-fire floor is 14a's randomised estimate: only fires
                 that carry an arm, on or after `arms_since`, enter it; it FAILS
                 below `MIN_ARM` per arm or under `MIN_GAP` of uptake gap, and
                 its value is the Wald (LATE) ratio on log bytes.
  the regression `--check` exits 1 only for a floor that PASSED last run, so the
                 healthcheck can carry it: a floor that is simply still failing is
                 5d's open question, not a regression.

No test reads the real sessions root or the real delegation log: both are handed
to `scan`.
"""
import json
import pathlib

import pytest

from orchestration import log as L

KB = 1024
PARENT = "2026-10-20T10-00-00-000Z_aaa.jsonl"


# --- synthetic logs ---------------------------------------------------------

def user():
    return {"type": "message", "message": {"role": "user", "content": [
        {"type": "text", "text": "go"}]}}


def calls(*pairs):
    return {"type": "message", "message": {"role": "assistant", "content": [
        {"type": "toolCall", "name": name, "arguments": arguments}
        for name, arguments in pairs]}}


def out(text):
    return {"type": "message", "message": {
        "role": "toolResult", "toolName": "read",
        "content": [{"type": "text", "text": text}]}}


def nudge():
    return {"type": "custom_message", "customType": "explore-trigger",
            "content": "delegate this", "display": True, "details": {}}


def withheld():
    return {"type": "custom", "customType": "explore-trigger-withheld",
            "data": {"files": 6, "bytes": 90 * KB, "withhold": 0.33}}


def firing_turn(after_kb, delegated=False, hinted=False, held=False):
    """One turn that fires: six files and 90 KB, then `after_kb` KB more."""
    rows = [user(), calls(*[("read", {"path": f"f{i}.py"}) for i in range(6)]),
            out("x" * (90 * KB))]
    if hinted:
        rows.append(nudge())
    if held:
        rows.append(withheld())
    if delegated:
        rows.append(calls(("bash", {"command": 'pi-agent explore "find it"'})))
    rows.append(out("y" * (after_kb * KB)))
    return rows


def session(root, name, entries):
    path = pathlib.Path(root) / "--home-rg--" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    return path


def delegation(parent, used, compression="10", returned=1000):
    return {"ts": "2026-10-20T11:00:00+00:00", "role": "explore",
            "model": "deepseek/deepseek-flash", "profile": "private", "effort": "low",
            "session": f"/sessions/pi-agent/{parent}-child.jsonl", "exit": 0,
            "usage": {"input": 1000, "output": 200, "cache_write": 0, "cache_read": 0,
                      "frontier": 1200},
            "bytes_read": int(returned * float(compression)),
            "bytes_returned": returned, "compression": float(compression),
            "parent": parent, "used": used}


@pytest.fixture
def window(tmp_path):
    """Two firing turns -- one delegated, one plain, with a 130 KB against 490 KB
    of tool output at or after the fire -- and three delegation lines: used,
    unused, and one from the days before the parent field.

    The crossing result counts as post-fire output (the parent has already paid
    for it), so a turn's `bytes_after` is 90 KB + what the turn read afterwards.
    """
    root = tmp_path / "sessions"
    a = session(root, PARENT, firing_turn(400, delegated=False, hinted=True))
    b = session(root, "2026-10-21T10-00-00-000Z_bbb.jsonl",
                firing_turn(40, delegated=True, hinted=True))
    data = tmp_path / "delegations.jsonl"
    data.write_text("".join(json.dumps(r) + "\n" for r in [
        delegation(str(a), True, compression="10"),
        delegation(str(b), False, compression="4"),
        dict(delegation("", None, compression="20"), parent=None,
             ts="2026-10-16T09:00:00+00:00"),
    ]), encoding="utf-8")
    return root, data


# --- the numbers ------------------------------------------------------------

def test_report_reads_turns_from_the_transcripts_and_sizes_from_the_log(window):
    root, data = window
    w = L.scan("2026-10-15", root, data)
    m = w.metrics()
    assert (m["sessions"], m["turns"], m["fires"]) == (2, 2, 2)
    assert (m["nudges"], m["acted"]) == (2, 1), "one hint was answered, one was not"
    assert m["delegations"] == 3
    assert m["delegated_read"] == 10000 + 4000 + 20000
    assert m["tool_bytes"] == (90 + 400 + 90 + 40) * KB  # both turns, crossing result included
    floors = {f["floor"]: f for f in m["floors"]}
    assert floors["median compression >= 5x"]["value"] == 10, "the median of 4, 10, 20"
    assert floors["uptake >= 50%"]["value"] == 0.5 and floors["uptake >= 50%"]["ok"]
    assert floors[L.FLOOR_BYTES_NAME]["ok"] is False, "fires before 14a carry no arm"
    assert floors[L.FLOOR_BYTES_NAME]["value"] is None
    assert m["usd"] > 0, "the catalogue prices the model the log names"
    assert m["gate"] == {"fires": 2, "sessions": 2, "fires_needed": 28,
                         "sessions_needed": 58, "open": False}


def test_report_attributes_a_line_by_its_parent_and_otherwise_by_its_date(tmp_path):
    root = tmp_path / "sessions"
    inside = session(root, PARENT, firing_turn(10))
    data = tmp_path / "delegations.jsonl"
    outside = "/sessions/--elsewhere--/2026-10-19T00-00-00-000Z_ccc.jsonl"
    data.write_text("".join(json.dumps(r) + "\n" for r in [
        delegation(str(inside), True),
        delegation(outside, True),                                   # another session
        dict(delegation("", True), parent=None, ts="2026-10-16T00:00:00+00:00"),
        dict(delegation("", True), parent=None, ts="2026-10-01T00:00:00+00:00"),
    ]), encoding="utf-8")
    rows = L.window_rows([inside], "2026-10-15", data)
    assert [r["session"] for r in rows] == [
        f"/sessions/pi-agent/{inside}-child.jsonl",           # parent names the window
        "/sessions/pi-agent/-child.jsonl",                    # no parent, date inside
    ]


def test_report_fails_a_floor_it_cannot_measure(tmp_path):
    root = tmp_path / "sessions"
    session(root, PARENT, [user(), calls(("read", {"path": "a.py"})), out("small")])
    data = tmp_path / "delegations.jsonl"
    m = L.scan("2026-10-15", root, data).metrics()
    floors = {f["floor"]: f for f in m["floors"]}
    assert all(f["ok"] is False for f in m["floors"]), "nothing measured is not a pass"
    assert floors["uptake >= 50%"]["shown"] == "--"
    assert m["delegations"] == 0 and m["usd"] == 0


def test_report_a_zero_compression_is_a_measurement(tmp_path):
    root = tmp_path / "sessions"
    a = session(root, PARENT, firing_turn(10))
    data = tmp_path / "delegations.jsonl"
    data.write_text(json.dumps(delegation(str(a), True, compression="0",
                                          returned=10)) + "\n", encoding="utf-8")
    floors = {f["floor"]: f for f in L.scan("2026-10-15", root, data).metrics()["floors"]}
    assert floors["median compression >= 5x"]["value"] == 0
    assert floors["median compression >= 5x"]["ok"] is False


# --- the screen and the check ----------------------------------------------

def test_report_prints_the_six_numbers_the_floors_and_the_gate(window, capsys):
    root, data = window
    assert L.report_main(["--since", "2026-10-15", "--sessions", str(root),
                          "--path", str(data)]) == 0
    printed = capsys.readouterr().out
    assert "nudges    2 sent, 1 acted on in the same turn" in printed
    assert "median compression >= 5x" in printed and "PASS" in printed
    assert "gate      2/30 fires, 2/60 sessions: waiting on 28 more fire(s)" in printed


def test_report_check_exits_1_only_when_a_floor_regresses(window, capsys):
    root, data = window
    argv = ["--since", "2026-10-15", "--sessions", str(root), "--path", str(data)]
    assert L.report_main(argv + ["--check"]) == 0, "no previous run: not a regression"
    before = json.loads(L.state_path().read_text())
    assert [f["ok"] for f in before["floors"]] == [True, True, False]
    capsys.readouterr()
    # The window loses its delegations: every floor that passed now fails.
    pathlib.Path(data).write_text("", encoding="utf-8")
    assert L.report_main(argv + ["--check"]) == 1
    assert "REGRESSED uptake >= 50%" in capsys.readouterr().out


def test_report_check_does_not_call_a_standing_failure_a_regression(tmp_path, capsys):
    root = tmp_path / "sessions"
    session(root, PARENT, firing_turn(10))
    data = tmp_path / "delegations.jsonl"
    data.write_text("", encoding="utf-8")
    argv = ["--since", "2026-10-15", "--sessions", str(root), "--path", str(data)]
    assert L.report_main(argv + ["--check"]) == 0
    assert L.report_main(argv + ["--check"]) == 0, "still failing, not a new regression"
    assert "REGRESSED" not in capsys.readouterr().out


def test_report_json_carries_the_same_counts(window, capsys):
    root, data = window
    assert L.report_main(["--since", "2026-10-15", "--sessions", str(root),
                          "--path", str(data), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fires"] == 2 and payload["delegations"] == 3
    assert [f["floor"] for f in payload["floors"]] == [
        "uptake >= 50%", "median compression >= 5x", L.FLOOR_BYTES_NAME]
    assert payload["arm_gate"]["since"] == L.ARMS_START
    assert payload["regressed"] == []


# --- 14a: the randomised floor ----------------------------------------------

def arm_sessions(root, nudged, held, day="2026-10-23"):
    """One session per fire: `nudged` and `held` are lists of (after_kb, delegated)."""
    i = 0
    for arm, turns in (("n", nudged), ("w", held)):
        for after_kb, delegated in turns:
            i += 1
            session(root, f"{day}T10-00-{i:02d}-000Z_{arm}{i}.jsonl",
                    firing_turn(after_kb, delegated=delegated,
                                hinted=arm == "n", held=arm == "w"))


def test_report_floor_3_reads_only_fires_with_an_arm_since_14a(tmp_path):
    root = tmp_path / "sessions"
    session(root, PARENT, firing_turn(400, hinted=True))          # 2026-10-20: before 14a
    arm_sessions(root, [(10, True)] * 3, [(100, False)] * 2)
    w = L.scan("2026-10-15", root, tmp_path / "none.jsonl", arms_since="2026-10-22")
    assert w.fires == 6 and w.arm_fires == 5 and w.arm_sessions == 5
    r = w.randomised()
    assert (r["nudged"], r["withheld"]) == (3, 2)
    assert r["ratio"] is None and "needs 10 fires per arm" in r["why"]


def test_report_floor_3_is_the_wald_ratio_on_log_bytes(tmp_path):
    """Nudged: half delegate and read 10 KB after the hint, half do not and read
    490 KB. Withheld: nobody delegates and all read 490 KB. The LATE ratio is then
    the delegating turns' own (100 KB / 580 KB in log terms), not the ITT one."""
    import math
    root = tmp_path / "sessions"
    arm_sessions(root, [(10, True)] * 6 + [(400, False)] * 6, [(400, False)] * 10)
    w = L.scan("2026-10-15", root, tmp_path / "none.jsonl", arms_since="2026-10-22")
    r = w.randomised()
    assert r["gap"] == pytest.approx(0.5)
    a, b = math.log1p(100 * KB), math.log1p(490 * KB)
    assert r["itt"] == pytest.approx(math.exp((a + b) / 2 - b))
    assert r["ratio"] == pytest.approx(math.exp(a - b))
    floors = {f["floor"]: f for f in w.metrics()["floors"]}
    assert floors[L.FLOOR_BYTES_NAME]["ok"] is True
    assert "12 nudged / 10 withheld" in floors[L.FLOOR_BYTES_NAME]["note"]


def test_report_floor_3_fails_when_the_arm_moves_no_delegation(tmp_path):
    root = tmp_path / "sessions"
    arm_sessions(root, [(400, False)] * 10, [(400, False)] * 10)
    r = L.scan("2026-10-15", root, tmp_path / "none.jsonl", arms_since="2026-10-22").randomised()
    assert r["ratio"] is None and r["gap"] == 0 and "uptake gap" in r["why"]


def test_report_prints_floor_3_its_own_gate(window, capsys):
    root, data = window
    L.report_main(["--since", "2026-10-15", "--sessions", str(root), "--path", str(data)])
    printed = capsys.readouterr().out
    assert f"gate 3    0/{L.GATE_ARM_FIRES} fires, 0/60 sessions since {L.ARMS_START}" in printed


def test_report_holds_the_verdict_until_both_gates_open(window, capsys):
    root, data = window
    L.report_main(["--since", "2026-10-15", "--sessions", str(root), "--path", str(data)])
    assert "verdict   HELD" in capsys.readouterr().out
    L.report_main(["--since", "2026-10-15", "--sessions", str(root), "--path", str(data),
                   "--json"])
    assert json.loads(capsys.readouterr().out)["verdict_readable"] is False
