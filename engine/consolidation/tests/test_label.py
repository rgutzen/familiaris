"""Step 3a: the labelling proposal, its batch item, and the outlier split.

THE LOAD-BEARING TESTS HERE ARE THE TWO THAT DEFINE THE SHAPE:

  * one batch item, carrying its count and a sample -- never N numbered rows;
  * a low-confidence member gets its OWN NUMBERED ITEM, never a hidden field.

Everything else is plumbing around those two. The third one that matters is
negative: `tags:` is never written and never proposed, because the concept layer
staying uncontrolled is the whole reason the category layer is allowed to exist
(`config/knowledge/facets.yaml`, `ontology PLAN` §The cognitive layering).
"""
import datetime as dt
import json

import pytest

from harness import bands, jev, jev_schemas
from knowledge import ontology
from consolidation import pass_ctx, queue
from consolidation.stages import label, recommend


# ── the fixture corpus ───────────────────────────────────────────────────────

def _entry(root, name, *, tags=None, subject=None, title="A session",
           frontmatter=True):
    p = root / "journal" / "2026" / "09" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    if not frontmatter:
        p.write_text("no frontmatter here\n")
        return p
    fm = [f"title: {title}", "date: 2026-09-29"]
    if subject is not None:
        fm.append(f"subject: {subject}")
    fm.append(f"tags: [{', '.join(tags)}]" if tags else "tags: []")
    p.write_text("---\n" + "\n".join(fm) + "\n---\n\n## What happened\n\nbody\n")
    return p


class _Ctx:
    """Enough of a Pass for a proposal-only stage and for `recommend`."""

    def __init__(self, tmp_path):
        self.repo = tmp_path
        self.agents = tmp_path / "agents"
        self.base = tmp_path / "base"
        self.agents.mkdir(exist_ok=True)
        self.dry_run = False
        self.flags = frozenset({"--with-jev"})
        self.today = dt.date(2026, 9, 30)
        self.notes, self.actions, self.proposals = [], [], []
        self.stages_run, self.branch, self.aborted = [], "main", None
        self.quiet, self.fingerprint, self.head = False, "", ""

    propose = pass_ctx.Pass.propose
    note = pass_ctx.Pass.note

    def log(self, msg):
        pass

    def loaded_tree(self):
        return None


@pytest.fixture
def ctx(tmp_path):
    return _Ctx(tmp_path)


def _stub(monkeypatch, answer):
    """Stub the client. `answer` may be a callable taking the member's state."""
    calls = []

    def fake_ask(state, questions, key=None, model=jev.MODEL, timeout=None):
        calls.append({"state": state, "questions": questions})
        a = answer(state) if callable(answer) else answer
        return {"model": jev.MODEL, "answers": {next(iter(questions)): a},
                "usage": {"input_tokens": 100, "output_tokens": 5}}

    monkeypatch.setattr(recommend.jev, "ask", fake_ask)
    monkeypatch.setattr(recommend.jev, "load_key", lambda *a, **k: "k")
    return calls


def _choice(winner, p, options=None):
    probs = {winner: p}
    for o in (options or ["tree", "harness"]):
        probs.setdefault(o, (1 - p) / 2)
    return {"type": "choice", "choice": winner, "probabilities": probs,
            "confidence": 0.7}


# ── the population ───────────────────────────────────────────────────────────

def test_the_population_is_entries_with_no_subject_and_no_tags(ctx):
    _entry(ctx.agents, "a.md")
    _entry(ctx.agents, "b.md")
    _entry(ctx.agents, "c.md", subject="pass")
    _entry(ctx.agents, "d.md", tags=["memory", "pass"])
    _entry(ctx.agents, "e.md", frontmatter=False)
    refs = [m["ref"] for m in label.population(ctx.agents)]
    assert refs == ["journal/2026/09/a.md", "journal/2026/09/b.md"]


def test_the_hand_tagged_entries_are_held_out_of_the_population(ctx):
    """3b scores against them. A run that had already seen them could not be
    scored against them -- that is the whole point of holding them back."""
    _entry(ctx.agents, "a.md")
    _entry(ctx.agents, "tagged.md", tags=["memory", "pass"])
    assert [m["ref"] for m in label.population(ctx.agents)] == \
        ["journal/2026/09/a.md"]
    held = label.held_out(ctx.agents)
    assert [m["ref"] for m in held] == ["journal/2026/09/tagged.md"]
    assert held[0]["tags"] == ["memory", "pass"]


def test_an_empty_tags_list_does_not_count_as_labelled(ctx):
    """`tags: []` parses to `[]`; treating it as present would empty the
    population and report a fully labelled corpus that does not exist."""
    _entry(ctx.agents, "a.md", tags=[])
    assert len(label.population(ctx.agents)) == 1


def test_reports_and_routers_are_not_episodes(ctx):
    _entry(ctx.agents, "a.md")
    (ctx.agents / "journal" / "CONTEXT.md").write_text(
        "---\ntitle: router\ntags: []\n---\n")
    rep = ctx.agents / "journal" / "reports" / "2026-09-30.md"
    rep.parent.mkdir(parents=True)
    rep.write_text("---\ntitle: a report\ntags: []\n---\n")
    assert [m["ref"] for m in label.population(ctx.agents)] == \
        ["journal/2026/09/a.md"]


# ── one batch item ───────────────────────────────────────────────────────────

def test_the_stage_raises_ONE_proposal_over_N_entries(ctx):
    """233 numbered rows for one decision is not a queue, it is the report the
    queue replaced (`SPECS.md` §Item shape)."""
    for i in range(7):
        _entry(ctx.agents, f"e{i}.md")
    label.run(ctx)
    assert len(ctx.proposals) == 1
    p = ctx.proposals[0]
    assert p.kind == "entry-subject"
    assert len(p.members) == 7
    assert "7" in p.what


def test_the_batch_row_carries_its_count_and_a_sample(ctx):
    """3a's exit is this row. A bare `[233 members]` is a number the reader
    cannot judge."""
    for i in range(7):
        _entry(ctx.agents, f"e{i}.md", title=f"session {i}")
    label.run(ctx)
    its = [queue.as_dict(p.kind, p.target, p.what, p.why, p.stage,
                         p.target_kind, "2026-09-30", members=p.members)
           for p in ctx.proposals]
    row = queue.Item(**{k: v for k, v in its[0].items()
                        if k in queue.Item.__dataclass_fields__}).row(1)
    assert "7 members" in row
    assert "journal/2026/09/e0.md" in row
    assert "+4 more" in row, "the sample says how much it is not showing"


def test_no_entries_left_is_a_note_and_not_a_proposal(ctx):
    _entry(ctx.agents, "done.md", subject="pass")
    label.run(ctx)
    assert ctx.proposals == []
    assert any("nothing to label" in n.text for n in ctx.notes)


def test_the_stage_writes_nothing_at_all(ctx):
    """`subject:` is O5a's write, and an entry labelled early breaks O4's
    ground truth."""
    p = _entry(ctx.agents, "a.md")
    before = p.read_text()
    label.run(ctx)
    assert p.read_text() == before


def test_tags_is_never_proposed_and_never_written(ctx):
    """Making `tags:` exclusive collapses the concept layer into the category
    layer, which is the error the whole schema exists to avoid."""
    p = _entry(ctx.agents, "a.md")
    label.run(ctx)
    assert "tags" not in ctx.proposals[0].what.lower().replace("`tags:`", "")
    assert "subject" in ctx.proposals[0].what
    assert p.read_text().count("tags: []") == 1


# ── the question is the ontology's, not a copy ───────────────────────────────

def test_the_kind_the_stage_raises_has_a_schema(ctx):
    """An undeclared kind is an error, not a default."""
    cov = jev_schemas.coverage([label.KIND])
    assert cov["missing"] == [] and cov["needs_ontology"] == []


def test_the_criteria_map_IS_the_ontology_object(ctx):
    """One artifact, two readers -- identity, never equality. A copy that
    happens to match today is the drift this track exists to prevent."""
    q = jev_schemas.question(label.KIND)
    assert q["criteria"] is ontology.criteria("entry-subject")


def test_a_subject_with_a_place_shows_it_and_one_without_does_not():
    """The instructions promise each subject "names a PLACE IN THE SYSTEM";
    O4b found the map sent the criteria alone (`ontology SPECS` O4d).
    The mnemonic name is deliberately not sent."""
    crit = ontology.criteria("subject")
    for s in ontology.subjects():
        assert crit[s.id].startswith(" ".join(s.criteria.split()))
        assert all(f"`{p}/`" in crit[s.id] for p in s.places)
        assert ("Place" in crit[s.id]) == bool(s.places)
        assert s.name not in crit[s.id]


# ── the state a labelling question is asked about ────────────────────────────

def test_the_state_carries_title_headings_and_the_body_opening(tmp_path):
    p = _entry(tmp_path, "2026-09-29_x.md", title="Fixed the thing")
    s = label.state(p)
    assert "title: Fixed the thing" in s
    assert "  - What happened" in s
    assert "body (opening):" in s and "body" in s.split("body (opening):")[1]


def test_the_state_never_carries_the_path(tmp_path):
    """For a leaf the folder IS the answer; for an entry it is only a date."""
    p = _entry(tmp_path, "2026-09-29_x.md")
    assert "journal" not in label.state(p) and "2026-09-29_x" not in label.state(p)


def test_the_body_opening_is_bounded(tmp_path):
    p = tmp_path / "long.md"
    p.write_text("---\ntitle: t\n---\n\n" + "word " * 2000)
    opening = label.state(p).split("body (opening):\n")[1]
    assert len(opening) == label.BODY_CHARS


# ── the band, scaled to the primitive ────────────────────────────────────────

def test_a_choice_kind_does_not_use_the_noul_triple():
    """0.80 on one of fourteen options is a far stronger claim than 0.80 on a
    yes/no. The shared triple would band a working classifier `drop`."""
    assert bands.triple("entry-subject") != bands.DEFAULT
    assert bands.triple("dangling-link") == bands.DEFAULT


def test_the_choice_triple_is_derived_from_the_option_count():
    """Arithmetic, not intuition -- and it moves if the vocabulary moves."""
    wide, narrow = bands.for_choice(100), bands.for_choice(4)
    assert wide.accept_at < narrow.accept_at < bands.DEFAULT.accept_at
    assert bands.for_choice(2) == bands.DEFAULT
    with pytest.raises(ValueError):
        bands.for_choice(1)


def test_the_derived_triples_are_declared_unvalidated():
    """It inherits every bit of DEFAULT's provisionality; 3d is what replaces
    it with a calibrated number."""
    assert any("entry-subject" in line for line in bands.unvalidated())


# ── asking a batch ───────────────────────────────────────────────────────────

def _run_batch(ctx, monkeypatch, answer, n=4):
    for i in range(n):
        _entry(ctx.agents, f"e{i}.md", title=f"session {i}")
    label.run(ctx)
    p = ctx.proposals[0]
    queue.save(ctx.base, [queue.as_dict(p.kind, p.target, p.what, p.why,
                                        p.stage, p.target_kind, "2026-09-30",
                                        members=p.members)])
    calls = _stub(monkeypatch, answer)
    recommend.run(ctx)
    return calls, queue.items(ctx.base)


def test_a_batch_is_asked_once_per_member(ctx, monkeypatch):
    """One state per artefact: that is what makes the answer unambiguous about
    which entry it belongs to."""
    calls, _ = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    assert len(calls) == 4
    states = [c["state"] for c in calls]
    assert len({s for s in states}) == 4, "each call carries ONE member"
    for i in range(4):
        assert any(f"e{i}.md" in s for s in states)


def test_every_call_shares_one_question_object_and_one_hash(ctx, monkeypatch):
    """N wordings would be N schema_hashes, which shatters the calibration
    population the hash exists to define (2e)."""
    calls, _ = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    qs = [next(iter(c["questions"].values())) for c in calls]
    assert all(q is qs[0] for q in qs)


def test_each_member_records_its_own_envelope(ctx, monkeypatch):
    """A label with no model or schema_hash beside it is the unversioned
    confidence scalar this track rejects."""
    _, its = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    for m in its[0]["members"]:
        assert m["choice"] == "pass"
        assert m["schema_hash"] == jev_schemas.schema_hash("entry-subject")
        assert m["model"] == jev.MODEL
        assert m["band"] == bands.ACCEPT
        assert m["probability"] == pytest.approx(0.9)


def test_the_batch_is_accept_only_when_every_kept_member_is(ctx, monkeypatch):
    """One keystroke must not apply a label the model itself put in `ask`."""
    seen = []

    def answer(state):
        seen.append(state)
        return _choice("pass", 0.9 if len(seen) < 4 else 0.5)

    _, its = _run_batch(ctx, monkeypatch, answer)
    assert its[0]["recommendation"]["band"] == bands.ASK


def test_the_batch_records_its_distribution_and_not_an_average(ctx, monkeypatch):
    """A batch has no single confidence; a number there would be an average
    nobody asked for."""
    _, its = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    rec = its[0]["recommendation"]
    assert rec["distribution"] == {"accept": 4, "ask": 0, "drop": 0}
    assert rec["members"] == 4
    assert rec["confidence"] is None and rec["probabilities"] is None


def test_a_member_already_banded_is_not_paid_for_twice(ctx, monkeypatch):
    calls, its = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    assert len(calls) == 4
    calls2 = _stub(monkeypatch, _choice("pass", 0.9))
    recommend.run(ctx)
    assert calls2 == [], "carried-forward answers are not re-asked"


# ── the outlier split: the property the batch shape rests on ────────────────

def test_a_low_confidence_member_becomes_its_own_numbered_item(ctx, monkeypatch):
    """Never a hidden field. This is the whole reason a batch is allowed."""
    seen = []

    def answer(state):
        seen.append(state)
        return _choice("pass", 0.9 if len(seen) < 4 else 0.01)

    _, its = _run_batch(ctx, monkeypatch, answer)
    batch = [i for i in its if i["target"] == label.TARGET][0]
    assert len(batch["outliers"]) == 1
    outlier_id = batch["outliers"][0]
    own = [i for i in its if i["id"] == outlier_id]
    assert len(own) == 1, "the outlier is a real queue item with its own row"
    assert own[0]["target"] == "journal/2026/09/e3.md"
    assert own[0]["recommendation"]["band"] == bands.DROP
    # reachable by ordinal, which is the whole interface
    n = its.index(own[0]) + 1
    assert queue.by_ordinal(its, n) is own[0]


def test_outliers_are_ids_not_copies_of_the_member(ctx, monkeypatch):
    """A list of dicts here would be the second place the artefact lives."""
    _, its = _run_batch(
        ctx, monkeypatch,
        lambda s: _choice("pass", 0.01 if "e0.md" in s else 0.9))
    batch = [i for i in its if i["target"] == label.TARGET][0]
    assert all(isinstance(o, str) and o.startswith("q-")
               for o in batch["outliers"])


def test_a_lifted_member_stays_in_the_population_count(ctx, monkeypatch):
    """The count is the corpus it was raised over; a count that shrank as
    outliers left would report a corpus smaller than the one that exists."""
    _, its = _run_batch(
        ctx, monkeypatch,
        lambda s: _choice("pass", 0.01 if "e0.md" in s else 0.9))
    batch = [i for i in its if i["target"] == label.TARGET][0]
    assert len(batch["members"]) == 4


def test_a_middle_band_member_is_not_lifted(ctx, monkeypatch):
    """`ask` means the proposal stands and wants a look -- which is what
    resolving the batch IS. Lifting it would restore the 233-row report."""
    _, its = _run_batch(ctx, monkeypatch, _choice("pass", 0.5))
    batch = [i for i in its if i["target"] == label.TARGET][0]
    assert batch["outliers"] == []
    assert all(m["band"] == bands.ASK for m in batch["members"])
    assert len(its) == 1


def test_an_outlier_survives_the_next_nights_rebuild(ctx, monkeypatch):
    """`_fresh` never re-raises an outlier -- it is minted from a BAND. Dropping
    it would un-number an item the user holds an ordinal for."""
    _, its = _run_batch(
        ctx, monkeypatch,
        lambda s: _choice("pass", 0.01 if "e0.md" in s else 0.9))
    assert len(its) == 2
    label.run(ctx)                                   # tonight's population again
    p = ctx.proposals[-1]
    fresh = [queue.as_dict(p.kind, p.target, p.what, p.why, p.stage,
                           p.target_kind, "2026-10-01", members=p.members)]
    merged = queue.merge(its, fresh, "2026-10-01")
    assert len(merged) == 2, "the outlier is still numbered"
    assert merged[0]["outliers"] == its[0]["outliers"]


def test_an_outliers_resolution_is_not_lost_to_a_re_split(ctx, monkeypatch):
    """Re-minting it unresolved would re-ask a question the user settled."""
    answer = lambda s: _choice("pass", 0.01 if "e0.md" in s else 0.9)
    _, its = _run_batch(ctx, monkeypatch, answer)
    oid = its[0]["outliers"][0]
    queue.resolve(ctx.base, oid, {"action": "refuse", "ts": "t",
                                  "kind": "entry-subject", "target": "x"})
    # a second banding pass over the same corpus
    for it in queue.items(ctx.base):
        pass
    data = queue.load(ctx.base)
    for it in data["items"]:
        for m in it.get("members") or []:
            m.pop("band", None)
    queue.save(ctx.base, data["items"])
    _stub(monkeypatch, answer)
    recommend.run(ctx)
    again = [i for i in queue.items(ctx.base) if i["id"] == oid]
    assert len(again) == 1 and again[0]["resolution"]["action"] == "refuse"


# ── cost, shown before it is spent ───────────────────────────────────────────

def test_a_dry_run_shows_the_cost_and_makes_no_call(ctx, monkeypatch):
    """3a's exit: question accepted, cost shown, nothing written."""
    for i in range(5):
        _entry(ctx.agents, f"e{i}.md")
    label.run(ctx)
    p = ctx.proposals[0]
    queue.save(ctx.base, [queue.as_dict(p.kind, p.target, p.what, p.why,
                                        p.stage, p.target_kind, "2026-09-30",
                                        members=p.members)])
    ctx.dry_run = True
    calls = _stub(monkeypatch, _choice("pass", 0.9))
    recommend.run(ctx)
    assert calls == []
    note = [n.text for n in ctx.notes if "would be banded" in n.text][0]
    assert "5 call(s)" in note
    assert "ESTIMATED" in note, "an estimate is labelled one"
    assert "$" in note


def test_the_per_night_cap_is_reported_rather_than_silent(ctx, monkeypatch):
    monkeypatch.setattr(recommend, "MAX_MEMBERS_PER_NIGHT", 2)
    calls, its = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    assert len(calls) == 2
    assert any("not asked tonight" in n.text for n in ctx.notes)


# ── the queue file stays readable ────────────────────────────────────────────

def test_the_queue_still_round_trips_at_version_1(ctx, monkeypatch):
    """`members` and `outliers` were declared in v1 and were empty everywhere,
    so giving their elements a shape moves no field a v1 reader reads."""
    _, its = _run_batch(ctx, monkeypatch, _choice("pass", 0.9))
    raw = json.loads((queue.path(ctx.base)).read_text())
    assert raw["version"] == queue.VERSION == 1
    assert raw["digest"] == queue.digest(raw["items"])
    assert queue.items(ctx.base) == its
