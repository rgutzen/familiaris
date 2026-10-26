"""server -- the relay process: the socket sessions ask through, and the one poller (R1a).

One asyncio loop owns the `Relay` (core.py), so nothing in it needs a lock: the
socket handlers and the update handler run on the loop thread, and only the
blocking `getUpdates` call runs in a worker thread.

THE SOCKET speaks JSON lines, one object per line:

    {"op": "ask", "id", "session", "kind", "title", "options", "context"}
        -> nothing until answered, then {"op": "answer", "id", ...}
    {"op": "annotate", "id", "lines"}    -> {"ok": true, "annotated": bool}
    {"op": "withdraw", "id", "reason"}   -> {"ok": true, "withdrawn": bool}
    {"op": "notify", "session", "text"}  -> {"ok": true}
    {"op": "status"}                     -> {"ok": true, ...}
    {"op": "pause"} | {"op": "resume"}   -> {"ok": bool, "paused": ...}   (a LOCAL pause)

No op produces an answer: answers come only from the owner's Telegram updates.
A connection may hold several open asks; when it closes they stay open, and a
client that re-asks the same id later gets the stored answer or keeps waiting.
The socket is created mode 600 under $XDG_RUNTIME_DIR.

THE POLLER backs off on failure (2 s doubling to 60 s) and records the last
success and the last error for `status`. HTTP 409 means another program polls
the same bot; 401 means the token is wrong, and the relay exits rather than
retrying a dead token forever.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib

from relay.core import AskError, Relay
from relay.telegram import BotError

BACKOFF_MAX = 60.0


class Server:
    def __init__(self, relay: Relay, sock: pathlib.Path, *, poll_timeout: int = 50):
        self.relay = relay
        self.sock = pathlib.Path(sock)
        self.poll_timeout = poll_timeout
        self.waiters: dict[str, set] = {}
        relay.on_answer = self._deliver
        self.fatal = ""

    def _deliver(self, ask_id: str, answer: dict) -> None:
        for writer in self.waiters.pop(ask_id, set()):
            try:
                writer.write((json.dumps(answer, ensure_ascii=False) + "\n").encode())
            except (ConnectionError, RuntimeError):
                pass

    async def handle(self, reader, writer) -> None:
        mine: set[str] = set()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                reply = self._op(line, writer, mine)
                if reply is not None:
                    writer.write((json.dumps(reply, ensure_ascii=False) + "\n").encode())
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            for ask_id in mine:
                self.waiters.get(ask_id, set()).discard(writer)
            writer.close()

    def _op(self, line: bytes, writer, mine: set) -> dict | None:
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("not an object")
        except ValueError as e:
            return {"ok": False, "error": f"unreadable request: {e}"}
        op = req.get("op")
        try:
            if op == "ask":
                answer = self.relay.ask(req)
                if answer is not None:
                    return answer
                self.waiters.setdefault(str(req["id"]), set()).add(writer)
                mine.add(str(req["id"]))
                return None
            if op == "annotate":
                return {"ok": True, "annotated": self.relay.annotate(
                    str(req.get("id") or ""), req.get("lines") or [])}
            if op == "withdraw":
                return {"ok": True, "withdrawn": self.relay.withdraw(
                    str(req.get("id") or ""), str(req.get("reason") or "withdrawn"))}
            if op == "notify":
                self.relay.notify(str(req.get("session") or "?"), str(req.get("text") or ""))
                return {"ok": True}
            if op == "status":
                return {"ok": True, **self.relay.status()}
            if op == "pause":
                self.relay.pause("local")
                return {"ok": True, "paused": self.relay.paused}
            if op == "resume":
                return {"ok": self.relay.resume("local"), "paused": self.relay.paused}
        except AskError as e:
            return {"ok": False, "error": str(e), "id": req.get("id")}
        return {"ok": False, "error": f"unknown op {op!r}; "
                                      f"ask | annotate | withdraw | notify | status | pause | resume"}

    async def poll_forever(self, bot) -> None:
        delay = 2.0
        while not self.fatal:
            try:
                updates = await asyncio.to_thread(
                    bot.get_updates, self.relay.state.get("offset", 0), self.poll_timeout)
            except BotError as e:
                self.relay.poll["error"] = str(e)
                if e.status == 401:
                    self.fatal = "the bot token was refused (401)"
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 2, BACKOFF_MAX)
                continue
            delay = 2.0
            self.relay.poll = {"ok_ts": self.relay.clock(), "error": ""}
            for update in updates:
                self.relay.handle_update(update)
            self.relay.flush()

    async def run(self, bot) -> int:
        if self.sock.exists():
            self.sock.unlink()                    # a stale socket from a dead relay
        self.sock.parent.mkdir(parents=True, exist_ok=True)
        old = os.umask(0o177)
        try:
            server = await asyncio.start_unix_server(self.handle, path=str(self.sock))
        finally:
            os.umask(old)
        os.chmod(self.sock, 0o600)
        self.relay.flush()
        async with server:
            await self.poll_forever(bot)
        return 2 if self.fatal else 0
