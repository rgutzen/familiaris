"""price -- the one function that turns tokens into dollars (item 14c).

WHY ONE. The review of steps 11-13 found six formulas: `dispatch.yaml`'s 1:1 sum
of list rates, a copy of it in `bindings.py`, another in `scout.inversions`, the
cheapest-Claude pick in `ping.py`, the scout's 3:1 chart blend, and `eval.cost`
over measured usage. None of the list-rate sums carried the cache-hit rate, which
decides a read: the latest `explore` line read 101 760 cache-hit tokens against
20 670 fresh input, and deepseek-flash bills the first at 0.006 and the second at
0.30. 12c measured haiku against deepseek-flash at 1 : 1.9 per read where list
price said 1 : 2.5. This module is the only place a catalogue rate is multiplied
(a check enforces it); the chart's own price stays inside the chart's comparison.

WHAT A COST BLOCK HOLDS. `in`, `out`, `cache_hit` (default: the input rate, which
is Jev's case), `cache_write` (default: the input rate, eval's rule before 14c),
and two optional bands that used to live in free-text `note:`:
  long_prompt:  {over: N, in, cache_hit, out, ...} -- a prompt of more than N
                tokens bills every pool at the band's rates (haiku over 100 000);
  off_peak:     {peak: "mon-fri 01:00-04:00, 06:00-10:00", factor: "0.5"} -- the
                rates are PEAK; outside the windows (UTC) every rate is scaled by
                `factor`. A public holiday the vendor also discounts is not
                modelled, so an off-peak holiday reads at peak: an over-estimate.
A cost with no time (`at=None`) is at peak, the dearer reading.

THE PROMPT SIZE that selects `long_prompt` is ONE REQUEST's context, passed as
`prompt=`. The usage pi logs is summed over every request of a session (a child
that reads in six steps carries six contexts in `cache_read`), so the band is
never inferred from the pools: a caller that knows the largest single prompt
passes it, and one that does not gets the base rates, an under-estimate for a
haiku request over 100 000 tokens. Usage pools are pi's: `input`, `cache_write`,
`cache_read`, `output`. A reference shape may carry `prompt` for the same reason.

REFERENCE USAGE. A tier is ranked before anything has run, so `reference()` prices
a declared usage shape (dispatch.yaml `reference_usage:`, per class, from the
logs' medians) rather than a sum of rates. 14e replaces the shape with the learned
per-option estimate.
"""
from __future__ import annotations

import datetime

POOLS = ("input", "cache_write", "cache_read", "output")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class PriceError(ValueError):
    """A cost block this module cannot read. Named, never defaulted to zero."""


def block(model: str, cat: dict | None = None) -> dict:
    """The catalogue's cost block for a model id or a pi `provider/id`, or {}.

    The log holds what pi ran (`deepseek/deepseek-flash`); the catalogue is keyed
    by the vendor's id, so the provider prefix is stripped only when the whole
    string names nothing.
    """
    from orchestration import models, profiles
    cat = cat if cat is not None else models.load()
    for candidate in (model, model.split("/", 1)[-1]):
        _, entry = profiles.find(cat, candidate)
        if entry and entry.get("cost"):
            return dict(entry["cost"])
    return {}


def _num(value, default: float | None = None) -> float:
    if value in (None, ""):
        if default is None:
            raise PriceError("a rate is missing")
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise PriceError(f"{value!r} is not a rate") from None


def _minutes(hhmm: str) -> int:
    h, m = hhmm.strip().split(":")
    return int(h) * 60 + int(m)


def _days(spec: str) -> set:
    spec = spec.strip().lower()
    if "-" in spec:
        a, b = (DAYS.index(x.strip()) for x in spec.split("-"))
        return set(DAYS[a:b + 1])
    return {spec}


def peak(spec: str, at: datetime.datetime) -> bool:
    """Whether `at` (UTC) falls in `spec`: `"mon-fri 01:00-04:00, 06:00-10:00"`,
    a day range and its windows; a later `day hh:mm-hh:mm` part starts a new range."""
    at = at.astimezone(datetime.timezone.utc) if at.tzinfo else at
    day, minute = DAYS[at.weekday()], at.hour * 60 + at.minute
    days: set = set(DAYS)
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if " " in part:
            head, part = part.split(None, 1)
            days = _days(head)
        lo, hi = (_minutes(x) for x in part.split("-"))
        if day in days and lo <= minute < hi:
            return True
    return False


def rates(price: dict, at: datetime.datetime | None = None, prompt: int = 0) -> dict:
    """The rates that apply: {in, out, cache_hit, cache_write}, $ per M tokens."""
    if not price:
        return {}
    band = price.get("long_prompt") if isinstance(price.get("long_prompt"), dict) else None
    src = dict(price)
    if band and prompt > _num(band.get("over")):
        src.update({k: v for k, v in band.items() if k != "over"})
    ins = _num(src.get("in"), 0.0)
    out = {"in": ins, "out": _num(src.get("out"), 0.0),
           "cache_hit": _num(src.get("cache_hit"), ins),
           "cache_write": _num(src.get("cache_write"), ins)}
    off = price.get("off_peak") if isinstance(price.get("off_peak"), dict) else None
    if off and at is not None and not peak(str(off.get("peak") or ""), at):
        f = _num(off.get("factor"))
        out = {k: v * f for k, v in out.items()}
    return out


def cost(price: dict, usage: dict, at: datetime.datetime | None = None,
         prompt: int | None = None) -> tuple:
    """(the $, the frontier pools' $) for one usage at one moment.

    PLAN §Option 0 counts frontier tokens as input + output + cache-write, so the
    frontier $ is those three pools; cache-read is reported beside the frontier
    total, never inside it, because a long session's bill is mostly cache-read and
    the token rule and the dollar rule would otherwise answer different questions.
    """
    if not price:
        return 0.0, 0.0
    u = {k: int((usage or {}).get(k, 0) or 0) for k in POOLS}
    r = rates(price, at, prompt or 0)
    frontier = (u["input"] * r["in"] + u["cache_write"] * r["cache_write"]
                + u["output"] * r["out"]) / 1e6
    total = frontier + u["cache_read"] * r["cache_hit"] / 1e6
    return round(total, 6), round(frontier, 6)


def model_cost(model: str, usage: dict, at: datetime.datetime | None = None,
               cat: dict | None = None, prompt: int | None = None) -> tuple:
    """`cost` for a model id, at the catalogue's block for it."""
    return cost(block(model, cat), usage, at, prompt)


def reference(model: str, usage: dict, cat: dict | None = None) -> float:
    """The $ of one reference usage at peak: what ranks a tier before any run."""
    return model_cost(model, usage, None, cat, usage.get("prompt"))[0]


def reference_usage(rules: dict, task_class: str = "") -> dict:
    """The class's declared reference usage, else the `default` one. Missing
    both is an error: a ranking with no usage would be a sum of rates again."""
    table = (rules or {}).get("reference_usage") or {}
    got = table.get(task_class) or table.get("default")
    if not got:
        raise PriceError("dispatch.yaml rules.reference_usage has no `default`")
    out = {k: int(got.get(k, 0) or 0) for k in POOLS}
    if got.get("prompt"):
        out["prompt"] = int(got["prompt"])
    return out


# --- 14d: the quota pool's shadow price --------------------------------------
#
# DECISION 24, AMENDED 2026-10-22 (the user): a `pool: quota` model is priced at
# API-equivalent $ times a weight read from the live Claude usage, so the window is
# cheap while it has room and dear near its limit. The table is `quota_weight:` in
# dispatch.yaml's rules (`"0.50: 0.25, 0.80: 1, else: 4"`: under 50% of the binding
# window, a quarter; under 80%, list; above, four times). The binding window is the
# fuller of the five-hour and weekly fractions. No reading -- the probe failed, or
# a caller that does not probe, which is every test and every offline replay --
# is weight 1, decision 24 exactly. The weight orders picks only; a REPORT (6d's
# ratio, the delegation $) stays at API-equivalent dollars.

def quota_steps(text: str) -> list:
    """`"0.50: 0.25, 0.80: 1, else: 4"` -> [(0.5, 0.25), (0.8, 1.0), (inf, 4.0)]."""
    steps = []
    for part in str(text or "").split(","):
        if not part.strip():
            continue
        bound, _, weight = part.partition(":")
        bound = bound.strip()
        steps.append((float("inf") if bound == "else" else float(bound), float(weight)))
    steps.sort()
    if not steps or steps[-1][0] != float("inf"):
        raise PriceError("quota_weight needs an `else:` step")
    return steps


def quota_weight(reading: float | None, steps: list) -> float:
    """The weight at a reading (the fuller window's fraction); 1 without one."""
    if reading is None:
        return 1.0
    return next(w for bound, w in steps if reading < bound)


def live_quota(env=None) -> float | None:
    """The fuller of the Claude windows now, or None when the probe cannot say.
    The schedule track owns the probe and its cache; this only asks it."""
    import os
    from schedule import conditions, sessions                       # noqa: PLC0415
    try:
        env = dict(env if env is not None else os.environ)
        reading = conditions.read_budget(conditions.Context(sessions.load_policy(), env=env))
    except Exception:                       # noqa: BLE001 -- a pick must not die on a probe
        return None
    fractions = [float(f) for f, _resets in reading.values()]
    return max(fractions) if fractions else None


def with_quota(rules: dict, reading: float | None = None, probe: bool = True) -> dict:
    """The rules with the live reading in them, for a pick made now."""
    got = reading if reading is not None else (live_quota() if probe else None)
    return dict(rules, quota_reading=got)


def pick_cost(entry: dict, usage: dict, rules: dict) -> float:
    """What `cheapest` ranks by: the reference $, weighted when the pool is quota."""
    usd = cost(entry.get("cost") or {}, usage, None, usage.get("prompt"))[0]
    if entry.get("pool") != "quota":
        return usd
    steps = rules.get("quota_steps") or [(float("inf"), 1.0)]
    return usd * quota_weight(rules.get("quota_reading"), steps)
