"""pi-agent resolves a role's catalogue id through the profile (item 2k).

No pi is spawned and nothing touches the network: `subprocess.run` (which
`harness/pi_call` calls) is replaced by
a function that fails the test, so "exit 3 without spawning" is checked, not assumed.
`pi-agent` has no `.py` suffix, so it is loaded through a SourceFileLoader.
"""
import importlib.machinery
import importlib.util
import pathlib

import pytest

PATH = pathlib.Path(__file__).resolve().parents[1] / "pi-agent"


@pytest.fixture
def pi_agent(monkeypatch):
    loader = importlib.machinery.SourceFileLoader("pi_agent_under_test", str(PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    monkeypatch.delenv("PI_PROFILE", raising=False)
    return mod


def _agent(mod, name="explore"):
    """The role, on its DECLARED path: the shipped explore.md says `model: class`
    since 2026-10-22 (14g), so these tests pin the declaration they exercise."""
    a = next(a for a in mod.load_all() if a.name == name)
    if name == "explore":
        a.model = "deepseek-flash"
    return a


def test_the_shipped_explore_role_routes_per_call(pi_agent):
    """Ruled 2026-10-22: the class tier decides each `explore` call (14g)."""
    a = next(a for a in pi_agent.load_all() if a.name == "explore")
    assert a.model == pi_agent.CLASS and a.task_class == "read"


def _capture(monkeypatch, mod):
    calls = []

    class Done:
        returncode = 0
        stdout = stderr = None

    monkeypatch.setattr(mod.pi_call.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)) or Done())
    return calls


def _model_arg(cmd):
    return cmd[cmd.index("--model") + 1]


def test_the_roles_name_catalogue_ids(pi_agent):
    assert "/" not in _agent(pi_agent, "explore").model
    assert "/" not in _agent(pi_agent, "bash").model


def test_private_resolves_a_local_role_to_ollama(pi_agent, monkeypatch):
    """The bash worker is the roster's local definition; `explore` is not any more
    (5a: the B roles name `deepseek-flash`, the cheap cloud default)."""
    calls = _capture(monkeypatch, pi_agent)
    a = _agent(pi_agent, "bash")
    assert pi_agent.run(a, "t", ".", None, None, None) == 0
    assert _model_arg(calls[0][0]) == f"ollama/{a.model}"


def test_private_resolves_explore_to_the_cheap_cloud_default(pi_agent, monkeypatch):
    """5a, 2026-10-14: `explore` moved off the local 30B to the catalogue's
    cheap cloud default, and still resolves through the profile."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    calls = _capture(monkeypatch, pi_agent)
    assert pi_agent.run(_agent(pi_agent), "t", ".", None, None, None) == 0
    assert _model_arg(calls[0][0]) == "deepseek/deepseek-flash"


def test_the_child_inherits_profile_and_claude_account(pi_agent, monkeypatch):
    monkeypatch.setenv("PI_PROFILE", "private")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/x/acct")
    calls = _capture(monkeypatch, pi_agent)
    pi_agent.run(_agent(pi_agent), "t", ".", None, None, None)
    env = calls[0][1]["env"]
    assert env["PI_PROFILE"] == "private" and env["CLAUDE_CONFIG_DIR"] == "/x/acct"


def test_an_unavailable_model_exits_3_without_spawning(pi_agent, monkeypatch, capsys):
    monkeypatch.setenv("PI_PROFILE", "work")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY_WORK", raising=False)   # the key the work profile reads
    monkeypatch.setattr(pi_agent.pi_call.subprocess, "run",
                        lambda *a, **k: pytest.fail("pi was spawned"))
    rc = pi_agent.run(_agent(pi_agent), "t", ".", None, "deepseek-flash", None)
    err = capsys.readouterr().err
    assert rc == 3
    assert "pi-agent: explore: deepseek-flash unavailable in profile work:" in err


def test_a_slash_override_passes_through_unchanged(pi_agent, monkeypatch):
    calls = _capture(monkeypatch, pi_agent)
    pi_agent.run(_agent(pi_agent), "t", ".", None, "ollama/other:1b", None)
    assert _model_arg(calls[0][0]) == "ollama/other:1b"


def test_an_unknown_catalogue_id_exits_2(pi_agent, monkeypatch):
    monkeypatch.setattr(pi_agent.pi_call.subprocess, "run",
                        lambda *a, **k: pytest.fail("pi was spawned"))
    assert pi_agent.run(_agent(pi_agent), "t", ".", None, "no-such-model", None) == 2


def test_list_verbose_shows_the_resolution(pi_agent, monkeypatch, capsys):
    pi_agent.cmd_list([_agent(pi_agent, "bash")], True)
    out = capsys.readouterr().out
    assert "-> ollama/" in out and "(profile private)" in out


# --- the class fallback and the effort level (ruled 2026-10-14) ----------------

def test_a_role_whose_model_is_unavailable_takes_the_class_fallback(pi_agent, monkeypatch, capsys):
    """The role file is the DECLARATION and still wins; the class tier is what
    runs when the declaration cannot be served, and the swap is never silent."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(pi_agent, "class_pick",
                        lambda a: ("qwen3:4b-instruct-2507-q4_K_M", "read tier 1 (the fallback)"))
    calls = _capture(monkeypatch, pi_agent)
    a = _agent(pi_agent)                                  # explore: deepseek-flash
    assert pi_agent.run(a, "t", ".", None, None, None) == 0
    assert _model_arg(calls[0][0]) == "ollama/qwen3:4b-instruct-2507-q4_K_M"
    err = capsys.readouterr().err
    assert "deepseek-flash unavailable in profile" in err
    assert "running the class fallback qwen3:4b-instruct-2507-q4_K_M" in err
    assert "read tier 1 (the fallback)" in err


def test_an_explicit_model_never_falls_back(pi_agent, monkeypatch, capsys):
    """`--model` is the caller's own choice: it fails loudly, because a swap here
    would change what the caller asked for."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(pi_agent, "class_pick",
                        lambda a: pytest.fail("an explicit --model must not fall back"))
    monkeypatch.setattr(pi_agent.pi_call.subprocess, "run", lambda *a, **k: pytest.fail("spawned"))
    assert pi_agent.run(_agent(pi_agent), "t", ".", None, "deepseek-flash", None) == 3
    assert "class fallback" not in capsys.readouterr().err


def test_a_role_that_does_not_think_refuses_an_effort_level(pi_agent, monkeypatch, capsys):
    """qwen3:4b is `thinking: no` in the catalogue: asking for a level is refused
    with the reason, never clamped to nothing."""
    monkeypatch.setattr(pi_agent.pi_call.subprocess, "run", lambda *a, **k: pytest.fail("spawned"))
    assert pi_agent.run(_agent(pi_agent, "bash"), "t", ".", None, None, None, "high") == 2
    assert "does not think (thinking: no)" in capsys.readouterr().err


def test_effort_is_passed_as_thinking_and_an_override_wins(pi_agent, monkeypatch):
    calls = _capture(monkeypatch, pi_agent)
    a = _agent(pi_agent)                                  # explore: effort low
    pi_agent.run(a, "t", ".", None, None, None)
    cmd = calls[0][0]
    assert cmd[cmd.index("--thinking") + 1] == "low"
    calls.clear()
    pi_agent.run(a, "t", ".", None, None, None, "high")
    cmd = calls[0][0]
    assert cmd[cmd.index("--thinking") + 1] == "high", "an explicit --effort wins"


def test_every_role_declares_a_class_and_only_thinking_models_a_level(pi_agent):
    """The roster's own discipline: a role that names no class has no fallback,
    and a level on a model that does not think is a refused request."""
    agents = pi_agent.load_all()
    assert {a.name for a in agents} >= {"explore", "research", "review", "bash"}
    for a in agents:
        assert a.task_class, f"{a.name} names no class, so a swap could not happen"
    assert {a.name: a.effort for a in agents} == {
        "bash": "", "deepen": "high", "explore": "low", "research": "low",
        "review": "medium"}
