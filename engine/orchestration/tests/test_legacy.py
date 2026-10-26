"""The eight pre-contract `dev/*/SPECS.md` named under `legacy:` in specs.yaml are
this mechanism's test corpus (item 3g of dev/orchestration/SPECS.md). The real
files are the fixtures: when one is edited or backfilled, its test here fails
until the expected values are updated. Each file pins what the gate, `--check`,
`dispatch <file>` and `waves.build` actually do with it.

No test reaches Jev: `jev.ask` is replaced by a function that fails the test."""
import pathlib

import pytest

from lib import roots
from orchestration import dispatch, specs, waves

pytestmark = pytest.mark.skipif(
    not roots.instance_here(),
    reason="the corpus is this instance's pre-contract `dev/*/SPECS.md`, which the "
           "classification omits with `dev/`")

DEV = roots.REPO / "dev"
NO_ID = ("no item id; the head must open `**<id> · <title>**`, "
         "e.g. **2a · the contract**")
PRE = "pre-contract"


def noid(line):
    return f"line {line}: item line {line}: id: {NO_ID}"


def missing(line, item_id):
    """The four required fields absent from one item, in contract order."""
    return [f"line {line}: item {item_id}: {k}: missing"
            for k in ("touches", "depends", "model", "verify")]


def also(line, item_id, first):
    return f"line {line}: item {item_id}: id: also used on line {first}"


def flat(*groups):
    return [x for g in groups for x in (g if isinstance(g, list) else [g])]


def path(name):
    return DEV / name / "SPECS.md"


@pytest.fixture
def no_jev(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("dispatch reached Jev for a legacy file")
    monkeypatch.setattr(dispatch.jev, "ask", boom)


def gate_lines(capsys):
    contract = specs.load_contract()
    callable_ids, candidate_ids = dispatch.catalogue_ids()
    rc = dispatch.gate(roots.REPO, contract, callable_ids, candidate_ids)
    return rc, capsys.readouterr().out.splitlines()


def check_lines(name, capsys):
    rc = dispatch.main(["--check", str(path(name))])
    return rc, capsys.readouterr().out.splitlines()


def refused(name, capsys, no_jev, *extra):
    """`dispatch <file>` in-process; returns (rc, stdout lines, stderr)."""
    rc = dispatch.main([*extra, str(path(name))])
    cap = capsys.readouterr()
    return rc, cap.out.splitlines(), cap.err


def plan(name):
    contract = specs.load_contract()
    items = specs.parse(path(name).read_text(encoding="utf-8"), set(contract["fields"]))
    return [[it.id for it in w] for w in waves.build(items, contract["none"])]


# name -> (gate line, open items, finding lines, waves). Explicit per file.
CASES = {
    "cli": (
        "legacy: dev/cli/SPECS.md: 3 finding(s) -- pre-contract chore list; items carry no ids",
        3,
        [noid(9), noid(13), noid(17)],
        [["line 9", "line 13", "line 17"]]),
    "data": (
        "legacy: dev/data/SPECS.md: 7 finding(s) -- pre-contract chore list; items carry no ids",
        7,
        [noid(n) for n in (18, 22, 25, 27, 30, 32, 34)],
        [["line 18", "line 22", "line 25", "line 27", "line 30", "line 32", "line 34"]]),
    "hermes-guard": (
        "legacy: dev/hermes-guard/SPECS.md: 12 finding(s) -- pre-contract; ids, no fields",
        3,
        flat(missing(41, "H3"), missing(50, "H4"), missing(53, "H5")),
        [["H3", "H4", "H5"]]),
    "integrity": (
        "legacy: dev/integrity/SPECS.md: 14 finding(s) -- "
        "pre-contract; ids, no fields, three items share N3",
        3,
        flat(missing(36, "N3"),
             also(48, "N3", 36), missing(48, "N3"),
             also(55, "N3", 36), missing(55, "N3")),
        [["N3", "N3", "N3"]]),
    "jev": (
        "legacy: dev/jev/SPECS.md: 12 finding(s) -- pre-contract; ids, no fields",
        3,
        flat(missing(363, "3b"), missing(416, "3c"), missing(433, "3d")),
        [["3b", "3c", "3d"]]),
    "memory": (
        "legacy: dev/memory/SPECS.md: 18 finding(s) -- "
        "pre-contract; ids, no fields, two items share M4",
        4,
        flat(missing(67, "M2b"), missing(73, "M3"),
             also(77, "M4", 13), missing(77, "M4"),
             also(80, "M4", 13), missing(80, "M4")),
        [["M2b", "M3", "M4", "M4"]]),
}

NAMES = sorted(CASES)


def test_legacy_corpus_is_exactly_the_six_declared_files():
    declared = set(specs.load_contract()["legacy"])
    assert declared == {f"dev/{n}/SPECS.md" for n in CASES}
    assert len(CASES) == 6


def test_legacy_gate_warns_per_file_and_passes_overall(capsys):
    rc, lines = gate_lines(capsys)
    assert rc == 0
    # The file count follows the tree (a new track adds a SPECS.md); the legacy count is
    # the pinned part. Pinning the total broke on 2026-10-20 when dev/schedule/ arrived.
    total = len(list(DEV.glob("*/SPECS.md")))
    assert lines[-1] == f"dispatch --gate: {total} file(s), 0 failing, 6 legacy"
    warned = [l for l in lines if l.startswith("legacy: ")]
    assert warned == [CASES[n][0] for n in NAMES]


def _gate_line_for(name, capsys):
    return next(l for l in gate_lines(capsys)[1] if l.startswith(f"legacy: dev/{name}/SPECS.md:"))


def _check(name, capsys):
    gate_line, n_open, findings, _ = CASES[name]
    assert _gate_line_for(name, capsys) == gate_line
    rc, lines = check_lines(name, capsys)
    assert rc == 1
    assert lines[:-1] == findings
    assert lines[-1] == (f"dispatch --check: {path(name)}: {n_open} open item(s), "
                         f"{len(findings)} finding(s)")
    assert len(findings) == int(gate_line.split(": ")[2].split(" ")[0])


def _dispatch(name, capsys, no_jev):
    findings = CASES[name][2]
    for extra in ((), ("--dry-run",)):
        rc, out, err = refused(name, capsys, no_jev, *extra)
        assert rc == 1
        assert out == findings                       # the findings, and nothing after them
        assert not any("wave" in l or "probes" in l or "jev" in l for l in out)
        assert err == (f"dispatch: {path(name)} is not dispatchable "
                       f"({len(findings)} finding(s)); see `dispatch --check`\n")


def _waves(name):
    assert plan(name) == CASES[name][3]


# One test per file. Each names its file and runs the four behaviours; the
# expected values above are its own.

def test_legacy_cli(capsys, no_jev):
    _check("cli", capsys)
    _dispatch("cli", capsys, no_jev)
    _waves("cli")                  # three id-less items: stand-in ids "line N"


def test_legacy_data(capsys, no_jev):
    _check("data", capsys)
    _dispatch("data", capsys, no_jev)
    _waves("data")



def test_legacy_hermes_guard(capsys, no_jev):
    _check("hermes-guard", capsys)
    _dispatch("hermes-guard", capsys, no_jev)
    _waves("hermes-guard")


def test_legacy_integrity_shares_n3(capsys, no_jev):
    _check("integrity", capsys)
    _dispatch("integrity", capsys, no_jev)
    _waves("integrity")            # all three N3 items land in the one wave
    items = specs.parse(path("integrity").read_text(encoding="utf-8"),
                        set(specs.load_contract()["fields"]))
    assert [(i.id, i.line) for i in items if i.id == "N3"] == [("N3", 36), ("N3", 48), ("N3", 55)]


def test_legacy_jev(capsys, no_jev):
    _check("jev", capsys)
    _dispatch("jev", capsys, no_jev)
    _waves("jev")


def test_legacy_memory_shares_m4(capsys, no_jev):
    _check("memory", capsys)
    _dispatch("memory", capsys, no_jev)
    _waves("memory")
    items = specs.parse(path("memory").read_text(encoding="utf-8"),
                        set(specs.load_contract()["fields"]))
    # the first M4 (line 13) is done, so it is exempt and the other two are open
    assert [(i.id, i.line, i.done) for i in items if i.id == "M4"] == [
        ("M4", 13, True), ("M4", 77, False), ("M4", 80, False)]



@pytest.mark.parametrize("name", NAMES)
def test_legacy_no_file_has_a_cycle_to_refuse(name):
    """No legacy file declares `depends:`, so none can form a cycle or a
    backwards dependency: `waves.build` succeeds on all eight and returns one
    wave. Dispatch never gets that far (it refuses on findings first); this
    pins that the cycle refusal is unreachable for the corpus today."""
    contract = specs.load_contract()
    items = specs.parse(path(name).read_text(encoding="utf-8"), set(contract["fields"]))
    assert all("depends" not in it.fields for it in items)
    assert len(waves.build(items, contract["none"])) == 1
