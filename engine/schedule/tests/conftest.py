"""Put `engine/` on the path so tests import the packages the way the entry
points do (`from schedule import sessions`)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))


import datetime as dt                                         # noqa: E402

import pytest                                                 # noqa: E402


def _legacy_9a(env, prompt, *, name="old", kind="once"):
    """A record as 9a's `add` wrote it -- a unit pair of its own -- which 1d's `add`
    no longer writes but which must still check, list and run."""
    from schedule import sessions
    d = sessions.session_dir(name, env)
    due = sessions.now_local() + dt.timedelta(minutes=10)
    decl = {"name": name, "created": sessions.now_local().isoformat(timespec="seconds"),
            "kind": kind, "due": "" if kind == "repeat" else due.isoformat(timespec="seconds"),
            "on_calendar": "*-*-* 01/5:35:00" if kind == "repeat" else sessions.calendar_of(due),
            "every": "5h" if kind == "repeat" else "", "anchor": "01:35" if kind == "repeat" else "",
            "ask": {"kind": "prompt", "path": str(prompt), "selector": "the file"},
            "touches": [], "cwd": str(prompt.parent), "branch": "", "commit": "per-item",
            "push": "never", "sandbox": "none", "nice": "15", "accuracy": "1s",
            "timeout": "12h", "unit": f"familiar-session-{name}", "record": str(d),
            "model": {"id": "deepseek-flash", "effort": "high", "source": "--model",
                      "profile": "private", "pi_model": "deepseek/deepseek-flash"}}
    d.mkdir(parents=True)
    decl["wrapper"] = str(sessions.write_wrapper(d, name, decl, env=env))
    sessions.render_units(name, decl, sessions.units_dir(env))
    sessions.write_decl(d, decl)
    return d, decl



@pytest.fixture
def legacy():
    """`legacy(env, prompt, name=..., kind="once"|"repeat")` -> (d, decl)."""
    return _legacy_9a


@pytest.fixture(autouse=True)
def _quiet_channels(monkeypatch):
    """No test pops a desktop notification or reaches a relay (1g): the channels
    record instead. A test that inspects them asks for `told`."""
    from schedule import notify
    sent = []
    monkeypatch.setattr(notify, "CHANNELS", {
        "desktop": lambda title, text, urgency, env: sent.append(("desktop", title, text)) or "",
        "relay": lambda job, text, env: sent.append(("relay", job, text)) or ""})
    return sent


@pytest.fixture
def told(_quiet_channels):
    return _quiet_channels


@pytest.fixture(autouse=True)
def _no_quota_probe(monkeypatch):
    """No test asks the live Claude usage probe (14d, 15a): a reading taken from the
    machine would make a test's verdict depend on which window is open. `None` is
    no reading, which is never a block."""
    from orchestration import price
    monkeypatch.setattr(price, "live_quota", lambda env=None: None)
