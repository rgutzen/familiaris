"""The pi-spawn gate: it finds a pi argv outside the module, and only there."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pi_spawn  # noqa: E402


def _tree(tmp_path, files: dict) -> pathlib.Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_a_pi_argv_outside_the_module_is_a_finding(tmp_path):
    eng = _tree(tmp_path, {"orchestration/x.py": 'cmd = ["pi", "-p", task]\n',
                           "context/y.py": "argv = ('pi', '--list-models')\n"})
    got = {p.name for p, _, _ in pi_spawn.findings(eng, eng / "harness/pi_call.py")}
    assert got == {"x.py", "y.py"}


def test_the_module_tests_comments_and_marked_lines_are_exempt(tmp_path):
    eng = _tree(tmp_path, {
        "harness/pi_call.py": 'out = ["pi", "-p", task]\n',
        "orchestration/tests/test_x.py": 'assert argv[:2] == ["pi", "-p"]\n',
        "orchestration/c.py": '# an old ["pi", "-p"] spelling, in prose\n',
        "orchestration/m.py": 'cmd = ["pi", "-v"]  # pi-spawn: the version probe needs no guard\n',
        "orchestration/n.py": 'cmd = ["pi-agent", role]\nx = ["pip", "install"]\n',
        "context/r.py": 'return Result("pi", "failed", "-", cwd)\n',
    })
    assert pi_spawn.findings(eng, eng / "harness/pi_call.py") == []


def test_an_unmarked_reason_is_not_an_exemption(tmp_path):
    eng = _tree(tmp_path, {"a.py": 'cmd = ["pi", "-p"]  # pi-spawn:\n'})
    assert len(pi_spawn.findings(eng, eng / "harness/pi_call.py")) == 1


def test_the_live_engine_is_clean():
    assert pi_spawn.findings() == []
