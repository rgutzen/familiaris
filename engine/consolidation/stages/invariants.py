"""invariants -- what each stage of the pass GUARANTEES, declared and checked.

WHY THIS EXISTS. On 2026-09-11 stage 5d shipped with three independent defects
that a 333-test suite was green against, because each one failed silently and
PLAUSIBLY: an inverted argument pair that printed every relation backwards in
sentences that read correctly; a comparison of a bare name against a rel path
that could never match, so the same marking would have been re-applied every
night forever; and a supersession CYCLE that still emitted a marking, asserting
a precedence in a loop where no leaf can be the current one. None raised, none
produced syntactically wrong output, and all three would have survived a human
review of the diff. They were caught only because tests happened to be written
adversarially for that module -- i.e. by author judgement, which is enforcement
level 4 in memory-mechanisms.md's own table and the first thing to go under
context pressure.

The gap is not coverage. `checks.py --audit` reports every test file in
`engine/**` is run by a registry entry, and it did so while these bugs were
live. The gap is that A STAGE COULD ENTER `run.STAGES` WITHOUT EVER STATING
WHAT IT GUARANTEES, so the existence of an invariant depended on the author
imagining the failure.

This module is the missing declaration. It is modelled on the two idioms the
codebase already has for exactly this shape of problem:

  * `invocation.Spec` -- an undeclared flag is an ERROR, not a default. Here:
    a stage in `run.STAGES` with no entry in `DECLARED` fails the gate. That is
    the property a parameterised test over today's stages cannot have.
  * `ranking.unvalidated()` -- a constant nobody has validated must be NAMED in
    the report rather than quietly trusted. Here: an invariant a stage does not
    hold must carry a `reason`, so "this stage is not idempotent" is a recorded
    decision instead of an omission.

THE THREE INVARIANTS, and which bug each would have caught:

  IDEMPOTENCE   `plan(); apply(); plan()` yields zero pending writes. Catches
                bug 2 outright, and needs no knowledge of the domain -- it is a
                pure function of any module exposing plan/apply.
  DISJOINTNESS  in one plan, no file is both an error-level finding and the
                target of a pending write. Catches bug 3: the cycle was an
                error AND a write on the same leaf.
  DIRECTIONAL   which file gets touched is asserted over a GENERATED relation
                graph, not a hand-picked pair. Catches bug 1, which neither of
                the above sees -- both were happy to write to the wrong file.
                Lives in the property tests (`tests/test_stage_invariants.py`),
                because it needs generated input rather than one fixture; the
                declaration here records which stages owe one.

SHAPES. Three stages (`conflict`, `knowledge-index`, `reindex`) are plan/apply
shaped and are checked generically by iterating them. The rest write through
`ctx` and have no plan object to iterate; rewriting six stages to fit one
protocol was rejected as a cost out of proportion to the defect. They declare
instead -- either a DIFFERENT mechanism that holds the invariant (the whole-pass
dry-run snapshot in `tests/test_dry_run_invariant.py`, or proposal-only writing,
which cannot be non-idempotent because it writes nothing), or `N/A` with a
reason. An undeclared stage is still an error; a stage claiming an exemption it
has not justified is still an error. What is NOT allowed is silence.

The fixture is built here rather than in the test suite, deliberately: this gate
must run from `familiar checks selftest --invariants` with no pytest on the path,
because the pass itself is stdlib-only and started by a systemd timer.
"""
from __future__ import annotations

import dataclasses
import pathlib
import subprocess
import tempfile

from lib import roots

# ── the vocabulary of a declaration ──────────────────────────────────────────

PLAN_APPLY = "plan/apply"      # exposes plan(root) -> Plan with .apply()
CTX_WRITE = "ctx-write"        # writes through ctx.act, no plan object
PROPOSAL_ONLY = "proposal-only"  # records ctx.propose and never writes

HELD = "held"          # this module checks it, here
ELSEWHERE = "elsewhere"  # something else checks it; `reason` names what
NOT_APPLICABLE = "n/a"   # the invariant has no content for this stage
OWED = "owed"          # it should hold and nothing checks it yet -- a finding

STATUSES = (HELD, ELSEWHERE, NOT_APPLICABLE, OWED)


@dataclasses.dataclass(frozen=True)
class Claim:
    """One invariant, for one stage, with its status and its justification.

    `reason` is REQUIRED for everything except `held`. That asymmetry is the
    point: claiming the gate checks it is falsifiable by running the gate, so it
    needs no prose. Claiming it does not need checking is not falsifiable by
    anything, so it needs a person's sentence on the record.
    """

    status: str
    reason: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")
        if self.status != HELD and not self.reason:
            raise ValueError(f"status {self.status!r} requires a reason")


@dataclasses.dataclass(frozen=True)
class Declaration:
    """What one stage guarantees. Keyed by its label in `run.STAGES`."""

    stage: str
    shape: str
    idempotent: Claim
    disjoint: Claim
    directional: Claim


# ── the declarations ─────────────────────────────────────────────────────────
#
# Keys are the stage LABELS from run.STAGES, which is the only place a stage's
# name is spelled (see run.py: "a stage never spells its own label"). Two
# labels share stage id 5 and two share id 7; they are separate callables and
# so separate declarations, for the same reason run.py keeps them separate --
# one broken half must not take the other down.

DECLARED: dict[str, Declaration] = {
    "conflicts": Declaration(
        stage="conflicts", shape=PLAN_APPLY,
        idempotent=Claim(HELD),
        disjoint=Claim(HELD),
        directional=Claim(HELD),
    ),
    "knowledge-index": Declaration(
        stage="knowledge-index", shape=PLAN_APPLY,
        idempotent=Claim(HELD),
        disjoint=Claim(HELD),
        directional=Claim(
            NOT_APPLICABLE,
            "renders a whole file from the leaf set; there is no pair of "
            "documents whose ORDER could be inverted, so there is no direction "
            "to assert. Its content is checked by `drift` against the bytes."),
    ),
    "reindex": Declaration(
        stage="reindex", shape=PLAN_APPLY,
        idempotent=Claim(HELD),
        disjoint=Claim(HELD),
        directional=Claim(
            NOT_APPLICABLE,
            "same as knowledge-index: a whole-file render over the skill set, "
            "with no directed relation between two documents."),
    ),
    "preflight": Declaration(
        stage="preflight", shape=CTX_WRITE,
        idempotent=Claim(
            ELSEWHERE,
            "commits the HUMAN's uncommitted work as a snapshot and takes a "
            "lock; running it twice is the resume path the pass is built on, "
            "and is covered by tests/test_preflight.py. It has no plan to "
            "re-derive."),
        disjoint=Claim(
            NOT_APPLICABLE,
            "aborts the pass rather than producing findings; there is no "
            "finding list for a write to collide with."),
        directional=Claim(NOT_APPLICABLE, "no relation between documents."),
    ),
    "replay": Declaration(
        stage="replay", shape=CTX_WRITE,
        idempotent=Claim(
            ELSEWHERE,
            "writes a journal entry per STAGED TRANSCRIPT and consumes the "
            "staging directory, so the second run has no input rather than the "
            "same input. tests/test_replay.py owns that; re-running it here "
            "would need a model call."),
        disjoint=Claim(
            NOT_APPLICABLE,
            "creates new journal entries; it never reports a finding against a "
            "file it also writes."),
        directional=Claim(NOT_APPLICABLE, "no relation between documents."),
    ),
    "aggregate": Declaration(
        stage="aggregate", shape=CTX_WRITE,
        idempotent=Claim(HELD),
        disjoint=Claim(
            NOT_APPLICABLE,
            "folds session counts read off the transcripts and the usage "
            "ledger into frontmatter. It emits "
            "no error-level finding, so the disjointness set is empty on one "
            "side by construction."),
        directional=Claim(NOT_APPLICABLE, "no relation between documents."),
    ),
    "label": Declaration(
        stage="label", shape=PROPOSAL_ONLY,
        idempotent=Claim(
            NOT_APPLICABLE,
            "raises ONE batch proposal over the journal entries that carry no "
            "`subject:` and writes nothing at all -- `subject:` itself is "
            "ontology SPECS O5a's write, deliberately not this stage's, "
            "because an entry labelled early breaks O4's ground truth. There "
            "is no write to repeat. If it ever gains one this claim becomes "
            "OWED."),
        disjoint=Claim(NOT_APPLICABLE, "writes nothing."),
        directional=Claim(
            NOT_APPLICABLE,
            "its proposal relates an entry to a SUBJECT, not to another "
            "document; there is no pair whose order could be inverted."),
    ),
    "score": Declaration(
        stage="score", shape=PROPOSAL_ONLY,
        idempotent=Claim(
            NOT_APPLICABLE,
            "computes R over the scored tree and writes nothing at all; there "
            "is no write to repeat."),
        disjoint=Claim(NOT_APPLICABLE, "writes nothing."),
        directional=Claim(NOT_APPLICABLE, "no relation between documents."),
    ),
    "consolidate": Declaration(
        stage="consolidate", shape=PROPOSAL_ONLY,
        idempotent=Claim(
            NOT_APPLICABLE,
            "proposal-only by design (M2 decision 2): every stage-4 output is a "
            "patch in the report and is never applied, so no write exists to be "
            "repeated. If it ever gains an apply path this claim becomes OWED."),
        disjoint=Claim(NOT_APPLICABLE, "writes nothing."),
        directional=Claim(
            OWED,
            "its `supersede-leaf` proposals carry a SUPERSEDES: field and so do "
            "have a direction -- the same direction stage 5d got backwards. "
            "Unchecked because asserting it needs a model reply; the parser "
            "`_parse` is the checkable half and is covered by "
            "tests/test_model_replies.py."),
    ),
    "associate": Declaration(
        stage="associate", shape=CTX_WRITE,
        idempotent=Claim(HELD),
        disjoint=Claim(
            NOT_APPLICABLE,
            "closes `related:` back-links, a SYMMETRIC relation, and emits no "
            "error-level finding against a file it writes."),
        directional=Claim(
            NOT_APPLICABLE,
            "`related:` is symmetric: there is no wrong end to write to, which "
            "is precisely what made stage 5d's asymmetric relation the one that "
            "could be inverted."),
    ),
    "downscale": Declaration(
        stage="downscale", shape=PROPOSAL_ONLY,
        idempotent=Claim(
            NOT_APPLICABLE,
            "proposal-only, ALWAYS (run.py's stage table says so): a demotion "
            "is scoring-derived and a wrong number would churn frontmatter "
            "unattended. Nothing is written."),
        disjoint=Claim(NOT_APPLICABLE, "writes nothing."),
        directional=Claim(NOT_APPLICABLE, "no relation between documents."),
    ),
}


# ── findings ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Finding:
    stage: str
    invariant: str
    detail: str
    level: str = "error"      # error | warn


# ── the fixture ──────────────────────────────────────────────────────────────
#
# A small agents tree that gives every checked stage REAL pending work. A gate
# that runs against a tree with nothing to do passes vacuously, which is the
# failure mode tests/test_dry_run_invariant.py names explicitly and guards with
# its own second test. Kept in step with that fixture on purpose: the two gates
# check different properties of the same shape of tree.

_LEAF = """---
title: {name}
authority: agent
trust: trusted
last_verified: 2026-09-01
use_count: 0
last_used: 2026-09-01
stability: evolving
related: {related}
{extra}
---

# {name}

body of {name}, long enough to have some words in it
"""

_SKILL = """---
name: doer
description: does things
invocation: model
trust: trusted
origin: authored
triggers: []
antitriggers: []
related: []
use_count: 0
---

body
"""

_SUBJECT = """---
name: practice
blurb: how we work
always_on: []
---
"""

_KNOWLEDGE_ROUTER = """<!-- LAYER 2 · what this system has written down -->

# knowledge

<!-- BEGIN:BRANCHES -->
<!-- END:BRANCHES -->
"""


def build_fixture(root: pathlib.Path) -> pathlib.Path:
    """Write a minimal `memory/` tree under `root` and return it.

    Deliberately contains a DECLARED SUPERSESSION (`c` replaced by `d`), which
    is the one relation stage 5d acts on. Without it the idempotence check on
    the conflict stage would be vacuous -- it would be proving that a stage with
    nothing to do does nothing twice.
    """
    agents = root / roots.MEMORY_REL
    kdir = agents / "knowledge"
    (kdir / "meta").mkdir(parents=True)
    (agents / "skills" / "system" / "practice" / "doer").mkdir(parents=True)

    (kdir / "CONTEXT.md").write_text(_KNOWLEDGE_ROUTER)
    (kdir / "meta" / "CONTEXT.md").write_text(
        "<!-- LAYER 2 · maintaining the tree itself -->\n\n# meta\n")
    for name, related, extra in (("a", '["b"]', ""),
                                 ("b", "[]", ""),
                                 ("c", "[]", "superseded_by: d"),
                                 ("d", "[]", "supersedes: c")):
        (kdir / "meta" / f"{name}.md").write_text(
            _LEAF.format(name=name, related=related, extra=extra))

    (agents / "skills" / "system" / "practice" / "_subject.md").write_text(_SUBJECT)
    (agents / "skills" / "system" / "practice" / "doer" / "SKILL.md").write_text(_SKILL)
    return agents


def _git_repo(root: pathlib.Path) -> None:
    """`ranking.load` resolves `created` from git history, so the fixture must be a
    real repository or every document reads as having no history."""
    ident = ["-c", "user.email=selftest@example.invalid", "-c", "user.name=Selftest"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), *ident, "add", "-A"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), *ident, "commit", "-q", "-m", "fixture",
                    "--date=2026-09-01T00:00:00"], check=True, capture_output=True)


# ── normalising the three plan shapes ────────────────────────────────────────
#
# The three plan/apply stages agree on the WORDS `writes` and `problems` and
# disagree on what they hold: conflict's `writes` is a list of Finding with
# `.rel` and `.updates`, the two generators' is a list of `(path, content)`.
# One adapter each, here, rather than a base class imposed on three modules
# that have no other reason to share one -- and named so the next stage's author
# sees exactly what a new entry must supply.

def _conflict_targets(plan):
    pending = set(plan.pending())
    errors = {f.rel for f in plan.problems if f.level == "error"}
    return pending, errors


def _render_targets(plan):
    """`knowledge-index` and `reindex`: pending == the files whose bytes differ.

    `writes` on these two lists every file the plan CONSIDERED, changed or not,
    so using it directly would report a stage as non-idempotent for rendering
    the same bytes twice. `drift` is the pending set.
    """
    root = plan.root
    def rel(p):
        try:
            return pathlib.Path(p).relative_to(root).as_posix()
        except ValueError:
            return str(p)
    pending = {rel(p) for p in plan.drift}
    errors = {rel(p.path) for p in plan.problems
              if p.level == "error" and p.path is not None}
    return pending, errors


def _plan_stages():
    """`{label: (plan_callable, adapter)}`. Imported lazily so this module can
    be read (and its declarations audited) without pulling in the pass."""
    from consolidation.stages import conflict, reindex
    from knowledge import knowledge_index
    return {
        "conflicts": (conflict.plan, _conflict_targets),
        "knowledge-index": (knowledge_index.plan, _render_targets),
        "reindex": (reindex.plan, _render_targets),
    }


def _ctx_stages():
    """Stage callables whose idempotence is claimed HELD but which write through
    `ctx` rather than a plan. Checked by running them twice and counting."""
    from consolidation.stages import aggregate, associate
    return {"aggregate": aggregate.run, "associate": associate.run}


# ── the checks ───────────────────────────────────────────────────────────────

def check_declarations(stage_labels) -> list[Finding]:
    """Every stage in `run.STAGES` is declared, and nothing else is.

    This is the check the three bugs needed and did not have. The others below
    can only test a stage somebody thought about; this one fails when nobody
    did.
    """
    out: list[Finding] = []
    declared = set(DECLARED)
    actual = set(stage_labels)
    for label in sorted(actual - declared):
        out.append(Finding(
            label, "declaration",
            f"stage `{label}` is wired into run.STAGES and declares no "
            f"invariants. Add an entry to invariants.DECLARED saying what it "
            f"guarantees -- or why each invariant does not apply. Silence here "
            f"is how stage 5d shipped three defects."))
    for label in sorted(declared - actual):
        out.append(Finding(
            label, "declaration",
            f"`{label}` is declared here but is not in run.STAGES. Either the "
            f"stage was removed and this entry is stale, or it was renamed and "
            f"the gate is now checking nothing.", "warn"))
    return out


def check_idempotence_plan(label, plan_fn, adapter, root) -> list[Finding]:
    """plan(); apply(); plan() -- the second plan must have nothing pending."""
    first = plan_fn(root)
    pending_before, _ = adapter(first)
    first.apply()
    second = plan_fn(root)
    pending_after, _ = adapter(second)
    if not pending_after:
        return []
    return [Finding(
        label, "idempotence",
        f"after applying its own plan, {label} still wants to write "
        f"{len(pending_after)} file(s): {', '.join(sorted(pending_after))}. "
        f"A stage that cannot see its own work is done re-applies it every "
        f"night forever -- this is defect 2 of 2026-09-11 exactly. "
        f"(first plan had {len(pending_before)} pending)")]


def check_disjointness(label, plan_fn, adapter, root) -> list[Finding]:
    """No file is both an error-level finding and a pending write."""
    pending, errors = adapter(plan_fn(root))
    both = pending & errors
    if not both:
        return []
    return [Finding(
        label, "disjointness",
        f"{label} reports {', '.join(sorted(both))} as an ERROR and also plans "
        f"to write to it. A stage that cannot parse a file's claims must not "
        f"act on them -- this is defect 3 of 2026-09-11, where a supersession "
        f"CYCLE was reported and marked in the same plan.")]


def check_idempotence_ctx(label, stage_fn, agents, base, today) -> list[Finding]:
    """Run a ctx-shaped stage twice; the second run must record no action.

    Needs two fresh `Pass` objects rather than one reused: `ctx.actions` is
    cumulative and `ctx.tree()` memoises the tree as it was BEFORE the first
    run's writes, so a single ctx would score the second run against a stale
    tree and report idempotence it has not got.
    """
    from consolidation import pass_ctx
    first = pass_ctx.Pass(agents, base, False, today, flags=frozenset())
    stage_fn(first)
    second = pass_ctx.Pass(agents, base, False, today, flags=frozenset())
    stage_fn(second)
    if not second.actions:
        return []
    what = "; ".join(f"{a.target}: {a.what}" for a in second.actions[:4])
    return [Finding(
        label, "idempotence",
        f"{label} recorded {len(second.actions)} action(s) on a second run over "
        f"a tree it had just finished with: {what}. Either it cannot see its "
        f"own writes, or it is oscillating between two states.")]


def run_all(root: pathlib.Path = None, today=None) -> list[Finding]:
    """Every declared invariant this module can check, against a fresh fixture.

    `root` is for a caller that wants to point the gate at a real tree; the
    default builds a throw-away one, because a gate that can only run against
    the live repository cannot be run before the change that would break it.
    """
    import datetime as dt

    from consolidation import run as _run

    # `preflight` is stage 0 and deliberately NOT in run.STAGES -- the pass
    # cannot proceed without it, so run.main calls it directly rather than in
    # the loop (see run.py). It is a stage and owes a declaration all the same,
    # so it is named here. Anything else added outside the loop must be named
    # here too, or the audit will call its declaration stale.
    out = check_declarations([label for _, label, _ in _run.STAGES]
                             + ["preflight"])

    with tempfile.TemporaryDirectory() as tmp:
        if root is None:
            repo = pathlib.Path(tmp) / "repo"
            agents = build_fixture(repo)
            _git_repo(repo)
        else:
            agents = pathlib.Path(root)
        base = pathlib.Path(tmp) / "data"
        (base / "transcripts").mkdir(parents=True)
        (base / "skill-usage.jsonl").write_text(
            '{"ts":"2026-09-04T10:00:00Z","harness":"claude","skill":"doer",'
            '"session":"sess-1","cwd":"/tmp","signal":"model"}\n')

        for label, (plan_fn, adapter) in _plan_stages().items():
            decl = DECLARED[label]
            # Disjointness first: it reads a plan without applying it, so its
            # verdict is about the tree as the pass found it. Idempotence
            # applies, and would otherwise decide what disjointness sees.
            if decl.disjoint.status == HELD:
                out += check_disjointness(label, plan_fn, adapter, agents)
            if decl.idempotent.status == HELD:
                out += check_idempotence_plan(label, plan_fn, adapter, agents)

        today = today or dt.date(2026, 9, 5)
        for label, stage_fn in _ctx_stages().items():
            if DECLARED[label].idempotent.status == HELD:
                out += check_idempotence_ctx(label, stage_fn, agents, base, today)

    for label, decl in sorted(DECLARED.items()):
        for name in ("idempotent", "disjoint", "directional"):
            claim = getattr(decl, name)
            if claim.status == OWED:
                out.append(Finding(label, name,
                                   f"declared OWED: {claim.reason}", "warn"))
    return out
