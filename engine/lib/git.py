"""git -- the one place that knows how to ask git a question.

WHY. Four modules each built their own `subprocess.run(["git", "-C", ...])`
with their own answer to "and if that fails?": `check=True` with a 60 s timeout
in `tree`, `check=True` with 30 s in `activity`, `check=False` with NO timeout
in `preflight` and in the nightly commit. The commit is the one call that must
not hang -- it runs after the lock is taken, and a hung `git commit` under
`Persistent=true` means the pass never finishes and the next night's catch-up
run finds the lock held. Now every call is timed and one module owns the answer.

DEEP, NOT A WRAPPER. The queries return DOMAIN VALUES -- dates, sets, lines --
so the two `git log` parsers (first-added dates for the cold-start window, and
commit days for the activity record) live here rather than in the modules that
happen to need them. A module that only rebuilt the argument list would be a
shallow module: deleting it would just scatter the same boilerplate back.

NOTHING HERE RAISES. Each caller already has its own documented fallback for
"git could not answer", and those fallbacks are the interesting knowledge:
preflight ABORTS (no repo means no idea what is being changed), `tree` falls
back to file mtime (which a checkout resets, hence the preference for git), and
`activity` falls back to calendar days (an empty activity record means "we do
not know", not "no work happened"). So a failed query returns an empty result
and the caller does what it already documented. `commit()` is the exception: it
returns a Result carrying stderr, because the pass must report WHY a commit
failed rather than silently not committing.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
import subprocess

from lib import roots

DEFAULT_TIMEOUT = 60
COMMIT_TIMEOUT = 120          # the lock is held; it must end, one way or another


@dataclasses.dataclass
class Result:
    ok: bool
    out: str = ""
    err: str = ""
    timed_out: bool = False


def run(repo, *args, timeout: int = DEFAULT_TIMEOUT) -> Result:
    """One git invocation. Never raises: a missing binary, a directory that is
    not a repository and a timeout are all answers, not exceptions."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return Result(False, err=f"`git {args[0]}` timed out after {timeout}s",
                      timed_out=True)
    except OSError as exc:
        return Result(False, err=f"cannot run git: {exc}")
    return Result(p.returncode == 0, p.stdout, p.stderr)


# ── queries ──────────────────────────────────────────────────────────────────

def status_lines(repo) -> list[str] | None:
    """Porcelain lines, or None when git could not answer at all.

    None and [] are different answers and the difference is load-bearing: []
    means a clean tree, None means this is not a repository, which is why
    preflight aborts on one and proceeds on the other.
    """
    r = run(repo, "status", "--porcelain")
    if not r.ok:
        return None
    return [l for l in r.out.split("\n") if l.strip()]


def head(repo) -> str:
    return run(repo, "rev-parse", "--short", "HEAD").out.strip()


def branch(repo) -> str:
    return run(repo, "rev-parse", "--abbrev-ref", "HEAD").out.strip()


def first_added(repo) -> dict[str, dt.date]:
    """repo-relative path -> the date it was first added.

    The cold-start window needs an age, and git is the only honest source:
    mtime is reset by a checkout or an rsync. A path that has never been
    committed is absent, and the caller falls back to mtime.
    """
    r = run(repo, "log", "--reverse", "--diff-filter=A", "--name-only",
            "--date=short", "--format=%x00%ad")
    if not r.ok:
        return {}
    seen: dict[str, str] = {}
    cur = None
    for line in r.out.split("\n"):
        if line.startswith("\x00"):
            cur = line[1:].strip()
        elif line.strip() and cur:
            seen.setdefault(line.strip(), cur)
    out = {}
    for path, day in seen.items():
        d = _day(day)
        if d:
            out[path] = d
    return out


def commit_days(repo) -> set:
    """Every date carrying a commit, on any branch -- evidence of work.

    `--all`, deliberately: a day spent on a feature branch was still a day at
    this machine, and utility must not decay for it.
    """
    r = run(repo, "log", "--all", "--date=short", "--format=%ad")
    if not r.ok:
        return set()
    return {d for d in (_day(l) for l in r.out.split("\n")) if d}


def _day(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError:
        return None


@dataclasses.dataclass
class Commit:
    sha: str
    date: str
    subject: str
    paths: tuple = ()


def commits_since(repo, rev: str = "", since_date: str = "",
                  limit: int = 200) -> list[Commit]:
    """Commits after `rev` (preferred) or after `since_date`, newest first.

    Two selectors because the caller has two qualities of memory of where it
    was. `rev..HEAD` is EXACT -- it is the revision the last pass left behind --
    and a date is the degraded fallback for a state file written before the
    revision was recorded, or for a rev that no longer resolves (a rebase, a
    reset, a fresh clone). The two are not equivalent and the caller must say
    which one it got, because "since 2026-09-11" silently re-reports commits
    the previous brief already covered.

    Empty on any failure, per the module rule: the caller states its fallback.
    """
    fmt = "--format=%x00%h%x1f%ad%x1f%s"
    args = ["log", "--date=short", "--name-only", f"--max-count={limit}", fmt]
    if rev:
        probe = run(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")
        if not probe.ok:
            return []
        args.append(f"{rev}..HEAD")
    elif since_date:
        # `--since` filters on the COMMITTER date and is parsed by approxidate,
        # which reads epoch 0 as "no date" and then matches nothing. Callers
        # pass a date written by the pass itself, so this only bites a sentinel.
        args.append(f"--since={since_date}")
    else:
        return []
    r = run(repo, *args)
    return _parse_log(r.out) if r.ok else []


def commits_matching(repo, grep: str, limit: int = 60) -> list[Commit]:
    """Commits whose message matches `grep`, newest first, with their paths.

    The posture check's evidence source: "which files has the nightly pass
    actually written" is a question about history, not about what a module
    claims it writes, and the two are exactly what a drifting control makes
    disagree.
    """
    r = run(repo, "log", "--all", f"--grep={grep}", "--date=short",
            "--name-only", f"--max-count={limit}",
            "--format=%x00%h%x1f%ad%x1f%s")
    return _parse_log(r.out) if r.ok else []


def diff_lines(repo, sha: str, *paths) -> list[str]:
    """The `+`/`-` lines one commit made under `paths`. Empty on any failure."""
    r = run(repo, "show", "--format=", "--unified=0", sha, "--", *paths)
    if not r.ok:
        return []
    # `l[:1] in "+-"` would be True for the empty string -- `"" in "+-"` is a
    # substring test, not a membership one -- and would return the trailing
    # blank line as a diff line.
    return [l for l in r.out.split("\n")
            if l[:1] in ("+", "-") and not l.startswith(("+++", "---"))]


def _parse_log(out: str) -> list[Commit]:
    commits: list[Commit] = []
    paths: list[str] = []
    for line in out.split("\n"):
        if line.startswith("\x00"):
            if commits:
                commits[-1].paths = tuple(paths)
            paths = []
            sha, _, tail = line[1:].partition("\x1f")
            day, _, subject = tail.partition("\x1f")
            commits.append(Commit(sha.strip(), day.strip(), subject.strip()))
        elif line.strip() and commits:
            paths.append(line.strip())
    if commits:
        commits[-1].paths = tuple(paths)
    return commits


# ── the one write ────────────────────────────────────────────────────────────

def commit(repo, message: str, paths=(roots.MEMORY_REL + "/",)) -> Result:
    """Stage `paths` and commit them as ONE commit (invariant 4: a bad night is
    one `git revert`). Returns the failure rather than hiding it."""
    add = run(repo, "add", "-A", *paths, timeout=COMMIT_TIMEOUT)
    if not add.ok:
        return Result(False, err=add.err or "git add failed", timed_out=add.timed_out)
    r = run(repo, "commit", "-m", message, timeout=COMMIT_TIMEOUT)
    return r
