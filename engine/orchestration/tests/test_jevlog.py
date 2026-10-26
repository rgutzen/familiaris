"""jevlog: every Jev answer is kept with its probabilities, and 3f's labels join
the item's newest dispatch answers (the shadow-mode record, 2026-10-19)."""
from orchestration import bindings, dispatch, jevlog, labels as L

RESP = {"model": "jev-1.13.0",
        "answers": {"q": {"type": "choice", "choice": "a", "confidence": 0.7,
                          "probabilities": {"a": 0.7, "b": 0.3}}}}


def test_jevlog_keeps_the_answer_map_verbatim_and_latest_picks_the_newest(tmp_path):
    log = tmp_path / "j.jsonl"
    jevlog.record("dispatch", "S.md#1a", "h1", RESP, log)
    jevlog.record("dispatch", "S.md#1a", "h2", dict(RESP, model="jev-2"), log)
    jevlog.record("pair", "S.md#1a+1b", "h3", RESP, log)
    rows = jevlog.read(log)
    assert rows[0]["answers"]["q"]["probabilities"] == {"a": 0.7, "b": 0.3}
    assert jevlog.latest("dispatch", "S.md#1a", log)["question_hash"] == "h2"
    assert jevlog.latest("route", "S.md#1a", log) is None


def test_jevlog_an_unwritable_log_never_fails_the_caller(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    jevlog.record("route", "x", "h", RESP, blocker / "sub" / "j.jsonl")   # no raise


def test_jevlog_dispatch_records_one_row_per_probed_item(tmp_path, monkeypatch, capsys):
    from test_dispatch import ITEMS, stub
    f = tmp_path / "SPECS.md"
    f.write_text(ITEMS)
    stub(monkeypatch)
    assert dispatch.main([str(f)]) == 0
    capsys.readouterr()
    rows = [r for r in jevlog.read() if r["source"] == "dispatch"]
    assert [r["subject"] for r in rows] == [f"{f}#1a"]
    assert rows[0]["question_hash"] == dispatch.probes_hash(dispatch.load_config(
        dispatch.models.load_capabilities())["probes"])
    assert rows[0]["answers"]["open_decision"]["type"] == "noul"


def test_jevlog_a_route_is_recorded_whatever_its_threshold_decides(monkeypatch):
    from test_bindings import jev_answers, resolve, table
    jev_answers(monkeypatch, "lookup", 0.5)
    resolve(table(), "tool:explore", "find X")
    rows = jevlog.read()
    assert [(r["source"], r["subject"]) for r in rows] == [("route", "tool:explore")]


def test_labels_verify_joins_the_items_newest_probe_answers(tmp_path):
    f = tmp_path / "SPECS.md"
    f.write_text("- [ ] **9z · a thing.** text\n  model: claude-sonnet-5-5\n  verify: true\n")
    log = tmp_path / "j.jsonl"
    jevlog.record("dispatch", "SPECS.md#9z", "h1", RESP, log)
    out = tmp_path / "labels.jsonl"

    class P:
        returncode, stdout, stderr = 0, "", ""
    kw = dict(path=out, ran="m/x", session=str(tmp_path / "none"), cwd=tmp_path,
              run=lambda *a, **k: P(), out=lambda s: None, answers_log=log)
    assert L.verify(f, "9z", **kw) == 0
    (row,) = L.read(out)
    assert row["probes"]["question_hash"] == "h1"
    assert row["probes"]["answers"]["q"]["confidence"] == 0.7
    f2 = tmp_path / "S2.md"
    f2.write_text(f.read_text())
    L.verify(f2, "9z", **kw)
    assert L.read(out)[1]["probes"] is None, "an unprobed item says so"
