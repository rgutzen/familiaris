"""activity -- which days this machine was actually worked on.

WHY THIS EXISTS. `memory-ranking.md` decays utility as
`u_rec = 2^(-Delta_u / 180 d)` on CALENDAR days. That silently punishes a leaf
for days the laptop was closed: come back from three weeks away and the first
pass sees three weeks of "disuse" and proposes demotions, when in fact there
was no opportunity to use anything. Disuse must mean *"not used on a day you
were working"*, not *"time passed"*.

  F stays on calendar days -- the world drifts whether or not you are at the
    machine. Tools update, configs rot, a claim goes stale unattended.
  U counts ACTIVE days only -- you cannot use a skill on a day the machine
    was off, so an idle day is not evidence of anything.

DERIVED, NOT STORED. Active days are recomputed from records that already
exist -- the session log, the skill-usage log, and git commit dates -- so there
is no counter to drift and no state file to lose. Same principle that keeps F
recomputable from `last_verified` alone.
"""
from __future__ import annotations

import datetime as dt
import functools

from lib import git
from consolidation import ledger


def _day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _dates_from_tsv(path) -> set:
    """`session.log` only: ts is the first column. Not a ledger -- see
    ledger.py, which deliberately covers the JSON-lines files alone."""
    out = set()
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.split("\n"):
        if line.strip():
            d = _day(line.split("\t", 1)[0])
            if d:
                out.add(d)
    return out


def _dates_from_ledger(base, name: str) -> set:
    """A malformed line contributes no date and is NOT reported here: the stages
    that read the same ledgers count and report them (ledger.py §WHO REPORTS),
    and this function has no `Pass` to report to."""
    return {d for d in (_day(ts) for ts in ledger.read(base, name).field("ts")) if d}


@functools.lru_cache(maxsize=4)
def active_days(base, repo) -> frozenset:
    """Every date on which this machine shows evidence of work."""
    days = set()
    days |= _dates_from_tsv(base / "session.log")
    days |= _dates_from_ledger(base, ledger.USAGE)
    days |= _dates_from_ledger(base, ledger.DECISIONS)
    days |= git.commit_days(repo)
    return frozenset(days)


def count_between(days: frozenset, start: dt.date, end: dt.date) -> int:
    """Active days in (start, end]. Never negative.

    Falls back to the calendar span when there is no evidence at all -- an
    empty activity record means "we do not know", and inventing zero decay
    would make every leaf look permanently fresh.
    """
    if end <= start:
        return 0
    if not days:
        return (end - start).days
    return sum(1 for d in days if start < d <= end)
