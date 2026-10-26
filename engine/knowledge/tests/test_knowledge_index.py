"""The knowledge-index plan: what would be written, decided without writing it.

The tests that earn their keep here are the ones covering the invariants the
index exists for -- ONE level of disclosure (§index does not index itself, and
`SKIP_NAMES` is shared with scoring), a BUDGET that is reported rather than
silently blown, and NOTHING AUTHORED (every cell traceable to a leaf).
"""
import pathlib

import pytest

from knowledge import tree
from knowledge import knowledge_index as ki

ROUTER = """# Knowledge Tree — Router

<!-- LAYER 2 · ROUTING ONLY -->

<!-- BEGIN:BRANCHES (generated) -->
placeholder
<!-- END:BRANCHES -->
"""


def _leaf(root, rel, *, title=None, summary=None, tags=None, triggers=None,
          body="# Heading\n\ntext\n"):
    p = root / "knowledge" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = []
    if title is not None:
        fm.append(f"title: {title}")
    if summary is not None:
        fm.append(f"summary: {summary}")
    if tags is not None:
        fm.append(f"tags: [{', '.join(tags)}]")
    if triggers is not None:
        fm.append(f"triggers: [{', '.join(triggers)}]")
    p.write_text(("---\n" + "\n".join(fm) + "\n---\n\n" if fm else "") + body)
    return p


@pytest.fixture
def root(tmp_path):
    a = tmp_path / "agents"
    k = a / "knowledge"
    k.mkdir(parents=True)
    (k / "CONTEXT.md").write_text(ROUTER)
    for name, blurb in (("meta", "Maintaining this knowledge base itself"),
                        ("tools", "Per-tool behaviour and traps"),
                        ("domains", "Subject knowledge")):
        (k / name).mkdir()
        (k / name / "CONTEXT.md").write_text(
            f"# {name}\n\n<!-- LAYER 3 · {blurb} -->\n")
    _leaf(a, "meta/alpha.md", title="Alpha", summary="What alpha is for",
          tags=["one", "two"])
    _leaf(a, "tools/beta.md", title="Beta", tags=["t1"], triggers=["b-trigger"])
    return a


def _top(p):
    """The top index, `knowledge/INDEX.md` -- one of several INDEX.md writes."""
    return next(c for w, c in p.writes if w == p.root / "knowledge" / "INDEX.md")


def _group(p, group):
    return next(c for w, c in p.writes if w == p.root / "knowledge" / group / "INDEX.md")


def _rels(p, paths):
    return [str(x.relative_to(p.root / "knowledge")) for x in paths]


# ── the cells come from the leaf, never from the generator ───────────────
def test_summary_prefers_summary_then_title_then_h1(root):
    _leaf(root, "meta/titled.md", title="Only a title")
    _leaf(root, "meta/bare.md", body="# Just an H1\n\ntext\n")
    rows = {leaf.rel: leaf.summary for leaf in ki.plan(root).leaves}
    assert rows["meta/alpha.md"] == "What alpha is for"
    assert rows["meta/titled.md"] == "Only a title"
    assert rows["meta/bare.md"] == "Just an H1"


def test_terms_prefer_triggers_over_tags_and_are_capped(root):
    _leaf(root, "meta/many.md", title="Many",
          tags=[f"t{i}" for i in range(ki.MAX_TERMS + 5)])
    rows = {leaf.rel: leaf.terms for leaf in ki.plan(root).leaves}
    assert rows["tools/beta.md"] == ["b-trigger"]      # triggers win over tags
    assert rows["meta/alpha.md"] == ["one", "two"]
    assert len(rows["meta/many.md"]) == ki.MAX_TERMS


def test_branch_heading_is_the_routers_own_layer_comment(root):
    p = ki.plan(root)
    assert p.branches["tools"] == "Per-tool behaviour and traps"
    index = _top(p)
    assert "## `tools/` — Per-tool behaviour and traps" in index


def test_empty_branch_is_named_but_gets_no_table(root):
    index = _top(ki.plan(root))
    assert "Branches with no leaves yet: `domains/`." in index
    assert "## `domains/`" not in index


# ── one level, one population ────────────────────────────────────────────
def test_index_does_not_index_itself(root):
    (root / "knowledge" / "INDEX.md").write_text("# stale\n")
    assert "INDEX.md" in tree.SKIP_NAMES      # shared with the scoring pass
    assert not [leaf for leaf in ki.plan(root).leaves if leaf.rel == "INDEX.md"]


def test_branch_routers_and_templates_are_not_leaves(root):
    _leaf(root, "meta/_draft.md", title="Draft")
    rels = {leaf.rel for leaf in ki.plan(root).leaves}
    assert rels == {"meta/alpha.md", "tools/beta.md"}


def test_branch_counts_are_regenerated_into_the_router(root):
    text = dict((w.name, c) for w, c in ki.plan(root).writes)["CONTEXT.md"]
    assert "| `meta/` | Maintaining this knowledge base itself | 1 |" in text
    assert "| `domains/` | Subject knowledge | 0 |" in text
    assert "placeholder" not in text


# ── the budget is reported, and the file is still written ────────────────
def test_over_budget_warns_but_still_writes(root, monkeypatch):
    monkeypatch.setattr(ki, "INDEX_BUDGET_TOKENS", 1)
    p = ki.plan(root)
    assert p.over_budget and not p.failed
    assert any("over the 1 budget" in prob.what for prob in p.problems)
    assert [w for w, _ in p.writes if w.name == "INDEX.md"]


def test_long_summary_is_reported_never_truncated(root):
    long = "x" * (ki.MAX_SUMMARY_CHARS + 1)
    _leaf(root, "meta/verbose.md", title="V", summary=long)
    p = ki.plan(root)
    assert any("max 110" in prob.what for prob in p.problems)
    assert long in _group(p, "meta")


# ── failure is data, not an exit ─────────────────────────────────────────
def test_missing_marker_is_an_error_and_writes_nothing(root):
    (root / "knowledge" / "CONTEXT.md").write_text("# no marker here\n")
    p = ki.plan(root)
    assert p.failed and p.writes == []
    assert any("BEGIN:BRANCHES" in prob.what for prob in p.problems)


def test_missing_tree_is_an_error_not_a_traceback(tmp_path):
    p = ki.plan(tmp_path / "agents")
    assert p.failed and p.writes == []


def test_leaf_without_frontmatter_is_reported(root):
    _leaf(root, "meta/bare.md", body="# H\n\ntext\n")
    assert any("no frontmatter" in prob.what for prob in ki.plan(root).problems)


# ── apply is idempotent and drift is observable ──────────────────────────
def test_apply_is_idempotent(root):
    first = ki.plan(root).apply()
    assert {p.name for p in first} == {"INDEX.md", "CONTEXT.md"}
    assert len([p for p in first if p.name == "INDEX.md"]) == 3, "the top and one per group"
    assert ki.plan(root).drift == []
    assert ki.plan(root).apply() == []


def test_drift_appears_when_a_leaf_changes(root):
    ki.plan(root).apply()
    _leaf(root, "meta/gamma.md", title="Gamma")
    p = ki.plan(root)
    assert _rels(p, p.drift) == ["INDEX.md", "meta/INDEX.md", "CONTEXT.md"]


def test_stage_run_writes_nothing_under_dry_run(root, tmp_path):
    class Ctx:
        agents = root
        dry_run = True

        def __init__(self):
            self.notes = []

        def note(self, sid, what, level="note"):
            self.notes.append((sid, what, level))

        def act(self, *a):                       # pragma: no cover - must not fire
            raise AssertionError("a dry run wrote")

    ctx = Ctx()
    assert ki.run(ctx) is True
    assert not (root / "knowledge" / "INDEX.md").exists()
    assert any("drifted" in n[1] for n in ctx.notes)


# ── O3a: the branch router is generated from the register ────────────────────

def test_the_branch_blurb_comes_from_the_register_not_the_router(root):
    """O3a reversed the source. It used to be the router's own `LAYER n · …`
    comment, which made the description a hand-edited fact this module then
    copied -- and it went visibly wrong when O2b deleted the three routers and
    the table started printing `system/ —`."""
    from knowledge import ontology as O
    router = root / "knowledge/system/CONTEXT.md"
    router.parent.mkdir(parents=True, exist_ok=True)
    router.write_text("# x\n\n<!-- LAYER 3 · a hand-written lie -->\n")
    blurb = ki.branch_blurb(router)
    assert "hand-written lie" not in blurb
    assert blurb == " ".join(O.BRANCHES["system"].criteria.split())


def test_an_undeclared_branch_still_falls_back_to_its_comment(root):
    """The fallback is kept on purpose: a directory naming no declared branch
    is already an error in `ontology check`, and printing nothing here would
    hide it behind a second failure."""
    router = root / "knowledge/bogus/CONTEXT.md"
    router.parent.mkdir(parents=True, exist_ok=True)
    router.write_text("# x\n\n<!-- LAYER 3 · whatever this is -->\n")
    assert ki.branch_blurb(router) == "whatever this is"


def test_an_areas_group_takes_its_label_from_the_profile(root):
    """`areas/<Area>/` is labelled by the PROFILE, not by the subject register:
    the folder mirrors `~/02_AREAS/` (rule 7's exception), so its name is an
    Area and `ontology.subject()` has never held one. Before 2026-10-25 the
    index printed `—` for the branch's only real group, which reads as "this
    subject has no name" rather than "wrong vocabulary asked"."""
    from lib import roots as R
    label = ki._subject_name("areas/B_Tech", {})
    assert label == R.PROFILE.areas["B_Tech"]["description"]
    assert ki._subject_name("areas/No_Such_Area", {}) == ""


def test_areas_is_not_generated_and_the_reason_is_recorded():
    """`knowledge-index.md` §Known duplication: `areas/CONTEXT.md` indexes
    Areas A-P rather than leaves, so generating it would destroy human
    judgement to remove a cosmetic repeat."""
    assert ki.GENERATED_ROUTERS == ("system",)
    assert "areas" not in ki.GENERATED_ROUTERS
    src = pathlib.Path(ki.__file__).read_text()
    assert "destroy human judgement" in src


def test_the_system_router_lists_every_declared_subject(root):
    from knowledge import ontology as O
    (root / "knowledge/system/tree").mkdir(parents=True, exist_ok=True)
    _leaf(root, "system/tree/a.md", title="A", summary="a leaf")
    plan = ki.plan(root)
    writes = {p.name: text for p, text in plan.writes}
    assert "CONTEXT.md" in writes
    router = [t for p, t in plan.writes if p.parent.name == "system"][0]
    for sid in O.SUBJECTS:
        # populated subjects are folders; empty ones are named as bare ids
        assert (f"`{sid}/`" in router) or (f"`{sid}`" in router), sid
    assert "the Workshop" in router
    assert ki.BANNER in router          # generated, and says so


def test_an_empty_subject_reads_declared_not_missing(root):
    (root / "knowledge/system/tree").mkdir(parents=True, exist_ok=True)
    _leaf(root, "system/tree/a.md", title="A", summary="a leaf")
    router = [t for p, t in ki.plan(root).writes if p.parent.name == "system"][0]
    # named WITHOUT a trailing slash: it is not a folder yet, and writing one
    # would make this generated file a permanent entry in `links --check`'s
    # decision list -- a pointer that resolves to nothing, by construction.
    assert "| `publication` |" in router
    assert "| `publication/` |" not in router
    assert "| — |" in router and "never missing" in router


def test_generating_the_router_is_idempotent(root):
    _leaf(root, "system/tree/a.md", title="A", summary="a leaf")
    written = ki.plan(root).apply()
    assert root / "knowledge/system/CONTEXT.md" in written
    assert ki.plan(root).drift == []
    assert ki.plan(root).apply() == []


# ── split per subject (O3d, 2026-10-21) ──────────────────────────────────
def test_the_top_index_names_each_subject_with_its_leaves_terms(root):
    _leaf(root, "tools/pi/gamma.md", title="Gamma", triggers=["g1", "g2"])
    _leaf(root, "tools/pi/delta.md", title="Delta", triggers=["d1"])
    p = ki.plan(root)
    top = _top(p)
    assert "| `tools/pi/INDEX.md` |" in top and "| 2 | d1, g1, g2 |" in top, top
    assert "`tools/pi/gamma.md`" not in top, "the leaves are one level down"
    group = _group(p, "tools/pi")
    assert "| `tools/pi/gamma.md` | Gamma | g1, g2 |" in group
    assert "tools/beta.md" not in group


def test_group_terms_take_one_from_each_leaf_before_a_second():
    leaves = [ki.Leaf("a/s/x.md", "a", "x", ["x1", "x2", "x3"]),
              ki.Leaf("a/s/y.md", "a", "y", ["y1"])]
    assert ki._group_terms(leaves) == ["x1", "y1", "x2", "x3"]


def test_a_subject_that_lost_its_leaves_loses_its_index(root):
    leaf = _leaf(root, "tools/pi/gamma.md", title="Gamma")
    ki.plan(root).apply()
    assert (root / "knowledge" / "tools" / "pi" / "INDEX.md").exists()
    leaf.unlink()
    p = ki.plan(root)
    assert "tools/pi/INDEX.md" in _rels(p, p.drift)
    p.apply()
    assert not (root / "knowledge" / "tools" / "pi" / "INDEX.md").exists()


def test_the_budget_is_per_file_and_names_the_largest(root, monkeypatch):
    monkeypatch.setattr(ki, "INDEX_BUDGET_TOKENS", 1)
    p = ki.plan(root)
    assert p.largest in {"INDEX.md", "meta/INDEX.md", "tools/INDEX.md"}
    assert any(prob.what.startswith(p.largest) for prob in p.problems)
