"""The stage-invariant gate, proved by breaking it.

A gate that has only ever been seen to pass is not evidence of anything: it is
indistinguishable from a gate that returns "ok" unconditionally, which is what
the 333 green tests of 2026-09-11 effectively were for the three defects in
stage 5d. So every check in `stages/invariants.py` is exercised here twice --
once against the real pass (it must be silent) and once against a stage
deliberately broken in the shape of the bug the check exists for (it must
speak, and name the stage).

The three injections reproduce the three defects:

  test_idempotence_*   defect 2 -- a stage that cannot recognise its own
                       completed work, so it re-applies it every night.
  test_disjointness_*  defect 3 -- a file reported as an ERROR and written to
                       in the same plan.
  test_direction_*     defect 1 -- the marking applied to the wrong end of an
                       asymmetric relation, in output that reads correctly.

The direction check is a PROPERTY over generated graphs rather than a fixture
pair, because the hand-written test that would have caught defect 1 is the one
nobody thought to write. A property holds over a family; a fixture holds over
one instance, and the instance an author picks is by construction the one they
already had in mind.
"""
import dataclasses
import itertools
import pathlib
import random
import subprocess

import pytest

from consolidation.stages import conflict, invariants

IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]


@pytest.fixture
def agents(tmp_path):
    """The gate's own fixture, built the way the gate builds it."""
    repo = tmp_path / "repo"
    root = invariants.build_fixture(repo)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *IDENT, "add", "-A"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *IDENT, "commit", "-q", "-m", "f",
                    "--date=2026-09-01T00:00:00"], check=True, capture_output=True)
    return root


# ── the gate is silent on the real pass ──────────────────────────────────────

def test_the_live_pass_holds_every_invariant_it_claims():
    """The gate, run as `familiar checks selftest --invariants` runs it."""
    findings = invariants.run_all()
    errors = [f for f in findings if f.level == "error"]
    assert not errors, "\n".join(f"{f.stage}/{f.invariant}: {f.detail}"
                                 for f in errors)


def test_every_stage_in_the_pass_declares_its_invariants():
    """The check the three defects actually needed: not "is this stage correct"
    but "did anyone ever say what this stage guarantees"."""
    from consolidation import run
    labels = {label for _, label, _ in run.STAGES} | {"preflight"}
    assert labels == set(invariants.DECLARED), (
        f"undeclared: {sorted(labels - set(invariants.DECLARED))}; "
        f"stale: {sorted(set(invariants.DECLARED) - labels)}")


def test_the_fixture_gives_the_checked_stages_real_work(agents):
    """Without this the whole module passes vacuously -- the same guard
    test_dry_run_invariant.py carries, for the same reason."""
    assert conflict.plan(agents).writes, (
        "fixture declares no supersession; the conflict checks prove nothing")


def test_a_claim_that_is_not_held_must_carry_a_reason():
    """The `ranking.unvalidated()` rule, one field over: an exemption nothing
    can falsify needs a person's sentence on the record."""
    with pytest.raises(ValueError, match="requires a reason"):
        invariants.Claim(invariants.NOT_APPLICABLE)
    with pytest.raises(ValueError, match="status must be one of"):
        invariants.Claim("probably fine")
    invariants.Claim(invariants.HELD)          # held needs none: the gate is it


def test_selftest_exits_nonzero_when_a_stage_declares_nothing(monkeypatch,
                                                              capsys):
    """End to end, through the command the gate is actually run as.

    The checks above prove each rule catches its bug; this proves the rule is
    WIRED -- that `familiar checks selftest --invariants` reports a failure rather
    than printing findings and returning 0, which is the shape of every gate
    that ran and could not fail.
    """
    from consolidation import run
    from cli import selftest

    assert selftest.invariants() == 0, "the real pass must pass"

    monkeypatch.setattr(run, "STAGES", list(run.STAGES) + [("9", "undeclared",
                                                            lambda ctx: True)])
    assert selftest.invariants() == 1
    assert "declares no invariants" in capsys.readouterr().out


def test_selftest_exits_nonzero_on_a_real_stage_that_breaks_idempotence(
        monkeypatch, capsys):
    """Exit criterion 1, in its strongest form: not "the check catches it" but
    "the command the gate runs exits non-zero on a REAL stage".

    The violation is injected into `conflict.plan` -- the live module, not a
    synthetic stub -- in the shape of defect 2: a marking whose value can never
    equal what `apply` writes, so it is pending forever.
    """
    from cli import selftest
    from consolidation.stages import conflict

    assert selftest.invariants() == 0, "the real pass must pass first"

    real = conflict.plan

    def not_idempotent(root=None):
        p = real(root)
        p.findings.append(conflict.Finding(
            "knowledge/meta/c.md", "injected", "pending forever", "injected",
            updates={"superseded_by": ["never-matches-what-is-written"]}))
        return p

    monkeypatch.setattr(conflict, "plan", not_idempotent)
    assert selftest.invariants() == 1
    out = capsys.readouterr().out
    assert "idempotence" in out and "INVARIANTS FAILED" in out


def test_selftest_exits_nonzero_on_a_real_stage_that_marks_an_error(
        monkeypatch, capsys):
    """The same for defect 3: a file reported as an ERROR and written to in one
    plan -- a supersession cycle that is nonetheless marked."""
    from cli import selftest
    from consolidation.stages import conflict

    assert selftest.invariants() == 0
    real = conflict.plan

    def marks_an_error(root=None):
        p = real(root)
        p.findings.append(conflict.Finding(
            "knowledge/meta/c.md", "injected-cycle",
            "c supersedes d supersedes c", "no leaf in a cycle is current",
            level="error"))
        return p

    monkeypatch.setattr(conflict, "plan", marks_an_error)
    assert selftest.invariants() == 1
    out = capsys.readouterr().out
    assert "disjointness" in out and "INVARIANTS FAILED" in out


# ── defect 2: idempotence ────────────────────────────────────────────────────

def test_idempotence_gate_is_silent_on_the_real_conflict_stage(agents):
    assert not invariants.check_idempotence_plan(
        "conflicts", conflict.plan, invariants._conflict_targets, agents)


def test_idempotence_gate_catches_a_stage_that_cannot_see_its_own_work(agents):
    """Defect 2 reproduced: the back-pointer check compares against something
    the writer never produces, so the write stays pending forever."""
    def blind_plan(root):
        p = conflict.plan(root)
        # The bug, in one line: re-assert a marking whose value can never equal
        # what `apply` writes, so the next plan sees it as still missing.
        p.findings.append(conflict.Finding(
            "knowledge/meta/c.md", "injected", "always pending", "injected",
            updates={"superseded_by": ["never-matches-what-is-written"]}))
        return p

    out = invariants.check_idempotence_plan(
        "injected", blind_plan, invariants._conflict_targets, agents)
    assert len(out) == 1
    assert out[0].invariant == "idempotence"
    assert "knowledge/meta/c.md" in out[0].detail


def test_idempotence_gate_catches_a_ctx_stage_that_rewrites_every_run(agents,
                                                                     tmp_path):
    """The ctx-shaped half of the same check: a stage whose second run over a
    tree it just finished with still records actions."""
    import datetime as dt

    base = tmp_path / "data"
    (base / "transcripts").mkdir(parents=True)

    def churn(ctx):
        leaf = ctx.agents / "knowledge/meta/a.md"
        leaf.write_text(leaf.read_text() + "one more line\n")
        ctx.act("x", "knowledge/meta/a.md", "appended, again")
        return True

    out = invariants.check_idempotence_ctx("churn", churn, agents, base,
                                           dt.date(2026, 9, 5))
    assert len(out) == 1
    assert "second run" in out[0].detail


# ── defect 3: error/act disjointness ─────────────────────────────────────────

def test_disjointness_gate_is_silent_on_the_real_conflict_stage(agents):
    assert not invariants.check_disjointness(
        "conflicts", conflict.plan, invariants._conflict_targets, agents)


def test_disjointness_gate_catches_an_error_and_a_write_on_one_file(agents):
    """Defect 3 reproduced: a supersession CYCLE is an error -- no leaf in a
    loop can be the current one -- and the same plan marked a leaf in it."""
    def cyclic_plan(root):
        p = conflict.plan(root)
        p.findings.append(conflict.Finding(
            "knowledge/meta/c.md", "supersession-cycle",
            "c supersedes d supersedes c", "no leaf in a cycle is current",
            level="error"))
        return p

    out = invariants.check_disjointness(
        "injected", cyclic_plan, invariants._conflict_targets, agents)
    assert len(out) == 1
    assert out[0].invariant == "disjointness"
    assert "knowledge/meta/c.md" in out[0].detail


def test_a_real_cycle_in_the_tree_is_reported_and_not_marked(agents):
    """The live stage, on the live rule -- not an injection. `c` and `d` already
    supersede each other in the fixture's second half; assert the module itself
    keeps the two sets apart rather than trusting the injected proof above."""
    (agents / "knowledge/meta/c.md").write_text(
        (agents / "knowledge/meta/c.md").read_text()
        .replace("superseded_by: d", "supersedes: d\nsuperseded_by: d"))
    p = conflict.plan(agents)
    errors = {f.rel for f in p.problems if f.level == "error"}
    assert errors, "a mutual supersession must be an error"
    assert not (errors & set(p.pending())), (
        f"marked a leaf it also reported as an error: {errors & set(p.pending())}")


# ── defect 1: direction, as a property over generated graphs ─────────────────

def _write_graph(root, edges, names):
    """A knowledge tree whose only content is a supersession graph.

    `supersedes:` is written on the SUPERSEDER, which is the direction the
    frontmatter key means and the direction the module got backwards.
    """
    kdir = root / "knowledge" / "meta"
    kdir.mkdir(parents=True, exist_ok=True)
    (root / "knowledge" / "CONTEXT.md").write_text(
        "<!-- LAYER 2 · knowledge -->\n\n# knowledge\n")
    (kdir / "CONTEXT.md").write_text("<!-- LAYER 2 · meta -->\n\n# meta\n")
    for n in names:
        sup = sorted(b for a, b in edges if a == n)
        extra = f"supersedes: [{', '.join(sup)}]" if sup else ""
        (kdir / f"{n}.md").write_text(
            invariants._LEAF.format(name=n, related="[]", extra=extra))


@pytest.mark.parametrize("seed", range(12))
def test_only_the_superseded_end_is_ever_marked(tmp_path, seed):
    """THE PROPERTY: for every edge `a supersedes b`, the marking lands on `b`.

    Generated rather than hand-picked. Defect 1 inverted the argument pair, and
    every finding it produced still read correctly in prose -- so the only thing
    that distinguishes correct from inverted is WHICH FILE CHANGED, asserted
    over enough graphs that a symmetric fixture cannot hide the difference.

    Acyclic by construction: `a_i` may only supersede `a_j` with j > i. A cycle
    is a different property (the test above), and mixing them would let this
    test pass because the module refused to act at all.
    """
    rng = random.Random(seed)
    names = [f"n{i}" for i in range(rng.randint(2, 6))]
    edges = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]
             if rng.random() < 0.45]
    if not edges:
        pytest.skip("empty graph for this seed; the property is vacuous")

    root = tmp_path / "agents"
    _write_graph(root, edges, names)

    superseded = {b for _, b in edges}
    superseders_only = {a for a, _ in edges} - superseded

    pending = set(conflict.plan(root).pending())
    touched = {pathlib.PurePosixPath(r).stem for r in pending}

    assert touched <= superseded, (
        f"marked a leaf that nothing supersedes: {sorted(touched - superseded)} "
        f"— edges {edges}. This is defect 1: the relation was written to the "
        f"wrong end.")
    assert not (touched & superseders_only), (
        f"marked a pure superseder: {sorted(touched & superseders_only)}")
    assert touched == superseded, (
        f"left a superseded leaf unmarked: {sorted(superseded - touched)}")


@pytest.mark.parametrize("seed", range(8))
def test_marking_the_wrong_end_is_visible_to_the_property(tmp_path, seed):
    """The property is falsifiable: invert the direction and it must fail.

    Without this, `test_only_the_superseded_end_is_ever_marked` could be passing
    because the generator never produces a graph where the two ends differ.
    """
    rng = random.Random(100 + seed)
    names = [f"n{i}" for i in range(3)]
    edges = [(names[0], names[1]), (names[1], names[2])]
    root = tmp_path / "agents"
    _write_graph(root, edges, names)

    real = conflict._supersession_findings

    def inverted(old, new, by_rel, by_name):
        return real(new, old, by_rel, by_name)      # defect 1, exactly

    conflict._supersession_findings = inverted
    try:
        touched = {pathlib.PurePosixPath(r).stem
                   for r in conflict.plan(root).pending()}
    finally:
        conflict._supersession_findings = real

    superseded = {b for _, b in edges}
    assert touched != superseded, (
        "inverting the direction changed nothing the property can see — the "
        "property is not testing direction at all")
