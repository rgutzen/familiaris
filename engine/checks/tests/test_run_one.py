"""`--run` takes a check id as well as a gate name (2c's verify line names one).

Proved with stand-in checks: the claim is about which checks run, so it is
visible in which fake commands leave a mark.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import checks  # noqa: E402


@pytest.fixture
def marks(tmp_path, monkeypatch):
    def fake(name, gates):
        script = f"import pathlib; pathlib.Path({str(tmp_path / name)!r}).touch()"
        return checks.Check(name, name, (sys.executable, "-c", script), frozenset(gates))
    monkeypatch.setattr(checks, "CHECKS", (
        fake("one", {checks.GATE_PRE_COMMIT}), fake("two", {checks.GATE_PRE_COMMIT})))
    return lambda: sorted(p.name for p in tmp_path.iterdir())


def test_check_id_runs_only_that_check(marks):
    assert checks.main(["--run", "two"]) == 0
    assert marks() == ["two"]


def test_gate_still_runs_every_check(marks):
    assert checks.main(["--run", checks.GATE_PRE_COMMIT]) == 0
    assert marks() == ["one", "two"]


def test_unknown_name_fails_listing_gates_and_ids(marks, capsys):
    with pytest.raises(SystemExit) as e:
        checks.main(["--run", "nope"])
    assert e.value.code != 0
    err = capsys.readouterr().err
    assert "pre-commit" in err and "one" in err and "two" in err
    assert marks() == []


def test_specs_dispatchable_is_registered():
    (c,) = [c for c in checks.CHECKS if c.id == "specs-dispatchable"]
    assert checks.GATE_PRE_COMMIT in c.gates and c.command[-1] == "--gate"
