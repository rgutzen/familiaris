"""bands -- three decisions per answer: accept, ask, or drop.

WHAT A BAND IS, AND WHAT IT IS NOT. A band is a DISPOSITION: it orders the queue
and sets what `decide N` does by default. It is never authority. `associate.py`
states that a `related:` name resolving to nothing is a REPORT LINE, not a
deletion; `frontmatter.PROMOTED_TRUST` refuses `trusted` from any stage. A band
that wrote itself would be a write authority smuggled in behind a probability --
so `decide` reads a band to pick its DEFAULT and the keystroke still authorises it.

PROMOTION CANNOT BE BANDED AT ALL. `trust:`, `supersedes:` and `contradicts:` are
written only on an explicit accept (`SPECS.md` §Write authority). Those kinds are
`ask`-only, enforced by `_is_promotion` returning `ASK` before any threshold is
consulted -- not by setting a high threshold, which would still band them under a
per-kind override.

ONE RULE PER PRIMITIVE, STATED ONCE. A Noul thresholds on its probability, a
Choice on the winning option's probability, a Score on the mass of its
action-bearing levels. Stating this in one place is the point: a per-kind
threshold is a tuning knob, not a re-derivation of what the number means.

WHY A TRIPLE AND NOT ONE NUMBER. From the first real distribution
(`PLAN.md` §A first distribution): six kinds landed at 0.18-0.74, one just above
0.5 and another just below, on the same leaf. A single threshold would draw the
line through that spread for no reason the probabilities supply. Two cuts
(`accept_at`, `drop_below`) leave a middle band for exactly the cases the model is
genuinely unsure about -- and an uncertain item stays `ask` rather than being
pushed to one side.

WHY NO FOURTH STATE. `PLAN.md` §The queue fixes the surface at three bands:
`accept` sorts to the top, `ask` is marked `needs you`, `drop` collapses to the
bottom. A refused item is still numbered and still reachable (`decide N --no`).
"""
from __future__ import annotations

import dataclasses

from harness import jev_schemas

ACCEPT, ASK, DROP = "accept", "ask", "drop"
BANDS = (ACCEPT, ASK, DROP)


@dataclasses.dataclass(frozen=True)
class Triple:
    """Two cuts over [0, 1]. `accept_at` must exceed `drop_below`.

    `accept_at`: at or above this, the recommendation is "do the thing".
    `drop_below`: below this, the recommendation is "do not".
    Between them: no recommendation, and the item is marked `needs you`.
    """
    accept_at: float
    drop_below: float

    def __post_init__(self):
        if not (0.0 <= self.drop_below <= self.accept_at <= 1.0):
            raise ValueError(
                f"thresholds must satisfy 0 <= drop_below <= accept_at <= 1: "
                f"got drop_below={self.drop_below}, accept_at={self.accept_at}")


# THE SHARED TRIPLE. A first estimate, and it is flagged as such rather than
# tuned by intuition -- the same rule every constant feeding R carries
# (`ranking.unvalidated`). It is wide on purpose: of the six kinds measured,
# only one sat outside [0.3, 0.7], so this puts most items in `ask`, which is the
# honest disposition while the calibration population does not exist.
#
# Set from consequences, not from the probability (PLAN.md §The record). The
# consequence of a wrong `accept` here is a proposal the user must notice and
# refuse; the consequence of a wrong `drop` is a real gap never surfaced again
# until the leaf changes. The asymmetry is why `drop_below` is low: dropping is
# the more expensive mistake, so the evidence for it must be stronger.
DEFAULT = Triple(accept_at=0.80, drop_below=0.30)

# CHANCE for the primitive DEFAULT was set against: a Noul is a yes/no, so an
# uninformative answer sits at 0.5. Named so the derivation below reads as what
# it is rather than as a magic 0.5.
NOUL_CHANCE = 0.5


def for_choice(n_options: int, base: Triple = DEFAULT) -> Triple:
    """`base` re-expressed for a choice over `n_options`, and why that is needed.

    A PROBABILITY DOES NOT MEAN THE SAME THING ACROSS PRIMITIVES, and this is
    the one per-kind difference that is structural rather than tuning. A Noul
    spreads its mass over two outcomes, so an uninformative answer is 0.5 and
    0.80 is a strong claim. A `choice` over fourteen subjects spreads it over
    fourteen: uninformative is 0.071, and 0.80 on one option is a far stronger
    claim than the same number on a Noul -- strong enough that the shared triple
    would band almost every real answer `drop` and call a working classifier a
    failure. `TRIPLES`' rule is that nothing is listed without a reason to
    differ; the option count is that reason, and it is arithmetic rather than
    intuition, which is why this is a function and not three typed-in numbers.

    THE CUTS ARE HELD AT THE SAME DISTANCE from chance that `base` puts them at:
    `accept_at` the same fraction of the way from chance up to certainty,
    `drop_below` the same fraction of the way from chance down to zero. The
    SHAPE is preserved and re-derived; the judgement stays in `DEFAULT`, in one
    place, which is what stops a second unvalidated constant appearing here.

    STILL UNVALIDATED. The derivation makes the number defensible, not measured:
    it inherits every bit of `DEFAULT`'s provisionality and is declared in
    `unvalidated()` for exactly that reason. `SPECS.md` 3d is what would replace
    it with a calibrated one, and its trigger is >= 30 resolutions.
    """
    if n_options < 2:
        raise ValueError(f"a choice needs at least two options, got {n_options}")
    chance = 1.0 / n_options
    up = (base.accept_at - NOUL_CHANCE) / (1.0 - NOUL_CHANCE)
    down = (NOUL_CHANCE - base.drop_below) / NOUL_CHANCE
    return Triple(accept_at=round(chance + up * (1.0 - chance), 3),
                  drop_below=round(chance * (1.0 - down), 3))


# Per-kind triples, beside the question they tune (SPECS.md §Thresholds). A kind
# absent here uses DEFAULT. Nothing is listed until there is a reason to differ:
# a per-kind number invented now would be intuition wearing a lookup table's
# clothes.
#
# The three labelling kinds are listed because their PRIMITIVE differs, not
# because someone tuned them -- see `for_choice`. They are registered from the
# ontology's own criteria maps, so a subject added or retired moves the
# threshold with it instead of leaving a number calibrated against a vocabulary
# that no longer exists.
TRIPLES: dict[str, Triple] = {}


def _register_choice_kinds() -> None:
    for kind, schema in jev_schemas.SCHEMAS.items():
        q = schema.get("question", {})
        if q.get("type") != jev_schemas.CHOICE:
            continue
        n = len(q.get("criteria") or ())
        if n >= 2:
            TRIPLES[kind] = for_choice(n)


_register_choice_kinds()


def triple(kind: str) -> Triple:
    return TRIPLES.get(kind, DEFAULT)


def _is_promotion(kind: str) -> bool:
    return jev_schemas.is_promotion(kind)


def _noul_probability(answer: dict) -> float | None:
    """A Noul's own number. The only field it has (PLAN.md §The answer shapes)."""
    v = answer.get("noul", answer.get("probability"))
    return None if v is None else float(v)


def _choice_probability(answer: dict) -> float | None:
    """The winning option's probability. `choice` names the winner."""
    probs = answer.get("probabilities") or {}
    if not probs:
        return None
    winner = answer.get("choice")
    if winner is not None and winner in probs:
        return float(probs[winner])
    return float(max(probs.values()))       # no named winner: the best we have


def _score_mass(answer: dict) -> float | None:
    """The mass of the ACTION-BEARING levels.

    A Score returns a probability per level and the levels are ordered, so "how
    much does this matter" is the mass at or above the level the action needs.
    `action_from` is the level at which the proposed thing is done; without it
    the caller has not said what the score means, so there is no band to give.
    """
    probs = answer.get("probabilities") or {}
    levels = answer.get("levels") or {}
    floor = answer.get("action_from")
    if not probs or floor is None:
        return None
    keys = [k for k in probs if _level_index(k, levels) is not None
            and _level_index(k, levels) >= _level_index(floor, levels)]
    if not keys:
        return None
    return float(sum(probs[k] for k in keys))


def _level_index(value, levels) -> int | None:
    """Where a level sits in the ordered list. `levels` maps name -> score."""
    if isinstance(value, int):
        return value
    if isinstance(levels, dict) and value in levels:
        return levels[value]
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def of_answer(kind: str, answer: dict) -> dict:
    """The band for one answer, with the number it was taken on.

    Returns `{band, axis, value, triple}`. `value` is the probability the band
    was computed from -- recorded so the decision can be re-derived later rather
    than trusted (`SPECS.md` 2e: `probabilities` and `confidence` in the record).

    `band` is ASK when there is nothing to compute from. That is deliberate:
    an answer this code cannot read is not evidence for accepting or dropping,
    and `ask` is the state that means "a human should look".
    """
    tr = triple(kind)
    out = {"band": ASK, "axis": None, "value": None,
           "triple": {"accept_at": tr.accept_at, "drop_below": tr.drop_below}}
    # The number is read FIRST, for every kind including a promotion.
    #
    # Ask-only means the band is withheld; it does NOT mean the answer is
    # discarded. The recommendation is still SHOWN -- the report prints it and
    # the walk's `?` key reads it -- and a promotion that hid its own probability
    # would leave the user judging a claim with no evidence attached, which is
    # the opposite of what an ask-only bound is for. Getting this wrong is easy
    # and silent: the band came out right either way, and only the displayed
    # number vanished.
    qtype = answer.get("type")
    if qtype == "noul":
        value, axis = _noul_probability(answer), "probability"
    elif qtype == "choice":
        value, axis = _choice_probability(answer), "choice_probability"
    elif qtype == "score":
        value, axis = _score_mass(answer), "score_mass"
    else:
        value, axis = None, None
    out["axis"], out["value"] = axis, value
    if _is_promotion(kind):
        # Written only on an explicit accept, never on a band -- enforced here,
        # before any threshold is consulted, so no per-kind override can open it.
        out["axis"] = out["axis"] or "promotion"
        return out
    if value is None:
        return out
    if value >= tr.accept_at:
        out["band"] = ACCEPT
    elif value < tr.drop_below:
        out["band"] = DROP
    else:
        out["band"] = ASK
    return out


def order_key(item: dict) -> tuple:
    """Sort key putting `accept` first, `ask` next, `drop` last.

    The report's band order (SPECS.md 1b). An item with no band sorts with `ask`:
    nothing has judged it, which is the same position as "a human should look"
    and must not be mistaken for either decision.
    """
    rank = {ACCEPT: 0, ASK: 1, DROP: 2}
    band = (item.get("recommendation") or {}).get("band") or ASK
    return (rank.get(band, 1),)


def unvalidated() -> list:
    """Thresholds that are first estimates. The report prints these (2g's shape).

    Same contract as `ranking.unvalidated`: a number feeding a decision that
    nobody has validated is declared, so it is not mistaken for measured.
    """
    out = [f"bands.DEFAULT accept_at={DEFAULT.accept_at} "
           f"drop_below={DEFAULT.drop_below}"]
    out += [f"bands.TRIPLES[{k}] accept_at={t.accept_at} "
            f"drop_below={t.drop_below}" for k, t in sorted(TRIPLES.items())]
    return out
