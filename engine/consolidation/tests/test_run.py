"""The pass's own bookkeeping: who is allowed to name a stage.

A stage used to append its own `"N label"` to `ctx.stages_run` at each of its
exit paths -- 19 call sites across 9 modules, spelling a label `STAGES` already
carried. Editing one and not the other silently desynced the report from the
stage that produced it. `run.main` now records the label once, from `STAGES`,
and only for a stage that returned.
"""
import datetime as dt
import pathlib

import pytest

from lib import invocation
from consolidation import run
from consolidation.stages import preflight


@pytest.fixture
def inv(tmp_path):
    return invocation.parse([], run.SPEC, base=tmp_path, agents=tmp_path / "agents")


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """`main` without the git tree: preflight succeeds, nothing is committed.

    Only the surfaces `main` touches outside the stage loop are stubbed, so the
    loop under test is the real one.
    """
    monkeypatch.setattr(preflight, "run", lambda ctx: True)
    monkeypatch.setattr(preflight, "release", lambda: None)
    monkeypatch.setattr(preflight, "record_run", lambda ctx: None)
    monkeypatch.setattr(run.report, "write", lambda ctx: tmp_path / "report.md")
    monkeypatch.setattr(run.git, "status_lines", lambda repo: [])


def test_every_stage_is_named_once_from_the_stages_table(inv, isolated,
                                                         monkeypatch):
    seen = []
    monkeypatch.setattr(run, "STAGES", [("1", "alpha", lambda ctx: seen.append(1)),
                                        ("2", "beta",  lambda ctx: seen.append(2))])
    ctx = _run(inv, monkeypatch)
    assert seen == [1, 2]
    assert ctx.stages_run == ["0 preflight", "1 alpha", "2 beta", "8 report"]


def test_a_stage_that_raises_is_not_recorded_as_having_run(inv, isolated,
                                                           monkeypatch):
    """The old placement gave this for free -- the append sat after the body,
    so an exception skipped it. Recording centrally must not start crediting a
    stage that blew up, or the report and last-run.json would claim work that
    never happened."""
    def boom(ctx):
        raise RuntimeError("stage exploded")

    monkeypatch.setattr(run, "STAGES", [("1", "alpha", boom),
                                        ("2", "beta",  lambda ctx: None)])
    ctx = _run(inv, monkeypatch)
    assert "1 alpha" not in ctx.stages_run, "a stage that raised did not run"
    assert "2 beta" in ctx.stages_run, "one broken stage must not lose the rest"
    assert [n for n in ctx.notes if n.level == "error" and "RuntimeError" in n.text]


def test_a_stage_the_user_deselected_is_not_recorded(inv, isolated, monkeypatch,
                                                     tmp_path):
    monkeypatch.setattr(run, "STAGES", [("1", "alpha", lambda ctx: None),
                                        ("2", "beta",  lambda ctx: None)])
    only = invocation.parse(["--stages=2"], run.SPEC, base=tmp_path,
                            agents=tmp_path / "agents")
    ctx = _run(only, monkeypatch)
    assert "1 alpha" not in ctx.stages_run and "2 beta" in ctx.stages_run


def test_no_stage_module_spells_its_own_name():
    """The duplication itself, asserted structurally: `STAGES` is the only
    place a stage's label is written."""
    stages = pathlib.Path(run.__file__).parent / "stages"
    offenders = [p.name for p in stages.glob("*.py")
                 if "stages_run.append" in p.read_text()]
    assert offenders == []


def test_branch_and_head_are_declared_fields_not_late_attributes():
    """`report.render` read `getattr(ctx, "branch", "?")` because preflight set
    an attribute `Pass` never declared. A fresh Pass must already have both."""
    from consolidation import pass_ctx
    ctx = pass_ctx.Pass(pathlib.Path("/a/agents"), pathlib.Path("/b"), True,
                        dt.date(2026, 9, 5))
    assert ctx.branch == "" and ctx.head == ""


def _run(inv, monkeypatch):
    """Call `main`, returning the Pass it built."""
    made = []
    real = run.pass_ctx.Pass

    def capture(*a, **kw):
        ctx = real(*a, **kw)
        made.append(ctx)
        return ctx

    monkeypatch.setattr(run.pass_ctx, "Pass", capture)
    assert run.main(inv) == 0
    return made[0]
