"""rpc -- a scheduled run drives `pi --mode rpc`, so every dialog reaches the phone (R2a).

WHY RPC AND NOT `pi -p`. Under `-p` a session has no UI, and the permission
system answers every ask with "requires approval, but no interactive UI is
available" -- the run cannot be supervised at all. Under `--mode rpc` the UI is
a protocol: every dialog (`select`, `confirm`, `input`, `editor`) arrives on
stdout as an `extension_ui_request` and blocks until an `extension_ui_response`
comes back on stdin. Measured 2026-10-20 with a `git push` ask
(dev/schedule/2026-10-20-remote-supervision.md). This module is that client: it
forwards each dialog to the relay as an ask and writes the owner's answer back.

THE TWO LINES (item 8g). A `setWidget` request with the `pi-explain` key carries
an ask's two one-liners: the requester's claim and an independent reading. pi
sends it fire-and-forget and it arrives BEFORE the dialog (measured 2026-10-24),
so the lines are held and attached to the ask as it opens, and a later change
edits the message on the phone in place. An ask never waits for them.

WAITING IS NOT WORKING. An ask waits indefinitely (dev/remote decision 3), so
the run's timeout counts only the time with NO open ask: a run that waited eight
hours for a sleeping user is not a run that worked eight hours.

ONE TRANSLATION. Telegram lets the owner answer a `select` in words. A
permission ask has an option "No, provide reason", which pi follows with an
`input` for the reason; a worded reply therefore picks that option and answers
the next `input` with the words, so the model reads them. A `select` with no
such option takes a worded reply as a cancel, and the words are recorded.

THE LOG is for a person: the assistant's text, each tool call, every error
(a refused window's message included, which `sessions.DENIED` reads), every ask
and its answer. The transcript pi writes under `--session-dir` is the full
record.
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time

from harness import pi_call
from relay import client as relay_client

DIALOGS = ("select", "confirm", "input", "editor")
#: The widget key an annotator uses for the ask on screen (`pi-explain`, 8g). The
#: key is how a fire-and-forget `setWidget` -- which carries no request id -- is
#: recognised: anything else is another extension's widget and is left alone.
WIDGET_PREFIX = "pi-explain"
LINES_MAX = 4
#: The option a worded reply picks: the permission system's "No, provide reason", or
#: `ask_user`'s "Other (reply in words)" (engine/relay/pi-ask-user).
REASON = re.compile(r"reason|in words", re.I)
CONTEXT_TEXT = 1500
SETTLE_WAIT = 60
ABORT_WAIT = 30


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if c.get("type") == "text")


class Run:
    """One `pi --mode rpc` process and its conversation with the relay."""

    def __init__(self, argv, prompt, *, cwd, log, session, run_id, asked="",
                 write_event=lambda row: None, ask=relay_client.ask,
                 annotate=relay_client.annotate,
                 popen=pi_call.popen, clock=time.monotonic, timeout_s=12 * 3600,
                 env=None):
        self.argv, self.prompt, self.cwd, self.log = list(argv), prompt, cwd, log
        self.session, self.run_id, self.asked = session, run_id, asked
        self.write_event, self.relay_ask = write_event, ask
        self.relay_annotate = annotate
        self.lines: list = []                      # the annotator's latest pair
        self.open_ask_id = None                    # the ask on screen, if any
        self.popen, self.clock, self.timeout_s = popen, clock, timeout_s
        # The account overlay the job declares (2b): `pi_call.popen` puts it on top
        # of this process's environment, a None value meaning "unset".
        self.env = env
        self.events: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.open_asks = 0
        self.waited = 0.0
        self.wait_since = None
        self.reason = None                         # a worded reply waiting for its input
        self.last_text = ""
        self.last_error = ""
        self.asks = 0

    # --- I/O -------------------------------------------------------------------

    def _note(self, line: str) -> None:
        with self.lock:
            self.log.write(line.rstrip("\n") + "\n")
            self.log.flush()

    def _send(self, obj: dict) -> None:
        with self.lock:
            try:
                self.proc.stdin.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
                self.proc.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                pass                               # pi is gone; the main loop sees the exit

    def _read_stdout(self) -> None:
        """Strict LF framing on bytes (json.md: no readline over Unicode separators)."""
        buf = b""
        for chunk in iter(lambda: self.proc.stdout.read1(65536), b""):
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                raw = raw.rstrip(b"\r")
                if raw.strip():
                    try:
                        self.events.put(json.loads(raw))
                    except ValueError:
                        self._note(f"[pi stdout, not JSON] {raw[:300]!r}")
        self.events.put(None)

    def _read_stderr(self) -> None:
        for raw in iter(self.proc.stderr.readline, b""):
            self._note("[pi] " + raw.decode("utf-8", "replace"))

    # --- the waiting clock -----------------------------------------------------

    def _ask_opened(self) -> None:
        with self.lock:
            self.open_asks += 1
            if self.open_asks == 1:
                self.wait_since = self.clock()

    def _ask_closed(self) -> None:
        with self.lock:
            self.open_asks -= 1
            if self.open_asks == 0 and self.wait_since is not None:
                self.waited += self.clock() - self.wait_since
                self.wait_since = None

    def working_seconds(self, started: float) -> float:
        with self.lock:
            waiting = self.waited + (self.clock() - self.wait_since if self.wait_since else 0)
        return self.clock() - started - waiting

    # --- dialogs ---------------------------------------------------------------

    def _dialog(self, req: dict) -> None:
        """Runs in its own thread: the main loop keeps draining stdout meanwhile."""
        method, rid = req.get("method"), req.get("id")
        if method in ("input", "editor") and self.reason is not None:
            text, self.reason = self.reason, None
            self._note(f"[answer] the reason given with the worded reply: {text}")
            self.write_event({"event": "answer", "ask": rid, "value": text,
                              "by": "worded reply", "waited_s": 0})
            self._send({"type": "extension_ui_response", "id": rid, "value": text})
            return
        ask_id = f"{self.session}/{self.run_id}/{rid}"
        kind = {"editor": "input"}.get(method, method)
        title = str(req.get("title") or "")
        if req.get("message"):
            title += "\n" + str(req["message"])
        options = [str(o) for o in req.get("options") or []]
        context = (f"session {self.session}, run {self.run_id}\ncwd {self.cwd}\n"
                   f"{self.asked}\n\nthe agent's last text:\n{self.last_text[-CONTEXT_TEXT:]}"
                   f"\n\nthe request:\n{json.dumps(req, ensure_ascii=False, indent=1)}")
        self.asks += 1
        with self.lock:
            self.open_ask_id = ask_id
            lines = list(self.lines)
        self._note(f"[ask] {ask_id} {kind}: {title}")
        self.write_event({"event": "ask", "ask": ask_id, "kind": kind,
                          "title": title[:2000], "options": options})
        self._ask_opened()
        told = []

        def down(err):
            if not told:
                told.append(err)
                self._note(f"[relay] not reachable ({err}); the ask waits for it")
                self.write_event({"event": "relay_down", "ask": ask_id, "error": str(err)})
        try:
            answer = self.relay_ask({"id": ask_id, "session": self.session, "kind": kind,
                                     "title": title, "options": options, "context": context,
                                     "lines": lines},
                                    on_retry=down)
        except ValueError as e:                    # the relay refused the ask itself
            answer = {"cancelled": True, "error": str(e)}
        finally:
            with self.lock:
                if self.open_ask_id == ask_id:
                    self.open_ask_id = None
            self._ask_closed()
        response = self._response(kind, options, answer)
        self._note(f"[answer] {ask_id}: {json.dumps(response)[:300]}"
                   + (f" (words: {answer['text']})" if answer.get("text") else ""))
        self.write_event({"event": "answer", "ask": ask_id,
                          **{k: answer.get(k) for k in ("value", "confirmed", "cancelled",
                                                         "text", "withdrawn", "by", "waited_s")
                             if answer.get(k) is not None}})
        self._send({"type": "extension_ui_response", "id": rid, **response})

    def _response(self, kind: str, options: list, answer: dict) -> dict:
        if answer.get("cancelled"):
            return {"cancelled": True}
        if kind == "confirm":
            return {"confirmed": bool(answer.get("confirmed"))}
        if kind == "input":
            return {"value": str(answer.get("value") or answer.get("text") or "")}
        if answer.get("value") in options:
            return {"value": answer["value"]}
        words = answer.get("text")
        pick = next((o for o in options if REASON.search(o)), None)
        if words and pick:
            self.reason = words
            return {"value": pick}
        return {"cancelled": True}

    # --- the annotator's lines -------------------------------------------------

    def _widget(self, ev: dict) -> None:
        """One `setWidget`: hold the lines, and edit them into the open ask.

        A missing or empty `widgetLines` is how pi clears a widget: the lines go,
        and the open ask is re-rendered without them so the phone does not keep a
        stale pair under a live prompt.
        """
        if not str(ev.get("widgetKey") or "").startswith(WIDGET_PREFIX):
            return
        lines = [str(x) for x in (ev.get("widgetLines") or []) if str(x).strip()][:LINES_MAX]
        with self.lock:
            self.lines = lines
            ask_id = self.open_ask_id
        self._note(f"[explain] {json.dumps(lines, ensure_ascii=False)[:300]}")
        if ask_id:
            def push(target: str, payload: list) -> None:
                # A relay that predates the `annotate` op (or is down) answers no,
                # and the lines then never reach the phone: say so in the run log,
                # where a missing pair would otherwise look like a quiet success.
                landed = self.relay_annotate(target, payload)
                if not landed:
                    self._note(f"[explain] NOT annotated on the phone ({target}) -- the "
                               f"relay refused or is unreachable; a relay older than "
                               f"item 8g has no `annotate` op")
            threading.Thread(target=push, args=(ask_id, lines), daemon=True).start()

    # --- events ----------------------------------------------------------------

    def _event(self, ev: dict) -> bool:
        """Handle one record; True when pi has settled."""
        kind = ev.get("type")
        if kind == "extension_ui_request":
            if ev.get("method") in DIALOGS:
                threading.Thread(target=self._dialog, args=(ev,), daemon=True).start()
            elif ev.get("method") == "setWidget":
                self._widget(ev)
            elif ev.get("method") == "notify":
                self._note(f"[notify] {ev.get('message') or ev.get('title') or ''}")
        elif kind == "message_end":
            msg = ev.get("message") or {}
            if msg.get("role") == "assistant":
                text = _text_of(msg)
                if text.strip():
                    self.last_text = text
                    self._note(text)
                if msg.get("stopReason") == "error" or msg.get("errorMessage"):
                    self.last_error = str(msg.get("errorMessage") or "error")
                    self._note(f"[error] {self.last_error}")
        elif kind == "tool_execution_start":
            args = json.dumps(ev.get("args") or {}, ensure_ascii=False)
            self._note(f"[tool] {ev.get('toolName', '?')} {args[:300]}")
        elif kind in ("auto_retry_start", "extension_error"):
            self._note(f"[{kind}] {ev.get('errorMessage') or ev.get('error') or ''}")
        elif kind == "response" and ev.get("success") is False:
            self.last_error = str(ev.get("error") or "the prompt was refused")
            self._note(f"[error] {self.last_error}")
            return True
        elif kind == "agent_settled":
            return True
        return False

    # --- the run ---------------------------------------------------------------

    def run(self) -> dict:
        # `harness/pi_call.popen` is the one place a pi process starts; it owns the
        # pipes and the environment (pi.md §Starting a pi process).
        self.proc = self.popen(self.argv, cwd=self.cwd, env=self.env)
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        started = self.clock()
        self._send({"id": "prompt", "type": "prompt", "message": self.prompt})
        settled = timed_out = False
        while True:
            try:
                ev = self.events.get(timeout=1.0)
            except queue.Empty:
                ev = ...
            if ev is None:                         # stdout closed: pi exited
                break
            if ev is not ... and self._event(ev):
                settled = True
                break
            if self.working_seconds(started) > self.timeout_s:
                timed_out = True
                self._note(f"[familiar] timeout after {self.timeout_s}s of work "
                           f"(waiting excluded) -- aborting")
                self._send({"type": "abort"})
                break
        try:
            self.proc.stdin.close()                # an orderly shutdown (rpc.md)
        except OSError:
            pass
        try:
            code = self.proc.wait(timeout=ABORT_WAIT if timed_out else SETTLE_WAIT)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = self.proc.wait()
        if timed_out:
            code = 124
        elif settled and code == 0 and self.last_error:
            code = 1                               # the model call failed; say so in the exit
        return {"exit": code, "settled": settled, "timed_out": timed_out, "asks": self.asks,
                "waited_s": round(self.waited, 1), "error": self.last_error}


def drive(argv, prompt, **kw) -> dict:
    return Run(argv, prompt, **kw).run()
