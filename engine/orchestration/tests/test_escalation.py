"""8b: the escalation ladder -- effort first, then one tier up, then the user."""
from orchestration import escalation as E
from orchestration import labels as L

CAT = {"models": [
    {"id": "cheap", "cost": {"in": 1, "out": 1}, "capabilities": {"effort": "low, medium, high"}},
    {"id": "mid", "cost": {"in": 3, "out": 3}, "capabilities": {"effort": "low, medium, high"}},
    {"id": "big", "cost": {"in": 9, "out": 9}, "capabilities": {"effort": "low, medium, high"}},
    {"id": "local", "cost": {}, "capabilities": {}},
]}
SEL = {"classes": {"edit": [
    {"up_to_difficulty": "0.6", "models": "cheap", "effort": "medium"},
    {"up_to_difficulty": "0.85", "models": "mid, big", "effort": "high"},
    {"models": "big", "effort": "high"},
]}}
RULES = {"reference_usage": {"default": {"input": 1000000, "output": 1000000}}}


def row(model, effort, passed):
    return {"source": "verify", "specs": "S.md", "item": "1a",
            "ran_model": model, "effort": effort, "passed": passed}


def step(hist, cls="edit"):
    return E.next_step(hist, task_class=cls, cat=CAT, sel=SEL, caps={}, rules=RULES)


def test_escalation_waits_for_two_failures():
    assert step([row("cheap", "medium", False)]).rung == "retry"
    assert step([row("cheap", "medium", False), row("cheap", "medium", True)]).rung == "retry"


def test_escalation_raises_effort_first():
    s = step([row("cheap", "medium", False)] * 2)
    assert (s.rung, s.model, s.effort) == ("effort", "cheap", "high")


def test_escalation_then_steps_one_tier_to_its_cheapest_member():
    h = [row("cheap", "medium", False)] * 2 + [row("cheap", "high", False)] * 2
    s = step(h)
    assert (s.rung, s.model, s.effort) == ("tier", "mid", "high")


def test_escalation_raises_effort_once_per_model():
    """After an effort step failed, the next step is a tier, not another level."""
    h = [row("mid", "low", False)] * 2 + [row("mid", "medium", False)] * 2
    assert step(h).rung == "tier"


def test_escalation_unknown_levels_are_never_invented():
    s = step([row("local", "", False)] * 2)
    assert s.rung == "tier" and s.model == "cheap"


def test_escalation_stops_at_the_top_tier():
    h = [row("big", "medium", False)] * 2 + [row("big", "high", False)] * 2
    assert step(h).rung == "user"


def test_escalation_counts_only_this_item():
    other = dict(row("cheap", "medium", False), item="2b")
    assert E.history([other, row("cheap", "medium", False)], "S.md", "1a") == \
        [row("cheap", "medium", False)]


def test_escalation_verify_prints_the_ladder_on_failure(tmp_path):
    specs = tmp_path / "S.md"
    specs.write_text("- [ ] **1a · x.** y\n  touches: a\n  depends: none\n"
                     "  model: cheap\n  verify: false\n")
    path, out = tmp_path / "labels.jsonl", []
    seen = []
    for _ in range(2):
        L.verify(specs, "1a", path=path, ran="cheap", session=tmp_path / "none.jsonl",
                 cwd=tmp_path, out=out.append, effort="medium", task_class="edit",
                 ladder=lambda h, c: seen.append((len(h), c)) or "LADDER")
    assert seen == [(1, "edit"), (2, "edit")]
    assert [r["effort"] for r in L.read(path)] == ["medium", "medium"]
    assert out.count("LADDER") == 2


def test_effort_by_names_a_members_own_level():
    """deepseek-flash lacks `medium`; pi clamps it up to `high`, so the tier
    declares that rather than letting --check pass a request pi rewrites."""
    from orchestration import selection as S
    t = {"models": "sonnet, flash", "effort": "medium", "effort_by": "flash=high"}
    assert S.effort_of(t) == "medium" and S.effort_of(t, "sonnet") == "medium"
    assert S.effort_of(t, "flash") == "high"
