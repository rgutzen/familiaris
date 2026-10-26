"""selection -- who does a class of work when nobody decided (decision 27, 2026-10-14).

`config/orchestration/selection.yaml` holds the pre-selections: per task class, an
ordered list of tiers, each naming the models that are adequate for that class at
that difficulty, with the reason a person is meant to argue with. This module
reads that policy and answers two questions:

  `find(sel, task_class, difficulty, raises)`   the tier that applies, its models
                                                cheapest first, and why
  `scope_of(sel, cwd)`                          what a directory vetoes

WHY IT REPLACED THE SCORE FLOOR. `dispatch.eligible` used to keep a model only if
it reached `capability_floor` (a percentile within the catalogue) on every
capability its class named. That conflated "may do this work" with "scores well at
it", and it collapsed the candidate set: the catalogue's own median is where the
frontier models sit, so exactly one model cleared it for `edit` and `test`, and
none cleared it for `read`, `docs` or `batch` -- whose benchmarks are unmeasured.
It also disqualified a model for a MISSING measurement, which `capabilities.yaml`
forbids in its own header ("No benchmark, no score: unknown, never zero"). A score
now only orders models inside a tier; it never decides membership.

WHAT A TIER ASSERTS. Membership is a judgement (this model is fit for this class),
not a measurement, and the reason field says why. The arithmetic the rule may do
is the choice WITHIN a tier: cheapest first by API-equivalent list price (decision
24), ties by the measured mean over the class's capabilities, then the order
written in the file. So a reader can check the arithmetic and argue with the
judgement separately, which is the whole point of keeping the judgement in YAML.

WHO USES IT.
  `dispatch`        the audit's suggestion: the tier the difficulty warrants.
  the eval runner   an item nobody declared gets the class's first tier, which is
                    what makes the "pi + dispatch" arm differ from the baseline
                    without editing any prompt.
  `bindings`        a binding may name `class:<name>` instead of a model id.

DIFFICULTY IS A ONE-WAY SIGNAL. An item meets the first tier whose
`difficulty_up_to` is at least its difficulty; the last tier has no limit. With no
difficulty reading the first tier applies -- a pre-selection is the baseline, and a
probe may move an item UP the tiers, never down and never sideways. `raises` is
that upward step, one per forcing answer the audit found (an open design decision,
a verify nobody can judge alone), capped at the last tier.

SCOPE IS A VETO, NOT A TIGHTENING. Nothing in this system orders privacy classes
(`local`, `EU-no-training`, `CN-undisclosed`, `US-unknown` are distinct and none is
narrower than another), so a scope can only REMOVE candidates: a model whose class
is not among those a scope allows is not eligible there. It is read only where
nothing else declared a class, and `scope_of` returns the longest matching
directory prefix, so a nested project may differ from its parent.

EXIT AND ERRORS. `check` is offline and keyless: it refuses a class that
`capabilities.yaml` does not declare, a tier with no models or no reason, a model
id the catalogue cannot call, and a `difficulty_up_to` that is not a number or not
rising across the tiers. `find` raises `SelectionError` for an unknown class rather
than guessing -- a caller that cannot name its class must ask for `unknown`.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from lib import _miniyaml
from lib import roots
from orchestration import models as _models

SELECTION = roots.SUBAGENTS / "selection.yaml"
UNKNOWN = "unknown"
# pi's own vocabulary (`pi --thinking`), the only one a level may be written in.
LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")


class SelectionError(ValueError):
    """An unknown class, or a policy file that cannot be used; exit 2."""


def load(path: pathlib.Path = SELECTION) -> dict:
    return _miniyaml.load(path.read_text(encoding="utf-8"))


def classes(sel: dict) -> dict:
    return sel.get("classes") or {}


def tiers(sel: dict, task_class: str) -> list:
    """The class's tiers, or the `unknown` class's when there is no class. A
    class nobody declared is an error: the caller must say `unknown`, so a typo
    cannot silently select the session default."""
    by = classes(sel)
    if task_class == UNKNOWN or not task_class:
        got = by.get(UNKNOWN)
        if not got:
            raise SelectionError("selection.yaml declares no `unknown` class")
        return got
    if task_class not in by:
        raise SelectionError(f"no class {task_class!r} in selection.yaml; "
                             f"declared: {', '.join(sorted(by))}")
    return by[task_class]


def pick(sel: dict, task_class: str, difficulty: float | None = None,
         raises: int = 0) -> tuple[dict, int, str]:
    """(the applicable tier, its index, why). `difficulty` None means no reading,
    so the first tier applies; `raises` steps up one tier per forcing answer."""
    got = tiers(sel, task_class)
    idx = 0
    if difficulty is not None:
        for n, t in enumerate(got):
            limit = t.get("up_to_difficulty")
            if limit is None or difficulty <= float(limit):
                idx = n
                break
        else:
            idx = len(got) - 1
    why = (f"no difficulty reading, first tier" if difficulty is None
           else f"difficulty {difficulty:.2f} -> tier {idx + 1} of {len(got)}")
    if raises:
        idx = min(idx + raises, len(got) - 1)
        why += f"; {raises} forcing answer(s) raise it to tier {idx + 1}"
    return got[idx], idx, why


def models_of(tier: dict) -> list:
    return [m.strip() for m in (tier.get("models") or "").split(",") if m.strip()]


def effort_by(tier: dict) -> dict:
    """`effort_by: "model=level, ..."`: a member whose vendor lacks the tier's
    level, declared at the level it really runs at. pi clamps an unsupported
    level UPWARD (deepseek-flash: medium -> high), so the declaration says what
    pi would otherwise do silently."""
    out = {}
    for part in str(tier.get("effort_by") or "").split(","):
        mid, _, level = part.partition("=")
        if mid.strip():
            out[mid.strip()] = level.strip()
    return out


def effort_of(tier: dict, model: str | None = None) -> str:
    """The thinking level this tier runs `model` at (pi's `--thinking`
    vocabulary), or '' when the tier names none. The level is the cheapest dial:
    same model, output tokens only (decision 28)."""
    if model and model in effort_by(tier):
        return effort_by(tier)[model]
    return (tier.get("effort") or "").strip()


def reason(tier: dict) -> str:
    return " ".join((tier.get("reason") or "").split())


def cheapest(cat: dict, caps: dict, tier: dict, rules: dict,
             allowed: set | None = None) -> tuple[list, str]:
    """The tier's models, best first: (ids, why). With `route_live: yes`
    (dispatch.yaml) this is `route` with exploration off -- lowest expected cost
    per VERIFIED result; until then it is the 14c order, lowest `pick_cost`, and
    the route is printed beside it (`shadow`) for the week 14g asks for before the
    switch. A model the catalogue cannot call, or that `allowed` excludes, is
    dropped with its reason -- membership of the tier is the judgement, so this
    never adds one."""
    ids, why, _choice = route(cat, caps, tier, rules, allowed,
                              by="e" if live(rules) else "usd")
    return ids, why


def live(rules: dict) -> bool:
    """Whether the router decides (`route_live: yes`) or only reports."""
    return str(rules.get("route_live", "no")).strip().lower() in ("yes", "true", "1")


def shadow(cat: dict, caps: dict, tier: dict, rules: dict,
           allowed: set | None = None) -> dict:
    """The router's greedy choice, for printing beside the pick that runs."""
    return route(cat, caps, tier, rules, allowed)[2]


# --- 14g: the router ---------------------------------------------------------
#
# THE QUANTITY. For each admissible member at the effort its tier runs:
#     E = pick_cost(one attempt) / P(verified)
# -- `costs.usage_for` for the tokens (the class's reference usage when nothing
# has run), `price.pick_cost` for the dollars (14d's quota weight included), and
# `posterior.belief` for P (this class's own evidence). 1/P is the expected
# number of attempts until one verifies, so E is the expected cost of a verified
# result.
#
# THE FLOOR. The greedy pick is the lowest E among members whose LOWER bound
# (posterior.LOWER) reaches `route_floor` (dispatch.yaml); when none does, every
# member is ranked and the note says so -- a tier is never emptied by a number.
#
# EXPLORATION (ruled 2026-10-22: Thompson sampling, inside the tier only, $1.00 a
# week). With `explore=True`, P is a DRAW from each member's posterior instead of
# its mean, over members whose posterior MEAN reaches the floor (one the record
# shows to be poor is not re-sampled; one it has not judged usually is). The draw
# is what lets an unjudged member collect labels, which a greedy rule never would.
# The spend is the expected cost of each pick that differed from the greedy one,
# summed over `route.jsonl` for the last seven days; at the cap, exploration stops
# until the week rolls. The tier is the user's judgement that any member is
# acceptable, so exploring inside it costs money, not quality.
#
# THE ORDER RETURNED is the pick first, then the rest by E: a cascade (14g, for a
# class with a free verifier) takes the next id on a failed check.

ROUTE_LOG = "route.jsonl"
_EVIDENCE: dict = {}


def evidence(refresh: bool = False) -> tuple:
    """(costs fit, posterior outcomes), read once per process from the data dir."""
    from orchestration import costs as _costs, posterior as _post, profiles  # noqa: PLC0415
    key = str(profiles.data_dir())
    if refresh or key not in _EVIDENCE:
        _EVIDENCE[key] = (_costs.fit(_costs.observations()), _post.outcomes())
    return _EVIDENCE[key]


def route_log_path():
    from orchestration import profiles                             # noqa: PLC0415
    return profiles.data_dir() / ROUTE_LOG


def explored_spend(now=None, path=None) -> float:
    """$ of the exploring picks in the last seven days, from `route.jsonl`."""
    import datetime as _dt                                         # noqa: PLC0415
    import json as _json                                           # noqa: PLC0415
    path = path or route_log_path()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if not path.is_file():
        return 0.0
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = _json.loads(line)
            at = _dt.datetime.fromisoformat(row["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if row.get("explored") and (now - at).total_seconds() < 7 * 86400:
            total += float(row.get("usd") or 0)
    return total


def route(cat: dict, caps: dict, tier: dict, rules: dict, allowed: set | None = None,
          *, size: int | None = None, explore: bool = False, rng=None,
          record: bool = False, now=None, data=None, by: str = "e") -> tuple[list, str, dict]:
    """(ids best first, why, the choice as a `route.jsonl` row). `by="usd"` is
    the 14c order exactly -- the class's reference usage priced, no learned tokens,
    no P, no floor, no exploration -- kept for the shadow week and for any caller
    that must not depend on the record."""
    import datetime as _dt                                         # noqa: PLC0415
    import json as _json                                           # noqa: PLC0415
    import random as _random                                       # noqa: PLC0415
    from orchestration import costs as _costs, posterior as _post, price as _price  # noqa: PLC0415
    fit, obs = data if data is not None else evidence()
    klass = tier.get("_class") or UNKNOWN
    needs = tier.get("_needs") or []
    floor = float(rules.get("route_floor", 0.5))
    known = {e.get("id"): e for e in cat.get("models") or []}
    bases = _post.base_rates(obs)
    rng = rng or _random.Random()
    options, dropped = [], []
    for order, mid in enumerate(models_of(tier)):
        e = known.get(mid)
        if e is None:
            dropped.append(f"{mid}: not a callable catalogue id")
            continue
        if allowed is not None and mid not in allowed:
            dropped.append(f"{mid}: outside the declared privacy")
            continue
        level = effort_of(tier, mid)
        if by == "usd":              # 14c exactly: the class's reference shape
            usage, how = _price.reference_usage(rules, klass), "the class's reference usage"
        else:
            usage, how = _costs.usage_for(fit, mid, level, klass, size, rules)
        usd = _price.pick_cost(e, usage, rules)
        b = _post.belief(mid, level, klass, obs, cat, caps, bases)
        sc = _models.capability_scores(mid, cat, caps) if needs else {}
        got = [sc[c][0] for c in needs if sc.get(c, (None,))[0] is not None]
        options.append({"id": mid, "effort": level or "", "usd": usd, "usage_from": how,
                        "mean": b.mean, "lower": b.lower, "draw": None,
                        "e": usd / b.mean, "cap": sum(got) / len(got) if got else -1.0,
                        "order": order})
    why = " (dropped: " + "; ".join(dropped) + ")" if dropped else ""
    if not options:
        return [], why, {}

    def rank(o, key="e"):
        return (o[key], -o["mean"], -o["cap"], o["order"])

    if by == "usd":
        ordered = sorted(options, key=lambda o: (o["usd"], -o["cap"], o["order"]))
        return [o["id"] for o in ordered], why, {"class": klass, "pick": ordered[0]["id"],
                                                 "by": "usd"}
    passing = [o for o in options if o["lower"] >= floor]
    pool = passing or options
    if not passing:
        why += f" (no member's lower bound reaches {floor:.2f}: all ranked)"
    greedy = min(pool, key=rank)
    pick, explored = greedy, False
    budget = float(rules.get("explore_budget") or 0)
    spent = explored_spend(now) if explore else 0.0
    if explore and spent < budget:
        open_ = [o for o in options if o["mean"] >= floor] or options
        for o in open_:
            o["draw"] = max(_draw(o, obs, cat, caps, klass, bases, rng), 0.01)
            o["e_draw"] = o["usd"] / o["draw"]
        pick = min(open_, key=lambda o: rank(o, "e_draw"))
        explored = pick["id"] != greedy["id"]
    elif explore:
        why += f" (exploration paused: ${spent:.2f} of ${budget:.2f} this week)"
    rest = sorted((o for o in options if o is not pick), key=rank)
    ids = [pick["id"]] + [o["id"] for o in rest]
    choice = {"ts": (now or _dt.datetime.now(_dt.timezone.utc)).isoformat(timespec="seconds"),
              "class": klass, "pick": pick["id"], "greedy": greedy["id"],
              "explored": explored, "usd": round(pick["usd"], 6), "floor": floor,
              "options": [{k: (round(v, 6) if isinstance(v, float) else v)
                           for k, v in o.items() if k not in ("order", "cap")} for o in options]}
    if explored:
        why += f" (exploring: {pick['id']} drawn over {greedy['id']})"
    if record:
        path = route_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(choice) + "\n")
    return ids, why, choice


def _draw(o: dict, obs: list, cat: dict, caps: dict, klass: str, bases: dict, rng) -> float:
    from orchestration import posterior as _post                   # noqa: PLC0415
    return _post.belief(o["id"], o["effort"], klass, obs, cat, caps, bases).draw(rng)


def with_needs(sel: dict, caps: dict) -> dict:
    """The same policy with each tier carrying its class's capabilities, so
    `cheapest` can tie-break without reaching for the capability map again."""
    out = dict(sel)
    by = {}
    for name, got in classes(sel).items():
        caps_needed = ((caps.get("task_classes") or {}).get(name) or {}).get("capabilities") or []
        by[name] = [dict(t, _needs=caps_needed, _class=name) for t in got]
    out["classes"] = by
    return out


def scope_of(sel: dict, cwd: pathlib.Path | str) -> dict:
    """The longest declared directory prefix that contains `cwd`, or {}. A scope
    can only remove candidates; see the module docstring."""
    path = pathlib.Path(cwd).expanduser()
    best, best_len = {}, -1
    for raw, decl in (sel.get("scope") or {}).items():
        root = pathlib.Path(raw).expanduser()
        try:
            path.resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            continue
        if len(str(root)) > best_len:
            best, best_len = dict(decl or {}), len(str(root))
    return best


def allowed_classes(caps: dict, allowed: set | None, class_name: str) -> list:
    """The class's capabilities, for a caller that wants to print them."""
    return ((caps.get("task_classes") or {}).get(class_name) or {}).get("capabilities") or []


def check(sel: dict, cat: dict, caps: dict) -> list:
    """Findings. Offline and keyless, like `dispatch --check`."""
    found = []
    declared = set(classes(sel))
    wanted = set((caps.get("task_classes") or {})) | {UNKNOWN}
    for missing in sorted(wanted - declared):
        found.append(f"classes: {missing!r} is declared in capabilities.yaml and not here")
    for extra in sorted(declared - wanted):
        found.append(f"classes: {extra!r} is not a task class in capabilities.yaml")
    callable_ids = {e.get("id") for e in cat.get("models") or []}
    for name, got in sorted(classes(sel).items()):
        last, windowless = None, None
        for n, t in enumerate(got, 1):
            where = f"{name} tier {n}"
            ids = models_of(t)
            if not ids:
                found.append(f"{where}: no models")
            for mid in ids:
                if mid not in callable_ids:
                    found.append(f"{where}: {mid!r} is not a callable catalogue id")
            if len(set(ids)) != len(ids):
                found.append(f"{where}: the same model twice")
            if not reason(t):
                found.append(f"{where}: no reason")
            for mid in effort_by(t):
                if mid not in ids:
                    found.append(f"{where}: effort_by names {mid!r}, which is not in the tier")
            for mid in ids:
                level = effort_of(t, mid)
                if not level:
                    continue
                if level not in LEVELS:
                    found.append(f"{where}: effort {level!r} is not one of {', '.join(LEVELS)}")
                    continue
                why = _models.effort_reason(cat, mid, level)
                if why:
                    found.append(f"{where}: effort: {why}")
            limit = t.get("up_to_difficulty")
            if limit is not None:
                try:
                    val = float(limit)
                except ValueError:
                    found.append(f"{where}: up_to_difficulty {limit!r} is not a number")
                    continue
                if not 0.0 <= val <= 1.0:
                    found.append(f"{where}: up_to_difficulty {val:g} is outside 0..1")
                if windowless is not None:
                    found.append(f"{where}: unreachable, because {windowless} carries no "
                                 f"up_to_difficulty and catches everything")
                elif last is not None and val <= last:
                    found.append(f"{where}: up_to_difficulty {val:g} does not rise "
                                 f"above the tier before it ({last:g})")
                last = val
            elif windowless is None:
                windowless = where
        if got and got[-1].get("up_to_difficulty") is not None:
            found.append(f"{name}: the last tier has an up_to_difficulty, so an item "
                         f"above it has no tier")
    for raw, decl in sorted((sel.get("scope") or {}).items()):
        if not str(raw).startswith("~") and not str(raw).startswith("/"):
            found.append(f"scope {raw!r}: not an absolute or ~ path")
        for key in (decl or {}):
            if key not in ("egress", "privacy", "reason"):
                found.append(f"scope {raw!r}: unknown key {key!r}")
    return found


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration selection",
                                 description="The pre-selections: which models a class of work gets.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate against the catalogue")
    mode.add_argument("--explain", metavar="CLASS", nargs="?", const=UNKNOWN,
                      help="the tiers a class would get, with reasons (default: unknown)")
    mode.add_argument("--for", dest="for_class", metavar="CLASS",
                      help="the model a class of work would get, and why")
    ap.add_argument("--difficulty", type=float, help="with --for: the item's difficulty 0..1")
    ap.add_argument("--scope", help="a working directory, so its scope veto is applied")
    args = ap.parse_args(argv)
    try:
        sel = with_needs(load(), _caps())
        cat = _cat()
        if args.check:
            found = check(load(), cat, _caps())
            for line in found:
                print(line)
            print(f"selection --check: {len(classes(sel))} class(es), {len(found)} finding(s)")
            return 1 if found else 0
        if args.for_class:
            tier, idx, why = pick(sel, args.for_class, args.difficulty)
            allowed = _allowed(cat, args.scope)
            ids, note = cheapest(cat, _caps(), tier, _rules(probe=True), allowed)
            n = len(tiers(sel, args.for_class))
            print(f"{args.for_class}: tier {idx + 1} of {n} -- {why}")
            print(f"  effort   {effort_of(tier, ids[0] if ids else None) or '(pi default)'}")
            print(f"  reason   {reason(tier)}")
            print(f"  models   {', '.join(ids) or 'none available'}{note}")
            print(f"  runs     {ids[0] if ids else 'nothing; the caller must refuse'}")
            sh = shadow(cat, _caps(), tier, _rules(probe=True), allowed)
            if sh:
                o = next(x for x in sh["options"] if x["id"] == sh["pick"])
                print(f"  route    {sh['pick']} -- E ${o['e']:.4f} per verified result "
                      f"(${o['usd']:.4f} an attempt, P {o['mean']:.2f}, lower {o['lower']:.2f})"
                      + ("" if live(_rules()) else "; shadow until `route_live: yes`"))
            return 0 if ids else 3
        for n, t in enumerate(tiers(sel, args.explain), 1):
            limit = t.get("up_to_difficulty")
            head = f"up to difficulty {limit}" if limit else "the hardest work"
            level = f", effort {effort_of(t)}" if effort_of(t) else ""
            level += "".join(f"; {m} {lv}" for m, lv in effort_by(t).items())
            print(f"{args.explain} tier {n} ({head}{level}): {', '.join(models_of(t))}")
            print(f"  {reason(t)}")
        return 0
    except (SelectionError, _miniyaml.YamlError, OSError) as e:
        print(f"selection: {e}", file=sys.stderr)
        return 2


def _cat():
    from orchestration import models as _models                    # noqa: PLC0415
    return _models.load()


def _caps():
    from orchestration import models as _models                    # noqa: PLC0415
    return _models.load_capabilities()


def _rules(probe: bool = False):
    """dispatch.yaml's rules; `probe` adds the live Claude reading (14d) for a
    pick made now. Off by default, so a test or a replay never asks the probe."""
    from orchestration import dispatch as _dispatch                # noqa: PLC0415
    from orchestration import price as _price                      # noqa: PLC0415
    return _price.with_quota(_dispatch.load_config(_caps())["rules"], probe=probe)


def _allowed(cat: dict, scope: str | None) -> set | None:
    """What a directory's scope vetoes. `None` means "nothing vetoed" -- the
    caller's own privacy filter may still narrow it."""
    if not scope:
        return None
    from orchestration import profiles as _profiles                # noqa: PLC0415
    decl = scope_of(load(), scope)
    wanted = decl.get("privacy")
    if not wanted:
        return None
    return {e["id"] for e in cat.get("models") or []
            if _profiles.privacy_class(e.get("jurisdiction", ""), "", _profiles.load()) == wanted}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
