"""Stage 2 -- Aggregate: the adopt-on-first-use (Loop D) opaque proposal, and
its dismissal wiring.

Only the adoption path is covered here -- `use_count`/`last_used` writing and
verification-history bookkeeping are exercised elsewhere; this file is about
whether a dismissed "no, don't adopt X" actually suppresses the nightly
re-proposal, which is the gap this test closes.
"""
import datetime as dt

import pytest

from consolidation import ledger, pass_ctx
from consolidation.stages import aggregate


@pytest.fixture
def ctx(tmp_path):
    agents = tmp_path / "agents"
    (agents / "skills").mkdir(parents=True)
    (agents / "knowledge").mkdir()
    return pass_ctx.Pass(agents, tmp_path / "data", False, dt.date(2026, 9, 8))


def _usage(base, skill, *, signal="model", n=1):
    for _ in range(n):
        ledger.append(base, ledger.USAGE,
                     {"ts": "2026-09-07T00:00:00Z", "harness": "claude",
                      "skill": skill, "session": "s", "cwd": "/x",
                      "signal": signal, "caller": "user", "terms": []})


def test_an_unknown_skill_is_proposed_for_adoption(ctx):
    _usage(ctx.base, "new-skill", signal="model")
    aggregate.run(ctx)
    props = [p for p in ctx.proposals if p.kind == "adopt"]
    assert [p.target for p in props] == ["new-skill"]
    assert props[0].target_kind == "opaque"


def test_a_dismissed_adoption_is_not_reproposed(ctx):
    _usage(ctx.base, "new-skill", signal="model")
    ledger.record_dismissal(ctx.base, ctx.repo, "new-skill", "adopt",
                            target_kind="opaque")
    aggregate.run(ctx)
    assert not [p for p in ctx.proposals if p.kind == "adopt"]
    notes = [n for n in ctx.notes if "suppressed" in n.text]
    assert len(notes) == 1 and "new-skill" not in notes[0].text
    assert "1 adoption proposal" in notes[0].text


def test_a_lapsed_dismissal_lets_the_proposal_resurface(ctx, monkeypatch):
    _usage(ctx.base, "new-skill", signal="model")
    ledger.record_dismissal(ctx.base, ctx.repo, "new-skill", "adopt",
                            target_kind="opaque")
    # Move the dismissal's clock back past the TTL by rewriting the row.
    import json
    p = ctx.base / ledger.DISMISSALS
    row = json.loads(p.read_text().strip())
    row["ts"] = "2026-01-01T00:00:00Z"
    p.write_text(json.dumps(row) + "\n")
    aggregate.run(ctx)
    assert [p.target for p in ctx.proposals if p.kind == "adopt"] == ["new-skill"]


def test_dismissing_a_different_skill_does_not_suppress_this_one(ctx):
    _usage(ctx.base, "new-skill", signal="model")
    ledger.record_dismissal(ctx.base, ctx.repo, "other-skill", "adopt",
                            target_kind="opaque")
    aggregate.run(ctx)
    assert [p.target for p in ctx.proposals if p.kind == "adopt"] == ["new-skill"]


# ── use_count from reads (dev/memory/SPECS.md M2a) ──────────────────────────
# One use = one session that read the document, from the staged transcripts and
# the skill-invocation log, keyed by session so neither double-counts.

import json as _json

from knowledge import frontmatter


def _doc(agents, rel, **fm):
    p = agents / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    head = {"title": p.stem, "use_count": 0, "last_used": "", **fm}
    p.write_text("---\n" + "".join(f"{k}: {v}\n" for k, v in head.items())
                 + "---\n\nbody\n")
    return p


def _stage(base, name, *calls):
    """A staged Claude Code transcript whose assistant turn made `calls`."""
    d = base / "transcripts"
    d.mkdir(parents=True, exist_ok=True)
    blocks = [{"type": "tool_use", "name": tool, "input": inp} for tool, inp in calls]
    (d / name).write_text(_json.dumps(
        {"type": "assistant", "message": {"content": blocks}}) + "\n")


LEAF = "knowledge/system/harness/rtk.md"
SKILL = "skills/system/practice/handoff/SKILL.md"
ABS = "/home/u/06_SYSTEM/memory/"


@pytest.fixture
def tree_ctx(ctx):
    _doc(ctx.agents, LEAF)
    _doc(ctx.agents, SKILL, name="handoff")
    return ctx


def _fm(ctx, rel):
    return frontmatter.read(ctx.agents / rel)


def test_a_read_in_a_transcript_is_a_use_for_a_leaf_and_a_skill(tree_ctx):
    _stage(tree_ctx.base, "20261001T100000Z_claude_s1.jsonl",
           ("Read", {"file_path": ABS + LEAF}),
           ("Bash", {"command": "cat ~/06_SYSTEM/memory/" + SKILL}))
    _stage(tree_ctx.base, "20261003T100000Z_claude_s2.jsonl",
           ("Read", {"file_path": ABS + LEAF}))
    aggregate.run(tree_ctx)
    assert str(_fm(tree_ctx, LEAF)["use_count"]) == "2"
    assert str(_fm(tree_ctx, LEAF)["last_used"]) == "2026-10-03"
    assert str(_fm(tree_ctx, SKILL)["use_count"]) == "1"


def test_one_session_counts_once_across_files_and_sources(tree_ctx):
    # The same session staged twice, and also logged as a Skill invocation.
    for ts in ("20261001T100000Z", "20261001T120000Z"):
        _stage(tree_ctx.base, f"{ts}_claude_s1.jsonl",
               ("Read", {"file_path": ABS + SKILL}),
               ("Read", {"file_path": ABS + SKILL}))
    ledger.append(tree_ctx.base, ledger.USAGE,
                  {"ts": "2026-10-01T09:00:00Z", "harness": "claude",
                   "skill": "handoff", "session": "s1", "cwd": "/x",
                   "signal": "model", "caller": "user", "terms": []})
    ledger.append(tree_ctx.base, ledger.USAGE,
                  {"ts": "2026-10-05T09:00:00Z", "harness": "claude",
                   "skill": "handoff", "session": "s9", "cwd": "/x",
                   "signal": "model", "caller": "user", "terms": []})
    _stage(tree_ctx.base, "20261002T100000Z_claude_s2.jsonl",
           ("Read", {"file_path": ABS + SKILL}))
    aggregate.run(tree_ctx)
    fm = _fm(tree_ctx, SKILL)
    assert str(fm["use_count"]) == "3"          # s1 (3 records), s2, s9
    assert str(fm["last_used"]) == "2026-10-05"


def test_writing_a_document_is_not_using_it(tree_ctx):
    _stage(tree_ctx.base, "20261001T100000Z_claude_s1.jsonl",
           ("Edit", {"file_path": ABS + LEAF, "old_string": "a", "new_string": "b"}),
           ("Write", {"file_path": ABS + LEAF, "content": "x"}))
    aggregate.run(tree_ctx)
    assert str(_fm(tree_ctx, LEAF)["use_count"]) == "0"


def test_a_read_of_an_old_path_resolves_by_name(tree_ctx):
    # Before R3b the vault was `agents/`, and skills sat one folder higher.
    _stage(tree_ctx.base, "20260901T100000Z_claude_s1.jsonl",
           ("Read", {"file_path": "/home/u/06_SYSTEM/agents/skills/productivity/handoff/SKILL.md"}),
           ("Read", {"file_path": "/home/u/06_SYSTEM/agents/knowledge/meta/rtk.md"}))
    aggregate.run(tree_ctx)
    assert str(_fm(tree_ctx, SKILL)["use_count"]) == "1"
    assert str(_fm(tree_ctx, LEAF)["use_count"]) == "1"


def test_an_ambiguous_name_is_dropped_not_guessed(tree_ctx):
    _doc(tree_ctx.agents, "knowledge/areas/rtk.md")
    _stage(tree_ctx.base, "20261001T100000Z_claude_s1.jsonl",
           ("Read", {"file_path": "/home/u/06_SYSTEM/agents/knowledge/meta/rtk.md"}))
    aggregate.run(tree_ctx)
    assert str(_fm(tree_ctx, LEAF)["use_count"]) == "0"
    assert str(_fm(tree_ctx, "knowledge/areas/rtk.md")["use_count"]) == "0"


def test_the_count_is_recomputed_so_a_second_run_writes_nothing(tree_ctx):
    _stage(tree_ctx.base, "20261001T100000Z_claude_s1.jsonl",
           ("Read", {"file_path": ABS + LEAF}))
    aggregate.run(tree_ctx)
    before = len(tree_ctx.actions)
    aggregate.run(tree_ctx)
    assert len(tree_ctx.actions) == before
