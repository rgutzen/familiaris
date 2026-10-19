"""Stage 5d -- Conflicts. Declared precedence, resolved deterministically.

memory/knowledge/system/consolidation/consolidation-cycle.md §5. Deterministic and no LLM: every input is frontmatter, every rule is
a comparison, and the whole module can be read and re-derived without a network
call. That is not a limitation accepted for convenience -- it is the point. The
failure this module exists to prevent is a settled policy being contradicted
nightly by a store that cannot tell that it is contradicting itself
(`journal/2026/09/2026-09-10_lore-reevaluation.md`, the `.lore.md` git policy),
and a module that decides "which side wins" by asking a language model is one
more unauditable opinion in exactly the layer that just went wrong.

WHAT A CONFLICT IS, HERE. Two frontmatter fields, both already in the leaf
contract:

  `supersedes:`   ASYMMETRIC and ASSERTED. "This leaf replaces that one." The
                  author has decided. Nothing in this module second-guesses it;
                  it only checks that the tree is internally consistent with a
                  decision that has already been made (the other side marked,
                  a back-pointer present, the target actually existing).
  `contradicts:`  SYMMETRIC and UNRESOLVED. "These two make incompatible
                  claims and I am not saying which is right." THIS is where the
                  precedence rule applies: the later `last_verified:` wins.

ISO-8601 CHRONOLOGICAL PRECEDENCE, stated because it is a rule and a rule that
is only in code is a rule nobody can argue with. Of two leaves making
incompatible claims, the one verified more recently is the current one. It is
the same signal `F = 2^(-Δv/H)` already decays on, read to a different end:
freshness says how much to trust a claim, this says which of two claims is the
surviving one. Ties, missing dates and future dates are all UNDECIDABLE, and
undecidable means propose, never apply -- guessing a winner between two claims
is the one outcome worse than reporting the conflict.

WHAT IT WRITES, AND WHY THAT IS ALLOWED UNATTENDED. `consolidation-cycle.md`
splits the pass into ACTIONS (mechanical) and PROPOSALS (scoring- or
LLM-derived). Marking a supersession is mechanical in the sense that rule
defines: it does not depend on a number nobody has validated. It depends on a
relation an author DECLARED and, for `contradicts:`, on a date comparison. So:

  APPLIES  `superseded_by:` on the superseded side, `supersedes:` on the winner
           of a resolvable contradiction, and `trust: deprecated` on the loser.
  PROPOSES everything else: a dangling or self-referential `supersedes:`, a
           cycle, a declaration the dates contradict, a contradiction with no
           decidable winner, an overlapping pair with no declaration, and any
           case where the losing side is directive.

`trust: deprecated` is retained, never deleted, and stage 6's demotion ladder
already ends there -- so the worst case of a wrong `supersedes:` is a leaf that
is marked and reversible, not a leaf that is gone. That is what makes applying
it defensible; if this module could delete, it would be proposal-only.

WHAT THE OVERLAP CHECK IS NOT. `overlapping-leaf` finds two leaves whose
title/summary/triggers/tags share vocabulary. It does NOT find contradictions:
deterministic detection of a semantic contradiction between two differently
worded paragraphs is not a thing that exists, and a module that claimed to do it
would manufacture exactly the distractor noise the L-track exists to remove. It
finds the pair a human should read, and it says so in the finding. Hard-gated
(`MIN_SHARED_TERMS`, `MIN_OVERLAP_JACCARD`) and capped, because a report that
cries wolf stops being read -- the failure mode `consolidation-cycle.md` names as
the one this design is most exposed to.

POPULATION. The same one stage 3 scores and stage 6 already reads `supersedes:`
from -- `knowledge/**` leaves and `skills/**/SKILL.md`, minus `tree.SKIP_NAMES`.
Shared with the scorer by import, so the two cannot disagree about the
denominator. `MEMORY.md` is NOT in it: deleted 2026-09-04, see
`stages/consolidate.py`. The always-on prose (`conventions/**`, `user/**`,
`CONTEXT.md`) carries no frontmatter, so it can be NAMED by a leaf but never
marked -- which is reported, not silently skipped, since `knowledge/conventions/`
being directive is exactly the case where a conflict must reach a person.

Same shape as `knowledge_index.py`: `plan()` decides and writes nothing,
`Plan.apply()` writes and reports what changed, `main()` is a CLI adapter,
`run()` is the stage. Nothing here raises past its caller.

Exit codes: 0 ok - 3 --check found pending marking. Nothing exits 1: this
stage has no error condition, only findings, and a code meaning "found
something" would train the reader to ignore it.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import sys

from knowledge import frontmatter, ontology
from consolidation import ranking
from knowledge.tree import SKIP_NAMES
from lib import roots

DEFAULT_ROOT = pathlib.Path(os.environ.get(
    "PAZRAS_MEMORY_DIR", str(roots.INSTALL / roots.MEMORY_REL)))

SUPERSEDES = "supersedes"
SUPERSEDED_BY = "superseded_by"
CONTRADICTS = "contradicts"
# The three fields this module may write. `trust` is the marking; the other two
# are the precedence pair. Listed in one place so `test_conflicts` can assert
# that nothing else is ever touched -- the same discipline `consolidate.
# MARKING_KEYS` applies to a stage-4 patch.
WRITABLE = (SUPERSEDED_BY, SUPERSEDES, "trust")
DEPRECATED = "deprecated"

# Paths an agent may never write, whatever the rule says: directive at every
# stage (`consolidation-cycle.md` invariant 2). A conflict that lands here is
# reported and stops. Which documents are directive is asked of the entity
# register (`ontology.is_directive`), as `associate.py` does; since R3b those
# kinds live under `config/`, outside the vault this stage walks. What is left
# here is the one vault-relative prefix the register cannot answer for: where
# the conventions lived before they left the scored tree.
DIRECTIVE = ("knowledge/conventions/",)

# -- the overlap check's two constants, unvalidated like every other threshold
# in this pass and named in the note they produce. 4 shared normalized terms is
# the point where two leaves are about the same subject rather than adjacent
# ones; 0.40 Jaccard is high enough that the shared vocabulary dominates both
# leaves rather than being one leaf's tags against another's summary.
MIN_SHARED_TERMS = 4
MIN_OVERLAP_JACCARD = 0.40
MAX_OVERLAP = 5            # a night's reading budget, not a ranked list

# `_leaf-template.md` and `tree.SKIP_NAMES` both agree these are not leaves.
STOPWORDS = frozenset("""a an and are as at be by for from has have how in into
is it its not of on or that the their there these this to was were what when
which who why will with without you your never always may can should must do
does""".split())
WORD = re.compile(r"[a-z0-9][a-z0-9_-]{2,}")


@dataclasses.dataclass
class Node:
    """One frontmatter-carrying document: a knowledge leaf or a skill."""

    rel: str                       # agents-relative posix path
    path: pathlib.Path
    fm: dict
    body: str

    @property
    def name(self) -> str:
        """The stem `related:` uses, and the skill's own `name:`."""
        if self.rel.startswith("skills/"):
            return (self.fm.get("name") or self.path.parent.name).strip()
        return self.path.stem

    @property
    def title(self) -> str:
        return (self.fm.get("title") or self.path.stem).strip()

    def list_of(self, key) -> list[str]:
        v = self.fm.get(key)
        if v is None or v == "":
            return []
        return [str(x).strip() for x in (v if isinstance(v, list) else [v])
                if str(x).strip()]

    def verified(self):
        return ranking.date_of(self.fm.get("last_verified"))

    @property
    def human(self) -> bool:
        return (self.fm.get("authority") or "").strip() == "human" \
            or self.rel.startswith(DIRECTIVE) \
            or ontology.is_directive(f"{roots.MEMORY_REL}/{self.rel}")


@dataclasses.dataclass
class Finding:
    """One thing the tree says about itself that does not add up.

    `updates` is None for everything that needs a person. When it is a dict the
    finding is APPLIABLE, and `Plan.apply` writes exactly those keys -- which is
    why the field is `updates` and not a predicate: what gets written is visible
    at the point the finding is constructed, not one call away.
    """

    rel: str
    kind: str
    what: str
    why: str
    level: str = "warn"            # note | warn | error
    updates: dict | None = None


class Plan:
    """What the tree would say after the pass. Decided without writing."""

    def __init__(self, root: pathlib.Path, nodes: list[Node],
                 findings: list[Finding]):
        self.root = root
        self.nodes = nodes
        self.findings = findings

    @property
    def writes(self) -> list[Finding]:
        return [f for f in self.findings if f.updates]

    @property
    def problems(self) -> list[Finding]:
        return [f for f in self.findings if not f.updates]

    def pending(self) -> dict[str, tuple[dict, list[str]]]:
        """`{rel: (merged updates, reasons)}` -- exactly what `apply` will write.

        One leaf can be named by several findings: `old.md` takes
        `superseded_by:` from its successor and `trust:` from the same finding
        set, and could take a third from a contradiction. Merging here rather
        than inside `apply` means what will be written is inspectable -- and
        testable -- without writing it, which is the same `plan()`/`apply()`
        split the rest of the pass uses and the thing the CLI's dry report is.
        Two `set_fields` calls on one file would also race each other.
        """
        merged: dict[str, dict] = {}
        reasons: dict[str, list[str]] = {}
        for f in self.writes:
            merged.setdefault(f.rel, {}).update(f.updates)
            reasons.setdefault(f.rel, []).append(f.what)
        return {rel: (updates, reasons[rel]) for rel, updates in merged.items()}

    def apply(self) -> list[tuple[str, str]]:
        """Write every appliable marking. Returns what actually changed.

        Uses the same line-surgical writer as stages 2 and 5a, so key order and
        trailing `# comments` survive; a parse-then-reserialise round trip would
        destroy M1's provenance comments and cannot reconstruct them.
        """
        changed: list[tuple[str, str]] = []
        for rel, (updates, reasons) in sorted(self.pending().items()):
            path = self.root / rel
            try:
                if frontmatter.update(path, updates):
                    changed.append((rel, "; ".join(reasons)))
            except (ValueError, OSError):
                # No frontmatter, or vanished between plan and apply. Neither is
                # reachable from `plan` (the node was read to build it) and
                # neither may take the pass down: the finding was reported, and
                # the next pass reports it again.
                continue
        return changed


def _resolve(ref: str, by_rel: dict, by_name: dict) -> Node | None:
    """A `supersedes:`/`contradicts:` value -> the Node it names, or None.

    Three spellings are accepted because the tree contains all three and a
    resolver that accepted one would report the other two as dangling:
      * `knowledge/system/consolidation/foo.md`   the leaf contract's wording ("path of a leaf")
      * `meta/foo.md`             relative to `knowledge/`
      * `foo`                     the bare stem, which is what `related:` uses
    """
    ref = ref.strip().strip("[]").strip()
    if not ref:
        return None
    if ref.startswith(roots.MEMORY_REL + "/"):
        ref = ref[len(roots.MEMORY_REL + "/"):]
    ref = ref.rstrip("/")
    stem = pathlib.PurePosixPath(ref).stem
    cands = [ref]
    if not ref.endswith(".md"):
        cands.append(f"{ref}.md")
    for c in list(cands):
        cands.append(f"knowledge/{c}")
    for c in cands:
        node = by_rel.get(c)
        if node is not None:
            return node
    return by_name.get(stem)


def _supersession_cycle(start: Node, next_of: dict) -> list[str] | None:
    """The cycle reachable from `start`, or None. Iterative: the graph is small
    but a recursive walk over a hostile chain is how a nightly pass dies."""
    seen, order, cur = {}, [], start
    while cur is not None:
        if cur.rel in seen:
            return order[seen[cur.rel]:] + [cur.rel]
        seen[cur.rel] = len(order)
        order.append(cur.rel)
        cur = next_of.get(cur.rel)
    return None


def _tokens(node: Node) -> set[str]:
    text = " ".join([node.title, str(node.fm.get("summary") or "")]
                    + node.list_of("triggers") + node.list_of("tags"))
    return {w for w in WORD.findall(text.lower()) if w not in STOPWORDS}


def _resolved(node: Node, key: str, by_rel: dict, by_name: dict) -> set:
    """The rels one node's reference list actually names.

    Exists because a reference has two legal spellings in this tree and the
    EXISTING data uses both: `related:`-style bare stems are what the skills
    carry (`superseded_by: diagnosing-bugs`), while the leaf contract's wording
    is a path (`supersedes: knowledge/system/consolidation/old.md`). Comparing a raw
    string against a rel path therefore never matches, and a check that never
    matches re-applies the same marking every night forever.
    """
    out = set()
    for ref in node.list_of(key):
        tgt = _resolve(ref, by_rel, by_name)
        if tgt is not None:
            out.add(tgt.rel)
    return out


def _name_of(rel: str, by_rel: dict) -> str:
    """What to WRITE when recording a reference to `rel`.

    The bare stem, matching `related:` and matching what is already on disk.
    A rel path would resolve too, but two spellings for one field in one tree is
    how the next reader concludes the two entries mean different things.
    """
    node = by_rel.get(rel)
    return node.name if node is not None else rel


def plan(root: pathlib.Path = None) -> Plan:
    root = pathlib.Path(root or DEFAULT_ROOT)
    nodes: list[Node] = []
    for p in sorted((root / "knowledge").rglob("*.md")):
        if p.name in SKIP_NAMES:
            continue
        nodes.append(_node(p, root))
    # `rglob`, not a fixed depth: O6b put the branch and the subject in the
    # path, and a hardcoded `*/*/` silently emptied this population the moment
    # it did -- the same failure `tree.py` had.
    for p in sorted((root / "skills").rglob("SKILL.md")):
        nodes.append(_node(p, root))
    live = [n for n in nodes if n.fm]

    by_rel = {n.rel: n for n in live}
    by_name: dict[str, Node] = {}
    for n in live:
        by_name.setdefault(n.name, n)      # first wins; the report names rels

    findings: list[Finding] = []
    # Resolved relations, computed once. Every check below reads these sets
    # rather than re-resolving, so "is it already recorded" and "what do we
    # write" cannot drift apart.
    supersedes: dict[str, list[Node]] = {}     # superseder rel -> [superseded]
    for n in live:
        for ref in n.list_of(SUPERSEDES):
            tgt = _resolve(ref, by_rel, by_name)
            if tgt is None:
                # AN EDGE TO `external` RESOLVES TO *OUTSIDE*, NOT TO *NOTHING*.
                # Both open `dangling-supersession` items named real files
                # outside the memory tree (`02_AREAS/...`, `~/.claude/...`): the
                # claim was true and the edge's RANGE was too narrow, so the
                # ontology declares the range and this stage stops reporting a
                # true claim as a defect. No finding, and -- stated rather than
                # left to be discovered -- NO `superseded_by:` back-pointer is
                # derived: there is nothing in this tree to write one into
                # (SPECS.md O1d).
                if ontology.resolve_type(ref, agents=root) == "external":
                    continue
                findings.append(Finding(
                    n.rel, "dangling-supersession",
                    f"`supersedes: {ref}` names nothing in the memory tree",
                    "either the leaf was renamed (fix the reference) or it was "
                    "never a leaf here (drop the claim) — as written this leaf "
                    "asserts a precedence over nothing"))
                continue
            if tgt.rel == n.rel:
                findings.append(Finding(
                    n.rel, "self-supersession",
                    f"`supersedes: {ref}` resolves to this leaf",
                    "a leaf cannot replace itself — the relation is a loop of "
                    "length one and no precedence follows from it"))
                continue
            supersedes.setdefault(n.rel, []).append(tgt)

    next_of: dict[str, Node] = {k: v[0] for k, v in supersedes.items()}
    # A cycle first, and every edge inside one is then OFF the marking list: if
    # a -> b -> a then no leaf in the loop can be the current one, so marking
    # either as superseded asserts a precedence that does not exist. The error
    # finding is the whole output for those leaves.
    in_cycle: set[str] = set()
    reported_cycles: set = set()
    for n in live:
        cyc = _supersession_cycle(n, next_of)
        if not cyc:
            continue
        in_cycle.update(cyc)
        key = tuple(sorted(set(cyc)))
        if key in reported_cycles:
            continue
        reported_cycles.add(key)
        findings.append(Finding(
            n.rel, "supersession-cycle",
            "supersedes chain loops: " + " → ".join(cyc),
            "no leaf in the loop can be the current one, so no precedence "
            "can be applied to any of them — a person breaks the loop",
            level="error"))

    for rel in sorted(supersedes):
        if rel in in_cycle:
            continue
        for tgt in supersedes[rel]:
            if tgt.rel in in_cycle:
                continue
            # (superseded, superseder). `by_rel[rel]` HOLDS the supersedes:
            # list, so it is the superseder -- passing it first inverts every
            # finding below, and the inverted text reads perfectly plausibly.
            findings += _supersession_findings(tgt, by_rel[rel], by_rel, by_name)

    # A back-pointer with no claim behind it. Reported, and deliberately NOT
    # applied in the other direction: `superseded_by:` is derived, so a missing
    # `supersedes:` is either a withdrawn claim or a lost one, and re-asserting
    # a withdrawn claim would deprecate a live leaf. The conservative error.
    for n in live:
        for rel in sorted(_resolved(n, SUPERSEDED_BY, by_rel, by_name)):
            src = by_rel.get(rel)
            if src is None or src.rel not in supersedes or n.rel not in \
                    {x.rel for x in supersedes[src.rel]}:
                findings.append(Finding(
                    n.rel, "unclaimed-supersession-backlink",
                    f"`superseded_by:` names `{rel}`, which does not declare "
                    f"`supersedes: {n.name}`",
                    "`superseded_by:` is DERIVED — never authored by hand — so "
                    "this marks a relation one side has withdrawn or lost. Not "
                    "re-applied in the other direction: re-asserting a "
                    "withdrawn claim would deprecate a live leaf"))

    # ── declared contradictions ────────────────────────────────────────────
    seen_pairs = set()
    for n in live:
        for ref in n.list_of(CONTRADICTS):
            tgt = _resolve(ref, by_rel, by_name)
            if tgt is None:
                findings.append(Finding(
                    n.rel, "dangling-contradiction",
                    f"`contradicts: {ref}` names nothing in the memory tree",
                    "a conflict with a leaf that does not exist cannot be "
                    "resolved — fix the reference or drop the claim"))
                continue
            if tgt.rel == n.rel:
                continue
            key = tuple(sorted((n.rel, tgt.rel)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            findings += _contradiction_findings(n, tgt, by_rel, by_name)

    findings += _overlap_findings(live, seen_pairs, next_of)

    order = {"error": 0, "warn": 1, "note": 2}
    findings.sort(key=lambda f: (order.get(f.level, 3), f.kind, f.rel))
    return Plan(root, nodes, findings)


def _node(p: pathlib.Path, root: pathlib.Path) -> Node:
    try:
        text = p.read_text()
    except OSError:
        text = ""
    fm = frontmatter.parse(text)
    return Node(p.relative_to(root).as_posix(), p, fm, fm.get("_body", ""))


# ── supersedes: an asserted decision, made self-consistent ───────────────────

def _supersession_findings(old: Node, new: Node, by_rel: dict,
                           by_name: dict) -> list[Finding]:
    """`new` declares `old` superseded. Make the tree say so everywhere.

    Argument order is the whole correctness of this function and was wrong on
    the first wiring: `supersedes:` runs superseder -> superseded, so getting it
    backwards inverts every finding, and the resulting text reads perfectly
    plausibly ("X supersedes this leaf" on the leaf X is replaced BY). The names
    are the ones the reader needs; the call site is the thing to check.

    Three findings, in the order a reader meets them:
      1. The back-pointer. `related:` established the closure rule for links;
         this is the same rule for precedence, and it is the mechanical part --
         a symmetric fact only one side recorded.
      2. The mark. The superseded leaf is still scored and routed as current.
         NOT writing it here is the whole bug L4 names.
      3. The contradiction between the declaration and the dates, when there is
         one. Reported, never applied: the author asserted a precedence, the
         `last_verified` values suggest the winner was never re-checked, and a
         module that silently overrode either would be wrong roughly half the
         time with no way to tell which half.
    """
    out: list[Finding] = []
    if old.human:
        out.append(Finding(
            old.rel, "human-owned-superseded",
            f"`{new.rel}` declares this leaf superseded",
            "authority: human / a directive path — reported, never marked "
            "(consolidation-cycle.md invariant 2)", level="warn"))
    else:
        if new.rel not in _resolved(old, SUPERSEDED_BY, by_rel, by_name):
            out.append(Finding(
                old.rel, "missing-supersession-backlink",
                f"`{new.rel}` supersedes this leaf; `{SUPERSEDED_BY}:` does not "
                f"name it",
                "the reverse of `supersedes:`, closed the same way `related:` "
                "is — one side recording the relation is not enough for a "
                "reader arriving at this leaf",
                updates={SUPERSEDED_BY: old.list_of(SUPERSEDED_BY)
                          + [_name_of(new.rel, by_rel)]}))
        trust = (old.fm.get("trust") or "trusted").strip()
        if trust != DEPRECATED:
            out.append(Finding(
                old.rel, "unmarked-superseded",
                f"still `trust: {trust}` while `{new.rel}` replaces it",
                "a superseded leaf that is not marked is still routed and "
                "still scored as current — this is the contradiction the "
                "conflict module exists to close",
                updates={"trust": DEPRECATED}))
    a, b = new.verified(), old.verified()
    if a and b and b > a:
        out.append(Finding(
            new.rel, "declaration-outranks-dates",
            f"`supersedes: {old.name}`, but that leaf was verified later "
            f"({b.isoformat()} > {a.isoformat()})",
            "the declaration is the stronger signal, so nothing is applied — "
            "but the winner looks un-reverified, and the fix is a "
            "`last_verified:` on the winner or a withdrawn claim", level="warn"))
    return out


# ── contradicts: symmetric, resolved by ISO-8601 precedence ──────────────────

def _contradiction_findings(a: Node, b: Node, by_rel: dict,
                            by_name: dict) -> list[Finding]:
    """Resolve a declared contradiction, or say why nothing can be.

    The winner is the leaf verified later. `stability` does not enter it:
    precedence is about which claim is CURRENT, and a leaf not checked against
    the world in a year is not current because it is old.
    """
    da, db = a.verified(), b.verified()
    if da is None or db is None:
        side = a.rel if da is None else b.rel
        return [Finding(a.rel, "contradiction-undecidable",
                        f"`contradicts: {b.name}` and `{side}` has no usable "
                        f"`last_verified:`",
                        "chronological precedence is the only rule this module "
                        "has; with a missing date there is no winner to mark, "
                        "so this needs a person, not a guess", level="warn")]
    if da == db:
        return [Finding(a.rel, "contradiction-tied",
                        f"`contradicts: {b.name}` and both were verified on "
                        f"{da.isoformat()}",
                        "equal dates cannot order two claims — re-verify one, "
                        "or say which one wins with `supersedes:`", level="warn")]

    win, lose = (a, b) if da > db else (b, a)
    later, earlier = max(da, db).isoformat(), min(da, db).isoformat()

    already = (win.rel in _resolved(lose, SUPERSEDED_BY, by_rel, by_name)
               and (lose.fm.get("trust") or "").strip() == DEPRECATED)
    if already:
        # ALREADY RESOLVED -> say nothing. This stage runs nightly, and a
        # resolved conflict that kept re-reporting itself is exactly the unread
        # report consolidation-cycle.md names as the failure mode this design is
        # most exposed to. The state is legible from the frontmatter, which is
        # the point of writing it there rather than to a ledger.
        return []

    if lose.human:
        return [Finding(lose.rel, "human-owned-contradiction",
                        f"`{win.rel}` was verified later ({later}) and disagrees "
                        f"with this leaf",
                        "a directive path is never marked by the pass — the "
                        "resolution is the reader's", level="warn")]

    out = [Finding(lose.rel, "contradiction-resolved",
                   f"`{win.rel}` verified later ({later} > {earlier}) and "
                   f"disagrees",
                   "ISO-8601 precedence: the more recently verified claim is "
                   "the current one; the loser is marked, never deleted",
                   updates={SUPERSEDED_BY: lose.list_of(SUPERSEDED_BY)
                            + [_name_of(win.rel, by_rel)],
                            "trust": DEPRECATED})]
    if lose.rel not in _resolved(win, SUPERSEDES, by_rel, by_name):
        out.append(Finding(win.rel, "contradiction-won",
                           f"resolved against `{lose.rel}` by later verification",
                           "recorded on the winner too, so either end of the "
                           "pair tells the same story",
                           updates={SUPERSEDES: win.list_of(SUPERSEDES)
                                    + [_name_of(lose.rel, by_rel)]}))
    return out


# ── overlap: candidates for a person, explicitly not contradictions ──────────

def _overlap_findings(live: list[Node], declared: set,
                      next_of: dict) -> list[Finding]:
    """Leaves that share enough vocabulary to be about the same thing.

    Deliberately NOT called a conflict. See the module docstring: this finds the
    pair to read, and a report that overstated it would be the distractor
    problem wearing a different hat.
    """
    by_rel = {n.rel: n for n in live}
    tokens = {n.rel: _tokens(n) for n in live}
    by_token: dict[str, list[Node]] = {}
    for n in live:
        for t in tokens[n.rel]:
            by_token.setdefault(t, []).append(n)

    counted: dict[tuple[str, str], int] = {}
    for token, holders in by_token.items():
        if len(holders) < 2:
            continue
        for i, x in enumerate(holders):
            for y in holders[i + 1:]:
                key = tuple(sorted((x.rel, y.rel)))
                counted[key] = counted.get(key, 0) + 1

    out: list[Finding] = []
    for (rel_a, rel_b), shared in sorted(counted.items(),
                                         key=lambda kv: (-kv[1], kv[0])):
        if shared < MIN_SHARED_TERMS:
            continue
        if (rel_a, rel_b) in declared:
            continue                     # already declared; a finding exists
        if next_of.get(rel_a) or next_of.get(rel_b):
            continue                     # already ordered; not a candidate
        ta, tb = tokens[rel_a], tokens[rel_b]
        jac = shared / len(ta | tb) if (ta | tb) else 0.0
        if jac < MIN_OVERLAP_JACCARD:
            continue
        out.append(Finding(rel_a, "overlapping-leaf",
                           f"`{rel_b}` shares {shared} terms "
                           f"(jaccard {jac:.2f}): {' '.join(sorted(ta & tb))}",
                           "NOT a detected contradiction — two leaves about the "
                           "same subject are where one would hide. Read the pair; "
                           "if they disagree, add `contradicts:` and this stage "
                           "resolves it by `last_verified:`", level="note"))
    return out[:MAX_OVERLAP]


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    """Thin adapter over `plan`. Exit codes: 0 ok, 3 --check found pending
    marking. Nothing here exits 1: this stage has no error condition, only
    findings, and a code that means "found something" would train the reader to
    ignore it."""
    ap = argparse.ArgumentParser(prog="familiar consolidation conflicts")
    ap.add_argument("--check", action="store_true",
                    help="report pending marking and exit 3; write nothing")
    ap.add_argument("--apply", action="store_true",
                    help="write the marking. Without it this is a report.")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    p = plan()
    for f in p.findings:
        mark = "APPLY " if f.updates else f.level.upper().ljust(5)
        print(f"{mark} [{f.kind}] {f.rel}")
        print(f"       {f.what}")
        print(f"       {f.why}")
    print(f"\n{len(p.nodes)} documents, {len(p.findings)} finding(s): "
          f"{len(p.writes)} appliable, {len(p.problems)} for a person")

    if args.check:
        if p.writes:
            print(f"{len(p.writes)} file(s) would be marked")
            return 3
        return 0
    if args.apply:
        changed = p.apply()
        print(f"marked {len(changed)} file(s)")
    return 0


# ── stage entry point ────────────────────────────────────────────────────────
def run(ctx) -> bool:
    """Stage 5d of the pass. Applies declared precedence; reports the rest.

    Runs after `consolidate` (4, which creates leaves) and after `associate`
    (5a, whose back-link closure is the same mechanical rule one field over), and
    before `downscale` (6) so a superseded leaf is already `deprecated` when the
    quadrant table reads it -- otherwise a leaf that has been replaced would be
    proposed for a demotion it does not need.
    """
    p = plan(ctx.agents)
    for f in p.problems:
        ctx.propose("5d", f.kind, f.rel, f.what, f.why, target_kind="leaf")

    if ctx.dry_run:
        if p.writes:
            ctx.note("5d", f"{len(p.writes)} marking(s) pending; a real run "
                           f"would apply them (declared supersession only)")
        return True

    changed = p.apply()
    for rel, what in changed:
        ctx.act("5d", rel, f"marked superseded — {what}")
    if not p.findings:
        ctx.note("5d", f"{len(p.nodes)} documents checked: no supersession or "
                       f"contradiction declared, and no overlapping pair above "
                       f"the threshold ({MIN_SHARED_TERMS} shared terms, "
                       f"jaccard {MIN_OVERLAP_JACCARD})")
    return True
