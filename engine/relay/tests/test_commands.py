"""The bot's registry commands (R5a): a declared argv, one checked argument, no shell.

Each rule in `relay/commands.py`'s docstring is held here. The commands run for
real (a `python3 -c` argv), so the subprocess path is the one the relay uses; the
Bot API is the recording fake.
"""
from __future__ import annotations

import json
import sys

import pytest

from relay import commands as C
from relay.core import Relay
from relay_fakes import OWNER, FakeBot, tap


def msg(text, *, user=OWNER, uid=1):
    return {"update_id": uid, "message": {"message_id": 7, "text": text,
                                          "from": {"id": user},
                                          "chat": {"id": user, "type": "private"}}}


PY = sys.executable
ECHO = ["-c", "import sys; print('argv=' + repr(sys.argv[1:]))"]


def registry(**extra):
    raw = {
        "jobs": {"help": "one line per job", "run": [PY, *ECHO, "jobs"]},
        "job": {"help": "one job", "run": [PY, *ECHO, "show", "{args}"],
                "arg": "[a-z0-9][a-z0-9-]{0,60}", "usage": "<name>"},
        "brief": {"help": "the brief", "run": [PY, *ECHO, "{args}"],
                  "arg": "(changed|open|failed|scheduled)?", "usage": "[section]"},
        "cancel": {"help": "cancel a job", "run": [PY, *ECHO, "cancel", "{args}"],
                   "arg": "[a-z0-9][a-z0-9-]{0,60}", "tier": "control", "confirm": "true"},
        "status": {"help": "the scheduler", "run": [PY, "-c", "print('jobs: 1 running')"]},
        "secret": {"help": "prints a key", "run": [PY, "-c", "print('key sk-0123456789abcdefghijklmn')"]},
        "slow": {"help": "too slow", "run": [PY, "-c", "import time; time.sleep(5)"]},
    }
    raw.update(extra)
    return C.load(raw)


@pytest.fixture
def relay(tmp_path):
    bot = FakeBot()
    r = Relay(bot, tmp_path / "relay", {"command_timeout": "2"}, commands=registry(),
              runner=lambda f: f(), nonce=iter(f"n{i}" for i in range(99)).__next__)
    r.state["owner_id"] = OWNER
    return r, bot


def texts(bot):
    return [p["text"] for p in bot.sent()]


def audit(r):
    return [json.loads(l) for l in (r.dir / "audit.jsonl").read_text().splitlines()]


# --- the argv ----------------------------------------------------------------------

def test_the_argument_is_one_argv_element_never_a_shell_string():
    reg = registry()
    assert C.argv(reg["job"], "chain-1i")[-1] == "chain-1i"
    with pytest.raises(C.CommandError, match="usage: /job <name>"):
        C.argv(reg["job"], "x; rm -rf ~")
    with pytest.raises(C.CommandError, match="takes no argument"):
        C.argv(reg["jobs"], "extra")
    assert C.argv(reg["brief"], "")[-1] != "", "an optional argument may be absent"


def test_a_relative_program_is_resolved_against_the_repository(tmp_path):
    c = C.load({"x": {"run": ["engine/familiar", "schedule"]}})["x"]
    assert C.argv(c, "", base=tmp_path) == [str(tmp_path / "engine/familiar"), "schedule"]


def test_a_bad_registry_entry_is_refused_not_dropped():
    for bad in ({"Bad": {"run": ["x"]}}, {"x": {"help": "no run"}},
                {"x": {"run": ["x", "{args}"]}}, {"x": {"run": ["x"], "tier": "god"}}):
        with pytest.raises(C.CommandError):
            C.load(bad)


# --- through the relay ---------------------------------------------------------------

def test_a_command_runs_and_its_output_comes_back_audited(relay):
    r, bot = relay
    r.handle_update(msg("/job chain-1i"))
    assert "argv=[&#x27;show&#x27;, &#x27;chain-1i&#x27;]" in texts(bot)[-1]
    row = [e for e in audit(r) if e["event"] == "command"][-1]
    assert row["name"] == "job" and row["args"] == "chain-1i" and row["exit"] == 0


def test_a_misfit_argument_answers_with_the_usage_and_runs_nothing(relay):
    r, bot = relay
    r.handle_update(msg("/job $(whoami)"))
    assert texts(bot)[-1].startswith("usage: /job")
    assert [e["event"] for e in audit(r)] == ["command_refused"]


def test_output_is_redacted_and_a_slow_command_is_an_exit(relay):
    r, bot = relay
    r.handle_update(msg("/secret"))
    assert "sk-0123" not in texts(bot)[-1] and "&lt;redacted&gt;" in texts(bot)[-1]
    r.handle_update(msg("/slow"))
    assert "exit 124" in texts(bot)[-1]


def test_status_puts_the_relays_lines_above_the_schedulers(relay):
    r, bot = relay
    r.handle_update(msg("/status"))
    assert texts(bot)[-1].startswith("0 open ask(s)") and "jobs: 1 running" in texts(bot)[-1]


def test_help_lists_the_built_ins_and_the_registry_with_usage(relay):
    r, bot = relay
    r.handle_update(msg("/help"))
    t = texts(bot)[-1]
    assert "/pause" in t and "/job &lt;name&gt; -- one job" in t


def test_a_confirmed_command_asks_first_and_runs_on_yes_only(relay):
    r, bot = relay
    r.handle_update(msg("/cancel chain-1i"))
    ask = bot.sent()[-1]
    assert ask["text"] == "Run /cancel chain-1i?"
    assert [b["callback_data"] for b in ask["reply_markup"]["inline_keyboard"][0]] == \
        ["n0:y", "n0:n"]
    assert not [e for e in audit(r) if e["event"] == "command"], "nothing ran yet"
    r.handle_update(tap("n0:y", uid=2))
    assert "cancel" in texts(bot)[-1] and "chain-1i" in texts(bot)[-1]
    r.handle_update(tap("n0:y", uid=3))
    assert [e["event"] for e in audit(r)].count("command") == 1, "a second tap is stale"


def test_a_confirm_answered_no_runs_nothing(relay):
    r, bot = relay
    r.handle_update(msg("/cancel chain-1i"))
    r.handle_update(tap("n0:n", uid=2))
    assert not [e for e in audit(r) if e["event"] == "command"]
    assert "confirm_no" in [e["event"] for e in audit(r)]


def test_the_client_learns_every_command_for_autocomplete(relay):
    r, bot = relay
    r.register_commands()
    names = [c["command"] for c in bot.sent("setMyCommands")[0]["commands"]]
    assert names[:2] == ["status", "help"] and "job" in names and names.count("status") == 1


def test_the_committed_registry_loads():
    from relay import cli
    reg = cli.load_commands()
    assert {"jobs", "job", "budget", "brief", "todos", "approve", "hold", "cancel"} <= set(reg)
    assert reg["cancel"].confirm and not reg["approve"].confirm
