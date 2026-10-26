"""telegram -- the smallest Bot API client the relay needs (R1a).

Standard library only: one POST per method, JSON in and out. The token is part
of every request URL, so NOTHING here formats a URL into an error or a log line:
a `BotError` carries the method, the HTTP status and Telegram's own
`description`, never the request.

Telegram allows ONE long-polling consumer per bot token; a second `getUpdates`
gets HTTP 409. The relay is that one consumer (dev/remote/SPECS.md, shared
rules), and a 409 here means another program is polling the same bot.
"""
from __future__ import annotations

import http.client
import json
import pathlib
import socket
import urllib.error
import urllib.request

API = "https://api.telegram.org"
#: Seconds to wait for a TCP connect to ONE address before trying the next. urllib
#: spends its whole timeout (30 s) on each address: measured 2026-10-21, the IPv6
#: address of api.telegram.org dropped 2 of 6 connects while IPv4 answered all 6 in
#: 0.03 s, and two `ask_user` messages reached the phone 31 s late (R3c).
CONNECT_TIMEOUT = 3.0


class _QuickConnect(http.client.HTTPSConnection):
    """An HTTPS connection whose CONNECT gives each address `CONNECT_TIMEOUT`, then
    reads with the request's own timeout (a long poll needs its 65 s)."""

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), CONNECT_TIMEOUT,
                                             self.source_address)
        self.sock.settimeout(self.timeout)
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _QuickHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_QuickConnect, req)


_OPENER = urllib.request.build_opener(_QuickHTTPS())
TOKEN_KEY = "TELEGRAM_BOT_TOKEN"


class BotError(RuntimeError):
    """A Bot API call that failed. `status` 0 means the network, not Telegram."""

    def __init__(self, method: str, status: int, description: str):
        super().__init__(f"{method}: {status or 'network'} {description}")
        self.method, self.status, self.description = method, status, description


def load_token(path: pathlib.Path) -> str:
    """`TELEGRAM_BOT_TOKEN=...` from an env-style file (`export` and quotes allowed).

    Raises:
        BotError: The file is missing or names no token -- said without its content.
    """
    if not path.is_file():
        raise BotError("token", 0, f"{path} does not exist")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if line.startswith(TOKEN_KEY + "="):
            value = line.split("=", 1)[1].strip().strip("'\"")
            if value:
                return value
    raise BotError("token", 0, f"{path} has no {TOKEN_KEY}= line")


class Bot:
    """`call(method, payload)` -> the `result` field, or a `BotError`."""

    def __init__(self, token: str, *, base: str = API, opener=_OPENER.open):
        self._url = f"{base}/bot{token}/"
        self._token = token
        self._open = opener

    def _err(self, method: str, status: int, description: str) -> BotError:
        """Whatever produced the description -- Telegram, urllib, the OS -- the token is
        scrubbed from it: a URLError's reason can quote the request URL (measured in
        test_telegram.py)."""
        return BotError(method, status, str(description).replace(self._token, "<token>"))

    def call(self, method: str, payload: dict | None = None, *, timeout: float = 30):
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(self._url + method, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with self._open(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                desc = json.loads(e.read().decode("utf-8")).get("description", "")
            except (ValueError, OSError):
                desc = e.reason or ""
            raise self._err(method, e.code, str(desc)) from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            reason = getattr(e, "reason", None) or type(e).__name__
            raise self._err(method, 0, str(reason)) from None
        if not body.get("ok"):
            raise self._err(method, int(body.get("error_code") or 0),
                            body.get("description", ""))
        return body.get("result")

    def get_updates(self, offset: int, timeout: int) -> list:
        return self.call("getUpdates", {"offset": offset, "timeout": timeout,
                                        "allowed_updates": ["message", "callback_query"]},
                         timeout=timeout + 15) or []
