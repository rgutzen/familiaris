"""A gate does not inherit the hook's git environment.

Regression for 2026-09-29. `checks.py --run pre-commit` from a linked worktree
set `core.bare = true` in the *main* repository's config, after which every git
command in `~/06_SYSTEM` failed with "this operation must be run in a work
tree". The chain: a linked worktree's pre-commit hook exports `GIT_DIR`, the
registry passed its own environment straight to each check, and the memory
selftest's fixture runs `git init` -- which, with `GIT_DIR` pointing at a real
repository whose git dir has no `core.worktree`, re-initialises it as bare. The
same inheritance staged the fixture's files into the real index.

Proved by aiming the registry at a stand-in check rather than by reproducing the
damage: the failure is an environment leak, so it is visible in what the child
process sees.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import checks  # noqa: E402


def _gate_that_reports(monkeypatch, predicate: str) -> None:
    """Point the `pre-commit` gate at one fake check whose exit code is 1 when
    `predicate` holds in its own environment."""
    script = f"import os, sys; sys.exit(1 if {predicate} else 0)"
    fake = checks.Check(
        id="env-probe",
        description="reports one environment fact about itself",
        command=(sys.executable, "-c", script),
        gates=frozenset({checks.GATE_PRE_COMMIT}),
    )
    monkeypatch.setattr(checks, "CHECKS", (fake,))


@pytest.mark.parametrize("var", checks.GIT_ENV_VARS)
def test_gates_do_not_inherit_git_variables(monkeypatch, var):
    monkeypatch.setenv(var, "/tmp/pretend-worktree-git-dir")
    _gate_that_reports(monkeypatch, f"os.environ.get({var!r})")
    assert checks.run_gate(checks.GATE_PRE_COMMIT) == 0, (
        f"{var} reached a gate: a check may not run inside the hook's git "
        f"environment")


def test_the_rest_of_the_environment_survives(monkeypatch):
    """The scrub is a deny-list of git's own variables, not a clean slate: PATH,
    HOME and the rest are what make a check runnable at all."""
    monkeypatch.setenv("PAZRAS_TEST_MARKER", "kept")
    _gate_that_reports(monkeypatch, "not os.environ.get('PAZRAS_TEST_MARKER')")
    assert checks.run_gate(checks.GATE_PRE_COMMIT) == 0
