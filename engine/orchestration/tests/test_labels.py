"""Per-item outcome labels (3f, option C): the eval seed, the verify wrapper, the bar."""
import json
import pathlib

from orchestration import labels as L

ROW = {"ts": "t", "task": "orch-step3", "kind": "coding", "arm": "dispatch", "attempt": 2,
       "ran_model": "x/sonnet", "effort": "medium", "usage": {"input": 10, "output": 5},
       "verifier": {"pass": True},
       "items": [{"id": "3a", "model": "claude-sonnet-5-5", "source": "declared", "effort": "medium"},
                 {"id": "3b", "model": "deepseek-flash", "source": "default (edit tier 1)"}]}
ONE = dict(ROW, task="orch-2b", attempt=1, items=[ROW["items"][0]])


def test_labels_eval_seed_is_per_item_and_marks_a_shared_verifier():
    got = L.from_eval([ROW, ONE, dict(ROW, kind="batch"), dict(ROW, arm="reference")])
    assert [(r["item"], r["verdict"]) for r in got] == [("3a", "shared"), ("3b", "shared"), ("3a", "own")]
    assert got[0]["declared"] == "claude-sonnet-5-5" and got[1]["declared"] is None
    assert got[1]["ran_model"] == "deepseek-flash", "a multi-item dispatch cell ran each item's own model"
    assert got[0]["attempt"] == 1 and got[0]["rerun"] == 2, "a rerun is not a retry"
    assert got[2]["usage"]["frontier"] == 15 and got[0]["usage"]["frontier"] == 0


def test_labels_seed_runs_once(tmp_path):
    rows = tmp_path / "rows.jsonl"
    rows.write_text(json.dumps(ONE) + "\n")
    out = tmp_path / "labels.jsonl"
    assert L.seed(rows, out) == 1 and L.seed(rows, out) == 0
    assert len(L.read(out)) == 1


def test_labels_seed_appends_a_cell_it_has_not_labelled(tmp_path):
    """A model arm's row must reach the posterior, or measuring a new model writes
    rows nothing reads (changed 2026-10-23: one-shot became incremental)."""
    rows = tmp_path / "rows.jsonl"
    rows.write_text(json.dumps(ONE) + "\n")
    out = tmp_path / "labels.jsonl"
    assert L.seed(rows, out) == 1
    model_row = dict(ONE, ts="t2", arm="model", ran_model="mistral/zai-glm-5-3-flash",
                     items=[{"id": "orch-2b", "model": "zai-glm-5-3-flash",
                             "source": "override", "effort": "medium"}])
    rows.write_text(json.dumps(ONE) + "\n" + json.dumps(model_row) + "\n")
    assert L.seed(rows, out) == 1, "the labelled row is not written twice"
    got = L.read(out)
    assert len(got) == 2
    assert got[1]["ran_model"] == "mistral/zai-glm-5-3-flash"
    assert got[1]["verdict"] == "own" and got[1]["specs"] == "eval:orch-2b:model"


SPECS = """- [ ] **9z · a thing.** text
  model: claude-sonnet-5-5
  verify: true
- [ ] **9y · manual.** text
  verify: manual: look at it
"""


class P:
    def __init__(self, rc):
        self.returncode, self.stdout, self.stderr = rc, "ok\n", ""


def test_labels_verify_counts_attempts_and_refuses_a_manual_verify(tmp_path):
    f = tmp_path / "SPECS.md"
    f.write_text(SPECS)
    out = tmp_path / "labels.jsonl"
    rcs = iter([1, 0])
    run = lambda *a, **k: P(next(rcs))
    kw = dict(path=out, ran="m/x", session=str(tmp_path / "none.jsonl"), cwd=tmp_path, run=run, out=lambda s: None)
    assert L.verify(f, "9z", **kw) == 1
    assert L.verify(f, "9z", **kw) == 0
    a, b = L.read(out)
    assert (a["attempt"], a["passed"], a["first_pass"]) == (1, False, False)
    assert (b["attempt"], b["passed"], b["first_pass"]) == (2, True, False)
    assert a["declared"] == "claude-sonnet-5-5" and a["specs"] == "SPECS.md"
    assert L.verify(f, "9y", **kw) == 2 and L.verify(f, "nope", **kw) == 2
    assert len(L.read(out)) == 2, "a refused verify writes no label"


def test_labels_report_holds_thresholds_until_thirty_own_items():
    rows = [L.label(source="verify", specs_path="S", item=str(i), declared=None, ran_model="m",
                    effort="", usage={}, attempt=1, passed=True, verdict="own") for i in range(29)]
    assert L.report(rows, out=lambda s: None)["met"] is False
    rows.append(dict(rows[0], item="29"))
    assert L.report(rows, out=lambda s: None)["met"] is True
