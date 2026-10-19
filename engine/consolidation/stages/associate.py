"""Stage 5 -- Associate. Back-link repair (5a) and co-location proposals (5b).

5a IS MECHANICAL: `related:` is bidirectional across knowledge/**, so if A names
B then B must name A. Pure set symmetry -- no scoring, no model, no unvalidated
constant. That is exactly why it is allowed to write unattended.

5b IS NOT, and is gated. `scope:` is the leaf's CLAIM about where it applies;
the usage log's `cwd` is the OBSERVATION. Disagreement is a filing signal --
but inference from two log lines is noise, so the stage stays silent below
MIN_SAMPLE and says so rather than emitting confident nonsense.

THE NODE SET IS DECLARED, NOT GUESSED. This stage used to resolve `related:`
against `tree.leaves()` alone, so a name pointing at a real convention, or a real
file outside the tree, was reported as dangling -- five of the eighteen open
queue items on 2026-09-30. The resolvers' world was smaller than the tree's
reference set. `ontology.resolve` is that world, declared once, and this stage
reads it instead of re-deriving it. When a reference resolves to a DECLARED
type that is not a leaf, it is an edge to a real thing: reported when it is
directive, and never dangling.

TWO HARD RULES:
  * Never write into a directive document -- `conventions/**`, `user/**`,
    `boundaries/**` -- at every stage. A missing back-link there is a REPORTED
    FINDING, never a repair: `code-style.md` holds a knowledge->skill link that
    `knowledge-vs-skills.md` forbids, and that is reported too.
  * A `related:` name that resolves to nothing is a REPORT LINE, not a deletion.
    Nothing in this pass deletes a link, the same way nothing deletes a leaf.
"""
from __future__ import annotations

from knowledge import frontmatter, ontology
from consolidation import ledger

MIN_SAMPLE = 30        # usage lines before co-location says anything at all
MIN_BROWSE = 3         # browse hits on one term before it is a trigger candidate


def _is_conventions(hit) -> bool:
    """Is the resolved target a document an agent may never write?

    THE NAME IS KEPT ON PURPOSE: this function used to read

        doc.rel.startswith("knowledge/conventions/")

    -- a path that has not existed since conventions moved to
    `config/practice/conventions/`, which made the branch dead and the `frozen` list it
    feeds permanently empty. The INTENT was right; the mechanism was a
    hardcoded path, and a hardcoded path rots silently. It now asks the entity
    register, so it cannot rot again, and `grep _is_conventions` still finds the
    decision (ontology SPECS O1c).

    Takes what `ontology.resolve` returns, or a document's own rel path -- both
    spellings reach this function from the two call sites below.
    """
    if hit is None:
        return False
    rel = hit[1] if isinstance(hit, tuple) else hit
    return ontology.is_directive(rel)


def run(ctx) -> bool:
    tree = ctx.tree()
    leaves = {d.name: d for d in tree.leaves()}
    # One world, built once: the identifier set is the same for every reference
    # in the tree, and re-walking it per name would be a glob per name.
    idx = ontology.index(ctx.agents, ctx.base)

    # -- 5a: back-link repair ---------------------------------------------
    missing: dict[str, set[str]] = {}
    dangling: list[tuple[str, str]] = []
    frozen: list[tuple[str, str, str]] = []
    for name, d in leaves.items():
        for other in d.get("related") or []:
            other = other.strip()
            if not other or other == name:
                continue
            tgt = leaves.get(other)
            if tgt is None:
                hit = ontology.resolve(other, agents=ctx.agents, base=ctx.base,
                                       idx=idx)
                if hit is None:
                    dangling.append((name, other))
                elif _is_conventions(hit):
                    frozen.append((other, name, hit[1]))
                # Anything else is an edge to a DECLARED type -- a skill, an
                # episode, a report, an external file. Not dangling, and not
                # writable from here.
                continue
            if name not in [x.strip() for x in (tgt.get("related") or [])]:
                if _is_conventions(tgt.rel):
                    frozen.append((other, name, tgt.rel))
                else:
                    missing.setdefault(other, set()).add(name)

    for target, adds in sorted(missing.items()):
        d = leaves[target]
        cur = [x.strip() for x in (d.get("related") or [])]
        new = cur + sorted(a for a in adds if a not in cur)
        try:
            changed = frontmatter.update(d.path, {"related": new}, dry_run=ctx.dry_run)
        except ValueError as exc:
            ctx.note("5", f"{d.rel}: {exc}", "error")
            continue
        if changed:
            ctx.act("5a", d.rel, "back-link added: " + ", ".join(sorted(adds)))
            d.fm["related"] = new

    for target, source, rel in sorted(frozen):
        # A FINDING, not a queue item, and the distinction is load-bearing.
        # A queue item is something `decide N` can resolve; the pass may not
        # write into `config/practice/conventions/**`, `config/practice/user/**` or
        # `config/boundaries/**` at all, so there is nothing here for the user
        # to decide and nothing for the next pass to apply. It is reported in
        # the report's warnings, with the word `backlink` and the target, which
        # is what the dead guard was written to do (SPECS.md O1c: "reported,
        # never written").
        ctx.note("5a", f"backlink `{rel}`: `{source}` names it and the reverse "
                       f"link is missing; `{target}` is directive, so this is "
                       f"reported and never written", "warn")
    for src, name in sorted(dangling):
        ctx.propose("5a", "dangling-link", src,
                    f"`related: {name}` resolves to no leaf",
                    "reported, never deleted — the name may be a leaf yet to be written",
                    target_kind="leaf")

    if not missing and not frozen:
        ctx.log("back-links symmetric")

    # -- 5a: knowledge -> skill references, reported and never repaired ----
    # knowledge-vs-skills.md forbids a leaf from pointing INTO a skill: the
    # dependency runs skill -> leaf, so that a skill can be replaced without
    # editing the knowledge it cites. code-style.md violates this today. It
    # lives under conventions/, which is directive, so this is a REPORT LINE
    # in both senses -- the rule says do not write there, and the fix is an
    # editorial judgement about which direction the sentence should run.
    skill_names = {d.name for d in tree.skills()}
    for name, d in sorted(leaves.items()):
        body = d.get("_body") or ""
        for sk in sorted(skill_names):
            if f"`{sk}`" in body:
                ctx.propose("5a", "knowledge→skill link", d.rel,
                            f"body cites the `{sk}` skill",
                            "knowledge-vs-skills.md: the dependency runs "
                            "skill → leaf, never the reverse — reported, not repaired",
                            target_kind="leaf")

    # -- 5b: co-location, gated on sample size ----------------------------
    usage = ledger.read(ctx.base, ledger.USAGE)
    rows = usage.rows
    if usage.malformed:
        # Said here as well as in stage 2: this stage gates on the SAMPLE SIZE,
        # so a line it could not read is a line missing from the denominator.
        ctx.note("5b", f"{usage.malformed} unparseable line(s) in {ledger.USAGE} "
                       f"are not in the {len(rows)}-line sample below", "warn")
    if len(rows) < MIN_SAMPLE:
        ctx.note("5b", f"co-location silent: {len(rows)} usage line(s), needs "
                       f"{MIN_SAMPLE}. `scope:` claims are not yet testable against "
                       f"observed `cwd`.")
    else:
        by_cwd: dict[str, set[str]] = {}
        for r in rows:
            if r.get("cwd") and r.get("skill"):
                by_cwd.setdefault(r["cwd"], set()).add(r["skill"])
        pairs: dict[tuple[str, str], int] = {}
        for skills in by_cwd.values():
            ordered = sorted(skills)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1:]:
                    pairs[(a, b)] = pairs.get((a, b), 0) + 1
        # Read once, then ask per pair: a rejected link must not be re-proposed
        # every night while the co-occurrence still holds in the current window.
        dismissed = ledger.dismissals(ctx.base)
        skipped_d = 0
        for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:5]:
            if n >= 3:
                target = f"{a} ↔ {b}"
                if dismissed.covers(ctx.repo, target, "link", target_kind="opaque"):
                    skipped_d += 1
                    continue
                ctx.propose("5b", "link", target,
                            f"co-occurred in {n} working directories",
                            "association measured rather than asserted",
                            target_kind="opaque")
        if skipped_d:
            ctx.note("5b", f"{skipped_d} link proposal(s) suppressed -- already "
                          f"decided, within the {ledger.OPAQUE_TTL_DAYS}-day "
                          f"window (`familiar consolidation dismiss`)")

    _trigger_promotion(ctx, rows)

    return True


def _trigger_promotion(ctx, rows) -> None:
    """5c -- signal 4 should become signal 3 (skill-routing.md Sec.Trigger promotion).

    Resolution order is a cost gradient: signal 2 is free, signal 3 costs a grep,
    signal 4 costs a round trip. Nothing else moves a decision DOWN that gradient,
    so a browse that resolves correctly today costs the same tomorrow. When a
    skill was reached by category browse, the vocabulary that led there is a
    `triggers:` candidate; promoting it makes the next occurrence free.

    Proposal-only, and gated: `terms` is INFERRED from the invocation args, not
    reported by the agent, so promoting a term on one observation would bake an
    inference error into the router.
    """
    browse = [r for r in rows if r.get("signal") == "browse" and r.get("terms")]
    if not browse:
        ctx.note("5c", f"trigger promotion silent: no `browse`-resolved "
                       f"invocations in {len(rows)} usage line(s). A browse is "
                       f"what marks vocabulary as a promotion candidate.")
        return
    by_skill: dict[str, dict[str, int]] = {}
    for r in browse:
        d = by_skill.setdefault(r["skill"], {})
        for t in r["terms"]:
            d[t] = d.get(t, 0) + 1
    known = {d.name: d for d in ctx.tree().skills()}
    proposed = 0
    for skill, terms in sorted(by_skill.items()):
        doc = known.get(skill)
        if doc is None:
            continue
        declared = {t.lower() for t in (doc.get("triggers") or [])}
        anti = {t.lower() for t in (doc.get("antitriggers") or [])}
        hot = [(t, n) for t, n in terms.items()
               if n >= MIN_BROWSE and t not in declared and t not in anti]
        for t, n in sorted(hot, key=lambda kv: -kv[1])[:5]:
            ctx.propose("5c", "trigger", doc.rel, f"promote `{t}` to `triggers:`",
                        f"led to a browse-resolved selection {n}x; signal 4 → 3",
                        target_kind="leaf")
            proposed += 1
    if not proposed:
        ctx.note("5c", f"{len(browse)} browse-resolved invocation(s), but no term "
                       f"reached the {MIN_BROWSE}x threshold. `terms` is inferred, "
                       f"not reported — one observation is not evidence.")
