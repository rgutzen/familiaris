"""eval (4a): the loader refuses a task missing a field, `--list` prints one row
per task over a tmp tasks directory, and `--validate` holds a verifier to its
exit -- fail on the base alone, pass with the change -- on a tiny tmp git repo,
for a coding task (a reference commit) and for a key-answer task.

No test runs an arm or calls a model: there is nothing here to call one."""
import subprocess
import textwrap

import pytest

from lib import roots
from orchestration import eval as E

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="the real task set is `dev/orchestration/tasks/`, which the "
           "classification omits with `dev/`")

SET = textwrap.dedent("""\
    fields:
      - id
      - kind
      - title
      - base
      - reference
      - scope
      - verify
      - arms
    arms:
      - baseline
      - dispatch
      - bindings
      - jev
      - reference
    kinds:
      coding:
        count: 1
        arms: baseline, dispatch, reference
      retrieval:
        count: 1
        arms: baseline, dispatch, bindings, reference
        fields:
          - answer
    """)


def git(repo, *args):
    return subprocess.run(("git", "-C", str(repo)) + args, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A repository of two commits: `note.txt` says `old`, then `new`."""
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    for word in ("old", "new"):
        (r / "note.txt").write_text(word + "\n")
        git(r, "add", "-A")
        git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", word)
    return r, git(r, "rev-parse", "HEAD~1"), git(r, "rev-parse", "HEAD")


def fresh(tmp_path):
    """A tasks directory of its own, beside the `repo` fixture's repository."""
    root = tmp_path / "set"
    root.mkdir()
    (root / E.SET).write_text(SET)
    return root


def write_task(root, tid, fields, prompt=True, key=None):
    d = root / tid
    d.mkdir(parents=True)
    (d / "task.yaml").write_text("".join(f"{k}: {v}\n" for k, v in fields.items()))
    if prompt:
        (d / "prompt.md").write_text("Do the thing.\n")
    if key is not None:
        (d / "key.txt").write_text(key)
    return d


def coding(base_sha, ref, verify="grep -q new note.txt", **over):
    f = {"id": "c1", "kind": "coding", "title": "say new", "base": base_sha,
         "reference": ref, "scope": "note.txt", "verify": verify,
         "arms": "baseline, dispatch, reference"}
    f.update(over)
    return f


def retrieval(base_sha, **over):
    f = {"id": "r1", "kind": "retrieval", "title": "find it", "base": base_sha,
         "reference": "key.txt", "scope": "answer.md", "answer": "answer.md",
         "verify": 'cmp -s answer.md "$TASK_DIR/key.txt"',
         "arms": "baseline, dispatch, bindings, reference"}
    f.update(over)
    return f


@pytest.fixture
def tasks(tmp_path, repo):
    _, base, ref = repo
    root = tmp_path / "tasks"
    root.mkdir()
    (root / E.SET).write_text(SET)
    write_task(root, "c1", coding(base, ref))
    write_task(root, "r1", retrieval(base), key="note.txt:1\n")
    return root


# ── the loader ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field", ["id", "kind", "title", "base", "reference",
                                   "scope", "verify", "arms"])
def test_a_task_missing_a_field_is_refused_naming_it(tmp_path, repo, field):
    _, base, ref = repo
    root = fresh(tmp_path)
    f = coding(base, ref)
    del f[field]
    write_task(root, "c1", f)
    with pytest.raises(E.TaskError, match=f"missing field.*{field}"):
        E.load(root)


def test_a_kind_s_own_field_is_required_too(tmp_path, repo):
    _, base, _ = repo
    root = fresh(tmp_path)
    f = retrieval(base)
    del f["answer"]
    write_task(root, "r1", f, key="x")
    with pytest.raises(E.TaskError, match="missing field.*answer"):
        E.load(root)


@pytest.mark.parametrize("over,fragment", [
    ({"kind": "essay"}, "kind 'essay'"),
    ({"base": "abc123"}, "not a full commit sha"),
    ({"arms": "baseline, dispatch, reference, jev"}, "a coding task runs"),
    ({"arms": "baseline, dispatch, oracle"}, "unknown arm"),
    ({"id": "other"}, "is not its directory's name"),
    ({"tree": "half"}, "tree 'half'"),
])
def test_a_bad_value_is_refused(tmp_path, repo, over, fragment):
    _, base, ref = repo
    root = fresh(tmp_path)
    write_task(root, "c1", coding(base, ref, **over))
    with pytest.raises(E.TaskError, match=fragment):
        E.load(root)


def test_a_task_without_a_prompt_is_refused(tmp_path, repo):
    _, base, ref = repo
    root = fresh(tmp_path)
    write_task(root, "c1", coding(base, ref), prompt=False)
    with pytest.raises(E.TaskError, match="no prompt.md"):
        E.load(root)


@INSTANCE
def test_the_real_set_loads_and_has_the_declared_composition():
    tasks = E.load()
    assert len(tasks) == 14
    assert E.composition(tasks, E.load_set()) == []


# ── --list ───────────────────────────────────────────────────────────────────

def test_list_prints_one_row_per_task(tasks, repo, capsys):
    r, base, _ = repo
    rc = E.main(["--list", "--tasks-dir", str(tasks), "--repo", str(r)])
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out[0].split() == ["id", "kind", "base", "arms", "scope", "key"]
    assert out[1].split() == ["c1", "coding", base[:7], "baseline,dispatch,reference", "note.txt", "yes"]
    assert out[2].split() == ["r1", "retrieval", base[:7],
                              "baseline,dispatch,bindings,reference", "answer.md", "yes"]
    assert out[-1] == "eval: 2 task(s)"


def test_list_says_when_a_key_is_missing(tasks, repo, capsys):
    r, _, _ = repo
    (tasks / "r1" / "key.txt").unlink()
    rc = E.main(["--list", "--tasks-dir", str(tasks), "--repo", str(r)])
    row = [l for l in capsys.readouterr().out.splitlines() if l.startswith("r1")][0]
    assert rc == 1 and row.split()[-1] == "NO"


def test_list_names_a_kind_short_of_its_count(tasks, repo, capsys):
    r, _, _ = repo
    for p in (tasks / "r1").iterdir():
        p.unlink()
    (tasks / "r1").rmdir()
    rc = E.main(["--list", "--tasks-dir", str(tasks), "--repo", str(r)])
    assert rc == 1
    assert "retrieval: 0 task(s), the set declares 1" in capsys.readouterr().out


# ── --validate ───────────────────────────────────────────────────────────────

def test_materialise_is_the_base_alone_or_the_base_with_the_change(tasks, repo, tmp_path):
    r, _, _ = repo
    t = {x.id: x for x in E.load(tasks)}["c1"]
    E.materialise(t, tmp_path / "a", change=False, repo=r)
    E.materialise(t, tmp_path / "b", change=True, repo=r)
    assert (tmp_path / "a" / "note.txt").read_text() == "old\n"
    assert (tmp_path / "b" / "note.txt").read_text() == "new\n"
    # A fresh repository whose one commit is the base: no later commit is reachable.
    assert git(tmp_path / "b", "rev-list", "--all", "--count") == "1"


def test_a_coding_verifier_that_judges_meets_the_exit(tasks, repo):
    r, _, _ = repo
    t = {x.id: x for x in E.load(tasks)}["c1"]
    row = E.validate(t, r)
    assert row["ok"] and row["without"] == 1 and row["with"] == 0


def test_a_key_answer_task_meets_the_exit(tasks, repo):
    r, _, _ = repo
    t = {x.id: x for x in E.load(tasks)}["r1"]
    row = E.validate(t, r)
    assert row["ok"] and row["without"] != 0 and row["with"] == 0


@pytest.mark.parametrize("verify,why", [
    ("test -f note.txt", "passes on the base too"),
    ("grep -q newer note.txt", "fails with the change too"),
])
def test_a_verifier_that_cannot_tell_the_states_apart_is_reported(tmp_path, repo, verify, why, capsys):
    r, base, ref = repo
    root = fresh(tmp_path)
    write_task(root, "c1", coding(base, ref, verify=verify))
    rc = E.main(["--validate", "all", "--tasks-dir", str(root), "--repo", str(r)])
    out = capsys.readouterr().out
    assert rc == 1, why
    assert "0 met, 1 not met" in out


def test_several_references_apply_one_commit_diff_at_a_time(tmp_path, repo):
    """A reference list skips what landed between its commits: the middle
    commit adds a file no reference names, and it is not applied."""
    r, base, ref = repo
    (r / "other.txt").write_text("unrelated\n")
    git(r, "add", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "between")
    (r / "note.txt").write_text("new\nnewer\n")
    git(r, "add", "-A")
    git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "newer")
    last = git(r, "rev-parse", "HEAD")
    root = fresh(tmp_path)
    write_task(root, "c1", coding(base, f"{ref}, {last}", verify="grep -q newer note.txt"))
    t = E.load(root)[0]
    E.materialise(t, tmp_path / "w", change=True, repo=r)
    assert (tmp_path / "w" / "note.txt").read_text() == "new\nnewer\n"
    assert not (tmp_path / "w" / "other.txt").exists()
    assert E.validate(t, r)["ok"]


def test_an_empty_tree_task_starts_from_nothing(tmp_path, repo):
    r, base, _ = repo
    root = fresh(tmp_path)
    write_task(root, "r1", retrieval(base, tree="empty"), key="x\n")
    t = E.load(root)[0]
    E.materialise(t, tmp_path / "w", change=False, repo=r)
    assert [p.name for p in (tmp_path / "w").iterdir()] == [".git"]
