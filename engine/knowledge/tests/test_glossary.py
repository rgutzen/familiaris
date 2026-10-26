"""O3c — the generated subject glossary.

The invariants that earn their keep here: every row is traceable to the
register (nothing authored), the leaf is IDEMPOTENT (a second build writes
nothing), a register change DRIFTS it (the point of generating rather than
writing it by hand), and `--check` exits 3 on drift and 0 when in sync.
"""
import pathlib

import pytest

from knowledge import glossary


# ── the cells come from the register, never from the writer ───────────────
def test_every_subject_appears_once_with_its_register_name_and_criteria():
    from knowledge import ontology
    text = glossary.render_glossary()
    for sid, s in ontology.SUBJECTS.items():
        assert f"| `{sid}` | {s.name} |" in text, f"{sid} row missing"
        # the criteria is copied verbatim (whitespace folded), not summarised
        assert " ".join(s.criteria.split())[:40] in text, f"{sid} criteria absent"


def test_rows_are_sorted_by_subject_id_so_the_diff_is_readable():
    from knowledge import ontology
    text = glossary.render_glossary()
    ids = sorted(ontology.SUBJECTS)
    positions = [text.index(f"| `{sid}` |") for sid in ids]
    assert positions == sorted(positions)


def test_the_leaf_carries_a_generated_banner_and_no_hand_maintained_prose():
    text = glossary.render_glossary()
    assert glossary.BANNER in text
    assert "do not hand-edit" in glossary.BANNER


def test_a_subject_with_no_places_prints_a_dash_not_an_empty_cell():
    """A subject that occupies no directory rendered its cell as `—`; a
    generated table with a blank cell reads as a bug."""
    from knowledge import ontology
    places_cells = []
    for line in glossary.render_glossary().splitlines():
        if line.startswith("| `") and line.count("|") == 5:
            places_cells.append(line.split("|")[4].strip())
    assert places_cells, "no subject rows parsed"
    assert all(cell for cell in places_cells)
    assert not any(cell == "" for cell in places_cells)


# ── idempotence and drift ────────────────────────────────────────────────
def test_building_twice_writes_nothing_the_second_time(tmp_path):
    root = tmp_path / "memory"
    (root / "knowledge" / "system").mkdir(parents=True)
    p = glossary.plan(root)
    assert not p.failed
    p.apply()
    again = glossary.plan(root)
    assert again.drift == []


def test_a_register_change_drifts_the_leaf(tmp_path, monkeypatch):
    """This is WHY it is generated: if the criteria changes and the leaf does
    not follow, `--check` must notice."""
    root = tmp_path / "memory"
    (root / "knowledge" / "system").mkdir(parents=True)
    glossary.plan(root).apply()          # build once against the live register

    from knowledge import ontology
    fake = dict(ontology.SUBJECTS)
    first = next(iter(fake))
    import dataclasses
    fake[first] = dataclasses.replace(fake[first], criteria="CHANGED BY THE TEST")
    monkeypatch.setattr(ontology, "SUBJECTS", fake)

    assert glossary.plan(root).drift != []


def test_check_exits_3_on_drift_and_0_when_in_sync(tmp_path, monkeypatch):
    root = tmp_path / "memory"
    (root / "knowledge" / "system").mkdir(parents=True)
    monkeypatch.setattr(glossary, "DEFAULT_ROOT", root)
    assert glossary.main(["--check"]) == 3      # nothing written yet -> drift
    glossary.plan(root).apply()
    assert glossary.main(["--check"]) == 0      # now in sync


def test_a_missing_knowledge_tree_is_an_error_not_an_empty_leaf(tmp_path):
    p = glossary.plan(tmp_path / "nope")
    assert p.failed
    assert p.writes == []


# ── the leaf lands where the publication branch is created ───────────────
def test_the_target_creates_the_publication_branch():
    assert glossary.GLOSSARY_REL == "knowledge/system/publication/glossary.md"


def test_a_rebuild_keeps_the_counts_stage_2_wrote(tmp_path):
    """Consolidation stage 2 counts reads into `use_count`/`last_used` (M2a).
    A rebuild that reset them would undo every night's count, and a check that
    compared them would report drift every morning."""
    from knowledge import frontmatter
    root = tmp_path / "memory"
    (root / "knowledge").mkdir(parents=True)
    glossary.plan(root).apply()
    leaf = root / glossary.GLOSSARY_REL
    frontmatter.update(leaf, {"use_count": 2, "last_used": "2026-10-09"})
    assert glossary.plan(root).drift == []
    glossary.plan(root).apply()
    fm = frontmatter.read(leaf)
    assert str(fm["use_count"]) == "2" and str(fm["last_used"]) == "2026-10-09"


# ── the vault a write goes to is this tree's, or it is refused ───────────────

def test_a_write_into_another_checkout_s_vault_is_refused(tmp_path, monkeypatch):
    """Measured 2026-10-14: `familiar knowledge glossary` from the publication
    worktree, with `PAZRAS_MEMORY_DIR` unset, rewrote `~/06_SYSTEM`'s glossary
    with this branch's pruned register — dropping `memory/journal`,
    `config/backup` and `config/schedule` from a tree that has all three. The
    default root is the INSTALL's vault, which is right for a read and ruinous
    for a write, so the write is what carries the guard."""
    # The override is the documented way THROUGH the guard, so a gate run that
    # sets it for a worktree must not turn this refusal into a write.
    monkeypatch.delenv("PAZRAS_MEMORY_DIR", raising=False)
    other = tmp_path / "another-vault"
    (other / "knowledge").mkdir(parents=True)
    monkeypatch.setattr(glossary, "DEFAULT_ROOT", other)
    with pytest.raises(SystemExit) as exc:
        glossary.main([])
    assert "PAZRAS_MEMORY_DIR" in str(exc.value)
    # and the read is NOT refused: it reports, and says which vault it read
    assert glossary.main(["--check"]) == 3


def test_this_tree_s_own_vault_is_written_without_being_asked(tmp_path,
                                                              monkeypatch):
    """The guard must not obstruct the ordinary case: a run whose vault IS this
    checkout's own memory tree writes, with no environment variable set."""
    root = tmp_path / "memory"
    (root / "knowledge").mkdir(parents=True)
    monkeypatch.setattr(glossary, "DEFAULT_ROOT", root)
    monkeypatch.setattr(glossary.roots, "MEMORY", root)
    assert glossary.main([]) == 0
    assert (root / glossary.GLOSSARY_REL).exists()
