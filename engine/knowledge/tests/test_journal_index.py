"""The journal index's two invariants and its one trap.

WHY THIS FILE EXISTS AT ALL. `journal_index` is the module that talks to
Ollama and writes a cache outside the repo, and it had no test -- so every
change to it was verified by running it against the live corpus, which is how
a 1,514-chunk rebuild becomes part of a unit test's feedback loop. The seam is
one function wide (`embed`), and every test here stubs it: a test that needs a
model server is a test that passes on one machine and fails everywhere else.

THE TRAP. A facet is a key on a chunk, and Python does not error on a missing
key -- it returns False. So an index built before `branch` existed answers a
filtered search with ZERO hits and no error, and a search that used to work
looks like a search with nothing to find. `test_the_schema_stamp_forces_a_
rebuild` writes that index by hand and asserts the rebuild, because the
failure mode has no other symptom.

What is NOT tested here: the numbers. `branch_of_cwd` is asserted against
R1h's four CLASSES; the split over the live corpus (170/20/55/26 on
2026-10-09) is a measurement, and `journal search`'s exit records it.
"""
import json
import os
import pathlib

import pytest

from knowledge import journal_index as ji
from knowledge import ontology

ENTRY = "# Title\n\n## What was done\n\nrestic backup ran here\n"

# R1h's four classes, as cwd values. Built from the real home because `build()`
# derives the facet from the machine it runs on -- the same reason the
# production path cannot be made hermetic, stated rather than hidden.
HOME = pathlib.Path.home()
SYSTEM_CWD = str(HOME / ji.SYSTEM_DIR)
PROJECT_CWD = str(HOME / ji.PROJECTS_DIR / "demo")
AREA_CWD = str(HOME / ji.AREAS_DIR / "B_Tech")


# ── the seam ─────────────────────────────────────────────────────────────────

VOCAB = ("restic", "backup", "journal", "facet")


def _stub_embed(texts, model=""):
    """A deterministic stand-in: a bag of four words, so ranking is real
    (a query about restic outranks a chunk that never says it) without a
    model, a port, or a machine that has the weights pulled."""
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


@pytest.fixture(autouse=True)
def _no_ollama(monkeypatch):
    monkeypatch.setattr(ji, "_post_json", _raise_ollama)
    monkeypatch.setattr(ji, "embed", _stub_embed)


def _raise_ollama(*_a, **_kw):
    raise AssertionError("a test reached for Ollama; stub `embed` instead")


# ── fixtures ─────────────────────────────────────────────────────────────────

def _entry(memory: pathlib.Path, rel: str, cwd=None, touches=None) -> pathlib.Path:
    p = memory / "journal" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = []
    if cwd is not None:
        fm.append(f"cwd: {cwd}")
    if touches:
        fm.append("touches: [" + ", ".join(touches) + "]")
    head = ("---\ntitle: t\ndate: 2026-10-09\n" + "\n".join(fm)
            + "\n---\n\n") if fm else ""
    p.write_text(head + ENTRY)
    return p


@pytest.fixture
def memory(tmp_path):
    """Four entries, one per class of `cwd:`, plus a router that must not be
    indexed at all. Two of them carry `touches:` — a facet only stage 1 writes,
    so a fixture is the only way to see one before the next session is distilled.
    """
    m = tmp_path / "memory"
    _entry(m, "2026/10/2026-10-01_system.md", SYSTEM_CWD,
           touches=["knowledge", "consolidation"])
    _entry(m, "2026/10/2026-10-02_project.md", PROJECT_CWD)
    _entry(m, "2026/10/2026-10-03_area.md", AREA_CWD, touches=["backup"])
    _entry(m, "2026/10/2026-10-04_none.md")
    _entry(m, "2026/10/2026-10-05_ambiguous.md", str(HOME))
    (m / "journal" / "CONTEXT.md").write_text("# Router\n\nnot a session\n")
    return m


@pytest.fixture
def base(tmp_path):
    return tmp_path / "data"


def _index(base) -> dict:
    return json.loads((base / "journal-index" / "index.json").read_text())


# ── the derivation (R1h) ─────────────────────────────────────────────────────

def test_the_four_classes_of_cwd():
    home = pathlib.Path("/home/someone")
    assert ji.branch_of_cwd("/home/someone/06_SYSTEM/x", home=home) == (ji.SYSTEM, "")
    assert ji.branch_of_cwd("/home/someone/01_PROJECTS/demo/sub", home=home) == \
        (ji.PROJECTS, "demo")
    assert ji.branch_of_cwd("/home/someone/02_AREAS/B_Tech", home=home) == (ji.AREAS, "B")
    assert ji.branch_of_cwd(None, home=home) == (ji.UNKNOWN, "")


@pytest.mark.parametrize("cwd", [
    "/home/someone",                    # the home directory itself
    "/home/someone/03_ZETTEL/notes",     # a PARA directory with no branch
    "/home/someone/06_SYSTEMX",          # a prefix, not a path
    "/tmp", "relative/path", "", None, "~",
])
def test_everything_else_is_unknown_never_guessed(cwd):
    assert ji.branch_of_cwd(cwd, home=pathlib.Path("/home/someone")) == (ji.UNKNOWN, "")


def test_the_branch_values_are_the_registers_branches():
    """The three ids are `subjects.yaml`'s, and this is what keeps them so: a
    rename in the register fails here rather than silently producing a fourth
    value that nothing filters on and no one sees."""
    assert set(ji.BRANCH_VALUES) - {ji.UNKNOWN} == set(ontology.BRANCHES)


def test_a_missing_or_bad_branch_is_an_error_not_an_empty_page():
    assert ji.validate_branch("system") == "system"
    assert ji.validate_branch("unknown") == "unknown"
    with pytest.raises(ValueError):
        ji.validate_branch("backup")           # a SUBJECT, not a branch
    with pytest.raises(ValueError):
        ji.validate_branch("")


# ── the build ────────────────────────────────────────────────────────────────

def test_each_chunk_carries_the_facet_of_its_file(memory, base):
    stats = ji.build(str(memory), str(base))
    idx = _index(base)
    assert "CONTEXT.md" not in " ".join(idx["files"])       # a router is not content
    by_path = {c["path"]: c["branch"] for c in idx["chunks"]}
    assert by_path["journal/2026/10/2026-10-01_system.md"] == ji.SYSTEM
    assert by_path["journal/2026/10/2026-10-02_project.md"] == ji.PROJECTS
    assert by_path["journal/2026/10/2026-10-03_area.md"] == ji.AREAS
    assert by_path["journal/2026/10/2026-10-04_none.md"] == ji.UNKNOWN
    assert stats["files_unmapped"] == 2                     # no `cwd:`, and `~`
    assert idx["schema"] == ji.SCHEMA
    # The per-file record too, so the build log's ambiguous count is checkable
    # without walking the chunks.
    assert idx["files"]["journal/2026/10/2026-10-03_area.md"]["locator"] == "B"


def test_a_second_build_changes_nothing(memory, base):
    first = ji.build(str(memory), str(base))
    second = ji.build(str(memory), str(base))
    assert first["files_changed"] == 5
    assert second["files_changed"] == 0
    assert second["chunks_embedded"] == 0
    assert second["files_removed"] == 0
    assert second["total_chunks"] == first["total_chunks"]


def test_one_changed_entry_rebuilds_one_file(memory, base):
    ji.build(str(memory), str(base))
    p = memory / "journal" / "2026" / "10" / "2026-10-02_project.md"
    p.write_text(p.read_text() + "\n## Later\n\nmore\n")
    os.utime(p, (1_700_000_000, 1_700_000_000))             # coarser than one build
    stats = ji.build(str(memory), str(base))
    assert stats["files_changed"] == 1
    assert stats["chunks_embedded"] == 3                    # frontmatter + two H2s
    left = [c for c in _index(base)["chunks"]
            if c["path"].endswith("2026-10-02_project.md")]
    assert all(c["branch"] == ji.PROJECTS for c in left)


def test_a_removed_entry_drops_its_chunks(memory, base):
    ji.build(str(memory), str(base))
    (memory / "journal" / "2026" / "10" / "2026-10-03_area.md").unlink()
    stats = ji.build(str(memory), str(base))
    assert stats["files_removed"] == 1
    assert not [c for c in _index(base)["chunks"] if c["branch"] == ji.AREAS]


# ── the trap ─────────────────────────────────────────────────────────────────

def test_the_schema_stamp_forces_a_rebuild(memory, base):
    """An index built before the facet is not silently filtered to nothing.

    Hand-written, not simulated: this is exactly what is on disk on the
    machine that upgrades, and the assertion that the old shape returns ZERO
    hits is the bug the stamp exists to catch."""
    ji.build(str(memory), str(base))
    idx = _index(base)
    idx["schema"] = 1
    for c in idx["chunks"]:
        c.pop("branch")
        c.pop("locator")
    (base / "journal-index" / "index.json").write_text(json.dumps(idx))

    assert ji.search(str(memory), str(base), "restic", branch=ji.SYSTEM) == []
    assert ji.summary(str(base))["branches"] == {"(none)": len(idx["chunks"])}

    stats = ji.build(str(memory), str(base))
    assert stats["files_changed"] == 5                      # everything, not the delta
    assert ji.summary(str(base))["schema"] == ji.SCHEMA
    assert ji.search(str(memory), str(base), "restic", branch=ji.SYSTEM)


def test_a_changed_model_still_rebuilds_everything(memory, base):
    ji.build(str(memory), str(base))
    stats = ji.build(str(memory), str(base), model="other-model")
    assert stats["files_changed"] == 5


# ── the pre-filter ───────────────────────────────────────────────────────────

def test_the_filter_selects_a_subset_and_top_counts_within_it(memory, base):
    ji.build(str(memory), str(base))
    everything = ji.search(str(memory), str(base), "restic", top=99)
    assert len(everything) == 9            # five entries: frontmatter block + H2
    one = ji.search(str(memory), str(base), "restic", top=99, branch=ji.PROJECTS)
    assert [h["branch"] for h in one] == [ji.PROJECTS] * 2
    # `top` is the cut INSIDE the subset: asked for one, got one -- not one
    # surviving a post-hoc prune of an unfiltered ranking.
    assert len(ji.search(str(memory), str(base), "restic", top=1, branch=ji.SYSTEM)) == 1
    assert len(one) < len(everything)


def test_ranking_inside_the_subset_is_by_similarity(memory, base):
    _entry(memory, "2026/10/2026-10-06_system.md", SYSTEM_CWD)
    p = memory / "journal" / "2026" / "10" / "2026-10-06_system.md"
    p.write_text(p.read_text().replace("restic backup ran here",
                                       "backup backup backup backup"))
    ji.build(str(memory), str(base))
    hits = ji.search(str(memory), str(base), "backup", top=9, branch=ji.SYSTEM)
    assert hits[0]["score"] > hits[-1]["score"]
    assert hits[0]["text"].lower().count("backup") > 1


def test_an_empty_facet_returns_nothing_without_embedding_the_query(
        memory, base, monkeypatch):
    """A facet that selects no chunk costs no embedding call, and the caller
    gets the shape of the index back so it can say WHY the page is empty."""
    ji.build(str(memory), str(base))
    calls = []
    monkeypatch.setattr(ji, "embed",
                        lambda texts, model="": calls.append(texts) or _stub_embed(texts))
    assert ji.search(str(memory), str(base), "restic", branch="nothing-here") == []
    assert calls == []
    assert ji.summary(str(base))["chunks"] == 9
    assert "no chunk matches" in ji._no_hits(str(base), ji.AREAS, None)
    assert "no index yet" in ji._no_hits(str(base / "elsewhere"), None, None)


# ── the second facet: `touches:` (C2) ────────────────────────────────────────

def test_a_chunk_carries_the_touches_its_entry_declares(memory, base):
    ji.build(str(memory), str(base))
    idx = _index(base)
    by_path = {c["path"]: c["touches"] for c in idx["chunks"]}
    assert by_path["journal/2026/10/2026-10-01_system.md"] == ["knowledge",
                                                              "consolidation"]
    assert by_path["journal/2026/10/2026-10-03_area.md"] == ["backup"]
    assert by_path["journal/2026/10/2026-10-02_project.md"] == []
    assert idx["files"]["journal/2026/10/2026-10-03_area.md"]["touches"] == ["backup"]
    assert ji.summary(str(base))["touches_chunks"] == 4      # two entries, two chunks each


def test_touches_is_read_verbatim_and_never_validated_here():
    """The index mirrors the record. An out-of-domain subject is
    `ontology.facet_findings`' finding, in the entry -- not a second vocabulary
    rule in this module, which is how the two would come to disagree."""
    assert ji.touches_of(["backup", "backup", "knowledge"]) == ["backup", "knowledge"]
    assert ji.touches_of("backup") == ["backup"]           # a bare value is a list of one
    assert ji.touches_of("  ") == [] and ji.touches_of(None) == []
    assert ji.touches_of("knolwedge") == ["knolwedge"]     # the register reports it


def test_the_touches_filter_selects_a_subset_and_top_counts_within_it(memory, base):
    ji.build(str(memory), str(base))
    one = ji.search(str(memory), str(base), "restic", top=99, touches="backup")
    assert [h["touches"] for h in one] == [["backup"]] * 2
    assert len(one) == 2
    assert len(ji.search(str(memory), str(base), "restic", top=1, touches="backup")) == 1
    # Both facets intersect rather than override: `areas` has chunks and
    # `backup` has chunks, and their intersection is those two.
    both = ji.search(str(memory), str(base), "restic", top=99,
                     branch=ji.AREAS, touches="backup")
    assert len(both) == 2 and all(h["branch"] == ji.AREAS for h in both)
    assert ji.search(str(memory), str(base), "restic", branch=ji.PROJECTS,
                     touches="backup") == []


def test_the_touches_filter_says_when_no_entry_carries_the_facet(memory, base):
    """The C2 trap: an index whose entries predate the facet answers a
    `--touches=` search with zero hits and no error, which reads as "nothing
    matches" rather than "nothing is labelled yet". Say which."""
    ji.build(str(memory), str(base))
    msg = ji._no_hits(str(base), None, "knowledge")
    assert "no chunk matches" in msg
    # ... and when NOTHING carries it, the message names that instead:
    idx = _index(base)
    for c in idx["chunks"]:
        c.pop("touches")
    (base / "journal-index" / "index.json").write_text(json.dumps(idx))
    msg = ji._no_hits(str(base), None, "knowledge")
    assert "no chunk carries `touches:` at all yet" in msg


def test_a_v2_index_is_rebuilt_for_touches_too(memory, base):
    """Bumping SCHEMA is what makes the facet present rather than absent, and
    the absence is invisible -- the same trap as v1's `branch`."""
    ji.build(str(memory), str(base))
    idx = _index(base)
    idx["schema"] = 2
    for c in idx["chunks"]:
        c.pop("touches")
    (base / "journal-index" / "index.json").write_text(json.dumps(idx))
    assert ji.search(str(memory), str(base), "restic", touches="backup") == []
    stats = ji.build(str(memory), str(base))
    assert stats["schema"] == ji.SCHEMA == 3
    assert stats["files_changed"] == 5
    assert ji.search(str(memory), str(base), "restic", touches="backup")


def test_a_touches_value_that_is_not_a_subject_is_an_error(memory, base, capsys):
    assert ji.validate_touches("backup") == "backup"
    with pytest.raises(ValueError):
        ji.validate_touches("backup/")            # a path, not an id
    code = ji.main(["search", "restic", "--touches=nope"], str(base), str(memory))
    assert code == 1
    assert "is not a subject" in capsys.readouterr().err


def test_a_hit_is_a_pointer_to_the_entry_never_a_copy(memory, base):
    """The governing rule: the index ranks, markdown is the truth. Every hit
    carries the location and no chunk claims to be the section itself."""
    ji.build(str(memory), str(base))
    for h in ji.search(str(memory), str(base), "restic", top=99):
        assert {"path", "header", "start_line", "end_line", "score", "branch"} <= set(h)
        assert "embedding" not in h
        assert h["start_line"] >= 1 and h["end_line"] >= h["start_line"]


# -- the command line --------------------------------------------------------
def test_help_prints_the_usage_and_does_not_start_a_build(memory, base, capsys):
    """`invocation.parse` accepts `--help` for every spec, so a verb that
    ignores it answers a question with minutes of Ollama. The trap is named in
    the module's own handoff; this pins the fix."""
    assert ji.main(["index", "--help"], str(base), str(memory)) == 0
    assert "usage" in capsys.readouterr().out
    assert not (base / "journal-index" / "index.json").exists()
    assert ji.main(["search"], str(base), str(memory)) == 1      # a query is required


def test_a_bad_branch_exits_nonzero_with_the_allowed_values(memory, base, capsys):
    code = ji.main(["search", "restic", "--branch=backup"], str(base), str(memory))
    assert code == 1
    assert "system, areas, projects, unknown" in capsys.readouterr().err
