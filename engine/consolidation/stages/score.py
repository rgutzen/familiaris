"""Stage 3 -- Score. Pure function of the tree. WRITES NOTHING.

That is the design, not an omission (consolidation-cycle.md): the output can be
regenerated and diffed without touching git history, so a change to the formula
is auditable against the tree it scored.

Since the scored tree became a seam (`ctx.tree()`), scoring is no longer this
stage's private act -- any stage that asks gets a scored tree. What remains here,
and belongs nowhere else, is SAYING WHAT WAS SCORED: the population, the exempt
sets, and the fact that utility decayed over active days rather than calendar
days. An unstated exemption reads as a low score.
"""
from __future__ import annotations


def run(ctx) -> bool:
    tree = ctx.tree()

    n_k = len(tree.leaves())
    n_s = len(tree.skills())
    never = tree.exempt_for("never-verified")
    cold = tree.exempt_for("cold-start")
    ctx.log(f"scored {n_k} leaves + {n_s} skills; "
            f"{len(never)} never-verified, {len(cold)} cold-start")
    ctx.note("3", f"utility decays over {len(tree.active_days)} ACTIVE day(s), not "
                  f"calendar days — a leaf is never demoted for days the laptop was "
                  f"closed. Freshness still uses calendar days: the world drifts "
                  f"while you are away.")

    if never:
        ctx.note("3", f"{len(never)} document(s) have no `last_verified`: F is "
                      f"UNDEFINED (not zero) and they are exempt from pruning -- "
                      + ", ".join(sorted(d.name for d in never)))
    undated = tree.exempt_for("used-never-dated")
    if undated:
        ctx.note("3", f"{len(undated)} document(s) have use_count > 0 but no "
                      f"`last_used`; u_rec was floored at 0.5 rather than guessed")

    return True
