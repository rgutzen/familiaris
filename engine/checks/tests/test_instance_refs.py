"""instance_refs: the R1k gate reads the register, fails only on new work --
and takes the words it searches for from the profile rather than spelling them.

The last part is P2's: the gate's pattern used to be eight words written in
`instance_refs.py`, four of which were the user's own name in the file whose job
is to find it. So the tests below are about the COMPOSITION and not about the
instance's actual words -- a test asserting that a particular name is searched
for would fail in the tree that ships the example profile, which is a tree this
gate is supposed to be green in.
"""
import dataclasses
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # engine/checks
sys.path.insert(0, str(HERE.parents[2]))          # engine

import instance_refs as ir  # noqa: E402
from lib import profile, roots  # noqa: E402


def test_the_register_declares_the_gate():
    """Warn mode is a DECLARATION, not an exemption: the entry must exist."""
    assert ir.declared(), ("no violation with surfaced_by: instance-refs in "
                           "config/knowledge/violations.yaml")


def test_every_declared_file_still_carries_one():
    """A declared file that got cleaned is a stale reason -- the register's
    own rule, applied to a measurement. Where the register is about THIS tree:
    in the generated tree it is the exporting instance's measurement, and a
    reader there can neither satisfy nor fix it (`instance_here`)."""
    if not ir.instance_here():
        pytest.skip("the generated tree: entry 12 declares the instance that "
                    "exported it, not this checkout")
    _, stale, _ = ir.findings()
    assert stale == []


def test_nothing_new_in_the_engine():
    undeclared, _, _ = ir.findings()
    assert undeclared == [], undeclared


# ── what the gate searches for, and where it comes from ──────────────────────


def test_the_identity_words_come_from_the_profile():
    """The gate's identity part is a configuration value: a different profile
    is a different search, through the same code."""
    other = dataclasses.replace(roots.PROFILE,
                                identity={"name": "Zaphod Beeblebrox",
                                          "handle": "zaphod42"})
    pattern = ir.pattern(other)
    for word in ("Zaphod", "Beeblebrox", "zaphod42"):
        assert pattern.search(f"see {word} here"), word


def test_the_module_does_not_spell_the_words_it_searches_for():
    """The leak P1 recorded and P2 closes: `instance_refs.py` searched for the
    user's name and contained it. It may not any more, whatever the profile
    says -- and in the tree that ships the example, the assertion is empty
    rather than wrong."""
    text = (roots.ENGINE / "checks" / "instance_refs.py").read_text()
    for word in ir.identity():
        assert word not in text, word


def test_the_home_path_and_the_residue_are_always_searched():
    """The two parts that are not identity: the account the engine runs as, and
    the device/provider/host words P5 retires."""
    pattern = ir.pattern()
    assert pattern.search(str(pathlib.Path.home()))
    for word in ir.RESIDUE.split("|"):
        assert pattern.search(word), word


def test_a_profile_holding_the_examples_own_words_names_nobody(tmp_path):
    """A copy of the example that was never edited is the case this must
    catch: searching for `Name` would match every `class Name` in the tree and
    measure the tree's length, which is loud and means nothing."""
    text = ("version: 1\n"
            "identity:\n  name: Your Name\n  handle: your-handle\n")
    (tmp_path / profile.NAME).write_text(text)
    (tmp_path / profile.EXAMPLE).write_text(text)
    assert ir.identity(profile.resolve(tmp_path)) == []
    assert not ir.pattern(profile.resolve(tmp_path)).search("class Name:")


def test_an_edited_name_in_an_unedited_copy_is_searched(tmp_path):
    """The other half of the same rule: the placeholder is dropped per value,
    not per file, so editing one field starts searching for that field."""
    (tmp_path / profile.EXAMPLE).write_text(
        "version: 1\nidentity:\n  name: Your Name\n  handle: your-handle\n")
    (tmp_path / profile.NAME).write_text(
        "version: 1\nidentity:\n  name: Zaphod\n  handle: your-handle\n")
    assert ir.identity(profile.resolve(tmp_path)) == ["Zaphod"]


def test_a_word_too_short_to_search_is_not_one(tmp_path):
    """MIN_WORD, named rather than discovered: an unanchored one-character
    alternative matches the inside of every identifier, so a name that short is
    a gap the gate takes deliberately."""
    (tmp_path / profile.NAME).write_text(
        "version: 1\nidentity:\n  name: Li\n  handle: li\n")
    assert ir.identity(profile.resolve(tmp_path)) == []


def test_it_counts_occurrences_per_file(tmp_path, monkeypatch):
    """What the declaration is about: which files, and how often. The payload
    is the account this engine runs as and the residue, so the test holds in
    whichever tree it runs in."""
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "a.py").write_text(
        f"p = '{pathlib.Path.home()}/x'\nq = 'bigfish bigfish'\n")
    (tmp_path / "x" / "b.py").write_text("nothing here\n")
    monkeypatch.setattr(ir, "SKIP", ())
    monkeypatch.setattr(ir.roots, "REPO", tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert ir.measure(".") == {"x/a.py": 3}
