"""The decision log (item 8e): the pi extension writes one line per permission
decision, and the ask census reads that line before it greps a transcript."""
import json
import pathlib
import shutil
import subprocess

import pytest

from orchestration import asks

EXT = pathlib.Path(__file__).resolve().parents[2] / "boundaries/pi-emitter/index.ts"
SID = "019a1b2c-3d4e-7f00-8a9b-0c1d2e3f4a5b"
SLUG = "--home-rg-06_SYSTEM--"

# A stub pi: `on` keeps the session_start handler, `events.on` the bus handler;
# the script fires both the way pi and the permission system would.
DRIVER = """
const { default: factory, line, logPath, CHANNEL } = await import(process.argv[1]);
const hooks = {}, bus = {};
factory({ on: (n, f) => { hooks[n] = f; }, events: { on: (n, f) => { bus[n] = f; } } });
hooks.session_start({}, { sessionManager: { getSessionId: () => process.argv[2] } });
for (const e of JSON.parse(process.argv[3])) bus[CHANNEL](e);
console.log(JSON.stringify({ path: logPath(), pure: line({ result: "deny" }, null, new Date(0), {}) }));
"""


def drive(tmp_path, events, sid=SID, child=False):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PAZRAS_DATA_DIR": str(tmp_path / "data")}
    if child:
        env["PI_OFFLINE"] = "1"
    out = subprocess.run([node, "--input-type=module", "-e", DRIVER, str(EXT), sid, json.dumps(events)],
                         capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout), tmp_path / "data" / asks.DECISIONS_NAME


ASKED = {"requestId": "perm-1", "surface": "bash", "value": "env FOO=1 pytest -q",
         "result": "allow", "resolution": "user_approved", "origin": None,
         "agentName": None, "matchedPattern": "<indirection-bash-wrapper>"}
ALLOWED = {"requestId": "perm-2", "surface": "read", "value": "README.md",
           "result": "allow", "resolution": "policy_allow", "matchedPattern": "*"}
PUSH = {"requestId": "perm-3", "surface": "bash", "value": "git push origin x",
        "result": "deny", "resolution": "confirmation_unavailable", "matchedPattern": "git push *"}


def test_decision_log_one_line_per_decision_with_the_item_s_six_fields(tmp_path):
    info, log = drive(tmp_path, [ASKED, ALLOWED, PUSH])
    assert info["path"] == str(log)
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert len(lines) == 3, "every decision, policy_allow included: the census needs the denominator"
    first = lines[0]
    for key in ("ts", "surface", "value", "decision", "reason", "session"):
        assert key in first
    assert (first["surface"], first["decision"], first["reason"], first["session"]) == \
        ("bash", "allow", "user_approved", SID)
    assert first["rule"] == "<indirection-bash-wrapper>" and first["child"] is False
    assert info["pure"]["decision"] == "deny" and info["pure"]["surface"] is None, \
        "a missing field is null, never guessed"


def test_decision_log_cuts_a_long_value_and_says_how_long_it_was(tmp_path):
    long = dict(ASKED, value="x" * 5000)
    _info, log = drive(tmp_path, [long], child=True)
    row = json.loads(log.read_text())
    assert len(row["value"]) == 300 and row["value_len"] == 5000
    assert row["child"] is True, "on in children: that is where an ask kills the work"


def test_decision_log_an_angle_bracket_rule_is_class_b():
    assert asks.classify("<indirection-bash-wrapper>") == asks.CLASS_B
    assert asks.classify("") == asks.CLASS_B
    assert asks.classify("git push *") == asks.CLASS_A


def session(tmp_path, name, *texts):
    d = tmp_path / "sessions" / SLUG
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("".join(json.dumps({"type": "message", "message": {
        "role": "toolResult", "toolName": "bash",
        "content": [{"type": "text", "text": t}]}}) + "\n" for t in texts))
    return p


def test_decision_log_is_read_first_and_the_transcript_only_for_older_sessions(tmp_path):
    _info, log = drive(tmp_path, [ASKED, ALLOWED, PUSH])
    session(tmp_path, f"2026-10-15T04-00-00-000Z_{SID}.jsonl",
            "This 'bash' call for tool 'bash' (rule 'git push *') requires approval, "
            "but no interactive UI is available.")
    session(tmp_path, "2026-10-01T04-00-00-000Z_00000000-0000-0000-0000-000000000000.jsonl",
            "This 'bash -ic' call for tool 'bash' requires approval, "
            "but no interactive UI is available.")
    pairs = asks.logs(10, tmp_path / "sessions")
    events, _mentions, gates, sources = asks.replay(pairs, asks.read_decisions(log))
    assert sources == {"decision_log": 1, "transcripts": 1}
    assert gates == 1, "policy_allow asked nobody"
    kinds = sorted((e.kind, e.klass) for e in events)
    assert kinds == [("answered", asks.CLASS_B), ("unavailable", asks.CLASS_A),
                     ("unavailable", asks.CLASS_B)], \
        "the logged session's transcript line is not counted twice"
    assert asks.main(["--replay", "10", "--root", str(tmp_path / "sessions"),
                      "--decisions", str(log)]) == 0


def test_decision_log_review_joins_an_ask_to_its_outcome(tmp_path):
    rl = tmp_path / "review.jsonl"
    rows = [
        {"timestamp": "2026-09-05T10:00:00Z", "event": "permission_request.waiting",
         "requestId": "r1", "surface": "bash", "matchedPattern": "git push *"},
        {"timestamp": "2026-09-05T10:00:05Z", "event": "permission_request.approved",
         "requestId": "r1", "decidedBy": {"kind": "user", "via": "dialog"}},
        {"timestamp": "2026-10-15T04:00:00Z", "event": "permission_request.waiting",
         "requestId": "r2", "surface": "bash", "matchedPattern": "<indirection-bash-wrapper>"},
        {"timestamp": "2026-10-15T04:00:00Z", "event": "permission_request.denied",
         "requestId": "r2", "decidedBy": {"kind": "unavailable"}},
        {"timestamp": "2026-10-15T04:00:01Z", "event": "permission_request.session_approved"},
    ]
    rl.write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
    events, span = asks.review(rl)
    assert span == ("2026-09-05", "2026-10-15")
    got = sorted((e.kind, e.klass, e.decision) for e in events)
    assert got == [("answered", asks.CLASS_A, "allow"), ("unavailable", asks.CLASS_B, "deny")]
    assert asks.main(["--review", str(rl)]) == 0
    assert asks.main(["--review", str(tmp_path / "nowhere.jsonl")]) == 2
