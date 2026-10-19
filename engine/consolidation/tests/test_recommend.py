"""The recommend stage: batching, the gate, and the shadow rule (items 2d-2h).

The load-bearing test here is the SHADOW one: a band must be displayed and must
not reorder anything for one cycle. Everything else is plumbing around it.
"""
import datetime as dt
import pathlib

import pytest

from harness import bands, jev, jev_schemas
from consolidation import pass_ctx, queue, report
from consolidation.stages import recommend


def _item(kind="dangling-link", target="knowledge-vs-skills", **kw):
    d = queue.as_dict(kind, target, "`related: voice` resolves to no leaf",
                      "reported, never deleted", "5a", "leaf", "2026-09-29")
    d.update(kw)
    return d


class _Ctx:
    """Enough of a Pass for the stage and the render."""

    def __init__(self, base, repo, dry_run=False, flags=frozenset()):
        self.base, self.repo = base, repo
        self.dry_run = dry_run
        self.flags = flags
        self.today = dt.date(2026, 9, 29)
        self.notes, self.actions = [], []
        self.stages_run, self.branch, self.aborted = [], "main", None
        self.quiet, self.fingerprint, self.head = False, "", ""

    @property
    def proposals(self):
        """The report renders from `ctx.proposals`; a real pass has them from
        the stages. Derived from the queue so the two agree about the ordinals."""
        out = []
        for i in queue.items(self.base) if self.base.exists() else []:
            out.append(pass_ctx.Proposal(stage=i.get("stage", ""), kind=i["kind"],
                                         target=i["target"], what=i.get("summary", ""),
                                         why=i.get("why", ""),
                                         target_kind=i.get("target_kind", "leaf")))
        return out

    def note(self, stage, text, level="note"):
        self.notes.append(pass_ctx.Note(stage, text, level))

    def act(self, *a):
        self.actions.append(pass_ctx.Action(*a))

    def loaded_tree(self):
        return None

    def log(self, msg):
        pass


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "memory").mkdir()
    return _Ctx(tmp_path / "base", tmp_path)


def _stub_ask(monkeypatch, answers_by_kind, *, model=jev.MODEL,
              usage=None, fail=None):
    """Stub the client. Returns the list of calls, for batching assertions.

    The stub resolves the KIND from the question object it was handed (by
    matching against the real schemas), so a test can key its answers by kind
    without the stage having to pass a kind through to the client -- which the
    real client does not do either.
    """
    calls = []
    by_hash = {jev_schemas.schema_hash(k): k for k in jev_schemas.SCHEMAS}

    def fake_ask(state, questions, key=None, model=model, timeout=None):
        qid = next(iter(questions))
        q = questions[qid]
        kind = by_hash.get(
            __import__("hashlib").sha256(
                __import__("json").dumps(q, sort_keys=True,
                                         ensure_ascii=False).encode()
            ).hexdigest()[:16])
        calls.append({"state": state, "qid": qid, "questions": questions,
                      "kind": kind})
        if fail is not None:
            raise fail
        ans = answers_by_kind.get(kind) or answers_by_kind.get("_default") \
            or {"type": "noul", "noul": 0.5}
        return {"model": model, "answers": {qid: ans},
                "usage": usage or {"input_tokens": 100, "output_tokens": 5}}

    monkeypatch.setattr(recommend.jev, "ask", fake_ask)
    monkeypatch.setattr(recommend.jev, "load_key", lambda *a, **k: "k")
    return calls


# ── the gate ─────────────────────────────────────────────────────────────────

def test_a_real_pass_does_not_call_jev_without_the_flag(ctx, monkeypatch):
    """A nightly job that starts billing on an upgrade is a job that gets
    switched off the first time someone reads the invoice."""
    queue.save(ctx.base, [_item()])
    calls = _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    assert recommend.run(ctx) is True
    assert calls == [], "no call without --with-jev"
    assert any("no cost was incurred" in n.text.lower() for n in ctx.notes)


def test_a_dry_run_makes_no_call_even_with_the_flag(ctx, monkeypatch):
    """A dry run writes nothing, so a paid answer would be thrown away."""
    ctx.dry_run = True
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    calls = _stub_ask(monkeypatch, {})
    recommend.run(ctx)
    assert calls == []


def test_a_dry_run_with_jev_reports_what_it_would_ask(ctx, monkeypatch):
    ctx.dry_run = True
    queue.save(ctx.base, [_item()])
    recommend.run(ctx)
    assert any("would be banded" in n.text for n in ctx.notes)


def test_the_flag_makes_the_call_and_records_the_cost(ctx, monkeypatch):
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}},
              usage={"input_tokens": 1_000_000, "output_tokens": 999})
    recommend.run(ctx)
    note = [n.text for n in ctx.notes if "banded" in n.text][0]
    assert "$0.042000" in note, note     # input only; output is free


# ── what it writes ───────────────────────────────────────────────────────────

def test_a_banded_item_carries_its_band_action_and_probability(ctx, monkeypatch, tmp_path):
    ctx.flags = frozenset({"--with-jev"})
    item = _item()
    queue.save(ctx.base, [item])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.95}})
    recommend.run(ctx)
    rec = queue.items(ctx.base)[0]["recommendation"]
    assert rec["band"] == bands.ACCEPT
    assert rec["probability"] == 0.95
    assert rec["action"] == jev_schemas.action("dangling-link")
    assert rec["model"] == jev.MODEL
    assert rec["schema_hash"] == jev_schemas.schema_hash("dangling-link")
    assert rec["threshold"] == {"accept_at": bands.DEFAULT.accept_at,
                                "drop_below": bands.DEFAULT.drop_below}


def test_a_noul_recommendation_records_no_confidence(ctx, monkeypatch):
    """The field is absent for a Noul, so `None` is the honest value and a number
    would be invented (PLAN.md §The answer shapes)."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    assert queue.items(ctx.base)[0]["recommendation"]["confidence"] is None


def test_the_recommendation_is_never_written_to_the_decision_ledger(ctx, monkeypatch):
    """A recommendation is not a decision. Writing one to the ledger would make
    `decide`'s record say the user resolved something they never saw."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    from consolidation import ledger
    assert ledger.read(ctx.base, ledger.DECISIONS).rows == []
    assert ledger.read(ctx.base, ledger.DISMISSALS).rows == []


def test_an_undeclared_kind_is_reported_and_not_asked(ctx, monkeypatch):
    """An undeclared kind is an error, not a default: it gets no recommendation
    rather than a generic question answered anyway."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item(kind="a-kind-nobody-declared")])
    calls = _stub_ask(monkeypatch, {})
    recommend.run(ctx)
    assert calls == []
    assert any("no question schema" in n.text and n.level == "error"
               for n in ctx.notes)


def test_a_failed_call_leaves_the_queue_intact_and_notes_it(ctx, monkeypatch):
    """Never fatal to the pass: a skipped recommendation is a queue with no
    recommendation, which `queue` and `decide` already handle."""
    ctx.flags = frozenset({"--with-jev"})
    item = _item()
    queue.save(ctx.base, [item])
    _stub_ask(monkeypatch, {}, fail=jev.JevError("rate-limited", "429"))
    assert recommend.run(ctx) is True
    assert queue.items(ctx.base)[0]["recommendation"] is None
    assert any("rate-limited" in n.text for n in ctx.notes)


def test_one_ask_per_item_so_the_answer_is_unambiguous(ctx, monkeypatch):
    """The question is per KIND; the state is per ITEM. Two items of one kind must
    produce two calls, or the answer's owner is ambiguous."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item(target="a"), _item(target="b")])
    calls = _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    assert len(calls) == 2
    assert calls[0]["qid"] != calls[1]["qid"]


def test_the_state_carries_the_targets_own_text(ctx, monkeypatch):
    """The question is about the artefact, not only about the pass's description
    of it."""
    ctx.flags = frozenset({"--with-jev"})
    (ctx.repo / "memory" / "knowledge-vs-skills.md").write_text("the leaf body\n")
    queue.save(ctx.base, [_item()])
    calls = _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    assert "the leaf body" in calls[0]["state"]


def test_an_opaque_target_says_it_has_no_file(ctx, monkeypatch):
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item(kind="decision", target="dec-123",
                                target_kind="opaque")])
    calls = _stub_ask(monkeypatch, {"decision": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    assert "no file" in calls[0]["state"]


# ── the shadow rule: displayed, not steering (2h) ────────────────────────────

def test_the_stage_bands_tonights_queue_not_last_nights(ctx, monkeypatch):
    """The bug this test exists for: `recommend` used to run BEFORE the queue was
    rebuilt from tonight's proposals. It therefore banded LAST night's item set,
    and the rebuild then replaced it -- every item new tonight was banded nowhere
    and lost its recommendation in the merge. The symptom was unbanded items and
    no cost line, which reads like a skipped call.

    Asserted here as a property of the stage: every open item present when it
    runs gets a recommendation, including one that did not exist before.
    """
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item(target="old"), _item(target="new")])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    recs = {i["target"]: i.get("recommendation") for i in queue.items(ctx.base)}
    assert recs["new"] is not None, "a newly-added item was left unbanded"
    assert recs["old"] is not None


def test_a_recommendation_survives_the_queue_rebuild(ctx, monkeypatch):
    """The other half: `merge` must carry a recommendation forward, or the
    rebuild that follows the band would wipe it."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    fresh = [queue.as_dict("dangling-link", "knowledge-vs-skills", "newer wording",
                           "why", "5a", "leaf", "2026-09-30")]
    merged = queue.merge(queue.items(ctx.base), fresh, "2026-09-30")
    assert merged[0]["recommendation"] is not None
    assert merged[0]["summary"] == "newer wording"      # wording still updates


def test_the_gate_notes_land_where_the_report_can_carry_them(ctx, monkeypatch):
    """2g: the cost line is part of the night's RECORD, not only a console."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    recommend.run(ctx)
    out = report.render(ctx)
    assert "banded" in out and "$" in out


def test_the_cost_line_survives_the_note_cap(ctx, monkeypatch):
    """The 8b cost note must appear in the DEFAULT report, not only `--full`.

    With a few dozen stage-1 skip notes, MAX_LISTED pushed it out of the default
    render -- so a reader who never opens `--full` would never see what the night
    cost. Same class as the ordinal truncation: a cap hiding an entry point.
    """
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.9}})
    # bury it under more notes than the cap, as a real night does
    for i in range(30):
        ctx.note("1", f"transcript {i} too little prose to distil")
    recommend.run(ctx)
    out = report.render(ctx)                       # NOT full
    assert "banded" in out, "the cost line was truncated out of the default report"
    assert "$" in out


def test_the_note_cap_still_caps_ordinary_notes():
    """`_uncappable` must stay narrow, or the cap stops keeping the report to a
    screen."""
    ctx = _Ctx(pathlib.Path("/nonexistent"), pathlib.Path("/nonexistent"))
    for i in range(20):
        ctx.note("1", f"skip {i}")
    out = report.render(ctx)
    assert "... and" in out and "more" in out


def test_a_band_does_not_reorder_the_report(ctx, monkeypatch):
    """The shadow rule. A scoring-derived proposal that starts steering on
    unvalidated constants fails silently -- the same reason M2 kept its ranking
    constants report-only."""
    ctx.flags = frozenset({"--with-jev"})
    # 'a' banded accept, 'z' would band drop; the ROW order must stay a-then-...
    queue.save(ctx.base, [_item(target="z"), _item(target="a")])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.01}})
    recommend.run(ctx)
    items = queue.items(ctx.base)
    assert items[0]["target"] == "z", "the queue order changed"
    assert items[0]["recommendation"]["band"] == bands.DROP


def test_the_report_shows_the_recommendation_with_its_probability(ctx, monkeypatch):
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item()])
    _stub_ask(monkeypatch, {"dangling-link": {"type": "noul", "noul": 0.91}})
    recommend.run(ctx)
    items = queue.items(ctx.base)
    out = report.render(ctx)
    assert "Recommendations (displayed; ordering unchanged)" in out
    assert "p 0.91" in out


def test_an_item_with_no_recommendation_prints_no_recommendation_line(ctx):
    queue.save(ctx.base, [_item()])
    out = report.render(ctx)
    assert "Recommendations" not in out, "a blank section reads as 'nothing judged'"


def test_a_promoted_kind_shows_ask_and_cannot_be_defaulted_away(ctx, monkeypatch):
    """Ask-only means the recommendation is DISPLAYED and cannot be banded -- not
    that the item is unasked."""
    ctx.flags = frozenset({"--with-jev"})
    queue.save(ctx.base, [_item(kind="supersede-leaf", target="knowledge/a.md")])
    _stub_ask(monkeypatch, {"supersede-leaf": {"type": "noul", "noul": 1.0}})
    recommend.run(ctx)
    rec = queue.items(ctx.base)[0]["recommendation"]
    assert rec["band"] == bands.ASK
    assert rec["probability"] == 1.0, "the number is still shown"
