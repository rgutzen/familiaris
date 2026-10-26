"""The Bot API client (R1a): errors never carry the token, and the token file parses."""
import io
import json
import urllib.error

import pytest

from relay.telegram import Bot, BotError, load_token

TOKEN = "123456789:AAH-secret-token-value-0123456789abcdef"


def opener_raising(exc):
    def _open(req, timeout):
        assert TOKEN in req.full_url        # the token IS in the URL; that is the hazard
        raise exc
    return _open


@pytest.mark.parametrize("exc", [
    urllib.error.HTTPError(f"https://api.telegram.org/bot{TOKEN}/getUpdates", 409,
                           "Conflict", {}, io.BytesIO(json.dumps(
                               {"ok": False, "description": "Conflict: terminated by "
                                "other getUpdates request"}).encode())),
    urllib.error.URLError(f"cannot reach https://api.telegram.org/bot{TOKEN}/"),
    TimeoutError("timed out"),
])
def test_an_error_never_carries_the_token(exc):
    bot = Bot(TOKEN, opener=opener_raising(exc))
    with pytest.raises(BotError) as info:
        bot.call("getUpdates", {})
    assert TOKEN not in str(info.value) and "secret-token" not in repr(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_a_409_names_the_conflict():
    exc = urllib.error.HTTPError("u", 409, "Conflict", {}, io.BytesIO(
        b'{"ok": false, "description": "Conflict: terminated by other getUpdates request"}'))
    with pytest.raises(BotError) as info:
        Bot(TOKEN, opener=opener_raising(exc)).call("getUpdates")
    assert info.value.status == 409 and "other getUpdates" in info.value.description


def test_load_token_reads_the_env_line(tmp_path):
    f = tmp_path / "relay.env"
    f.write_text(f"# the relay's bot\nexport TELEGRAM_BOT_TOKEN='{TOKEN}'\n")
    assert load_token(f) == TOKEN


def test_load_token_refuses_without_echoing_content(tmp_path):
    f = tmp_path / "relay.env"
    f.write_text("OTHER=abc\n")
    with pytest.raises(BotError, match="no TELEGRAM_BOT_TOKEN"):
        load_token(f)
    with pytest.raises(BotError, match="does not exist"):
        load_token(tmp_path / "missing.env")


def test_a_dead_address_costs_the_connect_timeout_not_the_request_timeout(monkeypatch):
    """R3c, 2026-10-21: api.telegram.org's IPv6 address dropped connects, and urllib
    waited the whole 30 s on it before IPv4; two asks reached the phone 31 s late."""
    from relay import telegram
    seen = {}

    def create_connection(address, timeout, source_address=None):
        seen["connect_timeout"] = timeout
        raise OSError("stop here")

    monkeypatch.setattr(telegram.socket, "create_connection", create_connection)
    conn = telegram._QuickConnect("api.telegram.org", timeout=65)
    with pytest.raises(OSError):
        conn.connect()
    assert seen["connect_timeout"] == telegram.CONNECT_TIMEOUT < 30
    assert telegram.Bot("t")._open == telegram._OPENER.open
