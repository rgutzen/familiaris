"""`familiar checks updates` reads three sources and applies nothing."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cli import updates  # noqa: E402


def _stub(monkeypatch, mise="{}", npm="{}"):
    calls = []

    def run(cmd, cwd=None):
        calls.append(cmd)
        if cmd[0] == "mise":
            return mise
        if cmd[0] == "npm":
            return npm
        raise AssertionError(f"unexpected command {cmd}")
    monkeypatch.setattr(updates, "_run", run)
    monkeypatch.setattr(updates, "PI_DIR", pathlib.Path(__file__).parent)
    monkeypatch.setattr(updates, "skill_upstreams", lambda: {})
    return calls


def test_nothing_behind_exits_zero_even_with_check(monkeypatch, capsys):
    _stub(monkeypatch)
    assert updates.main(["--check"]) == 0
    assert "0 behind" in capsys.readouterr().out


def test_a_harness_behind_says_what_to_re_verify(monkeypatch, capsys):
    _stub(monkeypatch, mise=json.dumps({"claude": {"current": "1", "latest": "2"}}))
    assert updates.main(["--check"]) == 3
    out = capsys.readouterr().out
    assert "mise upgrade claude" in out and "context route --check" in out


def test_report_without_check_is_not_a_failure(monkeypatch):
    _stub(monkeypatch, npm=json.dumps({"p": {"current": "1", "latest": "2"}}))
    assert updates.main([]) == 0


def test_an_unreadable_surface_is_exit_two_not_zero(monkeypatch, capsys):
    def boom(cmd, cwd=None):
        raise updates.Unreadable("offline")
    monkeypatch.setattr(updates, "_run", boom)
    monkeypatch.setattr(updates, "skill_upstreams", lambda: {})
    assert updates.main(["--check"]) == 2


def test_it_only_ever_runs_read_commands(monkeypatch):
    calls = _stub(monkeypatch, mise=json.dumps({"pi": {"current": "1", "latest": "2"}}))
    updates.main(["--check"])
    assert all(c[:2] in (["mise", "outdated"], ["npm", "outdated"]) for c in calls)


def test_a_pin_the_remote_head_matches_is_not_behind(monkeypatch):
    clone = pathlib.Path("/x/up")
    monkeypatch.setattr(updates, "skill_upstreams",
                        lambda: {clone: {"pins": {"abc1234"}, "skills": ["s"]}})
    monkeypatch.setattr(updates, "_run", lambda cmd, cwd=None: "abc1234ffff\tHEAD\n")
    assert updates.skills() == []
    monkeypatch.setattr(updates, "_run", lambda cmd, cwd=None: "def5678ffff\tHEAD\n")
    (row,) = updates.skills()
    assert row["name"] == "up" and row["latest"] == "def5678" and row["skills"] == 1
