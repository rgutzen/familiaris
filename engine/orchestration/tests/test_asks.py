"""The ask census (item 8c): what is counted, what is only a mention, and why the
difference decides whether judging the ask band is worth building."""
import json
import pathlib

import pytest

from orchestration import asks

SLUG = "--home-rg-06_SYSTEM--"
ASK = ("This 'path_read' call for tool 'bash' for path '~/03_ZETTEL/x' "
       "(rule '~/03_ZETTEL/*') requires approval, but no interactive UI is available.")
ASK_B = ("This 'bash -ic' call for tool 'bash' requires approval, "
         "but no interactive UI is available.")
DENY = "[pi-permission-system] Denied by policy: 'path' for tool 'bash' for path " \
       "'engine/harness/jev.py' (rule 'engine/harness/jev.py')."
TEMPLATE = ("This '<surface>' call <invokedAsClause> (rule '<pattern>') requires "
            "approval, but no interactive UI is available.")
PROSE = ("Item 3d is implemented, but I did not run the real read-only dispatch: the "
         "permission system blocked bash -ic (requires approval, but no interactive "
         "UI is available).")


def log(tmp_path, name, *texts, where="parent", role="toolResult", tool="bash"):
    # The real layout: one directory per cwd for a parent session, and a single
    # `pi-agent/` for the children.
    d = tmp_path / (SLUG if where == "parent" else "pi-agent")
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    with p.open("w") as fh:
        for t in texts:
            fh.write(json.dumps({"type": "message", "message": {
                "role": role, "toolName": tool,
                "content": [{"type": "text", "text": t}]}}) + "\n")
        fh.write(json.dumps({"type": "message", "message": {
            "role": "assistant", "content": [{"type": "text", "text": ASK}]}}) + "\n")
    return p


def test_asks_an_event_needs_the_renderer_s_shape_not_just_the_phrase(tmp_path):
    """A quote of the phrase is not an ask: a source file read, a child's report of
    being blocked, this module's own test fixtures. That distinction is the whole
    instrument, so it is pinned first."""
    log(tmp_path, "a.jsonl", ASK, ASK_B, DENY, TEMPLATE, PROSE)
    events, mentions = asks.census(asks.logs(10, tmp_path))
    assert [e.klass for e in events] == ["A (a rule asked)", "B (no rule matched)",
                                         "A (a rule asked)"]
    assert [e.kind for e in events] == ["unavailable", "unavailable", "denied"]
    assert events[0].rule == "~/03_ZETTEL/*" and events[0].surface == "path_read"
    assert events[1].rule == "" and events[1].surface == "bash -ic"
    assert events[2].surface == "path"
    assert len(mentions) == 2, "the template and the child's prose line"
    assert all(m.text for m in mentions)


def test_asks_a_source_file_quote_and_a_child_report_are_mentions(tmp_path):
    log(tmp_path, "b.jsonl", "Denied by policy: ${identification(payload, budget,", PROSE)
    events, mentions = asks.census(asks.logs(10, tmp_path))
    assert events == [] and len(mentions) == 2
    assert mentions[0].text.startswith("Denied by policy: ${")


def test_asks_the_parent_sessions_and_the_children_are_both_read_newest_first(tmp_path):
    log(tmp_path, "old.jsonl", ASK)
    log(tmp_path, "child.jsonl", ASK_B, where="child")
    p = log(tmp_path, "new.jsonl", DENY)
    import os
    os.utime(p, (2_000_000_000, 2_000_000_000))
    pairs = asks.logs(2, tmp_path)
    assert [x[0].name for x in pairs] == ["new.jsonl", "child.jsonl"]
    assert [x[1] for x in pairs] == ["parent", "child"]
    assert asks.logs(10, tmp_path)[0][0].name == "new.jsonl"


def test_asks_only_tool_results_are_read(tmp_path):
    """The assistant's own text can contain the phrase; only a tool result can
    carry a decision."""
    log(tmp_path, "c.jsonl", role="assistant", tool="")
    events, mentions = asks.census(asks.logs(10, tmp_path))
    assert (events, mentions) == ([], [])


def test_asks_the_summary_splits_the_classes_and_names_the_child_case(tmp_path):
    log(tmp_path, "d.jsonl", ASK, DENY)
    log(tmp_path, "e.jsonl", ASK_B, where="child")
    events, mentions = asks.census(asks.logs(10, tmp_path))
    s = asks.summarise(events, mentions)
    assert (s["events"], s["class_A"], s["class_B"]) == (3, 2, 1)
    assert s["child"] == 1 and s["parent"] == 2
    assert s["rules"] == {"~/03_ZETTEL/*": 1, "engine/harness/jev.py": 1}
    assert s["unavailable"] == 2 and s["denied"] == 1


def test_asks_the_report_says_not_sized_when_class_b_is_empty(tmp_path, capsys):
    """The verdict the item exists to produce: with no class-B event the honest
    answer is "not measured", and the instrument's blind spots are named."""
    log(tmp_path, "f.jsonl", ASK, DENY)
    assert asks.main(["--replay", "10", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "B (no rule matched) 0" in out
    assert "NOT measured" in out
    assert "decision log" in out and "an ask the user answered" in out


def test_asks_the_json_summary_and_the_usage_errors(tmp_path, capsys):
    log(tmp_path, "g.jsonl", ASK_B, where="child")
    assert asks.main(["--replay", "10", "--root", str(tmp_path), "--json"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["class_B"] == 1 and s["mentions"] == 0
    assert asks.main(["--replay", "0", "--root", str(tmp_path)]) == 2
    assert asks.main(["--replay", "5", "--root", str(tmp_path / "nowhere")]) == 2


def test_asks_the_real_logs_read_without_crashing():
    """Not an assertion about the numbers (they change): the item's verify is the
    printed census, and this pins only that the machine's own logs parse."""
    pairs = asks.logs(30)
    if not pairs:
        pytest.skip("no session logs on this machine")
    events, mentions = asks.census(pairs)
    s = asks.summarise(events, mentions)
    assert set(s) >= {"events", "class_A", "class_B", "mentions", "surfaces"}
    assert s["events"] == s["class_A"] + s["class_B"]
