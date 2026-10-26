"""The relay's state machine (R1a): asks wait, answers bind, nothing is lost or doubled."""
import json
import stat

import pytest
from relay_fakes import OWNER, STRANGER, reply, tap

from relay.core import AskError, Relay

PERMISSION = ("Permission Required\ntool : bash\nrule : rtk git push *\n"
              "command : rtk git push origin main")


def make(bot, tmp_path, owner=OWNER):
    r = Relay(bot, tmp_path / "relay", nonce=iter(f"n{i}" for i in range(99)).__next__)
    r.state["owner_id"] = owner
    got = []
    r.on_answer = lambda ask_id, ans: got.append((ask_id, ans))
    return r, got


def ask(r, ask_id="a1", **kw):
    req = {"id": ask_id, "session": "mantis-chain", "kind": "select", "title": PERMISSION,
           "options": ["Yes", "Yes, allow bash \"rtk *\" for this session", "No",
                       "No, provide reason"], **kw}
    return r.ask(req)


def audit(r):
    return [json.loads(line) for line in (r.dir / "audit.jsonl").read_text().splitlines()]


def test_a_tap_answers_the_ask_and_closes_the_message(bot, tmp_path):
    r, got = make(bot, tmp_path)
    assert ask(r) is None, "an ask waits"
    (msg,) = bot.sent()
    assert "rtk git push origin main" in msg["text"] and "[mantis-chain]" in msg["text"]
    buttons = [b[0]["callback_data"] for b in msg["reply_markup"]["inline_keyboard"]]
    assert buttons == ["n0:0", "n0:1", "n0:2", "n0:3"]
    r.handle_update(tap("n0:2"))
    assert got[0][0] == "a1" and got[0][1]["value"] == "No" and got[0][1]["by"] == "telegram"
    assert not r.pending and r.answered["a1"]["value"] == "No"
    (edit,) = bot.sent("editMessageText")
    assert edit["reply_markup"] == {"inline_keyboard": []}
    assert "rtk git push *" in edit["text"] and "-&gt; No" in edit["text"]
    assert "origin main" not in edit["text"], "the closed message keeps the rule, not the command"


def test_a_stale_or_repeated_tap_is_refused_and_said_so(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask(r)
    r.handle_update(tap("n0:0", uid=1))
    r.handle_update(tap("n0:2", uid=2))            # the second tap on the same message
    r.handle_update(tap("zz:0", uid=3))            # a nonce that was never sent
    assert len(got) == 1 and got[0][1]["value"] == "Yes"
    refusals = [p["text"] for p in bot.sent("answerCallbackQuery")][1:]
    assert refusals == ["This ask is no longer open.", "This ask is no longer open."]
    assert [e["event"] for e in audit(r)].count("stale") == 2


def test_a_foreign_chat_is_ignored_and_audited(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask(r)
    r.handle_update(tap("n0:0", user=STRANGER, chat=STRANGER, uid=1))
    r.handle_update(tap("n0:0", user=OWNER, chat=-100123, uid=2))     # owner, but in a group
    r.handle_update(reply("yes", 101, user=STRANGER, chat=STRANGER, uid=3))
    assert not got and "a1" in r.pending
    assert [e["kind"] for e in audit(r) if e["event"] == "foreign"] == [
        "callback", "callback", "message"]
    assert r.state["offset"] == 4, "an ignored update still moves the offset"


def test_a_restart_keeps_the_open_ask_and_sends_it_once(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    ask(r)
    r2, got = make(bot, tmp_path)                   # the relay restarted
    assert ask(r2) is None, "the client re-asks with the same id after the restart"
    assert len(bot.sent()) == 1, "no second message"
    r2.handle_update(tap("n0:1"))
    assert got[0][1]["value"].startswith("Yes, allow")


def test_an_answer_given_while_the_client_was_gone_waits_for_it(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    ask(r)
    r.handle_update(tap("n0:0"))
    r2, _ = make(bot, tmp_path)
    stored = ask(r2)
    assert stored["value"] == "Yes" and stored["id"] == "a1"


def test_a_withdraw_closes_the_message_and_releases_the_waiter(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask(r)
    assert r.withdraw("a1", "answered at the laptop")
    assert got == [("a1", got[0][1])] and got[0][1]["cancelled"] and got[0][1]["withdrawn"]
    assert "a1" not in r.answered, "a withdrawal is not an answer"
    assert "withdrawn: answered at the laptop" in bot.sent("editMessageText")[0]["text"]
    assert not r.withdraw("a1")


def test_without_an_owner_nothing_is_sent_until_one_exists(bot, tmp_path):
    r, _ = make(bot, tmp_path, owner=None)
    ask(r)
    r.notify("mantis-chain", "chain done")
    assert not bot.sent()
    r.state["owner_id"] = OWNER
    r.flush()
    r.flush()
    assert len(bot.sent()) == 2 and r.pending["a1"]["sent"] and not r.outbox


def test_a_failed_send_is_retried_by_flush(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    bot.fail.add("sendMessage")
    ask(r)
    assert not r.pending["a1"]["sent"]
    bot.fail.clear()
    r.flush()
    assert r.pending["a1"]["sent"] and len(bot.sent()) == 1


def test_an_input_ask_is_answered_by_a_reply(bot, tmp_path):
    r, got = make(bot, tmp_path)
    r.ask({"id": "q1", "session": "s", "kind": "input", "title": "Why not?"})
    mid = r.pending["q1"]["message_id"]
    r.handle_update(reply("the remote is not ours", mid))
    assert got[0][1]["value"] == "the remote is not ours"


def test_a_worded_reply_to_a_select_carries_the_text_and_no_value(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask(r)
    r.handle_update(reply("no -- push to the fork instead", r.pending["a1"]["message_id"]))
    assert got[0][1]["value"] is None and got[0][1]["text"].startswith("no -- push")


def test_a_reply_that_names_no_ask_is_answered_with_a_hint(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask(r)
    r.handle_update(reply("yes", None))
    assert not got and "Reply to the ask you mean" in bot.sent()[-1]["text"]


def test_more_sends_the_context_and_is_audited(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask(r, context="cwd /tmp/x\nlast text: I will push the release branch")
    keys = [b[0]["callback_data"] for b in bot.sent()[0]["reply_markup"]["inline_keyboard"]]
    assert keys[-1] == "n0:m"
    r.handle_update(tap("n0:m"))
    assert not got and "a1" in r.pending, "More is not an answer"
    assert "push the release branch" in bot.sent()[-1]["text"]
    assert bot.sent()[-1]["reply_to_message_id"] == r.pending["a1"]["message_id"]
    assert any(e["event"] == "more" for e in audit(r))


def test_confirm_maps_to_confirmed(bot, tmp_path):
    r, got = make(bot, tmp_path)
    r.ask({"id": "c1", "session": "s", "kind": "confirm", "title": "Clear?"})
    r.handle_update(tap("n0:1"))
    assert got[0][1]["confirmed"] is False


@pytest.mark.parametrize("req, why", [
    ({"session": "s", "title": "t", "options": ["a"]}, "needs an id"),
    ({"id": "x", "kind": "poll", "title": "t"}, "kind"),
    ({"id": "x", "kind": "select", "title": "t"}, "needs options"),
])
def test_a_malformed_ask_is_refused(bot, tmp_path, req, why):
    r, _ = make(bot, tmp_path)
    with pytest.raises(AskError, match=why):
        r.ask(req)


def test_the_state_files_are_private(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    ask(r)
    assert stat.S_IMODE(r.dir.stat().st_mode) == 0o700
    for name in ("state.json", "pending.json", "answered.json", "audit.jsonl"):
        assert stat.S_IMODE((r.dir / name).stat().st_mode) == 0o600, name
