"""The leak scanner, proved by breaking it -- on a tree that is not this one.

The scanner reads the GENERATED tree, so its tests do the same: a throw-away
directory with one planted leak per test. Two things are being proved, and the
second is the one a scanner usually gets wrong:

  * a leak the instance's private patterns describe is FOUND;
  * a declaration is a MEASUREMENT, not a licence -- one occurrence more than
    it says is a new leak, and one occurrence fewer is a declaration that
    outlived its subject.
"""
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import publish_scan as ps

# The BUILT-IN shapes, compiled here rather than through `patterns()`.
# `patterns()` merges this instance's private names and REFUSES to return a set
# when it cannot read the file they live in, which is the right behaviour for
# the scanner and the wrong dependency for these tests: their subject is the
# scanner's logic on a tree that is not this one, and a suite that needs the
# private register would stop running in the published tree -- the export --
# where it is needed most. That `patterns()` still fails closed, and still adds
# the private names when it can, is asserted on its own below.
PATS = [(name, re.compile(rx), keep) for name, rx, keep in ps.BUILTIN]


def scan(tree, pats=None):
    """`ps.scan` with the built-ins, so no test reads the private file by
    accident -- an explicit `pats` still wins."""
    return ps.scan(tree, PATS if pats is None else pats)


def _tree(tmp_path, files: dict, **more) -> pathlib.Path:
    """Write `{relative path: text}` under tmp_path and hand the root back."""
    for name, text in dict(files, **more).items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def _names(hits) -> set:
    return {h.name for h in hits}


# ── the built-in shapes ──────────────────────────────────────────────────────

def test_the_built_in_shapes_are_found(tmp_path):
    tree = _tree(tmp_path, {
        "home/x.md": "lives in /home/zaphod/06_SYSTEM\n",
        "mail/x.md": "write to someone@elsewhere.net\n",
        "ip/x.md": "the box answers on 192.168.1.44\n",
        "key/x.md": "-----BEGIN OPENSSH PRIVATE KEY-----\n",
        "tok/x.md": "token ghp_0123456789abcdefghijklmnopqrstuv\n",
        "restic/x.sh": 'RESTIC_PASSWORD="hunter2"\n',
    })
    assert _names(scan(tree)) == {"home-path", "email", "ipv4", "private-key",
                                     "token", "restic-passphrase"}


@pytest.mark.parametrize("text", [
    "/home/someone/06_SYSTEM/x",       # a fixture's placeholder account
    "/home/user/docs",                 # the generic one
    "test@example.invalid",            # RFC 2606 reserved
    "t@e.test",
    "127.0.0.1:8080",                  # loopback, not a host
    "0.0.0.0:11434",
    "git@github.com:owner/repo.git",   # a VCS remote, not a mailbox
    "opencode-plugin@1.18.18",         # a version, not an address
])
def test_the_shapes_that_are_not_hits(tmp_path, text):
    assert scan(_tree(tmp_path, {"a/x.md": text + "\n"})) == []


def test_a_binary_file_is_not_scanned(tmp_path):
    p = tmp_path / "chart.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n\x00/home/zaphod\x00rest")
    assert scan(tmp_path) == []


def test_the_private_pattern_file_adds_the_instance_s_own_names(tmp_path):
    pats = tmp_path / "patterns.txt"
    pats.write_text("# the disk\n"
                    "device-name\tZorblax|zorblax\n"
                    "person-name\tZaphod Beeblebrox\n")
    tree = _tree(tmp_path / "tree", {"a/x.md": "copied to Zorblax\n"})
    names = _names(scan(tree, ps.patterns(pats)))
    assert names == {"device-name"}


def test_a_missing_pattern_file_is_a_failure_not_an_empty_set(tmp_path):
    """The names and the devices are the patterns with real disclosure value;
    a scanner that silently dropped them would report a clean tree it never
    looked at."""
    with pytest.raises(SystemExit):
        ps.patterns(tmp_path / "not-there.txt")


# ── declarations ─────────────────────────────────────────────────────────────

def test_a_declared_hit_with_its_count_is_clean(tmp_path):
    tree = _tree(tmp_path, {"a/x.md": "one /home/zaphod here\n"})   # the real name
    hits = scan(tree)
    decls = [ps.Declaration("a/x.md", "home-path", 1, "a fixture")]
    problems, notes = ps.findings(tree, hits, decls)
    assert problems == []
    assert notes and "declared" in notes[0]


def test_an_undeclared_hit_is_a_leak(tmp_path):
    tree = _tree(tmp_path, {"a/x.md": "one /home/zaphod here\n"})
    problems, _ = ps.findings(tree, scan(tree), [])
    assert len(problems) == 1
    assert "no declaration covers this" in problems[0]


def test_one_occurrence_more_than_declared_is_a_leak(tmp_path):
    """A declaration is not a licence for the next occurrence."""
    tree = _tree(tmp_path, {"a/x.md": "one /home/zaphod here\nand /home/zaphod again\n"})
    decls = [ps.Declaration("a/x.md", "home-path", 1, "a fixture")]
    problems, _ = ps.findings(tree, scan(tree), decls)
    assert len(problems) == 1
    assert "MORE than the declaration covers" in problems[0]


def test_a_declaration_that_no_longer_hits_is_stale(tmp_path):
    """Templated away, renamed or deleted -- either way the declaration now
    describes a tree that does not exist."""
    tree = _tree(tmp_path, {"a/x.md": "clean now\n"})
    decls = [ps.Declaration("a/x.md", "home-path", 1, "was there")]
    problems, _ = ps.findings(tree, scan(tree), decls)
    assert len(problems) == 1
    assert "outlived its subject" in problems[0]


def test_a_declaration_that_under_counts_is_a_note_not_a_leak(tmp_path):
    """Fewer than declared is left for the reader of the register rather than
    failing the publish: the tree is safe, and the count is bookkeeping."""
    tree = _tree(tmp_path, {"a/x.md": "one /home/zaphod here\n"})
    decls = [ps.Declaration("a/x.md", "home-path", 3, "a fixture")]
    problems, notes = ps.findings(tree, scan(tree), decls)
    assert problems == []
    assert any("lower than declared" in n for n in notes)


def test_a_malformed_declaration_is_refused(tmp_path, monkeypatch):
    bad = tmp_path / "leak-exceptions.txt"
    bad.write_text("a/x.md\thome-path\t1\n")      # no reason
    monkeypatch.setattr(ps, "EXCEPTION_FILE", bad)
    with pytest.raises(SystemExit):
        ps.declarations()


# ── the CLI ──────────────────────────────────────────────────────────────────

def test_it_refuses_to_scan_this_repository(capsys):
    """The scanner reads what publish.py wrote. This tree holds the journal,
    the mail filters and the user's own paths on purpose."""
    from lib import roots
    assert ps.main(["--tree", str(roots.REPO)]) == 2
    assert "not a generated tree" in capsys.readouterr().err


def test_a_clean_generated_tree_exits_zero(tmp_path, capsys, monkeypatch):
    tree = _tree(tmp_path, {"a/x.md": "nothing here\n"})
    # The CLI reads the two register files from the module constants, and this
    # instance's private pattern file is not what the test is about: an empty
    # one leaves the built-ins, which is the whole of the scanner's own logic.
    empty = tmp_path / "patterns.txt"
    empty.write_text("# no private names in this tree\n")
    monkeypatch.setattr(ps, "PATTERN_FILE", empty)
    monkeypatch.setattr(ps, "EXCEPTION_FILE", tmp_path / "none.txt")
    assert ps.main(["--tree", str(tree)]) == 0
    assert "0 undeclared or stale" in capsys.readouterr().out
