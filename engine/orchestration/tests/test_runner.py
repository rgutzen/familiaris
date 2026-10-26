"""runner (4c): the arms, the cell count, the command lines, the row, the dry run.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  count      PLAN's fifty cells come from `tasks.yaml`'s arms per kind, so the
             arithmetic is asserted twice: once as the composition over the real
             fourteen tasks, once as PLAN's own 14 x 3 + 5 + 3.
  commands   What separates the arms is a process, a model and one environment
             variable. A test per difference: the baseline's one session on the
             default, dispatch's one session per item in that item's model,
             PI_BINDINGS on the retrieval and web tasks and nowhere else, Jev as
             the process on the batch tasks only, and opencode's orchestrator.
  usage      A synthetic pi session log with exact numbers, because the frontier
             rule (input + output + cache-write, cache-read beside it) and the
             catalogue's price are two sums that must not drift into one.
  footprint  A real tmp repository: what the agent wrote against what the task
             declared, and the digest over the paths.
  rows       One JSON object per line, every arm's row carrying the same keys in
             the same order -- a row whose shape depends on the arm cannot be read
             as a column, which is what 4e's adoption rule does.
  dry run    `--run --dry-run` spawns nothing and writes nothing, with
             `subprocess.run` and `jev.ask` replaced by functions that fail the
             test. This is the item's own exit, so it is the one thing that must
             hold in a fresh checkout.

No test here starts pi, opencode, Jev or any other harness: the one test that
exercises a whole cell replaces the spawn seam with a fake agent.
"""
import json
import shutil
import subprocess
import textwrap
import time
import pathlib
import subprocess

import pytest

from lib import roots
from orchestration import eval as E

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="it plans cells from the real task set, `dev/orchestration/tasks/`,"
           " which the classification omits with `dev/`")


@pytest.fixture(autouse=True)
def _vendor_keys(monkeypatch):
    """Placeholder keys, so a model's availability never depends on the shell
    that runs the suite: the nightly pass's snapshot runs it under systemd, which
    has no DEEPSEEK_API_KEY, and these tests failed there (2026-10-16)."""
    for var in ("DEEPSEEK_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.setenv(var, "test-placeholder")

REAL = "orch-2b-dispatch-check"          # one item, `model: claude-sonnet-5-5` declared
STEP2 = "orch-step2-gate-skill-pointers"  # three items, three different models
RETRIEVAL = "retrieval-jev-calls"
BATCH = "batch-leaf-subject"             # 33 documents, 14 subjects


def task(tid, **kw):
    for t in E.load():
        if t.id == tid:
            return t
    raise AssertionError(f"no task {tid}")


def world(tmp_path):
    """The repository's own catalogue, capability map and dispatch rules: a plan
    reads real content, never a fixture that could drift from what dispatch does.
    `tmp_path` is there so a caller can pass one world to many cells."""
    return E.World.load()


@pytest.fixture
def tuning(tmp_path, monkeypatch):
    path = tmp_path / "oh-my-opencode-slim.json"
    path.write_text(json.dumps({"preset": "deepseek",
                                "presets": {"deepseek": {"orchestrator":
                                                         {"model": "deepseek/deepseek-v4-pro"}}}}))
    monkeypatch.setattr(E, "OPENCODE_TUNING", path)
    return path


# --- the count ---------------------------------------------------------------

@INSTANCE
def test_runner_cell_count_and_composition():
    """PLAN §Option 0's fifty, the way it counts them and the way tasks.yaml holds them."""
    tasks = E.load()
    cs = E.cells(tasks)
    assert len(cs) == 50
    assert E.cell_composition(cs) == {"baseline": 14, "dispatch": 14, "bindings": 5,
                                      "jev": 3, "reference": 14, "model": 0}, \
        "the model arm is the set's open slot: no kind declares it, so a bare run plans none"
    assert task(REAL).arms == ("baseline", "dispatch", "reference")
    assert 14 * 3 + 5 + 3 == 50                     # PLAN's own arithmetic
    by_kind = {}
    for t, _ in cs:
        by_kind[t.kind] = by_kind.get(t.kind, 0) + 1
    assert by_kind == {"coding": 18, "retrieval": 12, "batch": 12, "web": 8}
    assert 6 * 3 + 3 * 4 + 3 * 4 + 2 * 4 == 50      # the same fifty, by kind
    assert task(RETRIEVAL).arms == ("baseline", "dispatch", "bindings", "reference")
    assert task(BATCH).arms == ("baseline", "dispatch", "jev", "reference")
    assert task("hermes-guard-h1h2").arms == ("baseline", "dispatch", "reference")


@INSTANCE
def test_runner_arm_filter_selects_and_refuses():
    tasks = E.load()
    assert len(E.cells(tasks, "jev")) == 3
    assert len(E.cells(tasks, "bindings")) == 5
    assert len(E.cells(tasks, "baseline,reference")) == 28
    assert len(E.cells(tasks, "jev,bindings")) == 8
    with pytest.raises(E.RunnerError) as e:
        E.cells(tasks, "bogus")
    assert "unknown arm(s): bogus" in str(e.value)


# --- the measurement arm (2026-10-23) -----------------------------------------

@INSTANCE
def test_runner_the_model_arm_runs_the_model_the_run_names(tmp_path, tuning):
    """One session for the whole prompt on the catalogue id `--model` names. It is
    the arm a model is measured on BEFORE any tier names it: the dispatch arm runs
    the tiers, so a set that only runs dispatch can never measure a new model."""
    w = E.World.load()
    w.override = "zai-glm-5-3-flash"
    c = E.plan_cell(task(REAL), "model", workdir=tmp_path, w=w)
    cmd, = c.commands
    assert cmd.model == "zai-glm-5-3-flash" and cmd.source == "override"
    assert cmd.pi_model == "mistral/zai-glm-5-3-flash", "resolved through the profile"
    assert cmd.argv[4] == "mistral/zai-glm-5-3-flash"
    assert "override: zai-glm-5-3-flash" in cmd.how
    assert cmd.effort, "the class's tier level, so a comparison has one difference"
    base = E.plan_cell(task(REAL), "baseline", workdir=tmp_path, w=E.World.load())
    assert base.commands[0].argv[4] != cmd.argv[4], "the model is the only difference"


@INSTANCE
def test_runner_the_model_arm_without_a_model_is_refused(tmp_path):
    with pytest.raises(E.RunnerError) as e:
        E.plan_cell(task(REAL), "model", workdir=tmp_path, w=E.World.load())
    assert "pass --model" in str(e.value)


@INSTANCE
def test_runner_cells_plan_the_model_arm_only_when_a_model_is_named():
    tasks = E.load()
    assert len(E.cells(tasks)) == 50, "a bare --run is unchanged"
    assert len(E.cells(tasks, None, with_model=True)) == 14, "one cell per task, alone"
    both = E.cells(tasks, "baseline,model", with_model=True)
    assert len(both) == 28 and E.cell_composition(both)["model"] == 14
    with pytest.raises(E.RunnerError) as e:
        E.cells(tasks, "model")
    assert "pass --model" in str(e.value)


# --- the command lines -------------------------------------------------------

@INSTANCE
def test_runner_baseline_is_one_session_on_the_default(tmp_path, tuning):
    """The baseline runs the whole prompt once, on the session default, with no
    arm-specific environment at all."""
    c = E.plan_cell(task(STEP2), "baseline", workdir=tmp_path, w=world(tmp_path))
    assert len(c.commands) == 1
    cmd = c.commands[0]
    assert cmd.model == E.DEFAULT_MODEL == "claude-opus-5-5"
    assert cmd.pi_model == "claude-bridge/claude-opus-5-5"
    assert cmd.env == ()
    assert cmd.argv[0:3] == ("pi", "-p", (task(STEP2).dir / "prompt.md").read_text())
    assert cmd.argv[3:5] == ("--model", "claude-bridge/claude-opus-5-5")
    # The level follows the CLASS (edit tier 1), not the model's chooser: it is
    # the cheapest dial and nobody declares one in a SPECS.md (decision 28).
    assert cmd.effort == "medium" and cmd.argv[5:7] == ("--thinking", "medium")
    assert cmd.argv[7:9] == ("--session-dir", str(c.sessions))
    assert cmd.argv[-1] == "--no-approve"
    assert E.shell_line(cmd).startswith("pi -p \"$(cat ")


@INSTANCE
def test_runner_dispatch_runs_one_session_per_item_in_that_item_s_model(tmp_path, tuning):
    t = task(STEP2)
    c = E.plan_cell(t, "dispatch", workdir=tmp_path, w=world(tmp_path))
    assert [x.item for x in c.commands] == ["2c", "2d", "2e"]
    assert [x.model for x in c.commands] == ["claude-sonnet-5-5", "claude-opus-5-5",
                                             "claude-haiku-5-5"]
    assert [x.pi_model for x in c.commands] == ["claude-bridge/claude-sonnet-5-5",
                                                "claude-bridge/claude-opus-5-5",
                                                "claude-bridge/claude-haiku-5-5"]
    assert [x.wave for x in c.commands] == [1, 1, 2]      # 2e depends on 2d
    assert {x.effort for x in c.commands} == {"medium"}, "the class's level, per command"
    assert all(x.how == "declared: dispatch stands (probes unknown)" for x in c.commands)
    assert all(x.prompt_file == f"prompt-{x.item}.txt" for x in c.commands)
    # the item's own text, under the prompt's preamble: 2e is the pointers item
    prompt = c.commands[2].argv[2]
    assert prompt.startswith("Implement these three items")
    assert "- [ ] **2e · the pointers.**" in prompt
    assert "- [ ] **2c · the gate.**" not in prompt
    assert prompt.endswith("verify: engine/familiar context links --check\n")
    assert c.note == "2 wave(s), 3 dependency(ies) outside this task: 2a, 2b, 2g"


@INSTANCE
def test_runner_dispatch_builds_a_field_less_prompt_s_item_from_task_yaml(tmp_path, tuning):
    """4a's note: the pre-contract prompts carry no fields, so the arm's plan is
    built from task.yaml -- and its MODEL is the class's first tier
    (selection.yaml, decision 27), not the session default."""
    t = task("hermes-guard-h1h2")
    c = E.plan_cell(t, "dispatch", workdir=tmp_path, w=world(tmp_path))
    assert [x.item for x in c.commands] == ["H1", "H2"]
    assert {x.model for x in c.commands} == {"deepseek-flash"}, \
        "the edit class's first tier, whose cheapest member is the non-Claude one"
    assert all(x.source == "default (edit tier 1)" for x in c.commands)
    assert all("the class's pre-selection" in x.how for x in c.commands)


@INSTANCE
def test_runner_dispatch_differs_where_a_kind_names_a_class(tmp_path, tuning):
    """It USED to be the baseline's command line for every prompt that declared
    nothing -- 11 of the 14 cells, measured 2026-10-14 -- which made the arm
    unmeasurable. With the class tiers the arm has a treatment: retrieval and web
    are `read`, batch is `batch`, and each class's first tier names the model."""
    for tid, want in ((RETRIEVAL, "claude-haiku-5-5"), (BATCH, "claude-haiku-5-5"),
                      ("web-retention-terms", "claude-haiku-5-5")):
        base = E.plan_cell(task(tid), "baseline", workdir=tmp_path, w=world(tmp_path))
        disp = E.plan_cell(task(tid), "dispatch", workdir=tmp_path, w=world(tmp_path))
        assert base.commands[0].model == E.DEFAULT_MODEL
        assert disp.commands[0].model == want
        assert disp.commands[0].how.startswith("no declaration (not a SPECS item)")
        assert [x.model for x in base.commands] != [x.model for x in disp.commands]


@INSTANCE
def test_runner_bindings_sets_pi_bindings_on_retrieval_and_web_only(tmp_path, tuning):
    for tid, want in ((RETRIEVAL, True), ("web-deepseek-routing", True),
                      ("batch-leaf-subject", False), ("hermes-guard-h1h2", False)):
        t = task(tid)
        assert ("bindings" in t.arms) is want
        if not want:
            continue
        c = E.plan_cell(t, "bindings", workdir=tmp_path, w=world(tmp_path))
        assert c.commands[0].env == (("PI_BINDINGS", "1"),)
        assert c.commands[0].model == E.DEFAULT_MODEL
        assert E.shell_line(c.commands[0]).startswith("PI_BINDINGS=1 pi -p ")
    base = E.plan_cell(task(RETRIEVAL), "baseline", workdir=tmp_path, w=world(tmp_path))
    assert base.commands[0].env == ()                       # the whole difference
    assert not E.shell_line(base.commands[0]).startswith("PI_BINDINGS")


@INSTANCE
def test_runner_jev_is_the_process_on_batch_tasks_and_calls_no_pi(tmp_path, tuning):
    assert "jev" not in task("hermes-guard-h1h2").arms
    assert "jev" not in task(RETRIEVAL).arms
    c = E.plan_cell(task(BATCH), "jev", workdir=tmp_path, w=world(tmp_path))
    assert len(c.commands) == 1
    cmd = c.commands[0]
    assert cmd.argv == ()                                   # `jev.ask`, not a process
    assert cmd.model == "jev-1.13.0"
    assert len(cmd.calls) == 33
    assert all(size > 200 for _, size in cmd.calls)          # each document's own state
    assert E.shell_line(cmd) == "(no process: `jev.ask` is called in-process)"
    docs, opts, instructions = E.jev_plan(task(BATCH))
    assert len(docs) == 33 and len(opts) == 14
    assert docs[0][0] == "L01" and docs[0][1].startswith("title: pazras-cli")
    assert "falsified" in " ".join(opts.values()).lower()
    assert instructions.startswith("The state is one document")
    jdocs, jopts, jinstructions = E.jev_plan(task("batch-journal-tags"))
    assert len(jdocs) == 10 and len(jopts) == 10
    assert jinstructions.startswith("Match each journal entry to its own tag set")


@INSTANCE
def test_runner_reference_runs_opencode_with_the_orchestrator_agent(tmp_path, tuning):
    c = E.plan_cell(task(REAL), "reference", workdir=tmp_path, w=world(tmp_path))
    cmd = c.commands[0]
    assert cmd.argv[0:6] == ("opencode", "run", "--agent", "orchestrator",
                             "--title", f"eval {REAL} reference #1")
    # The workspace is named EXPLICITLY: the client hands it to opencode's server,
    # and cwd alone does not fix the agent's idea of where it works (2026-10-14).
    assert cmd.argv[6:8] == ("--dir", str(c.sessions.parent / "tree"))
    assert cmd.argv[8] == (task(REAL).dir / "prompt.md").read_text()
    assert cmd.model == "deepseek/deepseek-v4-pro"
    assert cmd.pi_model == ""
    assert cmd.pi_model == "" and "orchestrator" in cmd.how
    assert E.opencode_model(tuning) == "deepseek/deepseek-v4-pro"
    assert E.opencode_model(tmp_path / "absent.json") == ""


@INSTANCE
def test_runner_plans_are_refused_before_anything_runs(tmp_path, tuning):
    with pytest.raises(E.RunnerError):
        E.plan_cell(task(REAL), "nope", workdir=tmp_path, w=world(tmp_path))
    # a prompt the runner has no documents to ask about
    d = tmp_path / "empty-task"
    d.mkdir()
    (d / "prompt.md").write_text("Nothing to label.\n")
    t = E.Task(id="empty-task", kind="batch", title="t", base="", reference=(),
               scope=("labels.tsv",), verify="true", arms=("jev",), dir=d,
               answer="labels.tsv", tree="empty")
    with pytest.raises(E.RunnerError) as e:
        E.plan_cell(t, "jev", workdir=tmp_path, w=world(tmp_path))
    assert "Jev cannot be asked" in str(e.value)
    # an item only the user may do
    (d / "prompt.md").write_text(
        "- [ ] **U1 · the user's.** prose\n  touches: a\n  depends: —\n  model: user\n"
        "  verify: true\n")
    t = E.Task(id="user-task", kind="coding", title="t", base="", reference=(),
               scope=("a",), verify="true", arms=("dispatch",), dir=d, tree="empty")
    with pytest.raises(E.RunnerError) as e:
        E.plan_cell(t, "dispatch", workdir=tmp_path, w=world(tmp_path))
    assert "model: user" in str(e.value)


# --- usage -------------------------------------------------------------------

LOG = "\n".join([
    json.dumps({"type": "session", "cwd": "/tmp/cell/tree"}),
    json.dumps({"type": "model_change", "provider": "claude-bridge",
                "modelId": "claude-opus-5-5"}),
    json.dumps({"type": "message", "message": {
        "role": "assistant",
        "usage": {"input": 1000, "output": 200, "cacheWrite": 5000, "cacheRead": 40000,
                  "totalTokens": 46200},
        "content": [{"type": "toolCall", "name": "bash"},
                    {"type": "toolCall", "name": "read"}]}}),
    "a torn last line",                       # append-only: the log's normal last state
    json.dumps({"type": "message", "message": {
        "role": "assistant",
        "usage": {"input": 500, "output": 100, "cacheWrite": 0, "cacheRead": 2000},
        "content": [{"type": "toolCall", "name": "bound_read"}]}}),
]) + "\n"


def test_runner_reads_a_pi_session_log_into_the_usage_row(tmp_path):
    """The pools, the frontier rule and the API-equivalent price, exactly:
    frontier = input + output + cache-write = 1500 + 300 + 5000 = 6800;
    frontier $ = 1500 x 4/Mtok + 5000 x 5/Mtok + 300 x 20/Mtok = 0.006 + 0.025 + 0.006
    = 0.037 (cache writes at the vendor's 5m rate, 14c; at the input rate before);
    cache-read is separate, at the catalogue's cache_hit (0.20/Mtok): 0.0084 more."""
    log = tmp_path / "sessions" / "2026-01-01T00-00-00-000Z_x.jsonl"
    log.parent.mkdir()
    log.write_text(LOG, encoding="utf-8")
    pools = E.read_usage([log])
    assert pools == {"input": 1500, "output": 300, "cache_write": 5000, "cache_read": 42000}
    price = E.catalogue_price("claude-opus-5-5", E.World.load().cat)
    assert price["in"] == "4" and price["out"] == "20" and price["cache_hit"] == "0.20"
    assert price["cache_write"] == "5"
    usd, frontier_usd = E.cost(pools, price)
    assert frontier_usd == 0.037
    assert usd == 0.0454
    assert E.log_model([log]) == "claude-bridge/claude-opus-5-5"
    assert E.log_tools([log]) == ["bash", "bound_read", "read"]
    # the arm's fingerprint is the tool names: the bindings arm calls bound_*
    assert "bound_read" in E.log_tools([log]) and "bound_read" not in ["bash", "read"]


def test_runner_price_is_the_catalogue_s_and_missing_ones_are_named(tmp_path):
    cat = E.World.load().cat
    jev_price = E.catalogue_price("jev-1.13.0", cat)
    assert jev_price["in"] == "0.042" and jev_price["out"] == "0"
    # Jev names no cache rate: cache-read falls back to the input rate, and output is free
    assert E.cost({"input": 1_000_000, "output": 5_000_000, "cache_write": 0,
                   "cache_read": 1_000_000}, jev_price) == (0.084, 0.042)
    assert E.catalogue_price("deepseek/deepseek-v4-pro", cat) == {}
    assert E.cost({"input": 100, "output": 100, "cache_write": 0, "cache_read": 0}, {}) == (0.0, 0.0)
    assert E.estimate(4000, E.catalogue_price("claude-opus-5-5", cat)) == (1000, 0.004)
    assert E.estimate(4000, {}) == (1000, 0.0)


@INSTANCE
def test_runner_price_comes_from_one_row_for_every_arm(tmp_path, tuning):
    """No arm prices itself: the row's $ is the catalogue's, whatever the harness
    wrote in its own log."""
    t = task(BATCH)
    rows = []
    for arm in ("baseline", "jev"):
        c = E.plan_cell(t, arm, workdir=tmp_path, w=world(tmp_path))
        model = c.commands[0].model
        rows.append(E.make_row(t, arm, model=model,
                               pools={"input": 1_000_000, "output": 0, "cache_write": 0,
                                      "cache_read": 0},
                               price=E.catalogue_price(model, E.World.load().cat)))
    assert rows[0]["usage"]["usd"] == 4.0        # Opus at $4/Mtok in
    assert rows[1]["usage"]["usd"] == 0.042      # Jev at $0.042/Mtok in
    assert rows[0]["usage"]["frontier"] == rows[1]["usage"]["frontier"] == 1_000_000


# --- the tree ----------------------------------------------------------------

def test_runner_out_of_scope_files_from_a_synthetic_tree(tmp_path):
    """A real repository: three files the task declared and two it did not, a
    directory the scope covers under a glob, and the digest over what changed."""
    tree = tmp_path / "tree"
    tree.mkdir()
    subprocess.run(("git", "init", "-q", "-b", "main"), cwd=tree, check=True)
    (tree / "answer.md").write_text("start\n")
    subprocess.run(("git", "add", "-A"), cwd=tree, check=True)
    subprocess.run(("git", "-c", "user.email=e@x", "-c", "user.name=e",
                    "commit", "-qm", "base snapshot"), cwd=tree, check=True)
    assert E.touched(tree, ("answer.md",))["changed"] == []
    (tree / "answer.md").write_text("1999 the answer\n")             # declared
    (tree / "notes").mkdir()
    (tree / "notes" / "a.md").write_text("in\n")                     # declared: notes/**
    (tree / "stray.py").write_text("out\n")                          # not declared
    (tree / ".pytest_cache").mkdir()
    (tree / ".pytest_cache" / "CACHEDIR.TAG").write_text("out\n")    # not declared, either
    got = E.touched(tree, ("answer.md", "notes/**"))
    assert got["changed"] == [".pytest_cache/CACHEDIR.TAG", "answer.md", "notes/a.md", "stray.py"]
    assert got["outside"] == [".pytest_cache/CACHEDIR.TAG", "stray.py"]
    assert got["n"] == 4
    assert got["digest"] == "sha256:" + __import__("hashlib").sha256(
        "\n".join(got["changed"]).encode()).hexdigest()[:16]
    assert E.touched(tree, ("answer.md", "notes"))["outside"] == [".pytest_cache/CACHEDIR.TAG",
                                                                 "stray.py"]
    assert E.in_scope("engine/x/y.py", ("engine/x",))
    assert E.in_scope("engine/orchestration/tests/test_a.py", ("engine/orchestration/tests/**",))
    assert not E.in_scope("engine/orchestration/waves.py", ("engine/orchestration/tests/**",))
    assert not E.in_scope("dev/orchestration/SPECS.md.bak", ("dev/orchestration/SPECS.md",))
    assert E.in_scope("config/checks/x.yaml", ("config/checks/**",))


def test_runner_rework_counts_the_rounds_after_a_non_pass():
    assert E.rework([]) == 0
    assert E.rework([(0, "d")]) == 0                       # passed first, nothing after
    assert E.rework([(0, "d"), (0, "d")]) == 0              # passed twice, no further edit
    assert E.rework([(0, "d"), (0, "e")]) == 1              # edited after the pass
    assert E.rework([(1, "d")]) == 0                        # failed, never retried
    assert E.rework([(1, "d"), (0, "e")]) == 1
    assert E.rework([(1, "d"), (1, "e"), (0, "f")]) == 2
    assert E.rework([(0, "d"), (1, "e")]) == 1


# --- the row -----------------------------------------------------------------

@INSTANCE
def test_runner_rows_append_one_json_object_per_line_with_stable_keys(tmp_path, monkeypatch):
    t = task(BATCH)
    rows = [E.make_row(t, "baseline", model="claude-opus-5-5", pi_model="claude-bridge/x",
                       ran_model="claude-bridge/claude-opus-5-5", attempt=2,
                       tree="/tmp/t", session_dir="/tmp/s",
                       commands=(E.Command("", "claude-opus-5-5", ("pi", "-p", "x")),),
                       verifier={"exit": 1, "pass": False, "tail": "two of three"},
                       pools={"input": 10, "output": 2, "cache_write": 0, "cache_read": 0},
                       price={"in": "4", "out": "20"},
                       footprint={"changed": ["a"], "outside": ["a"], "digest": "sha256:x", "n": 1},
                       verifies=[1], rework_n=0, usage_source="session-log", note="n"),
            E.make_row(t, "jev", model="jev-1.13.0", ran_model="jev-1.13.0",
                       commands=(E.Command("", "jev-1.13.0"),),
                       verifier={"exit": 0, "pass": True, "tail": ""},
                       pools={"input": 1_000_000, "output": 5, "cache_write": 0, "cache_read": 0},
                       price={"in": "0.042", "out": "0"}, usage_source="jev-response")]
    assert tuple(rows[0]) == E.ROW_KEYS and tuple(rows[1]) == E.ROW_KEYS
    assert rows[0]["verifier"] == {"exit": 1, "pass": False, "tail": "two of three"}
    assert rows[0]["usage"]["frontier"] == 12 and rows[0]["usage"]["usd"] == 0.00008
    assert rows[0]["rework"] == 0 and rows[0]["attempt"] == 2
    path = tmp_path / "rows.jsonl"
    for row in rows:
        E.append_row(row, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2                                  # one object per line, appended
    assert [tuple(json.loads(line)) for line in lines] == [E.ROW_KEYS, E.ROW_KEYS]
    assert json.loads(lines[0])["outside_scope"] == ["a"]
    E.append_row(rows[0], path)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3
    # the default lives under PAZRAS_DATA_DIR, like the approvals log; the test
    # points that at a tmp directory rather than writing into the user's own
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path / "data"))
    assert E.append_row(rows[0]) == tmp_path / "data" / E.RESULTS
    assert (tmp_path / "data" / E.RESULTS).read_text(encoding="utf-8").count("\n") == 1
    assert E.profiles.data_dir() == tmp_path / "data"


# --- the whole cell, and the dry run -----------------------------------------

@pytest.fixture
def demo(tmp_path):
    """One task whose tree is empty and whose verifier is a file test, so a whole
    cell runs offline in a second."""
    d = tmp_path / "demo-task"
    d.mkdir()
    (d / "prompt.md").write_text("Write the answer.\n")
    return E.Task(id="demo-task", kind="retrieval", title="demo", base="", reference=(),
                  scope=("answer.md", "notes/**"), verify="test -s answer.md",
                  arms=("baseline",), dir=d, answer="answer.md", tree="empty")


def fake_agent(cwd, log):
    """What a real agent does, at the seam: writes in and out of scope and a
    session log, then exits."""
    def spawn(argv, cwd_, env, timeout=E.AGENT_TIMEOUT):
        cwd_ = pathlib.Path(cwd_)
        (cwd_ / "answer.md").write_text("1999 the answer\n")
        (cwd_ / "notes").mkdir(exist_ok=True)
        (cwd_ / "notes" / "a.md").write_text("in\n")
        (cwd_ / "stray.py").write_text("out\n")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(LOG.replace("/tmp/cell/tree", str(cwd_)), encoding="utf-8")
        return subprocess.CompletedProcess(list(argv), 0, "ok", "")
    return spawn


def test_runner_a_cell_runs_end_to_end_and_records_its_row(demo, tmp_path):
    c = E.plan_cell(demo, "baseline", workdir=tmp_path / "wd", w=world(tmp_path))
    log = c.sessions / "2026-01-01T00-00-00-000Z_x.jsonl"
    row = E.run_cell(c, w=world(tmp_path), spawn=fake_agent(c.tree, log))
    assert tuple(row) == E.ROW_KEYS
    assert row["task"] == "demo-task" and row["arm"] == "baseline" and row["attempt"] == 1
    assert row["verifier"] == {"exit": 0, "pass": True, "tail": ""}
    assert row["usage"]["input"] == 1500 and row["usage"]["cache_read"] == 42000
    assert row["usage"]["frontier"] == 6800 and row["usage"]["usd"] == 0.0454
    assert row["usage"]["source"] == "session-log" and row["usage"]["priced"] is True
    assert row["ran_model"] == "claude-bridge/claude-opus-5-5"
    assert row["outside_scope"] == ["stray.py"]
    assert row["session_logs"] == [str(log)]
    assert row["rework"] == 0 and row["verifies"] == [0]
    assert row["commands"][0][0] == "pi"
    assert (c.tree / "answer.md").is_file()
    assert str(c.tree) in row["tree"]


def test_runner_a_failing_cell_records_the_verifier_s_tail_and_its_rounds(tmp_path):
    """The verifier is the only judge: its exit, its last lines, and how many times
    the cell had to run again after the first non-pass."""
    d = tmp_path / "noisy"
    d.mkdir()
    (d / "prompt.md").write_text("x\n")
    t = E.Task(id="noisy", kind="retrieval", title="t", base="", reference=(),
               scope=("answer.md",), arms=("baseline",), dir=d, answer="answer.md",
               verify="echo 'one of two' >&2; echo 'two of two' >&2; false", tree="empty")
    c = E.plan_cell(t, "baseline", workdir=tmp_path / "wd", w=world(tmp_path))
    row = E.run_cell(c, w=world(tmp_path), spawn=fake_agent(c.tree, c.sessions / "s.jsonl"))
    assert row["verifier"] == {"exit": 1, "pass": False, "tail": "one of two | two of two"}
    assert row["verifies"] == [1] and row["rework"] == 0
    again = E.run_cell(c, rounds=3, w=world(tmp_path),
                       spawn=fake_agent(c.tree, c.sessions / "s.jsonl"))
    assert again["verifies"] == [1, 1, 1] and again["rework"] == 2


def test_runner_rework_after_a_pass_counts_against_the_arm(demo, tmp_path):
    """A run that passed and kept writing is not the run that stopped: the second
    round's footprint differs, and the digest is what says so."""
    c = E.plan_cell(demo, "baseline", workdir=tmp_path / "wd", w=world(tmp_path))
    log = c.sessions / "s.jsonl"
    calls = []

    def two_faced(argv, cwd, env, timeout=E.AGENT_TIMEOUT):
        calls.append(1)
        (pathlib.Path(cwd) / "answer.md").write_text("1999\n")
        if len(calls) > 1:
            (pathlib.Path(cwd) / "stray.py").write_text("out\n")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(LOG, encoding="utf-8")
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    row = E.run_cell(c, rounds=2, w=world(tmp_path), spawn=two_faced)
    assert row["verifies"] == [0, 0]
    assert row["rework"] == 1
    assert row["outside_scope"] == ["stray.py"]
    assert row["verifier"]["pass"] is True


def test_runner_a_cell_without_a_session_log_says_so(demo, tmp_path):
    c = E.plan_cell(demo, "baseline", workdir=tmp_path / "wd", w=world(tmp_path))
    row = E.run_cell(c, w=world(tmp_path), spawn=fake_agent(c.tree, tmp_path / "elsewhere.jsonl"))
    assert row["usage"]["source"] == "" and row["usage"]["frontier"] == 0
    assert row["session_logs"] == []
    assert "no session log found: usage not read" in row["note"]


def test_runner_session_log_fallback_is_by_the_tree_the_log_names(tmp_path, monkeypatch):
    """A pi that ignores `--session-dir` writes under ~/.pi/agent/sessions/<cwd>/:
    the fallback reads that log, and only if it names this cell's tree."""
    root = tmp_path / "sessions"
    (root / "--tmp-cell--").mkdir(parents=True)
    mine = root / "--tmp-cell--" / "2026-01-01T00-00-00-000Z_mine.jsonl"
    theirs = root / "--tmp-other--" / "2026-01-01T00-00-00-000Z_theirs.jsonl"
    theirs.parent.mkdir()
    mine.write_text(LOG.replace("/tmp/cell/tree", "/tmp/cell/tree"), encoding="utf-8")
    theirs.write_text(LOG.replace("/tmp/cell/tree", "/tmp/other/tree"), encoding="utf-8")
    monkeypatch.setattr(E, "SESSION_ROOT", root)
    empty = tmp_path / "empty-session-dir"
    assert E.session_logs(empty, tree="/tmp/cell/tree") == [mine]
    assert E.session_logs(empty, tree="/tmp/other/tree") == [theirs]
    assert E.read_usage(E.session_logs(empty, tree="/tmp/cell/tree"))["input"] == 1500
    assert E.session_logs(empty, tree="/tmp/cell/tree", since=time.time() + 60) == []


def test_runner_reads_the_reference_arm_s_usage_from_opencode_s_store(tmp_path):
    """opencode keeps its tokens in SQLite, keyed by the `--title` the runner
    gives the cell; a missing store, table or row is no usage, never a crash."""
    import sqlite3
    db = tmp_path / "opencode.db"
    con = sqlite3.connect(db)
    con.execute("create table session (id text, title text, model text, agent text,"
                "tokens_input integer, tokens_output integer, tokens_cache_write integer,"
                "tokens_cache_read integer, time_created integer)")
    con.execute("insert into session values ('s1', 'eval demo reference #1', "
                "'anthropic/claude-sonnet-5', 'orchestrator', 12000, 900, 400, 30000, 1)")
    con.execute("insert into session values ('s0', 'plain session', 'x', 'build', 1, 1, 1, 1, 0)")
    con.commit()
    con.close()
    got = E.opencode_usage("eval demo reference #1", db)
    assert got == {"model": "anthropic/claude-sonnet-5", "agent": "orchestrator",
                   "pools": {"input": 12000, "output": 900, "cache_write": 400,
                             "cache_read": 30000}}
    assert E.opencode_usage("nobody", db) == {}
    assert E.opencode_usage("x", tmp_path / "absent.db") == {}
    broken = tmp_path / "broken.db"
    broken.write_text("not a database", encoding="utf-8")
    assert E.opencode_usage("x", broken) == {}



def test_runner_dispatch_hands_each_item_its_own_text_and_keeps_it_outside_the_tree(tmp_path):
    """The per-item session is exactly `prompt.md`'s preamble plus that item, the
    stitched prompt is kept beside the tree (never inside it: it would be an
    out-of-scope file the agent did not write), and the two items run in their own
    declared models."""
    d = tmp_path / "split-task"
    d.mkdir()
    (d / "prompt.md").write_text(textwrap.dedent("""\
        Implement these two items of `dev/x/SPECS.md`, as written there:

        - [ ] **A1 · the first.** One change.
          touches: a.py
          depends: —
          model: claude-sonnet-5-5
          verify: true
        - [ ] **A2 · the second.** Another.
          touches: b.py
          depends: A1
          model: claude-opus-5-5
          verify: true
        """))
    t = E.Task(id="split-task", kind="coding", title="t", base="", reference=(),
               scope=("a.py", "b.py"), verify="true", arms=("dispatch",), dir=d,
               tree="empty")
    c = E.plan_cell(t, "dispatch", workdir=tmp_path / "wd", w=world(tmp_path))
    assert [(x.item, x.model) for x in c.commands] == [("A1", "claude-sonnet-5-5"),
                                                      ("A2", "claude-opus-5-5")]
    assert c.commands[0].argv[2].endswith("verify: true\n")
    assert "**A2 ·" not in c.commands[0].argv[2]
    assert c.commands[1].argv[2].startswith("Implement these two items")
    seen = []

    def spawn(argv, cwd, env, timeout=E.AGENT_TIMEOUT):
        seen.append((argv[2], argv[4], pathlib.Path(cwd)))
        return subprocess.CompletedProcess(list(argv), 0, "", "")

    row = E.run_cell(c, w=world(tmp_path), spawn=spawn)
    assert [m for _, m, _ in seen] == ["claude-bridge/claude-sonnet-5-5",
                                       "claude-bridge/claude-opus-5-5"]
    assert (c.sessions / "prompt-A1.txt").read_text() == seen[0][0]
    assert (c.sessions / "prompt-A2.txt").read_text() == seen[1][0]
    assert row["outside_scope"] == []          # the prompts are outside the tree
    assert row["usage"]["source"] == "" and "no session log found" in row["note"]
    assert row["items"] == [{"id": "A1", "model": "claude-sonnet-5-5", "wave": 1, "effort": "medium",
                             "source": "declared"},
                            {"id": "A2", "model": "claude-opus-5-5", "wave": 2,
                             "effort": "medium", "source": "declared"}]


@INSTANCE
def test_runner_dry_run_spawns_nothing(tmp_path, monkeypatch, capsys, tuning):
    """The item's own exit: fifty cells printed, no process, no Jev, no file."""
    def boom(*a, **k):
        raise AssertionError("the dry run must not spawn")
    monkeypatch.setattr(E.subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(E.jev, "ask", boom)
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path / "data"))
    out = tmp_path / "wd"
    code = E.main(["--run", "--tasks=all", "--dry-run", "--workdir", str(out)])
    assert code == 0
    printed = capsys.readouterr().out
    assert ("eval --run --dry-run: 50 cell(s) from 14 task(s); baseline 14, dispatch 14, "
            "bindings 5, jev 3, reference 14") in printed
    assert not out.exists()                                   # no tree, no session dir
    assert not (tmp_path / "data").exists()                    # no row appended
    assert printed.count("\n    cmd ") == 54    # 50 cells; dispatch runs one per item
    assert "PI_BINDINGS=1 pi -p" in printed
    assert "opencode run --agent orchestrator" in printed
    assert "(no process: `jev.ask` is called in-process)" in printed


@INSTANCE
def test_runner_dispatch_commands_are_one_per_item(demo, tmp_path, tuning):
    """The 54th command: dispatch's multi-item tasks carry one command per item,
    so the fifty cells are not fifty processes."""
    total = 0
    for t, arm in E.cells(E.load()):
        total += len(E.plan_cell(t, arm, workdir=tmp_path, w=world(tmp_path)).commands)
    assert total == 54
    assert len(E.plan_cell(task(STEP2), "dispatch", workdir=tmp_path,
                           w=world(tmp_path)).commands) == 3
    assert len(E.plan_cell(task("hermes-guard-h1h2"), "dispatch", workdir=tmp_path,
                           w=world(tmp_path)).commands) == 2


@INSTANCE
def test_runner_command_line_refuses_a_misused_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(E.subprocess, "run", lambda *a, **k: pytest.fail("spawned"))
    assert E.main(["--run", "--arms=bogus", "--dry-run", "--workdir", str(tmp_path)]) == 2
    assert "unknown arm(s): bogus" in capsys.readouterr().err
    assert E.main(["--run", "--tasks=nope", "--dry-run", "--workdir", str(tmp_path)]) == 2
    assert "no task 'nope'" in capsys.readouterr().err
    assert E.main(["--list", "--dry-run"]) == 2
    assert "--dry-run applies to --run" in capsys.readouterr().err
    with pytest.raises(SystemExit):                    # no mode at all is argparse's refusal
        E.main(["--dry-run"])


# --- the 2026-10-14 pilot's two findings ---------------------------------------

@INSTANCE
def test_runner_the_jev_step_runs_before_the_verifier(tmp_path, monkeypatch):
    """The pilot's bug: the jev arm has no argv, and its call (which WRITES the
    task's answer file) ran after the verifier, so every jev cell was judged on an
    empty tree. The answer file must exist when the verifier looks."""
    t = task(BATCH)
    c = E.plan_cell(t, "jev", workdir=tmp_path, w=world(tmp_path))
    assert c.commands and not c.commands[0].argv, "the jev arm has no process"
    seen = {}

    def fake_jev(cell, out=print):
        (cell.tree / t.answer).write_text("doc\tlabel\n", encoding="utf-8")
        return {"input": 1}, "jev-1.13.0", "stub"

    def fake_verify(task, tree, timeout=None):
        seen["answer_existed"] = (tree / task.answer).is_file()
        return 0, "stub"

    monkeypatch.setattr(E, "jev_run", fake_jev)
    monkeypatch.setattr(E, "verify", fake_verify)
    row = E.run_cell(c, keep=True)
    assert seen["answer_existed"] is True, "the verifier judged an empty tree"
    assert row["verifier"]["pass"] is True and row["usage"]["source"] == "jev-response"
    assert "ran after the verifier" not in row["note"]


@INSTANCE
def test_runner_an_arms_output_is_kept_and_a_reference_tail_reaches_the_row(tmp_path, monkeypatch):
    """The pilot's second gap: opencode's stdout was discarded on a zero exit, so a
    failed reference cell was unattributable. The output is kept, and the last line
    is in the row."""
    class Done:
        returncode = 0
        stdout = "thinking...\nI could not find the file, so I stopped.\n"
        stderr = ""

    monkeypatch.setattr(E, "verify", lambda *a, **k: (1, "score: cannot read answer.md"))
    c = E.plan_cell(task(REAL), "reference", workdir=tmp_path, w=world(tmp_path))
    # `spawn` is a parameter, not a module lookup: patch the seam the runner is
    # handed, or a real opencode runs (learned the hard way, 2026-10-14).
    row = E.run_cell(c, spawn=lambda *a, **k: Done(), keep=True)
    kept = c.sessions / "prompt.out"
    assert kept.read_text().startswith("thinking...")
    assert "last line: I could not find the file" in row["note"]
    assert row["verifier"]["pass"] is False


@INSTANCE
def test_runner_a_cell_that_moves_the_repository_under_test_is_flagged(tmp_path, monkeypatch):
    """The pilot's third finding (2026-10-14): the tree's AGENTS.md/CLAUDE.md are
    the real ones and name real paths, so the reference arm wrote its answer into
    THIS repository. Isolation keeps the future out of the cell; this keeps the
    cell out of the repository."""
    class Done:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    escapes = tmp_path / "escaped.txt"

    def spawn(argv, cwd, env, timeout=None):
        escapes.write_text("written by the arm\n")
        return Done()

    monkeypatch.setattr(E, "isolate", lambda *a, **k: ((), []))
    monkeypatch.setattr(E, "repo_state",
                        lambda r: ["?? escaped.txt"] if escapes.exists() else [])
    monkeypatch.setattr(E, "verify", lambda *a, **k: (0, "stub"))
    c = E.plan_cell(task(REAL), "reference", workdir=tmp_path, w=world(tmp_path))
    c.tree.mkdir(parents=True, exist_ok=True)
    row = E.run_cell(c, spawn=spawn, keep=True)
    assert row["repo_touched"] == ["?? escaped.txt"]
    assert "moved the repository under test" in row["note"]


@INSTANCE
def test_runner_a_clean_cell_reports_no_repository_change(tmp_path, monkeypatch):
    class Done:
        returncode = 0
        stdout = ""
        stderr = ""
    monkeypatch.setattr(E, "isolate", lambda *a, **k: ((), []))
    monkeypatch.setattr(E, "repo_state", lambda r: [])
    monkeypatch.setattr(E, "verify", lambda *a, **k: (0, "stub"))
    c = E.plan_cell(task(REAL), "reference", workdir=tmp_path, w=world(tmp_path))
    c.tree.mkdir(parents=True, exist_ok=True)
    row = E.run_cell(c, spawn=lambda *a, **k: Done(), keep=True)
    assert row["repo_touched"] == [] and "moved the repository" not in row["note"]


def test_runner_the_isolated_tree_carries_no_pointer_to_the_live_checkout(tmp_path, monkeypatch):
    """8f's first fix. The snapshot's AGENTS.md/CLAUDE.md/CONTEXT.md name real
    $HOME paths; an arm that follows them reads the CURRENT repository, which is
    the future the isolation hides (and, for a task keyed in this repo, the
    answer). Deleting them is a recorded trade-off: the cell's environment is
    slightly poorer than the run it replays."""
    dest = tmp_path / "tree"
    dest.mkdir()
    for name in (*E.POINTERS, "README.md"):
        (dest / name).write_text("see ~/06_SYSTEM/AGENTS.md\\n")
    gone = E.strip_pointers(dest)
    assert gone == list(E.POINTERS)
    assert sorted(p.name for p in dest.iterdir()) == ["README.md"]
    assert E.strip_pointers(dest) == [], "idempotent: a second call finds nothing"


def test_runner_every_cell_runs_under_the_mask_that_hides_the_future(tmp_path):
    """8f: the boundary is a property of the spawn seam, so no arm can forget it.
    The live checkout is read-only and the three paths that answer a task are
    emptied; everything else -- the harnesses in $HOME, the tree in /tmp -- is
    left alone."""
    argv = E.mask_argv(["pi", "-p", "hello", "--model", "x"], tmp_path, wrap="/usr/bin/bwrap")
    assert argv[:4] == ["/usr/bin/bwrap", "--dev-bind", "/", "/"]
    repo = str(E.roots.REPO)
    assert argv[4:6] == ["--ro-bind", repo]
    masked = [argv[i + 1] for i, a in enumerate(argv) if a == "--tmpfs"]
    assert masked == [str(p) for p in E.mask_paths()]
    assert masked == [str(E.git_dir()), f"{repo}/dev", f"{repo}/memory/journal"]
    ro = [argv[i + 1] for i, a in enumerate(argv) if a == "--ro-bind-try"]
    assert ro == [str(p) for p in E.readonly_paths()]
    assert any(p.endswith("pi-permission-system/config.json") for p in ro), \
        "the machine's compiled boundaries are read-only inside a cell"
    assert argv[-7:-2] == ["--chdir", str(tmp_path), "pi", "-p", "hello"]
    assert argv[-2:] == ["--model", "x"], "the arm's own argv is untouched"


def test_runner_without_bubblewrap_the_argv_is_unchanged_and_the_guard_still_holds(tmp_path):
    assert E.mask_argv(["pi", "-p", "x"], tmp_path, wrap="") == ["pi", "-p", "x"]


def test_runner_the_mask_finds_the_history_behind_a_worktree(tmp_path):
    """In a worktree `.git` is a pointer file, and bwrap cannot lay a tmpfs over a
    file: every cell failed to start. The history is the COMMON git dir, and that is
    what is masked; the pointer itself is bound to /dev/null."""
    main = tmp_path / "main" / ".git"
    (main / "worktrees" / "wt").mkdir(parents=True)
    (main / "worktrees" / "wt" / "commondir").write_text("../..\n")
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main / 'worktrees' / 'wt'}\n")
    assert E.git_dir(wt) == main.resolve()
    assert E.git_dir(tmp_path / "main") == main
    argv = E.mask_argv(["true"], tmp_path, repo=wt, wrap="/usr/bin/bwrap")
    i = argv.index("/dev/null")
    assert argv[i - 1:i + 2] == ["--ro-bind", "/dev/null", str(wt / ".git")]


@INSTANCE
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap is not installed")
def test_runner_the_mask_really_hides_the_task_set_and_refuses_a_write(tmp_path):
    """The behavioural half: not the argv but what a process finds. Cheap -- no
    model, one bubblewrap -- and it is the claim the reference arm's pilot rows
    failed on, so it is worth running for real."""
    script = ("ls %s | wc -l; ls %s | wc -l; "
              "test -x %s && echo executable; "
              "touch %s/canary 2>&1 | head -1")
    repo = E.roots.REPO
    argv = ["bash", "-c", script % (repo / "dev", E.git_dir(repo),
                                    repo / "engine/familiar", repo)]
    p = subprocess.run(E.mask_argv(argv, tmp_path), capture_output=True, text=True)
    out = p.stdout.strip().splitlines()
    assert out[0] == "0", "dev/ (the task set) is emptied"
    assert out[1] == "0", ".git/ (the future) is emptied"
    assert "executable" in out[2], "the harness is still reachable"
    assert "Read-only file system" in out[3], "the live checkout cannot be written"
    assert not (repo / "canary").exists()


@INSTANCE
@pytest.mark.skipif(not shutil.which("bwrap"), reason="bubblewrap is not installed")
def test_runner_the_mask_keeps_the_machine_s_boundaries_readable_and_unwritable(tmp_path):
    """A base-commit compiler inside a cell rewrote the pi policy twice. `-w` asks
    the kernel, so nothing is written even if the mask failed."""
    target = E.readonly_paths()[0]
    if not target.is_file():
        pytest.skip(f"{target} does not exist here")
    script = f"test -r {target} && echo readable; test -w {target} || echo read-only"
    p = subprocess.run(E.mask_argv(["bash", "-c", script], tmp_path),
                       capture_output=True, text=True)
    assert p.stdout.split() == ["readable", "read-only"], p.stderr


@INSTANCE
def test_runner_jev_run_records_each_documents_probabilities(tmp_path, monkeypatch, tuning):
    """The batch arm keeps more than the label: one jevlog row per document, so
    a cascade threshold can be fitted from the arm's own answers (2026-10-19)."""
    from orchestration import jevlog
    t = task("batch-journal-tags")
    docs, opts, _ = E.jev_plan(t)
    first = next(iter(opts))
    monkeypatch.setattr(E.jev, "ask", lambda s, q, **k: {
        "model": "jev-1.13.0", "usage": {"input_tokens": 5},
        "answers": {"answer": {"type": "choice", "choice": first, "confidence": 0.6,
                               "probabilities": {first: 0.6}}}})
    c = E.Cell(task=t, arm="jev", tree=tmp_path / "tree", sessions=tmp_path / "s", attempt=2)
    E.jev_run(c, out=lambda s: None)
    rows = jevlog.read()
    assert len(rows) == len(docs) and rows[0]["subject"] == f"{t.id}:jev-2#{docs[0][0]}"
    assert rows[0]["answers"]["answer"]["probabilities"] == {first: 0.6}
