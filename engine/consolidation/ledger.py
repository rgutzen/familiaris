"""ledger -- the append-only JSON-lines logs, and the two mechanisms built on them.

ONE READER, ONE POLICY. "Append a row; read it back tolerantly, skipping what
will not parse" was written five times: `aggregate._read_log` counted malformed
lines and warned, `associate` dropped them in silence, `activity` dropped them
again, and `decisions`/`dismissals` each carried a third copy. The same file
therefore yielded different denominators to different stages, and the pass's
rule that a limit must be stated rather than implied held in exactly one of
them. `_boundaries.py` already applies the fix this module copies: one
implementation of what the format means, shared by everyone who reads it.

WHO REPORTS. `read()` counts malformed lines and returns the count; it never
notes, warns or raises. A stage decides what a skipped line means in its own
terms -- which keeps this module a pure function of a file, testable without a
`Pass`, and stops two stages double-reporting one file.

WHAT IS NOT HERE. `session.log` is TSV, not JSON lines, and its only reader
wants dates rather than rows; covering it would widen this interface for a
caller that does not want it. Transcripts are the verbatim tier, read under a
budget by `transcripts.py`. `last-run.json` is one state object, not a log.

WHAT WRITES BUT CANNOT IMPORT THIS. `capture.py` appends to `skill-usage.jsonl`
by hand-rolled string interpolation, because it runs on the user's latency
budget and may not import `json` (see its module docstring). Two writers of one
format that cannot share code is the drift `selftest --schema` exists to catch:
`USAGE_FIELDS` below is the read side's declaration of that contract.
"""
from __future__ import annotations

import calendar
import dataclasses
import hashlib
import json
import pathlib
import time

from lib import roots

# The ledger set. `preflight` fingerprints these to decide an idle day, so a new
# ledger added here is a new ledger the idle check can see -- which it could not
# when the list lived as a literal tuple in that module.
USAGE = "skill-usage.jsonl"
DECISIONS = "decisions.jsonl"
DISMISSALS = "dismissals.jsonl"
FILES = (USAGE, DECISIONS, DISMISSALS)

# What `capture.py` is contracted to write, declared on the READ side because
# the writer cannot import it. Enforced by `familiar checks selftest --schema`.
USAGE_FIELDS = ("ts", "harness", "skill", "session", "cwd",
                "signal", "caller", "terms")
# Lines written before 2026-08-30 carry only these. They are VALID and must stay
# readable: they are most of the real usage data this system has. A reader that
# demands the full field set would silently drop them -- see aggregate.py, which
# counts them and declines to classify rather than guessing a `signal`.
USAGE_FIELDS_LEGACY = ("ts", "harness", "skill", "session", "cwd")

KINDS = ("decision", "disagreement")

# What a proposal's `target` names. `leaf` targets are files under memory/ and
# self-clear by content hash (see record_dismissal); `opaque` targets are not
# files (an invocation name, a link pair, a decision id) and have
# no content to change, so their dismissals are time-boxed instead.
TARGET_KINDS = ("leaf", "opaque")

# How long an opaque dismissal lasts. First estimate, unvalidated -- like every
# constant feeding R, it must be flagged for the user rather than tuned by
# intuition. A dismissed opaque proposal returns no sooner than the source
# material that would re-derive it (consolidate.RECENT_DAYS is 14), but 14 was
# judged too short for a "never adopt this skill": ~a month of quiet per "no".
OPAQUE_TTL_DAYS = 30


def path(base, name: str) -> pathlib.Path:
    return pathlib.Path(base) / name


# ── the format ───────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Rows:
    """What one ledger holds, plus what could not be read.

    `malformed` is part of the answer, not an error: a truncated line from a
    killed hook is expected, and the honest report is "N lines, M unreadable",
    never a quietly smaller N.
    """
    rows: list[dict]
    malformed: int
    path: pathlib.Path

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def field(self, key: str) -> list:
        """Every present, non-empty value of one key, in file order."""
        return [r[key] for r in self.rows if r.get(key)]


def read(base, name: str) -> Rows:
    """Read one ledger. Never raises: an absent file is an empty ledger."""
    p = path(base, name)
    try:
        text = p.read_text()
    except OSError:
        return Rows([], 0, p)
    rows, malformed = [], 0
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            malformed += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            malformed += 1          # a bare scalar is not a ledger row
    return Rows(rows, malformed, p)


def append(base, name: str, row: dict) -> None:
    """One row, one line. The only write path in this module."""
    p = path(base, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_ts(s) -> float | None:
    """ISO-UTC timestamp -> epoch seconds, or None when it will not parse."""
    try:
        return calendar.timegm(time.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return None


def _within_ttl(ts, days: int, now: str) -> bool:
    """True while `ts` sits inside the window ending at `now`.

    An unreadable or missing ts is NOT within the window -- the dismissal
    lapses and the proposal resurfaces. Fail toward surfacing, never a blind.
    """
    t, n = _parse_ts(ts), _parse_ts(now)
    if t is None or n is None:
        return False
    age = n - t
    return 0 <= age < days * 86400


# ── decisions ────────────────────────────────────────────────────────────────
# ROADMAP Track M, M2 exit criteria 10 and 11, required by
# `knowledge/conventions/collaboration.md` §Asking (Learning) and §Disagreement
# (Persistence).
#
#   decision      a decision of the user's that settles a recurring question, so
#                 a later session does not re-ask it
#   disagreement  a push-back the agent was overruled on after two rounds,
#                 recorded so both parties can refer back
#
# HONEST LIMIT: this is LEVEL 4 in the memory-mechanisms.md enforcement table.
# No hook can detect that the user just settled a recurring question, so an agent
# must choose to call it. Level 4 is advisory and skippable under context
# pressure -- writing "always record decisions" in a CONTEXT.md and calling it
# enforced is exactly the failure that table exists to prevent. What IS enforced
# is the second half: once a line is here, the nightly pass surfaces it every
# night until it lands somewhere durable. Capture is advisory; not-losing-it is
# not.

def record_decision(base, kind: str, text: str, context: str = "",
                    session: str = "") -> str:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    ts = _now()
    # A short stable id so the pass can tell whether the decision has landed
    # anywhere durable, and stop nagging once it has.
    did = f"{kind[:3]}-{abs(hash((ts, text))) % 10**8:08d}"
    append(base, DECISIONS, {"id": did, "ts": ts, "kind": kind, "text": text,
                             "context": context, "session": session})
    return did


# ── dismissals ───────────────────────────────────────────────────────────────
# THE PROBLEM THIS SOLVES. Stage 4 distils from journal entries, which do not
# change when a proposal is acted on. So a proposal accepted at noon is proposed
# again that night, and every night, until its source entries age out of the
# 14-day window. Sending the model each leaf's section headings helped and did
# not fix it: headings say which TOPICS a leaf covers, not which FACTS are in it.
#
# A report that repeats yesterday's resolved proposals is a report that stops
# being read -- and `consolidation-cycle.md` names the unread report as the
# failure mode this design is most exposed to. So the ledger is not tidiness; it
# protects the one property the pass cannot survive losing.
#
# SELF-CLEARING BY DESIGN. A dismissal records the target leaf's content hash. If
# the leaf changes later, the dismissal lapses and the topic may be proposed
# again -- because a leaf that has moved on may genuinely warrant new material.
# A permanent "never mention this again" would silently blind the pass instead.

def leaf_hash(repo, target: str) -> str:
    """Content hash of the leaf a dismissal names, or "" when there is no file.

    `target` arrives in two shapes and both are real: a PATH when the proposer
    knew it (`knowledge/system/boundaries/boundaries.md`) and a bare NAME when it did
    not (`knowledge-vs-skills`, which the dangling-link check raises precisely
    because no such leaf resolves). The name case is tried as a `.md` leaf too,
    because that is what a name means in this tree.
    """
    root = pathlib.Path(repo) / roots.MEMORY_REL
    names = [target.lstrip("/")]
    if not target.endswith(".md"):
        names.append(names[0] + ".md")
    for name in names:
        try:
            return hashlib.sha256((root / name).read_bytes()).hexdigest()[:16]
        except OSError:
            continue
    return ""


def record_dismissal(base, repo, target: str, kind: str, note: str = "",
                     target_kind: str = "leaf") -> str:
    if target_kind not in TARGET_KINDS:
        raise ValueError(f"target_kind must be one of {TARGET_KINDS}")
    if target_kind == "opaque":
        # No file to hash: an opaque target hashes to "" unconditionally and
        # "" == "" would suppress it forever. Time-box instead (see covers).
        append(base, DISMISSALS, {"ts": _now(), "target": target, "kind": kind,
                                  "target_kind": "opaque", "note": note})
        return ""
    sha = leaf_hash(repo, target)
    append(base, DISMISSALS, {"ts": _now(), "target": target, "kind": kind,
                              "target_kind": "leaf", "leaf_sha": sha,
                              "note": note})
    return sha


class Dismissals:
    """Read once, asked many times.

    Stage 4 tests every proposal the model returned, and the old
    `is_dismissed(...)` re-read and re-parsed the whole file per call. The read
    is now explicit and happens once; `covers` is pure arithmetic over what was
    read, plus one hash of the target leaf.
    """

    __slots__ = ("_rows", "malformed")

    def __init__(self, rows: Rows):
        self._rows = rows.rows
        self.malformed = rows.malformed

    def __len__(self) -> int:
        return len(self._rows)

    def covers(self, repo, target: str, kind: str, target_kind: str = "leaf",
               now: str | None = None) -> bool:
        """True only while the dismissal still holds.

        A leaf dismissal self-clears by content hash: it covers while the file
        still reads as it did when dismissed, and lapses once the leaf changes.
        An opaque dismissal has no file to change, so it covers only while
        inside its time window -- never permanently, because a permanent
        "never mention this again" would silently blind the pass.
        """
        if target_kind not in TARGET_KINDS:
            raise ValueError(f"target_kind must be one of {TARGET_KINDS}")
        if target_kind == "opaque":
            cutoff = now if now is not None else _now()
            return any(r.get("target") == target and r.get("kind") == kind
                       and r.get("target_kind") == "opaque"
                       and _within_ttl(r.get("ts"), OPAQUE_TTL_DAYS, cutoff)
                       for r in self._rows)
        cur = leaf_hash(repo, target)
        # A TARGET THAT RESOLVES TO NO FILE MUST NOT SUPPRESS FOREVER. This is
        # the same hole the opaque branch above closes, and it is reachable: the
        # `dangling-link` check raises proposals whose target is a leaf name
        # that does not exist yet, so `leaf_hash` returns "" -- and "" == ""
        # would cover that proposal on every future night, for good. The check
        # exists to send a proposal back to the queue when the world moves; a
        # fact about a file that is not there is not a fact that can change.
        # Treated as time-boxed, on the same terms as an opaque target.
        if not cur:
            cutoff = now if now is not None else _now()
            return any(r.get("target") == target and r.get("kind") == kind
                       and r.get("target_kind", "leaf") == "leaf"
                       and not r.get("leaf_sha")
                       and _within_ttl(r.get("ts"), OPAQUE_TTL_DAYS, cutoff)
                       for r in self._rows)
        # Legacy rows carry no target_kind; they are leaves. A leaf lookup can
        # never match an opaque row and vice versa.
        return any(r.get("target") == target and r.get("kind") == kind
                   and r.get("target_kind", "leaf") == "leaf"
                   and r.get("leaf_sha") == cur for r in self._rows)


def dismissals(base) -> Dismissals:
    return Dismissals(read(base, DISMISSALS))
