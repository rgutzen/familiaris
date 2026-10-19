"""Stage 1's two invariants: a dry run writes nothing, and a transcript is
distilled once.

The second test is the one that matters. `--dry-run --with-model` exists to
exercise the model call, and the first version of that wiring wrote three
journal entries into the tree during a dry run, because the write was guarded
only by the early return the flag bypasses.
"""
import datetime as dt
import json

import pytest

from consolidation import pass_ctx
from consolidation.stages import replay

ENTRY = """SLUG: a-worked-session
TITLE: Something was decided

## What was done
Work happened, at a path, with a command.

## Decisions taken
One decision, recorded verbatim.
"""


@pytest.fixture
def staged(tmp_path):
    """One staged transcript with enough prose to be worth distilling."""
    d = tmp_path / "data" / "transcripts"
    d.mkdir(parents=True)
    prose = "We investigated the failing unit and found the cause. " * 8
    rows = [
        {"type": "user", "cwd": "/home/rg/06_SYSTEM", "gitBranch": "main",
         "sessionId": "sess-1", "timestamp": "2026-09-03T10:00:00Z",
         "message": {"content": prose}},
        {"type": "assistant", "sessionId": "sess-1",
         "message": {"content": [{"type": "text", "text": prose}]}},
    ]
    (d / "20260903T100000Z_claude_sess-1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    (tmp_path / "agents" / "journal").mkdir(parents=True)
    return tmp_path


def _ctx(tmp_path, *, dry, flags=frozenset()):
    return pass_ctx.Pass(tmp_path / "agents", tmp_path / "data", dry,
                         dt.date(2026, 9, 3), flags=flags)


@pytest.fixture
def model(monkeypatch):
    """A model that answers instantly and counts how often it was asked."""
    calls = []

    def ask(prompt, timeout=None):
        calls.append(prompt)
        return ENTRY

    monkeypatch.setattr(replay.model, "ask", ask)
    monkeypatch.setattr(replay.model, "available", lambda: True)
    return calls


def _entries(tmp_path):
    return sorted(p.name for p in (tmp_path / "agents" / "journal").rglob("*.md"))


def test_a_plain_dry_run_makes_no_model_call_and_writes_nothing(staged, model):
    replay.run(_ctx(staged, dry=True))
    assert model == [] and _entries(staged) == []


def test_with_model_calls_the_model_and_still_writes_nothing(staged, model):
    ctx = _ctx(staged, dry=True, flags=frozenset({"--with-model"}))
    replay.run(ctx)
    assert len(model) == 1, "the flag exists to exercise the call"
    assert _entries(staged) == [], "a dry run leaves the tree byte-identical"
    assert any("DISCARDED" in n.text for n in ctx.notes)
    assert ctx.actions == [], "nothing was done, so nothing is claimed"


def test_a_real_run_writes_one_entry_citing_its_transcript(staged, model):
    ctx = _ctx(staged, dry=False)
    replay.run(ctx)
    assert _entries(staged) == ["2026-09-03_a-worked-session.md"]
    written = next((staged / "agents" / "journal").rglob("*.md")).read_text()
    assert "transcript: 20260903T100000Z_claude_sess-1.jsonl" in written
    assert "session: sess-1" in written
    assert len(ctx.actions) == 1


def test_a_transcript_already_journalled_is_not_distilled_twice(staged, model):
    replay.run(_ctx(staged, dry=False))
    replay.run(_ctx(staged, dry=False))
    assert len(model) == 1, "an interrupted night resumes, it does not duplicate"
    assert len(_entries(staged)) == 1


def test_a_pi_shaped_transcript_is_distilled_like_a_claude_one(staged, model):
    """Same stage, a different harness's line shape (`type: \"message\"`
    envelopes, role under `message.role`, `toolCall` blocks) -- staged
    entirely by capture.py copying Pi's real per-session file verbatim."""
    d = staged / "data" / "transcripts"
    prose = "We investigated the failing unit and found the cause. " * 8
    rows = [
        {"type": "session", "version": 3, "id": "sess-pi",
         "timestamp": "2026-09-03T12:00:00Z", "cwd": "/home/rg/06_SYSTEM"},
        {"type": "message", "id": "u1",
         "message": {"role": "user", "content": [{"type": "text", "text": prose}]}},
        {"type": "message", "id": "a1",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": prose},
             {"type": "toolCall", "name": "bash", "arguments": {"command": "pytest"}},
         ]}},
    ]
    (d / "20260903T120000Z_pi_sess-pi.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    ctx = _ctx(staged, dry=False)
    replay.run(ctx)
    entries = _entries(staged)
    assert len(entries) == 2, "the pre-staged claude transcript plus this one"
    pi_entry = next(p for p in (staged / "agents" / "journal").rglob("*.md")
                     if "session: sess-pi" in p.read_text())
    written = pi_entry.read_text()
    assert "transcript: 20260903T120000Z_pi_sess-pi.jsonl" in written
    assert "cwd: /home/rg/06_SYSTEM" in written


def test_a_transcript_from_a_personal_area_never_reaches_the_model(staged, model, tmp_path):
    d = staged / "data" / "transcripts"
    rows = [{"type": "user", "cwd": "/home/rg/02_AREAS/H_Health/notes",
             "sessionId": "sess-2", "timestamp": "2026-09-03T11:00:00Z",
             "message": {"content": "private " * 100}}]
    (d / "20260903T110000Z_claude_sess-2.jsonl").write_text(json.dumps(rows[0]) + "\n")
    ctx = _ctx(staged, dry=False)
    replay.run(ctx)
    assert len(model) == 1, "only the 06_SYSTEM transcript was sent"
    assert any("NOT sent to the cloud model" in n.text for n in ctx.notes)


# ── `touches:` is written at distill time (C2, SPECS O5b) ───────────────────

def test_the_written_entry_carries_the_subjects_its_session_touched(staged, model):
    """The facet lives in the RECORD, not in the search index -- which is the
    whole point of the route the user chose: the index is a disposable cache,
    and an entry that carries its own `touches:` cannot lose it when a
    transcript is pruned."""
    d = staged / "data" / "transcripts"
    p = d / "20260903T100000Z_claude_sess-1.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines()]
    rows.append({"type": "assistant", "sessionId": "sess-1", "message": {"content": [
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/home/rg/06_SYSTEM/engine/consolidation/run.py"}},
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "cd ~/06_SYSTEM && git add engine/knowledge/journal_index.py"}},
    ]}})
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    replay.run(_ctx(staged, dry=False))
    written = next((staged / "agents" / "journal").rglob("*.md")).read_text()
    # Register order, so two runs cannot write the same claim two ways.
    assert "touches: [knowledge, consolidation]\n" in written
    assert written.index("tags: []") < written.index("touches:")


def test_an_entry_whose_transcript_named_nothing_omits_the_key(staged, model):
    """Empty is a real answer and the common one. An absent key says it; an
    empty `touches: []` on every entry would be noise, and would make "not
    labelled" and "labelled with nothing" the same thing on disk."""
    replay.run(_ctx(staged, dry=False))
    written = next((staged / "agents" / "journal").rglob("*.md")).read_text()
    assert "touches" not in written


def test_touches_is_empty_for_a_reduced_transcript_and_the_run_says_so(staged, model):
    """`opencode_extract` and `hermes_extract` keep the tool NAME and drop the
    arguments, so a session on those harnesses yields no paths. The stage
    reports the count rather than leaving silence to be read as a fact."""
    rows = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "bash"}]}}]
    (staged / "data" / "transcripts" / "20260903T130000Z_opencode_o1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    ctx = _ctx(staged, dry=False)
    replay.run(ctx)
    assert any("carry no `touches:`" in n.text for n in ctx.notes)


def test_touches_reads_a_path_spelled_either_way(tmp_path):
    """Absolute and repo-relative spellings are the same file -- the rule
    `pointers.normalise` already owns, reused rather than restated."""
    d = tmp_path / "data" / "transcripts"
    d.mkdir(parents=True)
    rows = [{"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "engine/host/pazras-utils.sh"}},
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/home/rg/06_SYSTEM/engine/host/pazras-aliases.sh"}},
    ]}}]
    p = d / "x.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert replay._touches(p) == ("host",)
