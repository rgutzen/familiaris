"""core -- the relay's state machine: asks that wait, answers that bind (R1a).

WHAT IT IS. A session (through the socket, `server.py`) asks; the relay sends
the ask to the owner's Telegram chat with one button per option; the owner's tap
or reply is the answer, and it goes back to whoever is waiting for that ask id.
Everything here is synchronous and does no I/O except through `self.bot` and the
state files, so the tests drive it with a fake bot and fabricated updates.

THE RULES IT KEEPS (dev/remote/PLAN.md, decisions 2 and 3):

* **No timeout decides anything.** An ask is open until the owner answers it or
  its asker withdraws it. Open asks live in `pending.json`, so a restart re-sends
  nothing twice and loses nothing; an ask whose send failed (no network, no
  owner yet) is retried by `flush`.
* **Answers come only from the owner's Telegram updates.** The socket has no
  verb that produces one. A button carries `<nonce>:<n>`; a tap whose nonce is
  not open (answered, withdrawn, or never sent) is refused and said so.
* **Re-asking is idempotent.** A client that reconnects with the same ask id
  gets the same open ask (no second message) or, if it was answered while the
  client was gone, the stored answer (`answered.json`, kept 30 days).

THE SECURITY LAYERS (R1b; PLAN.md, none of them costs the owner a tap):

* **Pairing.** No owner answers until `familiar relay pair` printed a one-time
  code locally and `/pair <code>` arrived from a private chat inside its ten
  minutes; five wrong codes void it. A re-pair is announced to the old owner.
* **Redaction.** Everything sent and everything audited passes `redact.redact`.
* **The closed message is short.** After an answer the message is edited to
  `rule . answer . time` (`redact_after_answer`), so the chat history keeps no
  command lines.
* **Pause.** `/pause` from the phone or `familiar relay pause` holds every ask
  and note and refuses every tap. A pause set LOCALLY is lifted only locally:
  a lost phone must not be able to undo the pause its loss caused.

FILES, under `<PAZRAS_DATA_DIR>/relay/` (mode 700, files 600 -- they hold
commands): `state.json` (owner, update offset, pause), `pending.json`,
`answered.json`, `outbox.json` (notes not yet delivered), `pair.json` (the hash
of an open pairing code), `audit.jsonl` (append-only).
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import pathlib
import secrets
import threading
import time

from relay import commands as commands_mod
from relay.redact import redact
from relay.telegram import BotError

#: The commands the relay answers itself; the rest are `relay.yaml`'s registry (R5a).
BUILTIN = {"status": "open asks, and the scheduler at a glance",
           "help": "every command",
           "away": "send interactive sessions' asks here",
           "back": "interactive sessions ask in the terminal",
           "pause": "hold every ask and note; refuse taps",
           "resume": "release a pause set from the phone"}
#: A confirm button is answered within this, or it is stale.
CONFIRM_S = 600

ANSWERED_DAYS = 30
KINDS = ("select", "confirm", "input")
MORE = "m"
#: An ask may carry annotation lines from a client (`pi-explain`, item 8g): the
#: agent's claim and one independent reading. Capped so a long sentence cannot
#: push the command out of the message.
LINES_MAX = 4
LINE_MAX = 200
#: Telegram's hard cap is 4096 characters. This leaves room for the header, the
#: `<pre>` markup, the hint, and the two lines, so a re-budget never overruns it.
MESSAGE_MAX = 4000
#: What a cut title says, so the cut is never silent.
CUT_MARKER = "\n[... cut; More shows the rest]"
PAIR_TTL_S = 600
PAIR_TRIES = 5
#: No 0/O or 1/I/L: the code is read off a screen and typed on a phone.
PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _escape_to(text: str, budget: int, marker: str) -> tuple[str, str]:
    """As much of `text` as fits `budget` ESCAPED characters, and the cut marker.

    Escaping is what a budget must count: `&` becomes five characters on the wire,
    so a title measured raw can still overrun Telegram's limit.
    """
    if len(html.escape(text)) <= budget:
        return html.escape(text), ""
    keep = budget - len(marker)
    if keep <= 0:
        return "", ""
    out = ""
    for ch in text:
        piece = html.escape(ch)
        if len(out) + len(piece) > keep:
            break
        out += piece
    return out, marker


def _write_json(path: pathlib.Path, data) -> None:
    """Atomic and private: a reader never sees half a file, nobody else reads it."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _truthy(value) -> bool:
    return str(value).strip().lower() not in ("false", "no", "0", "off")


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def new_pair_code(state_dir: pathlib.Path, *, clock=time.time) -> str:
    """Write a one-time pairing code's HASH, valid PAIR_TTL_S; return the code to print."""
    code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(8))
    state_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(state_dir, 0o700)                    # `pair` may run before the relay ever did
    _write_json(state_dir / "pair.json", {"sha256": _hash(code), "expires": clock() + PAIR_TTL_S,
                                          "tries": 0})
    return code


class AskError(ValueError):
    """A malformed request from a client; it is answered with the reason."""


class Relay:
    def __init__(self, bot, state_dir: pathlib.Path, cfg: dict | None = None, *,
                 clock=time.time, nonce=lambda: secrets.token_hex(4),
                 commands: dict | None = None, runner=None):
        self.bot = bot
        self.dir = pathlib.Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        self.cfg = cfg or {}
        self.commands = commands or {}
        # A command runs off the event loop: a verb that takes seconds must not hold
        # every socket client and the poller. A test passes `lambda f: f()`.
        self.runner = runner or (lambda f: threading.Thread(target=f, daemon=True).start())
        self.confirms: dict = {}
        self.clock = clock
        self.new_nonce = nonce
        self.state = _read_json(self.dir / "state.json", {"owner_id": None, "offset": 0})
        self.pending = _read_json(self.dir / "pending.json", {})
        self.answered = _read_json(self.dir / "answered.json", {})
        self.outbox = _read_json(self.dir / "outbox.json", [])
        cutoff = self.clock() - ANSWERED_DAYS * 86400
        self.answered = {k: v for k, v in self.answered.items() if v.get("ts", 0) >= cutoff}
        #: Called as on_answer(ask_id, answer) when an answer arrives; the server sets it.
        self.on_answer = lambda ask_id, answer: None
        self.poll = {"ok_ts": None, "error": ""}

    # --- persistence ---------------------------------------------------------

    def save(self) -> None:
        _write_json(self.dir / "state.json", self.state)
        _write_json(self.dir / "pending.json", self.pending)
        _write_json(self.dir / "answered.json", self.answered)
        _write_json(self.dir / "outbox.json", self.outbox)

    def audit(self, event: str, **fields) -> None:
        row = {"ts": round(self.clock(), 3), "event": event, **fields}
        path = self.dir / "audit.jsonl"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(redact(json.dumps(row, ensure_ascii=False)) + "\n")

    @property
    def owner(self):
        return self.state.get("owner_id")

    @property
    def paused(self):
        """None, or who paused: "local" or "phone"."""
        return self.state.get("paused")

    def can_send(self) -> bool:
        return bool(self.owner) and not self.paused

    def pause(self, by: str) -> None:
        if self.paused != "local":                 # a local pause is never downgraded
            self.state["paused"] = by
        self.audit("pause", by=by)
        self.save()

    def resume(self, by: str) -> bool:
        """Lift a pause. A pause set locally is lifted only locally."""
        if self.paused == "local" and by != "local":
            self.audit("resume_refused", by=by)
            return False
        self.state["paused"] = None
        self.audit("resume", by=by)
        self.save()
        self.flush()
        return True

    # --- what a client asks for ---------------------------------------------

    def ask(self, req: dict) -> dict | None:
        """Register an ask; the stored answer if it already has one, else None (wait).

        Raises:
            AskError: No id, an unknown kind, or a select with no options.
        """
        ask_id = str(req.get("id") or "")
        if not ask_id or len(ask_id) > 200:
            raise AskError("an ask needs an id (at most 200 characters)")
        if ask_id in self.answered:
            return self.answered[ask_id]
        if ask_id in self.pending:
            return None
        kind = req.get("kind") or "select"
        if kind not in KINDS:
            raise AskError(f"kind {kind!r}: one of {', '.join(KINDS)}")
        options = [str(o) for o in (req.get("options") or [])]
        if kind == "select" and not options:
            raise AskError("a select ask needs options")
        self.pending[ask_id] = {
            "id": ask_id, "session": str(req.get("session") or "?"), "kind": kind,
            "title": str(req.get("title") or ""), "options": options,
            "context": str(req.get("context") or ""), "nonce": self.new_nonce(),
            "created": self.clock(), "message_id": None, "sent": False,
            "lines": [str(ln)[:LINE_MAX] for ln in (req.get("lines") or [])][:LINES_MAX],
        }
        self.audit("ask", id=ask_id, session=self.pending[ask_id]["session"], kind=kind,
                   title=self.pending[ask_id]["title"][:500])
        self._send_ask(self.pending[ask_id])
        self.save()
        return None

    def withdraw(self, ask_id: str, reason: str = "withdrawn") -> bool:
        ask = self.pending.pop(ask_id, None)
        if not ask:
            return False
        self.audit("withdraw", id=ask_id, reason=reason)
        if ask.get("message_id"):
            self._edit(ask, f"withdrawn: {reason}")
        self.save()
        # Anyone still waiting is released; a withdrawal is not an answer, so it is not stored.
        self.on_answer(ask_id, {"op": "answer", "id": ask_id, "cancelled": True,
                                "withdrawn": reason, "by": "withdraw", "ts": self.clock()})
        return True

    def annotate(self, ask_id: str, lines: list) -> bool:
        """Add or replace an ask's annotation lines and re-render it in place.

        The message is EDITED, never re-sent: the owner may already be looking at
        it, a second message would arrive after the verdict, and holding the ask
        back for the reader would make a prompt late -- which makes it denied.
        Returns False when the ask is no longer open: an answer that lands first
        wins, and the lines are then only in this ask's audit entry.
        """
        ask = self.pending.get(ask_id)
        if not ask:
            return False
        ask["lines"] = [str(ln)[:LINE_MAX] for ln in (lines or [])][:LINES_MAX]
        self.audit("annotate", id=ask_id, lines=ask["lines"])
        if ask.get("sent") and ask.get("message_id"):
            try:
                self.bot.call("editMessageText", {"chat_id": self.owner,
                                                 "message_id": ask["message_id"],
                                                 "text": self.render(ask), "parse_mode": "HTML",
                                                 "reply_markup": self.keyboard(ask)})
            except BotError as e:
                self.audit("edit_failed", id=ask_id, error=str(e))
        self.save()
        return True

    def notify(self, session: str, text: str) -> None:
        self.outbox.append({"session": session, "text": text, "ts": self.clock()})
        self.audit("notify", session=session, text=text[:500])
        self.flush()

    def status(self) -> dict:
        return {"owner": bool(self.owner), "paused": self.paused,
                "away_since": self.state.get("away_since"), "pending": len(self.pending),
                "unsent": sum(1 for a in self.pending.values() if not a["sent"]),
                "outbox": len(self.outbox), "poll": dict(self.poll),
                "asks": [{"id": a["id"], "session": a["session"], "kind": a["kind"],
                          "age_s": round(self.clock() - a["created"]), "sent": a["sent"]}
                         for a in self.pending.values()]}

    def flush(self) -> None:
        """Send what could not be sent before: asks first, then notes."""
        if not self.can_send():
            return
        for ask in list(self.pending.values()):
            if not ask["sent"]:
                self._send_ask(ask)
        while self.outbox:
            note = self.outbox[0]
            try:
                self._send(f"<b>[{html.escape(note['session'])}]</b>\n"
                           f"{html.escape(redact(note['text']))}")
            except BotError:
                break
            self.outbox.pop(0)
        self.save()

    # --- rendering -----------------------------------------------------------

    def _max_text(self) -> int:
        return int(self.cfg.get("max_text") or 3500)

    def render(self, ask: dict, *, hint: bool = True) -> str:
        """The ask as the phone shows it: one `<pre>` block, then the hint.

        The annotation lines go INSIDE that block, after the command and through
        the same `html.escape`, so `<<'EOF'`, `2>&1`, `&` and `<` stay literal. The
        title is cut to make room for them rather than pushing the message past
        Telegram's limit: the head of the command survives, and `More` still
        carries the whole title.
        """
        title = redact(ask["title"])
        lines = [ln for ln in (ask.get("lines") or []) if ln][:LINES_MAX]
        block = "".join("\n" + html.escape(ln[:LINE_MAX]) for ln in lines)
        head = f"<b>[{html.escape(ask['session'])}]</b>"
        tail = ""
        if hint:
            if ask["kind"] == "input":
                tail = "\nReply to this message to answer."
            elif ask["kind"] == "select":
                tail = "\nTap an option, or reply in words."
        body = MESSAGE_MAX - len(head) - len("<pre></pre>") - len(block) - len(tail) - 1  # + the newline
        cut, marker = _escape_to(title, min(self._max_text(), max(0, body)), CUT_MARKER)
        return f"{head}\n<pre>{cut}{marker}{block}</pre>{tail}"

    def keyboard(self, ask: dict) -> dict:
        labels = ask["options"] if ask["kind"] == "select" else (
            ["Yes", "No"] if ask["kind"] == "confirm" else [])
        rows = [[{"text": label[:60], "callback_data": f"{ask['nonce']}:{i}"}]
                for i, label in enumerate(labels)]
        if ask["context"] or len(ask["title"]) > self._max_text():
            rows.append([{"text": "More", "callback_data": f"{ask['nonce']}:{MORE}"}])
        return {"inline_keyboard": rows}

    # --- sending -------------------------------------------------------------

    def _send(self, text: str, **extra) -> dict:
        return self.bot.call("sendMessage", {"chat_id": self.owner, "text": text,
                                             "parse_mode": "HTML",
                                             "disable_web_page_preview": True, **extra})

    def _send_ask(self, ask: dict) -> None:
        if not self.can_send():
            return
        try:
            msg = self._send(self.render(ask), reply_markup=self.keyboard(ask))
        except BotError as e:
            self.audit("send_failed", id=ask["id"], error=str(e))
            return
        ask["message_id"], ask["sent"] = msg.get("message_id"), True
        self.audit("sent", id=ask["id"], message_id=ask["message_id"])

    def summary(self, ask: dict, outcome: str) -> str:
        """`[session] rule . outcome . HH:MM` -- what the chat keeps after an answer."""
        rule = next((line.split(":", 1)[1].strip() for line in ask["title"].splitlines()
                     if line.strip().lower().startswith("rule") and ":" in line), "")
        # The first line that says something: `ask_user` titles open with the heading
        # "The agent asks:", and a summary of that alone loses the question (R2c).
        lines = [ln.strip() for ln in ask["title"].strip().splitlines() if ln.strip()]
        what = rule or next((ln for ln in lines if not ln.endswith(":")),
                            lines[0] if lines else "")[:80]
        when = time.strftime("%H:%M", time.localtime(self.clock()))
        return (f"<b>[{html.escape(ask['session'])}]</b> {html.escape(redact(what))}"
                f" · {html.escape(outcome)} · {when}")

    def _edit(self, ask: dict, outcome: str) -> None:
        """Close the message: the buttons go; the text is cut to the summary, or the
        outcome is appended when `redact_after_answer` is off."""
        if _truthy(self.cfg.get("redact_after_answer", "true")):
            text = self.summary(ask, outcome)
        else:
            text = self.render(ask, hint=False) + f"\n<b>{html.escape(outcome)}</b>"
        try:
            self.bot.call("editMessageText", {"chat_id": self.owner,
                                              "message_id": ask["message_id"], "text": text,
                                              "parse_mode": "HTML",
                                              "reply_markup": {"inline_keyboard": []}})
        except BotError as e:
            self.audit("edit_failed", id=ask["id"], error=str(e))

    # --- what Telegram says ----------------------------------------------------

    def handle_update(self, update: dict) -> None:
        """One update from getUpdates. The offset moves even when it is ignored."""
        uid = update.get("update_id")
        if isinstance(uid, int):
            self.state["offset"] = max(self.state.get("offset", 0), uid + 1)
        if "callback_query" in update:
            self._on_callback(update["callback_query"])
        elif "message" in update:
            self._on_message(update["message"])
        self.save()

    def _from_owner(self, sender: dict, chat: dict) -> bool:
        return (bool(self.owner) and sender.get("id") == self.owner
                and chat.get("type") == "private" and chat.get("id") == self.owner)

    def _foreign(self, kind: str, sender: dict, chat: dict) -> None:
        self.audit("foreign", kind=kind, user_id=sender.get("id"),
                   username=sender.get("username", ""), chat_id=chat.get("id"),
                   chat_type=chat.get("type", ""))

    def _by_nonce(self, nonce: str) -> dict | None:
        for ask in self.pending.values():
            if ask["nonce"] == nonce:
                return ask
        return None

    def _on_callback(self, cq: dict) -> None:
        sender, msg = cq.get("from") or {}, cq.get("message") or {}
        chat = msg.get("chat") or {}
        if not self._from_owner(sender, chat):
            self._foreign("callback", sender, chat)
            return
        if self.paused:
            self.audit("paused_tap", data=cq.get("data"))
            self._answer_cb(cq, "The relay is paused; nothing was recorded.")
            return
        nonce, _, which = str(cq.get("data") or "").partition(":")
        if nonce in self.confirms:
            self._on_confirm(cq, self.confirms.pop(nonce), which)
            return
        ask = self._by_nonce(nonce)
        if ask is None:
            self.audit("stale", data=cq.get("data"))
            self._answer_cb(cq, "This ask is no longer open.")
            return
        if which == MORE:
            self.audit("more", id=ask["id"])
            self._answer_cb(cq, "")
            self._send_more(ask)
            return
        labels = ask["options"] if ask["kind"] == "select" else ["Yes", "No"]
        try:
            idx = int(which)
            label = labels[idx]
        except (ValueError, IndexError):
            self.audit("stale", data=cq.get("data"))
            self._answer_cb(cq, "Unknown option.")
            return
        if ask["kind"] == "confirm":
            answer = {"confirmed": idx == 0}
        else:
            answer = {"value": label}
        self._answer_cb(cq, f"Recorded: {label[:150]}")
        self._resolve(ask, answer, label)

    def _on_message(self, msg: dict) -> None:
        sender, chat = msg.get("from") or {}, msg.get("chat") or {}
        text = str(msg.get("text") or "").strip()
        if text.lower().startswith("/pair") and chat.get("type") == "private":
            self._pair(sender, chat, text.split(maxsplit=1)[1] if " " in text else "")
            return
        if not self._from_owner(sender, chat):
            self._foreign("message", sender, chat)
            return
        if text.startswith("/"):
            self._command(text)
            return
        if self.paused:
            self.audit("paused_reply")
            self._send("The relay is paused; nothing was recorded.")
            return
        replied = (msg.get("reply_to_message") or {}).get("message_id")
        ask = next((a for a in self.pending.values()
                    if replied and a.get("message_id") == replied), None)
        if ask is None:
            self._send("Reply to the ask you mean (swipe it), so the answer reaches "
                       "the right session.")
            return
        if ask["kind"] == "input":
            answer = {"value": text}
        else:
            answer = {"value": None, "text": text}
        self._resolve(ask, answer, f"replied: {text[:200]}")

    def _pair(self, sender: dict, chat: dict, code: str) -> None:
        """`/pair <code>` from a private chat. Any outcome is audited; a wrong code is
        not told apart from an expired one, and five wrong codes void it."""
        path = self.dir / "pair.json"
        pending = _read_json(path, None)
        ok = bool(pending) and pending.get("expires", 0) > self.clock() \
            and secrets.compare_digest(pending.get("sha256", ""), _hash(code or "-"))
        if not ok:
            if pending:
                pending["tries"] = pending.get("tries", 0) + 1
                if pending["tries"] >= PAIR_TRIES:
                    path.unlink(missing_ok=True)
                else:
                    _write_json(path, pending)
            self.audit("pair_refused", user_id=sender.get("id"),
                       username=sender.get("username", ""))
            self._reply(chat, "No pairing code is open, or this one is wrong. Run "
                              "`familiar relay pair` on the machine.")
            return
        path.unlink(missing_ok=True)
        old = self.owner
        self.state["owner_id"] = sender.get("id")
        self.audit("pair", user_id=sender.get("id"), username=sender.get("username", ""),
                   replaced=old)
        self.save()
        if old and old != self.owner:
            self._reply({"id": old}, "This relay was paired to another Telegram account. "
                                     "If that was not you, run `familiar relay pause` now.")
        self._send("Paired. Asks from agent sessions on this machine come here. "
                   "/pause holds them, /resume releases them, /status lists them.")
        self.flush()

    def _reply(self, chat: dict, text: str) -> None:
        try:
            self.bot.call("sendMessage", {"chat_id": chat.get("id"), "text": text})
        except BotError:
            pass

    def _command(self, text: str) -> None:
        head, _, rest = text.strip().partition(" ")
        cmd = head.split("@")[0].lower()
        name = cmd[1:]
        if cmd == "/pause":
            self.pause("phone")
            self._send("Paused: asks and notes are held, taps are refused. /resume releases.")
            return
        if cmd == "/resume":
            if self.resume("phone"):
                self._send("Resumed.")
            else:
                self._send("This pause was set on the machine; only the machine lifts it "
                           "(`familiar relay resume`).")
            return
        if cmd in ("/away", "/back"):
            # Read by interactive sessions (familiar-remote): away from /away until /back,
            # or until a session sees local input after it -- that session is back.
            self.state["away_since"] = self.clock() if cmd == "/away" else None
            self.audit(cmd[1:])
            self.save()
            self._send("Away: interactive sessions send their asks and turn ends here."
                       if cmd == "/away" else "Back: interactive sessions ask in the terminal.")
            return
        if cmd == "/status":
            st = self.status()
            lines = [f"{st['pending']} open ask(s)"] + [
                f"- [{a['session']}] {a['kind']}, open {a['age_s'] // 60} min"
                for a in st["asks"]]
            asks = html.escape("\n".join(lines))
            # A registry `status` adds the scheduler's screen below the relay's own lines.
            if "status" in self.commands:
                self._run(self.commands["status"], rest, prefix=asks + "\n")
            else:
                self._send(asks)
            return
        if cmd == "/help":
            rows = [f"/{n} -- {h}" for n, h in BUILTIN.items()]
            rows += [f"/{c.name}{(' ' + c.usage) if c.usage else ''} -- {c.help}"
                     for c in self.commands.values() if c.name not in BUILTIN]
            self._send(html.escape("\n".join(rows)))
            return
        if name in self.commands:
            c = self.commands[name]
            if c.confirm:
                self._ask_confirm(c, rest)
            else:
                self._run(c, rest)
            return
        self._send(html.escape(f"Unknown command {cmd}. /help lists them."))

    # --- registry commands (R5a) ---------------------------------------------

    def _argv(self, c, rest: str) -> list | None:
        try:
            return commands_mod.argv(c, rest)
        except commands_mod.CommandError as e:
            self.audit("command_refused", name=c.name, args=rest[:200], why=str(e))
            self._send(html.escape(str(e)))
            return None

    def _run(self, c, rest: str, *, prefix: str = "") -> None:
        argv = self._argv(c, rest)
        if argv is None:
            return
        timeout = float(self.cfg.get("command_timeout") or 20)

        def work() -> None:
            code, text, secs = commands_mod.execute(argv, timeout=timeout)
            self.audit("command", name=c.name, args=rest[:200], exit=code, seconds=secs)
            body = redact(text) or "(no output)"
            limit = self._max_text()
            if len(body) > limit:
                body = body[:limit] + "\n[... cut]"
            head = "" if code == 0 else f"<b>exit {code}</b>\n"
            try:
                self._send(prefix + head + f"<pre>{html.escape(body)}</pre>")
            except BotError as e:
                self.audit("send_failed", id=f"/{c.name}", error=str(e))

        self.runner(work)

    def _ask_confirm(self, c, rest: str) -> None:
        if self._argv(c, rest) is None:
            return
        nonce = self.new_nonce()
        self.confirms[nonce] = {"name": c.name, "rest": rest, "created": self.clock()}
        self.audit("confirm", name=c.name, args=rest[:200])
        self._send(html.escape(f"Run /{c.name} {rest}?".rstrip()),
                   reply_markup={"inline_keyboard": [[
                       {"text": "Yes", "callback_data": f"{nonce}:y"},
                       {"text": "No", "callback_data": f"{nonce}:n"}]]})

    def _on_confirm(self, cq: dict, entry: dict, which: str) -> None:
        msg = cq.get("message") or {}
        try:
            self.bot.call("editMessageReplyMarkup", {"chat_id": self.owner,
                                                     "message_id": msg.get("message_id"),
                                                     "reply_markup": {"inline_keyboard": []}})
        except BotError:
            pass
        c = self.commands.get(entry["name"])
        if c is None or self.clock() - entry["created"] > CONFIRM_S:
            self.audit("stale", data=cq.get("data"))
            self._answer_cb(cq, "This confirmation is no longer open.")
            return
        if which != "y":
            self.audit("confirm_no", name=c.name)
            self._answer_cb(cq, "Not run.")
            return
        self._answer_cb(cq, f"Running /{c.name}")
        self._run(c, entry["rest"])

    def register_commands(self) -> None:
        """`setMyCommands`, so the client autocompletes `/`. Best effort."""
        try:
            self.bot.call("setMyCommands", {"commands": commands_mod.telegram_list(
                BUILTIN, self.commands)})
        except BotError as e:
            self.audit("set_commands_failed", error=str(e))

    def _send_more(self, ask: dict) -> None:
        body = redact(ask["context"] or ask["title"])
        limit = self._max_text()
        for start in range(0, max(len(body), 1), limit):
            self._send(f"<pre>{html.escape(body[start:start + limit])}</pre>",
                       reply_to_message_id=ask["message_id"])

    def _answer_cb(self, cq: dict, text: str) -> None:
        try:
            self.bot.call("answerCallbackQuery", {"callback_query_id": cq.get("id"),
                                                  "text": text[:190]})
        except BotError:
            pass                                   # the spinner stops by itself

    def _resolve(self, ask: dict, answer: dict, label: str) -> None:
        full = {"op": "answer", "id": ask["id"], **answer, "by": "telegram",
                "ts": self.clock(), "waited_s": round(self.clock() - ask["created"], 1)}
        self.pending.pop(ask["id"], None)
        self.answered[ask["id"]] = full
        self.audit("answer", id=ask["id"], label=label[:300], waited_s=full["waited_s"])
        self._edit(ask, f"-> {label}")
        self.save()
        self.on_answer(ask["id"], full)
