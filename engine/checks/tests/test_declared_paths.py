"""The declared-path check, proved by breaking it.

The bug this guards is `memory/MEMORY.md`: deleted 2026-09-04, still read,
cap-checked and offered as a write TARGET for a week, and re-creatable by a
stage-4 proposal whose patch read `--- /dev/null`. Nothing caught it, so the
check that now does must be shown to catch it rather than merely to exist.

Each test builds a throw-away repository with its own package tree, because the
check reads source by AST rather than importing -- which means it can be aimed
at any tree, and a test does not have to mutate the real one to prove anything.
"""
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import declared_paths as dp


@pytest.fixture
def repo(tmp_path):
    """A miniature of this repository: one package, one agents tree."""
    pkg = tmp_path / "engine/consolidation"
    pkg.mkdir(parents=True)
    (tmp_path / "engine/context/").mkdir(parents=True)
    (tmp_path / "memory/knowledge").mkdir(parents=True)
    (tmp_path / "memory/knowledge/INDEX.md").write_text("# index\n")
    return tmp_path


def _module(repo, name, source):
    (repo / "engine/consolidation" / name).write_text(source)
    return f"engine/consolidation/{name}"


# ── the live repository ──────────────────────────────────────────────────────

def test_the_real_repository_has_no_undeclared_or_missing_path():
    assert [f for f in dp.check() if f.level == "error"] == []


def test_every_tombstone_carries_a_reason_and_is_actually_gone():
    """The three names that are declared absent are absent for a stated reason,
    and `check` proves the reasons are not stale by testing the other
    direction. Named here so the set is visible without reading the policies."""
    off = dp.POLICIES["engine/consolidation/stages/consolidate.py:OFF_LIMITS"]
    assert set(off.absent) == {"MEMORY.md", "USER.md", "knowledge/conventions/"}
    for name, reason in off.absent.items():
        assert len(reason.split()) >= 5, name
    for name in off.absent:
        assert not (dp.AGENTS / name.rstrip("/")).exists(), (
            f"{name} is declared a tombstone and exists")


# ── discovery ────────────────────────────────────────────────────────────────

def test_a_new_declared_list_with_no_policy_is_an_error(repo):
    """The `checks.py --audit` property, one level down: adding a list forces a
    decision about what its entries mean. Without this, the whole module is
    just another hand-maintained list with the same defect as its subjects."""
    _module(repo, "newstage.py", 'BRAND_NEW = ("knowledge/whatever.md",)\n')
    errors = [f for f in dp.check(repo) if f.level == "error"]
    assert any("BRAND_NEW" in f.where and "no policy" in f.detail
               for f in errors), errors


def test_a_list_of_non_paths_is_not_discovered(repo):
    """The discovery heuristic must not drag in every uppercase tuple, or the
    policy table fills with noise and stops being read."""
    _module(repo, "quiet.py", 'LEVELS = ("note", "warn", "error")\n'
                              'COUNT = 3\n')
    assert not any("quiet.py" in k for k in dp.discover(repo))


def test_a_dict_declares_its_keys_not_its_values(repo):
    """`CAPS` maps a path to a character budget; the path is the declaration."""
    _module(repo, "capped.py", 'BUDGET = {"knowledge/gone.md": 1375}\n')
    found = dp.discover(repo)
    assert found["engine/consolidation/capped.py:BUDGET"] == \
        ["knowledge/gone.md"]


# ── the MEMORY.md failure itself ─────────────────────────────────────────────

def test_a_declared_path_that_does_not_exist_is_an_error(repo, monkeypatch):
    """MEMORY.md reproduced: a list names a file, the file is gone, and before
    this check nothing said so."""
    key = _module(repo, "reader.py",
                  'SOURCES = ("MEMORY.md", "knowledge/INDEX.md")\n') + ":SOURCES"
    monkeypatch.setitem(dp.POLICIES, key, dp.Policy(dp.K_EXISTS))
    errors = [f for f in dp.check(repo) if f.level == "error"]
    assert any("MEMORY.md" in f.detail and "does not exist" in f.detail
               for f in errors), errors
    # and the file that IS there must not be reported
    assert not any("INDEX.md" in f.detail for f in errors)


def test_declaring_it_absent_with_a_reason_silences_the_error(repo, monkeypatch):
    key = _module(repo, "reader.py", 'SOURCES = ("MEMORY.md",)\n') + ":SOURCES"
    monkeypatch.setitem(dp.POLICIES, key, dp.Policy(
        dp.K_EXISTS,
        absent={"MEMORY.md": "a tombstone, deleted when L1 moved into the "
                             "compiled always-loaded set"}))
    assert not [f for f in dp.check(repo) if f.level == "error"]


def test_a_reason_that_is_not_a_reason_is_refused():
    """"n/a", "legacy", "TODO" -- the shapes an exemption takes when it is being
    got past a gate rather than explained to the next reader."""
    for placeholder in ("n/a", "legacy", "see above", "TODO fix later"):
        with pytest.raises(ValueError, match="is not a reason"):
            dp.Policy(dp.K_EXISTS, absent={"MEMORY.md": placeholder})


def test_a_resurrected_tombstone_is_an_error(repo, monkeypatch):
    """The dangerous direction. A file declared gone that comes back means
    something is reachable again that a deny-list says cannot be -- and the
    stale reason would keep the gate green."""
    key = _module(repo, "reader.py", 'SOURCES = ("MEMORY.md",)\n') + ":SOURCES"
    (repo / "memory/MEMORY.md").write_text("# it came back\n")
    monkeypatch.setitem(dp.POLICIES, key, dp.Policy(
        dp.K_EXISTS,
        absent={"MEMORY.md": "a tombstone, deleted when L1 moved into the "
                             "compiled always-loaded set"}))
    errors = [f for f in dp.check(repo) if f.level == "error"]
    assert any("stale" in f.detail and "EXISTS" in f.detail for f in errors), errors


def test_a_policy_for_a_constant_that_is_gone_is_a_warning(repo, monkeypatch):
    """Renaming a constant must not silently disarm its policy."""
    monkeypatch.setitem(dp.POLICIES,
                        "engine/consolidation/vanished.py:GONE",
                        dp.Policy(dp.K_EXISTS))
    warns = [f for f in dp.check(repo) if f.level == "warn"]
    assert any("vanished.py:GONE" in f.where for f in warns), warns


# ── the kinds that opt out ───────────────────────────────────────────────────

def test_a_filename_filter_needs_a_why_but_not_existence(repo, monkeypatch):
    key = _module(repo, "filt.py",
                  'SKIP = ("CONTEXT.md", "_template.md")\n') + ":SKIP"
    with pytest.raises(ValueError, match="requires a `why`"):
        dp.Policy(dp.K_NAMES)
    monkeypatch.setitem(dp.POLICIES, key, dp.Policy(
        dp.K_NAMES, why="filenames matched anywhere, not paths"))
    assert not [f for f in dp.check(repo) if f.level == "error"]


# ── the shell table, and violation 6 ─────────────────────────────────────────
#
# `PAZRAS_TIMERS` named `knowledge/operations/consolidation-cycle.md` in a
# `doc=` field for the 26 days after the leaf moved into `meta/`. Neither gate
# could see it: this module read Python only, and `links --check` walks
# `memory/` only, so a `engine/` file naming a moved leaf fell between the two.
# The field is now a declared path, and these prove it in both directions.

TABLE = "config/structure/pazras-master-config.sh:PAZRAS_TIMERS"


@pytest.fixture
def home_repo(tmp_path):
    """The same miniature, but sited the way the real one is.

    A `doc=` is written `06_SYSTEM/agents/...` because the unit resolves it
    against `%h`, so the repository has to BE `%h/06_SYSTEM` for the entry to
    mean anything. The other fixture puts the repo at the tmp root, where
    `06_SYSTEM/` would resolve to a sibling that does not exist -- the test
    would then pass for the wrong reason, or fail for one.
    """
    repo = tmp_path / "06_SYSTEM"
    (repo / "engine/consolidation").mkdir(parents=True)
    (repo / "engine/context/").mkdir(parents=True)
    (repo / "memory/knowledge").mkdir(parents=True)
    return repo


def _config(repo, body):
    p = repo / "config/structure/pazras-master-config.sh"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def test_the_live_table_declares_every_exec_and_doc_it_carries():
    """Derived from the file rather than asserted as a number: a count written
    here would be a second copy of the table, with the same drift defect.

    The file is read through `source_text`, which follows the classification's
    rename to `*.example.sh`, so the same fourteen rows are asserted in the
    instance and in the published tree -- the table is what travels, and only
    its values are templated."""
    found = dp.discover()[TABLE]
    text = dp.source_text(TABLE)
    assert text is not None, TABLE
    expected = [part.partition("=")[2].split()[0]
                for line in text.splitlines() if line.strip().startswith('["')
                for part in line.rstrip('"').split(";")
                if part.partition("=")[0] in ("exec", "doc")]
    assert expected and found == expected
    assert all(e.startswith("06_SYSTEM/") for e in found)


def test_a_doc_field_naming_a_moved_leaf_is_an_error(home_repo):
    """Violation 6 itself, reproduced. The leaf exists at its new home and the
    table still names the old one -- the state that held for 26 days."""
    repo = home_repo
    (repo / "memory/knowledge/system/pass").mkdir(parents=True)
    (repo / "memory/knowledge/system/pass/consolidation-cycle.md").write_text("x")
    _config(repo, 'declare -gA PAZRAS_TIMERS=(\n'
                  '    ["familiar-memory"]="on_calendar=*-*-* 03:30:00;'
                  'doc=06_SYSTEM/memory/knowledge/operations/consolidation-cycle.md"\n'
                  ')\n')
    errors = [f for f in dp.check(repo) if f.level == "error"]
    assert any(f.where == TABLE and "operations/consolidation-cycle" in f.detail
               for f in errors), errors


def test_the_same_field_at_its_real_home_is_silent(home_repo):
    repo = home_repo
    (repo / "memory/knowledge/system/pass").mkdir(parents=True)
    (repo / "memory/knowledge/system/pass/consolidation-cycle.md").write_text("x")
    _config(repo, 'declare -gA PAZRAS_TIMERS=(\n'
                  '    ["familiar-memory"]="nice=10;'
                  'doc=06_SYSTEM/memory/knowledge/system/pass/consolidation-cycle.md"\n'
                  ')\n')
    assert not [f for f in dp.check(repo)
                if f.level == "error" and f.where == TABLE]


def test_an_exec_keeps_only_its_first_token(home_repo):
    """`exec=06_SYSTEM/engine/familiar backup verify 5%%` is one path and
    three arguments. Treating the whole value as a path would report every
    argument-carrying timer as missing, which is noise that would get the check
    switched off."""
    repo = home_repo
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "engine/structure").mkdir(parents=True, exist_ok=True)
    (repo / "engine/structure/pazras.sh").write_text("#!/bin/sh\n")
    _config(repo, 'declare -gA PAZRAS_TIMERS=(\n'
                  '    ["pazras-verify"]="exec=06_SYSTEM/engine/structure/pazras.sh '
                  'backup verify 5%%;nice=19"\n'
                  ')\n')
    assert dp.discover(repo)[TABLE] == ["06_SYSTEM/engine/structure/pazras.sh"]
    assert not [f for f in dp.check(repo)
                if f.level == "error" and f.where == TABLE]


def test_the_table_going_missing_is_reported_not_skipped(home_repo):
    """The dangerous direction for a NAMED source: renaming the table leaves a
    policy guarding nothing, and silence would look like success."""
    _config(home_repo,
            'declare -gA PAZRAS_SCHEDULES=(\n    ["x"]="doc=y.md"\n)\n')
    assert any(f.where == TABLE and "no longer exists" in f.detail
               for f in dp.check(home_repo))


def test_a_field_outside_the_repository_does_not_crash_the_report(home_repo):
    """An R_HOME entry need not be under `06_SYSTEM/`; `%h/.local/bin/x` is a
    legitimate `exec=`. `relative_to` raises there, so the reporting path would
    have crashed on exactly the entry it exists to report."""
    _config(home_repo, 'declare -gA PAZRAS_TIMERS=(\n'
                       '    ["x"]="exec=.local/bin/nothing-here"\n)\n')
    errors = [f for f in dp.check(home_repo) if f.where == TABLE]
    assert len(errors) == 1
    assert ".local/bin/nothing-here" in errors[0].detail


def test_the_shell_source_is_named_and_says_so():
    """Eight of the nine uppercase tables in `engine/**/*.sh` hold prose in
    their values, so the shell side is named rather than discovered. That is a
    real limitation and must stay written down, not inferred."""
    assert set(dp.SHELL_FIELDS) == {TABLE}
    assert dp.SHELL_FIELDS[TABLE] == ("exec", "doc")
    assert "not discovered" in pathlib.Path(dp.__file__).read_text()


# ── retired paths: O2f's no-shim gate ─────────────────────────────────────
#
# O2f split `scripts/core/` and added NO compatibility shim, on the reasoning
# that a shim becomes permanent and the caller list was small enough to
# exhaust. These are what make that reasoning safe rather than optimistic: a
# missed caller has to fail in review, because its own failure is silent --
# `source "$HOME/.pazras-system/core/pazras-config-loader.sh"` breaks at 03:30,
# and bootstrap.sh's copy prints "skipping" and enables no timers at all.

def test_the_live_repository_names_no_retired_path():
    assert [f"{f.where}: {f.detail[:60]}" for f in dp.retired_findings()] == []


def test_a_missed_caller_is_an_error(tmp_path):
    """The `engine/host/pazras-utils.sh` case, which is the one a grep for
    `scripts/core/` does not find -- it spells the path `.pazras-system/core/`
    through the stow symlink."""
    import subprocess
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    f = tmp_path / "engine/host/pazras-utils.sh"
    f.parent.mkdir(parents=True)
    f.write_text('source "$HOME/.pazras-system/core/pazras-config-loader.sh"\n')
    subprocess.run(("git", "-C", str(tmp_path), "add", "-A"), check=True)
    errs = dp.retired_findings(tmp_path)
    assert len(errs) == 1
    assert errs[0].where == "engine/host/pazras-utils.sh:1"
    assert ".pazras-system/core/" in errs[0].detail


def test_an_untracked_file_is_not_the_repositorys_claim(tmp_path):
    """Scoped to `git ls-files`. A machine-local settings file or a scratch
    note is not the repository asserting anything, and failing a shared gate
    on one would make the gate personal to whoever ran it."""
    import subprocess
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    (tmp_path / "scratch.sh").write_text("scripts/core/checks.py\n")
    assert dp.retired_findings(tmp_path) == []


def test_a_tree_that_cannot_be_read_warns_rather_than_passing(tmp_path):
    """A gate that silently becomes a no-op is the exact failure this module
    was written for. The file list now comes from git in a checkout and from a
    WALK in a generated tree, which has no `.git`; a directory that is neither
    is reported rather than shrugged off."""
    out = dp.retired_findings(tmp_path / "not-a-repo")
    assert len(out) == 1 and out[0].level == "warn"
    assert "did not run" in out[0].detail


def test_every_retired_path_carries_a_reason_and_is_actually_gone():
    for dead, why in dp.RETIRED.items():
        assert len(why.split()) >= 5, dead
        if dead.startswith("scripts/"):
            assert not (dp.REPO / dead).exists(), (
                f"{dead} is declared retired and still exists")


def test_only_the_register_and_its_test_are_exempt_from_themselves():
    """A list of retired names cannot be written without writing the names,
    and neither can the test that proves the list works. That is the ONLY
    reason either is exempt -- pinned here so the exemption cannot quietly
    grow to cover a file that merely finds the gate inconvenient."""
    assert set(dp.RETIRED_EXEMPT) == {
        "memory/journal/", "dev/", "config/knowledge/violations.yaml",
        "config/publication/export-state.json",
        "memory/knowledge/system/consolidation/_data/",
        "engine/checks/declared_paths.py",
        "engine/checks/tests/test_declared_paths.py",
    }


def test_the_split_actually_happened():
    """O2f's shape, asserted rather than assumed: the two subjects are two
    directories, and each holds what the spec table says it holds. R2c then
    filed the timers generator under `schedule/`, by `places:`."""
    for name in ("checks.py", "declared_paths.py", "healthcheck.sh",
                 "pre-commit", "tests"):
        assert (dp.REPO / "engine/checks" / name).exists(), name
    for name in ("pazras-config-loader.sh", "pazras-structure-gen.sh"):
        assert (dp.REPO / "engine/structure" / name).exists(), name
    assert (dp.REPO / "engine/schedule/timers-gen.sh").exists()
    # R2e: the master config is a decision, not code, and left the engine. Its
    # name differs by tree -- the instance's is the export's `*.example.sh` -- so
    # the assertion asks for the file the way the check does, by the key that
    # resolves through that rename.
    assert dp.source_text(TABLE) is not None
    assert not (dp.REPO / "scripts/core").exists()
    assert not (dp.REPO / "scripts/hooks").exists()


def test_the_git_hook_points_at_the_moved_gate():
    """`.git/hooks/pre-commit` is a SYMLINK and git does not move it, so O2f
    had to recreate it by hand -- the one interface in the split that no
    rewrite pass could have reached."""
    hook = dp.REPO / ".git/hooks/pre-commit"
    if not hook.exists():
        pytest.skip("no .git/hooks/pre-commit in this checkout")
    assert hook.resolve() == (dp.REPO / "engine/checks/pre-commit").resolve()


# ── the check registry's owner claims ────────────────────────────────────────
#
# `checks.py --list` said `manual` and a reader concluded "never runs". That
# reading was wrong -- healthcheck.sh runs those weekly and owns their
# --fix wiring -- and the fix is the label plus a verified owner claim. These
# prove the verification works rather than merely existing.

import importlib.util
import sys


def _checks():
    """Load checks.py by path. It is a script, not an installed module, and it
    must be in sys.modules before exec_module: `@dataclass` resolves type hints
    through the module's own namespace and raises without an entry."""
    path = pathlib.Path(__file__).resolve().parents[1] / "checks.py"
    name = "pazras_checks_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        pass
    return mod


def test_every_owner_claim_holds():
    assert _checks().owner_findings() == []


def test_a_wrong_owner_claim_is_caught(monkeypatch):
    """The label says who runs a check. If the command is renamed and the owner
    stops running it, `--list` must not go on saying it runs."""
    mod = _checks()
    bogus = mod.Check(
        "renamed-away", "a check nobody runs",
        ("engine/cli/familiar-context.py", "links", "--check", "--renamed"),
        frozenset({mod.GATE_MANUAL}), owner=mod.HEALTHCHECK)
    monkeypatch.setattr(mod, "CHECKS", (bogus,))
    problems = mod.owner_findings()
    assert len(problems) == 1
    assert "renamed-away" in problems[0]


def test_an_owner_that_does_not_exist_is_caught(monkeypatch):
    mod = _checks()
    bogus = mod.Check(
        "ghost-owned", "owner file is gone",
        ("engine/cli/familiar-context.py", "links", "--check"),
        frozenset({mod.GATE_MANUAL}), owner="engine/checks/nope.sh")
    monkeypatch.setattr(mod, "CHECKS", (bogus,))
    assert "unreadable" in mod.owner_findings()[0]


def test_a_check_this_registry_runs_needs_no_owner():
    """`owner` is for the checks this registry does NOT execute. A gated check
    needs none, and the audit must not invent one."""
    mod = _checks()
    assert not any(c.owner for c in mod.CHECKS
                   if c.gates != frozenset({mod.GATE_MANUAL}))


def test_the_shell_script_checks_are_all_in_the_registry():
    """The gap that produced this: healthcheck.sh ran
    `knowledge index --check` and the registry did not name it, so the one place
    that is supposed to know the full set of checks did not."""
    mod = _checks()
    text = (pathlib.Path(__file__).resolve().parents[2]
            / "checks/healthcheck.sh").read_text()
    for c in mod.CHECKS:
        if c.owner != mod.HEALTHCHECK:
            continue
        exe = pathlib.Path(str(c.command[0])).name
        args = " ".join(str(p) for p in c.command[1:])
        assert any(exe in line and args in line for line in text.splitlines()), c.id


def test_a_fixture_may_build_any_layout(tmp_path):
    """R2f's third kind: a test builds a synthetic tree in `tmp_path`, so its
    paths are data, not claims about this repository. ONE rule, and a live file
    is still checked -- the exemption is a scope, not an off switch."""
    live = tmp_path / "engine" / "knowledge" / "m.py"
    live.parent.mkdir(parents=True)
    live.write_text('X = "knowledge/meta/x.md"\n')
    fix = tmp_path / "engine" / "knowledge" / "tests" / "test_x.py"
    fix.parent.mkdir(parents=True)
    fix.write_text('X = "knowledge/meta/x.md"\n')
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    found = [f.where for f in dp.retired_findings(tmp_path)]
    assert len(found) == 1 and "m.py" in found[0], found


# ── the export gate, and what may skip in a generated tree ──────────────────
#
# `publish.py` runs `checks.py --run export` on the tree it has just built, so
# the membership of that gate is load-bearing: it is what stops a publish from
# carrying a tree whose own gate is red. It is DERIVED from `pre-commit` rather
# than listed a second time, and these two properties are what make the
# derivation safe to rely on.

def test_the_export_gate_is_pre_commit_minus_exactly_its_declared_exclusions():
    """The difference between the two gates IS `EXPORT_EXCLUDED`, both ways.

    One direction catches an exclusion that was added without saying so; the
    other catches a check that left `pre-commit` -- and therefore the export's
    gate with it -- which is the silent version of the same loss. Two hand-kept
    lists would drift invisibly, which is the failure `checks.py` exists to
    prevent one level up."""
    c = _checks()
    pre = {x.id for x in c.gate_checks(c.GATE_PRE_COMMIT)}
    export = {x.id for x in c.gate_checks(c.GATE_EXPORT)}
    assert pre - export == set(c.EXPORT_EXCLUDED)
    assert export - pre == set()


def test_every_export_exclusion_names_a_registered_check():
    """So a rename cannot widen the exclusion without anything noticing, and
    the reason `--list` implies always has a check to be about."""
    c = _checks()
    assert set(c.EXPORT_EXCLUDED) <= {x.id for x in c.CHECKS}


def test_every_instance_only_check_carries_a_reason_a_reader_can_act_on():
    """`instance_only` is the ONLY way a check may skip in a generated tree, so
    it costs a reason -- one that says what the check measures and why a tree
    without `dev/` has nothing for it to read. `Check.__post_init__` refuses a
    short one at import; this asserts the property and that it is not vacuous,
    because a registry where nobody declares anything is a gate that fails in
    the export rather than one that skips."""
    c = _checks()
    marked = [x for x in c.CHECKS if x.instance_only]
    assert marked, ("no check declares `instance_only`: in a generated tree "
                    "every instance-measuring check would fail instead")
    for x in marked:
        assert len(x.instance_only.split()) >= 5, x.id
