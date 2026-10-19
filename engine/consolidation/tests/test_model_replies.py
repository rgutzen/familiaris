"""The two parsers that read what the model said.

These were the last untested code in the package, and they are the point where
a cloud reply becomes a file in the knowledge base. They are tested WHERE THEY
LIVE rather than merged behind a shared protocol: stage 1 parses two header
lines and keeps everything else as prose, stage 4 parses a repeating record
with an explicit terminator. The overlap is real but thin, and a shared parser
would need a flag for each difference.

Where a test locks in behaviour that is arguably wrong, it says so.
"""
from consolidation.stages import consolidate, replay


# ── stage 1: SLUG / TITLE, then prose ────────────────────────────────────────

def test_the_two_headers_are_read_and_the_rest_is_the_entry():
    slug, title, text = replay._parse(
        "SLUG: a-worked-session\nTITLE: Something was decided\n\n## What was done\nWork.\n")
    assert (slug, title) == ("a-worked-session", "Something was decided")
    assert text == "## What was done\nWork."


def test_headers_are_matched_case_insensitively_and_through_markdown():
    """A model asked for `SLUG:` sometimes returns `## SLUG:` or `**SLUG:**`.
    An unmatched header is not cosmetic: it names the file, titles the entry
    "Session", and leaves the header line sitting in the prose."""
    slug, title, text = replay._parse("## Slug: My Entry\n**TITLE:** Big News\nbody\n")
    assert (slug, title, text) == ("my-entry", "Big News", "body")


def test_plain_headers_still_win_when_both_forms_appear():
    slug, title, _ = replay._parse("SLUG: plain\nTITLE: Plain Title\nbody\n")
    assert (slug, title) == ("plain", "Plain Title")


def test_a_missing_title_falls_back_rather_than_failing():
    slug, title, text = replay._parse("no headers at all\njust prose\n")
    assert title == "Session" and slug == "session"
    assert text.startswith("no headers")


def test_a_missing_slug_is_derived_from_the_title():
    slug, title, _ = replay._parse("TITLE: A Long Title With Many Words Indeed Here\nbody\n")
    assert title.startswith("A Long Title")
    assert slug == "a-long-title-with-many-words", "six words, lowercased, hyphenated"


def test_a_header_further_down_the_reply_is_prose_not_a_header():
    """Only the first 8 lines are scanned, so a journal entry that QUOTES
    `SLUG:` in its body cannot hijack the filename."""
    reply = "TITLE: Real\n" + "\n".join(f"line {i}" for i in range(10)) \
            + "\nSLUG: not-a-header\n"
    slug, _, text = replay._parse(reply)
    assert slug == "real" and "SLUG: not-a-header" in text


def test_the_entry_body_is_stripped_of_surrounding_blank_lines():
    _, _, text = replay._parse("SLUG: x\nTITLE: y\n\n\n  body  \n\n\n")
    assert text == "body"


# ── stage 4: PROPOSAL … END records ──────────────────────────────────────────

REPLY = """Here is what I found, which is chatter and must be ignored.

PROPOSAL: extend the ollama leaf
TARGET: knowledge/tools/ollama-local.md
KIND: extend-leaf
WHY: the model list changed
BODY:
## Models

- one
  - indented
END

PROPOSAL: a second one
TARGET: knowledge/tools/other.md
KIND: new-leaf
WHY: because
BODY:
text
END
"""


def test_every_record_is_read_with_its_fields():
    props = consolidate._parse(REPLY).proposals
    assert [p["target"] for p in props] == ["knowledge/tools/ollama-local.md",
                                            "knowledge/tools/other.md"]
    assert [p["kind"] for p in props] == ["extend-leaf", "new-leaf"]
    assert props[0]["summary"] == "extend the ollama leaf"
    assert props[0]["why"] == "the model list changed"


def test_prose_before_the_first_record_is_ignored():
    assert len(consolidate._parse(REPLY)) == 2


def test_a_body_keeps_its_own_indentation():
    """The body becomes markdown in a knowledge leaf; stripping indentation
    would silently flatten a nested list."""
    body = consolidate._parse(REPLY).proposals[0]["body"]
    assert "\n  - indented" in body
    assert body.startswith("## Models")


def test_a_record_without_its_terminator_is_still_read():
    reply = consolidate._parse("PROPOSAL: p\nTARGET: t\nKIND: k\nBODY:\nsome text\n")
    assert len(reply) == 1 and reply.proposals[0]["body"] == "some text"


def test_a_new_record_flushes_the_previous_one_even_without_END():
    props = consolidate._parse(
        "PROPOSAL: first\nTARGET: a\nBODY:\nbody one\n"
        "PROPOSAL: second\nTARGET: b\nBODY:\nbody two\nEND\n").proposals
    assert [p["summary"] for p in props] == ["first", "second"]
    assert [p["body"] for p in props] == ["body one", "body two"]


def test_missing_fields_are_marked_unknown_never_guessed():
    props = consolidate._parse("PROPOSAL: p\nBODY:\ntext\nEND\n").proposals
    assert props[0]["target"] == "?" and props[0]["kind"] == "?"
    assert props[0]["why"] == ""


def test_a_record_with_no_body_is_kept_out_but_not_thrown_away():
    """A proposal whose body the model forgot is not usable -- there is nothing
    to put in a leaf -- but it is WORK THE MODEL DID, so it is handed back for
    the caller to report. It used to vanish into no report and no count."""
    reply = consolidate._parse(
        "PROPOSAL: forgot the body\nTARGET: t\nKIND: k\nWHY: w\nEND\n")
    assert reply.proposals == []
    assert [p["summary"] for p in reply.dropped] == ["forgot the body"]
    assert reply.dropped[0]["target"] == "t"


def test_a_good_record_beside_a_bodyless_one_still_lands():
    reply = consolidate._parse(
        "PROPOSAL: usable\nTARGET: a\nKIND: k\nBODY:\ncontent\nEND\n"
        "PROPOSAL: empty\nTARGET: b\nKIND: k\nEND\n")
    assert [p["summary"] for p in reply.proposals] == ["usable"]
    assert [p["summary"] for p in reply.dropped] == ["empty"]


def test_a_reply_the_caller_can_iterate_over_yields_only_usable_proposals():
    reply = consolidate._parse(REPLY)
    assert [p["kind"] for p in reply] == ["extend-leaf", "new-leaf"]


def test_an_empty_reply_is_no_proposals_not_an_error():
    for text in ("", "the model declined to propose anything", "NOTHING"):
        reply = consolidate._parse(text)
        assert reply.proposals == [] and reply.dropped == []


# ── and the caller says so ───────────────────────────────────────────────────

def _stage4_ctx(tmp_path, reply, monkeypatch):
    """Stage 4 with a canned model reply and nothing else to distract it."""
    import datetime as dt

    from consolidation import pass_ctx

    agents = tmp_path / "agents"
    (agents / "journal" / "2026" / "09").mkdir(parents=True)
    (agents / "knowledge").mkdir()
    (agents / "journal" / "2026" / "09" / "2026-09-03_a-session.md").write_text(
        "---\ndate: 2026-09-03\n---\n\n# A session\n\nSomething durable happened.\n")
    monkeypatch.setattr(consolidate.model, "available", lambda: True)
    monkeypatch.setattr(consolidate.model, "ask", lambda *a, **k: reply)
    ctx = pass_ctx.Pass(agents, tmp_path / "data", False, dt.date(2026, 9, 3))
    consolidate.run(ctx)
    return ctx


def test_stage_4_names_the_proposals_it_could_not_use(tmp_path, monkeypatch):
    ctx = _stage4_ctx(tmp_path, "PROPOSAL: forgot the body\nTARGET: knowledge/x.md\n"
                                "KIND: new-leaf\nWHY: w\nEND\n", monkeypatch)
    dropped = [n for n in ctx.notes if "no BODY" in n.text]
    assert len(dropped) == 1, "work the model did that nobody can use is reported"
    assert dropped[0].level == "warn"
    assert "knowledge/x.md" in dropped[0].text and "forgot the body" in dropped[0].text
    assert ctx.proposals == []


def test_stage_4_says_nothing_when_every_proposal_was_usable(tmp_path, monkeypatch):
    ctx = _stage4_ctx(tmp_path, "NOTHING\n", monkeypatch)
    assert not [n for n in ctx.notes if "no BODY" in n.text], "no cry-wolf note"


# ── decision/disagreement surfacing (exit criteria 10 & 11), and its dismissal
#    wiring ─────────────────────────────────────────────────────────────────────────────
# Runs before any journal entries or model call exist, so an EMPTY memory/
# tree is enough to exercise it -- `run()` returns early right after
# `_surface_decisions`, once it sees no recent entries.

def _decisions_ctx(tmp_path):
    import datetime as dt

    from consolidation import ledger, pass_ctx

    agents = tmp_path / "agents"
    agents.mkdir()
    return pass_ctx.Pass(agents, tmp_path / "data", False, dt.date(2026, 9, 8))


def test_an_unlanded_decision_is_proposed(tmp_path):
    from consolidation import ledger

    ctx = _decisions_ctx(tmp_path)
    did = ledger.record_decision(ctx.base, "decision", "use rebase", context="git")
    consolidate.run(ctx)
    props = [p for p in ctx.proposals if p.target == did]
    assert len(props) == 1 and props[0].kind == "decision"
    assert props[0].target_kind == "opaque"


def test_a_dismissed_decision_is_not_reproposed(tmp_path):
    from consolidation import ledger

    ctx = _decisions_ctx(tmp_path)
    did = ledger.record_decision(ctx.base, "decision", "use rebase", context="git")
    ledger.record_dismissal(ctx.base, ctx.repo, did, "decision", target_kind="opaque")
    consolidate.run(ctx)
    assert not [p for p in ctx.proposals if p.target == did]
    notes = [n for n in ctx.notes if n.stage == "4" and "suppressed" in n.text]
    assert len(notes) == 1 and "1 decision/disagreement proposal" in notes[0].text


def test_a_lapsed_decision_dismissal_lets_it_resurface(tmp_path):
    import json

    from consolidation import ledger

    ctx = _decisions_ctx(tmp_path)
    did = ledger.record_decision(ctx.base, "decision", "use rebase", context="git")
    ledger.record_dismissal(ctx.base, ctx.repo, did, "decision", target_kind="opaque")
    p = ctx.base / ledger.DISMISSALS
    row = json.loads(p.read_text().strip())
    row["ts"] = "2026-01-01T00:00:00Z"
    p.write_text(json.dumps(row) + "\n")
    consolidate.run(ctx)
    assert [p.target for p in ctx.proposals] == [did]


def test_a_decision_that_landed_is_not_proposed_regardless_of_dismissal(tmp_path):
    from consolidation import ledger

    ctx = _decisions_ctx(tmp_path)
    did = ledger.record_decision(ctx.base, "decision", "use rebase", context="git")
    # A knowledge leaf is what "landed" means now: MEMORY.md was deleted
    # 2026-09-04, so the durable surfaces are a leaf and a journal entry.
    (ctx.agents / "knowledge").mkdir(exist_ok=True)
    (ctx.agents / "knowledge" / "git.md").write_text(f"settled: {did}\n")
    consolidate.run(ctx)
    assert not ctx.proposals
