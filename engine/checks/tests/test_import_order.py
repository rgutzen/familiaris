"""import_order: the R1j order holds on the real engine, and a breach is caught."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import import_order as io  # noqa: E402


def test_the_engine_holds_the_order():
    assert io.findings() == []


def _engine(tmp_path, pkg, src):
    for p in io.ORDER:
        (tmp_path / p).mkdir()
    (tmp_path / pkg / "m.py").write_text(src)
    return tmp_path


def test_an_import_to_the_right_is_caught(tmp_path):
    eng = _engine(tmp_path, "knowledge", "from consolidation import ranking\n")
    assert len(io.findings(eng)) == 1


def test_a_lazy_import_to_the_right_is_caught_too(tmp_path):
    eng = _engine(tmp_path, "context", "def f():\n    from consolidation import brief\n")
    assert len(io.findings(eng)) == 1


def test_imports_to_the_left_and_to_itself_are_fine(tmp_path):
    eng = _engine(tmp_path, "consolidation",
                  "from lib import git\nfrom knowledge import tree\n"
                  "from consolidation import ledger\nimport json\n")
    assert io.findings(eng) == []
