"""ranking -- F, U, R and the quadrant. The arithmetic of memory-ranking.md.

PURE. Reads frontmatter, returns numbers, writes nothing. Stage 3 is a pure
function of the tree precisely so its output can be regenerated and diffed
without touching git history.

EVERY CONSTANT BELOW IS A FIRST ESTIMATE. The skill-usage log held 2 lines when
they were chosen, one of them a test. `unvalidated()` names them so the report
can say so out loud instead of presenting a score as a measurement. Do not tune
them by intuition -- M2 Task 7: run report-only for at least two weeks, then
revisit against the log.
"""
from __future__ import annotations

import datetime as dt
import math

import pathlib

from consolidation import activity
from consolidation import ledger
from knowledge.tree import Doc, documents

# Freshness half-life per stability compartment, days. Four compartments rather
# than two, from Wang et al.'s Drosophila gamma-lobe mapping: a spectrum of
# decay rates beats one tuned compromise, which is simultaneously too fast for
# settled facts and too slow for volatile ones.
HALF_LIFE = {"permanent": None, "stable": 365, "evolving": 90, "volatile": 30}
SKILL_DEFAULT_H = 180

C_REF = 10                  # use_count saturation reference in u_mag
U_RECENCY_H = 180           # days, half-life of u_rec
COLD_START_DAYS = 60        # younger than this -> U undefined, exempt
                            #   also counted in ACTIVE days, for the same
                            #   reason: a leaf written before a long break has
                            #   not had 60 days of chances to be used.

TRUST_GATE = {"trusted": 1.0, "trial": 0.7, "quarantine": 0.0, "deprecated": 0.0}
WEIGHTS = {"knowledge": (0.60, 0.40),   # staleness primary: a wrong fact is the harm
           "skill": (0.35, 0.65)}       # disuse primary: use_count governs lifecycle

# NOT SPECIFIED IN memory-ranking.md. The quadrant table says "low"/"high" and
# never says where the line is. 0.5 is the midpoint of [0,1] and nothing more --
# it is the single most arbitrary number in the pass, and it decides which
# quadrant a document lands in, so it is reported as unvalidated.
QUADRANT_MIDPOINT = 0.5


def unvalidated() -> list[str]:
    return [
        f"H = {HALF_LIFE} d, skills {SKILL_DEFAULT_H} d  (stability half-lives)",
        f"C_ref = {C_REF}  (use_count saturation)",
        f"u_rec half-life = {U_RECENCY_H} d",
        f"cold start = {COLD_START_DAYS} d",
        f"weights knowledge {WEIGHTS['knowledge']}, skills {WEIGHTS['skill']}",
        f"quadrant midpoint = {QUADRANT_MIDPOINT}  (not in the spec at all)",
        f"opaque dismissal TTL = {ledger.OPAQUE_TTL_DAYS} d  (time-box, not a hash)",
    ]


def date_of(v):
    """A frontmatter date value -> `datetime.date`, or None when it will not
    parse.

    PUBLIC because the conflict stage compares `last_verified` values across
    leaves, and it must read a date exactly as the ranking does. Two parsers
    over the same field is how the branch ordering in the report and the branch
    ordering in the conflict table start disagreeing about which of two leaves
    is the later one.
    """
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v).strip().split()[0])
    except (ValueError, IndexError):
        return None


def freshness(doc, today: dt.date):
    """F in [0,1], or (None, reason) when it must not be computed.

    Missing last_verified -> F is UNDEFINED, not zero. The leaf is flagged
    never-verified and exempt from pruning: you cannot prune on a signal that
    was never collected, and a fake number here is indistinguishable from a
    real one six months later.
    """
    lv = date_of(doc.get("last_verified"))
    if lv is None:
        return None, "never-verified"
    stability = (doc.get("stability") or "").strip()
    if doc.kind == "skill" and not stability:
        h = SKILL_DEFAULT_H
    elif stability == "permanent":
        return 1.0, None
    elif stability in HALF_LIFE:
        h = HALF_LIFE[stability]
    else:
        h = SKILL_DEFAULT_H if doc.kind == "skill" else HALF_LIFE["evolving"]
    delta = (today - lv).days
    if delta < 0:
        return 1.0, "verified-in-future"
    return 2.0 ** (-delta / h), None


def utility(doc, today: dt.date, active: frozenset | None = None):
    """U in [0,1], or (None, reason).

    Cold-start exemption: a document younger than 60 days has U undefined.
    Without it everything written last week is the top pruning candidate --
    the standard failure of usage-based memory maintenance.
    """
    if doc.created:
        age = (activity.count_between(active, doc.created, today) if active
               else (today - doc.created).days)
        if age < COLD_START_DAYS:
            return None, "cold-start"
    try:
        count = int(str(doc.get("use_count", 0) or 0).strip())
    except ValueError:
        count = 0
    u_mag = min(1.0, math.log(1 + count) / math.log(1 + C_REF))
    lu = date_of(doc.get("last_used"))
    if lu is None:
        return (0.0, None) if count == 0 else (u_mag * 0.5, "used-never-dated")
    # ACTIVE days, not calendar days. A leaf must not be demoted for days the
    # laptop was closed -- there was no opportunity to use it, so idle time is
    # not evidence of disuse. See activity.py; F deliberately still uses
    # calendar days, because the world drifts while you are away.
    if active is None:
        delta = max(0, (today - lu).days)
    else:
        delta = activity.count_between(active, lu, today)
    u_rec = 2.0 ** (-delta / U_RECENCY_H)
    return u_mag * u_rec, None


def quadrant(f, u):
    """The action state. Exempt when either component is undefined -- a leaf
    that is never-verified or inside the cold-start window is exempt from BOTH
    columns of the table, per the hard rules in memory-ranking.md."""
    if f is None or u is None:
        return "exempt"
    m = QUADRANT_MIDPOINT
    if f < m and u >= m:
        return "re-verify"        # used, but probably stale -- highest priority
    if f >= m and u < m:
        return "demote"           # true, but nobody needs it
    if f < m and u < m:
        return "archive"          # stale and unused
    return "healthy"


def score(doc, today: dt.date, active: frozenset | None = None) -> dict:
    f, f_note = freshness(doc, today)
    u, u_note = utility(doc, today, active)
    t = TRUST_GATE.get((doc.get("trust") or "").strip(), 1.0)
    w_f, w_u = WEIGHTS[doc.kind]
    r = None
    if f is not None and u is not None:
        r = t * (w_f * f + w_u * u)
    return {
        "F": f, "U": u, "T": t, "R": r,
        "quadrant": quadrant(f, u),
        "exempt": [n for n in (f_note, u_note) if n],
        "human": (doc.get("authority") or "").strip() == "human",
    }


def score_all(docs, today: dt.date, active: frozenset | None = None) -> None:
    for d in docs:
        d.scores = score(d, today, active)


# -- the scored view ----------------------------------------------------------
#
# `load()` returns a ScoredTree, never a bare list. A document that has been
# loaded has been scored: "unscored" is not a state a stage can observe, and so
# not a state a stage can misreport. Before this seam existed, three stages
# lazily re-loaded an unscored list, stage 3 replaced it wholesale, and stage 6
# -- which cannot tell an exempt document from an unscored one -- reported
# `run --stages=5,6` as "all N documents are exempt ... the correct state for a
# tree this young", which was false.
#
# THE ONE MUTATION: `rescore()`. Stage 2 writes the frontmatter that R is
# computed from, so it, and only it, re-scores after writing. Everything else
# reads. Moved here from `tree.py` in R2c: the walk is the record's, the score
# is the pass's.

class ScoredTree:
    """The scored universe, behind one interface.

    Every accessor answers a question a stage actually asks. A stage that needs
    a question this does not answer should get a method here, not a list
    comprehension over `all()` -- the point of the seam is that the denominator
    is defined once.
    """

    __slots__ = ("_docs", "_today", "_active")

    def __init__(self, docs: list[Doc], today: dt.date, active: frozenset):
        self._docs = docs
        self._today = today
        self._active = active
        self.rescore()

    # -- the one mutation --------------------------------------------------
    def rescore(self) -> None:
        """Re-apply the ranking. For stage 2 alone, after it has written the
        frontmatter R is derived from; every other stage reads."""
        score_all(self._docs, self._today, self._active)

    # -- population --------------------------------------------------------
    def __len__(self) -> int:
        return len(self._docs)

    def __iter__(self):
        return iter(self._docs)

    def all(self) -> list[Doc]:
        return list(self._docs)

    def leaves(self) -> list[Doc]:
        return [d for d in self._docs if d.kind == "knowledge"]

    def skills(self) -> list[Doc]:
        return [d for d in self._docs if d.kind == "skill"]

    @property
    def active_days(self) -> frozenset:
        """The days utility decayed over. Reported, not just used: a number
        derived from an empty activity record must not read as measured."""
        return self._active

    # -- scores ------------------------------------------------------------
    def scorable(self) -> list[Doc]:
        """Documents with a defined R, weakest first. Everything else is exempt
        -- never-verified or inside the cold-start window -- and exempt means
        exempt from BOTH columns of the quadrant table."""
        return sorted((d for d in self._docs if d.scores.get("R") is not None),
                      key=lambda d: d.scores["R"])

    def exempt(self) -> list[Doc]:
        return [d for d in self._docs if d.scores.get("R") is None]

    def exempt_for(self, reason: str) -> list[Doc]:
        """never-verified | cold-start | used-never-dated | verified-in-future"""
        return [d for d in self._docs if reason in d.scores.get("exempt", ())]

    def bottom(self, fraction: float) -> list[Doc]:
        """The weakest slice BY RANK, never by an absolute R threshold: a cutoff
        calibrated at 40 leaves guts the tree at 400 (downscale.py)."""
        scored = self.scorable()
        if not scored:
            return []
        return scored[:max(1, int(len(scored) * fraction))]

    def ranked(self) -> list[Doc]:
        """Report order: exempt first, then ascending R."""
        return sorted(self._docs,
                      key=lambda d: (d.scores["R"] is not None,
                                     d.scores["R"] if d.scores["R"] is not None else 0))


def load(agents_dir: pathlib.Path, base_dir: pathlib.Path,
         today: dt.date) -> ScoredTree:
    """Load and score in one step. There is no way to get an unscored tree."""
    docs = documents(agents_dir)
    return ScoredTree(docs, today, activity.active_days(base_dir, agents_dir.parent))
