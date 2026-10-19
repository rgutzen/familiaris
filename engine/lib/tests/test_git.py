"""The git adapter, against a real repository.

Monkeypatching `subprocess.run` here would only assert that I typed the same
argument list twice. What can actually be wrong is the parsing of real `git
log` output and the behaviour when git cannot answer, so the tests build a
throw-away repo (identity passed with -c, so no global config is needed).
"""
import datetime as dt
import subprocess

import pytest

from lib import git

IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *IDENT, *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "memory").mkdir(parents=True)
    _git_init = subprocess.run(["git", "init", "-q", "-b", "main", str(r)],
                               capture_output=True, text=True)
    assert _git_init.returncode == 0
    (r / "memory" / "one.md").write_text("one\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "first", "--date=2026-01-02T00:00:00")
    return r


# ── the low level ────────────────────────────────────────────────────────────

def test_a_failing_command_is_an_answer_not_an_exception(tmp_path):
    r = git.run(tmp_path, "status", "--porcelain")
    assert r.ok is False and not r.timed_out and r.err


def test_a_timeout_is_reported_as_one(repo):
    r = git.run(repo, "log", timeout=0)
    assert r.ok is False and r.timed_out and "timed out" in r.err


def test_a_missing_git_binary_is_an_answer_too(repo, monkeypatch):
    def boom(*a, **k):
        raise OSError("No such file or directory: 'git'")
    monkeypatch.setattr(git.subprocess, "run", boom)
    r = git.run(repo, "status")
    assert r.ok is False and "cannot run git" in r.err


# ── status: None and [] mean different things ────────────────────────────────

def test_a_clean_tree_is_an_empty_list(repo):
    assert git.status_lines(repo) == []


def test_a_dirty_tree_lists_its_paths(repo):
    (repo / "memory" / "two.md").write_text("two\n")
    assert any("two.md" in line for line in git.status_lines(repo))


def test_a_directory_that_is_not_a_repository_answers_none(tmp_path):
    """preflight aborts on None and proceeds on [] -- the difference is why."""
    assert git.status_lines(tmp_path) is None


def test_head_and_branch(repo):
    assert len(git.head(repo)) >= 7
    assert git.branch(repo) == "main"


def test_head_of_a_non_repository_is_empty_rather_than_an_error(tmp_path):
    assert git.head(tmp_path) == "" and git.branch(tmp_path) == ""


# ── the two parsers ──────────────────────────────────────────────────────────

def test_first_added_dates_paths_by_the_commit_that_added_them(repo):
    (repo / "memory" / "later.md").write_text("later\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "second", "--date=2026-02-03T00:00:00")
    first = git.first_added(repo)
    assert first["memory/one.md"] == dt.date(2026, 1, 2)
    assert first["memory/later.md"] == dt.date(2026, 2, 3)


def test_a_rewritten_file_keeps_the_date_it_was_first_added(repo):
    (repo / "memory" / "one.md").write_text("rewritten\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "edit", "--date=2026-03-04T00:00:00")
    assert git.first_added(repo)["memory/one.md"] == dt.date(2026, 1, 2)


def test_a_path_never_committed_is_absent_so_the_caller_falls_back_to_mtime(repo):
    (repo / "memory" / "untracked.md").write_text("x\n")
    assert "memory/untracked.md" not in git.first_added(repo)


def test_first_added_of_a_non_repository_is_empty(tmp_path):
    assert git.first_added(tmp_path) == {}


def test_commit_days_counts_every_branch(repo):
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "memory" / "branch.md").write_text("b\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "on a branch", "--date=2026-04-05T00:00:00")
    _git(repo, "checkout", "-q", "main")
    days = git.commit_days(repo)
    assert dt.date(2026, 1, 2) in days
    assert dt.date(2026, 4, 5) in days, "a day on a feature branch was still a day"


def test_commit_days_of_a_non_repository_is_empty(tmp_path):
    assert git.commit_days(tmp_path) == set()


# ── the one write ────────────────────────────────────────────────────────────

def test_commit_stages_and_commits_in_one_commit(repo, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.invalid")
    (repo / "memory" / "new.md").write_text("new\n")
    (repo / "memory" / "second.md").write_text("second\n")
    before = git.run(repo, "rev-list", "--count", "HEAD").out.strip()
    r = git.commit(repo, "memory: nightly consolidation")
    assert r.ok, r.err
    after = git.run(repo, "rev-list", "--count", "HEAD").out.strip()
    assert int(after) == int(before) + 1, "one night, one commit"
    assert git.status_lines(repo) == []


def test_a_failed_commit_returns_why(repo):
    """Nothing staged: git refuses, and the pass must be able to say so."""
    r = git.commit(repo, "empty")
    assert not r.ok and (r.out or r.err)


def test_commit_only_stages_the_paths_it_was_given(repo, monkeypatch):
    for k, v in (("GIT_AUTHOR_NAME", "Test"), ("GIT_AUTHOR_EMAIL", "t@e.invalid"),
                 ("GIT_COMMITTER_NAME", "Test"), ("GIT_COMMITTER_EMAIL", "t@e.invalid")):
        monkeypatch.setenv(k, v)
    (repo / "memory" / "wanted.md").write_text("in\n")
    (repo / "outside.md").write_text("out\n")
    assert git.commit(repo, "only agents").ok
    assert [l for l in git.status_lines(repo) if "outside.md" in l], \
        "a path outside memory/ is left for the human"


# ── log ranges and diffs (the brief's and the posture check's evidence) ──────

def test_commits_since_a_revision_excludes_that_revision(repo):
    anchor = git.head(repo)
    (repo / "memory" / "new.md").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "after")
    got = git.commits_since(repo, rev=anchor)
    assert [c.subject for c in got] == ["after"]
    assert "memory/new.md" in got[0].paths


def test_an_unresolvable_revision_is_empty_not_a_traceback(repo):
    assert git.commits_since(repo, rev="deadbeef") == []


def test_commits_since_falls_back_to_a_date_when_asked(repo):
    # NOT 1970-01-01: git's approxidate reads epoch 0 as "no date" and the
    # filter then matches nothing, which would look like "nothing changed".
    # Every real caller passes a date out of `last-run.json`, so the sentinel
    # was the only place that trap could reach.
    got = git.commits_since(repo, since_date="2020-01-01")
    assert got and all(c.date for c in got)


def test_commits_since_nothing_is_empty_rather_than_the_whole_history(repo):
    """Neither selector given means the caller has no anchor -- answering with
    every commit ever would read as "all of this changed last night"."""
    assert git.commits_since(repo) == []


def test_commits_matching_selects_on_the_message(repo):
    (repo / "memory" / "a.md").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "memory: nightly consolidation 2026-09-12")
    (repo / "memory" / "b.md").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "docs: by hand")
    got = git.commits_matching(repo, "^memory: nightly consolidation")
    assert [c.subject for c in got] == ["memory: nightly consolidation 2026-09-12"]
    assert got[0].paths == ("memory/a.md",)


def test_diff_lines_returns_only_content_lines(repo):
    (repo / "memory" / "a.md").write_text("one\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add a")
    lines = git.diff_lines(repo, git.head(repo), "memory/a.md")
    assert lines == ["+one"]


def test_diff_lines_of_an_unknown_revision_is_empty(repo):
    assert git.diff_lines(repo, "deadbeef", ".") == []
