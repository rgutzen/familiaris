"""The publication audit, proved by breaking it.

The failure this guards is the FILE NOBODY THOUGHT OF. A deny-list fails open
on exactly that one; an allow-list fails closed, but only if the audit that
enforces it is known to fail -- so every rule below is a test of a way the
classification can be wrong rather than a test that the module exists.

Each test builds a miniature repository and passes the classification in as a
dict, because the audit is a pure function of (tree, classification) and a test
of it should not have to edit `dev/publication/publish.yaml` to prove anything.
The last test is the one that matters: the REAL classification, against the
REAL tree.
"""
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import publish_audit as pa
from lib import roots          # `publish_audit` puts `engine/` on the path


@pytest.fixture
def repo(tmp_path):
    """A miniature repository: two roots, one register, three tracked files."""
    (tmp_path / "engine/lib").mkdir(parents=True)
    (tmp_path / "engine/lib/x.py").write_text("x = 1\n")
    (tmp_path / "engine/lib/y.py").write_text("y = 1\n")
    (tmp_path / "memory/journal/2026").mkdir(parents=True)
    (tmp_path / "memory/journal/2026/a.md").write_text("a\n")
    (tmp_path / "config/knowledge").mkdir(parents=True)
    (tmp_path / "config/knowledge/subjects.yaml").write_text(
        "subjects:\n"
        "  - id: lib\n"
        "    places:\n"
        "      - engine/lib\n"
        "unmapped:\n"
        "  - id: memory/journal\n"
        "    reason: the record\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    return tmp_path


def _cfg(*rules, version="1"):
    """A classification built from rules, plus the baseline every tree needs:
    the audit READS `config/knowledge/subjects.yaml`, which is itself tracked,
    so a fixture that classifies nothing there is testing two things at once."""
    directories, overrides = [], [_dir("config/")]
    for r in rules:
        (overrides if r.get("section") == "overrides" else directories).append(r)
    return {"version": version, "directories": directories,
            "overrides": overrides}


def _dir(path, cls="public", **kw):
    """One `directories:` rule. `class` is a keyword, so the key is spelled."""
    return dict(path=path, why="a reason long enough to read",
                **{"class": cls}, **kw)


def _one(path, cls, **kw):
    """One `overrides:` rule."""
    return dict(path=path, why="a reason long enough to read",
                section="overrides", **{"class": cls}, **kw)


# ── the live repository ──────────────────────────────────────────────────────
#
# These two read `dev/publication/publish.yaml`, the classification of the tree
# the export was made FROM. `dev/` is what the classification omits, so the
# published tree has neither the file nor anything left to classify: they
# declare that and skip there, and the miniatures above still run.
needs_classification = pytest.mark.skipif(
    not roots.instance_here(),
    reason="it reads the classification, which lives under `dev/` and never "
           "travels; the published tree is the classification's own output")


@needs_classification
def test_the_real_repository_classifies_every_tracked_path():
    """The exit criterion for P0, as a gate: no path unclassified, no rule
    stale, no place in the ontology register without a publication decision."""
    assert pa.findings() == []
    assert len(pa.tracked()) > 700, "the tracked list came back empty or short"


@needs_classification
def test_the_real_classification_omits_what_must_not_travel():
    """The three trees PLAN.md forbids publishing are omitted, by name, here:
    a later `--list` reading `public` on one of them would be a decision, and
    this is where that decision is refused."""
    rules = pa.rules(pa.load())
    for rel in ("dev/publication/PLAN.md", "memory/journal/2026/10/x.md",
                "config/practice/user/user-identity.md"):
        rule, why = pa.classify(rel, rules)
        assert rule is not None, (rel, why)
        assert rule.cls == "omit", f"{rel} is classified {rule.cls}"


# ── the classification's own shape ───────────────────────────────────────────

def test_an_unclassified_path_is_an_error(repo):
    cfg = _cfg(_dir("engine/"))
    findings = pa.findings(repo, cfg)
    assert any("memory/journal/2026/a.md: unclassified" in f for f in findings), \
        findings


def test_a_rule_that_matches_nothing_is_an_error(repo):
    """The deletion nobody re-reads: the file a rule was written for is gone,
    and the rule now describes an export that does not exist."""
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"),
               _dir("engine/deleted-tree/"))
    findings = pa.findings(repo, cfg)
    assert any("matches no tracked path" in f
               and "engine/deleted-tree/" in f for f in findings), findings


def test_an_unknown_class_is_an_error(repo):
    cfg = _cfg(_dir("engine/", cls="maybe"), _dir("memory/journal/"))
    assert any("not one of public / example / omit" in f
               for f in pa.findings(repo, cfg))


def test_a_rule_without_a_reason_is_an_error(repo):
    cfg = _cfg(dict(path="engine/", cls="public", why=""), _dir("memory/journal/"))
    assert any("no `why:`" in f for f in pa.findings(repo, cfg))


def test_example_must_change_something_and_public_must_not(repo):
    """`example` means the bytes change on the way out; a `public` rule that
    substitutes is a contradiction, and either way the class is doing work."""
    cfg = _cfg(_dir("engine/", cls="example"), _dir("memory/journal/"))
    assert any("`example` and nothing changes" in f
               for f in pa.findings(repo, cfg))
    cfg = _cfg(_dir("engine/", substitute=[{"from": "a", "to": "b"}]),
               _dir("memory/journal/"))
    assert any("class 'public' with a surgery" in f
               for f in pa.findings(repo, cfg))


def test_a_tie_at_the_same_specificity_is_an_error_not_a_coin_toss(repo):
    cfg = _cfg(_dir("engine/"), _dir("engine/"), _dir("memory/journal/"))
    findings = pa.findings(repo, cfg)
    assert any("two rules claim it at the same specificity" in f
               for f in findings), findings


def test_an_override_beats_a_directory_default(repo):
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"),
               _one("engine/lib/y.py", "omit"))
    rules = pa.rules(cfg)
    assert pa.classify("engine/lib/y.py", rules)[0].cls == "omit"
    assert pa.classify("engine/lib/x.py", rules)[0].cls == "public"


def test_the_longest_directory_rule_wins(repo):
    cfg = _cfg(_dir("engine/"), _dir("engine/lib/", cls="omit"),
               _dir("memory/journal/"))
    rules = pa.rules(cfg)
    assert pa.classify("engine/lib/x.py", rules)[0].path == "engine/lib/"


def test_an_as_target_that_lands_in_an_omitted_tree_is_an_error(repo):
    """The export would write a file into a place it also prunes."""
    cfg = _cfg(_dir("engine/", cls="example",
                    substitute=[{"from": "x", "to": "y"}],
                    **{"as": "memory/journal/copy.py"}),
               _dir("memory/journal/", cls="omit"))
    assert any("lands under memory/journal/" in f
               for f in pa.findings(repo, cfg)), pa.findings(repo, cfg)


def test_an_as_target_written_twice_is_an_error(repo):
    """Two files cannot become one: the second write would silently win."""
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"))
    cfg["overrides"] = [
        dict(path="engine/lib/x.py", why="a reason",
             **{"class": "example", "as": "engine/one.py",
                "substitute": [{"from": "x", "to": "y"}]}),
        dict(path="engine/lib/y.py", why="a reason",
             **{"class": "example", "as": "engine/one.py",
                "substitute": [{"from": "a", "to": "b"}]}),
    ]
    assert any("is already written by" in f for f in pa.findings(repo, cfg))


# ── the seam to the ontology register ────────────────────────────────────────

def test_a_place_with_no_directory_rule_is_an_error(repo):
    """`subjects.yaml` forces a filing decision for a new folder; the export
    owes the same, and this is what makes the two decisions meet."""
    (repo / "docs").mkdir()
    (repo / "docs/README.md").write_text("read me\n")
    (repo / "config/knowledge/subjects.yaml").write_text(
        "subjects:\n  - id: lib\n    places:\n      - engine/lib\n"
        "      - docs\n"
        "unmapped:\n  - id: memory/journal\n    reason: the record\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    findings = pa.findings(repo, _cfg(_dir("engine/"), _dir("memory/journal/")))
    assert any("docs: a place in" in f for f in findings), findings


def test_place_coverage_accepts_an_override_for_a_root_file(repo):
    """`dotfiles` is a tracked symlink at the root: a `places:` entry with no
    directory of its own, covered by the override that classifies it."""
    (repo / "config/knowledge/subjects.yaml").write_text(
        "subjects:\n  - id: lib\n    places:\n      - engine/lib\n"
        "unmapped:\n  - id: memory/journal\n    reason: the record\n"
        "  - id: dotfiles\n    reason: a link to another repository\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"),
               _one("dotfiles", "omit"))
    assert not any("dotfiles: a place in" in f for f in pa.findings(repo, cfg))


def test_version_is_checked(repo):
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"), version="2")
    assert any("is not 1" in f for f in pa.findings(repo, cfg))


# ── the regenerate steps ─────────────────────────────────────────────────────

def test_a_regenerate_step_needs_a_run_and_a_reason(repo):
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"))
    cfg["regenerate"] = [{"produces": ["memory/knowledge/INDEX.md"]}]
    assert any("needs a `run:`" in f for f in pa.findings(repo, cfg))
    cfg["regenerate"] = [{"run": ["engine/familiar"], "why": ""}]
    assert any("no `why:`" in f for f in pa.findings(repo, cfg))


def test_two_steps_producing_the_same_file_is_an_error(repo):
    cfg = _cfg(_dir("engine/"), _dir("memory/journal/"))
    cfg["regenerate"] = [
        {"run": ["a"], "why": "one", "produces": ["memory/knowledge/INDEX.md"]},
        {"run": ["b"], "why": "two", "produces": ["memory/knowledge/INDEX.md"]},
    ]
    assert any("already produced by an earlier step" in f
               for f in pa.findings(repo, cfg))
