"""isolation (4b): `isolate` gives a repository whose only history is the base.

A tmp source repository has a base commit and a later one; the isolated tree
must not reach the later commit by any git command, must equal `git archive
base`, must give one sha on every run, and must not carry a symlink that
leaves it. One real 4a task is isolated from this repository."""
import os
import pathlib
import subprocess

import pytest

from lib import roots
from orchestration import eval as E

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="the real task is under `dev/orchestration/tasks/`, which the "
           "classification omits with `dev/`")


def git(repo, *args, check=True):
    return subprocess.run(("git", "-C", str(repo)) + args, capture_output=True,
                          text=True, check=check)


def task(base, **kw):
    d = pathlib.Path(kw.pop("dir", "/nonexistent/task"))
    return E.Task(id="t", kind="coding", title="t", base=base, reference=("0" * 40,),
                  scope=(), verify="true", arms=(), dir=d, **kw)


@pytest.fixture
def src(tmp_path):
    """base: a.txt, sub/b.txt, an ignored-but-tracked file, escaping and inner
    links; then a later commit that adds future.txt."""
    r = tmp_path / "src"
    r.mkdir()
    git(r, "init", "-q")
    (r / "a.txt").write_text("a\n")
    (r / "sub").mkdir()
    (r / "sub/b.txt").write_text("b\n")
    (r / ".gitignore").write_text("*.log\n")
    (r / "kept.log").write_text("tracked despite the pattern\n")
    (r / "run.sh").write_text("#!/bin/sh\n")
    (r / "run.sh").chmod(0o755)
    os.symlink("/etc/hostname", r / "abs")
    os.symlink("../../outside", r / "sub/up")
    os.symlink("sub/b.txt", r / "inner")
    os.symlink("nowhere", r / "dangling")
    git(r, "add", "-f", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    base = git(r, "rev-parse", "HEAD").stdout.strip()
    (r / "future.txt").write_text("future\n")
    git(r, "add", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "later")
    return r, base, git(r, "rev-parse", "HEAD").stdout.strip()


def test_isolation_future_unreachable(src, tmp_path):
    r, base, later = src
    dest = tmp_path / "d"
    E.isolate(task(base), dest, r)
    assert git(dest, "cat-file", "-e", later, check=False).returncode != 0
    assert git(dest, "cat-file", "-e", base, check=False).returncode != 0
    assert later not in git(dest, "rev-list", "--all").stdout
    assert later not in git(dest, "log", "--all", "--format=%H").stdout
    assert not (dest / "future.txt").exists()
    assert not (dest / ".git/objects/info/alternates").exists()
    assert not (dest / ".git/logs").exists()
    assert git(dest, "reflog").stdout.strip() == ""


def test_isolation_one_commit_no_remote_no_hooks(src, tmp_path):
    r, base, _ = src
    dest = tmp_path / "d"
    sha, _ = E.isolate(task(base), dest, r)
    assert git(dest, "rev-list", "--all", "--count").stdout.strip() == "1"
    assert git(dest, "remote").stdout.strip() == ""
    assert git(dest, "for-each-ref").stdout.split()[0] == sha
    assert git(dest, "status", "--porcelain").stdout == ""
    assert not list((dest / ".git/hooks").glob("*"))
    assert git(dest, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%aI").stdout.strip() == \
        "eval <eval@localhost>|eval <eval@localhost>|2000-01-01T00:00:00Z"


def test_isolation_tree_equals_archive(src, tmp_path):
    r, base, _ = src
    dest = tmp_path / "d"
    _, gone = E.isolate(task(base), dest, r)
    want = tmp_path / "want"
    want.mkdir()
    arc = subprocess.run(("git", "-C", str(r), "archive", base), capture_output=True, check=True)
    subprocess.run(("tar", "-x", "-C", str(want)), input=arc.stdout, check=True)
    for p in (want / n for n in gone):
        p.unlink()                      # the one deliberate difference
    listing = lambda root: sorted(  # noqa: E731
        (str(p.relative_to(root)), os.readlink(p) if p.is_symlink() else p.read_bytes(),
         p.stat().st_mode & 0o111 if not p.is_symlink() else 0)
        for p in root.rglob("*") if ".git" not in p.relative_to(root).parts and not p.is_dir())
    assert listing(dest) == listing(want)
    assert (dest / "kept.log").exists()             # tracked file matching .gitignore is base
    assert git(dest, "ls-files").stdout.split() == sorted(
        n for n in git(r, "ls-tree", "-r", "--name-only", base).stdout.split() if n not in gone)


def test_isolation_sha_reproducible(src, tmp_path):
    r, base, _ = src
    shas = {E.isolate(task(base), tmp_path / f"d{i}", r)[0] for i in range(2)}
    assert len(shas) == 1
    assert E.isolate(task(base, tree="empty"), tmp_path / "e1", r)[0] == \
        E.isolate(task(base, tree="empty"), tmp_path / "e2", r)[0]


def test_isolation_escaping_symlinks_deleted_inner_kept(src, tmp_path):
    r, base, _ = src
    dest = tmp_path / "d"
    _, gone = E.isolate(task(base), dest, r)
    assert gone == ["abs", "sub/up"]
    assert not os.path.lexists(dest / "abs") and not os.path.lexists(dest / "sub/up")
    assert os.readlink(dest / "inner") == "sub/b.txt"
    assert os.path.islink(dest / "dangling")        # stays inside: reaches nothing of the host
    assert "abs" not in git(dest, "ls-files").stdout.split()


def test_isolation_symlink_through_escaping_dir_link(tmp_path):
    r = tmp_path / "s"
    r.mkdir()
    git(r, "init", "-q")
    os.symlink("/usr", r / "d")
    os.symlink("d/bin", r / "viad")
    git(r, "add", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
    _, gone = E.isolate(task(git(r, "rev-parse", "HEAD").stdout.strip()), tmp_path / "d", r)
    assert gone == ["d"]                # `viad` now dangles inside the tree: it reaches nothing
    assert os.path.realpath(tmp_path / "d" / "viad").startswith(str((tmp_path / "d").resolve()))


def test_isolation_empty_tree(src, tmp_path):
    r, base, _ = src
    dest = tmp_path / "d"
    E.isolate(task(base, tree="empty"), dest, r)
    assert git(dest, "ls-files").stdout == ""
    assert sorted(p.name for p in dest.iterdir()) == [".git"]
    assert git(dest, "rev-list", "--all", "--count").stdout.strip() == "1"


def test_isolation_refuses_bad_dest_and_leak(src, tmp_path):
    r, base, _ = src
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x")
    with pytest.raises(E.TaskError, match="not an empty"):
        E.isolate(task(base), full, r)
    with pytest.raises(E.TaskError, match="inside the source"):
        E.isolate(task(base), r / "work", r)
    with pytest.raises(E.TaskError, match="key ships"):
        E.isolate(task(base, dir=r / "sub"), tmp_path / "d", r)
    E.isolate(task(base, dir=r / "sub", tree="empty"), tmp_path / "d2", r)   # empty tree holds no key


@INSTANCE
def test_isolation_real_task_verify_fails(tmp_path):
    if not E.has_commit(next(t for t in E.load() if t.id == "orch-2b-dispatch-check").base):
        pytest.skip("the base commit is not in this checkout")
    t = next(t for t in E.load() if t.id == "orch-2b-dispatch-check")
    dest = tmp_path / "w"
    sha, _ = E.isolate(t, dest)
    assert git(dest, "rev-list", "--all", "--count").stdout.strip() == "1"
    for ref in t.reference:
        assert git(dest, "cat-file", "-e", ref, check=False).returncode != 0
    code, _ = E.verify(t, dest)
    assert code != 0
    E.materialise(t, tmp_path / "w2", True)
    assert E.verify(t, tmp_path / "w2")[0] == 0
    assert E.main(["--isolate", t.id, str(tmp_path / "w3")]) == 0
    assert git(tmp_path / "w3", "rev-parse", "HEAD").stdout.strip() == sha
