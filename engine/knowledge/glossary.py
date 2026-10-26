#!/usr/bin/env python3
"""O3c — the glossary leaf, GENERATED from the registers.

`publication` is the one declared subject with no artifact: the branch router,
`INDEX.md` and `ontology.corpus()` all print it as declared-and-empty. This
module gives it its first leaf by rendering the registered subjects -- their
ids, mythic names, criteria and places -- into
`memory/knowledge/system/publication/glossary.md`.

WHY GENERATED, AND NOT WRITTEN BY HAND. The two vocabularies (this leaf and
`config/knowledge/subjects.yaml`) cannot drift if one is derived from the
other. A hand-maintained glossary is a second copy of the register, and a
second copy is the defect O3 exists to delete -- every other reader in this
phase reads the register directly, and this one is only a leaf because the
tree needs an artifact to point at.

Exit codes match `knowledge_index`: 0 ok · 1 error · 3 drift under `--check`.
The healthcheck reads the exit code, not the text.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import sys

from lib import roots

DEFAULT_ROOT = roots.vault_root()


def resolved_root(root: pathlib.Path | None = None) -> pathlib.Path:
    """The vault this run acts on: the default, or the one it was handed.

    The convention -- seven sibling modules share it -- is that the VAULT lives
    at the install, so `PAZRAS_MEMORY_DIR` is how a worktree or a generated tree
    points at its own. `roots.INSTALL` is the install path the profile names, so
    an installed run acts on the installed vault and the read is right.
    """
    return DEFAULT_ROOT if root is None else pathlib.Path(root)


def guard_write(root: pathlib.Path) -> None:
    """Refuse to write a generated leaf into a vault this tree does not own.

    The default above is right for a READ and ruinous for a WRITE from a
    checkout that is not the install: with `PAZRAS_MEMORY_DIR` unset,
    `roots.INSTALL/memory` is ANOTHER tree's vault, and the run renders the
    register in front of it into that vault's leaf. Measured 2026-10-14 --
    `familiar knowledge glossary` run from the publication worktree with the
    variable unset rewrote `~/06_SYSTEM`'s glossary with this branch's pruned
    register, dropping `memory/journal`, `config/backup` and `config/schedule`
    from a tree that has all three.

    A `--check` from the same place misreports in the mirror image -- it reads
    the install's leaf, compares it against this tree's register, and calls the
    difference drift -- which is why the check now prints the vault it read
    rather than being refused: reading is diagnosable, writing is destructive.
    """
    roots.guard_vault_write(root, "knowledge glossary")


BANNER = ("<!-- GENERATED FILE — do not hand-edit. Rebuild: "
          "`familiar knowledge glossary` -->")

# Where the leaf lands. This path is what creates the `publication` branch's
# first leaf, and with it the 13th subject in `INDEX.md`, the branch router and
# `ontology.corpus()`. Changing it changes which subject is represented.
GLOSSARY_REL = "knowledge/system/publication/glossary.md"


@dataclasses.dataclass
class Problem:
    """Same contract as `knowledge_index.Problem`: this module reports, the
    caller picks the volume."""
    level: str                  # error | warn | note
    what: str
    path: pathlib.Path | None = None


@dataclasses.dataclass
class Plan:
    root: pathlib.Path
    writes: list                # [(path, content)]
    problems: list
    subjects: int = 0

    @property
    def failed(self) -> bool:
        return any(p.level == "error" for p in self.problems)

    @property
    def drift(self) -> list:
        return [p for p, new in self.writes
                if not p.exists() or p.read_text() != new]

    def apply(self) -> list:
        changed = []
        for path, new in self.writes:
            if not path.exists() or path.read_text() != new:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new)
                changed.append(path)
        return changed


# The frontmatter consolidation stage 2 owns: counted off the transcripts,
# not derived from the register (dev/memory/SPECS.md M2a). Rendered from the
# leaf on disk, so a rebuild neither resets a count nor reports it as drift.
COUNTERS = ("use_count", "last_used")


# ── rendering ────────────────────────────────────────────────────────────
def render_glossary(counters: dict | None = None) -> str:
    """The leaf, wholly from the register.

    One row per subject: the id (which IS the folder name, R1e), the mythic
    name, the criteria verbatim, and the places the subject occupies. Nothing
    here is invented -- a name or a criterion this module could not read from
    `ontology.subjects()` would be a register failure, and `ontology selfcheck`
    is where that fails, not this writer.

    `counters` carries `COUNTERS` from the leaf on disk; absent, a new leaf
    starts at zero.
    """
    from knowledge import ontology

    counters = counters or {}
    use_count = counters.get("use_count") or 0
    last_used = counters.get("last_used") or ""

    # Built through `roots`, never spelled: `root-literals` forbids engine code
    # naming a root's directory (R2a), and the register moves with the root.
    register = roots.rel(roots.ONTOLOGY / "subjects.yaml")
    subjects = sorted(ontology.subjects(), key=lambda s: s.id)
    rows = ["| Subject | Name | Falsified when | Occupies |",
            "|---|---|---|---|"]
    for s in subjects:
        crit = " ".join(s.criteria.split())
        places = ", ".join(f"`{p}`" for p in s.places) if s.places else "—"
        rows.append(f"| `{s.id}` | {s.name} | {crit} | {places} |")

    return "\n".join([
        "---",
        "title: Glossary of subjects",
        "summary: The subject ids, their mythic names and their criteria, generated from the register",
        "origin: derived",
        "authority: agent",
        "trust: trial",
        "last_verified: 2026-10-09",
        f"use_count: {use_count}",
        f"last_used: {last_used}".rstrip(),
        "promoted_from:",
        f"source: {register}",
        "supersedes:",
        "related: [knowledge-index, memory-architecture, knowledge-vs-skills]",
        "tags: [glossary, ontology, subjects]",
        "scope: [\"06_SYSTEM/**\"]",
        "area: [A, B]",
        "stability: permanent",
        "verified_log: [2026-10-09]",
        "---",
        "",
        "# Glossary of subjects",
        "",
        BANNER,
        "",
        "Every subject this system declares, with the question that falsifies "
        "it. The register is",
        f"`{register}`; this leaf is one of its readers, so "
        "the two cannot drift.",
        "A subject is a PLACE, not a topic: the id is the folder name where "
        "its leaves live (R1e).",
        "",
        f"{len(subjects)} subjects under `system/`. `areas/` uses A–P "
        "unchanged; the `projects` branch is open.",
        "",
        *rows,
        "",
        "An empty subject is DECLARED, never missing — its folder appears on "
        "its first leaf.",
        "The branch router marks it with a bare name (no trailing slash) for "
        "the same reason.",
        "",
    ])


# ── planning ─────────────────────────────────────────────────────────────
def plan(root: pathlib.Path = None) -> Plan:
    """Decide everything; write nothing."""
    root = resolved_root(root)
    problems: list = []
    kdir = root / "knowledge"
    if not kdir.is_dir():
        return Plan(root=root, writes=[],
                    problems=[Problem("error", f"no knowledge tree at {kdir}", kdir)])

    try:
        from knowledge import ontology
        n = len(ontology.subjects())
    except Exception as exc:                       # noqa: BLE001
        return Plan(root=root, writes=[],
                    problems=[Problem("error",
                                      f"the subject register did not load: {exc}",
                                      kdir)])

    target = root / GLOSSARY_REL
    counters = {}
    if target.exists():
        from knowledge import frontmatter
        fm = frontmatter.read(target)
        counters = {k: fm.get(k) for k in COUNTERS}
    return Plan(root=root, writes=[(target, render_glossary(counters))],
                problems=problems, subjects=n)


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    """Thin adapter over `plan`. Healthcheck depends on these exit codes:
    0 ok · 1 error · 3 `--check` found drift."""
    ap = argparse.ArgumentParser(prog="familiar knowledge glossary")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 3; write nothing")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    p = plan()
    for prob in p.problems:
        if prob.level != "note":
            print(f"!! {prob.what}", file=sys.stderr)
    if p.failed:
        return 1

    if args.check:
        for path in p.drift:
            print(f"DRIFT {path.relative_to(p.root)}")
        # The vault is printed because with PAZRAS_MEMORY_DIR unset it is the
        # INSTALL's, not this checkout's, and a drift report about another
        # tree's leaf reads as a fact about this one.
        print(f"{len(p.drift)} of {len(p.writes)} generated files would change "
              f"in {p.root}")
        return 3 if p.drift else 0

    guard_write(p.root)
    changed = p.apply()
    print(f"knowledge glossary: {p.subjects} subjects → "
          f"{GLOSSARY_REL}")
    print(f"  rewritten: {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
