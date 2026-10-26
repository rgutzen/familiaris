"""The reader's calibration (12c): one task, one model id, three numbers -- the
verified-quote rate, the wall clock and the dollars.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  the score      A line counts only when the checker verifies its quote AND the
                 line carries the asked fact. The three ways to fail are pinned
                 separately: a wrong fact at a valid `path:line` (verified, not
                 correct), a quote that is not at the line named (unverified), and
                 no answer at all. Collapsing them would let a model that quotes
                 its own reasoning pass.
  the key        Every key on the real task appears exactly once across the two
                 records the prompt names, and the prompt asks every id. A record
                 edited until a key appears twice makes a question ambiguous, and
                 the suite says so instead of the score quietly drifting.
  the run        A spawned child is faked, so the row's seconds, dollars and
                 verdicts are read from the child's own log and the answer rather
                 than from anything the calibration believes.
  the key file   A child that reads `questions.yaml` scores what it looked up, not
                 what it read, so the row records it (`key_read`) and the run warns.

No test spawns pi and none reads the machine's real calibration log.
"""
import json
import pathlib

import pytest

from lib import _miniyaml
from lib import roots
from orchestration import eval as E

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="the calibration task and its graded tiers are files under "
           "`dev/orchestration/tasks/`, which the classification omits with "
           "`dev/`")

TASK = roots.DEV / "orchestration" / "tasks" / E.CALIBRATION
ANSWER_OK = 'Q1 doc.md:2 "the second line carries it"'


def task_dir(tmp_path, keys=(("Q1", "second line"), ("Q2", "third line"))):
    """A calibration task directory: a two-question prompt, a key, and a doc."""
    d = tmp_path / "task"
    d.mkdir()
    (d / "doc.md").write_text("# doc\n\nthe second line carries it\n"
                              "the third line carries that\n", encoding="utf-8")
    (d / "prompt.md").write_text("Answer from doc.md.\n\n"
                                 + "\n".join(f"{q} what?" for q, _k in keys) + "\n",
                                 encoding="utf-8")
    (d / "questions.yaml").write_text(_miniyaml_text(keys), encoding="utf-8")
    return d


def _miniyaml_text(keys):
    out = ["questions:"]
    for q, k in keys:
        out.append(f"  - id: {q}")
        out.append(f'    key: "{k}"')
    return "\n".join(out) + "\n"


# --- the score ---------------------------------------------------------------

def test_calibration_a_line_counts_only_if_the_quote_verifies(tmp_path):
    d = task_dir(tmp_path)
    _prompt, key, _docs = E.load_calibration(d)
    s = E.score(ANSWER_OK, d, key)
    assert (s["verified"], s["correct"], s["total"]) == (1, 1, 2)
    assert s["unverified"] == ["Q2"], "no answer at all is an unverified question"


def test_calibration_a_verified_quote_of_the_wrong_fact_is_not_a_hit(tmp_path):
    d = task_dir(tmp_path)
    _prompt, key, _docs = E.load_calibration(d)
    wrong = ('Q1 doc.md:2 "the second line carries it"\n'
             'Q2 doc.md:2 "the second line carries it"')     # right lines, wrong fact
    s = E.score(wrong, d, key)
    assert (s["verified"], s["correct"]) == (2, 1)
    assert s["misquoted"] == ["Q2"] and s["unverified"] == []


def test_calibration_a_quote_that_is_not_at_the_line_named_fails(tmp_path):
    d = task_dir(tmp_path)
    _prompt, key, _docs = E.load_calibration(d)
    s = E.score('Q1 doc.md:3 "the second line carries it"\n'
                'Q2 doc.md:99 "the third line carries that"', d, key)
    assert s["verified"] == 1 and s["correct"] == 1, "line 3 is within +-2 of line 2"
    assert s["unverified"] == ["Q2"], "line 99 is not"


def test_calibration_a_prompt_that_does_not_ask_a_question_is_refused(tmp_path):
    d = task_dir(tmp_path)
    _prompt, key, _docs = E.load_calibration(d)
    assert E.asked("Q1 what?", key) == ["Q2"]
    assert E.asked("Q1 and Q2, and not Q10", key) == []


def test_calibration_an_answer_that_reads_a_second_line_still_scores(tmp_path):
    d = task_dir(tmp_path)
    _prompt, key, _docs = E.load_calibration(d)
    s = E.score("Here is my answer.\n" + ANSWER_OK + "\nHope that helps.", d, key)
    assert s["verified"] == 1, "prose around the eight lines is not a failure"


# --- the real task -----------------------------------------------------------

@INSTANCE
def test_calibration_the_task_asks_every_id_and_keys_each_fact_once():
    prompt, key, docs = E.load_calibration(TASK)
    assert E.asked(prompt, key) == []
    assert len(docs) == 2 and all((roots.REPO / x).is_file() for x in docs)
    text = "\n".join((roots.REPO / x).read_text(encoding="utf-8") for x in docs)
    twice = [k.qid for k in key if text.count(k.key) != 1]
    assert not twice, f"a key is not unique in the records: {twice}"


@INSTANCE
def test_calibration_the_key_file_is_not_named_in_the_prompt():
    prompt, _key, _docs = E.load_calibration(TASK)
    assert "questions.yaml" not in prompt, "the prompt must not point at the key"


# 14i: the graded tiers. Every calibration task under tasks/ is held to the same
# contract: every id asked, every key once across its docs, no key holding a
# double quote (the answer line quotes in double quotes), no prompt naming its key.
GRADED = sorted(p.parent for p in (roots.DEV / "orchestration" / "tasks").glob("*/questions.yaml"))


@INSTANCE
def test_calibration_there_are_the_three_graded_tiers_and_the_first_task():
    assert [d.name for d in GRADED] == ["read-code-lookup", "read-large-context",
                                       "read-paraphrase", "read-superseded"]


@pytest.mark.parametrize("task", GRADED, ids=lambda d: d.name)
def test_calibration_every_graded_task_keys_each_fact_once(task):
    prompt, key, docs = E.load_calibration(task)
    assert E.asked(prompt, key) == []
    assert "questions.yaml" not in prompt
    assert docs and all((roots.REPO / x).is_file() for x in docs)
    text = "\n".join((roots.REPO / x).read_text(encoding="utf-8") for x in docs)
    twice = [k.qid for k in key if text.count(k.key) != 1]
    assert not twice, f"a key is not unique in the docs: {twice}"
    assert not [k.qid for k in key if '"' in k.key], "a key holding a double quote"


# --- the run -----------------------------------------------------------------

def child_log(path, answer, calls=()):
    rows = [{"type": "model_change", "provider": "deepseek", "modelId": "deepseek-flash"},
            {"type": "message", "message": {"role": "assistant", "content": [
                {"type": "toolCall", "name": "read", "arguments": a} for a in calls],
                "usage": {"input": 1000, "output": 100, "cacheRead": 0, "cacheWrite": 0}}},
            {"type": "message", "message": {"role": "assistant", "content": [
                {"type": "text", "text": answer}],
                "usage": {"input": 500, "output": 200, "cacheRead": 1000,
                          "cacheWrite": 0}}}]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.fixture
def fake_agent(monkeypatch, tmp_path, capsys):
    """A spawned `pi-agent`: it writes a child log, prints the join mark, and
    returns the answer the test asked for."""
    state = {"answer": ANSWER_OK + '\nQ2 doc.md:4 "the third line carries that"',
             "code": 0, "calls": ()}

    class Done:
        def __init__(self, code, out, err):
            self.returncode, self.stdout, self.stderr = code, out, err

    def run(argv, **kw):
        assert "--no-log" in argv, "a calibration attempt must not write a delegation line"
        log = child_log(tmp_path / "sessions/pi-agent/2026_c.jsonl", state["answer"],
                        state["calls"])
        return Done(state["code"], state["answer"],
                    f"pi-agent: delegation role=explore session={log}\n")

    monkeypatch.setattr(E.subprocess, "run", run)
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path / "data"))
    return state


def test_calibration_one_attempt_records_the_three_numbers(fake_agent, tmp_path, capsys):
    d = task_dir(tmp_path)
    assert E.calibrate(d, "deepseek-flash", "low", 1, repo=d) == 0
    out = capsys.readouterr().out
    assert "2 question(s)" in out and "model deepseek-flash at low, 1 attempt(s)" in out
    assert "     1  2/2" in out, "the table names the attempt's verified count"
    [row] = E.calibration_rows()
    assert (row["verified"], row["correct"], row["total"]) == (2, 2, 2)
    assert row["usd"] > 0 and row["seconds"] >= 0
    assert row["exit"] == 0 and row["key_read"] is False
    assert row["model"] == "deepseek-flash" and row["effort"] == "low"


def test_calibration_reading_the_key_file_is_recorded(fake_agent, tmp_path, capsys):
    d = task_dir(tmp_path)
    fake_agent["calls"] = ({"path": str(d / "questions.yaml")},)
    assert E.calibrate(d, "deepseek-flash", "", 1, repo=d) == 0
    [row] = E.calibration_rows()
    assert row["key_read"] is True
    captured = capsys.readouterr()
    assert "READ THE KEY" in captured.out
    assert "not a reading score" in captured.err


def test_calibration_a_failed_child_is_a_row_and_an_exit_1(fake_agent, tmp_path):
    d = task_dir(tmp_path)
    fake_agent["code"] = 3
    assert E.calibrate(d, "no-such-model", "", 1, repo=d) == 1
    [row] = E.calibration_rows()
    assert row["exit"] == 3


def test_calibration_a_prompt_missing_a_question_runs_nothing(fake_agent, tmp_path):
    d = task_dir(tmp_path)
    (d / "prompt.md").write_text("Answer from doc.md.\n\nQ1 what?\n", encoding="utf-8")
    assert E.calibrate(d, "deepseek-flash", "", 1, repo=d) == 2
    assert E.calibration_rows() == []


def test_calibration_the_cli_mode_needs_a_model(tmp_path, capsys):
    assert E.main(["--calibrate", "--tasks-dir", str(tmp_path)]) == 2
    assert "--model" in capsys.readouterr().err
