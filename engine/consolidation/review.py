"""review -- the decision queue walked from the phone, one relay ask per item (dev/remote R6d).

DESIGN A (the user, 2026-10-23). The walker is a CLIENT of the relay's `ask`,
not a relay feature: the relay stays standard library and blind to
consolidation, and everything the phone needs -- buttons, a reply in words, an
answer stored across a relay restart -- already exists there. This module only
decides what to ask and hands the answer to `resolve.apply`, the same writer
`decide` uses.

THE SHAPE OF ONE ITEM. A select ask: the item's own choices (`resolve.choices`)
plus Skip and Stop; `why` behind the relay's More button. A reply in words
instead of a tap is a Note -- the free-text field the user asked for, without a
second message. `superseded` asks a follow-up: the other open decisions as
buttons, or a reply naming any id.

ASK IDS. `review:<run>:<item>:<step>`. The run id lives in `review.json` under
the data dir, so `--resume` re-attaches to the ask already on the phone (the
relay answers a re-ask with the open ask, or with the answer it stored while
the walker was gone) instead of sending it twice. A fresh `/review` mints a new
run, so an item skipped last time is asked again, and withdraws the previous
run's open ask so the phone never holds two live reviews.

STALENESS BY ID, not by digest. `decide`'s digest guards an ORDINAL a user read
earlier; the walk never shows an ordinal. Before each write it re-reads the
queue and resolves the item by its stable id -- if another surface resolved it
meanwhile, or the nightly pass rewrote the queue, the item is skipped, never
written twice.
"""
from __future__ import annotations

import fcntl
import json
import os
import secrets
import shutil
import subprocess
import sys

from consolidation import queue, resolve
from lib import invocation

SPEC = invocation.Spec(name="review", usage="review --remote [--detach] [--resume]",
                       flags=("--remote", "--detach", "--resume"))
STATE = "review.json"
LOCK = "review.lock"
SESSION = "review"
UNIT = "familiar-review"
OTHER = "Other (reply with the id)"


def _relay_ask(req: dict) -> dict:
    from relay import client                                  # noqa: PLC0415
    return client.ask(req)


def _relay_request(req: dict) -> dict:
    try:
        from relay import client                              # noqa: PLC0415
        return client.request(req, timeout=5)
    except Exception as exc:                                  # noqa: BLE001 -- best effort
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


class Walker:
    """One walk over the open queue. `ask` blocks until answered; `request`
    sends withdraw/notify. Both are replaced in a test."""

    def __init__(self, base, repo, *, run: str, ask=_relay_ask, request=_relay_request):
        self.base, self.repo, self.run = base, repo, run
        self.ask, self.request = ask, request
        self.done = {"resolved": 0, "noted": 0, "skipped": 0}
        self.landed = 0

    def _save(self, current: str = "") -> None:
        (self.base / STATE).write_text(json.dumps({"run": self.run, "current": current}))

    def _ask(self, item_id: str, step: str, **req) -> dict:
        ask_id = f"review:{self.run}:{item_id}:{step}"
        self._save(ask_id)
        ans = self.ask({"id": ask_id, "session": SESSION, **req})
        self._save("")
        return ans

    def _open(self) -> list:
        return queue.unresolved(queue.items(self.base))

    def walk(self) -> str:
        """Ask every open item once; a one-line account of what happened."""
        seen = set()
        total = len(self._open())
        while True:
            todo = [it for it in self._open() if it["id"] not in seen]
            if not todo:
                break
            it = todo[0]
            seen.add(it["id"])
            if self.item(it, len(seen), total) == "stop":
                left = len([x for x in self._open() if x["id"] not in seen]) + 1
                return (f"review stopped: {self._tally()}; {left} left. "
                        f"/review to continue.")
        return f"review finished: {self._tally()}."

    def _tally(self) -> str:
        d = self.done
        return f"{d['resolved']} resolved, {d['noted']} noted, {d['skipped']} skipped"

    def item(self, it: dict, n: int, total: int) -> str:
        opts = list(resolve.choices(it))
        labels = [resolve.LABELS[c] for c in opts] + ["Skip", "Stop"]
        nights = f"  (night {it['nights']})" if it.get("nights", 1) > 1 else ""
        title = f"{n}/{total}  {it['kind']}  {it['target']}{nights}\n\n{it.get('summary', '')}"
        ans = self._ask(it["id"], "0", kind="select", title=title, options=labels,
                        context=it.get("why") or "")
        if ans.get("cancelled"):
            return "stop"
        value, text = ans.get("value"), (ans.get("text") or "").strip()
        if value is None and text:
            # A reply in words: a note where a note exists, else nothing is guessed.
            choice, note, by = ("note", text, "") if "note" in opts else ("", "", "")
            if not choice:
                self.done["skipped"] += 1
                return "skip"
        elif value in ("Skip", "Stop"):
            if value == "Skip":
                self.done["skipped"] += 1
            return value.lower()
        else:
            choice = opts[labels.index(value)]
            note, by = "", ""
            if choice == "superseded":
                by = self._superseded_by(it)
                if not by:
                    self.done["skipped"] += 1
                    return "skip"
            elif choice == "note":
                note = (self._ask(it["id"], "note", kind="input",
                                  title=f"Note on {it['target']}:").get("value") or "").strip()
                if not note:
                    self.done["skipped"] += 1
                    return "skip"
        current = next((x for x in self._open() if x["id"] == it["id"]), None)
        if current is None:                     # resolved elsewhere meanwhile
            self.done["skipped"] += 1
            return "skip"
        try:
            resolve.apply(self.base, self.repo, current, choice, note=note, by=by,
                          via="telegram")
        except ValueError:
            self.done["skipped"] += 1
            return "skip"
        self.done["noted" if choice == "note" else "resolved"] += 1
        self.landed += choice == "land"
        return choice

    def _superseded_by(self, it: dict) -> str:
        others = [x for x in self._open() if x["kind"] in resolve.DECISION_KINDS
                  and x["id"] != it["id"]][:8]
        labels = [f"{x['target']}: {x.get('summary', '').split(': ', 1)[-1]}"[:60]
                  for x in others] + [OTHER]
        ans = self._ask(it["id"], "by", kind="select",
                        title=f"{it['target']} is superseded by:", options=labels)
        if ans.get("cancelled"):
            return ""
        value, text = ans.get("value"), (ans.get("text") or "").strip()
        if value is None:
            return text.split()[0] if text else ""
        if value == OTHER:
            return (self._ask(it["id"], "by-id", kind="input",
                              title="The id that supersedes it:").get("value") or "").strip()
        return others[labels.index(value)]["target"]


def _detach(inv) -> int:
    """Start the walk as a transient user unit and return at once: `/review`
    runs under the relay's 20 s command timeout, and a walk waits for hours."""
    exe = shutil.which("systemd-run")
    if not exe:
        print("systemd-run not found; run `familiar consolidation review --remote`",
              file=sys.stderr)
        return 1
    familiar = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "familiar")
    argv = [exe, "--user", "--collect", f"--unit={UNIT}", "--quiet",
            f"--setenv=PAZRAS_DATA_DIR={inv.base}", sys.executable, familiar,
            "consolidation", "review", "--remote"] + (["--resume"] if inv.has("--resume") else [])
    p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode:
        if "already" in (p.stderr or "") or "exists" in (p.stderr or ""):
            print("a review is already running -- answer the ask on your phone")
            return 0
        print(f"could not start the review: {(p.stderr or '').strip()[:200]}")
        return 1
    n = len(queue.unresolved(queue.items(inv.base)))
    print(f"review started: {n} open item(s); the first ask follows.")
    return 0


def schedule_landing(base, repo) -> str:
    """R6e, replaced in a test: one landing job for what the walk said to land."""
    from consolidation import land                            # noqa: PLC0415
    return land.schedule(base, repo)


def main(inv, *, ask=_relay_ask, request=_relay_request) -> int:
    if not inv.has("--remote"):
        print(f"usage: familiar consolidation {SPEC.usage}", file=sys.stderr)
        return 1
    if inv.has("--detach"):
        return _detach(inv)
    base = inv.base
    base.mkdir(parents=True, exist_ok=True)
    lock = open(base / LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("a review is already running", file=sys.stderr)
        return 1
    try:
        prev = json.loads((base / STATE).read_text())
    except (OSError, ValueError):
        prev = {}
    if inv.has("--resume") and prev.get("run"):
        run = prev["run"]
    else:
        run = secrets.token_hex(4)
        if prev.get("current"):
            request({"op": "withdraw", "id": prev["current"],
                     "reason": "a new review started"})
    if not queue.unresolved(queue.items(base)):
        request({"op": "notify", "session": SESSION, "text": "Nothing waits on you."})
        return 0
    w = Walker(base, inv.agents.parent, run=run, ask=ask, request=request)
    msg = w.walk()
    if w.landed:
        msg += "\n" + schedule_landing(base, inv.agents.parent)
    request({"op": "notify", "session": SESSION, "text": msg})
    print(msg)
    return 0
