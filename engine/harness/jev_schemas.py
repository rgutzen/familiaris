"""jev_schemas -- one question per item kind, and the hash that pins its wording.

AN UNDECLARED KIND IS AN ERROR, NOT A DEFAULT. The rule N1 set for stages and
`invocation` sets for flags, applied to the model's input: a kind the report can
raise and this module has no question for must fail loudly, not be asked a
generic question and answered anyway. `coverage()` is what the test asserts
against the most recent report, so a stage that starts raising a new kind cannot
silently go un-asked.

WHY THE PAYLOAD SITS IN `criteria` AND `instructions`, AND `state` IS THE ITEM.
The skill-suggestion cookbook's pattern: the stable text goes in the question,
the volatile text in the state. It is also what makes batching cheap -- N items
share one question object, and the accuracy does not fall off with the state size
the way putting the criteria inline per item does.

THE SCHEMA HASH IS THE VALIDITY ENVELOPE. A change to a question's WORDING
changes its hash, and a hash change starts a new calibration population: a
threshold calibrated against the old wording means nothing against the new one.
The hash covers the question object only -- not the state, which changes every
night by design. Enforced in one place (`schema_hash`) rather than documented,
because a documented rule about hashing is a rule that gets forgotten.

WHAT IS NOT HERE: THE CLASS CRITERIA. `config/knowledge/subjects.yaml` owns the class list, and its
statement of the rule is that the `criteria` map for a `choice` question IS
class-with-membership-criteria -- one artifact with two readers, never one each.
The labelling questions therefore hold the ONTOLOGY'S map OBJECT rather than a
copy of it (`ontology.criteria` is identity-stable, and a test asserts `is`),
and `NEEDS_ONTOLOGY` -- the list of kinds that cannot be asked without it -- is
empty only because that list has landed. It is declared rather than deleted,
because the next classification task needs the same rule: a kind this module
cannot ask must fail loudly, not be asked a generic question and answered anyway.
"""
from __future__ import annotations

import hashlib
import json

from knowledge import ontology

# A question object, as `POST /v1/systemone` takes it. `criteria` is optional for
# a noul (it can be inferred from `instructions`), required for choice and score.
NOUL, CHOICE, SCORE = "noul", "choice", "score"


class UndeclaredKind(KeyError):
    """A kind with no question. Never defaulted -- see the module docstring."""


def _noul(instructions, true=None, false=None):
    q = {"type": NOUL, "instructions": instructions}
    if true or false:
        q["criteria"] = {"true": true or "yes", "false": false or "no"}
    return q


def _choice(instructions, options):
    return {"type": CHOICE, "instructions": instructions,
            "criteria": {o: None for o in options}}


def _score(instructions, levels):
    return {"type": SCORE, "instructions": instructions, "criteria": list(levels)}


# ── the questions, one per kind ──────────────────────────────────────────────
# The `action` describes what `decide N` does when the band says drop. It is
# prose for the report, not a machine field: `decide` reads the band, never this.
#
# Disposition kinds (`drop`-able): the question is "should this be done as
# proposed?" and a high probability means yes.
#
# PROMOTION kinds (`trust`, `supersedes`, `contradicts`) are `ask`-only and get
# NO question here that could ever band them -- `PROMOTED` below lists them so the
# band rule (2d) can assert they are never auto-accepted.
SCHEMAS: dict[str, dict] = {
    "contradiction-won": {
        "question": _noul(
            "Two leaves contradict and one already carries the marking that it "
            "won. Answer whether the marking is still CORRECT -- that is, whether "
            "the winner's assertion still holds against the loser's.",
            true="the marking is correct", false="the marking is stale"),
        "action": "confirm the winner keeps the mark",
    },
    "missing-supersession-backlink": {
        "question": _noul(
            "A leaf declares it supersedes another, but the superseded leaf "
            "carries no back-reference. Answer whether the backlink should be "
            "ADDED so the relation is navigable from both ends.",
            true="add the backlink", false="the one-way link is intentional"),
        "action": "add the backlink",
    },
    "unclaimed-supersession-backlink": {
        "question": _noul(
            "A leaf carries a back-reference to a supersession that no leaf "
            "declares. Answer whether the dangling back-reference should be "
            "REMOVED.",
            true="remove the back-reference", false="keep it — the claim may return"),
        "action": "remove the back-reference",
    },
    "human-owned-superseded": {
        "question": _noul(
            "A supersession involves a leaf under `conventions/**`, which is "
            "directive, so an agent may never edit it. Answer whether it "
            "should be brought to the USER.",
            true="bring it to the user", false="an agent may settle it"),
        "action": "bring it to the user",
    },
    # -- stage 4: distillation proposals, over leaf content ------------------
    "extend-leaf": {
        "question": _noul(
            "The `state` is a fact observed in recent journal entries, and the "
            "`target` leaf. Answer whether this fact DUPLICATES what the leaf "
            "already records. Answer no only if the leaf genuinely lacks it.",
            true="the leaf already records this fact",
            false="the leaf does not record this fact"),
        "action": "the fact is already in the leaf — drop",
    },
    "new-leaf": {
        "question": _noul(
            "The fact in the `state` has no leaf to attach to. Answer whether it "
            "is DURABLE enough to deserve its own leaf: a fact about this machine "
            "or this user's practice that will still be true in a month. Answer "
            "no for anything transient, one-off or already covered by a skill.",
            true="durable, deserves a leaf",
            false="transient or already covered"),
        "action": "durable — write the leaf",
    },
    "supersede-leaf": {
        "question": _noul(
            "The `state` proposes that one leaf replaces another. Answer whether "
            "the replacement is REAL -- the newer leaf covers everything the "
            "older one asserted and contradicts it where they differ. Answer no "
            "if the two are merely adjacent, or the older one is still correct "
            "for some cases.",
            true="the replacement is complete and correct",
            false="the older leaf still holds in some cases"),
        "action": "supersede the older leaf",
    },
    # -- stage 5a: relations between leaves ----------------------------------
    "dangling-link": {
        "question": _noul(
            "A leaf's `related:` names another leaf, and no such leaf exists. "
            "Answer whether the name should be DROPPED from the reference. Answer "
            "no if it names a leaf that is plausibly yet to be written and the "
            "reference is a useful reminder.",
            true="drop the reference",
            false="keep it — the leaf may yet be written"),
        "action": "drop the reference",
    },
    "dangling-supersession": {
        "question": _noul(
            "A leaf's `supersedes:` names something that exists in no memory "
            "tree. Answer whether that thing was NEVER a leaf here (so the claim "
            "should be dropped). Answer no if it names a real file that was "
            "renamed or lives outside the tree, in which case the REFERENCE "
            "should be fixed instead.",
            true="it was never a leaf here — drop the claim",
            false="the reference is wrong but the thing is real — fix it"),
        "action": "drop the claim",
    },
    "knowledge→skill link": {
        "question": _noul(
            "A knowledge leaf's body cites a skill. `knowledge-vs-skills.md` "
            "states the dependency runs skill -> leaf and never the reverse. "
            "Answer whether the citation should be REMOVED. Answer no if it is a "
            "legitimate cross-reference rather than a dependency.",
            true="remove the citation",
            false="it is only a cross-reference — keep it"),
        "action": "remove the citation",
    },
    "backlink": {
        "question": _noul(
            "Two leaves reference each other's topic but only one carries the "
            "`related:` entry. Answer whether the missing backlink should be "
            "ADDED.",
            true="add the backlink", false="leave it asymmetric"),
        "action": "add the backlink",
    },
    "link": {
        "question": _noul(
            "An association between two leaves was measured, not asserted. "
            "Answer whether it is STRONG enough to record as a `related:` entry, "
            "rather than an artefact of shared vocabulary.",
            true="record the association", false="shared vocabulary only"),
        "action": "record the association",
    },
    "trigger": {
        "question": _noul(
            "A term appears consistently in the usage log's `terms:` for one "
            "skill. Answer whether it should be PROMOTED into that skill's "
            "`triggers:` -- that is, whether the term genuinely predicts the "
            "skill is wanted, rather than being incidental vocabulary.",
            true="promote the term to a trigger",
            false="incidental vocabulary — do not promote"),
        "action": "promote the term",
    },
    # -- stage 5d: contradictions and supersession ----------------------------
    "contradiction-resolved": {
        "question": _noul(
            "Two leaves contradict and their dates are not tied. Answer whether "
            "the NEWER one should WIN -- that is, whether the newer assertion "
            "supersedes the older rather than the two describing different "
            "cases.",
            true="the newer leaf wins", false="they describe different cases"),
        "action": "mark the older superseded",
    },
    "contradiction-tied": {
        "question": _noul(
            "Two leaves contradict and carry the SAME date. Answer whether they "
            "can be RECONCILED as one assertion. Answer no if a human must "
            "choose between them.",
            true="they reconcile — merge them", false="a human must choose"),
        "action": "merge the two assertions",
    },
    "contradiction-undecidable": {
        "question": _noul(
            "Two leaves contradict and neither is clearly newer. Answer whether "
            "the newer-by-one-day one should be TREATED AS the later word, or "
            "whether the dates are too close to settle it.",
            true="treat the later date as decisive",
            false="too close to settle — needs a human"),
        "action": "treat the later date as decisive",
    },
    "dangling-contradiction": {
        "question": _noul(
            "A leaf's `contradicts:` names something that exists in no memory "
            "tree. Answer whether the claim should be DROPPED.",
            true="drop the claim", false="keep it — the target is real but moved"),
        "action": "drop the claim",
    },
    "self-supersession": {
        "question": _noul(
            "A leaf declares that it supersedes ITSELF. Answer whether the "
            "declaration should be REMOVED as an error.",
            true="remove the self-declaration", false="it is intentional"),
        "action": "remove the self-declaration",
    },
    "supersession-cycle": {
        "question": _noul(
            "Three or more leaves declare a supersession cycle (A supersedes B "
            "supersedes C supersedes A). Answer whether the WEAKEST edge in the "
            "cycle (the one whose dates are closest together) should be dropped "
            "to break it.",
            true="drop the weakest edge", false="the cycle is real — needs a human"),
        "action": "drop the weakest edge",
    },
    "declaration-outranks-dates": {
        "question": _noul(
            "A leaf declares it supersedes another, but the declared loser is "
            "NEWER by date. The declaration is the governance mechanism and "
            "outranks the dates mechanically. Answer whether the declaration "
            "should be KEPT despite that -- that is, whether it was deliberate.",
            true="keep the declaration", false="the declaration is stale — reverse it"),
        "action": "keep the declaration",
    },
    "unmarked-superseded": {
        "question": _noul(
            "A leaf is superseded by another but carries no marking. Answer "
            "whether the marking should be ADDED mechanically.",
            true="mark it superseded", false="leave it unmarked"),
        "action": "mark the leaf superseded",
    },
    "overlapping-leaf": {
        "question": _noul(
            "Two leaves overlap substantially in the vocabulary of their titles, "
            "summaries, triggers and tags, but neither declares a relation. "
            "Answer whether they are genuinely the SAME topic and should be "
            "merged.",
            true="same topic — merge", false="shared words only — keep both"),
        "action": "merge the two leaves",
    },
    "human-owned-contradiction": {
        "question": _noul(
            "A contradiction involves a leaf under `conventions/**`, which is "
            "directive. An agent may never edit it. Answer whether the matter "
            "needs the USER's decision (always yes for this kind -- the question "
            "is recorded so the item carries a probability like any other).",
            true="the user must decide", false="the agent may settle it"),
        "action": "bring it to the user",
    },
    # -- the stages' own bookkeeping -----------------------------------------
    "human-owned": {
        "question": _noul(
            "A document under a directive path was proposed for a change an "
            "agent may not make. Answer whether it should be brought to the USER.",
            true="bring it to the user", false="an agent may act"),
        "action": "bring it to the user",
    },
    "adopt": {
        "question": _noul(
            "A tool or skill is used often enough that keeping it is the "
            "question. Answer whether it should be ADOPTED as a standing part of "
            "the practice, rather than used ad hoc.",
            true="adopt it as standing practice", false="keep it ad hoc"),
        "action": "adopt as standing practice",
    },
    "re-verify": {
        "question": _noul(
            "A leaf has not been re-checked in long enough that its staleness is "
            "the question. Answer whether the FACT it records is still true on "
            "this machine as far as the state shows.",
            true="still true — reset the clock", false="doubtful — needs a check"),
        "action": "re-verify the leaf",
    },
    "demote": {
        "question": _noul(
            "A leaf's score places it low enough to be a demotion candidate. "
            "Answer whether it should be DEMOTED -- that is, whether it is "
            "genuinely superseded or low-value rather than merely unused.",
            true="demote it", false="unused but still valuable"),
        "action": "demote the leaf",
    },
    "archive": {
        "question": _noul(
            "A leaf's score places it in the pruning quadrant. Answer whether it "
            "should be ARCHIVED rather than deleted -- that is, whether it is "
            "obsolete but was once true and is worth keeping in the record.",
            true="archive it", false="delete it"),
        "action": "archive the leaf",
    },
    "stability": {
        "question": _noul(
            "A leaf's `stability:` claim may no longer match how often it "
            "actually changes. Answer whether the claim should be MOVED (made "
            "more volatile or more settled) to match the observed churn.",
            true="move the stability claim", false="the claim is right"),
        "action": "move the stability claim",
    },
    # -- the decision ledger, surfaced nightly (stage 4) ---------------------
    "decision": {
        "question": _noul(
            "A decision the user recorded has not landed anywhere durable. "
            "Answer whether the stated TARGET is already covered by the leaf "
            "named in the state -- that is, whether the decision has effectively "
            "been captured and the item can close.",
            true="already captured — close it",
            false="not captured — keep raising it"),
        "action": "mark the decision captured",
    },
}

# Kinds whose disposition is a PROMOTION. `trust:`, `supersedes:` and
# `contradicts:` are written only on an explicit accept (SPECS.md §Write
# authority); a band may never do it. Listed here as data so the band rule (2d)
# asserts against a list rather than a second copy of the rule.
PROMOTED = ("supersede-leaf", "contradiction-resolved", "contradiction-won",
            "unmarked-superseded", "declaration-outranks-dates")

# ── the classification questions, whose criteria map IS the ontology ─────────
#
# RESOLVED 2026-09-30, by `ontology SPECS` O1n: the class list landed, so
# the two kinds that were declared awaiting it are built here FROM the
# ontology's maps, by REFERENCE. `ontology.criteria(name)` returns the same
# object on every call, which is what makes the identity testable -- a copy that
# happens to match today is exactly the second-copy drift this whole track
# exists to prevent (ontology PLAN §4: one artifact, two readers).
#
# THE THIRD QUESTION IS NOT IN O1n's PROSE. `entry-subject` names `areas` as a
# terminal that OPENS a question over A-P; a terminal with no question behind it
# would be a dead end, so `entry-area` is that question, built from the Area
# vocabulary the master config already owns (`ontology.criteria("area")`).
#
# THE STATE IS THE ITEM, THE CRITERIA ARE THE QUESTION. One question object is
# shared by every item in a batch, and each item's `state` carries its title,
# summary, section headings and the opening of its body -- the cookbook pattern
# the module docstring states, and the reason a labelling run over 238 entries
# is one call. The state is built ONCE, by `stages/label.state`.
#
# 2026-10-02 (`ontology SPECS` O4d): the body opening joined the state,
# because the labeller O5a needs sees the whole document and O4b had tested a
# harder question than that; and `leaf-subject` lost its "filed in one place"
# clause, which pointed at the folder the experiment deliberately withholds.
SCHEMAS["leaf-subject"] = {
    "question": {
        "type": CHOICE,
        "instructions":
            "The state is one document: its title, its summary, its section "
            "headings and the opening of its body. Assign it to exactly ONE "
            "subject from `criteria`. Each subject names a PLACE IN THE SYSTEM "
            "you could point at, and each carries the question that decides "
            "membership: what change would make this document wrong? Choose "
            "the subject whose criteria that change falsifies. Answer with the "
            "id alone.",
        "criteria": ontology.criteria("subject"),
    },
    "action": "write the leaf's subject",
}

SCHEMAS["entry-subject"] = {
    "question": {
        "type": CHOICE,
        "instructions":
            "The state is one journal entry, the record of a session: its "
            "title, its section headings and the opening of its body. Assign "
            "it to exactly ONE subject from `criteria`, or to `areas` when the "
            "entry is SUBJECT KNOWLEDGE for one P.A.Z.R.A.S Area rather than "
            "something about this system. Most entries are about the system; "
            "`areas` is for the session where the work itself was the subject "
            "(a paper, a dataset, a design). Answer with the id alone.",
        "criteria": ontology.criteria("entry-subject"),
    },
    "action": "write the entry's subject",
}

SCHEMAS["entry-area"] = {
    "question": {
        "type": CHOICE,
        "instructions":
            "Asked only of an entry classified `areas`. Assign it to exactly "
            "one Area code from `criteria`. The Area vocabulary mirrors "
            "`~/02_AREAS/` and is deliberately personal: choose the area of "
            "responsibility the work belongs to, not the discipline it "
            "resembles. Answer with the letter alone.",
        "criteria": ontology.criteria("area"),
    },
    "action": "write the entry's area",
}

# Kinds that need the ontology's class list to be asked at all. EMPTY as of
# 2026-09-30: `leaf-subject`, `entry-subject` and `entry-area` were the first,
# and they now have schemas whose `criteria` maps are imported from
# `ontology.py`. The declaration stays because the next classification task
# needs the same rule: a kind this module cannot ask must fail loudly rather
# than be asked a generic question and answered anyway.
NEEDS_ONTOLOGY: tuple = ()


def question(kind: str) -> dict:
    """The question object for one kind. An undeclared kind raises.

    Accepts the report's hyphenated handle as well as the stored spelling, so a
    kind copied out of the report resolves.
    """
    kind = _canonical(kind)
    try:
        return SCHEMAS[kind]["question"]
    except KeyError:
        raise UndeclaredKind(
            f"no question schema for kind {kind!r}. Add one to "
            f"jev_schemas.SCHEMAS, or declare it in NEEDS_ONTOLOGY if it is a "
            f"classification task awaiting the class list. An undeclared kind is "
            f"an error, not a default.") from None


def action(kind: str) -> str:
    """What `decide N` does for this kind. Prose; `decide` reads the band."""
    return SCHEMAS.get(kind, {}).get("action", "")


def schema_hash(kind: str) -> str:
    """The hash that pins this question's WORDING.

    Covers the question object only. A change here starts a new calibration
    population: thresholds are keyed by `(schema_hash, model)` (SPECS.md 2e), so
    editing the wording cannot silently inherit a threshold calibrated against
    the old one. `sort_keys=True` so key order is not mistaken for a change.
    """
    return hashlib.sha256(
        json.dumps(question(kind), sort_keys=True, ensure_ascii=False)
        .encode()).hexdigest()[:16]


def all_hashes() -> dict:
    return {k: schema_hash(k) for k in sorted(SCHEMAS)}


def is_promotion(kind: str) -> bool:
    return kind in PROMOTED


def _canonical(kind: str) -> str:
    """The stored kind for a spelling that may be a renderer handle.

    The report renders `knowledge→skill link` as `knowledge→skill-link` so the
    columns do not shift, so a kind read back from a report is not necessarily
    the stored spelling. One rule, used by `coverage` and mirrored by
    `queue.of_kind`, so "what a kind is called" has a single answer.
    """
    if kind in SCHEMAS:
        return kind
    spaced = kind.replace("-", " ")
    return spaced if spaced in SCHEMAS else kind


def coverage(kinds) -> dict:
    """Which of `kinds` have a schema, which need the ontology, which are missing.

    The exit criterion's shape: pass the kinds from the most recent report and
    assert `missing` is empty. Returned rather than raised so a caller can report
    the gap in the report itself rather than dying on it. Accepts either spelling
    of a hyphenated kind -- see `_canonical`.
    """
    kinds = sorted({_canonical(k) for k in kinds})
    need = [k for k in kinds if k in NEEDS_ONTOLOGY]
    missing = [k for k in kinds if k not in SCHEMAS and k not in NEEDS_ONTOLOGY]
    return {"covered": [k for k in kinds if k in SCHEMAS],
            "needs_ontology": need, "missing": missing}
