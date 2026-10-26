"""dispatch: --check passes on the real SPECS.md and refuses a stripped item, an
unknown model and a candidate model, each naming item and field; --gate covers
every dev/*/SPECS.md; `dispatch <SPECS.md>` probes and audits (3c), with Jev
stubbed -- no test reaches the network."""
import pathlib
import subprocess

import pytest

from harness import jev

from lib import roots
from orchestration import dispatch

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="it reads this instance's `dev/*/SPECS.md`, which the "
           "classification omits with `dev/`; the gate is tested on fixtures "
           "above")

REAL = roots.REPO / "dev" / "orchestration" / "SPECS.md"
FAMILIAR = roots.REPO / "engine" / "familiar"


def run(path, capsys):
    rc = dispatch.main(["--check", str(path)])
    return rc, capsys.readouterr().out


def spec(tmp_path, model="claude-sonnet-5-5", drop=None):
    lines = ["- [ ] **1a · open.**",
             "  touches: engine/x.py",
             "  depends: —",
             f"  model: {model}",
             "  verify: true"]
    p = tmp_path / "SPECS.md"
    p.write_text("\n".join(l for l in lines if drop is None or not l.strip().startswith(drop)) + "\n")
    return p


def candidate_id():
    return sorted(dispatch.catalogue_ids()[1])[0]


@INSTANCE
def test_real_specs_pass(capsys):
    rc, out = run(REAL, capsys)
    assert rc == 0, out
    assert "0 finding(s)" in out


def test_good_copy_passes(tmp_path, capsys):
    assert run(spec(tmp_path), capsys)[0] == 0


def test_missing_field_named(tmp_path, capsys):
    rc, out = run(spec(tmp_path, drop="verify"), capsys)
    assert rc == 1
    assert "item 1a: verify: missing" in out


def test_unknown_model(tmp_path, capsys):
    rc, out = run(spec(tmp_path, model="gpt-nope"), capsys)
    assert rc == 1
    assert "item 1a: model:" in out and "not a callable catalogue id" in out


def test_candidate_model(tmp_path, capsys):
    cid = candidate_id()
    rc, out = run(spec(tmp_path, model=cid), capsys)
    assert rc == 1
    assert f"item 1a: model: {cid!r} is a candidate, not callable" in out
    assert "1 finding(s)" in out


def test_user_model_ok(tmp_path, capsys):
    assert run(spec(tmp_path, model="user"), capsys)[0] == 0


def test_unreadable_exits_2(tmp_path, capsys):
    assert dispatch.main(["--check", str(tmp_path / "nope.md")]) == 2


def test_without_a_file_exits_2(capsys):
    assert dispatch.main([]) == 2
    assert "give a SPECS.md" in capsys.readouterr().err


def test_check_output_unchanged_by_dispatch(tmp_path, capsys):
    """--check prints its findings and one summary line, nothing of dispatch's."""
    path = spec(tmp_path)
    rc, out = run(path, capsys)
    assert rc == 0
    assert out == f"dispatch --check: {path}: 1 open item(s), 0 finding(s)\n"


@INSTANCE
def test_cli_route(tmp_path):
    ok = subprocess.run([str(FAMILIAR), "orchestration", "dispatch", "--check", str(REAL)],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    bad = subprocess.run([str(FAMILIAR), "orchestration", "dispatch", "--check",
                          str(spec(tmp_path, drop="model"))], capture_output=True, text=True)
    assert bad.returncode == 1
    assert "item 1a: model: missing" in bad.stdout


# --- --gate: every dev/*/SPECS.md, legacy files warn ---------------------------

GOOD = ("- [ ] **1a · open.**\n  touches: engine/x.py\n  depends: —\n"
        "  model: claude-sonnet-5-5\n  verify: true\n")


def tree(tmp_path, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def gate(root, legacy, capsys, monkeypatch):
    contract = dict(dispatch.specs.load_contract(), legacy=legacy)
    monkeypatch.setattr(dispatch.specs, "load_contract", lambda: contract)
    rc = dispatch.main(["--gate", "--root", str(root)])
    return rc, capsys.readouterr().out


def test_gate_clean_tree_passes(tmp_path, capsys, monkeypatch):
    root = tree(tmp_path, {"dev/a/SPECS.md": GOOD})
    rc, out = gate(root, {}, capsys, monkeypatch)
    assert rc == 0, out
    assert "dispatch --gate: 1 file(s), 0 failing, 0 legacy" in out


def test_gate_field_removed_fails_naming_item_and_field(tmp_path, capsys, monkeypatch):
    bad = GOOD.replace("  model: claude-sonnet-5-5\n", "")
    root = tree(tmp_path, {"dev/a/SPECS.md": GOOD, "dev/b/SPECS.md": bad})
    rc, out = gate(root, {}, capsys, monkeypatch)
    assert rc == 1
    assert "dev/b/SPECS.md: line 1: item 1a: model: missing" in out
    assert "2 file(s), 1 failing, 0 legacy" in out


def test_gate_legacy_with_findings_warns(tmp_path, capsys, monkeypatch):
    root = tree(tmp_path, {"dev/old/SPECS.md": "- [ ] **x · no fields.**\n"})
    rc, out = gate(root, {"dev/old/SPECS.md": "pre-contract"}, capsys, monkeypatch)
    assert rc == 0, out
    assert "legacy: dev/old/SPECS.md: " in out and "finding(s) -- pre-contract" in out
    assert "1 file(s), 0 failing, 1 legacy" in out


def test_gate_legacy_now_clean_fails(tmp_path, capsys, monkeypatch):
    root = tree(tmp_path, {"dev/old/SPECS.md": GOOD})
    rc, out = gate(root, {"dev/old/SPECS.md": "pre-contract"}, capsys, monkeypatch)
    assert rc == 1
    assert "dev/old/SPECS.md is dispatchable now; remove it from legacy: in specs.yaml" in out


def test_gate_legacy_path_missing_fails(tmp_path, capsys, monkeypatch):
    root = tree(tmp_path, {"dev/a/SPECS.md": GOOD})
    rc, out = gate(root, {"dev/gone/SPECS.md": "pre-contract"}, capsys, monkeypatch)
    assert rc == 1
    assert "dev/gone/SPECS.md does not exist" in out


def test_gate_excludes_check_and_file(tmp_path, capsys):
    assert dispatch.main(["--gate", "--check", str(spec(tmp_path))]) == 2
    assert dispatch.main(["--gate", str(spec(tmp_path))]) == 2


@INSTANCE
def test_gate_real_repo_passes():
    ok = subprocess.run([str(FAMILIAR), "orchestration", "dispatch", "--gate"],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr


# --- dispatch <SPECS.md>: the probes and the audit (3c) ------------------------

ITEMS = ("- [ ] **1a · write the parser.** Read the file into items.\n"
         "  touches: engine/x.py\n  depends: —\n  model: claude-opus-5-5\n  verify: pytest\n"
         "- [ ] **1b · push it.**\n"
         "  touches: engine/y.py\n  depends: 1a\n  model: user\n  verify: manual: git log\n")


def answers(difficulty=1.0, cls="edit", open_decision=0.1, verify_alone=0.8):
    """A response as Jev returns it; four difficulty levels, so 1.0 reads 0.33."""
    return {"model": "jev-1.13.0",
            "answers": {"difficulty": {"type": "score", "score": difficulty, "confidence": 0.7},
                        "task_class": {"type": "choice", "choice": cls, "confidence": 0.9,
                                       "probabilities": {cls: 0.9}},
                        "open_decision": {"type": "noul", "noul": open_decision},
                        "verify_alone": {"type": "noul", "noul": verify_alone}},
            "usage": {"input_tokens": 500, "output_tokens": 40}}


@pytest.fixture
def specs_file(tmp_path):
    p = tmp_path / "SPECS.md"
    p.write_text(ITEMS)
    return p


def stub(monkeypatch, response=None, raises=None):
    calls = []

    def fake_ask(state, questions, **kw):
        calls.append((state, questions))
        if raises is not None:
            raise raises
        return response if response is not None else answers()
    monkeypatch.setattr(dispatch.jev, "ask", fake_ask)
    return calls


def tiers_stub(monkeypatch, ids, reason="a stubbed tier", idx=0, why="stubbed tier"):
    """Replace the tier policy and its arithmetic so an audit test is hermetic:
    the tier it reads is the one written here, and the privacy filter still
    applies, as the real `admissible` applies it. The policy itself is tested in
    test_selection.py."""
    tier = {"models": ", ".join(ids), "reason": reason}
    monkeypatch.setattr(dispatch.selection_mod, "tiers",
                        lambda sel, cls: [{"models": "", "reason": "stub"}] * idx + [tier])

    def fake(cat, caps, selection, task_class, rules, **k):
        allowed = k.get("allowed")
        return [i for i in ids if allowed is None or i in allowed], tier, idx, why
    monkeypatch.setattr(dispatch, "admissible", fake)
    return tier


def dispatch_(path, capsys, *extra):
    rc = dispatch.main([*extra, str(path)])
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def row(out, item_id):
    return next(l for l in out.splitlines() if l.startswith(item_id + " "))


def test_one_call_per_item_with_the_item_text_as_state(specs_file, capsys, monkeypatch):
    calls = stub(monkeypatch)
    rc, out, _ = dispatch_(specs_file, capsys)
    assert rc == 0, out
    assert len(calls) == 1, "the user's item is not probed; one call for 1a"
    state, questions = calls[0]
    assert set(questions) == set(dispatch.PROBES)
    assert "write the parser" in state and "touches: engine/x.py" in state
    assert "declared model: claude-opus-5-5 (Claude Opus 5.5)" in state
    assert "push it" not in state


def test_the_four_answers_land_in_the_table(specs_file, capsys, monkeypatch):
    stub(monkeypatch)
    _, out, _ = dispatch_(specs_file, capsys)
    r = row(out, "1a")
    assert "0.33" in r and "edit 0.90" in r and "no 0.10" in r and "yes 0.80" in r
    assert "user: the user's to do" in row(out, "1b")
    assert "wave 1: 1a" in out and "wave 2: 1b" in out
    assert "jev: 1 call(s), 500 in, 40 out" in out


def test_an_open_design_decision_no_longer_raises_the_tier(specs_file, capsys, monkeypatch):
    """It used to make the declaration stand, then it raised a tier; since
    2026-10-14 it does nothing, because Jev answered `yes` on 7 of 7 items -- a
    constant carries no information, and a constant raise is "always the
    frontier", the opposite of what this system is for."""
    stub(monkeypatch, answers(open_decision=0.9))
    _, out, _ = dispatch_(specs_file, capsys)
    line = row(out, "1a")
    assert "tier 1 of 3" in line and "raised" not in line


def test_a_verify_that_cannot_judge_alone_still_raises_the_tier(specs_file, capsys, monkeypatch):
    """The one raise left, because the answer varies (0.03 to 0.55 on our items)."""
    stub(monkeypatch, answers(verify_alone=0.2))
    _, out, _ = dispatch_(specs_file, capsys)
    line = row(out, "1a")
    assert "raised: verify cannot judge alone" in line and "tier 2 of 3" in line


def test_the_difficulty_picks_the_class_tier(specs_file, capsys, monkeypatch):
    """`difficulty_above: 0.5` used to make an item stand; the reading now
    selects the tier, against the shipped policy (edit has three)."""
    stub(monkeypatch, answers(difficulty=3.0))          # score 3 of 3 levels -> 1.00
    _, out, _ = dispatch_(specs_file, capsys)
    line = row(out, "1a")
    assert "agrees: claude-opus-5-5, the cheapest of tier 3 of 3" in line
    assert "difficulty 1.00 -> tier 3 of 3" in line


def test_a_differing_suggestion_is_reported_and_not_applied(specs_file, capsys, monkeypatch):
    stub(monkeypatch)
    tiers_stub(monkeypatch, ["mistral-small-2603"])
    before = specs_file.read_bytes()
    rc, out, _ = dispatch_(specs_file, capsys)
    assert rc == 0
    assert ("differs: suggest mistral-small-2603: the declaration is outside tier 1 of 1 "
            "(mistral-small-2603)") in row(out, "1a")
    assert "1 suggestion(s) differ" in out and "Nothing is applied" in out
    assert "n >= 30" in out
    assert specs_file.read_bytes() == before


def test_a_suggestion_equal_to_the_declaration_agrees(specs_file, capsys, monkeypatch):
    stub(monkeypatch)
    tiers_stub(monkeypatch, ["claude-opus-5-5"])
    _, out, _ = dispatch_(specs_file, capsys)
    assert "agrees: claude-opus-5-5, the cheapest of tier 1 of 1" in row(out, "1a")


def test_a_declaration_inside_the_tier_agrees_and_names_the_cheaper_one(specs_file, capsys,
                                                                     monkeypatch):
    stub(monkeypatch)
    tiers_stub(monkeypatch, ["mistral-small-2603", "claude-opus-5-5"])
    _, out, _ = dispatch_(specs_file, capsys)
    assert ("agrees: claude-opus-5-5 is in tier 1 of 1, and mistral-small-2603 is cheaper"
            in row(out, "1a"))
    assert "0 suggestion(s) differ" in out, "an admissible declaration is not a suggestion"


def test_nothing_available_in_the_tier_leaves_the_declaration(specs_file, capsys, monkeypatch):
    stub(monkeypatch)
    tiers_stub(monkeypatch, [], reason="prose whose only check is a reading")
    _, out, _ = dispatch_(specs_file, capsys)
    line = row(out, "1a")
    assert line.startswith("1a    claude-opus-5-5") and "stands: nothing available in tier 1 of 1" in line
    assert "prose whose only check is a reading" in line


def test_dry_run_makes_no_call(specs_file, capsys, monkeypatch):
    calls = stub(monkeypatch, raises=AssertionError("called under --dry-run"))
    rc, out, _ = dispatch_(specs_file, capsys, "--dry-run")
    assert rc == 0 and calls == []
    assert "1 call(s) to jev-1.13.0, ~" in out and "no call made" in out
    assert "stands: probes unknown" in row(out, "1a")
    assert "jev: " not in out


@pytest.mark.parametrize("kind,fatal,code", [("no-key", True, 2), ("bad-mode", True, 2),
                                             ("rate-limited", False, 3), ("transport", False, 3)])
def test_a_jev_failure_falls_back_to_the_rules_only_table(specs_file, capsys, monkeypatch,
                                                          kind, fatal, code):
    stub(monkeypatch, raises=jev.JevError(kind, "it failed", fatal=fatal))
    rc, out, err = dispatch_(specs_file, capsys)
    assert rc == code
    assert f"dispatch: no probes: {kind}: " in err and "Traceback" not in err
    assert "stands: probes unknown" in row(out, "1a")
    assert f"rules only, no probes ({kind})" in out


def test_an_answer_missing_from_the_response_is_unknown(specs_file, capsys, monkeypatch):
    resp = answers()
    del resp["answers"]["open_decision"]
    stub(monkeypatch, resp)
    _, out, _ = dispatch_(specs_file, capsys)
    r = row(out, "1a")
    assert "unknown" in r and "raised:" not in r, "an unknown answer raises nothing"
    assert "tier 1 of 3" in r, "and the difficulty still picks the tier"


def test_an_undispatchable_file_spends_nothing(tmp_path, capsys, monkeypatch):
    calls = stub(monkeypatch)
    rc, out, err = dispatch_(spec(tmp_path, drop="verify"), capsys)
    assert rc == 1 and calls == []
    assert "item 1a: verify: missing" in out


def test_dry_run_excludes_check(tmp_path, capsys):
    assert dispatch.main(["--check", "--dry-run", str(spec(tmp_path))]) == 2


# --- the audit's parts ----------------------------------------------------------

def test_the_config_classes_are_capabilities_task_classes():
    caps = dispatch.models.load_capabilities()
    cfg = dispatch.load_config(caps)
    assert set(cfg["probes"]["task_class"]["criteria"]) == set(caps["task_classes"])
    assert {k: q["type"] for k, q in cfg["probes"].items()} == dispatch.PROBES


def test_a_config_whose_classes_drift_is_refused(tmp_path):
    caps = {"task_classes": {"edit": {}, "read": {}}}
    with pytest.raises(dispatch.ConfigError):
        dispatch.load_config(caps)


CAT = {"models": [
    {"id": "dear", "kind": "chat", "cost": {"in": "5", "out": "20"}},
    {"id": "cheap", "kind": "chat", "cost": {"in": "0.1", "out": "0.5"}},
    {"id": "twin", "kind": "chat", "cost": {"in": "0.1", "out": "0.5"}},
    {"id": "typed", "kind": "typed", "cost": {"in": "0", "out": "0"}},
    {"id": "blind", "kind": "chat", "cost": {"in": "0", "out": "0"}}]}
RULES = {"capability_floor": 50.0, "reference_usage": {"default": {"input": 1000000, "output": 1000000}},
         "suggest_kinds": ["chat"]}


def test_the_wording_hash_moves_with_the_wording():
    caps = dispatch.models.load_capabilities()
    probes = dispatch.load_config(caps)["probes"]
    reworded = {**probes, "difficulty": {**probes["difficulty"], "instructions": "other"}}
    assert dispatch.probes_hash(probes) != dispatch.probes_hash(reworded)


# --- dispatch <SPECS.md>: the independence audit (3d) ---------------------------

def item(i, title, depends="—", model="claude-opus-5-5"):
    return (f"- [ ] **{i} · {title}.**\n  touches: engine/{i}.py\n  depends: {depends}\n"
            f"  model: {model}\n  verify: pytest\n")


def pair_stub(monkeypatch, yes=(), raises_on_pair=None):
    """Item calls get the usual answers; a pair call answers yes for the pairs
    whose state names an id in `yes` as a (A, B) tuple."""
    calls = []

    def fake_ask(state, questions, **kw):
        if dispatch.PAIR_KEY not in questions:
            return answers()
        calls.append(state)
        if raises_on_pair is not None:
            raise raises_on_pair
        a = state.split("item A:")[1].split("item B:")[0]
        b = state.split("item B:")[1]
        hit = any(f"**{x} " in a and f"**{y} " in b for x, y in yes)
        return {"model": "jev-1.13.0", "usage": {"input_tokens": 100, "output_tokens": 5},
                "answers": {dispatch.PAIR_KEY: {"type": "noul", "noul": 0.81 if hit else 0.12}}}
    monkeypatch.setattr(dispatch.jev, "ask", fake_ask)
    return calls


@pytest.fixture
def wide(tmp_path):
    """Four independent items in one wave (6 pairs), plus a user item."""
    p = tmp_path / "SPECS.md"
    p.write_text(item("1a", "parser") + item("1b", "writer") + item("1c", "cli")
                 + item("1d", "docs", model="user") + item("2a", "later", depends="1a"))
    return p


def test_independence_pair_count_is_n_choose_2_and_user_items_are_members(wide, capsys, monkeypatch):
    calls = pair_stub(monkeypatch)
    rc, out, _ = dispatch_(wide, capsys)
    assert rc == 0 and len(calls) == 6
    assert "same-wave pairs: 6 pair(s), 0 conflict(s)" in out
    assert any("1d" in c.split("item B:")[1] for c in calls)


def test_independence_pair_is_in_file_order(wide, capsys, monkeypatch):
    calls = pair_stub(monkeypatch)
    dispatch_(wide, capsys)
    first = calls[0]
    assert first.index("**1a ") < first.index("**1b ")
    assert all(c.index("item A:") < c.index("item B:") for c in calls)
    pairs = [(c.split("item B:")[0].split("**")[1][:2], c.split("item B:")[1].split("**")[1][:2])
             for c in calls]
    assert pairs == sorted(pairs)


def test_independence_yes_names_both_items_and_changes_nothing(wide, capsys, monkeypatch):
    before = wide.read_text()
    pair_stub(monkeypatch, yes=[("1a", "1c")])
    rc, out, _ = dispatch_(wide, capsys)
    assert rc == 0, "an audit finding is reported, never an exit code"
    assert "6 pair(s), 1 conflict(s)" in out
    line = next(l for l in out.splitlines() if l.startswith("  1a x 1c"))
    assert "YES 0.81" in line and "1c depends on something 1a produces" in line
    assert wide.read_text() == before
    assert "wave 1: 1a, 1b, 1c, 1d" in out


def test_independence_below_the_threshold_is_not_a_conflict(wide, capsys, monkeypatch):
    pair_stub(monkeypatch)
    _, out, _ = dispatch_(wide, capsys)
    assert "  1a x 1b  no 0.12" in out and "YES" not in out and "spec error" not in out


def test_independence_names_a_seeded_missed_dependency(tmp_path, capsys, monkeypatch):
    p = tmp_path / "SPECS.md"
    p.write_text(item("3c", "dispatch table") + item("4a", "uses the table"))
    pair_stub(monkeypatch, yes=[("3c", "4a")])
    _, out, _ = dispatch_(p, capsys)
    assert "  3c x 4a  YES 0.81  spec error: 4a depends on something 3c produces" in out
    assert "1 pair(s), 1 conflict(s)" in out


def test_independence_pair_failure_keeps_the_item_table(wide, capsys, monkeypatch):
    pair_stub(monkeypatch, raises_on_pair=jev.JevError("rate-limited", "slow", fatal=False))
    rc, out, err = dispatch_(wide, capsys)
    assert rc == 3 and "dispatch: no pair audit: rate-limited: slow" in err
    assert "Traceback" not in err
    assert "edit 0.90" in row(out, "1a") and "tier 1 of 3" in row(out, "1a")
    assert "same-wave pairs: 6 pair(s), not asked (rate-limited)" in out
    assert "probed" in out and "jev: 4 call(s) (4 item, 0 pair)" in out


def test_independence_dry_run_makes_no_pair_call(wide, capsys, monkeypatch):
    calls = stub(monkeypatch, raises=AssertionError("called under --dry-run"))
    rc, out, _ = dispatch_(wide, capsys, "--dry-run")
    assert rc == 0 and calls == []
    assert "same-wave pairs: 6 pair(s), none asked (--dry-run)" in out
    assert "  1a x 1b  unknown" in out and "jev: " not in out


def test_independence_leaves_the_existing_lines_unchanged(wide, capsys, monkeypatch):
    pair_stub(monkeypatch, yes=[("1a", "1b")])
    _, with_pairs, _ = dispatch_(wide, capsys)
    stub(monkeypatch)
    # a one-item-per-wave file has no pairs: the 3c output, line for line
    single = wide.with_name("single.md")
    single.write_text(ITEMS)
    _, base, _ = dispatch_(single, capsys)
    assert "same-wave pairs" not in base and "independence:" not in base
    kept = [l for l in with_pairs.splitlines() if l.startswith(("dispatch:", "  wave", "probes:",
                                                               "item ", "1a ", "1b ", "advisory only"))]
    assert any(l.startswith("advisory only (probed):") for l in kept)
    assert next(l for l in kept if l.startswith("probes:")).startswith("probes: 4 questions, wording hash 573fa7aa191cd6b0;")
    assert next(l for l in base.splitlines() if l.startswith("advisory only")).endswith("per task class.")


def test_independence_closing_line_counts_pair_calls(wide, capsys, monkeypatch):
    pair_stub(monkeypatch)
    _, out, _ = dispatch_(wide, capsys)
    assert "jev: 10 call(s) (4 item, 6 pair)" in out


def test_independence_wording_has_its_own_key_and_hash():
    cfg = dispatch.load_config(dispatch.models.load_capabilities())
    assert dispatch.probes_hash(cfg["probes"]) == "573fa7aa191cd6b0"
    assert "independent" not in cfg["probes"]
    assert cfg["independence"]["type"] == "noul"


@pytest.mark.parametrize("edit", [lambda t: t.replace("independence:\n  type: noul", "independence:\n  type: score"),
                                  lambda t: t.replace("independence:", "independence_x:", 1)])
def test_independence_config_missing_or_mistyped_is_refused(tmp_path, monkeypatch, edit):
    bad = tmp_path / "dispatch.yaml"
    bad.write_text(edit(dispatch.CONFIG.read_text()))
    with pytest.raises(dispatch.ConfigError):
        dispatch.load_config(dispatch.models.load_capabilities(), bad)


# --- dispatch <SPECS.md>: the egress and privacy limit (3e) ---------------------

SENTINEL = "SENTINEL-FILE-BODY-9f3a"
UNCHANGED = ("advisory only (probed): 1 suggestion(s) differ from the declared model, "
             "0 agree, 0 stand, 1 user.")


def declared(tmp_path, *lines, body=ITEMS):
    p = tmp_path / "SPECS.md"
    p.write_text("\n".join(lines) + "\n\n" + body if lines else body)
    return p


def opened_paths(monkeypatch):
    """Record every path the stdlib's file-opening entry points are given."""
    import builtins
    import io
    seen = []

    def wrap(real):
        def spy(file, *a, **kw):
            seen.append(str(file))
            return real(file, *a, **kw)
        return spy
    monkeypatch.setattr(builtins, "open", wrap(builtins.open))
    monkeypatch.setattr(io, "open", wrap(io.open))
    real_open = pathlib.Path.open

    def path_open(self, *a, **kw):
        seen.append(str(self))
        return real_open(self, *a, **kw)
    monkeypatch.setattr(pathlib.Path, "open", path_open)
    return seen


def test_egress_payload_is_the_specs_text_never_a_file_body(tmp_path, capsys, monkeypatch):
    secret = tmp_path / "secret.py"
    secret.write_text(SENTINEL)
    body = ITEMS.replace("touches: engine/x.py", f"touches: {secret}")
    path = declared(tmp_path, body=body)
    sent = []

    def fake_ask(state, questions, **kw):
        sent.append((state, questions))
        return answers()
    monkeypatch.setattr(dispatch.jev, "ask", fake_ask)
    seen = opened_paths(monkeypatch)
    rc, out, _ = dispatch_(path, capsys)
    assert rc == 0 and sent
    assert str(secret) in sent[0][0], "the path is item text and is sent"
    assert SENTINEL not in json_dump(sent)
    assert all(p != str(secret) for p in seen), "a touches: path is never opened"


def json_dump(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


def test_egress_payload_omits_the_file_level_declarations(tmp_path, capsys, monkeypatch):
    calls = stub(monkeypatch)
    dispatch_(declared(tmp_path, "egress: cloud", "privacy: US-unknown"), capsys)
    assert calls and not any("egress:" in s or "privacy:" in s for s, _ in calls)


def test_egress_none_makes_zero_calls_and_every_row_reads_unknown(tmp_path, capsys, monkeypatch):
    calls = stub(monkeypatch, raises=AssertionError("called under egress: none"))
    path = declared(tmp_path, "egress: none", body=item("2a", "first") + item("2b", "second"))
    rc, out, _ = dispatch_(path, capsys)
    assert rc == 0 and calls == []
    assert "declared: egress none" in out
    assert "wave 1: 2a, 2b" in out
    for i in ("2a", "2b"):
        r = row(out, i)
        assert r.split("stands")[0].count("unknown") == 4 and "stands: probes unknown" in r
    assert "same-wave pairs: 1 pair(s), not asked (egress: none)" in out
    assert "advisory only (rules only, egress: none)" in out
    assert "jev: " not in out and "independence:" not in out


def test_egress_none_with_dry_run_still_names_egress(tmp_path, capsys, monkeypatch):
    stub(monkeypatch, raises=AssertionError("called"))
    _, out, _ = dispatch_(declared(tmp_path, "egress: none"), capsys, "--dry-run")
    assert "advisory only (rules only, egress: none)" in out


def test_egress_none_suggests_local_models_only(monkeypatch):
    caps = dispatch.models.load_capabilities()
    cfg = dispatch.load_config(caps)
    cat = dispatch.models.load()
    allowed = dispatch.allowed_ids(cat, "none", None)
    local = {e["id"] for e in cat["models"] if e["jurisdiction"] == "local"}
    assert allowed == local and local
    mixed = [next(iter(local)), "claude-opus-5-5", "mistral-small-2603"]
    tiers_stub(monkeypatch, mixed)
    it = dispatch.specs.Item("1a", "t", False, 1)
    it.fields["model"] = "claude-opus-5-5"
    r = dispatch.audit(it, dispatch.Answers(difficulty=0.1, task_class="edit", open_decision=0.1,
                                                 verify_alone=0.8), cat, caps, cfg,
                       "user", allowed)
    assert r.suggested == mixed[0] and "tier 1 of 1" in r.reason


def test_egress_cloud_is_the_default_and_limits_nothing():
    assert dispatch.allowed_ids(dispatch.models.load(), "cloud", None) is None


@pytest.mark.parametrize("value", ["local", "", "None", "cloud please"])
def test_egress_invalid_value_exits_2_naming_the_line(tmp_path, capsys, monkeypatch, value):
    calls = stub(monkeypatch)
    path = declared(tmp_path, "# plan", f"egress: {value}")
    rc, out, err = dispatch_(path, capsys)
    assert rc == 2 and calls == []
    assert "line 2: egress:" in err and "cloud, none" in err


@pytest.mark.parametrize("key,a,b", [("egress", "cloud", "none"),
                                     ("privacy", "local", "US-unknown")])
def test_egress_duplicate_declaration_is_refused(tmp_path, capsys, monkeypatch, key, a, b):
    calls = stub(monkeypatch)
    path = declared(tmp_path, f"{key}: {a}", "", "prose", f"{key}: {b}")
    rc, _, err = dispatch_(path, capsys)
    assert rc == 2 and calls == []
    assert f"line 4: a second `{key}:`" in err and "line 1" in err


def test_egress_indented_lines_are_not_declarations(tmp_path, capsys, monkeypatch):
    stub(monkeypatch)
    body = ITEMS.replace("  verify: pytest\n", "  verify: pytest\n  egress: none\n", 1)
    rc, out, _ = dispatch_(declared(tmp_path, body=body), capsys)
    assert rc == 0 and "declared:" not in out and "jev: " in out


def class_of(model_id):
    cfg = dispatch.profiles.load()
    e = dispatch._entry(dispatch.models.load(), model_id)
    return dispatch.model_class(e, cfg, dispatch.profiles.active(cfg=cfg))


def test_egress_privacy_classes_are_computed_by_profiles(monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "private")
    assert class_of("mistral-small-2603") == "EU-no-training"
    assert class_of("deepseek-flash") == "CN-undisclosed"
    assert class_of("claude-opus-5-5") == "US-unknown"
    assert class_of("qwen3:4b-instruct-2507-q4_K_M") == "local"


def test_egress_privacy_restricts_the_eligible_set_to_the_exact_class(monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "private")
    cat = dispatch.models.load()
    for wanted in ("EU-no-training", "US-unknown", "local"):
        ids = dispatch.allowed_ids(cat, "cloud", wanted)
        assert ids and all(class_of(i) == wanted for i in ids)
        assert ids == {e["id"] for e in cat["models"] if class_of(e["id"]) == wanted}
    assert dispatch.allowed_ids(cat, "cloud", "no-such-class") == set()
    both = dispatch.allowed_ids(cat, "none", "EU-no-training")
    assert both == set(), "egress: none and an EU class share no model"


def test_egress_privacy_filters_the_suggestion_in_a_run(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "private")
    stub(monkeypatch)
    tiers_stub(monkeypatch, ["claude-sonnet-5-5", "mistral-small-2603"])
    _, out, _ = dispatch_(declared(tmp_path, "privacy: EU-no-training"), capsys)
    assert "declared: privacy EU-no-training" in out
    assert "differs: suggest mistral-small-2603" in row(out, "1a")


def test_egress_declared_model_violating_privacy_is_reported_not_applied(tmp_path, capsys,
                                                                       monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "private")
    stub(monkeypatch)
    tiers_stub(monkeypatch, ["mistral-small-2603"])
    path = declared(tmp_path, "privacy: EU-no-training")
    before = path.read_bytes()
    rc, out, _ = dispatch_(path, capsys)
    assert rc == 0
    assert ("1a: declared model claude-opus-5-5 is US-unknown; "
            "the spec declares privacy: EU-no-training") in out.splitlines()
    assert "1b:" not in out.split("privacy:")[1].split("same-wave")[0], "user item not probed"
    assert "privacy: 1 declared model(s) outside privacy: EU-no-training" in out
    assert "differs: suggest mistral-small-2603" in row(out, "1a")
    assert path.read_bytes() == before and "model: claude-opus-5-5" in path.read_text()


def test_egress_privacy_met_by_the_declared_model_reports_none(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "private")
    stub(monkeypatch)
    _, out, _ = dispatch_(declared(tmp_path, "privacy: US-unknown"), capsys)
    assert "privacy: 0 declared model(s) outside privacy: US-unknown" in out
    assert "declared model claude-opus-5-5 is" not in out


def test_egress_no_declaration_behaves_as_before(specs_file, tmp_path, capsys, monkeypatch):
    calls = stub(monkeypatch)
    rc, out, err = dispatch_(specs_file, capsys)
    assert rc == 0 and len(calls) == 1
    assert "declared:" not in out and "privacy:" not in out
    assert UNCHANGED in out
    assert "advisory only (probed)" in out and "jev: 1 call(s)" in out


def test_egress_a_declaration_adds_lines_and_rewrites_none(tmp_path, capsys, monkeypatch):
    stub(monkeypatch)
    plain = declared(tmp_path)
    _, base, _ = dispatch_(plain, capsys)
    _, out, _ = dispatch_(declared(tmp_path, "egress: cloud"), capsys)
    extra = [l for l in out.splitlines() if l not in base.splitlines()]
    assert extra == ["declared: egress cloud"] or all(
        l.startswith("dispatch:") or l == "declared: egress cloud" for l in extra)
    assert [l for l in base.splitlines() if l not in out.splitlines()
            and not l.startswith("dispatch:")] == []


def test_egress_declarations_do_not_change_check(tmp_path, capsys):
    path = declared(tmp_path, "egress: none", "privacy: local")
    rc, out = run(path, capsys)
    assert rc == 0
    assert out == f"dispatch --check: {path}: 2 open item(s), 0 finding(s)\n"
    items = dispatch.specs.parse(path.read_text(), set(dispatch.specs.load_contract()["fields"]))
    assert [i.id for i in items] == ["1a", "1b"]
    assert "egress" not in dispatch.specs.load_contract()["fields"]
    assert "privacy" not in dispatch.specs.load_contract()["fields"]


@INSTANCE
def test_egress_check_on_the_real_specs_still_reports_zero_findings(capsys):
    rc, out = run(REAL, capsys)
    assert rc == 0 and "0 finding(s)" in out
