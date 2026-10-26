"""bindings.yaml and its resolver (item 6b): the table checks offline, a binding
resolves under the profile, routing falls back to the default with its reason, and
the child's output is held to its contract."""
import json

import pytest

from lib import roots
from orchestration import bindings

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="the shipped table binds `code-review`, an imported skill the "
           "classification omits, so the export has no skill text to bind")

CAT = {"models": [
    {"id": "big", "vendor": "acme", "jurisdiction": "US", "pool": "usd"},
    {"id": "cheap", "vendor": "acme", "jurisdiction": "US", "pool": "usd"},
    {"id": "home", "vendor": "ollama", "jurisdiction": "local", "pool": "local"},
], "candidates": [{"id": "soon", "vendor": "acme", "jurisdiction": "US"}]}

CFG = {"default": "p", "privacy_class": {"local": "local", "suffix": {
    "no": "no-training", "unknown": "unknown"}},
    "profiles": {"p": {"jurisdictions": ["local", "US"], "vendors": {
        "acme": {"provider": "acme-api", "key_env": "ACME_KEY", "training": {"value": "no"}},
        "ollama": {"provider": "ollama"}}}}}

ENV = {"ACME_KEY": "x", "PI_PROFILE": "p"}

ROUTED = {"on": "tool:explore", "contract": "ref+quote", "role": "explore",
          "model": "route", "default": "big", "privacy": "any",
          "route": {"instructions": "which search", "criteria": {"lookup": "one", "recon": "many"},
                    "models": {"lookup": "cheap", "recon": "big"}}}


def table(*bs, at="0.8"):
    return {"route_confident_at": at,
            "contracts": {"ref+quote": "path:line + quote", "extract+url": "url + quote"},
            "bindings": list(bs) or [dict(ROUTED)]}


def static(**kw):
    b = {"on": "tool:read", "contract": "ref+quote", "role": "explore",
         "model": "cheap", "privacy": "any"}
    b.update(kw)
    return b


def resolve(t, on, task=None, env=ENV, **kw):
    return bindings.resolve(t, on, task, env=env, cfg=CFG, cat=CAT, **kw)


def jev_answers(monkeypatch, choice, p):
    calls = []

    def fake(state, questions, **kw):
        calls.append((state, questions))
        return {"answers": {"route": {"type": "choice", "choice": choice, "confidence": p,
                                      "probabilities": {choice: p}}},
                "usage": {"input_tokens": 90, "output_tokens": 5}}
    monkeypatch.setattr(bindings.jev, "ask", fake)
    monkeypatch.setattr(bindings.jev, "answer_fields", lambda a: a)
    return calls


# --- --check -------------------------------------------------------------------

@INSTANCE
def test_bindings_the_shipped_table_checks_clean():
    found, _ = bindings.check(bindings.load(), bindings._miniyaml.load(
        bindings.CATALOGUE.read_text()), bindings.roster())
    assert found == []


def test_bindings_check_names_each_mistake():
    bad = [static(on="widget:x"),
           static(on="tool:a", model="soon"),
           static(on="tool:b", contract="prose"),
           dict(ROUTED, on="tool:c", default=None, privacy="local"),
           dict(ROUTED, on="tool:d", route=dict(ROUTED["route"], models={"lookup": "cheap"})),
           static(on="tool:e", role=None),
           static(on="tool:e")]
    found, _ = bindings.check(table(*bad), CAT, {"explore"})
    assert "widget:x: on: want <kind>:<name>, kind one of item, tool, command, skill, role" in found
    assert "tool:a: model: 'soon' is not a callable catalogue id" in found
    assert "tool:b: contract: 'prose' is not under contracts:" in found
    assert "tool:c: default: missing; `model: route` needs one" in found
    assert ("tool:c: privacy: a routed binding sends the task text to Jev, so it must be `any`"
            in found)
    assert "tool:d: route: criteria and models name different answers (recon)" in found
    assert "tool:e: role: missing" in found
    assert "tool:e: on: also bound as #6" in found


def test_bindings_a_role_not_yet_written_is_inactive_not_a_finding():
    found, inactive = bindings.check(table(static(role="research")), CAT, {"explore"})
    assert found == []
    assert inactive == ["tool:read: inactive: role 'research' is not in pi-agent's roster"]


def test_bindings_tools_json_lists_only_active_tool_bindings():
    t = table(static(), static(on="tool:fetch", role="research"),
              static(on="skill:x"))
    names = [x["name"] for x in bindings.tools(t, {"explore"})]
    assert names == ["read"]


# --- resolve -------------------------------------------------------------------

def test_bindings_static_resolves_through_the_profile():
    c = resolve(table(static()), "tool:read")
    assert (c.available, c.model, c.pi_model, c.how) == (True, "cheap", "acme-api/cheap", "static")
    assert c.klass == "US-no-training", "the vendor's training posture, per the profile"
    assert "posture US-no-training" in c.line()


def test_bindings_a_missing_key_is_unavailable_never_borrowed():
    c = resolve(table(static()), "tool:read", env={"PI_PROFILE": "p"})
    assert not c.available
    assert c.reason == "cheap: ACME_KEY is not set"


def test_bindings_privacy_must_match_the_resolved_class():
    c = resolve(table(static(privacy="local")), "tool:read")
    assert not c.available
    assert c.reason == "cheap: privacy US-no-training, the binding wants local"
    assert resolve(table(static(model="home", privacy="local")), "tool:read").available


def test_bindings_an_unknown_on_is_an_error():
    with pytest.raises(bindings.BindingError, match="no binding for 'tool:zzz'"):
        resolve(table(static()), "tool:zzz")


def test_bindings_route_confident_takes_the_answer(monkeypatch):
    calls = jev_answers(monkeypatch, "lookup", 0.93)
    c = resolve(table(), "tool:explore", "where is def main")
    assert c.model == "cheap"
    assert c.how.startswith("route lookup p=0.93 (question ")
    assert calls[0][0] == "where is def main"
    assert list(calls[0][1]) == ["route"]
    assert c.usage == {"input_tokens": 90, "output_tokens": 5}


def test_bindings_route_below_threshold_falls_back_to_default(monkeypatch):
    jev_answers(monkeypatch, "lookup", 0.6)
    c = resolve(table(), "tool:explore", "where is def main")
    assert c.model == "big"
    assert c.how.startswith("default: route lookup p=0.60 < 0.8")


def test_bindings_route_failure_falls_back_with_its_kind(monkeypatch):
    def boom(*a, **kw):
        raise bindings.jev.JevError("rate-limited", "slow", fatal=False)
    monkeypatch.setattr(bindings.jev, "ask", boom)
    c = resolve(table(), "tool:explore", "x")
    assert (c.model, c.available) == ("big", True)
    assert c.how.startswith("default: route failed, rate-limited")


def test_bindings_dry_run_and_no_task_never_ask(monkeypatch):
    monkeypatch.setattr(bindings.jev, "ask", lambda *a, **k: pytest.fail("asked Jev"))
    assert resolve(table(), "tool:explore", "x", dry_run=True).how.startswith(
        "default: route not asked (--dry-run")
    assert resolve(table(), "tool:explore").how.startswith("default: route not asked (no task")


def test_bindings_a_routed_model_the_profile_lacks_falls_back(monkeypatch):
    jev_answers(monkeypatch, "lookup", 0.95)
    t = table(dict(ROUTED, route=dict(ROUTED["route"], models={"lookup": "home", "recon": "big"})))
    cfg_no_ollama = json.loads(json.dumps(CFG))
    del cfg_no_ollama["profiles"]["p"]["vendors"]["ollama"]
    c = bindings.resolve(t, "tool:explore", "x", env=ENV, cfg=cfg_no_ollama, cat=CAT)
    assert (c.model, c.available) == ("big", True)
    assert c.how.startswith("default: routed model unavailable (home: vendor ollama")


def test_bindings_the_question_hash_moves_with_the_wording():
    reworded = dict(ROUTED, route=dict(ROUTED["route"], instructions="which kind of search"))
    assert bindings.question_hash(ROUTED) != bindings.question_hash(reworded)
    assert bindings.question_hash(ROUTED) == bindings.question_hash(dict(ROUTED))


# --- the effective chain (fallbacks:) --------------------------------------------

NOKEY = {"PI_PROFILE": "p"}          # acme (big, cheap) unavailable; ollama (home) serves


def chain(**kw):
    return table(static(model="big", fallbacks="cheap, home", **kw))


def test_bindings_chain_head_available_leaves_the_chain_untouched():
    c = resolve(chain(), "tool:read")
    assert (c.available, c.model, c.how) == (True, "big", "static")


def test_bindings_chain_head_unavailable_runs_the_next_and_names_the_swap():
    t = table(static(model="big", fallbacks="home"))
    c = resolve(t, "tool:read", env=NOKEY)
    assert (c.available, c.model, c.pi_model) == (True, "home", "ollama/home")
    assert c.how == "fallback 2/2: big unavailable, ACME_KEY is not set"
    assert c.line() == ("tool:read -> home (ollama/home; fallback 2/2: big unavailable, "
                        "ACME_KEY is not set; posture local; contract ref+quote)")


def test_bindings_chain_a_middle_entry_unavailable_runs_the_third():
    cfg = json.loads(json.dumps(CFG))
    cfg["profiles"]["p"]["vendors"]["acme"]["key_env"] = "ACME_KEY"
    cat = {"models": CAT["models"] + [{"id": "other", "vendor": "oth", "jurisdiction": "US",
                                       "pool": "usd"}]}
    cfg["profiles"]["p"]["vendors"]["oth"] = {"provider": "oth-api", "key_env": "OTH_KEY",
                                              "training": {"value": "no"}}
    t = table(static(model="big", fallbacks="other, home"))
    c = bindings.resolve(t, "tool:read", env={"PI_PROFILE": "p", "OTH_KEY": "y"}, cfg=cfg, cat=cat)
    assert c.model == "other"                       # head out (no ACME_KEY), middle serves
    c = bindings.resolve(t, "tool:read", env=NOKEY, cfg=cfg, cat=cat)
    assert (c.model, c.how.split(":")[0]) == ("home", "fallback 3/3")
    assert "big unavailable, ACME_KEY is not set; other unavailable, OTH_KEY is not set" in c.how


def test_bindings_chain_privacy_skips_an_entry_with_its_reason():
    t = table(static(model="big", fallbacks="cheap, home", privacy="local"))
    c = resolve(t, "tool:read")
    assert (c.available, c.model) == (True, "home")
    assert c.how == ("fallback 3/3: big unavailable, privacy US-no-training, the binding wants "
                     "local; cheap unavailable, privacy US-no-training, the binding wants local")


def test_bindings_chain_every_entry_unavailable_exits_3_naming_each_reason(capsys, monkeypatch):
    t = table(static(model="big", fallbacks="cheap"))
    c = resolve(t, "tool:read", env=NOKEY)
    assert not c.available
    assert c.line() == ("tool:read: unavailable, no entry of the chain can run:\n"
                        "  big: ACME_KEY is not set\n  cheap: ACME_KEY is not set")
    monkeypatch.setattr(bindings, "load", lambda *a: t)
    monkeypatch.setattr(bindings._miniyaml, "load", lambda s: CAT)
    monkeypatch.setattr(bindings.profiles, "load", lambda *a: CFG)
    monkeypatch.setenv("PI_PROFILE", "p")
    monkeypatch.delenv("ACME_KEY", raising=False)
    assert bindings.main(["--resolve", "tool:read"]) == 3
    out = capsys.readouterr().out
    assert "  big: ACME_KEY is not set\n  cheap: ACME_KEY is not set" in out


def test_bindings_chain_every_entry_privacy_mismatched_names_each_reason():
    c = resolve(table(static(model="big", fallbacks="cheap", privacy="local")), "tool:read")
    assert c.reason.splitlines() == [
        "big: privacy US-no-training, the binding wants local",
        "cheap: privacy US-no-training, the binding wants local"]


def test_bindings_chain_a_single_entry_keeps_the_one_line_reason():
    c = resolve(table(static()), "tool:read", env=NOKEY)
    assert c.line() == "tool:read: unavailable: cheap: ACME_KEY is not set"


def test_bindings_chain_routed_default_precedes_fallbacks(monkeypatch):
    jev_answers(monkeypatch, "lookup", 0.95)
    cfg = json.loads(json.dumps(CFG))
    del cfg["profiles"]["p"]["vendors"]["ollama"]
    t = table(dict(ROUTED, route=dict(ROUTED["route"], models={"lookup": "home", "recon": "big"}),
                   default="cheap", fallbacks="big"))
    c = bindings.resolve(t, "tool:explore", "x", env=ENV, cfg=cfg, cat=CAT)
    assert c.model == "cheap"
    assert c.how.startswith("default: routed model unavailable (home: ")
    # routed choice and default both unavailable -> the fallback runs
    jev_answers(monkeypatch, "recon", 0.95)
    t["bindings"][0]["fallbacks"] = "home"
    c = resolve(t, "tool:explore", "x", env=NOKEY)
    assert c.model == "home"
    assert c.how == ("fallback 3/3: big unavailable, ACME_KEY is not set; "
                     "cheap unavailable, ACME_KEY is not set")


def test_bindings_chain_check_names_each_mistake():
    bad = [static(on="tool:a", fallbacks="cheap, soon"),
           static(on="tool:b", fallbacks="home, home"),
           static(on="tool:c", fallbacks="route"),
           dict(ROUTED, on="tool:d", fallbacks="cheap, big"),
           static(on="tool:e", fallbacks="cheap"),
           static(on="tool:f", fallbacks="home,"),
           static(on="tool:g", fallbacks="home")]
    found, _ = bindings.check(table(*bad), CAT, {"explore"})
    assert "tool:a: fallbacks: 'soon' is not a callable catalogue id" in found
    assert "tool:b: fallbacks: 'home' appears twice in the chain" in found
    assert "tool:c: fallbacks: `route` cannot be a link of a chain" in found
    assert "tool:d: fallbacks: 'big' is also the default" in found
    assert "tool:e: fallbacks: 'cheap' is also the model" in found
    assert "tool:f: fallbacks: an empty entry (stray comma)" in found
    assert not [f for f in found if f.startswith("tool:g")]      # availability is never a finding


# --- contracts -----------------------------------------------------------------

@pytest.fixture
def tree(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("import os\n\ndef main():\n    return 1\n")
    return tmp_path


def test_bindings_ref_quote_verifies_each_quote_in_its_file(tree):
    v = bindings.verify("ref+quote", 'src/a.py:3 "def main():"\nsrc/a.py:4 `return 1`', tree)
    assert (v.ok, v.summary) == (True, "2 of 2 quote(s) verified")


def test_bindings_a_ref_in_backticks_is_not_its_own_quote(tree):
    """Live, 2026-10-14: deepseek-flash wrote `path:line` - `quote`, and the
    closing backtick of the ref read as the opening of a quote."""
    v = bindings.verify("ref+quote", '`src/a.py:3` - `def main():`', tree)
    assert (v.ok, v.summary) == (True, "1 of 1 quote(s) verified")


def test_bindings_an_escaped_delimiter_stays_in_the_quote(tmp_path):
    (tmp_path / "b.yaml").write_text('x: "0.8"\ny: `z`\n')
    v = bindings.verify("ref+quote", 'b.yaml:1 "x: \\"0.8\\""\nb.yaml:2 `y: \\`z\\``', tmp_path)
    assert (v.ok, v.summary) == (True, "2 of 2 quote(s) verified")


def test_bindings_ref_quote_tolerates_drift_of_two_lines(tree):
    assert bindings.verify("ref+quote", 'src/a.py:2 "return 1"', tree).ok      # 2 off
    assert not bindings.verify("ref+quote", 'src/a.py:1 "return 1"', tree).ok  # 3 off
    assert not bindings.verify("ref+quote", 'src/a.py:4 "return 2"', tree).ok


def test_bindings_ref_quote_names_each_broken_finding(tree):
    v = bindings.verify("ref+quote",
                        'src/a.py:3 "def main():"\nsrc/b.py:1 "x"\nsrc/a.py:1\n', tree)
    assert not v.ok
    assert v.summary == "1 of 3 quote(s) verified"
    assert v.problems == ["src/b.py:1: no such file", "src/a.py:1: no quote"]


def test_bindings_prose_breaks_the_contract_and_not_found_keeps_it(tree):
    v = bindings.verify("ref+quote", "The main function returns one.", tree)
    assert (v.ok, v.summary) == (False, "no `path:line` finding")
    assert bindings.verify("ref+quote", "Not found.", tree).ok


def test_bindings_extract_url_wants_both_in_each_paragraph(tmp_path):
    good = 'https://a.example/x\n"the price is 3 USD"\n\n> quoted\nhttps://b.example'
    assert bindings.verify("extract+url", good, tmp_path).ok
    v = bindings.verify("extract+url", good + "\n\njust a summary https://c.example", tmp_path)
    assert v.problems == ["extract 3: no quote"]


# --- run -----------------------------------------------------------------------

def test_bindings_run_delegates_with_model_and_contract_and_checks_it(tree, monkeypatch, capsys):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, 'src/a.py:3 "def main():"\n', ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Proc()
    monkeypatch.setattr(bindings.subprocess, "run", fake_run)
    monkeypatch.setattr(bindings, "roster", lambda *a: {"explore"})
    real = bindings.resolve
    monkeypatch.setattr(bindings, "resolve",
                        lambda *a, **k: real(*a, **k, cfg=CFG, cat=CAT))
    rc = bindings.run(table(static()), "tool:read", "find main", tree, env=ENV)
    out = capsys.readouterr().out
    assert rc == 0, out
    cmd = seen["cmd"]
    assert cmd[cmd.index("--model") + 1] == "cheap"
    assert cmd[cmd.index("explore") + 1] == "find main\n\nReturn only this: path:line + quote"
    assert ("binding: tool:read -> cheap (acme-api/cheap; static; posture US-no-training; "
            "contract ref+quote); contract kept: 1 of 1 quote(s) verified") in out


def test_bindings_run_prints_the_swap_in_its_binding_line(tree, monkeypatch, capsys):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, 'src/a.py:3 "def main():"\n', ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Proc()
    monkeypatch.setattr(bindings.subprocess, "run", fake_run)
    monkeypatch.setattr(bindings, "roster", lambda *a: {"explore"})
    real = bindings.resolve
    monkeypatch.setattr(bindings, "resolve", lambda *a, **k: real(*a, **k, cfg=CFG, cat=CAT))
    t = table(static(model="big", fallbacks="home"))
    assert bindings.run(t, "tool:read", "find main", tree, env=NOKEY) == 0
    cmd = seen["cmd"]
    assert cmd[cmd.index("--model") + 1] == "home"
    assert ("binding: tool:read -> home (ollama/home; fallback 2/2: big unavailable, "
            "ACME_KEY is not set; posture local; contract ref+quote); contract kept"
            ) in capsys.readouterr().out


def test_bindings_run_exits_4_when_the_child_breaks_the_contract(tree, monkeypatch, capsys):
    class Proc:
        returncode, stdout, stderr = 0, "main is in a.py, trust me", ""
    monkeypatch.setattr(bindings.subprocess, "run", lambda cmd, **kw: Proc())
    monkeypatch.setattr(bindings, "roster", lambda *a: {"explore"})
    monkeypatch.setattr(bindings, "resolve", lambda *a, **k: bindings.Choice(
        "tool:read", "explore", "ref+quote", "cheap", "acme-api/cheap", "static", True))
    assert bindings.run(table(static()), "tool:read", "find main", tree, env=ENV) == 4
    assert "contract BROKEN: no `path:line` finding" in capsys.readouterr().out


def test_bindings_run_refuses_an_inactive_binding_before_spawning(tree, monkeypatch, capsys):
    monkeypatch.setattr(bindings.subprocess, "run", lambda *a, **k: pytest.fail("spawned"))
    monkeypatch.setattr(bindings, "roster", lambda *a: {"explore"})
    t = table(static(on="tool:fetch", role="research"))
    assert bindings.run(t, "tool:fetch", "x", tree, env=ENV) == 3
    assert "inactive: role 'research'" in capsys.readouterr().err


# --- commands and skills (6c) ---------------------------------------------------

CMD = "---\ndescription: check things\n---\nRun each:\n\n```bash\nfamiliar structure validate\nls -la\n```\n"
SKILL = "---\nname: code-review\nmode: link\nupstream_path: /tmp/up\n---\nBody the caller ignores.\n"


def cmd_table(**kw):
    b = {"on": "command:verify", "contract": "command+exit", "role": "bash",
         "model": "cheap", "privacy": "any"}
    b.update(kw)
    return table(b)


def test_bindings_a_command_is_read_from_its_file(tmp_path):
    (tmp_path / "verify.md").write_text(CMD)
    assert "familiar structure validate" in bindings.source_text("command:verify", commands=tmp_path)
    assert bindings.source_text("command:nope", commands=tmp_path) == ""
    assert bindings.source_text("tool:read", commands=tmp_path) == ""


def test_bindings_a_skill_reads_a_link_record_through_to_its_upstream(tmp_path):
    up = tmp_path / "up"
    up.mkdir()
    (up / "SKILL.md").write_text("---\nmode: link\n---\nThe real instructions.\n")
    d = tmp_path / "skills/system/checks/code-review"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(SKILL.replace("/tmp/up", str(up)))
    text = bindings.source_text("skill:code-review", skills=tmp_path / "skills")
    assert text == "The real instructions."


def test_bindings_check_refuses_a_command_with_no_text_and_an_unfenceable_contract(tmp_path):
    (tmp_path / "plain.md").write_text("---\n---\nDo the thing, carefully.\n")
    found, _ = bindings.check(cmd_table(on="command:gone", contract="ref+quote"), CAT, {"bash"},
                              commands=tmp_path)
    assert "command:gone: on: no command text for 'gone'" in found
    found, _ = bindings.check(cmd_table(on="command:plain"), CAT, {"bash"}, commands=tmp_path)
    assert "command:plain: contract: command+exit, but the text fences no command" in found
    found, _ = bindings.check(cmd_table(note=["x"]), CAT, {"bash"}, commands=tmp_path)
    assert "command:verify: note: not a string" in found


@INSTANCE
def test_bindings_the_shipped_command_and_skill_bindings_check_clean():
    found, inactive = bindings.check(bindings.load(), bindings._miniyaml.load(
        bindings.CATALOGUE.read_text()), bindings.roster())
    assert (found, inactive) == ([], [])
    on = {b["on"] for b in bindings.load()["bindings"]}
    assert {"command:verify", "skill:code-review"} <= on


def test_bindings_expected_commands_come_from_the_fences():
    assert bindings.expected_commands(CMD) == ["familiar structure validate", "ls -la"]
    assert bindings.expected_commands("no fence here") == []


def test_bindings_command_exit_contract_covers_every_command(tmp_path):
    text = "$ familiar structure validate\nexit 0\n\n$ ls -la\nexit 0\n"
    v = bindings.verify("command+exit", text, tmp_path, ["familiar structure validate", "ls -la"])
    assert (v.ok, v.summary) == (True, "2 of 2 command(s) with an exit code")
    v = bindings.verify("command+exit", text, tmp_path, ["familiar structure validate", "git status"])
    assert v.problems == ["git status: not reported"]
    v = bindings.verify("command+exit", "$ ls -la\nsome output\n", tmp_path, ["ls -la"])
    assert (v.ok, v.problems) == (False, ["ls -la: no `exit N` line"])
    v = bindings.verify("command+exit", "$ ls -la\nexit 2\n", tmp_path, [])
    assert v.ok and v.summary.endswith("; non-zero: ls -la")
    assert not bindings.verify("command+exit", "all good!", tmp_path, []).ok


def test_bindings_a_bound_child_gets_its_role_from_the_bound_role_plus_the_text(tmp_path):
    b = {"on": "command:verify", "contract": "command+exit", "role": "bash",
         "model": "cheap", "privacy": "any", "note": "Read-only. Do not fix anything."}
    agent = bindings.child_role(b, CMD, tmp_path)
    assert agent == "bound-command-verify"
    out = (tmp_path / f"{agent}.md").read_text()
    assert "name: bound-command-verify" in out          # a fresh role, so the skill's text is the prompt
    assert "tools: bash" in out                          # the bound role's cost lever, kept
    assert "Trust rules" in out                          # bash.md's body
    assert "familiar structure validate" in out          # the command's own text
    assert "Read-only. Do not fix anything." in out      # the binding's limits, last


def test_bindings_the_session_log_names_the_model_that_ran(tmp_path):
    import uuid
    sid = uuid.uuid5(bindings.PI_AGENT_NS, "bound-command-verify:77")
    (tmp_path / f"2026-10-14T10-00-00-000Z_{sid}.jsonl").write_text(
        '{"type":"model_change","provider":"deepseek","modelId":"deepseek-flash"}\n'
        '{"type":"message"}\n')
    path, model = bindings.session_model("bound-command-verify", "77", tmp_path)
    assert path.endswith(f"{sid}.jsonl")
    assert model == "deepseek/deepseek-flash"
    assert bindings.session_model("bound-command-verify", "78", tmp_path) == ("", "")


def test_bindings_commands_json_lists_the_active_commands_and_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(bindings, "source_text", lambda on, **kw: "text")
    t = table(static(), static(on="command:verify", contract="command+exit", role="bash"),
              static(on="skill:code-review", role="bash"))
    assert [(c["command"], c["on"]) for c in bindings.commands(t, {"explore", "bash"})] == [
        ("verify", "command:verify"), ("bound-code-review", "skill:code-review")]
    assert bindings.commands(t, {"nobody"}) == []
    assert bindings.commands(t, {"explore"}) == []


def test_bindings_run_a_command_builds_a_temp_role_and_names_the_session(tmp_path, monkeypatch, capsys):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, "$ ls -la\nexit 0\n", ""

    def fake_run(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw.get("env") or {}
        return Proc()
    monkeypatch.setattr(bindings.subprocess, "run", fake_run)
    monkeypatch.setattr(bindings, "roster", lambda *a: {"bash"})
    monkeypatch.setattr(bindings, "source_text", lambda on, **kw: CMD)
    monkeypatch.setattr(bindings, "expected_commands", lambda text: ["ls -la"])
    real = bindings.resolve
    monkeypatch.setattr(bindings, "resolve", lambda *a, **k: real(*a, **k, cfg=CFG, cat=CAT))
    monkeypatch.setattr(bindings, "session_model", lambda *a: ("/tmp/log.jsonl", "deepseek/deepseek-flash"))
    rc = bindings.run(table(static(on="command:verify", contract="command+exit", role="bash")),
                      "command:verify", "", tmp_path, env=ENV)
    out = capsys.readouterr().out
    assert rc == 0, out
    cmd, env = seen["cmd"], seen["env"]
    assert "bound-command-verify" in cmd
    assert cmd[cmd.index("--model") + 1] == "cheap"
    assert "--session" in cmd
    assert env["PI_AGENT_DIR"] and env["PI_AGENT_DIR"] != str(bindings.roots.SUBAGENTS)
    assert "contract kept: 1 of 1 command(s) with an exit code" in out
    assert "session /tmp/log.jsonl names deepseek/deepseek-flash" in out


def test_bindings_run_a_command_without_text_is_inactive(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bindings.subprocess, "run", lambda *a, **k: pytest.fail("spawned"))
    monkeypatch.setattr(bindings, "roster", lambda *a: {"bash"})
    monkeypatch.setattr(bindings, "source_text", lambda on, **kw: "")
    assert bindings.run(table(static(on="command:verify", role="bash")), "command:verify", "",
                        tmp_path, env=ENV) == 3
    assert "inactive: no command text" in capsys.readouterr().err


def test_bindings_a_broken_threshold_is_a_finding_and_exit_2_not_a_traceback(monkeypatch, capsys):
    """The review role's finding, 2026-10-14: an empty key parses to None, and
    `float(None)` is a TypeError, not a ValueError; and `resolve` read the key with
    `table[...]`, so a table that never ran `check` raised out of `main`."""
    found, _ = bindings.check(table(at=None), CAT, {"explore"})
    assert found == ["route_confident_at: None is not a number"]
    assert bindings.check(table(), CAT, {"explore"})[0] == []
    with pytest.raises(bindings.BindingError, match="route_confident_at: None"):
        resolve(table(at=None), "tool:explore", "x")
    missing = table()
    del missing["route_confident_at"]
    with pytest.raises(bindings.BindingError, match="route_confident_at: None"):
        bindings.resolve(missing, "tool:explore", "x", env=ENV, cfg=CFG, cat=CAT)
    # The same bad table through the CLI: exit 2 with the reason, no traceback.
    monkeypatch.setattr(bindings, "load", lambda *a: table(at=None))
    monkeypatch.setattr(bindings.jev, "ask", lambda *a, **k: pytest.fail("a broken table spent a call"))
    assert bindings.main(["--resolve", "tool:explore", "--task", "x"]) == 2
    assert "route_confident_at: None is not a number" in capsys.readouterr().err


def test_bindings_a_citation_without_a_clause_is_not_a_finding(tree):
    """Measured 2026-10-14: the review role answered with four bare citations and
    the checker passed them, so `not found` and four findings looked alike."""
    v = bindings.verify("ref+quote+defect", 'src/a.py:3 "def main():"', tree)
    assert (v.ok, v.problems) == (False, ["src/a.py:3: no `-- <what is wrong>` clause"])
    v = bindings.verify("ref+quote+defect", 'src/a.py:3 "def main():" -- it returns None on empty input', tree)
    assert (v.ok, v.summary) == (True, "1 of 1 quote(s) verified")
    assert bindings.verify("ref+quote+defect", "not found", tree).ok
    assert bindings.verify("ref+quote", 'src/a.py:3 "def main():"', tree).ok, "explore stays clause-free"


@INSTANCE
def test_bindings_the_shipped_review_binding_asks_for_the_clause():
    by = {b["on"]: b for b in bindings.load()["bindings"]}
    assert by["skill:code-review"]["contract"] == "ref+quote+defect"
    assert by["tool:explore"]["contract"] == "ref+quote"
    found, _ = bindings.check(bindings.load(), bindings._miniyaml.load(
        bindings.CATALOGUE.read_text()), bindings.roster())
    assert found == []


# --- the posture order and the scope opt-out (ruled 2026-10-14) -----------------

def test_bindings_the_scope_orders_the_chain_and_only_a_declaration_filters(tmp_path, monkeypatch):
    """A scope says which posture a directory PREFERS; it removes nothing. Both
    entries are available, and the one of the scope's class runs."""
    (tmp_path / "eu").mkdir()
    monkeypatch.setattr(bindings.selection, "load", lambda *a, **k: {
        "scope": {str(tmp_path / "eu"): {"privacy": "US-no-training"}}})
    # cheap is US-no-training, home is local: the scope prefers cheap's class.
    t = table(static(model="home", fallbacks="cheap"))
    c = bindings.resolve(t, "tool:read", cwd=tmp_path / "eu",
                         env={"ACME_KEY": "x", "PI_PROFILE": "p"}, cfg=CFG, cat=CAT)
    assert (c.model, c.klass) == ("cheap", "US-no-training")
    assert c.how == ("fallback 2/2: home (local) passed over: the preferred posture is US-no-training")
    assert c.how.count("passed over") == 1 and "unavailable" not in c.how


def test_bindings_a_cross_posture_swap_names_what_it_left(tmp_path, monkeypatch):
    (tmp_path / "eu").mkdir()
    monkeypatch.setattr(bindings.selection, "load", lambda *a, **k: {
        "scope": {str(tmp_path / "eu"): {"privacy": "CN-undisclosed"}}})
    # Nothing of the preferred class is in the chain, so the available one runs
    # and the line says why the posture differs.
    c = bindings.resolve(table(static(model="cheap")), "tool:read", cwd=tmp_path / "eu",
                         env=ENV, cfg=CFG, cat=CAT)
    assert c.available and c.model == "cheap"
    assert c.how == "static; posture US-no-training, the preferred CN-undisclosed is unavailable"


def test_bindings_a_binding_that_reads_no_local_file_ignores_the_scope(tmp_path, monkeypatch):
    """A web search or a fetch is not constrained by where it ran: the caller's
    files are not at issue, so `scope: ignored` skips the scope entirely."""
    (tmp_path / "eu").mkdir()
    monkeypatch.setattr(bindings.selection, "load", lambda *a, **k: {
        "scope": {str(tmp_path / "eu"): {"privacy": "CN-undisclosed"}}})
    c = bindings.resolve(table(static(model="cheap", on="tool:websearch", scope="ignored")),
                         "tool:websearch", cwd=tmp_path / "eu", env=ENV, cfg=CFG, cat=CAT)
    assert c.available and c.how == "static", "no preference is read, so nothing is crossed"
    found, _ = bindings.check(table(static(scope="sometimes")), CAT, {"explore"})
    assert "tool:read: scope: 'sometimes'; inherited or ignored" in found


def test_bindings_an_effort_level_no_model_in_the_chain_can_serve_is_a_finding():
    """`qwen3:4b` is `thinking: no` in the catalogue, so a chain that can land on
    it may not declare a level above `off` (decision 28). The check reads EVERY
    member, because a swap can land on any of them."""
    cat = {"models": [
        {"id": "claude-haiku-5-5", "kind": "chat", "cost": {"in": "0.1", "out": "0.5"},
         "capabilities": {"effort": "low, medium, high, xhigh, max", "thinking": "always"}},
        {"id": "qwen3:4b-instruct-2507-q4_K_M", "kind": "chat", "cost": {"in": "0", "out": "0"},
         "capabilities": {"thinking": "no"}}]}
    assert bindings.check(table(static(model="claude-haiku-5-5", effort="high")), cat,
                          {"explore"})[0] == [], "haiku lists low..max, so high is servable"
    found, _ = bindings.check(table(static(model="claude-haiku-5-5", effort="high",
                                           fallbacks="qwen3:4b-instruct-2507-q4_K_M")),
                              cat, {"explore"})
    assert any("does not think (thinking: no)" in f for f in found), found
    found, _ = bindings.check(table(static(effort="loud")), cat, {"explore"})
    assert "tool:read: effort: 'loud' is not one of off, minimal, low, medium, high, xhigh, max" in found


# --- rewrite (1b) and the role kind (1c) ----------------------------------------

GOOD_REWRITE = '''field: systems
reject: names no check, so any answer passes
add: evidence — ask what would be logged if a leaf were dropped
raw: the staging module's own log lines
check: today's run log, for the id of a leaf that vanished

```
Read staging.py. Quote the log lines it writes when a leaf is queued, then the
count in today's run log. Answer with the lines and the count.
```

kept: "drop a leaf silently"
self: "report yes/no" would accept a bare no — made it demand the count
'''
TASK = "can the staging step drop a leaf silently"


def test_bindings_rewrite_accepts_the_declared_shape(tmp_path):
    v = bindings.verify("rewrite", GOOD_REWRITE, tmp_path, task=TASK)
    assert (v.ok, v.problems) == (True, [])
    assert "one rewrite block, 1 kept line(s)" in v.summary


def test_bindings_rewrite_names_each_mistake(tmp_path):
    no_check = GOOD_REWRITE.replace("check: today's run log, for the id of a leaf that vanished\n", "")
    v = bindings.verify("rewrite", no_check, tmp_path, task=TASK)
    assert "check: missing" in v.problems

    two = GOOD_REWRITE.replace("```\n\nkept:", "```\n\n```\nx\n```\n\nkept:")
    v = bindings.verify("rewrite", two, tmp_path, task=TASK)
    assert any("2 fenced block(s)" in p for p in v.problems)

    long_head = GOOD_REWRITE.replace("field: systems", "field: systems " + "word " * 200)
    v = bindings.verify("rewrite", long_head, tmp_path, task=TASK)
    assert any("words before the block" in p for p in v.problems)

    v = bindings.verify("rewrite", GOOD_REWRITE, tmp_path, task="a different prompt entirely")
    assert any("no line quotes the task" in p for p in v.problems)


def test_bindings_rewrite_refuses_prose_with_no_block(tmp_path):
    v = bindings.verify("rewrite", "Here is a better prompt: ask for the log lines.\n"
                                    "kept: \"drop a leaf\"\nself: none\n", tmp_path, task=TASK)
    assert not v.ok and any("0 fenced block(s)" in p or "1 fenced block" in p for p in v.problems)


def test_bindings_rewrite_takes_kept_none_and_refuses_a_vacuous_quote(tmp_path):
    """`reject:`, `add:` and `check:` each accept a `none`; without the same escape for
    `kept:` the improver had to dress a word that merely occurs in the task as a
    preserved constraint -- and `kept: \"a\"` passed the substring test."""
    line = 'kept: "drop a leaf silently"'
    v = bindings.verify("rewrite", GOOD_REWRITE.replace(line, "kept: none"), tmp_path, task=TASK)
    assert (v.ok, v.problems) == (True, [])
    assert "kept: none" in v.summary, "the summary counts no kept line when there is none"

    v = bindings.verify("rewrite", GOOD_REWRITE.replace(line, 'kept: "a"'), tmp_path, task=TASK)
    assert any("quotes nothing usable" in p for p in v.problems), v.problems

    v = bindings.verify("rewrite", GOOD_REWRITE.replace(line, "`kept:`"), tmp_path, task=TASK)
    assert any("kept: is empty" in p for p in v.problems), v.problems

    v = bindings.verify("rewrite", GOOD_REWRITE.replace(line, 'kept: "a differently phrased constraint"'),
                        tmp_path, task=TASK)
    assert any("no line quotes the task" in p for p in v.problems), v.problems


def test_bindings_run_passes_the_declared_effort_or_the_receipt_would_lie(tree, monkeypatch):
    """`Choice.line()` prints `effort high`, and `pi-agent` takes `--effort` where an
    explicit flag WINS over the role's own level (pi-agent:199). The flag is what makes
    that line true; without it the role file's frontmatter governed a call the receipt
    described as the binding's."""
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, GOOD_REWRITE, ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Proc()

    def choice(effort):
        return bindings.Choice(on="role:deepen", role="deepen", contract="rewrite",
                               model="cheap", pi_model="acme-api/cheap", how="static",
                               available=True, effort=effort)

    monkeypatch.setattr(bindings.subprocess, "run", fake_run)
    monkeypatch.setattr(bindings, "roster", lambda *a: {"deepen"})
    monkeypatch.setattr(bindings, "resolve", lambda *a, **k: choice("high"))
    assert bindings.run(role_table(effort="high"), "role:deepen", TASK, tree, env=ENV) == 0
    cmd = seen["cmd"]
    assert cmd[cmd.index("--effort") + 1] == "high"

    monkeypatch.setattr(bindings, "resolve", lambda *a, **k: choice(""))
    assert bindings.run(role_table(), "role:deepen", TASK, tree, env=ENV) == 0
    assert "--effort" not in seen["cmd"], "no level declared, no level passed"


def test_bindings_a_role_binding_reads_the_roster_body():
    text = bindings.source_text("role:deepen")
    assert text.startswith("# Deeper, not bigger")
    assert "You are a prompt improver." in text
    assert bindings.source_text("role:nobody") == ""


def role_table(**kw):
    b = {"on": "role:deepen", "contract": "rewrite", "role": "deepen",
         "model": "cheap", "privacy": "any"}
    b.update(kw)
    t = table(b)
    t["contracts"]["rewrite"] = "the shape"
    return t


def test_bindings_run_a_role_spawns_the_roster_name_with_cwd_and_no_shape(tree, monkeypatch, capsys):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, GOOD_REWRITE, ""

    def fake_run(cmd, **kw):
        seen["cmd"], seen["env"] = cmd, kw.get("env")
        return Proc()

    monkeypatch.setattr(bindings.subprocess, "run", fake_run)
    monkeypatch.setattr(bindings, "roster", lambda *a: {"deepen"})
    monkeypatch.setattr(bindings, "resolve", lambda *a, **k: bindings.Choice(
        "role:deepen", "deepen", "rewrite", "cheap", "acme-api/cheap", "static", True))
    assert bindings.run(role_table(), "role:deepen", TASK, tree, env=ENV) == 0
    cmd = seen["cmd"]
    assert cmd[1] == "deepen", "the roster name, not a temporary bound-role"
    assert "PI_AGENT_DIR" not in (seen["env"] or {}), "no temp role is written for this kind"
    assert cmd[2] == f"Working directory: {tree}\n\n{TASK}", "cwd, and nothing appended"
    assert "Return only this" not in cmd[2], "the role body already asks for the shape"


def test_bindings_check_refuses_a_role_binding_that_runs_another_definition():
    found, _ = bindings.check(role_table(role="explore"), CAT, {"deepen", "explore"})
    assert "role:deepen: role: 'explore' must equal 'deepen' for this kind" in found
    found, _ = bindings.check(role_table(), CAT, {"deepen"})
    assert found == []
