"""Stage 6 -- Downscale. The quadrant table applied to the bottom percentile.

PROPOSAL-ONLY, permanently -- not "until it is trusted". Every action here is
derived from R, and every constant behind R is a first estimate (ranking.py
Sec.unvalidated). A demotion applied on an unvalidated score is a silent,
compounding error.

PRUNE BY RANK, NEVER BY AN ABSOLUTE R THRESHOLD. This is the one place the
sleep analogy changes the implementation rather than decorating it: under the
synaptic homeostasis hypothesis, sleep renormalises weights GLOBALLY so that
only relatively strong traces survive. A cutoff calibrated at 40 leaves
silently guts the tree at 400.

HARD RULES:
  * `authority: human` -> never touched, reported only.
  * never-verified or cold-start -> exempt from BOTH columns.
  * NOTHING IS DELETED. Demotion walks trusted -> trial -> deprecated, and
    `deprecated` is retained for provenance.
"""
from __future__ import annotations

from consolidation import ranking

BOTTOM_PERCENTILE = 0.25       # unvalidated, like every constant feeding R
DEMOTION = {"trusted": "trial", "trial": "deprecated"}


def run(ctx) -> bool:
    # `ctx.tree()` scores if nothing has yet, so this stage can run alone
    # (`--stages=6`). It used to read whatever list stage 3 had left behind, and
    # an EMPTY list is indistinguishable from a fully-exempt one: the stage
    # reported "all N document(s) are exempt ... the correct state for a tree
    # this young" on a tree it had never scored. A false line in the one report
    # this design depends on being read.
    tree = ctx.tree()
    scored = tree.scorable()
    if not scored:
        ctx.note("6", f"nothing scorable: all {len(tree.exempt())} document(s) are "
                      f"exempt (never-verified or inside the "
                      f"{ranking.COLD_START_DAYS}-day cold-start window). That is "
                      f"the correct state for a tree this young.")
        return True

    worklist = tree.bottom(BOTTOM_PERCENTILE)
    ctx.log(f"bottom {BOTTOM_PERCENTILE:.0%} = {len(worklist)} of {len(scored)} scorable")

    for d in worklist:
        s = d.scores
        q = s["quadrant"]
        if s["human"]:
            ctx.propose("6", "human-owned", d.rel,
                        f"quadrant `{q}` (R={s['R']:.2f})",
                        "authority: human — reported only, never auto-anything",
                        target_kind="leaf")
            continue
        if q == "re-verify":
            ctx.propose("6", "re-verify", d.rel,
                        f"used but stale (F={s['F']:.2f}, U={s['U']:.2f})",
                        "highest priority — the claim may already be wrong",
                        target_kind="leaf")
        elif q == "demote":
            cur = (d.get("trust") or "trusted").strip()
            nxt = DEMOTION.get(cur)
            if nxt:
                ctx.propose("6", "demote", d.rel,
                            f"trust {cur} → {nxt} (F={s['F']:.2f}, U={s['U']:.2f})",
                            "true but unused; nothing is deleted",
                            target_kind="leaf")
        elif q == "archive":
            ctx.propose("6", "archive", d.rel,
                        f"stale and unused (F={s['F']:.2f}, U={s['U']:.2f})",
                        "archive candidate — retained for provenance",
                        target_kind="leaf")

    # -- stability migration (memory-ranking.md) --------------------------
    # The consolidator may never WRITE `stability`; that rule stops the formula
    # from adjusting its own decay rate to flatter itself. It may propose.
    for d in tree.all():
        if d.scores["human"]:
            continue
        log = d.get("verified_log") or []
        sup = d.get("supersedes")
        stab = (d.get("stability") or "").strip()
        if stab == "evolving" and len(log) >= 3:
            ctx.propose("6", "stability", d.rel, "evolving → stable",
                        f"unchanged across {len(log)} recorded verifications",
                        target_kind="leaf")
        if sup and isinstance(sup, list) and len(sup) >= 2:
            ctx.propose("6", "stability", d.rel, f"{stab} → one step more volatile",
                        "supersedes chain ≥2 deep — it churns",
                        target_kind="leaf")

    ctx.note("6", "every proposal above is derived from R, whose constants are "
                  "unvalidated. Proposal-only by design, not by immaturity.")
    return True
