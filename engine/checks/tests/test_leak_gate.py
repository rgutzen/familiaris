"""leak_gate: the destination decides, and the delta is what is scanned.

Every test here is offline. The visibility probe is either INJECTED or pinned
with `git config pazras.visibility`, never called: a test that needed GitHub
would stop running the day the network does. The remotes are scratch
repositories on disk, the same way `test_push_guard.py` fakes its remote.

THE FIXTURES USE A SCRATCH PATTERN, NOT A REAL ONE. `Zaphod` is what these
trees leak, and the pattern that finds it comes from the same register machinery
a repository uses -- so the file this suite exports carries no planted
credential and needs no declaration (`test_publish_scan.py` proves the built-in
shapes and their false positives; what is proved HERE is the plumbing: the
destination, the delta, the register, the declarations). The suite also runs in
the export, where this machine's register is omitted by design.
"""
import contextlib
import io
import pathlib
import re
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # engine/checks
sys.path.insert(0, str(HERE.parents[2]))          # engine

import leak_gate as lg  # noqa: E402

# The pattern set every test runs under: one name, nothing about this machine.
SCRATCH = [("scratch-name", re.compile(r"Zaphod"), None)]
LEAK = "Zaphod was here\n"

IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]

PUBLIC_URL = "git@github.com:test-owner/test-repo.git"


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """The scratch patterns and a register that exists, so no test reads this
    machine's register and none of them needs the network."""
    monkeypatch.setattr(lg, "patterns", lambda tree=None: SCRATCH)
    monkeypatch.setattr(lg, "register_path",
                        lambda tree=None: pathlib.Path(__file__))


def git(tree, *args, **kw):
    return subprocess.run(("git", "-C", str(tree)) + tuple(IDENT) + args,
                          capture_output=True, text=True, check=True, **kw).stdout


def repo(tmp_path, files: dict, message="a commit") -> pathlib.Path:
    """A scratch repository with one commit carrying `files`."""
    tree = tmp_path / "checkout"
    tree.mkdir()
    git(tree, "init", "-q", "-b", "main")
    for name, text in files.items():
        p = tree / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    git(tree, "add", "-A")
    git(tree, "commit", "-q", "-m", message)
    return tree


def run(argv, tree, stdin=""):
    """`main()` with stdin replaced; returns the exit code."""
    out = io.StringIO()
    saved, sys.stdin = sys.stdin, io.StringIO(stdin)
    try:
        with contextlib.redirect_stderr(out), contextlib.redirect_stdout(out):
            code = lg.main(argv)
    finally:
        sys.stdin = saved
    return code, out.getvalue()


def push_line(local_sha: str, remote_sha: str) -> str:
    return (f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n")


def head(tree) -> str:
    return git(tree, "rev-parse", "HEAD").strip()


# ── the destination ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("git@github.com:Test-Owner/Some-Repo.git", ("github.com", "test-owner", "some-repo")),
    ("https://github.com/test-owner/some-repo", ("github.com", "test-owner", "some-repo")),
    ("ssh://git@github.com/test-owner/some-repo/", ("github.com", "test-owner", "some-repo")),
    ("/tmp/elsewhere/test-owner/some-repo.git", None),
    ("https://gitlab.com/x/y.git", ("gitlab.com", "x", "y")),
    ("", None),
])
def test_a_remote_is_read_as_a_pair(url, expected):
    assert lg.forge_pair(url) == expected


def test_visibility_pins_beat_the_probe(tmp_path):
    answer, evidence = lg.visibility(PUBLIC_URL, pin=lg.PUBLIC,
                                     probe=lambda *a: pytest.fail("probed"))
    assert (answer, evidence) == (lg.PUBLIC, "pinned")


def test_a_local_path_is_unknown_not_probed(tmp_path):
    answer, evidence = lg.visibility(str(tmp_path), tree=tmp_path,
                                     probe=lambda *a: pytest.fail("probed"))
    assert answer == lg.UNKNOWN and "not a remote" in evidence


def test_a_host_this_gate_cannot_ask_is_unknown(tmp_path):
    answer, evidence = lg.visibility("git@gitlab.com:x/y.git", tree=tmp_path,
                                     probe=lambda *a: pytest.fail("probed"))
    assert answer == lg.UNKNOWN and "gitlab.com" in evidence


def test_the_probe_answers_public_and_private():
    assert lg.visibility(PUBLIC_URL, probe=lambda o, r, t: (lg.PUBLIC, "x"))[0] == lg.PUBLIC
    assert lg.visibility(PUBLIC_URL, probe=lambda o, r, t: (lg.PRIVATE, "x"))[0] == lg.PRIVATE


def test_the_origin_pin_is_read_from_git_config(tmp_path):
    tree = repo(tmp_path, {"a.md": "nothing\n"})
    assert lg.pinned(tree) is None
    git(tree, "config", "pazras.visibility", "public")
    assert lg.pinned(tree) == lg.PUBLIC


# ── the blob walk ────────────────────────────────────────────────────────────

def test_a_new_branch_publishes_its_whole_history(tmp_path):
    """The leak is two commits back and the tip is clean: a first push still
    publishes it, so the range is everything the ref carries."""
    tree = repo(tmp_path, {"leak.md": LEAK})
    (tree / "leak.md").write_text("clean now\n")
    git(tree, "commit", "-qam", "second")
    objects = lg.range_objects(tree, head(tree), lg.ZERO)
    hits, _ = lg.scan_objects(tree, objects)
    assert {h.name for h in hits} == {"scratch-name"}


def test_only_the_delta_is_scanned(tmp_path):
    """A leak that is already on the remote is not this push's problem; the one
    being added is."""
    tree = repo(tmp_path, {"old.md": LEAK})
    first = head(tree)
    (tree / "new.md").write_text(LEAK + "again\n")
    git(tree, "add", "new.md")
    git(tree, "commit", "-qm", "second")
    hits, _ = lg.scan_objects(tree, lg.range_objects(tree, head(tree), first))
    assert {h.path for h in hits} == {"new.md"}


def test_a_blob_already_on_the_remote_is_not_republished(tmp_path):
    """The same bytes at a new path is not a new object, so there is nothing
    new to disclose -- and the gate says so rather than refusing the path."""
    tree = repo(tmp_path, {"old.md": LEAK})
    first = head(tree)
    (tree / "same.md").write_text(LEAK)
    git(tree, "add", "same.md")
    git(tree, "commit", "-qm", "second")
    assert lg.range_objects(tree, head(tree), first) == []


def test_every_path_that_carries_the_content_is_reported(tmp_path):
    """Two identical files are one object and two paths. A declaration covers a
    path, so the walk may not collapse them into one."""
    tree = repo(tmp_path, {"a.md": LEAK, "b.md": LEAK})
    hits, _ = lg.scan_objects(tree, lg.range_objects(tree, head(tree), lg.ZERO))
    assert {h.path for h in hits} == {"a.md", "b.md"}


def test_a_deleted_file_has_nothing_to_scan(tmp_path):
    tree = repo(tmp_path, {"a.md": "clean\n"})
    assert lg.pushed_refs(f"refs/heads/main {lg.ZERO} refs/heads/main {head(tree)}\n") == []


def test_the_index_is_what_a_commit_would_write(tmp_path):
    tree = repo(tmp_path, {"a.md": "clean\n"})
    (tree / "b.md").write_text(LEAK)
    git(tree, "add", "b.md")
    hits, _ = lg.scan_objects(tree, lg.staged_objects(tree))
    assert {h.path for h in hits} == {"b.md"}


# ── the gate ─────────────────────────────────────────────────────────────────

def test_a_public_destination_warns_and_the_push_proceeds(tmp_path):
    """The default stance: everything is printed, nothing is stopped. A gate
    that stops an unhurried push is a gate its reader learns to bypass."""
    tree = repo(tmp_path, {"notes.md": LEAK})
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public"], tree,
                    push_line(head(tree), lg.ZERO))
    assert code == 0
    assert "WARN" in out and "scratch-name" in out
    assert "NOT stopped" in out and "pazras.leak-gate strict" in out


def test_a_public_destination_refuses_in_a_strict_checkout(tmp_path):
    tree = repo(tmp_path, {"notes.md": LEAK})
    git(tree, "config", "pazras.leak-gate", "strict")
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public"], tree,
                    push_line(head(tree), lg.ZERO))
    assert code == 1
    assert "REFUSED" in out and "scratch-name" in out
    # The way through is named, and it is one command.
    assert "pazras.leak-gate=warn" in out


def test_strict_and_advisory_override_the_checkout_for_one_run(tmp_path):
    tree = repo(tmp_path, {"notes.md": LEAK})
    line = push_line(head(tree), lg.ZERO)
    git(tree, "config", "pazras.leak-gate", "strict")
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public", "--advisory"], tree, line)
    assert code == 0 and "WARN" in out
    git(tree, "config", "--unset", "pazras.leak-gate")
    code, _ = run(["--tree", str(tree), "--url", PUBLIC_URL,
                   "--visibility", "public", "--strict"], tree, line)
    assert code == 1


def test_a_private_destination_is_silent(tmp_path):
    """Not scanned at all: this IS the private tree's content, on purpose."""
    tree = repo(tmp_path, {"journals/x.md": LEAK})
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "private"], tree,
                    push_line(head(tree), lg.ZERO))
    assert code == 0 and out == ""


def test_an_unknown_destination_is_not_reported(tmp_path):
    """A destination that could not be resolved is not a public one, so the
    gate is not active -- and it does not nag about a question it could not
    ask. `--verbose` is how a reader sees what was skipped."""
    tree = repo(tmp_path, {"journals/x.md": LEAK})
    line = push_line(head(tree), lg.ZERO)
    code, out = run(["--tree", str(tree), "--url", str(tmp_path / "bare.git")],
                    tree, line)
    assert code == 0 and out == ""
    code, out = run(["--tree", str(tree), "--url", str(tmp_path / "bare.git"),
                     "--verbose"], tree, line)
    assert code == 0 and "unknown" in out and "advisory" in out


def test_quiet_silences_a_private_destination_but_not_a_warning(tmp_path):
    """The hook runs `--quiet`: a push that is fine says nothing, and a warning
    is what it exists to print."""
    tree = repo(tmp_path, {"journals/x.md": LEAK})
    line = push_line(head(tree), lg.ZERO)
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "private", "--quiet"], tree, line)
    assert code == 0 and out == ""
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public", "--quiet"], tree, line)
    assert code == 0 and "WARN" in out


def test_a_declaration_clears_a_hit(tmp_path):
    tree = repo(tmp_path, {"notes.md": LEAK})
    allow = tree / ".pazras" / "leak-allow.txt"
    allow.parent.mkdir()
    allow.write_text("notes.md\tscratch-name\t1\tpublished on purpose\n")
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public", "--strict"], tree,
                    push_line(head(tree), lg.ZERO))
    assert code == 0, out


def test_a_declaration_does_not_cover_another_path(tmp_path):
    tree = repo(tmp_path, {"notes.md": LEAK, "other.md": LEAK + "too\n"})
    allow = tree / ".pazras" / "leak-allow.txt"
    allow.parent.mkdir()
    allow.write_text("notes.md\tscratch-name\t1\tpublished on purpose\n")
    line = push_line(head(tree), lg.ZERO)
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public", "--strict"], tree, line)
    assert code == 1 and "other.md" in out
    # Both hits are listed -- the reader wants the whole picture -- and exactly
    # one of them is undeclared.
    assert "notes.md" in out and "1 occurrence(s)" in out


def test_the_delta_rule_does_not_read_counts(tmp_path):
    """A declaration's count measures a TREE; the push is a delta. The count in
    the register must not be read as a licence -- nor as a shortfall -- by a
    scan that cannot see the tree it was measured on. Strict, so a pass means
    the declaration cleared it rather than the mode did."""
    tree = repo(tmp_path, {"notes.md": LEAK})
    allow = tree / ".pazras" / "leak-allow.txt"
    allow.parent.mkdir()
    allow.write_text("notes.md\tscratch-name\t1\tpublished on purpose\n")
    code, _ = run(["--tree", str(tree), "--url", PUBLIC_URL,
                   "--visibility", "public", "--strict"], tree,
                  push_line(head(tree), lg.ZERO))
    assert code == 0


def test_a_built_in_shape_arrives_at_the_gate_too(tmp_path, monkeypatch):
    """The gate scans with `publish_scan`'s pattern set, so a shape that is
    wrong in any tree (a key, a token, an address) arrives here too. One case,
    because `test_publish_scan.py` owns the shapes themselves."""
    import publish_scan as ps
    monkeypatch.setattr(lg, "patterns",
                        lambda tree=None: [(n, re.compile(rx), keep)
                                           for n, rx, keep in ps.BUILTIN])
    tree = repo(tmp_path, {"id_rsa": "-----BEGIN OPENSSH PRIVATE KEY-----\n"})
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public", "--strict"], tree,
                    push_line(head(tree), lg.ZERO))
    assert code == 1 and "private-key" in out


def test_staged_mode_asks_about_the_origin(tmp_path):
    tree = repo(tmp_path, {"a.md": "clean\n"})
    (tree / "b.md").write_text(LEAK)
    git(tree, "add", "b.md")
    code, out = run(["--tree", str(tree), "--staged", "--visibility", "public"],
                    tree)
    assert code == 0 and "WARN" in out
    code, out = run(["--tree", str(tree), "--staged", "--visibility", "public",
                     "--strict"], tree)
    assert code == 1 and "scratch-name" in out
    code, out = run(["--tree", str(tree), "--staged", "--visibility", "private"],
                    tree)
    assert code == 0 and out == ""


def test_a_tree_with_its_own_register_reads_that_one(tmp_path, monkeypatch):
    """A repository that is not this instance carries the names that must not
    travel from there, and its register is the one that applies."""
    monkeypatch.undo()
    tree = repo(tmp_path, {"who.md": LEAK})
    (tree / ".pazras").mkdir()
    (tree / ".pazras" / "leak-patterns.txt").write_text("scratch-name\tZaphod\n")
    code, out = run(["--tree", str(tree), "--url", PUBLIC_URL,
                     "--visibility", "public", "--strict"], tree,
                    push_line(head(tree), lg.ZERO))
    assert code == 1 and "scratch-name" in out


def test_a_push_through_git_is_refused_by_an_armed_strict_hook(tmp_path):
    """End to end: git asks the hook, the hook reads the refs on stdin, the gate
    scans the blobs and a STRICT checkout stops the push. The remote is a bare
    directory, the visibility is pinned, and the pattern is the tree's own -- so
    nothing here touches a forge, and the case also runs in the export, where
    this machine's register is omitted by design."""
    tree = repo(tmp_path, {"notes.md": LEAK})
    (tree / ".pazras").mkdir()
    (tree / ".pazras" / "leak-patterns.txt").write_text("scratch-name\tZaphod\n")
    bare = tmp_path / "remotes" / "public.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(tree, "config", "pazras.visibility", "public")
    git(tree, "config", "pazras.leak-gate", "strict")
    lg.arm(tree)
    done = subprocess.run(["git", "-C", str(tree), "push", str(bare), "HEAD"],
                          capture_output=True, text=True)
    assert done.returncode != 0, done.stdout + done.stderr
    assert "REFUSED" in done.stderr and "scratch-name" in done.stderr
    assert subprocess.run(["git", "-C", str(bare), "rev-parse", "--verify", "HEAD"],
                          capture_output=True).returncode != 0


def test_a_push_through_git_proceeds_with_a_warning_by_default(tmp_path):
    """The advisory stance, end to end: the warning is printed and the push
    lands. This is the default, so this is the case a reader meets first."""
    tree = repo(tmp_path, {"notes.md": LEAK})
    (tree / ".pazras").mkdir()
    (tree / ".pazras" / "leak-patterns.txt").write_text("scratch-name\tZaphod\n")
    bare = tmp_path / "remotes" / "public.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(tree, "config", "pazras.visibility", "public")
    lg.arm(tree)
    done = subprocess.run(["git", "-C", str(tree), "push", str(bare), "HEAD"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "WARN" in done.stderr and "NOT stopped" in done.stderr
    assert subprocess.run(["git", "-C", str(bare), "rev-parse", "--verify", "HEAD"],
                          capture_output=True).returncode == 0


# ── arming ───────────────────────────────────────────────────────────────────

def test_arm_writes_an_executable_hook_that_names_this_engine(tmp_path):
    tree = repo(tmp_path, {"a.md": "clean\n"})
    path = lg.arm(tree)
    assert path.exists() and path.stat().st_mode & 0o111
    body = path.read_text()
    assert "leak_gate.py" in body and "rev-parse --show-toplevel" in body
    assert lg.armed(path)


def test_arm_refuses_when_the_register_is_unreadable(tmp_path, monkeypatch):
    tree = repo(tmp_path, {"a.md": "clean\n"})
    monkeypatch.setattr(lg, "register_path",
                        lambda tree=None: tmp_path / "absent.txt")
    with pytest.raises(SystemExit):
        lg.arm(tree)


def test_check_fails_where_the_origin_is_public(tmp_path):
    tree = repo(tmp_path, {"a.md": "clean\n"})
    git(tree, "remote", "add", "origin", PUBLIC_URL)
    git(tree, "config", "pazras.visibility", "public")      # no probe, no network
    ok, message = lg.check(tree)
    assert not ok and "NOT armed" in message


def test_check_passes_where_the_origin_is_private(tmp_path):
    """The private instance: not armed is the correct state, and saying so is
    the check's job. Arming it there would scan a destination that has nothing
    to refuse."""
    tree = repo(tmp_path, {"a.md": "clean\n"})
    git(tree, "remote", "add", "origin", PUBLIC_URL)
    git(tree, "config", "pazras.visibility", "private")
    ok, message = lg.check(tree)
    assert ok and "correctly so" in message
    lg.arm(tree)
    ok, message = lg.check(tree)
    assert ok and "armed at" in message and "(warn)" in message


def test_check_passes_in_a_tree_with_no_remote_at_all(tmp_path):
    """The export clone before its remote is set, and a scratch checkout: there
    is no destination, so there is nothing to refuse."""
    tree = repo(tmp_path, {"a.md": "clean\n"})
    ok, message = lg.check(tree)
    assert ok and "correctly so" in message
