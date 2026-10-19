"""publish-drift, proved by moving a source rather than by reading a flag.

The bug this guards is a *stale* artifact, not a wrong one: the export is human
work (export, review the diff, push), so the failure that actually happens is that
the private tree keeps moving and nobody re-publishes. A check that cannot tell
"same sources" from "sources moved" is decoration, so each test moves a source and
demands the answer change.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import publish_drift as pd  # noqa: E402
from lib import roots  # noqa: E402  (`engine/` is on the path, above)


def _state(path: pathlib.Path, sources: list[str], digest: str) -> dict:
    payload = {"artifacts": {"demo": {"repo": "x/y", "source": sources,
                                      "hash": digest, "commit": "deadbeef",
                                      "published_at": "2026-09-29"}}}
    return payload


def _tree(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / "src/pkg").mkdir(parents=True)
    (tmp_path / "src/pkg/one.py").write_text("one\n")
    (tmp_path / "src/CLI").write_text("cli\n")
    return tmp_path


def test_unchanged_sources_are_in_sync(tmp_path):
    root = _tree(tmp_path)
    digest, missing = pd.source_hash(root, ["src/pkg", "src/CLI"])
    assert missing == 0
    findings = pd.check(root, _state(tmp_path, ["src/pkg", "src/CLI"], digest))
    assert [f["drift"] for f in findings] == [False]


def test_an_edited_file_is_drift(tmp_path):
    root = _tree(tmp_path)
    digest, _ = pd.source_hash(root, ["src/pkg", "src/CLI"])
    (root / "src/pkg/one.py").write_text("one, but changed\n")
    findings = pd.check(root, _state(tmp_path, ["src/pkg", "src/CLI"], digest))
    assert findings[0]["drift"] is True


def test_a_rename_is_drift_not_a_new_file(tmp_path):
    """Path names enter the hash: an export mapping that has to follow a rename
    is exactly the case a content-only hash would miss."""
    root = _tree(tmp_path)
    digest, _ = pd.source_hash(root, ["src/pkg"])
    (root / "src/pkg/one.py").rename(root / "src/pkg/two.py")
    findings = pd.check(root, _state(tmp_path, ["src/pkg"], digest))
    assert findings[0]["drift"] is True


def test_a_vanished_source_is_drift_and_is_counted(tmp_path):
    root = _tree(tmp_path)
    digest, _ = pd.source_hash(root, ["src/pkg", "src/CLI"])
    (root / "src/CLI").unlink()
    findings = pd.check(root, _state(tmp_path, ["src/pkg", "src/CLI"], digest))
    assert findings[0]["drift"] is True
    assert findings[0]["missing_paths"] == 1


def test_caches_are_not_sources(tmp_path):
    """A bytecode cache appearing under a source directory must not read as an
    edit; the private tree has 133 of those files and they change on every run."""
    root = _tree(tmp_path)
    digest, _ = pd.source_hash(root, ["src/pkg"])
    (root / "src/pkg/__pycache__").mkdir()
    (root / "src/pkg/__pycache__/one.cpython-314.pyc").write_bytes(b"\x00\x01")
    assert pd.source_hash(root, ["src/pkg"])[0] == digest


def test_record_stamps_the_current_hash(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps(_state(tmp_path, ["src/pkg"], "sha256:stale")))
    monkeypatch.setattr(pd, "REPO", root)
    pd.record("demo", "cafebabe", None, state_path=state)
    written = json.loads(state.read_text())["artifacts"]["demo"]
    assert written["commit"] == "cafebabe"
    assert written["hash"] == pd.source_hash(root, ["src/pkg"])[0]
    assert pd.check(root, json.loads(state.read_text()))[0]["drift"] is False


# ── a retired artifact, and the classification as a source list ──────────────

def test_a_retired_artifact_is_listed_and_not_measured(tmp_path):
    """`context-clew` is a pointer to the umbrella now (decision C, 2026-10-14),
    so its freshness is no longer a question this gate can answer. It is still
    NAMED in the report: a name that silently stops being checked is the drift
    this module exists to make visible, one level up, and it is exactly what a
    quiet deletion from `artifacts` would look like."""
    root = _tree(tmp_path)
    state = _state(tmp_path, ["src/pkg"], "sha256:stale")
    state["artifacts"]["demo"]["retired"] = "a pointer to the umbrella now"
    findings = pd.check(root, state)
    assert [f["artifact"] for f in findings] == ["demo"]
    assert findings[0]["retired"] == "a pointer to the umbrella now"
    assert "drift" not in findings[0]


def test_a_retirement_needs_a_reason_and_record_refuses_it(tmp_path, monkeypatch):
    """Two halves of one property: a retirement nobody explained is not a
    retirement, and `--record` on one would re-arm a gate that no longer has
    anything to measure."""
    state = _state(tmp_path, ["src/pkg"], "sha256:stale")
    state["artifacts"]["demo"]["retired"] = "gone"
    assert len(pd.retirement_findings(state)) == 1

    root = _tree(tmp_path)
    path = tmp_path / "state.json"
    state["artifacts"]["demo"]["retired"] = "a pointer to the umbrella now"
    path.write_text(json.dumps(state))
    monkeypatch.setattr(pd, "REPO", root)
    with pytest.raises(SystemExit):
        pd.record("demo", "cafebabe", None, state_path=path)


def test_the_classification_sentinel_resolves_to_what_travels():
    """`source: classification` is the umbrella's own list, and it is resolved
    rather than copied so it cannot go stale. Two properties: the classification
    FILE is in the list -- a reclassification changes what is published, so it
    is a source too -- and every path beside it is one the export writes."""
    if not roots.instance_here():
        pytest.skip("the classification lives under `dev/`, which never travels")
    import publish_audit as pa
    got = pd.sources(pd.load_state()["artifacts"]["familiaris"])
    assert pa.CLASSIFICATION.relative_to(pd.REPO).as_posix() in got
    rules = pa.rules(pa.load())
    for rel in got:
        rule, _why = pa.classify(rel, rules)
        assert rule is not None, rel
        assert rule.cls != "omit" or rel.endswith("publish.yaml"), \
            f"{rel} is omitted and yet hashed as a source"
