"""roots.py -- where the repository keeps each kind of thing, declared once.

WHY. Before R2a the four top-level homes were spelled as string literals in
about forty places across both packages, the gate registry and the shell
scripts -- `REPO / "agents" / "ontology"`, `rel.startswith("memory/")`,
`"$HOME/06_SYSTEM/<code dir>/..."`. Phase R2 moved the code to `engine/` and
phase R3 dissolved the vault, then `agents/`, into `memory/` and `config/`
(`ontology SPECS` R1k). With the spellings scattered, each move is a
hunt for strings, and a missed one fails at 03:30. With them here, a move
changes a constant.

THE FOUR ROOTS, by what makes a file under them change:
  ENGINE  generic code; changes when we change what we built
  CONFIG  the user's decisions (directives); changes when the user decides
  MEMORY  the living record; changes with use (sessions, the nightly pass)
  DEV     per-track working notes; changes per track, then retires

THE NAMED HOMES below are the places code actually opens. Each is built from a
root, so R3's move of, say, the ontology registers out of the vault into
`config/knowledge/` was one line here.

`roots.sh` is this module's twin for the shell side. `test_roots.py` holds the
two to the same values.

Stdlib only, and imports nothing from either package: it sits under `lib`,
the bottom of the dependency order (R1j).
"""
from __future__ import annotations

import os
import pathlib
import subprocess

from lib import profile as _profile

REPO = pathlib.Path(__file__).resolve().parents[2]

ENGINE = REPO / "engine"
CONFIG = REPO / "config"
MEMORY = REPO / "memory"
DEV = REPO / "dev"

# The install's facts, from `config/profile.yaml` (or the example a fresh
# clone ships). P1 moved them there from a constant here, so a second install
# is one edited file rather than a hunt. `PROFILE.problems` is non-empty when
# the file did not parse; the roots then fall back to the defaults rather than
# raise, because the boundary guard imports this module on every tool call.
PROFILE = _profile.resolve(CONFIG)

# Where the system is installed, as opposed to where this checkout happens to
# be. A generated payload that tells a harness where to read names the
# install, so a run from a worktree does not write the worktree's path into
# `~/.claude/CLAUDE.md`.
INSTALL = PROFILE.install

# Where the PARA folders live. Outside the repository by definition: the
# repository is one of them (`06_SYSTEM`), at the install.
PARA_ROOT = PROFILE.para_root

# ── named homes ──────────────────────────────────────────────────────────────

LIB = ENGINE / "lib"

ROUTER = REPO / "CONTEXT.md"
JOURNAL = MEMORY / "journal"
KNOWLEDGE = MEMORY / "knowledge"
SKILLS = MEMORY / "skills"

ONTOLOGY = CONFIG / "knowledge"
BOUNDARIES = CONFIG / "boundaries"
USER = CONFIG / "practice" / "user"
CONVENTIONS = CONFIG / "practice" / "conventions"
SUBAGENTS = CONFIG / "orchestration"

# The user's decisions, one folder per subject. R2e moved the settings here
# and R3b the rest: `knowledge/` holds the registers, `boundaries/` the
# rules and their compiled guard targets, `practice/` the user profile and
# the conventions, `harness/` the subagent definitions.
PROFILE_FILE = CONFIG / _profile.NAME
PROFILE_EXAMPLE = CONFIG / _profile.EXAMPLE
VAULT_EXAMPLE = CONFIG / "vault.example.yaml"
MASTER_CONFIG = CONFIG / "structure" / "pazras-master-config.sh"
PARA_READMES = CONFIG / "structure" / "READMEs"
UNITS_STAGING = CONFIG / "schedule"
BOUNDARIES_JSON = CONFIG / "boundaries" / "boundaries.json"
RELAY_CONFIG = CONFIG / "relay" / "relay.yaml"
BACKUP_EXCLUDES = CONFIG / "backup" / "backup-excludes.txt"
MIRROR_EXCLUDES = CONFIG / "backup" / "mirror-excludes.txt"


VAULT_ENV = "PAZRAS_MEMORY_DIR"

# The DATA root: what the hooks and the pass write that is not tracked -- the
# capture logs, transcripts, the append-only records of the Loom and the Almanac.
# Outside the repository, so it is not one of the four roots above, but it is
# spelled once for the same reason they are: the context CLI spelled it
# without the override and would have ignored a test's or a relocated machine's
# `PAZRAS_DATA_DIR` the day one of its verbs read it.
DATA_ENV = "PAZRAS_DATA_DIR"
DATA_DEFAULT = "~/.local/share/pazras"


def data_root(env=None) -> pathlib.Path:
    """The data root: `$PAZRAS_DATA_DIR`, else `~/.local/share/pazras`. An empty
    variable counts as unset. `env` is a mapping, so a caller holding a child's
    environment asks about that one rather than this process's."""
    env = os.environ if env is None else env
    return pathlib.Path(env.get(DATA_ENV) or DATA_DEFAULT).expanduser()


def vault_root(env: str = VAULT_ENV) -> pathlib.Path:
    """The vault a generated leaf belongs in: the environment's, else the INSTALL's.

    Seven modules share the convention, and it is right for a READ: an installed
    run acts on the installed vault. It is ruinous for a WRITE from a checkout
    that is not the install -- see `guard_vault_write`.
    """
    return pathlib.Path(os.environ.get(env, str(INSTALL / MEMORY_REL)))


def guard_vault_write(root: pathlib.Path, tool: str) -> None:
    """Refuse to write a generated leaf into a vault this tree does not own.

    With `PAZRAS_MEMORY_DIR` unset, `INSTALL/memory` is ANOTHER tree's vault and
    the run renders the register in front of it into that vault's leaf. Measured
    2026-10-14: `familiar knowledge glossary`, run from the publication worktree
    with the variable unset, rewrote `~/06_SYSTEM`'s glossary with this branch's
    pruned register, dropping three subjects' places from a tree that has them.

    An explicit `PAZRAS_MEMORY_DIR` is a DECISION and is never refused: that is
    how a worktree writes its own vault, and how `publish.yaml` regenerates the
    leaves of a stage tree (`{stage}/memory`) -- a target the running tree does
    not own on purpose. Only the case nobody chose is the dangerous one.

    The mirror image is why the READ is not refused: a `--check` from the same
    place reads the install's leaf, compares it against this tree's register and
    calls the difference drift. Reading is diagnosable; writing is destructive.
    """
    if os.environ.get(VAULT_ENV):
        return
    if pathlib.Path(root).resolve() == MEMORY.resolve():
        return
    raise SystemExit(
        f"{tool}: no {VAULT_ENV} is set, and the profile's install vault is "
        f"{root} -- another checkout's, not this run's ({MEMORY}). Set "
        f"{VAULT_ENV}={MEMORY} to write this tree's leaf, or run from the "
        f"install. A generated leaf written into a vault the running tree does "
        f"not own replaces that vault's rendering with this one's.")


def rel(path: pathlib.Path) -> str:
    """`path` relative to the repository, POSIX-spelled: `memory/knowledge`."""
    return pathlib.Path(path).relative_to(REPO).as_posix()


def from_home(path: pathlib.Path) -> str:
    """The install's spelling from home, WITHOUT the `~/`: `06_SYSTEM/memory`.

    The spelling a generated marker carries -- `<!-- BEGIN GENERATED always-on
    -- 06_SYSTEM/memory/ -->` -- and the reason this function exists rather than
    `tilde(...)[2:]`: that idiom chops two characters off an absolute path the
    moment the install is not under home. Which it need not be, and in the
    README's own scratch recipe it is not (`HOME=/tmp/h PARA_ROOT=/tmp/p`).

    Absolute, then, when the install is outside home. A marker and a message
    are the two things that must not raise: both are written by tools whose job
    is to run in a scratch tree.
    """
    p = INSTALL / rel(path)
    try:
        return p.relative_to(pathlib.Path.home()).as_posix()
    except ValueError:
        return p.as_posix()


def tilde(path: pathlib.Path) -> str:
    """`path` as the install spells it from home: `~/06_SYSTEM/memory/`.

    Built from INSTALL rather than REPO, so text written for a harness names
    the installed system even when this checkout is somewhere else. An install
    that is not under home spells itself absolutely -- see `from_home`.
    """
    spelling = from_home(path)
    return spelling if spelling.startswith("/") else "~/" + spelling


# The repo-relative spellings, for prefix tests (`rel.startswith(MEMORY_REL +
# "/")`) and for messages a person reads.
ENGINE_REL = rel(ENGINE)
CONFIG_REL = rel(CONFIG)
MEMORY_REL = rel(MEMORY)
DEV_REL = rel(DEV)


# ── which tree this is, and what is in it ────────────────────────────────────

def instance_here() -> bool:
    """Whether this checkout IS the instance, as opposed to a generated tree.

    `dev/` is the marker: the publication classification omits it, so a tree
    without it is an EXPORT. The distinction matters to every check that
    measures this machine rather than the code -- the register declarations,
    the profile, the journal, the deny-list -- and those checks need one
    definition of it, which belongs in the module that already says where each
    root is. `publish.py` writes the export as a plain directory, so a check
    that needs this can not infer it from a `.git`.
    """
    return DEV.is_dir()


# A walk skips these by NAME: build products, never sources. In the instance
# `git ls-files` answers the same question and skips them by `.gitignore`; the
# two sets have to agree, which is why nothing else is skipped here.
WALK_SKIP = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache",
                       ".ruff_cache", ".git"})


def tracked(tree: str | None = ENGINE_REL,
            repo: pathlib.Path | None = None) -> list[str]:
    """The files under `tree` (or the whole repo, for `None`), sorted.

    Repo-relative POSIX spellings. `git ls-files` where that repo is a git
    checkout -- the answer that respects `.gitignore`, so a session's leftovers
    are not measured as if they were part of the tree -- and a walk where it is
    not. Both answers are wanted, and neither will do alone: a GENERATED tree is
    a plain directory by construction, because `publish.py` builds the export in
    a scratch dir and never runs `git init`, and a check that asked git there
    crashed instead of reporting. The walk returns the same set for the same
    reason git's answer is right in the instance: the export holds only
    classified paths, and the one thing a walk could add that git would not -- a
    bytecode cache written by running the gate itself -- is skipped by name.

    `repo` is for the checks that run against a throw-away tree they built
    themselves; it defaults to this checkout.
    """
    repo = REPO if repo is None else pathlib.Path(repo)
    if (repo / ".git").exists():
        argv = ("git", "ls-files") if tree is None else ("git", "ls-files", str(tree))
        out = subprocess.run(argv, cwd=repo, capture_output=True, text=True,
                             check=True).stdout
        return sorted(out.split())
    base = repo if tree is None else repo / tree
    if not base.is_dir():
        return []
    return sorted(
        p.relative_to(repo).as_posix() for p in base.rglob("*")
        if p.is_file()
        and not any(part in WALK_SKIP for part in p.relative_to(repo).parts))
