"""The two one-liners on every ask (item 8g): the requester's claim, and an
independent reading of the command alone.

Driven through node with a stub `pi` and a stub context, the way
`test_decision_log.py` drives the decision log: the interesting parts are the
branch binding, the independence guard, the failure wording, and the log row --
none of which need a real model or a terminal.
"""
import json
import pathlib
import shutil
import subprocess

import pytest

EXT = pathlib.Path(__file__).resolve().parents[1] / "boundaries/pi-explain/index.ts"
# The rule tier reads the compiled boundaries (index.ts `RULES_PATH`). The
# classification omits them, so a published tree has only the floor tier.
RULES = pathlib.Path(__file__).resolve().parents[2] / "config/boundaries/boundaries.json"
NEEDS_RULES = pytest.mark.skipif(
    not RULES.exists(),
    reason="the rule tier needs this machine's compiled boundaries, which the "
           "classification omits; the floor and scan tiers are tested without them")
MODEL = "ollama/qwen2.5-coder:14b"
FALLBACK = "ollama/qwen3:4b-instruct-2507-q4_K_M"
PUSH = "git push -u origin fix/x"

# The stub fires session_start and the two broadcasts the permission system
# emits, and awaits the handler the way pi's bus would not -- a test can.
DRIVER = """
const mod = await import(process.argv[1]);
const sc = JSON.parse(process.argv[2]);
const widgets = [], calls = [];
const ctx = {
  hasUI: sc.hasUI !== false,
  mode: sc.hasUI === false ? "print" : "tui",
  model: sc.requester ? { provider: sc.requester, id: sc.requesterId ?? "claude-sonnet-5-5" } : undefined,
  sessionManager: { getBranch: () => sc.branch ?? [], getSessionId: () => "sess-1" },
  modelRegistry: {
    find: (p, i) => (sc.catalog ?? []).includes(`${p}/${i}`) ? { provider: p, id: i } : undefined,
    hasConfiguredAuth: () => sc.auth !== false,
    complete: async (m, req, opts) => {
      calls.push({ model: `${m.provider}/${m.id}`, system: req.systemPrompt,
                   text: req.messages[0].content[0].text,
                   messages: req.messages.length, requestKeys: Object.keys(req).sort(),
                   messageKeys: Object.keys(req.messages[0]).sort() });
      if (sc.complete === "throw") throw new Error("model exploded");
      if (sc.complete === "hang") return await new Promise((_, rej) => {
        opts.signal.addEventListener("abort", () => rej(new Error("aborted")));
        setTimeout(() => rej(new Error("never")), 20000);
      });
      return { content: [{ type: "text", text: sc.answer ?? "" }] };
    },
  },
  ui: { setWidget: (k, l) => widgets.push(l === undefined ? null : [k, l]), notify: () => {} },
};
const hooks = {}, bus = {};
mod.default({ on: (n, f) => { hooks[n] = f; }, events: { on: (n, f) => { bus[n] = f; } } });
hooks.session_start({}, ctx);
if (sc.event) { const p = bus[mod.UI_CHANNEL](sc.event); if (p && p.then) await p; }
if (sc.decision) bus[mod.DECISION_CHANNEL](sc.decision);
const fs = await import("node:fs");
const rows = fs.existsSync(mod.logPath())
  ? fs.readFileSync(mod.logPath(), "utf8").split("\\n").filter(Boolean).map(JSON.parse) : [];
const pure = {};
if (sc.finish) pure.finish = sc.finish.map((t) => mod.finish(t));
if (sc.claim) pure.claim = mod.claimFrom(sc.branch ?? [], sc.claim[0], sc.claim[1]);
if (sc.audit) {
  const rs = mod.loadRules();
  pure.audit = sc.audit.map((one) => {
    const a = mod.auditForEvent(one.event, one.claim, rs);
    return { text: a.text, source: a.source, ops: a.ops };
  });
}
console.log(JSON.stringify({ widgets, calls, rows, pure, config: mod.loadConfig() }));
"""


def drive(tmp_path, **sc):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    home, data = tmp_path / "home", tmp_path / "data"
    home.mkdir(exist_ok=True)
    if sc.get("config"):
        cfg = home / ".pi/agent/extensions/pi-explain/config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps(sc.pop("config")))
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "PAZRAS_DATA_DIR": str(data)}
    out = subprocess.run([node, "--input-type=module", "-e", DRIVER, str(EXT), json.dumps(sc)],
                         capture_output=True, text=True, env=env, cwd=tmp_path, timeout=120)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def branch(text="The branch is verified; pushing it now.", command=PUSH, name="bash"):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    content.append({"type": "toolCall", "id": "tc1", "name": name, "arguments": {"command": command}})
    return [{"type": "message", "message": {"role": "user", "content": "push it"}},
            {"type": "message", "message": {"role": "assistant", "content": content}}]


def event(value=PUSH, **kw):
    return {"requestId": "perm-1", "source": "tool_call", "surface": "bash", "value": value,
            "agentName": None, "forwarding": None,
            "request": {"surface": "bash", "toolName": "bash", "value": value}, **kw}


ANSWER = "Pushes the branch fix/x to origin and sets its upstream."


def test_both_lines_render_and_the_row_records_the_pair(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER,
              catalog=[MODEL], requester="anthropic",
              decision={"requestId": "perm-1", "result": "allow", "resolution": "user_approved",
                        "matchedPattern": "git push *"})
    placeholder, final, clear = r["widgets"][0][1], r["widgets"][-2][1], r["widgets"][-1]
    assert placeholder[:2] == ["agent : The branch is verified; pushing it now.",
                               "independent : reading…"], "the claim is up before the model answers"
    assert placeholder[2] == "audit : ops history", \
        "the audit is synchronous, so it is in the first widget too"
    assert final[:2] == ["agent : The branch is verified; pushing it now.", f"independent : {ANSWER}"]
    assert final[2].startswith("audit : ")
    assert clear is None, "the decision clears the widget"
    row, decision = r["rows"]
    assert row["kind"] == "explain" and row["claim_bound"] is True
    assert row["request"] == "perm-1" and row["session"] == "sess-1"
    assert row["independent_model"] == MODEL and row["independence"] == "distinct-provider"
    assert row["rendered"] is True and isinstance(row["latency_ms"], int)
    assert row["value"] == PUSH and row["value_len"] == len(PUSH)
    assert decision["kind"] == "decision" and decision["request"] == "perm-1"
    assert decision["decision"] == "allow" and decision["rule"] == "git push *"


def test_the_model_sees_only_the_command(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER, catalog=[MODEL])
    (call,) = r["calls"]
    assert call["text"] == PUSH, "no cwd, no rule, no claim, no session"
    assert "no judgement" in call["system"] and "15 words" in call["system"]
    assert call["model"] == MODEL


def test_a_message_with_no_text_says_so_instead_of_showing_nothing(tmp_path):
    r = drive(tmp_path, branch=branch(text=None), event=event(), answer=ANSWER, catalog=[MODEL])
    assert r["widgets"][-1][1][0] == "agent : (nothing stated)"


def test_a_model_that_throws_is_stated_not_hidden(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), complete="throw", catalog=[MODEL])
    assert r["widgets"][-1][1][1] == "independent : unavailable (model exploded)"
    assert r["rows"][0]["independent"].startswith("unavailable (")


def test_a_hung_model_times_out_and_the_ask_is_never_held(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), complete="hang", catalog=[MODEL],
              config={"timeout_ms": 50})
    assert r["widgets"][-1][1][1] == "independent : unavailable (timeout 50 ms)"


CLAUDE = "anthropic/claude-sonnet-5-5"


def test_the_same_model_is_still_independent_because_it_reads_alone(tmp_path):
    """Independence is a separate instance with only the command, not a different
    brain (user, 2026-10-24): the same weights are allowed, and are read anyway."""
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER, catalog=[MODEL],
              requester="ollama", requesterId="qwen2.5-coder:14b")
    assert r["widgets"][-1][1][1] == f"independent : {ANSWER}"
    (call,) = r["calls"]
    assert call["messages"] == 1 and call["requestKeys"] == ["messages", "systemPrompt"]
    assert call["messageKeys"] == ["content", "role", "timestamp"], "no history, no session"
    assert r["rows"][0]["independence"] == "same-model"


def test_the_same_vendor_is_classified_and_still_read(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER,
              catalog=["anthropic/claude-haiku-9"], requester="anthropic",
              config={"model": "anthropic/claude-haiku-9"})
    assert r["widgets"][-1][1][1] == f"independent : {ANSWER}"
    assert r["rows"][0]["independence"] == "same-provider"


def test_another_family_behind_the_same_local_port_is_classified_too(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER, catalog=[MODEL],
              requester="ollama")
    assert r["widgets"][-1][1][1] == f"independent : {ANSWER}"
    assert r["rows"][0]["independence"] == "same-provider"


def test_a_thought_is_shown_and_labelled_as_one(tmp_path):
    """Real transcripts: the tool-call message carries thinking and no prose."""
    thought = ("The daemon may be down. Could be the socket. Let me check whether "
               "the privileged flag is even accepted here.")
    b = branch(text=None)
    b[-1]["message"]["content"] = [
        {"type": "thinking", "thinking": thought},
        {"type": "toolCall", "id": "tc1", "name": "bash", "arguments": {"command": PUSH}}]
    r = drive(tmp_path, branch=b, event=event(), answer=ANSWER, catalog=[MODEL])
    assert r["widgets"][-1][1][0] == \
        "agent (thinking) : Let me check whether the privileged flag is even accepted here."
    assert r["rows"][0]["claim_source"] == "thinking"


def test_the_carrier_is_the_message_that_carries_the_value(tmp_path):
    """A newer call about something else must not supply this ask's claim."""
    b = branch(text=None)
    b[-1]["message"]["content"] = [
        {"type": "thinking", "thinking": "Let me collect the hashes for the fingerprint."},
        {"type": "toolCall", "id": "tc9", "name": "bash", "arguments": {"command": "sha256sum x"}}]
    b.insert(1, {"type": "message", "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "The push is waiting on me. Let me send it upstream."},
        {"type": "toolCall", "id": "tc1", "name": "bash", "arguments": {"command": PUSH}}]}})
    b.append({"type": "message", "message": {"role": "user", "content": "go on"}})
    r = drive(tmp_path, branch=b, event=event(), answer=ANSWER, catalog=[MODEL])
    assert r["widgets"][-1][1][0] == "agent (thinking) : Let me send it upstream."


def test_a_thought_that_cannot_be_bound_is_withheld(tmp_path):
    """A guess dressed as intent is worse than saying nothing."""
    b = branch(text=None, command="something else entirely")
    b[-1]["message"]["content"] = [
        {"type": "thinking", "thinking": "Let me check the docker daemon anyway."},
        {"type": "toolCall", "id": "tc1", "name": "bash", "arguments": {"command": "ls"}}]
    r = drive(tmp_path, branch=b, event=event(), answer=ANSWER, catalog=[MODEL])
    assert r["widgets"][-1][1][0] == "agent : (nothing stated)"
    assert r["rows"][0]["claim_bound"] is False


def test_an_earlier_sentence_is_labelled_as_earlier(tmp_path):
    b = branch(text=None)
    b.insert(1, {"type": "message", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "I will verify the branch first, then push it."}]}})
    r = drive(tmp_path, branch=b, event=event(), answer=ANSWER, catalog=[MODEL])
    assert r["widgets"][-1][1][0] == \
        "agent (earlier) : I will verify the branch first, then push it."
    assert r["rows"][0]["claim_source"] == "earlier"


def test_a_model_outside_the_catalogue_is_named(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), catalog=[])
    assert r["widgets"][-1][1][1] == f"independent : unavailable ({MODEL} not in the catalogue)"


def test_without_a_ui_the_row_is_written_and_nothing_renders(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER, catalog=[MODEL], hasUI=False)
    assert r["widgets"] == []
    assert r["rows"][0]["rendered"] is False


def test_a_decision_for_another_request_leaves_the_widget_alone(tmp_path):
    r = drive(tmp_path, branch=branch(), event=event(), answer=ANSWER, catalog=[MODEL],
              decision={"requestId": "perm-other", "result": "allow"})
    assert r["widgets"] and r["widgets"][-1] is not None
    assert [w for w in r["widgets"] if w is None] == []


def test_a_forwarded_ask_says_the_claim_is_elsewhere(tmp_path):
    r = drive(tmp_path, branch=[], answer=ANSWER, catalog=[MODEL],
              event=event(forwarding={"requesterSessionId": "child-1", "requesterAgentName": "explore"}),
              decision=None)
    assert r["widgets"][-1][1][0] == "agent : (asked by explore; its words are not in this session)"


def test_a_non_bash_ask_is_left_alone(tmp_path):
    r = drive(tmp_path, branch=branch(), catalog=[MODEL],
              event={**event(value="/etc/hosts"), "surface": "read",
                     "request": {"surface": "read", "toolName": "read", "value": "/etc/hosts"}})
    assert r["widgets"] == [] and r["rows"] == [] and r["calls"] == []


def test_the_binding_survives_a_heredoc(tmp_path):
    value = "git commit -F - <<'MSG'\nrun the test\nMSG"
    r = drive(tmp_path, branch=branch(command=value), catalog=[MODEL],
              event=event(value=value), answer=ANSWER, claim=["bash", value])
    assert r["pure"]["claim"]["bound"] is True
    assert r["rows"][0]["claim_bound"] is True


def test_a_claim_that_does_not_bind_is_marked_in_the_row(tmp_path):
    r = drive(tmp_path, branch=branch(command="ls"), catalog=[MODEL], event=event(),
              answer=ANSWER, claim=["bash", PUSH])
    assert r["pure"]["claim"]["bound"] is False
    assert r["rows"][0]["claim_bound"] is False, "the newest claim is shown, the weak binding recorded"


AUDIT_CASES = [
    # real boundaries.json: the rule's own reason reaches the ask
    {"cmd": "docker version --privileged", "pattern": "*docker *--privileged*",
     "claim": "I am about to check the Docker version with privileged mode enabled.",
     "source": "rule", "ops": ["privilege"], "text": "A container given every device"},
    {"cmd": "git push -u origin fix/x", "pattern": "git push *",
     "claim": "The branch is verified; pushing it now.",
     "source": "rule", "ops": ["history"], "text": "Pushing and rewriting history"},
    # a floor: what the wrapper hides, and what the scan still sees
    {"cmd": "env -u HOME timeout 60 bash -c 'rm -rf /tmp/x'", "pattern": "<indirection-bash-wrapper>",
     "claim": "Clean up the temp dirs.", "source": "floor", "ops": ["delete"],
     "text": "ops delete · a wrapper"},
    {"cmd": "xargs grep -l pazras", "pattern": "<indirection-bash-wrapper>",
     "claim": "Find where pazras appears.", "source": "floor", "ops": [],
     "text": "no write, delete or network visible"},
    # divergence: the scan sees a write and a fetch the claim does not mention
    {"cmd": "curl -s https://example.com > out.sh", "pattern": "<opaque-bash-wrapper>",
     "claim": "Fetch the page.", "source": "floor", "ops": ["write", "network"],
     "text": "the claim names none of: write, network"},
    # nothing to say
    {"cmd": "ls ~/06_SYSTEM", "pattern": None, "claim": "List the tree.",
     "source": "none", "ops": [], "text": ""},
]


@NEEDS_RULES
def test_the_audit_line_quotes_the_rule_or_names_what_the_scan_sees(tmp_path):
    r = drive(tmp_path, branch=branch(), catalog=[MODEL], event=event(),
              audit=[{"event": {"value": c["cmd"], "request": {"matchedPattern": c["pattern"],
                                                              "value": c["cmd"]}},
                      "claim": c["claim"]} for c in AUDIT_CASES])
    for case, got in zip(AUDIT_CASES, r["pure"]["audit"]):
        assert got["source"] == case["source"], case["cmd"]
        assert got["ops"] == case["ops"], case["cmd"]
        assert case["text"] in got["text"], f"{case['cmd']}: {got['text']}"
        assert len(got["text"]) <= 200, "the line has to fit above an editor"


@NEEDS_RULES
def test_the_audit_line_rides_in_the_widget_and_the_row(tmp_path):
    ev = {**event(), "request": {"surface": "bash", "toolName": "bash", "value": PUSH,
                                 "matchedPattern": "git push *"}}
    r = drive(tmp_path, branch=branch(), event=ev, answer=ANSWER, catalog=[MODEL],
              decision={"requestId": "perm-1", "result": "allow"})
    line = r["widgets"][-2][1][2]
    assert line.startswith("audit : Pushing and rewriting history"), \
        "the rule's own reason, not a model's paraphrase"
    row = r["rows"][0]
    assert row["audit_source"] == "rule" and "history" in row["audit_ops"]
    assert row["audit"] and "instead" in row["audit"]


def test_the_reading_is_one_sentence_without_code(tmp_path):
    long = ("Runs `git push` with upstream tracking. Then it does many other things that are "
            "not part of the first sentence at all and would never fit")
    r = drive(tmp_path, branch=branch(), catalog=[MODEL], event=event(), answer=long,
              finish=["Operation: Runs a dry run.", "a" * 400, long, ""])
    short, cut, words, empty = r["pure"]["finish"]
    assert short == "Runs a dry run.", "the label a model likes to prepend is not a sentence"
    assert cut.endswith("…") and len(cut) <= 200
    assert words == "Runs git push with upstream tracking."
    assert empty == ""
    assert "`" not in r["widgets"][-1][1][1]
