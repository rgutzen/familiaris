"""C2: a dry run leaves the tracked tree byte-identical, whatever any stage does.

The `writes` column is gone and nothing table-driven forces a stage to honour
`--dry-run`; each stage self-gates. This test converts that convention into a
mechanism at the level that actually matters -- the working tree, not a column
declaring a stage *might* write.

The fixture gives the write-path stages real pending work, so the dry-run
gating is exercised rather than vacuous: aggregate must fold usage lines into a
skill, associate must add a missing back-link, replay must find a staged
transcript. If a stage ever drops its dry-run guard and writes, the snapshot
diverges and the test fails -- including for stages not yet written, because
the pass runs whole.
"""
import datetime as dt
import hashlib
import json
import subprocess

import pytest

from lib import git, invocation
from consolidation import run

TODAY = dt.date(2026, 9, 5)

# git plumbing -- a real repo, because preflight asks real git whether the tree
# is dirty and replay/aggregate resolve `created` from git history.
IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *IDENT, *args], check=True,
                   capture_output=True, text=True)


def _commit_all(repo, msg, date="2026-09-01T00:00:00"):
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)],
                   check=True, capture_output=True, text=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg, f"--date={date}")


def _leaf(p, *, name, related="[]", use_count=0, verified="2026-09-01",
          extra=""):
    p.mkdir(parents=True, exist_ok=True)
    f = p / f"{name}.md"
    f.write_text(
        "---\n"
        f"title: {name}\n"
        "authority: agent\n"
        "trust: trusted\n"
        f"last_verified: {verified}\n"
        f"use_count: {use_count}\n"
        f"last_used: {verified}\n"
        "stability: evolving\n"
        f"related: {related}\n"
        f"{extra}\n"
        "---\n\n"
        f"# {name}\n\nbody of {name}, long enough to matter\n")
    return f


@pytest.fixture
def repo(tmp_path):
    """A real git repo with an agents tree every stage can read, committed."""
    r = tmp_path / "repo"
    agents = r / "memory"
    (agents / "knowledge").mkdir(parents=True)
    (agents / "skills" / "system" / "practice" / "doer").mkdir(parents=True)

    # knowledge/ -- a and b are mutual neighbours but b is missing the back-link,
    # so associate has a repair to make.
    _leaf(agents / "knowledge", name="a", related='["b"]')
    _leaf(agents / "knowledge", name="b", related="[]")
    # c declares itself replaced by d, so the conflict stage has a marking to
    # apply -- without this the dry-run invariant below is VACUOUS for the one
    # stage that writes `trust:` outside downscale's proposal-only path.
    _leaf(agents / "knowledge", name="c", extra="superseded_by: d")
    _leaf(agents / "knowledge", name="d", extra="supersedes: c")
    # skills/ -- doer has use_count 0 but the usage ledger below says 2, so
    # aggregate has a frontmatter update to fold in.
    (agents / "skills" / "system" / "practice" / "doer" / "SKILL.md").write_text(
        "---\n"
        "name: doer\n"
        "description: does things\n"

        "invocation: model\n"
        "trust: trusted\n"
        "origin: authored\n"
        "triggers: []\n"
        "antitriggers: []\n"
        "related: []\n"
        "use_count: 0\n"
        "---\n\nbody\n")

    # journal/ -- one recent entry so consolidate has something to read.
    j = agents / "journal" / "2026" / "09"
    j.mkdir(parents=True)
    (j / "2026-09-03_sample.md").write_text(
        "---\n"
        "title: sample\n"
        "date: 2026-09-03\n"
        "session: sess-0\n"
        "cwd: /tmp\n"
        "---\n\nprose for the journal\n")

    _commit_all(r, "seed")
    return r


@pytest.fixture
def base(tmp_path):
    """The data dir (outside the repo, like the real one). Transcripts and the
    usage ledger make stages 1 and 2 believe there is real work."""
    d = tmp_path / "data"
    (d / "transcripts").mkdir(parents=True)
    prose = "We investigated the failing unit and found the cause. " * 8
    rows = [
        {"type": "user", "cwd": "/home/rg/06_SYSTEM", "gitBranch": "main",
         "sessionId": "sess-1", "timestamp": "2026-09-04T10:00:00Z",
         "message": {"content": prose}},
        {"type": "assistant", "sessionId": "sess-1",
         "message": {"content": [{"type": "text", "text": prose}]}},
    ]
    (d / "transcripts" / "20260904T100000Z_claude_sess-1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    (d / "skill-usage.jsonl").write_text(
        '{"ts":"2026-09-04T10:00:00Z","harness":"claude","skill":"doer",'
        '"session":"sess-1","cwd":"/tmp","signal":"model"}\n')
    return d


def _snapshot(repo):
    """{relative path: sha256} for every file under the repo working tree.

    Walking the tree rather than trusting git to report it means a file a stage
    writes NEW is caught the same as one it modifies -- the assertion is about
    bytes on disk, which is the invariant the comment on `report.py` states.
    """
    out = {}
    for p in sorted(repo.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            out[p.relative_to(repo).as_posix()] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return out


def _run_dry(repo, base, monkeypatch):
    """Run the full pass under --dry-run, every stage the real one."""
    inv = invocation.parse(["--dry-run", f"--date={TODAY.isoformat()}"],
                           run.SPEC, base=base, agents=repo / "memory")
    return run.main(inv)


def test_a_dry_run_leaves_the_tree_byte_identical(repo, base, monkeypatch,
                                                  tmp_path):
    before = _snapshot(repo)
    rc = _run_dry(repo, base, monkeypatch)
    assert rc == 0
    after = _snapshot(repo)
    assert after == before, "a --dry-run pass wrote to the tracked tree"


def test_the_fixture_has_real_pending_work(repo, base, monkeypatch):
    """Without this, the invariant test above could pass vacuously: a stage
    that never reaches its write decision is a stage not exercising its gate.
    Proved by running the tree-writers for real and watching the tree change --
    which is exactly what --dry-run must prevent."""
    from consolidation import pass_ctx
    from consolidation.stages import aggregate, associate, conflict
    ctx = pass_ctx.Pass(repo / "memory", base, False,
                        TODAY, flags=frozenset())
    before = _snapshot(repo)
    aggregate.run(ctx)
    associate.run(ctx)
    after = _snapshot(repo)
    assert after != before, ("fixture gives the write-stages nothing to do; "
                             "the dry-run invariant test is vacuous")

    # Stage 5d is the one writer whose change is not driven by a score or a log
    # line, so it is checked on its own terms: a plan with something pending, a
    # real apply, and markdown that says it happened.
    assert conflict.plan(repo / "memory").writes, (
        "fixture gives the conflict stage nothing to mark")
    marked = conflict.plan(repo / "memory").apply()
    assert [rel for rel, _ in marked] == ["knowledge/c.md"]
    assert "trust: deprecated" in (repo / "memory/knowledge/c.md").read_text()
