"""The exporter, proved against a real export.

The end-to-end test at the bottom is the P0 exit criterion as a gate: it builds
the tree into a throw-away directory, reads it back with the leak scanner, and
builds it a second time to show that the second run changes nothing. The unit
tests above it are the pieces of that, each one a way the exporter can quietly
do the wrong thing:

  * the register surgery keeps a declaration whose place travels and drops the
    ones whose place does not -- `ontology check` in the target fails otherwise;
  * the edge pruning keeps an edge that resolves and drops one that does not;
  * a target that is neither empty, a clone, nor a previous export is REFUSED,
    and a file the marker does not list is never touched.
"""
import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import publish  # noqa: E402
from lib import roots  # noqa: E402


# ── the register surgery ─────────────────────────────────────────────────────

REGISTER = """# subjects.yaml -- a miniature
subjects:
  - id: knowledge
    places:
      - memory/knowledge
      - memory/journal
  - id: publication
    places:
      - docs
unmapped:
  - id: engine/lib
    reason: >
      Shared and subject-neutral by design.
  - id: dotfiles
    reason: >
      A symlink to a separate repository.
"""


def test_the_register_keeps_the_places_that_travel():
    present = {"memory/knowledge/INDEX.md", "engine/lib/roots.py"}
    text, dropped = publish.prune_absent_places(REGISTER, present)
    assert sorted(dropped) == ["docs", "dotfiles", "memory/journal"]
    assert "- memory/knowledge" in text
    assert "- memory/journal" not in text
    assert "id: engine/lib" in text
    assert "id: dotfiles" not in text
    # The untouched entry keeps its folded reason and its indentation.
    assert "Shared and subject-neutral by design." in text


def test_the_register_surgery_is_idempotent():
    present = {"docs/x.md"}
    once, _ = publish.prune_absent_places(REGISTER, present)
    twice, dropped = publish.prune_absent_places(once, present)
    assert once == twice and dropped == []


# ── the edge pruning ─────────────────────────────────────────────────────────

LEAF = """---
title: A leaf
related: [backup-restic, boundaries, https://example.org/x]
promoted_from: [journal/2026/08/2026-08-30_m1-seed-the-spine.md]
source: memory/knowledge/system/knowledge/knowledge-index.md
---

# A leaf

Body text, untouched.
"""


def test_edges_that_do_not_travel_are_dropped_and_the_rest_kept():
    stems = {"boundaries"}
    present = {"memory/knowledge/system/knowledge/knowledge-index.md"}
    text, dropped = publish.prune_absent_edges(LEAF, stems, present)
    assert dropped == ["related:backup-restic",
                       "promoted_from:journal/2026/08/2026-08-30_m1-seed-the-spine.md"]
    assert "related: [boundaries, https://example.org/x]" in text
    assert "knowledge-index.md" in text          # a path that does travel
    assert "Body text, untouched." in text


def test_a_file_with_no_frontmatter_is_left_alone():
    text, dropped = publish.prune_absent_edges("# just prose\n", set(), set())
    assert (text, dropped) == ("# just prose\n", [])


# ── the target's permission slip ─────────────────────────────────────────────

# ── what never travels, and what is renamed on the way ───────────────────────

def test_dev_never_travels_whatever_the_classification_says():
    assert publish.never_public(["dev/x/SPECS.md", "engine/familiar",
                                 "docs/dev/x.md"]) == ["dev/x/SPECS.md"]


def test_a_classification_that_makes_dev_public_is_refused(monkeypatch):
    rule = publish.audit.Rule(section="overrides", index=0, path="dev/",
                              cls="public", why="a mistake")
    monkeypatch.setattr(publish.audit, "findings", lambda *a: [])
    monkeypatch.setattr(publish.audit, "tracked", lambda: ["dev/x/SPECS.md"])
    monkeypatch.setattr(publish.audit, "classify", lambda rel, rules: (rule, ""))
    with pytest.raises(SystemExit, match="never"):
        publish.main(["--to", "/nonexistent/familiaris-target"])


def test_a_rename_covers_its_three_spellings_and_stops_at_letters():
    rules = publish.renames({"rename": [{"from": "acme", "to": "work"}]})
    counts = {}
    out = publish._rename(
        b"profile acme, ~/.claude-acme, KEY_ACME, an Acme probe, acmesia\n",
        rules, counts).decode()
    assert out == ("profile work, ~/.claude-work, KEY_WORK, an Work probe, "
                   "acmesia\n")
    assert sum(counts.values()) == 4


def test_a_binary_file_is_not_renamed():
    data = b"\xff\xfeacme"
    assert publish._rename(data, [("acme", "work")], {}) == data


def test_an_empty_directory_is_a_target(tmp_path):
    publish.check_target(tmp_path)          # does not raise


def test_a_clone_is_a_target(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("the public readme\n")
    publish.check_target(tmp_path)


def test_a_directory_with_someone_else_s_files_is_refused(tmp_path):
    (tmp_path / "notes.md").write_text("mine\n")
    with pytest.raises(SystemExit) as exc:
        publish.check_target(tmp_path)
    assert "refusing to write" in str(exc.value)


def test_a_previous_export_is_a_target(tmp_path):
    (tmp_path / "notes.md").write_text("mine\n")
    publish.write_marker(tmp_path, {}, "sha256:x")
    publish.check_target(tmp_path)
    assert publish.read_marker(tmp_path)["managed"] == []
    assert publish.read_marker(tmp_path)["source_hash"] == "sha256:x"


def test_only_a_managed_path_is_ever_removed(tmp_path):
    stage, target = tmp_path / "stage", tmp_path / "target"
    for d in (stage, target):
        (d / "kept").mkdir(parents=True)
    (stage / "kept/a.md").write_text("a\n")
    (target / "kept/a.md").write_text("a\n")
    (target / "mine.md").write_text("a human's file\n")
    d = publish.diff(stage, target, managed={"kept/a.md", "gone.md"})
    assert d.removed == []
    assert d.added == [] and d.modified == []
    assert publish.diff(stage, target, {"mine.md"}).removed == ["mine.md"]


def _counts(out: str) -> dict:
    """`publish.py`'s own added/removed/modified report, read as numbers.

    READ, not substring-matched. The first version of this test asserted
    `"added       0" in first or "added       2" in first`, and the second
    alternative is a substring of `added       279` -- so it passed for a
    279-file export and failed for a 320-file one (the merged tree, 2026-10-14).
    An assertion that holds for any count starting with the digit it names is
    not a measurement.
    """
    found = dict(re.findall(r"^  (added|removed|modified)\s+(\d+)$", out,
                            re.MULTILINE))
    assert set(found) == {"added", "removed", "modified"}, out
    return {k: int(v) for k, v in found.items()}


def test_the_diff_counts_added_removed_and_modified(tmp_path):
    stage, target = tmp_path / "stage", tmp_path / "target"
    (stage / "sub").mkdir(parents=True)
    (target / "sub").mkdir(parents=True)
    (stage / "sub/new.md").write_text("new\n")
    (stage / "sub/changed.md").write_text("after\n")
    (target / "sub/changed.md").write_text("before\n")
    (target / "sub/gone.md").write_text("gone\n")
    d = publish.diff(stage, target, managed={"sub/gone.md", "sub/changed.md"})
    assert d.counts() == (1, 1, 1)
    assert d.added == ["sub/new.md"]
    assert d.removed == ["sub/gone.md"]
    assert d.modified == ["sub/changed.md"]


# ── the export, end to end ───────────────────────────────────────────────────
#
# These four drive the whole exporter, so they need the classification of the
# tree it exports FROM -- `config/publication/publish.yaml`, which `dev/`-omission
# keeps out of the published tree. In the export there is nothing to export and
# no classification to read, so they declare that and skip; the pieces above
# still run there, which is where most of this file's value is.
needs_classification = pytest.mark.skipif(
    not roots.instance_here(),
    reason="it runs the exporter, which reads the classification of the tree it "
           "exports from; `dev/` never travels, so a generated tree has "
           "neither a classification nor anything to export")


@pytest.fixture
def green_gate(monkeypatch, tmp_path):
    """Stand in for `checks.py` with a script that exits 0.

    What these four tests are about is the tree this module WRITES -- the
    surgery, the marker, the diff, the idempotency -- and they call `main()`
    four times between them, so the real gate would add eighty seconds to every
    commit. That a gate RUNS in the stage, and that its verdict reaches the
    report, is still exercised here; which checks are in the real one is
    asserted where its membership lives
    (`engine/checks/tests/test_checks.py`), and that a red one STOPS the
    publish has its own test below.
    """
    ok = tmp_path / "green.py"
    ok.write_text("import sys\n"
                  "print(\"checks.py: gate 'export' passed (24 check(s))\")\n"
                  "sys.exit(0)\n")
    monkeypatch.setattr(publish, "CHECKS_REL", ok)


def test_the_stage_gate_is_the_exported_tree_s_own():
    """The name the exporter runs, pinned.

    Any other value of `--run` is a weaker tree test: a gate that is real but
    not `export` would run a subset of the checks the published tree has to
    pass, and only this line would say so. That `export` is `pre-commit` minus
    exactly its declared exclusions is asserted where the registry lives,
    `engine/checks/tests/test_declared_paths.py`.
    """
    assert publish.GATE == "export"


@needs_classification
def test_a_red_gate_stops_the_publish_before_it_writes(tmp_path, capsys,
                                                       monkeypatch):
    """The point of running the gate in the STAGE rather than on the target: a
    tree that fails its own gate is never copied, so a red export cannot reach
    the clone the human is about to push.

    A one-line script stands in for `checks.py`: the exit code is the whole
    contract between the two, and what makes the real registry red in the stage
    is the registry's own business.
    """
    red = tmp_path / "red.py"
    red.write_text("import sys\n"
                   "print(\"checks.py: FAILED gate 'export'\")\n"
                   "sys.exit(1)\n")
    monkeypatch.setattr(publish, "CHECKS_REL", red)
    target = tmp_path / "public"
    with pytest.raises(SystemExit) as exc:
        publish.main(["--to", str(target)])
    assert "fails its own gate" in str(exc.value)
    capsys.readouterr()
    assert not target.exists()


@needs_classification
def test_the_export_writes_the_public_tree_and_a_second_run_changes_nothing(
        tmp_path, capsys, green_gate):
    """P0's exit criterion, as a gate.

    `publish.py --to <target>` twice from the same commit: the first writes the
    tree and comes back scanner-clean, the second reports 0 added, 0 removed,
    0 modified. Idempotency is a measurement here rather than a hope, because
    the tree is built in a scratch directory and diffed finished against
    finished.
    """
    target = tmp_path / "public"
    assert publish.main(["--to", str(target)]) == 0
    first = capsys.readouterr().out
    assert "0 undeclared or stale" in first
    assert (target / publish.MARKER).exists()

    # The first run writes the whole tree and says how much: the count is the
    # marker's own list, so a file the export silently dropped is a failure.
    written = publish.read_marker(target)["managed"]
    assert len(written) > 200
    assert _counts(first) == {"added": len(written), "removed": 0,
                              "modified": 0}

    # What must not be there: the journals, the user's own decisions, this
    # machine's schedule, and the classification itself.
    for absent in ("memory/journal", "dev", "dotfiles", "DATA-ARCHITECTURE.md"):
        assert not (target / absent).exists(), absent
    # The schedule is its generated unit pairs; the session policy beside them
    # is hand-written and travels, because the scheduler loads it.
    assert sorted(p.name for p in (target / "config/schedule").iterdir()) == \
        ["session-prompt.md", "sessions.yaml"]

    # The user's files and the session pointers travel as the skeleton's
    # placeholders (P2), byte for byte: the instance's own never do.
    skeleton = roots.REPO / "engine/structure/skeleton"
    for seed in ("CLAUDE.md", "AGENTS.md", "CONTEXT.md"):
        assert (target / seed).read_bytes() == (skeleton / seed).read_bytes(), seed
    user = target / "config/practice/user"
    for f in user.iterdir():
        assert f.read_bytes() == (skeleton / "config/practice/user" / f.name).read_bytes(), f

    # What must be: LICENSE, the engine's CLI, the registers and the writing.
    for present in ("LICENSE", "engine/familiar", "config/knowledge/subjects.yaml",
                    "memory/knowledge/INDEX.md", "engine/backup/remotes/example.sh"):
        assert (target / present).exists(), present

    report = capsys.readouterr().out
    assert publish.main(["--to", str(target)]) == 0
    second = capsys.readouterr().out
    assert _counts(second) == {"added": 0, "removed": 0, "modified": 0}
    assert "removed     0" in second
    assert "modified    0" in second
    assert report.count("publish scan") == 0      # --check only


@needs_classification
def test_a_human_s_file_in_the_target_survives_a_publish(tmp_path, capsys,
                                                          green_gate):
    target = tmp_path / "public"
    (target / "notes").mkdir(parents=True)
    (target / "notes/mine.md").write_text("a human put this here\n")
    publish.write_marker(target, {}, "sha256:first")
    assert publish.main(["--to", str(target)]) == 0
    capsys.readouterr()
    assert (target / "notes/mine.md").read_text() == "a human put this here\n"


@needs_classification
def test_check_mode_writes_nothing(tmp_path, capsys, green_gate):
    target = tmp_path / "public"
    assert publish.main(["--to", str(target), "--check"]) == 0
    capsys.readouterr()
    assert not target.exists()


@needs_classification
def test_the_source_hash_moves_when_a_published_source_moves(tmp_path):
    sources = [("LICENSE", None)]
    before = publish.source_hash(sources, roots.CONFIG / "publication" / "publish.yaml")
    assert before.startswith("sha256:")
    assert before == publish.source_hash(
        sources, roots.CONFIG / "publication" / "publish.yaml")


def test_the_marker_records_what_it_wrote(tmp_path):
    target = tmp_path / "public"
    publish.write_marker(target, {"a.md": publish.Exported(path="a.md")},
                         "sha256:x")
    marker = json.loads((target / publish.MARKER).read_text())
    assert marker["managed"] == ["a.md"]
    assert marker["files"] == 1
    assert marker["source_hash"] == "sha256:x"
    assert "never touched" in marker["$comment"]
