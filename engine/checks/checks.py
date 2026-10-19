#!/usr/bin/env python3
"""The one registry of drift/regression checks for this repo.

Problem this replaces: `engine/checks/pre-commit`, `healthcheck.sh`
and CLAUDE.md's "Verifying a change" section each hardcoded their own list
of "checks to run before trusting this repo", and the three disagreed.
Worse, five pytest suites (engine/lib/tests, engine/context/tests, and the
two hyphenated engine/boundaries/test-*.py files pytest's default glob
cannot even collect) were run by none of the three — a gap nothing caught
because there was no single place that knew the full set of checks that
*should* exist.

This module is that place. Add a check by adding one `Check(...)` entry
below — not by editing pre-commit, healthcheck.sh and CLAUDE.md by
hand. `--audit` closes the loop: it walks engine/** for test files and
fails if any exists that no registry entry runs, which is exactly the
mechanism that would have caught the original gap and now guards against it
recurring.

Scope decision: `healthcheck.sh` already runs its own drift checks
(STRUCTURE.md, timers staging, boundaries compile, memory/ pointers, skill
index) with per-check --fix wiring and warn/fail semantics richer than a
plain pass/fail command. Folding those into this registry's execution path
would mean re-deriving that --fix logic here; not worth it for this pass.
Those checks still get a `Check` entry (gates={"manual"}) so CLAUDE.md and
`--list` can point at them, but only the "healthcheck" gate is actually
wired into healthcheck.sh's own run (as a new unit-test section) —
see there for the previously-ungated pytest suites this was written to fix.

Usage:
    python3 engine/checks/checks.py --list [--gate {pre-commit,healthcheck,manual}]
    python3 engine/checks/checks.py --run  {pre-commit,healthcheck,manual}
    python3 engine/checks/checks.py --audit
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import roots  # noqa: E402

REPO = roots.REPO
# The roots as the registry spells them in a command line: relative to REPO,
# which is the cwd every check runs in. From `lib/roots.py`, so a move of a
# root rewrites no command here (R2a).
E = roots.ENGINE_REL
M = roots.MEMORY_REL

GATE_PRE_COMMIT = "pre-commit"
GATE_HEALTHCHECK = "healthcheck"
# The gate a GENERATED tree runs on itself, which `publish.py` drives in the
# scratch tree before it writes anything into the target. It is not a second
# list: it is `pre-commit` minus EXPORT_EXCLUDED, computed below, because two
# hand-kept lists would drift and the drift would be invisible -- the failure
# this module exists to prevent, one level up.
GATE_EXPORT = "export"
# NOT "never runs". A `manual` entry means THIS REGISTRY does not execute it,
# which is a statement about this module and not about coverage. The handoff on
# 2026-09-11 read `--list` as saying `context-links` never runs, and corrected
# it in place: healthcheck.sh runs `familiar context links --check` weekly
# (Wed 07:00) and owns the `--fix` wiring itself, independently of this file. So
# `--list` was an ACCURATE REGISTRY and a MISLEADING DELIVERY MAP, and the fix
# is the label plus the `owner` field below, not more coverage. Adding a second
# runner for checks the shell script already runs would mean re-deriving its
# --fix semantics here for no gain.
GATE_MANUAL = "manual"
GATES = (GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL, GATE_EXPORT)

# What a publish leaves out of the exported tree's own gate, and why each entry
# cannot be there:
#
#   pytest-publication  its end-to-end test CALLS `publish.py`, and
#                       `publish.py` runs this gate on the tree it has just
#                       built -- so a gate that includes it re-enters the
#                       publish with no base case. The suite still runs in the
#                       instance's own pre-commit gate, which is where the
#                       exporter is under test; inside a publish the exporter
#                       is the subject rather than the tester.
#
# `test_checks.py` asserts this set is EXACTLY the difference between the two
# gates, so an exclusion cannot be added quietly and a check cannot leave the
# export's gate by accident. Everything else in `pre-commit` runs in both, and
# whatever a generated tree cannot measure says so per check, via
# `instance_only`.
EXPORT_EXCLUDED = frozenset({"pytest-publication"})

# Who actually runs a check, when this registry does not. `owner` is either None
# (this registry runs it, so `gates` is the whole story) or the path of the file
# that does -- and a claim naming a file is CHECKED, by `owner_findings()`
# below, which greps that file for the command. That turns the label from
# something a reader infers into something the code asserts.
#
# Same discipline as the rest of Track B: a mechanism claim names the file that
# implements it, and a check fails when it cannot.
HEALTHCHECK = f"{E}/checks/healthcheck.sh"


# What a git hook exports into everything it runs. In a linked worktree
# `GIT_DIR` points at the *real* repository's git dir, so a check that shells
# out to `git init` -- the memory selftest's fixture does -- re-initialises that
# repository and writes `core.bare = true` into the shared config, after which
# every git command in the main worktree fails with "this operation must be run
# in a work tree". Observed 2026-09-29, reproduced in isolation. The same leak
# makes `git ls-files`-based checks (instance-refs) see the hook's index rather
# than the repository's. A gate is a check, not an extension of the hook's
# environment.
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX",
                "GIT_COMMON_DIR")


def child_env() -> dict[str, str]:
    """The environment a gate runs in: this process's, minus git's own."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}


@dataclass(frozen=True)
class Check:
    id: str
    description: str
    command: tuple[str, ...]  # argv; command[0] resolved against REPO if it exists there
    gates: frozenset[str]
    optional: bool = False  # skip with a warning (not a failure) if the tool isn't installed
    # The runner that owns this check, or None if `gates` says it. Set it to
    # HEALTHCHECK for the entries the shell script drives; leave it None for a
    # check nothing runs automatically, which is a deliberate state rather than
    # an oversight and is reported as such by `--list`.
    owner: str | None = None
    # Set when the check's SUBJECT exists only in this instance -- the
    # classification, the deny-list, the vault config -- so a GENERATED tree has
    # nothing for it to read and it would fail on an absence rather than on a
    # finding. The value is the reason, and it is mandatory when set.
    #
    # WHY THIS IS A DECLARATION AND NOT A SILENT `return 0`. A check that
    # measures the private tree and reports green in the export is worse than a
    # red one: the next publish carries whatever it stopped seeing. So the skip
    # is (a) declared here rather than inferred, (b) printed on every run, and
    # (c) counted in the gate's own summary -- "measured nothing" and "measured
    # clean" are different lines, and a reader has to be able to tell them
    # apart. A check that measures the instance and does NOT say so still fails
    # in the export, which is how this stays fail-closed: the declaration is the
    # only way out, and it costs a reason.
    #
    # The predicate is `roots.instance_here()` -- `dev/` is present or it is
    # not -- rather than "is the private input this check reads here". The two
    # agree wherever the classification is honest, because that is what omits
    # the inputs, and where it is not `publish-audit` is already red.
    instance_only: str = ""

    def __post_init__(self):
        if self.instance_only and len(self.instance_only.split()) < 5:
            raise ValueError(
                f"{self.id}: the reason for `instance_only` is not a reason: "
                f"{self.instance_only!r}")


CHECKS: tuple[Check, ...] = (
    Check(
        "boundaries-compile",
        "BOUNDARIES.yaml and its compiled targets agree",
        (f"{E}/boundaries/compile.py", "--check"),
        frozenset({GATE_PRE_COMMIT, GATE_MANUAL}),
        instance_only="the deny-list and its compiled targets belong to the "
                      "machine: `read-write.yaml` holds its paths, and two of "
                      "the four targets are files in its `$HOME`. The export "
                      "carries neither, so there is nothing to compile there, "
                      "and the check would read a deliberately absent "
                      "`boundaries.json` as drift.",
    ),
    Check(
        "pytest-knowledge",
        f"{E}/knowledge unit tests",
        ("python3", "-m", "pytest", f"{E}/knowledge/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    Check(
        "pytest-harness",
        f"{E}/harness unit tests",
        ("python3", "-m", "pytest", f"{E}/harness/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    Check(
        "pytest-consolidation",
        f"{E}/consolidation unit tests",
        ("python3", "-m", "pytest", f"{E}/consolidation/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    Check(
        "pytest-cli",
        f"{E}/cli unit tests",
        ("python3", "-m", "pytest", f"{E}/cli/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    # Runs WITHOUT pytest, deliberately. `pytest-consolidation` above also exercises
    # these invariants (engine/consolidation/tests/test_stage_invariants.py), but the pass itself is
    # stdlib-only and started by a systemd timer, so the gate that says whether
    # a stage still guarantees what it declares has to be reachable from the
    # same command the timer can run. See stages/invariants.py for why this
    # exists: three silent defects shipped in one module because nothing
    # required a stage to state its invariants.
    Check(
        "memory-invariants",
        "every pass stage declares its invariants, and holds them",
        (f"{E}/familiar", "checks", "selftest", "--invariants"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    Check(
        "pytest-lib",
        f"{E}/lib unit tests",
        ("python3", "-m", "pytest", f"{E}/lib/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    # The other half of the 2026-09-11 lesson. `memory-invariants` asks whether
    # a stage still does what it says; this asks whether the FILES every module
    # declares it depends on are still there. memory/MEMORY.md was deleted and
    # stage 4 kept reading it for a week, because a deleted name is invisible to
    # every gate by design — see the module docstring for why `links --check`
    # was right not to catch it.
    # Healthcheck and manual only, deliberately: between an edit and the next
    # publish the recorded hash is SUPPOSED to be stale, and a gate that fails on
    # every commit in between is a gate the reader learns to ignore.
    Check(
        "publish-drift",
        "a published artifact's private source has not moved since its export",
        ("python3", f"{E}/checks/publish_drift.py"),
        frozenset({GATE_HEALTHCHECK, GATE_MANUAL}),
        instance_only="the state file is `dev/publication/export-state.json` "
                      "and `dev/` never travels. Whether the sources have "
                      "moved since an artifact was published is a question "
                      "about the tree that exported it, not about the export.",
    ),
    # Track P's allow-list. The public tree is a GENERATED artifact, so the
    # failure that matters is the file nobody thought of -- and a deny-list
    # fails open on exactly that one. `dev/publication/publish.yaml` classifies
    # every tracked path, and this fails on a path it does not name and on a
    # rule that no longer matches anything (the deletion nobody re-reads).
    Check(
        "publish-audit",
        "every tracked path is classified for publication, and every rule bites",
        ("python3", f"{E}/checks/publish_audit.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        instance_only="its subject is `dev/publication/publish.yaml`, which "
                      "the classification itself omits: it describes the tree "
                      "that was exported, and says nothing about the tree "
                      "that came out.",
    ),
    # The exporter's own tests: the classification's precedence, the marker's
    # permission slip, and the register surgery. Pre-commit because a broken
    # exporter is a `git push` away from publishing the wrong tree.
    Check(
        "pytest-publication",
        f"{E}/publication unit tests",
        ("python3", "-m", "pytest", f"{E}/publication/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    # MANUAL, and no owner, deliberately: the leak scanner runs on the
    # GENERATED tree -- a clone of the public repository -- never on this one,
    # which holds the journal and the user's own paths on purpose. The
    # exporter calls it at the end of every publish, which is why nothing else
    # needs to.
    Check(
        "publish-scan",
        "a GENERATED tree carries no undeclared leak (runs on the export, not here)",
        ("python3", f"{E}/checks/publish_scan.py", "--tree", "<the exported tree>"),
        frozenset({GATE_MANUAL}),
    ),
    Check(
        "declared-paths",
        "every declared path exists, or is declared absent with a reason",
        ("python3", f"{E}/checks/declared_paths.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # R3e's gate. The Obsidian graph shows the files under the vault root, so
    # "no `engine/` files in the graph" is a claim about where that root is --
    # and `git mv memory/.obsidian .` is a one-line way to get it wrong without
    # anything announcing it.
    Check(
        "vault",
        f"the Obsidian vault is {roots.MEMORY_REL}/ and only {roots.MEMORY_REL}/",
        ("python3", f"{E}/checks/vault.py"),
        frozenset({GATE_PRE_COMMIT, GATE_MANUAL}),
        instance_only="it asserts the vault's config sits at "
                      f"`{roots.rel(roots.MEMORY / '.obsidian' / 'app.json')}`, "
                      "and the classification "
                      "omits that config: the published tree is not a vault, "
                      "so its absence there is the design rather than a "
                      "finding.",
    ),
    # P1's contract: which paths the engine expects, rewrites, may touch, and
    # leaves to the person -- derived from posture, roots and the registers, so
    # a change to any of them that is not regenerated fails here, not in a
    # second install that read a stale contract.
    Check(
        "vault-contract",
        f"{roots.rel(roots.VAULT_EXAMPLE)} is what posture, roots and the registers derive",
        (f"{E}/familiar", "consolidation", "vault", "--check"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # The profile parses, its Areas are well-formed and their codes unique. A
    # broken profile does not raise in `roots` (the guard imports it), so this
    # is where it is loud.
    Check(
        "profile",
        f"{roots.rel(roots.PROFILE_FILE)} (or the example) parses, its Areas well-formed",
        ("python3", f"{E}/lib/profile.py", "--check"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # R2a's gate: engine code asks `lib/roots` where a root is instead of
    # spelling its name, so the R2/R3 moves change constants, not strings.
    Check(
        "root-literals",
        "no engine code spells a root's name outside lib/roots",
        ("python3", f"{E}/checks/root_literals.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # R2c's exit: the engine's code packages import only to their left in
    # lib <- knowledge <- harness <- context <- consolidation <- cli (R1j).
    Check(
        "import-order",
        "engine packages import only to their left in R1j's order",
        ("python3", f"{E}/checks/import_order.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # R1k: `engine/` is generic code, so an occurrence of the user's
    # instance is a finding. Warn mode -- the ones that exist are
    # declared in the register entry whose `surfaced_by` is
    # `instance-refs`; anything NEW fails.
    Check(
        "instance-refs",
        "the engine names the user's instance only where declared",
        ("python3", f"{E}/checks/instance_refs.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # P2's push guard, wired as engine/checks/pre-push and run by git on every
    # push. The registry cannot carry that check: the rule needs the remote URL,
    # which only the hook has. What it carries is the state, which is the half
    # that rots -- the hook is a SYMLINK into this tree, git does not move it,
    # and a guard nobody installed protects nothing while looking installed.
    Check(
        "push-guard",
        "the push guard is armed wherever the private tree is",
        ("python3", f"{E}/checks/push_guard.py", "--check"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # The push guard's second rule, and the same shape of entry: the SCAN needs
    # a destination and the refs being pushed, which only the hook has, so what
    # the registry can carry is the state -- is the gate armed in a checkout
    # whose origin is public, and where the answer is unknown, what the reader
    # should do about it. 2026-10-16: the dotfiles repository had no hook at
    # all, which is the state this reports rather than assumes.
    #
    # instance_only: its subject is this instance's checkouts and this
    # instance's origin, and a generated tree has neither a hook of its own nor
    # a private register for the patterns to come from.
    Check(
        "leak-gate",
        "the leak gate is armed wherever a push starts that is public-bound",
        ("python3", f"{E}/checks/leak_gate.py", "--check"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        instance_only="it reports the arming of this instance's checkouts and the "
                      "visibility of their origins; a generated tree has no "
                      "hooks of its own to arm and no private register to "
                      "scan against",
    ),
    Check(
        "pytest-checks",
        f"{E}/checks unit tests",
        ("python3", "-m", "pytest", f"{E}/checks/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    Check(
        "pytest-context",
        f"{E}/context unit tests",
        ("python3", "-m", "pytest", f"{E}/context/tests", "-q"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
    ),
    # Not run through `pytest -m pytest`: both scripts call sys.exit() at
    # module level (script style, not test_ functions), which pytest's
    # assertion-rewriting import hook turns into an INTERNALERROR instead of
    # a clean process exit. Run them directly — that is how they were always
    # designed to run (renamed only to fix pytest's collection glob for
    # anyone who does point pytest at the directory; see docstrings).
    Check(
        "guard",
        "guard regression suite",
        ("python3", f"{E}/boundaries/test_guard.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        instance_only="it reads the compiled guard file "
                      f"`{roots.rel(roots.BOUNDARIES_JSON)}`, which the "
                      "classification omits and which `boundaries-compile` "
                      "writes on this machine only: a generated tree has no "
                      "compiled guard to regress.",
    ),
    Check(
        "pi-emitter",
        "Pi emitter regression suite",
        ("python3", f"{E}/boundaries/test_pi_emitter.py"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # Pre-commit since 2026-10-11: both guards failed OPEN for four days after
    # R2e moved boundaries.json (b75a1b3), and these suites -- then manual-only
    # -- were the only thing that showed it.
    Check(
        "pi-guard-node",
        "Pi guard node regression suite",
        ("node", f"{E}/boundaries/pi-guard/test-guard.mjs"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
        instance_only="the cases name the machine's private paths -- personal documents, ssh key, "
                      "the deny-list -- and expect the compiled guard to refuse them. "
                      "The export carries neither the rules nor the target, and "
                      "measured 2026-10-14 the suite is green in the published tree "
                      "only where `$HOME` is the publisher's: under a scratch HOME "
                      "every BLOCK case reads `got=allow`. A stranger's clone "
                      "reported these two red with no defect behind it.",
    ),
    Check(
        "opencode-plugin-node",
        "opencode boundaries plugin regression suite",
        ("node", f"{E}/boundaries/opencode-plugin/test-plugin.mjs"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
        optional=True,
        instance_only="the cases name the machine's private paths -- personal documents, ssh key, "
                      "the deny-list -- and expect the compiled guard to refuse them. "
                      "The export carries neither the rules nor the target, and "
                      "measured 2026-10-14 the suite is green in the published tree "
                      "only where `$HOME` is the publisher's: under a scratch HOME "
                      "every BLOCK case reads `got=allow`. A stranger's clone "
                      "reported these two red with no defect behind it.",
    ),
    Check(
        "structure",
        "STRUCTURE.md matches the master config",
        (f"{E}/familiar", "structure", "generate", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    # P4b's figures. `pre-commit` as well as `manual`, like boundaries-compile:
    # the figures are drawn from registers that several of these checks already
    # gate, and a register edited without a regenerate is exactly the drift this
    # catches. The authored figures' `%% path:` declarations are checked here
    # too, which is the only thing standing between them and a dead link.
    Check(
        "maps",
        "the architecture figures match the registers they are drawn from",
        (f"{E}/familiar", "structure", "maps", "--check"),
        frozenset({GATE_PRE_COMMIT, GATE_MANUAL}),
    ),
    Check(
        "validate",
        "master config parses, no duplicate Area codes",
        (f"{E}/familiar", "structure", "validate"),
        frozenset({GATE_MANUAL}),
    ),
    Check(
        "status",
        "system status report",
        (f"{E}/familiar", "structure", "status"),
        frozenset({GATE_MANUAL}),
    ),
    Check(
        "timers-gen",
        "scheduled units match the live dotfiles source, with no stale pair left",
        (f"{E}/schedule/timers-gen.sh", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    Check(
        "context-links",
        f"{M}/ pointers resolve, no orphaned leaves",
        (f"{E}/familiar", "context", "links", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    Check(
        "context-tree",
        "always-loaded budget and caps hold",
        (f"{E}/familiar", "context", "tree", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    Check(
        "context-l1",
        "always-on payload compiled into harness entry points",
        (f"{E}/familiar", "context", "l1", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    Check(
        "skills-index",
        "skill routers in sync with frontmatter",
        (f"{E}/familiar", "skills", "index", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    # Found missing from this registry on 2026-09-11, while adding the owner
    # column: healthcheck.sh has always run `knowledge index --check`, and
    # nothing here said so. The registry is meant to be the one place that knows
    # the full set of checks that should exist, so a check the shell script runs
    # and this file does not name is exactly the gap `--audit` was written for,
    # one level up. `knowledge/INDEX.md` is the always-reachable file every
    # routed session pays for, which makes it a poor candidate for a silent
    # omission.
    Check(
        "knowledge-index",
        "knowledge/INDEX.md and the branch table in sync, inside budget",
        (f"{E}/familiar", "knowledge", "index", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    # O3c's generated leaf. healthcheck.sh runs it (and regenerates on
    # --fix); named here for the same reason as `knowledge-index` above. It is
    # also the one generated file inside the scored tree, so it carries
    # consolidation's counters -- the generator keeps them (M2a), or every
    # night's count would read as drift.
    Check(
        "knowledge-glossary",
        "the subject glossary in sync with the register",
        (f"{E}/familiar", "knowledge", "glossary", "--check"),
        frozenset({GATE_MANUAL}),
        owner=HEALTHCHECK,
    ),
    # O1l's entry. The structural half of the ontology: every document resolves
    # to one branch and one subject, every declared facet value is inside its
    # domain, every entity has an identifier and no stem collides, every
    # relation endpoint resolves to a declared type or to `external`, and every
    # filename obeys NAMING. It exits 0 with the KNOWN gaps named -- the
    # violations register is data, so "a known gap and a new one must not look
    # the same" is a machine decision rather than a promise.
    Check(
        "ontology-valid",
        "the class registers hold, and every filename obeys NAMING",
        (f"{E}/familiar", "knowledge", "ontology", "check"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    # O1j's entry, kept separate so the naming rules have a surface of their own
    # and `checks.py --run manual` can name the three current violations without
    # running the whole structural half. Same code path as `ontology-valid`
    # (`ontology.naming_findings`), one implementation and two entry points, so
    # the two can not disagree about what a name may look like.
    Check(
        "naming-valid",
        "file- and directory-naming rules 1-9, declared once in the ontology",
        (f"{E}/familiar", "knowledge", "ontology", "naming"),
        frozenset({GATE_PRE_COMMIT, GATE_HEALTHCHECK, GATE_MANUAL}),
    ),
    Check(
        "memory-selftest",
        "memory pass self-test: capture signals, schema, invariants",
        (f"{E}/familiar", "checks", "selftest", "--signals"),
        frozenset({GATE_MANUAL}),
        # NOT owned by the shell script: the capture fixtures need a live
        # skills tree to classify against, so this is a gate a person runs
        # deliberately. Named here so the absence of an owner is a decision on
        # the record rather than an inference. Until 2026-10-13 the flag was
        # `--parity` and diffed the Python capture against the M1 bash
        # baseline, which was deleted with the rename.
    ),
)


def _resolve(command: tuple[str, ...]) -> list[str]:
    cmd = list(command)
    exe_path = REPO / cmd[0]
    if exe_path.exists():
        cmd[0] = str(exe_path)
    return cmd


def _available(check: Check) -> bool:
    """Whether an optional check's tool is present, without running it."""
    if len(check.command) >= 3 and check.command[1:3] == ("-m", "pytest"):
        return subprocess.run(
            [sys.executable, "-c", "import pytest"],
            capture_output=True,
        ).returncode == 0
    return shutil.which(check.command[0]) is not None


def gate_checks(gate: str) -> list[Check]:
    """The checks a gate runs, with `export` DERIVED from `pre-commit`."""
    if gate == GATE_EXPORT:
        return [c for c in CHECKS
                if GATE_PRE_COMMIT in c.gates and c.id not in EXPORT_EXCLUDED]
    return [c for c in CHECKS if gate in c.gates]


def run_gate(gate: str) -> int:
    checks = gate_checks(gate)
    if not checks:
        print(f"checks.py: no checks registered for gate {gate!r}", file=sys.stderr)
        return 0

    failed: list[str] = []
    skipped: list[str] = []
    for c in checks:
        if c.optional and not _available(c):
            print(f"checks.py: {c.id}: {c.command[0]} unavailable — SKIPPED (optional)", file=sys.stderr)
            continue
        print(f"── {c.id}: {c.description} ──")
        # The instance-only skip: printed, named and counted, so that a run
        # which measured nothing never reads like a run that measured clean.
        if c.instance_only and not roots.instance_here():
            print(f"   SKIPPED — measures this instance: {c.instance_only}")
            skipped.append(c.id)
            continue
        result = subprocess.run(_resolve(c.command), cwd=REPO,
                                env=child_env())
        if result.returncode != 0:
            failed.append(c.id)

    # The skip count rides on BOTH summary lines: a passing export and a
    # failing one are the two places a reader looks, and the number is the
    # whole difference between this gate and one that quietly stopped looking.
    tail = (f", {len(skipped)} skipped as instance-only ({', '.join(skipped)})"
            if skipped else "")
    if failed:
        print(f"checks.py: FAILED gate {gate!r}: {', '.join(failed)}{tail}",
              file=sys.stderr)
        return 1
    print(f"checks.py: gate {gate!r} passed ({len(checks)} check(s){tail})")
    return 0


def _covered_paths() -> list[Path]:
    paths = []
    for c in CHECKS:
        for arg in c.command:
            p = REPO / arg
            if p.exists():
                paths.append(p.resolve())
    return paths


def audit() -> list[Path]:
    """Test files under scripts/ that no registry entry's command references."""
    covered = _covered_paths()
    problems = []
    for pattern in ("test_*.py", "test-*.py", "test-*.mjs"):
        for f in sorted(REPO.glob(f"{roots.ENGINE_REL}/**/{pattern}")):
            rf = f.resolve()
            if not any(rf == c or c in rf.parents for c in covered):
                problems.append(f.relative_to(REPO))
    return problems


# The command a check runs, as it would appear in a shell script. Used to verify
# an `owner` claim by grepping the owner's file for it.
def _shell_command(check: Check) -> str:
    return " ".join(str(part) for part in check.command)


def owner_findings() -> list[str]:
    """Verify every `owner` claim against the file it names.

    WHY THIS IS A CHECK AND NOT A COMMENT. The `manual` label was read as
    "never runs" and that reading was wrong -- `healthcheck.sh` runs
    those commands weekly and owns their `--fix` wiring. The correction was
    right and it was written down, which means it can rot exactly like every
    other prose claim this module exists to catch: rename a check's command and
    the shell script silently stops running it while the registry still says it
    does.

    So the label is verified. A `manual`-only entry either names an owner and
    the owner's file really invokes the command, or names no owner and says so
    in a comment. There is no third state, which is the point.
    """
    problems: list[str] = []
    for c in CHECKS:
        if GATE_MANUAL not in c.gates or c.gates != frozenset({GATE_MANUAL}):
            continue
        if c.owner is None:
            continue
        path = REPO / c.owner
        try:
            text = path.read_text()
        except OSError as exc:
            problems.append(f"{c.id}: owner {c.owner} unreadable ({exc})")
            continue
        # Match on the executable's BASENAME plus its arguments, on one line.
        # The leading path is spelled through $HOME, $SCRIPT_DIR or
        # "$SCRIPT_DIR/.." in the shell script, so an exact match on the full
        # command would never fire; the basename and the arguments together are
        # what identify the invocation, and a rename of either is the drift this
        # is here to catch.
        exe = Path(str(c.command[0])).name
        args = " ".join(str(p) for p in c.command[1:])
        ran = any(exe in line and args in line for line in text.splitlines())
        if not ran:
            problems.append(
                f"{c.id}: declares owner {c.owner}, which does not run "
                f"`{_shell_command(c)}` (looked for `{exe}` with `{args}` on "
                f"one line). Either the command was renamed and the owner no "
                f"longer runs it, or the owner claim is wrong -- and `--list` "
                f"is telling readers it runs when it does not.")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print registered checks")
    ap.add_argument("--gate", choices=GATES, help="filter --list to one gate")
    ap.add_argument("--run", metavar="GATE", choices=GATES, help="run every check registered for GATE")
    ap.add_argument("--audit", action="store_true", help="fail if a test file exists that nothing runs")
    args = ap.parse_args(argv)

    if args.audit:
        problems = audit() + owner_findings()
        if problems:
            print("checks.py --audit:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"checks.py --audit: every {E}/ test file is covered by the "
              "registry, and every owner claim holds.")
        return 0

    if args.list:
        # THE LEGEND IS THE FIX. `manual` does not mean "never runs"; it means
        # this registry does not run it. The owner column says who does, and
        # `owner_findings()` checks that claim. Before this, a reader
        # (the handoff, 2026-09-11) concluded `context-links` never ran at all.
        print(f"gates:  pre-commit  runs on every commit ({E}/checks/pre-commit)")
        print(f"        pre-push    runs on every push, from git ({E}/checks/pre-push);")
        print("                    the entry in it checks that the hook is armed")
        print("        healthcheck runs on the weekly timer (healthcheck.sh)")
        print("        export      runs in the scratch tree of every publish,")
        print(f"                    driven by {E}/publication/publish.py:")
        print(f"                    `pre-commit` minus {', '.join(sorted(EXPORT_EXCLUDED))}")
        print("        manual      NOT run by this registry -- see the owner column")
        print("owner:  the file that runs it instead, when this registry does not.")
        print("        instance-only entries measure this machine, so a generated")
        print("        tree skips them and prints the reason.\n")
        chosen = gate_checks(args.gate) if args.gate else CHECKS
        for c in chosen:
            if c.owner:
                owner = c.owner
            elif GATE_MANUAL in c.gates and c.gates == frozenset({GATE_MANUAL}):
                owner = "nothing (documented only)"
            else:
                owner = "this registry"
            gates = ",".join(sorted(c.gates))
            note = "  [instance-only]" if c.instance_only else ""
            print(f"{c.id:20s} [{gates:28s}] {owner:32s} {' '.join(c.command)}{note}")
        return 0

    if args.run:
        return run_gate(args.run)

    if args.audit:
        problems = audit()
        if problems:
            print("checks.py --audit: test files not covered by any registry entry:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"checks.py --audit: every {E}/ test file is covered by the registry.")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
