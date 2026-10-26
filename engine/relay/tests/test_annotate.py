"""The two lines on the phone (item 8g): an ask reaches Telegram with the
requester's claim and an independent reading, and a later line EDITS the message
the owner is already reading instead of sending a second one."""
import json

from relay_fakes import OWNER, tap
from relay.core import LINE_MAX, MESSAGE_MAX

from test_core import audit, ask, make

LINES = ["agent : The branch is verified; pushing it now.",
         "independent : Pushes the branch fix/x to origin, setting its upstream."]


def ask_with_lines(r, lines=LINES, **kw):
    return ask(r, lines=lines, **kw)


def test_the_lines_are_in_the_first_message_inside_the_command_block(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    assert ask_with_lines(r) is None
    (msg,) = bot.sent()
    assert "agent : The branch is verified" in msg["text"]
    assert "independent : Pushes the branch" in msg["text"]
    assert msg["text"].index("<pre>") < msg["text"].index("agent :") < msg["text"].index("</pre>")
    assert msg["text"].index("rtk git push origin main") < msg["text"].index("agent :"), \
        "the command stays first; the lines read after it"
    assert len(msg["reply_markup"]["inline_keyboard"]) == 4, "the buttons are unaffected"


def test_three_lines_fit_and_the_third_is_the_audit(bot, tmp_path):
    """Item 8h adds `audit :` beside the claim and the reading."""
    r, _ = make(bot, tmp_path)
    three = LINES + ["audit : Pushing and rewriting history are the user's call. · instead commit"]
    ask_with_lines(r, lines=three)
    (msg,) = bot.sent()
    assert msg["text"].index("agent :") < msg["text"].index("independent :") \
        < msg["text"].index("audit :"), "the order is the reading order"
    assert len(msg["text"]) <= MESSAGE_MAX


def test_a_later_line_edits_the_same_message_and_never_sends_a_second(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    ask_with_lines(r, lines=[])
    assert r.annotate("a1", LINES) is True
    assert len(bot.sent("sendMessage")) == 1, "a second message would arrive after the verdict"
    (edit,) = bot.sent("editMessageText")
    assert "independent : Pushes the branch" in edit["text"]
    assert edit["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "n0:0", \
        "the owner can still answer it"
    assert "annotate" in [e["event"] for e in audit(r)]


def test_an_answered_ask_is_not_annotated(bot, tmp_path):
    r, got = make(bot, tmp_path)
    ask_with_lines(r)
    r.handle_update(tap("n0:2"))
    before = len(bot.calls)
    assert r.annotate("a1", ["agent : too late"]) is False
    assert len(bot.calls) == before, "the answer wins; nothing is re-rendered"


def test_clearing_the_lines_re_renders_without_them(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    ask_with_lines(r)
    assert r.annotate("a1", []) is True
    (edit,) = bot.sent("editMessageText")
    assert "agent :" not in edit["text"] and "rtk git push origin main" in edit["text"]


def test_the_lines_are_escaped_like_the_command(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    ask_with_lines(r, lines=["agent : I will run <<'EOF' 2>&1 and a < b & c"])
    (msg,) = bot.sent()
    assert "&lt;&lt;" in msg["text"] and "2&gt;&amp;1" in msg["text"]
    assert "a &lt; b &amp; c" in msg["text"] and " & a < b & c" not in msg["text"], \
        "no raw markup reaches Telegram"


def test_a_long_command_gives_way_to_the_lines_without_breaking_the_limit(bot, tmp_path):
    r, _ = make(bot, tmp_path)
    title = "Permission Required\ncommand : " + ("x" * 5000)
    r.ask({"id": "a1", "session": "s", "kind": "select", "title": title,
           "options": ["Yes", "No"], "lines": [f"independent : {'y' * 900}" for _ in range(3)]})
    (msg,) = bot.sent()
    assert len(msg["text"]) <= MESSAGE_MAX, "Telegram refuses anything over 4096"
    assert "More shows the rest" in msg["text"], "the cut is stated, not silent"
    assert "Permission Required" in msg["text"], "the head of the ask survives"
    ann = [ln for ln in msg["text"].split("\n") if ln.startswith(("agent : ", "independent : "))]
    assert ann and all(len(ln) <= LINE_MAX + len("independent : ") for ln in ann), \
        "a long sentence is capped, so it cannot push the command out"
