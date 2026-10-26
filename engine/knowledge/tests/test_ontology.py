"""The ontology registers: one statement of the classes, and what reads it.

The shape of this file follows the module's own governance rule. A REGISTER test
asserts the invariant that makes a register readable at all -- every entry
carries its criteria, its layer, its column and its `reviewed:` date, because
every later phase (the O2 restructure, the O5 labelling) reads these values and
a silent hole is what a schema exists to prevent. A CHECK test asserts the
distinction the whole violations register exists for: a KNOWN gap warns and a
NEW one fails, and the two must not look the same.
"""
import dataclasses
import datetime as dt
import pathlib
import types

import pytest

from knowledge import ontology as O
from lib import roots
from consolidation.stages import associate, conflict


# ── a throw-away tree, so the tree-dependent tests do not read the real one ──

def _leaf(agents, rel, **fm):
    p = agents / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}: {v}" for k, v in fm.items()]
    p.write_text("---\n" + "\n".join(lines) + "\n---\n\n# Body\n")
    return p


@pytest.fixture
def agents(tmp_path):
    """A minimal tree with one document per entity home."""
    a = tmp_path / "memory"
    _leaf(a, "knowledge/system/knowledge/alpha.md", trust="trusted",
          tags="[x]")
    # Outside the vault since R3b: the directive kinds live under `config/`.
    conv = tmp_path / "config/practice/conventions"
    conv.mkdir(parents=True)
    (conv / "voice.md").write_text("# Voice\n")
    return a


@pytest.fixture
def clean(agents, monkeypatch):
    """Point the module's own roots at the throw-away tree."""
    monkeypatch.setattr(O, "AGENTS", agents)
    monkeypatch.setattr(O, "PROJECTS", agents.parent / "01_PROJECTS")
    O.reset()
    yield agents
    O.reset()


# ── O1a: every register entry declares criteria, layer, column, reviewed ─────

REGISTERS = [(name, entries) for name, entries in O._register_entries()]


@pytest.mark.parametrize("name,entries", REGISTERS, ids=lambda v: str(v)[:20])
def test_every_register_entry_declares_its_criteria_layer_column_and_review(name,
                                                                           entries):
    """The contract O1a states: comments sit beside values, which is why this
    schema is Python and not JSON. A missing field is an error, not a default."""
    assert entries, f"{name} is empty"
    for key, entry in entries:
        for field in ("criteria", "layer", "column", "reviewed"):
            assert getattr(entry, field), f"{name}:{key} has no {field}"
        assert entry.layer in O.LAYERS, f"{name}:{key} layer {entry.layer}"
        assert entry.column in O.COLUMNS, f"{name}:{key} column {entry.column}"
        dt.date.fromisoformat(entry.reviewed)


def test_selfcheck_passes_and_names_every_register():
    """The exit criterion's command, with its output captured: one line per
    register, with its count."""
    assert O.selfcheck() == []


def test_selfcheck_raises_rather_than_warning_on_an_incoherent_register(monkeypatch):
    broken = dict(O.FACETS)
    broken["subject"] = dataclasses.replace(O.FACETS["subject"], column="")
    monkeypatch.setattr(O, "FACETS", broken)
    with pytest.raises(O.Inconsistent):
        O.selfcheck(verbose=False)


# ── O1a: the content files, read by the shared parser ──────────────────────

def test_every_register_is_a_content_file_loaded_through_miniyaml():
    """The content lives in `config/knowledge/*.yaml`, one file per register, and
    every one of them loads through the SAME parser boundaries uses. This is the
    test that keeps the "do not extend `_miniyaml`" promise honest: a register
    that needs a new YAML feature fails here rather than being patched in."""
    from lib import _miniyaml
    d = O.ONTOLOGY_DIR
    for name, (stem, key) in O.FILES.items():
        path = d / f"{stem}.yaml"
        data = _miniyaml.load(path.read_text())
        assert data.get(key), f"{path}: no `{key}:` section"
        assert all(isinstance(row, dict) for row in data[key]), path
        assert all(row.get("id") is not None for row in data[key]), path


def test_the_content_files_are_the_declared_ones(tmp_path):
    """One file per register, and the register count is what selfcheck prints."""
    stems = {stem for stem, _ in O.FILES.values()}
    on_disk = {p.stem for p in O.ONTOLOGY_DIR.glob("*.yaml")}
    assert on_disk == stems
    assert len(O._register_entries()) == 7


def test_the_folded_criteria_text_round_trips():
    """`_miniyaml` joins a `>` block with single spaces. A line lost or doubled
    by the fold would be a fact edited by a format change, which is exactly what
    this item must not do."""
    import re

    def words(s):
        return tuple(str(s).split())

    def loaded_strings(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from loaded_strings(v)
        elif isinstance(node, list):
            for v in node:
                yield from loaded_strings(v)
        elif isinstance(node, str):
            yield node

    for stem in {s for s, _ in O.FILES.values()}:
        text = (O.ONTOLOGY_DIR / f"{stem}.yaml").read_text()
        lines = text.split("\n")
        blocks, i = [], 0
        while i < len(lines):
            head = re.match(r"^(\s*)(\w+): >$", lines[i])
            if not head:
                i += 1
                continue
            col, i = len(head.group(1)), i + 1
            body = []
            while i < len(lines) and (not lines[i].strip()
                                      or len(lines[i]) - len(lines[i].lstrip()) > col):
                if lines[i].strip():
                    body.append(lines[i].strip())
                i += 1
            blocks.append(tuple(" ".join(body).split()))
        present = {words(s) for s in loaded_strings(O.read_register(
            O.ONTOLOGY_DIR / f"{stem}.yaml"))}
        assert blocks, f"{stem}.yaml has no folded scalars"
        for b in blocks:
            assert b in present, f"{stem}.yaml: a folded block did not survive"


def test_an_unknown_key_in_a_content_file_is_refused(tmp_path):
    """The reason the content is a file and not a dict: a config file refuses to
    load and names the line, where a typo in Python can import successfully and
    mean something different."""
    src = O.ONTOLOGY_DIR
    for p in src.glob("*.yaml"):
        (tmp_path / p.name).write_text(p.read_text())
    (tmp_path / "entities.yaml").write_text(
        (tmp_path / "entities.yaml").read_text().replace(
            "    column: assertion", "    colum: assertion", 1))
    with pytest.raises(O.Inconsistent) as exc:
        O.reload(tmp_path)
    assert "colum" in str(exc.value)
    O.reload()


def test_miniyaml_was_not_extended():
    """`_miniyaml` sits in the boundary path and "raises on anything else, which
    is the point". Its surface is frozen here, so a later need cannot quietly
    widen a parser the guard depends on."""
    import inspect
    from lib import _miniyaml
    public = {n for n in dir(_miniyaml) if not n.startswith("_")}
    funcs = {n for n, v in vars(_miniyaml).items() if inspect.isfunction(v)}
    assert public == {"YamlError", "load", "annotations", "re"}   # `annotations`
    # is the `from __future__` binding and `re` the stdlib import that
    # `_reject_flow` needs; neither is API. The assertion's subject is that no
    # new PUBLIC function or class appears.
    # `_reject_flow` was added 2026-10-20. Flow collections had always been
    # REJECTED in the docstring, but loaded as raw strings; a vocabulary file
    # (dev/architecture 2d) is where someone writes `[a, b]`. A parser fixed to
    # honour its own contract is not the surface widening this test guards.
    assert funcs == {"_strip_comment", "_unquote", "_lines", "_folded",
                     "_mapping", "_sequence", "_value", "_reject_flow", "load"}


def test_the_loader_reads_the_files_rather_than_a_copy(monkeypatch, tmp_path):
    """Nothing downstream knows the storage format, and nothing holds a second
    copy of the content: changing a file changes what the API answers."""
    for p in O.ONTOLOGY_DIR.glob("*.yaml"):
        (tmp_path / p.name).write_text(p.read_text())
    subj = tmp_path / "subjects.yaml"
    subj.write_text(subj.read_text().replace(
        "name: the Grimoire", "name: the Ledger", 1))
    O.reload(tmp_path)
    try:
        assert O.SUBJECTS["knowledge"].name == "the Ledger"
    finally:
        O.reload()
    assert O.SUBJECTS["knowledge"].name == "the Grimoire"


# ── O1b: entity types, including the declared-and-not-validated six ─────────

def test_the_live_tree_resolves_a_convention_and_an_outside_path():
    """Both halves of the exit criterion, on the real tree: a name pointing at a
    document type `tree.leaves()` never walks, and a path outside the tree."""
    assert O.resolve("voice") == ("convention", "config/practice/conventions/voice.md")
    etype, path = O.resolve("02_AREAS/B_Tech/SKILLS/OBSIDIAN-CLAUDE-SETUP.md")
    assert etype == "external" and path.endswith("OBSIDIAN-CLAUDE-SETUP.md")


def test_a_bare_name_that_names_nothing_is_not_external():
    """The distinction the five closed queue items turned on: `external` is a
    real thing elsewhere, None is a name that resolves to nothing."""
    assert O.resolve("no-such-leaf-yet") is None
    assert O.resolve("no-such-leaf-yet.md") is None
    assert O.resolve("") is None


def test_a_renamed_leaf_inside_the_tree_is_dangling_not_external():
    """A path under memory/ that does not exist is a broken reference, not a
    file outside the tree -- blessing it as `external` would hide the break."""
    assert O.resolve("knowledge/operations/consolidation-cycle.md") is None


def test_a_url_and_a_git_remote_are_external():
    assert O.resolve_type("https://example.org/x") == "external"
    assert O.resolve_type("git@github.com:rgutzen/dotfiles.git") == "external"


def test_the_six_declared_types_carry_no_frontmatter_contract():
    for name in ("convention", "identity", "ward", "track", "shadow", "external"):
        e = O.ENTITIES[name]
        assert not e.validated and e.column == "coincidence", name
    for name in ("leaf", "skill", "episode", "report"):
        assert O.ENTITIES[name].validated, name


def test_the_directive_types_are_asked_of_the_register(clean):
    assert set(O.directive_types()) == {"convention", "identity", "ward"}
    assert O.is_directive("config/practice/conventions/voice.md")
    assert not O.is_directive("knowledge/system/knowledge/alpha.md")


def test_resolve_is_stable_across_the_two_path_spellings(clean):
    """`tree.Doc.rel` is agents-relative; everything this module emits is
    repo-relative. Both must type the same document the same way."""
    assert O._type_of("knowledge/system/knowledge/alpha.md") == "leaf"
    assert O._type_of("memory/knowledge/system/knowledge/alpha.md") == "leaf"
    assert O.is_directive("config/practice/conventions/voice.md")


# ── O1c: the associate guard reads the register ─────────────────────────────

def test_the_associate_guard_is_no_longer_a_path_prefix():
    """`_is_conventions` tested `knowledge/conventions/`, gone since the move.
    The intent is kept; the mechanism is the entity register."""
    src = pathlib.Path(associate.__file__).read_text()
    body = src.split("def _is_conventions", 1)[1].split('"""', 2)[2]
    assert "doc.rel.startswith" not in body
    assert "ontology.is_directive" in body


def test_a_related_name_pointing_at_a_convention_is_not_dangling(clean, tmp_path):
    """The three `related: voice` items: the name is a real document of a type
    the tree does not walk, so it is a back-link finding, not a dangling name."""
    leaf = clean / "knowledge/system/knowledge/beta.md"
    leaf.write_text("---\ntitle: beta\nrelated: [voice]\n---\n\n# Body\n")
    ctx = _ctx(clean, tmp_path)
    associate.run(ctx)
    assert not [p for p in ctx.proposals if p.kind == "dangling-link"]
    frozen = [n for n in ctx.notes if n.stage == "5a" and "backlink" in n.text]
    assert len(frozen) == 1 and "config/practice/conventions/voice.md" in frozen[0].text


def _ctx(agents, tmp_path):
    from consolidation import pass_ctx
    return pass_ctx.Pass(agents, tmp_path / "data", False, dt.date(2026, 9, 30))


# ── O1d: an external supersession resolves to outside ──────────────────────

def test_no_back_pointer_is_derived_for_an_external_target(clean):
    """Stated rather than left to be discovered: there is nothing in this tree
    to write a `superseded_by:` into."""
    _leaf(clean, "knowledge/system/knowledge/gone.md",
          supersedes="02_AREAS/B_Tech/SKILLS/OBSIDIAN-CLAUDE-SETUP.md")
    plan = conflict.plan(clean)
    assert plan.pending() == {} and plan.writes == []


# ── O1e: the facet register ────────────────────────────────────────────────

def test_ten_facets_and_no_facet_is_both_derived_and_declared():
    assert len(O.FACETS) == 10
    for name, f in O.FACETS.items():
        assert not (set(f.derived_for) & set(f.declared_for)), name
        assert f.on, name


def test_touches_is_a_concept_with_a_closed_domain_and_no_derivation():
    """C2. The register's own rule forces the column: a closed domain may not
    be a coincidence, and unlike `area` this one is not grandfathered."""
    t = O.FACETS["touches"]
    assert t.layer == "concept" and t.column == "assertion"
    assert t.where == "frontmatter" and t.on == ("episode",)
    assert t.declared_for == ("episode",) and not t.derived_for
    assert set(t.domain) == set(O.SUBJECTS)


def test_subject_at_answers_for_any_file_and_guesses_nothing():
    """The third resolution rule: no folder convention, no frontmatter -- just
    the place a subject occupies."""
    assert O.subject_at("engine/knowledge/journal_index.py") == "knowledge"
    assert O.subject_at("engine/consolidation/stages/replay.py") == "consolidation"
    assert O.subject_at("config/practice/user/user-identity.md") == "practice"
    assert O.subject_at("engine/knowledge") == "knowledge"      # the place itself
    # A directory NO subject occupies, a prefix that is not a path, and a bare
    # segment: each is None, never the nearest match.
    assert O.subject_at("ontology SPECS") is None
    assert O.subject_at("enginex/knowledge/x.py") is None
    assert O.subject_at("engine") is None
    assert O.subject_at("") is None


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="the journal is this instance's: the classification omits "
           "memory/journal/**, so `publish.py` prunes its place from the "
           "exported subjects register and there is no such place to resolve")
def test_subject_at_resolves_the_journal_to_knowledge():
    """The instance's own place register answers for the journal, and only
    here: the assertion is about a directory the published tree does not have."""
    assert O.subject_at("memory/journal/2026/10/x.md") == "knowledge"


def test_subject_is_derived_for_leaves_and_declared_for_episodes():
    """One vocabulary, two resolution rules, stated once in `subject_of`."""
    s = O.FACETS["subject"]
    assert set(s.derived_for) == {"leaf", "skill"}
    assert set(s.declared_for) == {"episode", "report"}
    assert O.subject_of("leaf", "memory/knowledge/system/knowledge/alpha.md", {}) == "knowledge"
    assert O.subject_of("leaf", "memory/knowledge/areas/alpha.md", {}) is None
    assert O.subject_of("episode", "memory/journal/2026/09/x.md",
                        {"subject": "backup"}) == "backup"


def test_control_is_new_and_defaults_ours():
    assert O.FACETS["control"].domain == ("ours", "upstream", "shared")
    assert O.FACETS["control"].on == ("leaf",)


def test_facets_command_prints_the_domains_and_columns(capsys):
    from cli import cli
    from lib import invocation
    inv = invocation.parse(["facets"], cli.ONTOLOGY, "/tmp", "/tmp")
    assert cli.ontology_cmd(inv) == 0
    out = capsys.readouterr().out
    for name in O.FACETS:
        assert name in out
    assert "coincidence" in out


# ── O1f: branches and their lifecycles ─────────────────────────────────────

def test_three_branches_each_with_criteria_and_a_retirement():
    assert set(O.BRANCHES) == {"system", "areas", "projects"}
    assert len(O.branches()) == 3
    for b in O.branches():
        assert b.criteria and b.falsified_when and b.retirement


def test_a_projects_leaf_whose_project_is_gone_warns(clean, tmp_path):
    _leaf(clean, "knowledge/projects/gone-project.md", trust="trusted")
    findings = [f for f in O.branch_findings(clean, tmp_path / "01_PROJECTS")
                if f.code == "project"]
    assert len(findings) == 1 and "no longer exists" in findings[0].detail


def test_a_projects_leaf_with_a_live_project_does_not_warn(clean, tmp_path):
    _leaf(clean, "knowledge/projects/live-project.md", trust="trusted")
    (tmp_path / "01_PROJECTS/live-project").mkdir(parents=True)
    assert not [f for f in O.branch_findings(clean, tmp_path / "01_PROJECTS")
                if f.code == "project"]


# ── O1g: the subject vocabulary ────────────────────────────────────────────

def test_every_subject_carries_id_name_criteria_and_reviewed():
    """O1g. The expected set is spelled here ON PURPOSE: adding a subject is a
    vocabulary change, and this is the one place it must be edited by hand to
    stay deliberate. The count that used to live here (13) was a second
    statement of the register, and went with the register's own count."""
    subs = O.subjects()
    assert {s.id for s in subs} == {
        "knowledge", "consolidation", "harness", "orchestration", "context",
        "skills", "structure", "boundaries", "checks", "schedule", "backup",
        "host", "practice", "publication"}
    for s in subs:
        assert s.id and s.name and s.criteria and s.reviewed


def test_subject_ids_are_lowercase_unique_and_disjoint_from_the_branches():
    ids = [s.id for s in O.subjects()]
    assert ids == [i.lower() for i in ids]
    assert len(set(ids)) == len(ids)
    assert not set(ids) & set(O.BRANCHES)


def test_places_names_the_directories_a_subject_occupies():
    """O2c's accessor, widened by R1g from one referent to `places:`. An
    unknown subject has none rather than an invented one.

    `publication` gained `engine/publication` on 2026-10-15: Track P's exporter
    put a directory under `engine/`, and the register forces a filing decision
    for a new folder (`ontology check` failed on `unplaced` until it had one).
    The subject's two halves are the mechanism and the writing.
    """
    assert O.places("consolidation") == ("engine/consolidation",)
    assert O.places("boundaries") == ("engine/boundaries", "config/boundaries")
    # `config/publication` holds the private registers and is omitted from the
    # export, whose generated subjects.yaml drops a place that does not exist.
    assert O.places("publication") == tuple(
        p for p in ("docs", "config/publication", "engine/publication")
        if (roots.REPO / p).exists())
    assert O.places("no-such-subject") == ()


def test_every_top_level_directory_has_one_owner_or_a_reason():
    """R2b's map, complete: every subject claims at least one top-level
    directory, and every directory no subject claims is `unmapped:` with a
    reason. `publication` claimed nothing until 2026-10-09, when `docs/` (the
    human-facing documentation, `dev/docs/`) became its place; its glossary
    leaf still lives under `memory/knowledge`, which `knowledge` claims.

    WHICH directories are unmapped is the instance's answer, and is asserted
    below. This half is the invariant, and it has to hold in the exported tree
    too -- where `dotfiles` is not there to be unmapped, because the
    classification omits the symlink."""
    claimed = {p for s in O.subjects() for p in s.places}
    assert {s.id for s in O.subjects() if not s.places} == set()
    assert all(len(u.reason.split()) >= 5 for u in O.UNMAPPED.values())
    assert not claimed & set(O.UNMAPPED)


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="one of the three is `dotfiles`, a symlink at this repo's root "
           "that the classification omits: the export has two unmapped "
           "directories, not three")
def test_the_instance_s_unmapped_directories_are_exactly_these_three():
    assert set(O.UNMAPPED) == {"engine/lib", "engine/cli", "dotfiles"}


def test_the_live_tree_has_every_place_and_nothing_unplaced():
    """R2b's exit half, on the real repository: no place is missing, none is
    claimed twice, and no top-level directory is unclaimed."""
    assert [f.line() for f in O.places_findings()] == []


def _placed_tree(tmp_path):
    for s in O.subjects():
        for p in s.places:
            (tmp_path / p).mkdir(parents=True, exist_ok=True)
            (tmp_path / p / "x").write_text("x")
    for u in O.UNMAPPED:
        (tmp_path / u).mkdir(parents=True, exist_ok=True)
        (tmp_path / u / "x").write_text("x")
    return tmp_path


def test_a_missing_place_is_an_undeclared_error(tmp_path):
    """The folder losing its anchor is a NEW gap: it fails, and no violation
    entry declares it, because there is no such entry to write."""
    repo = _placed_tree(tmp_path)
    assert O.places_findings(repo) == []
    first = O.subjects()[0].places[0]
    for f in (repo / first).iterdir():
        f.unlink()
    (repo / first).rmdir()
    errs = [f for f in O.places_findings(repo) if f.code == "place"]
    assert len(errs) == 1
    assert errs[0].level == "error" and errs[0].violation == 0


def test_an_empty_new_engine_directory_fails(tmp_path):
    """R2b's exit: creating an empty `<engine>/xyz/` makes the gate fail.
    Empty on purpose -- git never tracks one, so the walk reads the disk."""
    repo = _placed_tree(tmp_path)
    (repo / O.roots.ENGINE_REL / "xyz").mkdir()
    errs = [f for f in O.places_findings(repo) if f.code == "unplaced"]
    assert [e.where for e in errs] == [f"{O.roots.ENGINE_REL}/xyz"]


# ── O4a: the ground truth ────────────────────────────────────────────────

def _live_leaves() -> list:
    """`find`'s answer over the live tree, minus the two routers and the
    underscore files -- restricted to `system/`, which is the population
    `corpus()` scores.

    The restriction is not a convenience: `corpus()` excludes `areas/` and
    `projects/` leaves on purpose (their vocabulary is A-P and a project name,
    and the question it answers is `criteria("subject")`). While both were empty
    this helper could walk the whole tree and agree anyway -- 2026-10-25 put the
    first `areas/` leaf in and the two definitions parted company, which is the
    drift the assertion exists to catch rather than to crash on.
    """
    root = pathlib.Path(O.AGENTS) / "knowledge"
    return sorted(
        f"memory/knowledge/{p.relative_to(root).as_posix()}"
        for p in (root / "system").rglob("*.md")
        if p.name not in ("CONTEXT.md", "INDEX.md")
        and not p.name.startswith("_"))


def test_the_corpus_is_the_whole_tree_and_matches_find():
    """O4a's exit. The dump IS `find`'s answer with a subject attached -- if
    the two ever differ, the answer key O4b scores against has drifted from
    the tree that ratified it.

    This is the invariant, and it holds in the exported tree too, where the
    corpus is smaller. HOW MANY leaves it holds is the instance's number and
    is asserted separately."""
    assert [rel for rel, _ in O.corpus()] == _live_leaves()


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="the count is this instance's: the classification omits two of the "
           "leaves, so the export's corpus is smaller, and O4b's answer key "
           "was scored against the private one")
def test_the_instance_corpus_is_the_39_leaves_of_the_live_tree():
    """**34, not 31, since O3c/O3e (2026-10-09) and D7 (2026-10-15)**: O3c's
    generated subject glossary landed under `system/publication/` (the branch's
    first leaf), O3e's `file-naming.md` joined `system/structure/`, and D7 gave
    the fifth harness its leaf, `system/harness/codex.md`. O4b was already run
    and reported against the 31 it was scored on; this assertion is about the
    LIVE tree, and the live tree grew.

    **35 since P6 (2026-10-20)**: the publication track's durable claims moved
    into `system/publication/publication-model.md` as the track retired.

    **39 since the merge with `plan/orchestration` (2026-10-20)**: schedule 9b's
    one-shot leaf and the Loom's three orchestration leaves joined.

    **40 since 2026-10-21**: `system/harness/agent-profiles.md`, billing profiles.
    **41 the same day**: `system/harness/phone-relay.md` (dev/remote R4).
    **42 on 2026-10-24**: `system/harness/herdr-cli.md` -- the terminal workspace
    manager's CLI surfaces and the three traps they set. Its stem is `herdr-cli`
    because `herdr` already names the track `dev/herdr/`, and a stem is one
    document.
    **43 on 2026-10-25**: `system/checks/component-evaluation.md` -- the
    evaluation layer (is a component worth it). Its stem is not `evaluation`
    for the same reason: the track is `dev/evaluation/`.
    **44 the same day**: `system/harness/voice-local.md`, the two local speech
    services and the `say` client (dev/voice-out). Its stem is `voice-local`
    because `voice` already names `config/practice/conventions/voice.md`, the
    house style for prose, and a stem is one document."""
    assert len(_live_leaves()) == 44


def test_every_leaf_in_the_corpus_carries_a_ratified_subject():
    """No leaf may reach O4b without an answer: an unlabelled one would score
    as a disagreement against nothing, which silently lowers the bar."""
    unlabelled = [rel for rel, subject in O.corpus() if not subject]
    assert unlabelled == []
    assert {s for _, s in O.corpus()} <= set(O.SUBJECTS)


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="the distribution counts two subjects -- `backup` and `host` -- "
           "whose leaves the classification omits, so the export's corpus is "
           "a different table; O4b's answer key is the private one")
def test_the_corpus_is_the_distribution_o2b_ratified():
    """The table in SPECS.md O2b, asserted rather than trusted -- including
    `rtk.md` making harness EIGHT, which is the amendment O2b had to make.

    **Amended by O3e (2026-10-09): `structure: 3`.** O3c added `publication: 1`
    the same day; O3e's `file-naming.md` joins `structure`, which is where a
    rule about what a file may be called belongs. **Amended by D7 (2026-10-15):
    `harness: 9`** — the fifth name in `harnesses.ALL` got its own leaf,
    `system/harness/codex.md`, which is where a fact about a harness belongs.
    The other counts are
    untouched -- asserted rather than assumed, because a move that silently
    joins a new subject would otherwise pass. O4b's score is unaffected: it was
    run and recorded against the 31 (SPECS O4b, `o4b-run{1,2,3}.json`), and its
    state carries titles and headings, not these leaves.

    **Amended by orchestration 1c (2026-10-14): `harness: 7, orchestration: 1`.**
    `orchestrators.md` moved to the Loom's folder, where its subject files it
    (R1e). O4b's key still labels it `harness`, as it was when O4b ran.

    **Amended by schedule 9b (2026-10-15): `schedule: 2`.** The one-shot
    session mechanism's leaf, `system/schedule/scheduled-sessions.md`, joins the
    recurring timers' leaf in the Almanac's folder.

    **Amended by the orchestration documentation (2026-10-15):
    `orchestration: 4`.** `the-loom.md`, `orchestration-eval.md` and
    `delegation-and-asks.md` join `orchestrators.md` in the Loom's folder.

    **Amended by P6 (2026-10-20): `publication: 2`** -- the retired track's
    model leaf. **And by the merge (2026-10-20): `harness: 8`** -- D7's
    `codex.md` joins the seven left after `orchestrators.md` moved.

    **Amended 2026-10-21: `harness: 9`** -- `agent-profiles.md` (billing profiles);
    **`harness: 10`** -- `phone-relay.md` (dev/remote R4).
    **Amended 2026-10-24: `harness: 11`** -- `herdr-cli.md` (the herdr track's
    traps, where a future session looks for them).
    **Amended 2026-10-25: `checks: 2`** -- `component-evaluation.md` joins
    `healthcheck.md` in the Threshold's folder (dev/evaluation decision 2).
    **And `harness: 12` the same day** -- `voice-local.md` (dev/voice-out: two
    local speech services and the `say` client)."""
    import collections
    assert collections.Counter(s for _, s in O.corpus()) == {
        "harness": 12, "orchestration": 4, "consolidation": 6, "knowledge": 5, "context": 2, "skills": 2,
        "structure": 3, "boundaries": 1, "checks": 2, "schedule": 2,
        "backup": 1, "host": 1, "practice": 1, "publication": 2,
    }


def test_the_corpus_excludes_branches_with_another_vocabulary(tmp_path):
    """`areas/` is labelled A-P and `projects/` by project name, so neither
    can be scored against `criteria("subject")`. Both are empty today, which
    is exactly when the filter has to be written -- not after a leaf lands
    there and quietly joins the answer key."""
    vault = tmp_path / "memory"
    d = vault / "knowledge/areas/A_Science"
    d.mkdir(parents=True)
    (d / "neuro.md").write_text("---\ntitle: x\n---\n# x\n")
    (vault / "knowledge/system/knowledge").mkdir(parents=True)
    (vault / "knowledge/system/knowledge/a.md").write_text("---\ntitle: y\n---\n")
    assert [rel for rel, _ in O.corpus(vault)] == [
        "memory/knowledge/system/knowledge/a.md"]


def test_the_live_system_branch_holds_only_declared_subjects():
    """O2d's exit half. Every directory O2b created is in the register."""
    assert [f.line() for f in O.subject_dir_findings()] == []


def test_an_areas_leaf_is_checked_against_the_area_vocabulary(tmp_path):
    """The same check as `system/`, with A-P as its vocabulary. Until
    2026-10-25 it compared every `areas/` leaf against the SUBJECTS register,
    which no leaf under that branch can satisfy -- so the first real one warned
    forever, in a message that promised A-P and could never see one.

    The Area folders are read from `config/profile.yaml` through `roots.PROFILE`,
    the same single source `_area_criteria` uses, so a profile edit moves both.
    """
    mem = tmp_path / "memory"
    good = mem / "knowledge/areas/B_Tech"
    good.mkdir(parents=True)
    (good / "sync.md").write_text("---\ntitle: x\n---\n# x\n")
    projects = tmp_path / "projects"
    subjects = [f for f in O.branch_findings(mem, projects) if f.code == "subject"]
    assert [f.line() for f in subjects] == []

    bad = mem / "knowledge/areas/nonsense"
    bad.mkdir()
    (bad / "y.md").write_text("---\ntitle: y\n---\n# y\n")
    subjects = [f for f in O.branch_findings(mem, projects) if f.code == "subject"]
    assert len(subjects) == 1
    assert "no Area" in subjects[0].detail and "B_Tech" in subjects[0].detail


def test_an_empty_undeclared_subject_directory_is_an_error(tmp_path):
    """The gap `branch_findings` cannot close: it reaches a folder only through
    a document IN it, so a subject invented by `mkdir` and not yet filled is
    invisible to every other check."""
    root = tmp_path / "knowledge/system"
    (root / "consolidation").mkdir(parents=True)
    assert O.subject_dir_findings(tmp_path) == []
    (root / "tooling").mkdir()
    errs = O.subject_dir_findings(tmp_path)
    assert len(errs) == 1
    assert errs[0].level == "error" and errs[0].code == "subject-dir"
    assert "tooling" in errs[0].where and "EMPTY" in errs[0].detail


def test_a_populated_undeclared_subject_says_so_differently(tmp_path):
    """A folder with documents in it is reported once as a directory, and the
    detail says the documents are reported separately -- so the reader is not
    told to go hunting for a cause that is already on the same screen."""
    d = tmp_path / "knowledge/system/tooling"
    d.mkdir(parents=True)
    (d / "a.md").write_text("x")
    errs = O.subject_dir_findings(tmp_path)
    assert len(errs) == 1 and "1 document(s)" in errs[0].detail


def test_a_declared_subject_with_no_directory_is_not_an_error(tmp_path):
    """`publication` has no folder and must not be forced to have one: a
    subject's directory appears on its first leaf, and declaring one empty
    directory per subject to satisfy a check would make the filesystem restate the
    register."""
    (tmp_path / "knowledge/system").mkdir(parents=True)
    assert "publication" in O.SUBJECTS
    assert O.subject_dir_findings(tmp_path) == []


def test_subject_dir_findings_reads_the_register_not_a_copy(tmp_path,
                                                            monkeypatch):
    """One artifact, two readers: the accepted names ARE `SUBJECTS`, so taking
    one out of the register must make its directory an error. A copied list
    would keep accepting it."""
    (tmp_path / "knowledge/system/consolidation").mkdir(parents=True)
    assert O.subject_dir_findings(tmp_path) == []
    # SUBJECTS is a mappingproxy, so the register is replaced rather than
    # mutated -- which is the register being read-only working as intended.
    monkeypatch.setattr(O, "SUBJECTS", types.MappingProxyType(
        {k: v for k, v in O.SUBJECTS.items() if k != "consolidation"}))
    errs = O.subject_dir_findings(tmp_path)
    assert len(errs) == 1 and "consolidation" in errs[0].where


def test_subject_of_accepts_a_document_as_well_as_a_triple(clean):
    class _Doc:
        kind, rel, fm = "knowledge", "knowledge/system/knowledge/alpha.md", {}
    assert O.subject_of(_Doc()) == "knowledge"
    assert O.subject_of("leaf", "memory/knowledge/system/knowledge/alpha.md", {}) == \
        "knowledge"


def test_subjects_is_a_category_register_and_retrieval_is_not_in_it():
    """The test that keeps this a category register: a category names a place
    you could point at. `retrieval` spans four modules, so it is a concept and
    lives in `tags:` (`PLAN.md` §The cognitive layering)."""
    assert "retrieval" not in O.SUBJECTS
    assert "tags" in O.FACETS and not O.FACETS["tags"].domain


# ── O1h: the relation register ─────────────────────────────────────────────

def test_relations_returns_the_two_registers_separately():
    walk, coin = O.relations()
    assert len(walk) == 6 and len(coin) == 4
    assert {r.column for r in walk} == {"assertion"}
    assert {r.column for r in coin} == {"coincidence"}


def test_no_coincidence_appears_in_the_walkable_set():
    walk, coin = O.relations()
    assert not set(id(r) for r in walk) & set(id(r) for r in coin)
    for name in ("same-subject", "same-area", "same-scope", "same-cwd"):
        assert not O.RELATIONS[name].walkable, name


def test_cites_is_a_declared_rule_with_no_key_and_none_planned():
    """The OWED was STRUCK 2026-10-09 (SPECS O1h, §Not specified item 2).
    The rule survives as a nightly `knowledge→skill link` proposal; the key does
    not, and a key with no writer is decoration — which is why the OWED, not
    the relation, is what retirement closes."""
    r = O.RELATIONS["cites"]
    assert "OWED" not in r.writer
    assert "STRUCK" in r.criteria
    assert r.from_ == "skill"
    assert r.to == "leaf"
    # it is still an ASSERTION, just an unwritten one: filing it as a
    # coincidence would say 'not an edge', which is a different claim
    assert r.walkable is True
    assert r.column == "assertion"


# ── O1i: identity ──────────────────────────────────────────────────────────

def test_the_live_tree_has_no_stem_collision():
    assert O.collisions() == []


def test_a_collision_between_a_leaf_and_a_skill_is_reported(clean):
    """The stem is the identifier, so a collision makes an edge ambiguous."""
    (clean / "skills/system/practice/alpha").mkdir(parents=True)
    (clean / "skills/system/practice/alpha/SKILL.md").write_text(
        "---\nname: alpha\n---\n\n# Alpha\n")
    O.reset()
    found = O.collisions(clean)
    assert found and found[0][0] == "alpha"
    assert {t for t, _ in found[0][1]} == {"leaf", "skill"}


# ── O1j: file naming, declared once ────────────────────────────────────────

def test_naming_rules_numbered_from_one_and_each_with_criteria():
    assert [r.id for r in O.NAMING] == list(range(1, 10))
    for r in O.NAMING:
        assert r.criteria and r.reviewed


def test_the_live_tree_names_no_naming_violation_at_all():
    """The exit criterion, in its final form: nothing to report.

    It read `{violation} == {8}` until 2026-10-13. **Violation 9 left the set
    on 2026-10-09 (O3e)**, when the 13 `dev/*/_refs/` files were renamed, and
    **violation 8 on 2026-10-13**, when
    `reference_agent-prompt-dream-memory-consolidation.md` became
    `agent-prompt-dream-memory-consolidation.md`. The register keeps both
    entries as `ratified`: the rule they broke still stands, and the entry is
    the record of what the breach was.

    The register's USE is still pinned, on fixtures that can be made to break a
    rule: `test_a_new_naming_violation_is_an_error_not_a_warning` and
    `test_a_declared_facet_value_warns_with_its_register_entry`."""
    findings = O.naming_findings()
    assert not [f for f in findings if f.level == "error"]
    assert findings == []


def test_a_new_naming_violation_is_an_error_not_a_warning(tmp_path):
    (tmp_path / "memory/knowledge").mkdir(parents=True)
    (tmp_path / "memory/knowledge/Title Case File.md").write_text("# x\n")
    findings = O.naming_findings(tmp_path)
    undeclared = [f for f in findings if not f.violation]
    assert len(undeclared) == 1 and undeclared[0].level == "error"
    assert "Title Case File.md" in undeclared[0].where


def test_an_ignored_scratch_file_is_not_a_naming_target(tmp_path):
    """`dev/figures/logs/` is where a figure job writes, and `.gitignore` says it
    is machine state rather than the repository's shape. Feeding it to the
    naming rules failed every commit on filenames nobody chose.

    The file is never `git add`ed, so removing the ignore rule also pins
    `--others`: a plain `git ls-files` would hide it too, and a leaf a session
    just wrote must still be checked."""
    import subprocess
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    log = tmp_path / "dev/figures/logs/F8-launch1.log"
    log.parent.mkdir(parents=True)
    log.write_text("x\n")
    ignore = tmp_path / ".gitignore"
    ignore.write_text("logs/\n")
    assert O.naming_findings(tmp_path) == []
    ignore.write_text("")
    got = [f for f in O.naming_findings(tmp_path) if f.code == "naming:3"]
    assert [f.where for f in got] == ["dev/figures/logs/F8-launch1.log"]


# ── O1k: the violations register ───────────────────────────────────────────

def test_every_violation_has_a_state_from_the_declared_vocabulary():
    for v in O.violations():
        assert v.state in O.STATES, v.n
        assert v.what and v.recommendation


def test_the_register_carries_the_ten_specs_items_plus_the_two_found_since():
    ns = [v.n for v in O.violations()]
    assert ns == list(range(1, 13))
    # 11 was ADDED by this implementation: the structural check found a
    # `promoted_from:` naming a journal entry that is dated a day later. An
    # undeclared breach is an error, so it is declared here rather than left
    # failing -- recorded because the register is a measurement, not a wish.
    assert O.VIOLATIONS[10].edge == "promoted_from"
    # 12 is R1k's instance-reference measurement: not a breach of a naming
    # or edge rule but a MEASUREMENT of which engine files still name this
    # installation. Its `surfaced_by` is the surface that reads it, which is
    # how the gate finds its own declaration rather than depending on an id.
    assert O.VIOLATIONS[11].surfaced_by == "instance-refs"
    assert all(p.startswith("engine/") for p in O.VIOLATIONS[11].paths)
    # 12 is R1k's instance-reference measurement: not a breach of a naming or
    # edge rule but a MEASUREMENT of which engine files still name this
    # installation. Its `surfaced_by` is the surface that reads it, which is
    # how the gate finds its own declaration rather than depending on an id.
    assert O.VIOLATIONS[11].surfaced_by == "instance-refs"
    assert all(p.startswith("engine/") for p in O.VIOLATIONS[11].paths)


def test_violations_command_lists_every_one_with_its_state(capsys):
    from cli import cli
    from lib import invocation
    inv = invocation.parse(["violations"], cli.ONTOLOGY, "/tmp", "/tmp")
    assert cli.ontology_cmd(inv) == 0
    out = capsys.readouterr().out
    for v in O.violations():
        assert str(v.n) in out and v.state in out


# ── O1l: the check, and the warn/fail distinction ──────────────────────────

def test_the_structural_check_reports_nothing_on_the_live_tree():
    """The ontology's own exit criterion, and the register is why it is
    reachable: every breach it found was either fixed or declared, so the check
    is SILENT rather than merely green.

    A register that hid a live breach would fail here too -- entries are matched
    against real findings, so an entry whose breach is gone reports nothing and
    a breach with no entry is an error (`test_an_undeclared_facet_value_fails`).
    This replaces `..._with_the_open_violations_named`, which asserted the set
    was non-empty: there were five on 2026-10-13 and there are none now."""
    assert O.structural_findings() == []


def test_a_router_past_the_concentration_rule_warns(clean):
    """Violation 10, applied 2026-10-13.

    The rule asks how many rows ONE ROUTER must triage, so a branch is not the
    unit: `system/CONTEXT.md` lists thirteen subjects and the subject routers
    below it list the leaves. Measured by branch the live tree reported 33
    leaves against a router that never sees them; measured per router, the
    largest subject holds 8 and nothing is reported."""
    # 13 added to the fixture's own `knowledge/system/knowledge/alpha.md`: 14
    # leaves behind a single router, over the rule.
    for i in range(13):
        _leaf(clean, f"knowledge/system/knowledge/many{i}.md", trust="trusted")
    O.reset()
    got = [f for f in O.branch_findings() if f.code == "branch-size"]
    assert [f.where for f in got] == ["memory/knowledge/system/knowledge/"], got
    assert "14 leaves" in got[0].detail and got[0].violation == 10


def test_leaves_spread_over_subject_routers_do_not_warn(clean):
    """The other direction, and the reading that made the live tree clean:
    thirteen subjects holding one leaf each is thirteen routers triaging one row
    apiece, not one router triaging thirteen."""
    for i in range(13):
        _leaf(clean, f"knowledge/system/subject{i}/one.md", trust="trusted")
    O.reset()
    assert not [f for f in O.branch_findings() if f.code == "branch-size"]


def test_an_undeclared_facet_value_fails(clean):
    _leaf(clean, "knowledge/system/knowledge/bogus.md", trust="bogus")
    O.reset()
    errors = [f for f in O.structural_findings(clean) if f.level == "error"]
    assert any("trust: bogus" in f.detail for f in errors)


def test_a_journal_entry_may_declare_a_registered_subject(clean):
    """2026-10-21: the check tested the KEY (`"subject" not in SUBJECTS`) instead of
    the value, so the first journal entry to declare `subject: consolidation` -- a
    registered subject -- failed the gate. No file had carried the field before."""
    _leaf(clean, "journal/2026/10/2026-10-21_triage.md", subject="consolidation")
    O.reset()
    assert [f for f in O.structural_findings(clean)
            if f.code.startswith(("subject", "facet:subject"))] == []
    _leaf(clean, "journal/2026/10/2026-10-21_other.md", subject="nonsense")
    O.reset()
    errors = [f for f in O.structural_findings(clean) if f.level == "error"]
    assert any("subject: nonsense" in f.detail for f in errors)


def test_a_declared_facet_value_warns_with_its_register_entry(clean):
    _leaf(clean, "knowledge/system/knowledge/old.md", trust="outdated")
    O.reset()
    got = [f for f in O.structural_findings(clean) if f.code == "facet:trust"]
    assert len(got) == 1 and got[0].level == "warn" and got[0].violation == 1


def test_check_exits_non_zero_on_an_undeclared_value(clean, monkeypatch, capsys):
    """The exit criterion's second half, through the CLI it names."""
    from cli import cli
    from lib import invocation
    _leaf(clean, "knowledge/system/knowledge/bogus.md", trust="bogus")
    O.reset()
    monkeypatch.setattr(O, "AGENTS", clean)
    inv = invocation.parse(["check"], cli.ONTOLOGY, "/tmp", str(clean))
    assert cli.ontology_cmd(inv) == 1
    assert "undeclared error" in capsys.readouterr().out


def test_an_undeclared_branch_is_an_error(clean):
    _leaf(clean, "knowledge/nowhere/alpha.md", trust="trusted")
    O.reset()
    errors = [f for f in O.structural_findings(clean) if f.level == "error"]
    assert any(f.code == "branch" for f in errors)


def test_the_pre_o2_layout_warns_rather_than_failing(clean):
    _leaf(clean, "knowledge/meta/alpha.md", trust="trusted")
    O.reset()
    got = [f for f in O.structural_findings(clean) if f.code == "pre-o2-layout"]
    assert got and got[0].level == "warn" and got[0].violation == 0


# ── O1m: the review cadence ────────────────────────────────────────────────

def test_nothing_is_stale_today_and_the_section_still_prints():
    assert O.review_findings() == []
    assert O.review_lines()[0].startswith("ok ")


def test_a_value_backdated_200_days_warns_and_does_not_fail():
    """The exit criterion: a stale definition is a signal. Warnings, and the
    section reports them without raising -- so the healthcheck exits 0."""
    later = dt.date.fromisoformat(O.REVIEWED) + dt.timedelta(days=200)
    findings = O.review_findings(later)
    assert findings and all(f.level == "warn" for f in findings)
    lines = O.review_lines(later)
    assert lines and all(line.startswith("warn ") for line in lines)


def test_the_cadence_boundary_is_the_declared_one():
    base = dt.date.fromisoformat(O.REVIEWED)
    at = base + dt.timedelta(days=O.CADENCE_DAYS)
    past = base + dt.timedelta(days=O.CADENCE_DAYS + 1)
    assert O.review_findings(at) == []
    assert O.review_findings(past)


def test_every_facet_subject_and_naming_rule_carries_a_reviewed_date():
    for entry in list(O.facets()) + list(O.subjects()) + list(O.naming()):
        dt.date.fromisoformat(entry.reviewed)


# ── the resolution rules the two edge resolvers now share ──────────────────

def test_the_five_queue_items_that_closed_were_resolver_defects(clean):
    """Stated as a test because it is the phase's headline result: the names
    were real, and the resolvers' node set was too small."""
    _leaf(clean, "knowledge/system/knowledge/alpha.md", related="[voice]")
    O.reset()
    idx = O.index(clean)
    assert O.resolve("voice", agents=clean, idx=idx) == (
        "convention", "config/practice/conventions/voice.md")
    assert O.resolve("02_AREAS/x/y.md", agents=clean, idx=idx)[0] == "external"
