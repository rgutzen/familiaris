"""The one command-line parser, and the declarations it is checked against.

The incident this module exists to prevent: on 2026-09-03
`familiar consolidation run --dry-dun --stages=3` silently dropped the unknown flag, ran
a REAL pass, and committed a partial report over the night's (reverted in
057d04b). Every "refused" test below is that failure mode.
"""
import pathlib
import re

import pytest

from cli import cli, selftest
from lib import invocation
from knowledge import journal_index
from consolidation import posture, run

SPEC = invocation.Spec(
    name="demo", usage="demo [--dry-run] [--stages=LIST]",
    flags=("--dry-run",), options=("--stages",), aliases={"-n": "--dry-run"})


def _parse(argv, spec=SPEC):
    return invocation.parse(argv, spec, "/tmp/base", "/tmp/agents")


# ── parsing ──────────────────────────────────────────────────────────────────

def test_a_flag_is_present_or_it_is_not():
    assert _parse(["--dry-run"]).has("--dry-run")
    assert not _parse([]).has("--dry-run")


def test_an_alias_resolves_to_the_long_name():
    assert _parse(["-n"]).has("--dry-run")


def test_an_option_carries_its_value():
    assert _parse(["--stages=1,2,3"]).get("--stages") == "1,2,3"


def test_a_value_may_contain_an_equals_sign():
    assert _parse(["--stages=a=b"]).get("--stages") == "a=b"


def test_a_repeated_option_takes_the_last_value():
    assert _parse(["--stages=1", "--stages=2"]).get("--stages") == "2"


def test_paths_come_from_the_environment_not_the_command_line():
    inv = _parse([])
    assert inv.base == pathlib.Path("/tmp/base") and inv.agents == pathlib.Path("/tmp/agents")


def test_help_is_always_accepted():
    assert _parse(["-h"]).help and _parse(["--help"]).help


# ── refusals ─────────────────────────────────────────────────────────────────

def test_an_unknown_flag_is_refused_and_names_what_is_accepted():
    with pytest.raises(invocation.UsageError) as exc:
        _parse(["--dry-dun"])
    assert "--dry-dun" in str(exc.value) and "--dry-run" in str(exc.value)


def test_an_option_without_a_value_is_refused():
    with pytest.raises(invocation.UsageError):
        _parse(["--stages"])


def test_a_flag_given_a_value_is_refused():
    with pytest.raises(invocation.UsageError):
        _parse(["--dry-run=yes"])


def test_a_stray_argument_is_refused_when_none_is_expected():
    with pytest.raises(invocation.UsageError):
        _parse(["stage3"])


def test_a_positional_is_kept_when_the_spec_takes_one():
    spec = invocation.Spec(name="search", options=("--top",), positional="query")
    inv = _parse(["what happened", "--top=3"], spec)
    assert inv.rest == ("what happened",) and inv.integer("--top", 8) == 3


def test_a_non_numeric_count_is_a_usage_error_not_a_traceback():
    spec = invocation.Spec(name="search", options=("--top",), positional="query")
    with pytest.raises(invocation.UsageError):
        _parse(["q", "--top=many"], spec).integer("--top", 8)


# ── the declarations ─────────────────────────────────────────────────────────

SPECS = [run.SPEC, cli.STATUS, cli.REPORT, cli.BRIEF, cli.DECISION, cli.DISMISS,
         cli.QUEUE, cli.DECIDE, cli.JEV, cli.ONTOLOGY,
         cli.OPENCODE_SESSION, cli.HERMES_SESSION, cli.HERMES_SESSION_WORKER,
         selftest.SPEC, journal_index.SPEC_INDEX, journal_index.SPEC_SEARCH,
         posture.SPEC, posture.VAULT_SPEC]


def _advertised(usage: str) -> set:
    return set(re.findall(r"--[a-z-]+", usage))


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_a_spec_accepts_exactly_what_its_usage_advertises(spec):
    """`report --last` sat in the usage text for a month with nothing behind
    it. A flag is either declared and documented, or it does not exist."""
    assert _advertised(spec.usage) == set(spec.flags) | set(spec.options)


def test_the_dispatcher_advertises_no_flag_that_no_spec_implements():
    """The top-level usage is what a human reads first; `--last` lived there."""
    doc = (pathlib.Path(__file__).resolve().parents[2] / "cli" / "familiar-memory.py").read_text()
    doc = doc[doc.index('"""'):doc.index("GOVERNING RULES")]
    declared = {f for s in SPECS for f in set(s.flags) | set(s.options)}
    declared |= {"--check", "--harness", "--event", "--all",
                 "--apply"}   # reindex, capture, conflict
    assert _advertised(doc) <= declared


# ── jev check (step 2b) ──────────────────────────────────────────────────────

@pytest.mark.parametrize("payload,expected", [
    ({"data": [{"id": "jev-1.13.0"}]}, ["jev-1.13.0"]),
    ({"models": ["jev-1.13.0"]}, ["jev-1.13.0"]),
    (["jev-1.13.0"], ["jev-1.13.0"]),
    ({"data": [{"name": "jev-1.13.0"}]}, ["jev-1.13.0"]),
    ({}, []),
    ("nonsense", []),
])
def test_model_ids_reads_the_shapes_a_models_endpoint_might_return(payload, expected):
    """The field names come from mirrors, so this reads the common shapes and
    reports nothing rather than raising on an unexpected one."""
    assert cli._model_ids(payload) == expected


def test_jev_check_needs_the_subcommand():
    inv = invocation.parse([], cli.JEV, "/tmp", "/tmp")
    assert cli.jev_cli(inv) == 1


# ── ontology (O1a/O1j/O1l) ───────────────────────────────────────────────────

def test_ontology_needs_a_declared_subcommand():
    """Same rule as an undeclared flag: a surface that guesses at what it was
    asked answers the wrong question quietly."""
    inv = invocation.parse([], cli.ONTOLOGY, "/tmp", "/tmp")
    assert cli.ontology_cmd(inv) == 1
    try:
        invocation.parse(["everything"], cli.ONTOLOGY, "/tmp", "/tmp")
    except invocation.UsageError:
        pass
    else:                      # a positional is taken, so it must be checked
        assert cli.ontology_cmd(invocation.parse(["everything"], cli.ONTOLOGY,
                                                 "/tmp", "/tmp")) == 1
