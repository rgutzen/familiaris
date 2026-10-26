"""Stage 0 -- Preflight, against a real repository.

Covers the 2026-09-07 change: a dirty tree is no longer an automatic abort.
It is snapshotted as its own commit UNLESS at least one dirty path looks
actively edited (mtime within QUIET_SECONDS), in which case the old abort
behaviour still applies.
"""
import datetime as dt
import os
import subprocess
import time

import pytest

from lib import git
from consolidation import pass_ctx
from consolidation.stages import preflight

IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *IDENT, *args],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "memory").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True)
    (r / "memory" / "one.md").write_text("one\n")
    (r / "CLAUDE.md").write_text("root file\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "first", "--date=2026-01-02T00:00:00")
    return r


@pytest.fixture
def ctx(repo, tmp_path):
    # base != agents in production (PAZRAS_DATA_DIR lives outside the repo,
    # see `roots.data_root()`) -- the lock file must not land inside
    # the tree it is guarding, or it would always be the dirty path.
    base = tmp_path / "data"
    base.mkdir()
    c = pass_ctx.Pass(repo / "memory", base, False, dt.date(2026, 1, 3))
    yield c
    preflight.release()


def _age(path, seconds):
    """Back-date a file's mtime so the quiescence check sees it as old."""
    t = time.time() - seconds
    os.utime(path, (t, t))


# ── clean tree: unaffected ───────────────────────────────────────────────────

def test_clean_tree_proceeds_without_committing(repo, ctx):
    before = git.head(repo)
    assert preflight.run(ctx) is True
    assert git.head(repo) == before
    assert ctx.actions == []


# ── dirty, old mtimes: snapshot ──────────────────────────────────────────────

def test_dirty_tree_outside_agents_is_snapshotted_and_the_pass_proceeds(repo, ctx):
    before = git.head(repo)
    (repo / "CLAUDE.md").write_text("edited by something, somewhere\n")
    (repo / "memory" / "one.md").write_text("edited too\n")
    _age(repo / "CLAUDE.md", preflight.QUIET_SECONDS + 60)
    _age(repo / "memory" / "one.md", preflight.QUIET_SECONDS + 60)

    assert preflight.run(ctx) is True
    assert git.head(repo) != before, "preflight must commit the dirty tree"
    assert git.status_lines(repo) == [], "tree must be clean after the snapshot"
    assert len(ctx.actions) == 1
    assert "pre-sleep snapshot" in ctx.actions[0].target


def test_the_snapshot_is_a_separate_commit_from_the_passs_own_work(repo, ctx):
    """Invariant 4 must still hold: reverting the pass's own commit must not
    also revert the human's leftover edits."""
    (repo / "CLAUDE.md").write_text("human wip\n")
    _age(repo / "CLAUDE.md", preflight.QUIET_SECONDS + 60)
    assert preflight.run(ctx) is True
    snapshot_head = git.head(repo)

    # Simulate the pass's own commit (invariant 4's normal path).
    (repo / "memory" / "one.md").write_text("pass-written content\n")
    r = git.commit(repo, "memory: nightly consolidation 2026-01-03")
    assert r.ok
    pass_head = git.head(repo)
    assert pass_head != snapshot_head

    _git(repo, "revert", "--no-edit", pass_head)
    assert (repo / "CLAUDE.md").read_text() == "human wip\n", (
        "reverting the pass's commit must leave the human snapshot intact")


# ── dirty, fresh mtime: still aborts ─────────────────────────────────────────

def test_a_freshly_touched_dirty_path_still_aborts(repo, ctx):
    before = git.head(repo)
    (repo / "CLAUDE.md").write_text("mid-edit right now\n")
    # No _age() call: mtime is "now", inside QUIET_SECONDS.

    assert preflight.run(ctx) is False
    assert git.head(repo) == before, "must not commit while someone looks active"
    assert "mid-edit" in ctx.aborted
    assert ctx.actions == []


# ── dry-run: report only, never commits ──────────────────────────────────────

def test_dry_run_never_commits_a_dirty_tree(repo, tmp_path):
    base = tmp_path / "data"
    base.mkdir()
    c = pass_ctx.Pass(repo / "memory", base, True, dt.date(2026, 1, 3))
    (repo / "CLAUDE.md").write_text("edited\n")
    _age(repo / "CLAUDE.md", preflight.QUIET_SECONDS + 60)
    before = git.head(repo)

    assert preflight.run(c) is True
    assert git.head(repo) == before
    assert git.status_lines(repo) != []
    assert any(n.level == "warn" for n in c.notes)
    preflight.release()


# ── a failing commit still aborts, loudly ────────────────────────────────────

def test_a_commit_failure_aborts_with_the_git_error(repo, ctx, monkeypatch):
    (repo / "CLAUDE.md").write_text("edited\n")
    _age(repo / "CLAUDE.md", preflight.QUIET_SECONDS + 60)

    def boom(repo_, message, paths=(".",)):
        return git.Result(False, err="simulated commit failure")
    monkeypatch.setattr(preflight.git, "commit", boom)

    assert preflight.run(ctx) is False
    assert "simulated commit failure" in ctx.aborted
