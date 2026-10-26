"""Stage 6c: the binding proposals reach the pass's brief and nothing is applied.

WHAT IS PINNED HERE, AND NOT IN THE ARITHMETIC'S TESTS.
  the record   The stage calls `bindings.evidence`/`proposal_for` and records what
               comes back with `ctx.propose` -- kind `binding`, target the binding's
               `on`, `target_kind` `opaque`. A pass whose proposals cannot be read
               by `queue`/`report` is the silent stage this item exists to avoid.
  the silence  A binding left alone is a NOTE. "No proposal" is the answer a reader
               most needs to see, and a stage that quietly proposed nothing would
               look identical to one that never ran.
  no writes    A proposal-only stage writes no file: `bindings.yaml` is the file a
               proposal is FOR the user to change. The stub `Pass` has no `act` to
               call, so an accidental write would raise rather than pass unnoticed.
  a young pass Nothing in the logs is not a failure: the stage says so and returns
               True, because a pass that aborts on a fresh machine reports nothing
               else either.
"""
import json

from consolidation import pass_ctx
from consolidation.stages import bindings as stage


class _Ctx:
    """Enough of a Pass for a proposal-only stage: propose, note, and log."""

    def __init__(self):
        self.dry_run = False
        self.flags = frozenset()
        self.proposals, self.notes = [], []

    propose = pass_ctx.Pass.propose
    note = pass_ctx.Pass.note

    def log(self, msg):
        pass


def logs(tmp_path, labels, delegations, monkeypatch):
    data = tmp_path / "pazras-data"
    data.mkdir(exist_ok=True)
    (data / "labels.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in labels), encoding="utf-8")
    (data / "delegations.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in delegations), encoding="utf-8")
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(data))
    return data


def test_bindings_the_stage_proposes_a_failing_binding_with_its_class_evidence(tmp_path,
                                                                             monkeypatch):
    """code-review runs as `bash` (class batch): haiku failing 1/4 there and
    deepseek-flash at 4/4 there is a proposal; edit labels say nothing about it."""
    logs(tmp_path,
         [{"ran_model": "claude-bridge/claude-haiku-5-5", "passed": i == 0, "verdict": "own",
           "attempt": 1, "class": "batch"} for i in range(4)]
         + [{"ran_model": "deepseek/deepseek-flash", "passed": True, "verdict": "own",
             "attempt": 1, "class": "batch"}] * 4
         + [{"ran_model": "deepseek/deepseek-flash", "passed": True, "verdict": "own",
             "attempt": 1, "class": "edit"}] * 9,
         [], monkeypatch)
    ctx = _Ctx()
    assert stage.run(ctx) is True
    [p] = [p for p in ctx.proposals if p.target == "skill:code-review"]
    assert (p.stage, p.kind, p.target_kind) == ("6c", "binding", "opaque")
    assert p.what.startswith("model claude-haiku-5-5 -> deepseek-flash (1/4 in batch against 4/4")
    assert "class batch only (14h)" in p.why and "Not applied" in p.why
    assert any("`model: route`" in n.text for n in ctx.notes)


def test_bindings_a_binding_left_alone_is_a_note_and_nothing_is_written(tmp_path,
                                                                        monkeypatch):
    # The labels carry no class (pre-14f rows with no probe), so no binding's class
    # has a record: nothing is proposed, and every binding still says why.
    data = logs(tmp_path,
                [{"ran_model": "deepseek/deepseek-flash", "passed": True, "verdict": "own",
                  "attempt": 1}] * 4
                + [{"ran_model": "claude-bridge/claude-haiku-5-5", "passed": True,
                    "verdict": "own", "attempt": 1}] * 4,
                [], monkeypatch)
    before = (data / "labels.jsonl").read_text()
    ctx = _Ctx()
    assert stage.run(ctx) is True
    assert [p for p in ctx.proposals if p.kind == "binding"] == [], \
        "no class has a record, so nothing is proposed"
    assert sum("nothing to propose" in n.text or "no proposal" in n.text
               for n in ctx.notes) == len(stage.bindings.load()["bindings"]), \
        "every binding says why it was left alone"
    assert (data / "labels.jsonl").read_text() == before


def test_bindings_a_pass_with_no_logs_says_so_and_returns(tmp_path, monkeypatch):
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(tmp_path / "nothing-here"))
    ctx = _Ctx()
    assert stage.run(ctx) is True
    assert ctx.proposals == [] and len(ctx.notes) == 1
    assert "no 3f labels and no 5c delegations yet" in ctx.notes[0].text


def test_bindings_a_malformed_log_line_does_not_skip_the_night(tmp_path, monkeypatch):
    data = logs(tmp_path,
                [{"ran_model": "deepseek/deepseek-flash", "passed": True, "verdict": "own",
                  "attempt": 1}] * 4,
                [], monkeypatch)
    with (data / "labels.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"ran_model": "trunc\n')
    ctx = _Ctx()
    assert stage.run(ctx) is True
    assert any("binding(s) left as they are" in n.text for n in ctx.notes)
