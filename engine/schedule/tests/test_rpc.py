"""The RPC driver (R2a) against a fake pi on real pipes: every dialog becomes a relay
ask, the answer goes back, waiting does not count as work, and a failed model call
is a failed run."""
import datetime as dt
import io
import json
import sys
import textwrap
import threading
import time

import pytest

from schedule import rpc, sessions

# A fake `pi --mode rpc`: reads the prompt, then plays the SCENARIO named in argv[1].
FAKE_PI = textwrap.dedent(r'''
    import json, sys, time
    def out(o): sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()
    def read():
        line = sys.stdin.readline()
        return json.loads(line) if line else None
    scenario = sys.argv[1]
    prompt = read()
    out({"type": "response", "command": "prompt", "success": True})
    out({"type": "agent_start"})
    said = []
    if scenario in ("permission", "reason"):
        out({"type": "message_end", "message": {"role": "assistant",
             "content": [{"type": "text", "text": "I will push the branch now."}]}})
        out({"type": "extension_ui_request", "id": "u1", "method": "select",
             "title": "Permission Required\ntool : bash\nrule : rtk git push *",
             "options": ["Yes", "Yes, allow bash \"rtk *\" for this session", "No",
                         "No, provide reason"]})
        said.append(read())
        if said[-1].get("value") == "No, provide reason":
            out({"type": "extension_ui_request", "id": "u2", "method": "input",
                 "title": "Reason"})
            said.append(read())
    if scenario == "explain":
        out({"type": "extension_ui_request", "id": "w0", "method": "setWidget",
             "widgetKey": "pi-explain",
             "widgetLines": ["agent : I will push the branch now.",
                             "independent : reading…"]})
        time.sleep(0.3)                    # the annotator's placeholder arrives first
        out({"type": "extension_ui_request", "id": "u1", "method": "select",
             "title": "Permission Required\ntool : bash\nrule : rtk git push *",
             "options": ["Yes", "No"]})
        time.sleep(0.3)                    # the ask is open on the phone now
        out({"type": "extension_ui_request", "id": "w1", "method": "setWidget",
             "widgetKey": "pi-explain",
             "widgetLines": ["agent : I will push the branch now.",
                             "independent : Pushes the branch to origin."]})
        said.append(read())
        out({"type": "extension_ui_request", "id": "w2", "method": "setWidget",
             "widgetKey": "pi-explain"})
    if scenario == "confirm":
        out({"type": "extension_ui_request", "id": "c1", "method": "confirm",
             "title": "Clear?", "message": "All lost."})
        said.append(read())
    if scenario == "hang":                 # busy until stdin closes (the driver's abort)
        while read() is not None:
            pass
        sys.exit(0)
    if scenario == "denied":
        out({"type": "message_end", "message": {"role": "assistant", "content": [],
             "stopReason": "error",
             "errorMessage": "Claude rate limit (five_hour) -- resets 7pm"}})
    out({"type": "message_end", "message": {"role": "assistant",
         "content": [{"type": "text", "text": "answers: " + json.dumps(said)}]}})
    out({"type": "agent_settled", "aborted": False})
    while read() is not None:
        pass
''')


@pytest.fixture
def fake_pi(tmp_path):
    path = tmp_path / "fake_pi.py"
    path.write_text(FAKE_PI)
    return lambda scenario: [sys.executable, "-I", str(path), scenario]


class Relay:
    """The relay's `ask` seam: scripted answers, every request kept.

    `release` makes the ask wait, the way a real one waits for the owner: the
    annotator's mid-ask edit can then be observed before the answer lands.
    """

    def __init__(self, *answers, down=0, release=None):
        self.answers, self.down, self.asked = list(answers), down, []
        self.release = release

    def __call__(self, req, on_retry=lambda e: None):
        for _ in range(self.down):
            on_retry(ConnectionError("relay not running"))
        self.asked.append(req)
        if self.release is not None:
            assert self.release.wait(20), "the test never released the ask"
        return self.answers.pop(0)


def drive(fake_pi, scenario, relay, *, timeout_s=60, tmp_path=None, annotate=None):
    log, events = io.StringIO(), []
    kw = {"annotate": annotate} if annotate else {}
    result = rpc.drive(fake_pi(scenario), "do the work", cwd=str(tmp_path), log=log,
                       session="chain", run_id="20261020T190000", asked="asked: item 1a",
                       write_event=events.append, ask=relay, timeout_s=timeout_s, **kw)
    return result, events, log.getvalue()


def test_the_annotator_s_lines_ride_along_with_the_ask_and_later_edits_follow(fake_pi, tmp_path):
    updates, release = [], threading.Event()

    def annotate(ask_id, lines):
        updates.append((ask_id, lines))
        release.set()                    # the answer lands only after the edit
        return True

    relay = Relay({"value": "Yes", "by": "telegram"}, release=release)
    result, events, log = drive(fake_pi, "explain", relay, tmp_path=tmp_path, annotate=annotate)
    assert result["exit"] == 0 and result["asks"] == 1
    (req,) = relay.asked
    assert req["lines"] == ["agent : I will push the branch now.", "independent : reading…"], \
        "the lines held before the dialog open travel with the ask"
    assert "[explain]" in log, "the run log says what the ask carried"
    assert [u[0] for u in updates] == ["chain/20261020T190000/u1"]
    assert updates[0][1][1].startswith("independent : Pushes"), \
        "the finished pair edits the message the owner is reading"
    assert "[explain] []" in log, "the clear is seen too"
    assert len(updates) == 1, "an ask that is already answered is not annotated"


def test_a_widget_from_another_extension_is_left_alone(tmp_path):
    log = io.StringIO()
    calls = []
    run = rpc.Run(["pi"], "p", cwd=str(tmp_path), log=log, session="s", run_id="r",
                  write_event=lambda row: None, annotate=lambda aid, ln: calls.append((aid, ln)))
    run._widget({"method": "setWidget", "widgetKey": "someone-else", "widgetLines": ["x"]})
    assert run.lines == [] and calls == [] and "[explain]" not in log.getvalue()
    run._widget({"method": "setWidget", "widgetKey": "pi-explain:perm-1",
                 "widgetLines": ["agent : a", "independent : b"]})
    assert run.lines == ["agent : a", "independent : b"]
    run.open_ask_id = "s/r/u1"
    run._widget({"method": "setWidget", "widgetKey": "pi-explain", "widgetLines": ["agent : c"]})
    deadline = time.time() + 5
    while time.time() < deadline and not calls:
        time.sleep(0.02)
    assert calls == [("s/r/u1", ["agent : c"])]
    run._widget({"method": "setWidget", "widgetKey": "pi-explain"})   # pi's clear
    assert run.lines == []


def test_a_permission_ask_reaches_the_relay_and_its_answer_reaches_pi(fake_pi, tmp_path):
    relay = Relay({"value": "Yes", "by": "telegram", "waited_s": 3.0})
    result, events, log = drive(fake_pi, "permission", relay, tmp_path=tmp_path)
    assert result["exit"] == 0 and result["settled"] and result["asks"] == 1
    (req,) = relay.asked
    assert req["id"] == "chain/20261020T190000/u1" and req["kind"] == "select"
    assert "rtk git push *" in req["title"] and req["options"][0] == "Yes"
    assert "I will push the branch now." in req["context"], "More shows the agent's last text"
    assert "item 1a" in req["context"]
    assert 'answers: [{"type": "extension_ui_response", "id": "u1", "value": "Yes"}]' in log
    assert [e["event"] for e in events] == ["ask", "answer"]
    assert events[1]["value"] == "Yes" and events[1]["waited_s"] == 3.0


def test_a_worded_reply_picks_provide_reason_and_answers_the_reason_input(fake_pi, tmp_path):
    relay = Relay({"value": None, "text": "push to the fork, not origin", "by": "telegram"})
    result, events, log = drive(fake_pi, "reason", relay, tmp_path=tmp_path)
    assert result["exit"] == 0 and len(relay.asked) == 1, "the reason is not asked twice"
    assert '"value": "No, provide reason"' in log
    assert '"id": "u2", "value": "push to the fork, not origin"' in log
    assert events[-1]["by"] == "worded reply"


def test_a_cancel_and_a_confirm_map_to_pi_s_shapes(fake_pi, tmp_path):
    _, _, log = drive(fake_pi, "permission", Relay({"cancelled": True, "withdrawn": "x"}),
                      tmp_path=tmp_path)
    assert '"id": "u1", "cancelled": true' in log
    relay = Relay({"confirmed": False})
    _, _, log = drive(fake_pi, "confirm", relay, tmp_path=tmp_path)
    assert relay.asked[0]["kind"] == "confirm" and "All lost." in relay.asked[0]["title"]
    assert '"id": "c1", "confirmed": false' in log


def test_a_relay_that_is_down_is_recorded_once_and_waited_for(fake_pi, tmp_path):
    relay = Relay({"value": "No"}, down=3)
    result, events, log = drive(fake_pi, "permission", relay, tmp_path=tmp_path)
    assert result["exit"] == 0
    assert [e["event"] for e in events] == ["ask", "relay_down", "answer"]
    assert log.count("[relay] not reachable") == 1


def test_waiting_for_the_owner_does_not_count_against_the_timeout(fake_pi, tmp_path):
    import time

    class Slow(Relay):
        def __call__(self, req, on_retry=lambda e: None):
            time.sleep(2.5)
            return {"value": "Yes"}
    result, _, _ = drive(fake_pi, "permission", Slow(), timeout_s=2, tmp_path=tmp_path)
    assert result["exit"] == 0 and not result["timed_out"] and result["waited_s"] >= 2.4


def test_work_past_the_timeout_aborts_the_run(fake_pi, tmp_path):
    result, _, log = drive(fake_pi, "hang", Relay(), timeout_s=1, tmp_path=tmp_path)
    assert result["exit"] == 124 and result["timed_out"]
    assert "timeout after 1s of work" in log


def test_a_refused_window_is_a_failed_run_whose_log_names_it(fake_pi, tmp_path):
    result, _, log = drive(fake_pi, "denied", Relay(), tmp_path=tmp_path)
    assert result["exit"] == 1 and "five_hour" in result["error"]
    assert any(sessions.DENIED.search(line) for line in log.splitlines())


def test_a_run_with_an_open_ask_lists_as_waiting_and_its_wait_is_not_age():
    now = dt.datetime(2026, 10, 21, 8, 0, tzinfo=dt.timezone.utc)
    start = (now - dt.timedelta(hours=20)).isoformat()
    decl = {"kind": "once", "due": start, "timeout": "12h"}
    events = [{"event": "started", "ts": start},
              {"event": "ask", "ask": "a/1/u1", "ts": start}]
    assert sessions._state(decl, events, now)["state"] == "waiting"
    events.append({"event": "answer", "ask": "a/1/u1", "waited_s": 19 * 3600})
    assert sessions._state(decl, events, now)["state"] == "running", \
        "19 h of waiting is not 20 h of work"
