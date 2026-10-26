"""The security layers that cost no tap (R1b): pairing, redaction, the short closed
message, the audit, the pause, and a token file nobody else can read."""
import json
import os
import types

import pytest
from relay_fakes import OWNER, STRANGER, reply, tap

from relay import cli
from relay.core import PAIR_TRIES, PAIR_TTL_S, Relay, new_pair_code
from relay.redact import MASK, redact


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(bot, tmp_path, owner=None, cfg=None, clock=None):
    r = Relay(bot, tmp_path / "relay", cfg or {}, clock=clock or Clock(),
              nonce=iter(f"n{i}" for i in range(99)).__next__)
    r.state["owner_id"] = owner
    got = []
    r.on_answer = lambda ask_id, ans: got.append((ask_id, ans))
    return r, got


def audit(r):
    return [json.loads(line) for line in (r.dir / "audit.jsonl").read_text().splitlines()]


def push_ask(r, ask_id="a1", title="Permission Required\ntool : bash\nrule : rtk git push *\n"
                                   "command : rtk git push origin main", **kw):
    return r.ask({"id": ask_id, "session": "s", "kind": "select", "title": title,
                  "options": ["Yes", "No"], **kw})


# --- pairing -------------------------------------------------------------------

def test_pair_with_the_printed_code_sets_the_owner_and_sends_the_held_ask(bot, tmp_path):
    clock = Clock()
    r, _ = make(bot, tmp_path, clock=clock)
    push_ask(r)
    assert not bot.sent(), "no owner, nothing sent"
    code = new_pair_code(r.dir, clock=clock)
    assert code not in (r.dir / "pair.json").read_text(), "only the hash is stored"
    r.handle_update(reply(f"/pair {code.lower()}", None, user=OWNER, chat=OWNER))
    assert r.owner == OWNER and not (r.dir / "pair.json").exists(), "the code is used once"
    texts = [m["text"] for m in bot.sent()]
    assert texts[0].startswith("Paired.") and "rtk git push" in texts[1]
    assert audit(r)[-3]["event"] == "pair" or any(e["event"] == "pair" for e in audit(r))


def test_pair_refuses_a_wrong_an_expired_and_a_group_code(bot, tmp_path):
    clock = Clock()
    r, _ = make(bot, tmp_path, clock=clock)
    code = new_pair_code(r.dir, clock=clock)
    r.handle_update(reply("/pair WRONGCOD", None, user=STRANGER, chat=STRANGER, uid=1))
    group = {"update_id": 2, "message": {"from": {"id": STRANGER},
                                         "chat": {"id": -100, "type": "group"},
                                         "text": f"/pair {code}"}}
    r.handle_update(group)
    clock.t += PAIR_TTL_S + 1
    r.handle_update(reply(f"/pair {code}", None, user=STRANGER, chat=STRANGER, uid=3))
    assert r.owner is None
    events = [e["event"] for e in audit(r)]
    assert events.count("pair_refused") == 2 and "foreign" in events


def test_five_wrong_codes_void_the_open_one(bot, tmp_path):
    clock = Clock()
    r, _ = make(bot, tmp_path, clock=clock)
    code = new_pair_code(r.dir, clock=clock)
    for i in range(PAIR_TRIES):
        r.handle_update(reply("/pair AAAAAAAA", None, user=STRANGER, chat=STRANGER, uid=i))
    r.handle_update(reply(f"/pair {code}", None, user=STRANGER, chat=STRANGER, uid=9))
    assert r.owner is None and not (r.dir / "pair.json").exists()


def test_a_re_pair_tells_the_old_owner(bot, tmp_path):
    clock = Clock()
    r, _ = make(bot, tmp_path, owner=OWNER, clock=clock)
    code = new_pair_code(r.dir, clock=clock)
    r.handle_update(reply(f"/pair {code}", None, user=STRANGER, chat=STRANGER))
    assert r.owner == STRANGER
    warned = [m for m in bot.sent() if m["chat_id"] == OWNER]
    assert warned and "familiar relay pause" in warned[0]["text"]


# --- redaction -----------------------------------------------------------------

@pytest.mark.parametrize("secret_line", [
    "curl -H 'Authorization: Bearer abcdefgh12345678' https://x",
    "export GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuv",
    "ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnop pi -p hi",
    "mysql --password=hunter2hunter2 db",
    "curl https://api.telegram.org/bot123456789:AAH0123456789abcdefghijklmnopqrstuvw/getMe",
    '{"secret": "s3cr3tvalue"}',
])
def test_redact_masks_a_secret_in_a_command_line(secret_line):
    out = redact(secret_line)
    assert MASK in out
    for word in ("abcdefgh12345678", "ghp_0123", "sk-ant-api03", "hunter2",
                 "AAH0123456789", "s3cr3tvalue"):
        assert word not in out


def test_redact_leaves_an_ordinary_command_alone():
    line = "rtk git push origin main && uv run pytest -q tests/test_tokenizer.py"
    assert redact(line) == line


def test_redact_reaches_the_message_the_more_text_and_the_audit(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=OWNER)
    push_ask(r, title="rule : bash *\ncommand : GITHUB_TOKEN=ghp_0123456789abcdefghijklmnopqrstuv gh pr list",
             context="env: API_KEY=sk-0123456789abcdefghijklmn")
    r.handle_update(tap("n0:m"))
    sent = " ".join(m["text"] for m in bot.sent())
    assert "ghp_0123" not in sent and "sk-0123" not in sent
    assert sent.count("&lt;redacted&gt;") == 2, "the title, and the context More sends"
    assert "ghp_0123" not in (r.dir / "audit.jsonl").read_text()


# --- the closed message --------------------------------------------------------

def test_redact_after_answer_keeps_rule_answer_and_time(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=OWNER)
    push_ask(r)
    r.handle_update(tap("n0:0"))
    text = bot.sent("editMessageText")[0]["text"]
    assert "rtk git push *" in text and "-&gt; Yes" in text and "origin main" not in text


def test_a_closed_question_keeps_the_question_not_its_heading(bot, tmp_path):
    """R2c, 2026-10-21: the `ask_user` message closed as "The agent asks: · red"."""
    r, _ = make(bot, tmp_path, owner=OWNER)
    push_ask(r, title="The agent asks:\nR2c test: which colour should colour.txt name?")
    r.handle_update(tap("n0:0"))
    text = bot.sent("editMessageText")[0]["text"]
    assert "R2c test: which colour should colour.txt name?" in text
    assert "The agent asks:" not in text


def test_redact_after_answer_off_keeps_the_full_ask(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=OWNER, cfg={"redact_after_answer": "false"})
    push_ask(r)
    r.handle_update(tap("n0:0"))
    assert "origin main" in bot.sent("editMessageText")[0]["text"]


# --- the audit -----------------------------------------------------------------

def test_audit_records_ask_sent_more_answer_and_foreign(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=OWNER)
    push_ask(r, context="ctx")
    r.handle_update(tap("n0:0", user=STRANGER, chat=STRANGER, uid=1))
    r.handle_update(tap("n0:m", uid=2))
    r.handle_update(tap("n0:1", uid=3))
    assert [e["event"] for e in audit(r)] == ["ask", "sent", "foreign", "more", "answer"]
    assert audit(r)[-1]["label"] == "No"


# --- pause ---------------------------------------------------------------------

def test_pause_holds_asks_and_refuses_taps(bot, tmp_path):
    r, got = make(bot, tmp_path, owner=OWNER)
    push_ask(r)
    r.pause("phone")
    r.handle_update(tap("n0:0", uid=1))
    push_ask(r, ask_id="a2")
    r.notify("s", "a note")
    assert not got and len(bot.sent()) == 1, "the second ask and the note are held"
    assert bot.sent("answerCallbackQuery")[-1]["text"].startswith("The relay is paused")
    r.handle_update(reply("/resume", None, uid=2))
    assert r.paused is None and len(bot.sent()) >= 4, "held ask and note go out on resume"


def test_pause_set_locally_is_not_lifted_from_the_phone(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=OWNER)
    r.pause("local")
    r.handle_update(reply("/resume", None, uid=1))
    assert r.paused == "local"
    assert "only the machine lifts it" in bot.sent()[-1]["text"]
    r.pause("phone")
    assert r.paused == "local", "a phone pause does not downgrade a local one"
    assert r.resume("local") and r.paused is None


def test_pause_survives_a_restart(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=OWNER)
    r.pause("local")
    r2 = Relay(bot, tmp_path / "relay", {})
    assert r2.paused == "local" and not r2.can_send()


# --- the token file ------------------------------------------------------------

def test_perms_a_group_readable_token_file_is_refused(tmp_path, capsys):
    tok = tmp_path / "relay.env"
    tok.write_text("TELEGRAM_BOT_TOKEN=123456789:AAH0123456789abcdefghijklmnopqrstuvw\n")
    os.chmod(tok, 0o640)
    env = {"FAMILIAR_RELAY_TOKEN_FILE": str(tok), "PAZRAS_DATA_DIR": str(tmp_path / "d"),
           "FAMILIAR_RELAY_SOCK": str(tmp_path / "s.sock")}
    assert cli.cmd_serve(types.SimpleNamespace(), env=env) == 2
    err = capsys.readouterr().err
    assert "chmod 600" in err and "AAH0123" not in err


def test_perms_pair_before_the_relay_ever_ran_makes_a_private_directory(tmp_path):
    d = tmp_path / "relay"
    new_pair_code(d)
    assert (d.stat().st_mode & 0o777) == 0o700 and (d / "pair.json").stat().st_mode & 0o077 == 0


def test_away_and_back_from_the_phone_are_in_status(bot, tmp_path):
    clock = Clock()
    r, _ = make(bot, tmp_path, owner=OWNER, clock=clock)
    r.handle_update(reply("/away", None, uid=1))
    assert r.status()["away_since"] == clock.t
    r.handle_update(reply("/back", None, uid=2))
    assert r.status()["away_since"] is None
    r.handle_update(reply("/away", None, user=STRANGER, chat=STRANGER, uid=3))
    assert r.status()["away_since"] is None, "only the owner declares the owner away"
