"""resolve -- what each queue kind can be answered with, and the one writer per answer.

WHY ITS OWN MODULE (dev/remote R6c). Three surfaces resolve queue items: `decide
N`, the terminal walk, and the phone's review (`review.py`). Each used to know
only accept/refuse, which fit a dismissal proposal and did not fit the item the
queue holds most of: "decision X has not landed anywhere durable". Accepting
that recorded a 30-day dismissal and landed nothing. The answers that mean
something there are different, so the choices are declared per kind here, once,
and every surface reads this table rather than growing its own.

THE CHOICES for a decision or an overruled disagreement:

* `land` -- the decision is right and should be written down. The item is
  resolved and queued in `landing.jsonl`, which the landing job (R6e) drains by
  writing each decision into the leaf or SPECS line it governs. Stage 4 sees
  the id in a leaf and stops raising it; until then the resolution holds it.
* `superseded` -- a later decision replaced it. Retired for good (`ledger`'s
  `retired` row), with the superseding id in the note.
* `drop` -- it should not land. Retired for good.
* `note` -- free text, appended to `review-notes.jsonl`; the item stays open.

Every other kind keeps `accept` / `refuse`, through `dismiss`'s semantics.
`skip` and `stop` are walk controls, not resolutions, and write nothing.
"""
from __future__ import annotations

import datetime as dt

from consolidation import ledger, queue

LANDING = "landing.jsonl"
NOTES = "review-notes.jsonl"

DECISION_KINDS = ("decision", "disagreement")
DECISION_CHOICES = ("land", "superseded", "drop", "note")
DEFAULT_CHOICES = ("accept", "refuse")
CONTROLS = ("skip", "stop")

#: A button's label per choice -- the phone shows these, the terminal their first letter.
LABELS = {"land": "Land it", "superseded": "Superseded by…", "drop": "Drop",
          "note": "Note", "accept": "Accept", "refuse": "Refuse",
          "skip": "Skip", "stop": "Stop"}

# The kinds whose accept goes through `dismiss` (cli.py's list, moved here so
# one module owns it).
DISMISS_KINDS = ("dangling-link", "dangling-supersession", "decision", "adopt", "link")


def choices(item: dict) -> tuple:
    """The resolutions this item accepts, without the walk controls."""
    return DECISION_CHOICES if item.get("kind") in DECISION_KINDS else DEFAULT_CHOICES


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply(base, repo, item: dict, choice: str, *, note: str = "", by: str = "",
          via: str = "cli") -> str:
    """Record one answer through the writer that owns it; a short human string.

    Raises:
        ValueError: `choice` is not one this item's kind accepts, or
            `superseded` without `by`, or `note` without text.
    """
    if choice not in choices(item):
        raise ValueError(f"{item.get('kind')} takes one of {', '.join(choices(item))}, "
                         f"not {choice!r}")
    kind, target = item["kind"], item["target"]
    tkind = item.get("target_kind", "leaf")
    row = {"action": choice, "ts": _now(), "kind": kind, "target": target, "via": via}
    if choice == "note":
        if not note.strip():
            raise ValueError("a note needs text")
        ledger.append(base, NOTES, {"ts": row["ts"], "id": item["id"], "kind": kind,
                                    "target": target, "note": note.strip(), "via": via})
        return "noted (still open)"
    if choice == "land":
        ledger.append(base, LANDING, {"ts": row["ts"], "id": item["id"], "target": target,
                                      "kind": kind, "summary": item.get("summary", ""),
                                      "why": item.get("why", ""), "note": note})
        queue.resolve(base, item["id"], row)
        return "queued for landing"
    if choice in ("superseded", "drop"):
        if choice == "superseded" and not by.strip():
            raise ValueError("superseded needs the id that replaced it")
        why = f"superseded by {by.strip()}" if choice == "superseded" else "dropped"
        ledger.record_dismissal(base, repo, target, kind,
                                (why + (f": {note}" if note else "")),
                                target_kind="opaque", retired=True)
        if by:
            row["by"] = by.strip()
        queue.resolve(base, item["id"], row)
        return why
    if kind in DISMISS_KINDS:
        ledger.record_dismissal(base, repo, target, kind, note, target_kind=tkind)
    queue.resolve(base, item["id"], row)
    return {"accept": "accepted", "refuse": "refused"}[choice]


def pending_landings(base) -> list:
    """Rows of `landing.jsonl` whose decision has not landed yet -- the landing
    job's input. A landed id is one stage 4 no longer raises, which the caller
    checks against the tree; here only the file is read."""
    return ledger.read(base, LANDING).rows
