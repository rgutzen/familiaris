"""The escalation ladder (8b): what to run an item on after its verify failed twice.

Decision 28, deterministic. The detector is the verifier, read from the item's
labels (3f); nothing here calls a model.

  1. fewer than 2 consecutive failures on the same (model, effort): retry as is;
  2. else, if this model has not yet had its effort raised for this item and the
     catalogue lists a higher level: the same model, one level up;
  3. else: a re-dispatch with context on the cheapest model of the next tier of
     the item's class, at that tier's effort;
  4. no tier above: the user decides.

A step is always a re-dispatch, never a hot switch inside a running session: a
switch forfeits the parent's prefix cache and changes `ran_model` mid-item.
"""
from __future__ import annotations

import dataclasses

from orchestration import models as _models
from orchestration import selection as _selection

FAILS = 2


@dataclasses.dataclass(frozen=True)
class Step:
    rung: str            # retry | effort | tier | user
    model: str
    effort: str
    why: str


def history(rows: list, specs_rel: str, item: str) -> list:
    """The item's live labels, oldest first."""
    return [r for r in rows if r.get("source") == "verify"
            and r.get("specs") == specs_rel and r.get("item") == item]


def _level_up(cat: dict, model: str, effort: str) -> str:
    levels, _ = _models.efforts(cat, model)
    if not levels:
        return ""                                  # unknown: never invent a level
    if effort not in levels:
        return levels[0] if not effort else ""     # an unlisted level is not climbed from
    i = levels.index(effort)
    return levels[i + 1] if i + 1 < len(levels) else ""


def _tier_index(tiers: list, model: str) -> int:
    """The highest tier naming the model, or -1."""
    found = [n for n, t in enumerate(tiers) if model in _selection.models_of(t)]
    return found[-1] if found else -1


def next_step(hist: list, *, task_class: str, cat: dict, sel: dict, caps: dict,
              rules: dict, allowed: set | None = None) -> Step:
    if not hist:
        return Step("retry", "", "", "no label yet")
    last = hist[-1]
    model, effort = last.get("ran_model") or "", last.get("effort") or ""
    if last.get("passed"):
        return Step("retry", model, effort, "the last verify passed")
    fails = 0
    for r in reversed(hist):
        if r.get("passed") or (r.get("ran_model") or "", r.get("effort") or "") != (model, effort):
            break
        fails += 1
    if fails < FAILS:
        return Step("retry", model, effort, f"{fails} failure(s) on {model or '?'} "
                                            f"at {effort or 'default'}; the ladder starts at {FAILS}")
    raised = any((r.get("ran_model") or "") == model and (r.get("effort") or "") != effort
                 for r in hist[:-fails])
    up = "" if raised or not model else _level_up(cat, model, effort)
    if up:
        return Step("effort", model, up, f"{fails} failures at {effort or 'default'}: "
                                         f"effort first, same model, one level up")
    tiers = _selection.tiers(sel, task_class)
    here = _tier_index(tiers, model)
    for idx in range(here + 1, len(tiers)):
        ranked, dropped = _selection.cheapest(cat, caps, tiers[idx], rules, allowed)
        ranked = [m for m in ranked if m != model]
        if ranked:
            return Step("tier", ranked[0], _selection.effort_of(tiers[idx], ranked[0]),
                        f"{fails} failures on {model}; class {task_class} tier "
                        f"{here + 1 if here >= 0 else '-'} -> {idx + 1}, re-dispatch with "
                        f"context{dropped}")
    return Step("user", model, effort, f"{fails} failures on {model}; no tier above in "
                                       f"class {task_class}: the user decides")


def render(step: Step) -> str:
    if step.rung == "retry":
        return f"escalation: retry ({step.why})"
    if step.rung == "user":
        return f"escalation: STOP -- {step.why}"
    return (f"escalation: {step.rung} -> {step.model} --effort {step.effort or 'default'} "
            f"({step.why})")
