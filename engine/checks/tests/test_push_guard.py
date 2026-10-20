"""push_guard: one repository name, two visibilities, and the hook that keeps
the private tree out of the public one.

Every test here runs against a scratch repository and a FAKE remote -- a bare
directory on disk. Nothing in this file touches a forge, and nothing in it
pushes anywhere but a tmp directory.
"""
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))          # engine/checks
sys.path.insert(0, str(HERE.parents[2]))          # engine

import push_guard as pg  # noqa: E402
from lib import profile, roots  # noqa: E402

IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]

# The handle these tests run under. Not the instance's: the point of the guard
# is that the handle is a configuration value, and a test bound to the real one
# would fail in the tree that ships the example profile.
OWNER = "test-owner"


def _profile(tmp_path, handle=OWNER, name="Test Owner"):
    """A profile as the guard reads it: the handle decides the public pair."""
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / profile.NAME).write_text(
        f"version: 1\nidentity:\n  name: {name}\n  handle: {handle}\n")
    return profile.resolve(cfg)


def _private(tmp_path):
    """A checkout that holds the private tree."""
    tree = tmp_path / "instance"
    (tree / "dev").mkdir(parents=True, exist_ok=True)
    return tree


@pytest.mark.parametrize("url", [
    f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}.git",
    f"https://github.com/{OWNER}/{pg.PUBLIC_REPO}.git",
    f"https://github.com/{OWNER}/{pg.PUBLIC_REPO}",
    f"ssh://git@github.com/{OWNER}/{pg.PUBLIC_REPO}/",
    f"/tmp/elsewhere/{OWNER}/{pg.PUBLIC_REPO}.git",
])
def test_every_spelling_of_the_public_remote_is_refused(tmp_path, url):
    """The transport is not parsed for meaning: ssh, https and a local path are
    one destination, and the test's fake remote is the third."""
    reason = pg.refuses(url, _private(tmp_path), _profile(tmp_path))
    assert reason, url
    assert "PUBLIC repository" in reason


@pytest.mark.parametrize("url", [
    f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}-other.git",
    f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}s.git",
    f"git@github.com:someone-else/{pg.PUBLIC_REPO}.git",
    f"git@github.com:{OWNER}/other.git",
    "origin",
    "",
])
def test_the_neighbours_are_allowed(tmp_path, url):
    """The suffix is the whole distinction, so it has to be exact: the private
    repository, another owner's repository and a bare remote name are not it."""
    assert pg.refuses(url, _private(tmp_path), _profile(tmp_path)) is None


def test_a_checkout_without_dev_is_never_refused(tmp_path):
    """The publish clone: pushing the generated tree to the public repository is
    the normal case, and it is the case this must not block."""
    tree = tmp_path / "publish"
    tree.mkdir()
    assert pg.refuses(f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}.git", tree,
                      _profile(tmp_path)) is None


def test_the_handle_is_the_profile_s_value(tmp_path):
    """A different profile is a different public pair, through the same code --
    which is what makes this a configuration value rather than a literal."""
    p = _profile(tmp_path, handle="zaphod42")
    assert pg.public_owner(p) == "zaphod42"
    assert pg.refuses(f"git@github.com:zaphod42/{pg.PUBLIC_REPO}.git",
                      _private(tmp_path), p)
    assert pg.refuses(f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}.git",
                      _private(tmp_path), p) is None


def test_the_examples_placeholder_handle_leaves_it_inert(tmp_path):
    """The shipped example names nobody: a mailbox that is a caption must not
    become a destination someone is refused over."""
    text = ("version: 1\n"
            "identity:\n  name: Your Name\n  handle: your-handle\n")
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / profile.NAME).write_text(text)
    (cfg / profile.EXAMPLE).write_text(text)
    assert pg.public_owner(profile.resolve(cfg)) == ""
    assert pg.refuses("git@github.com:your-handle/familiaris.git",
                      _private(tmp_path), profile.resolve(cfg)) is None


# ── the state of the hook, which is the half that rots ───────────────────────


def _scratch(tmp_path, dev=True, handle=OWNER):
    """A checkout that can RUN the hook: its own copy of the engine it
    resolves at push time, its own profile, and a hook that is ours."""
    tree = tmp_path / "instance"
    (tree / "engine" / "checks").mkdir(parents=True)
    shutil.copytree(roots.ENGINE / "lib", tree / "engine" / "lib")
    # The hook runs two rules now, and leak_gate imports the scanner: a fixture
    # that copies one of the three tests a push that the instance's hook would
    # have answered differently. `.pazras/leak-patterns.txt` is the register a
    # repository that is not this instance reads -- the scratch tree has no
    # `dev/`, and one name nothing in it says keeps the gate quiet, so these
    # tests stay about the guard's rule.
    for name in ("push_guard.py", "leak_gate.py", "publish_scan.py",
                 pg.HOOK_NAME):
        shutil.copy2(pg.HERE / name, tree / "engine" / "checks" / name)
    (tree / ".pazras").mkdir()
    (tree / ".pazras" / "leak-patterns.txt").write_text("scratch-name\tZaphod\n")
    (tree / "config").mkdir()
    (tree / "config" / profile.NAME).write_text(
        f"version: 1\nidentity:\n  name: Test Owner\n  handle: {handle}\n")
    if dev:
        (tree / "dev").mkdir()
    (tree / "README.md").write_text("scratch\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(tree)], check=True)
    subprocess.run(["git", "-C", str(tree), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tree), *IDENT, "commit", "-q", "-m", "x"],
                   check=True)
    os.symlink(f"../../engine/checks/{pg.HOOK_NAME}",
               tree / ".git" / "hooks" / pg.HOOK_NAME)
    return tree


def _remote(tmp_path, repo):
    path = tmp_path / "remotes" / OWNER / repo
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
    return path


def test_an_armed_hook_is_what_check_wants(tmp_path):
    tree = _scratch(tmp_path)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert armed, message
    assert "armed at" in message


def test_a_hook_that_is_not_ours_is_a_finding(tmp_path):
    """A foreign pre-push hook at that path is not a guard: it may refuse
    anything or nothing, and nobody knows which."""
    tree = _scratch(tmp_path)
    hook = tree / ".git" / "hooks" / pg.HOOK_NAME
    hook.unlink()
    hook.write_text("#!/bin/sh\nexit 0\n")
    armed, message = pg.check(tree, _profile(tmp_path))
    assert not armed
    assert "is not this guard" in message


def test_a_hook_that_cannot_run_is_a_finding(tmp_path):
    tree = _scratch(tmp_path)
    hook = tree / ".git" / "hooks" / pg.HOOK_NAME
    hook.chmod(0o644)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert not armed
    assert "not executable" in message


def test_a_symlink_into_a_checkout_without_the_file_is_inert(tmp_path):
    """The shared-hook case, which is the instance's own: git resolves
    `$GIT_COMMON_DIR/hooks`, so a symlink written from one worktree points into
    the main checkout -- and until the revision carrying the hook reaches it,
    there is nothing there. Reported, not failed: the reader installed it
    correctly and cannot make it run."""
    tree = _scratch(tmp_path)
    hook = tree / ".git" / "hooks" / pg.HOOK_NAME
    hook.unlink()
    os.symlink("../../../elsewhere/engine/checks/pre-push", hook)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert armed, message
    assert "INSTALLED AND INERT" in message


def test_a_copy_of_the_hook_body_is_an_install(tmp_path):
    """The one arming that works before the file reaches the checkout git
    resolves hooks from: a copy. It is the same body, byte for byte."""
    tree = _scratch(tmp_path)
    hook = tree / ".git" / "hooks" / pg.HOOK_NAME
    hook.unlink()
    hook.write_bytes(pg.HOOK_FILE.read_bytes())
    hook.chmod(0o755)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert armed, message


def test_a_drifted_copy_is_a_finding(tmp_path):
    """A copy is not updated by git, so it can age into a guard nobody can
    predict. That is the drift the content comparison is for."""
    tree = _scratch(tmp_path)
    hook = tree / ".git" / "hooks" / pg.HOOK_NAME
    hook.unlink()
    hook.write_bytes(pg.HOOK_FILE.read_bytes() + "\n# aged\n".encode())
    hook.chmod(0o755)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert not armed
    assert "is not this guard" in message


def test_an_unarmed_private_checkout_is_a_finding(tmp_path):
    """The failure this exists for: the guard was written, the hook was never
    installed, and the tree looks protected."""
    tree = _scratch(tmp_path)
    (tree / ".git" / "hooks" / pg.HOOK_NAME).unlink()
    subprocess.run(["git", "-C", str(tree), "remote", "add", "origin",
                    f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}-other.git"],
                   check=True)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert not armed
    assert "NOT armed" in message and "ln -sfn" in message


def test_the_advice_is_the_copy_where_a_symlink_would_be_inert(tmp_path):
    """The instance's own state between the rename and the merge: the checkout
    git resolves hooks from has no `engine/checks/pre-push`, so the symlink the
    advice used to name would be installed, reported inert, and guard nothing."""
    tree = _scratch(tmp_path)
    (tree / ".git" / "hooks" / pg.HOOK_NAME).unlink()
    (tree / "engine" / "checks" / pg.HOOK_NAME).unlink()
    subprocess.run(["git", "-C", str(tree), "remote", "add", "origin",
                    f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}-other.git"],
                   check=True)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert not armed
    assert f"cp {pg.HOOK_FILE}" in message and "ln -sfn" not in message


def test_origin_still_naming_the_public_repository_is_content(tmp_path):
    """Before the rename and the `remote set-url`, the public name IS this
    repository: arming the guard then would refuse the push that is right, so
    that state is not a failure."""
    tree = _scratch(tmp_path)
    (tree / ".git" / "hooks" / pg.HOOK_NAME).unlink()
    subprocess.run(["git", "-C", str(tree), "remote", "add", "origin",
                    f"git@github.com:{OWNER}/{pg.PUBLIC_REPO}.git"], check=True)
    armed, message = pg.check(tree, _profile(tmp_path))
    assert armed, message
    assert "correctly so" in message


# ── the whole thing, through git ─────────────────────────────────────────────


def test_a_push_to_a_fake_public_remote_is_refused(tmp_path):
    """End to end, with the hook wired the way the instance wires it and a
    remote that is a bare directory: git asks, the guard answers, the push
    stops. No network, no forge."""
    tree = _scratch(tmp_path)
    done = subprocess.run(
        ["git", "-C", str(tree), "push",
         str(_remote(tmp_path, f"{pg.PUBLIC_REPO}.git")), "HEAD"],
        capture_output=True, text=True)
    assert done.returncode != 0, done.stdout + done.stderr
    assert "REFUSED" in done.stderr, done.stderr


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="a push that LANDS needs the instance's hook environment; in a "
           "generated tree the same push exits 0 and arrives nowhere, measured "
           "2026-10-14 under a scratch HOME")
def test_a_push_to_the_private_remote_goes_through(tmp_path):
    """The control: the same hook, the same tree, one character of the name
    different -- and the push lands in the bare repository."""
    tree = _scratch(tmp_path)
    target = _remote(tmp_path, f"{pg.PUBLIC_REPO}-other.git")
    done = subprocess.run(["git", "-C", str(tree), "push", str(target), "HEAD"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True).returncode == 0


def test_a_push_from_a_checkout_without_dev_goes_through(tmp_path):
    """The publish clone again, now through the hook rather than the rule: it
    pushes the generated tree to the public repository, which is its job."""
    tree = _scratch(tmp_path, dev=False)
    target = _remote(tmp_path, f"{pg.PUBLIC_REPO}.git")
    done = subprocess.run(["git", "-C", str(tree), "push", str(target), "HEAD"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


def test_armed_and_inert_where_the_profile_names_nobody(tmp_path):
    """The shipped example's tree: a hook can be installed and still have no
    public repository to refuse, because a placeholder handle is not one. The
    message has to say that rather than print an empty owner."""
    tree = _scratch(tmp_path)
    text = ("version: 1\n"
            "identity:\n  name: Your Name\n  handle: your-handle\n")
    (tree / "config" / profile.NAME).write_text(text)
    (tree / "config" / profile.EXAMPLE).write_text(text)
    armed, message = pg.check(tree, profile.resolve(tree / "config"))
    assert armed, message
    assert "inert" in message and "no public handle" in message


# ── a tree older than its rules, through the shared hook ─────────────────────


def _older(tmp_path, *missing):
    """A checkout on a branch that predates some of the rules the hook runs:
    the hook is a copy in `.git/hooks`, the scripts are not in the tree."""
    tree = _scratch(tmp_path)
    hook = tree / ".git" / "hooks" / pg.HOOK_NAME
    hook.unlink()
    hook.write_bytes(pg.HOOK_FILE.read_bytes())
    hook.chmod(0o755)
    for name in missing:
        (tree / "engine" / "checks" / name).unlink()
    return tree


def test_a_pre_guard_tree_with_dev_is_still_refused_the_public_name(tmp_path):
    """The case the fallback exists for: a branch without push_guard.py still
    carries `dev/`, so skipping the rule would open exactly the push it refuses."""
    tree = _older(tmp_path, "push_guard.py", "leak_gate.py")
    done = subprocess.run(
        ["git", "-C", str(tree), "push",
         str(_remote(tmp_path, f"{pg.PUBLIC_REPO}.git")), "HEAD"],
        capture_output=True, text=True)
    assert done.returncode != 0, done.stdout + done.stderr
    assert "REFUSED (coarse rule" in done.stderr, done.stderr


def test_a_pre_guard_tree_pushes_to_the_private_remote(tmp_path):
    """And the reason for the fallback: without it, `set -e` refused every push
    from such a branch, the private remote's included."""
    tree = _older(tmp_path, "push_guard.py", "leak_gate.py")
    target = _remote(tmp_path, f"{pg.PUBLIC_REPO}-other.git")
    done = subprocess.run(["git", "-C", str(tree), "push", str(target), "HEAD"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "not scanned" in done.stderr, done.stderr
