#!/usr/bin/env python3
"""structure/maps.py — the architecture figures, drawn from what they depict.

WHY. `VISUAL-ARCHITECTURE.md` was a hand-drawn description of the system, kept
true by nobody: it outlived three restructures and was classified `omit` because
its content was this machine's. A figure drawn from the fact it depicts cannot
drift from it, which is the same rule `STRUCTURE.md`'s tables follow — the
registers are the source, the figure is an artifact, and never hand-edit it.

TWO KINDS OF FIGURE, KEPT APART.

  GENERATED — where a register already holds the relation. Import order
  (`checks/import_order.ORDER`), the subjects and their places
  (`config/knowledge/subjects.yaml`), the boundaries and what they compile to
  (`boundaries/compile.targets()`), the schedule (`PAZRAS_TIMERS` in the master
  config), and the pass's stages with their declared invariants
  (`consolidation/run.STAGES`, `stages/invariants.DECLARED`). Written into
  `docs/reference/maps.md` between `BEGIN:`/`END:` markers.

  AUTHORED — only where no register exists. Those live in
  `docs/explanation/architecture.md` and are hand-written, so each node declares
  what it stands for (`%% path: <repo-relative>`) and this module fails on a
  declaration whose path does not exist. A figure about the PARA tree cannot be
  generated — the filing decision has no register — but it can be checked for
  pointing at something real.

Usage:
  maps.py            regenerate the blocks in docs/reference/maps.md
  maps.py --check    exit 3 on drift, 1 on a broken authored declaration
  maps.py --print    write the figures to stdout instead

Every figure carries its source and its limit in the page's prose: a figure with
no stated limit teaches that the system is smaller than it is.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ENGINE = HERE.parent
for extra in (str(ENGINE), str(ENGINE / "boundaries"), str(ENGINE / "checks")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from lib import roots                                    # noqa: E402
from knowledge import ontology                           # noqa: E402
from consolidation import run as c_run                   # noqa: E402
from consolidation.stages import invariants              # noqa: E402
from consolidation.stages.reindex import replace_block   # noqa: E402
import import_order                                      # noqa: E402
import _boundaries                                       # noqa: E402
import compile as b_compile                              # noqa: E402  (engine/boundaries/compile.py)

PAGE = roots.REPO / "docs" / "reference" / "maps.md"
AUTHORED = roots.REPO / "docs" / "explanation" / "architecture.md"

# The five generated blocks, in page order. The tag names the block; the
# function below it writes the body.
BLOCKS = ("maps-import-order", "maps-subjects", "maps-boundaries",
          "maps-schedule", "maps-stages")

DIRS = ("engine", "config", "memory", "docs")


# ── the generated figures ────────────────────────────────────────────────────

def fig_import_order() -> str:
    chain = " --> ".join(import_order.ORDER)
    return "\n".join([
        "```mermaid",
        "flowchart LR",
        f"  {chain}",
        "```",
    ])


def fig_subjects() -> str:
    """Subjects and the top-level directories they occupy.

    Places are edge labels onto the directory they sit in, not nodes of their
    own: 14 subjects own ~40 places, and the answer this figure gives is which
    subject owns which directory, which a 40-node star would bury. The register
    declares subjects and branches as two lists, so there is no branch grouping
    to draw — the branch a leaf is filed under is the path, not a subject
    field."""
    out = ["```mermaid", "flowchart LR"]
    for s in ontology.SUBJECTS.values():
        out.append(f'  {s.id}["{s.name} — {s.id}"]')
    for d in DIRS:
        out.append(f'  dir_{d}["{d}/"]')
    for s in ontology.SUBJECTS.values():
        for place in s.places:
            top = place.split("/")[0]
            if top not in DIRS:
                continue          # a place outside the repository's own dirs
            out.append(f'  {s.id} -->|"{place}"| dir_{top}')
    out.append("```")
    return "\n".join(out)


def fig_boundaries() -> str:
    """Domains to the targets the compiler writes.

    Drawn from the compiler's own target constants, NOT from `targets()`: that
    generator yields the hermes block only when `~/.hermes/memories/MEMORY.md`
    already exists, so a figure taken from it would change with the machine that
    rendered it. The page states that condition instead, and this figure stays
    the same in the instance, in the export, and on a reader's machine."""
    domains = [p.stem for p in _boundaries.sources()]
    if _boundaries.directive_rules():
        domains.append(_boundaries.DIRECTIVE_DOMAIN)
    out = ["```mermaid", "flowchart LR"]
    for path in _boundaries.sources():
        out.append(f'  {_node("src", path.stem)}["{path.name}"]')
    if _boundaries.directive_rules():
        out.append(f'  {_node("src", _boundaries.DIRECTIVE_DOMAIN)}'
                   '["the entity register<br/>one rule per kind marked directive"]')
    targets = [
        (_node("tgt", "merged"), _boundaries.JSON_TARGET),
        (_node("tgt", "pi"), _boundaries.PI_PERMISSION_CONFIG),
        (_node("tgt", "hermes"), _boundaries.HERMES_MEMORY),
    ]
    for node, path in targets:
        out.append(f'  {node}["{_display(path)}"]')
        for d in domains:
            out.append(f'  {_node("src", d)} -->|"compiled"| {node}')
    for d in domains:
        out.append(f'  {_node("tgt", "advisory_" + d)}["{_display(_boundaries.advisory_target(d))}"]')
        out.append(f'  {_node("src", d)} -->|"advisory"| {_node("tgt", "advisory_" + d)}')
    out.append("```")
    return "\n".join(out)


def _node(prefix: str, name: str) -> str:
    """A Mermaid node ID: word characters only.

    A LABEL may carry a hyphen or a dot; an ID may not -- `read-write` as an id
    parses as a subtraction, and the figure renders as nothing."""
    return f"{prefix}_" + re.sub(r"\W+", "_", name)


def _display(path: pathlib.Path) -> str:
    """A target as a reader can check it: under the tree, or `~`-relative.

    NOT `roots.tilde()`: that spells a path inside the repository from the
    INSTALL, and half these targets are harness files under `$HOME`, outside the
    tree by definition."""
    try:
        return path.relative_to(roots.REPO).as_posix()
    except ValueError:
        pass
    try:
        return "~/" + path.relative_to(pathlib.Path.home()).as_posix()
    except ValueError:
        return path.as_posix()


def fig_schedule() -> str:
    """The units, from `PAZRAS_TIMERS` — the table `timers-gen.sh` renders."""
    rows = _timers()
    out = ["```mermaid", "flowchart LR"]
    for name, fields in rows:
        node = _node("u", name)
        out.append(f'  {node}["{name}<br/>{fields.get("desc", "")}"]')
    for name, fields in rows:
        node = "u_" + re.sub(r"\W+", "_", name)
        out.append(f'  {node} -->|"{fields.get("on_calendar", "?")}"| run_{node}'
                   f'["{fields.get("exec", "?")}"]')
    out.append("```")
    return "\n".join(out)


def _timers() -> list[tuple[str, dict]]:
    """`PAZRAS_TIMERS` from the master config in force, or the example.

    Parsed rather than imported: the table is shell, and the two files that may
    carry it are `roots.MASTER_CONFIG` and its `.example.sh` sibling."""
    path = roots.MASTER_CONFIG
    if not path.exists():
        path = path.with_name(path.name.replace(".sh", ".example.sh"))
    text = path.read_text(encoding="utf-8")
    body = text.split("PAZRAS_TIMERS=(", 1)[1].split("\n)", 1)[0]
    rows = []
    for line in body.splitlines():
        m = re.match(r'\s*\["([\w.@-]+)"\]="(.*)"\s*$', line)
        if not m:
            continue
        fields = {}
        for part in m.group(2).split(";"):
            k, _, v = part.partition("=")
            fields[k.strip()] = v.strip()
        rows.append((m.group(1), fields))
    return rows


def fig_stages() -> str:
    """The pass: the stage chain, and each stage's declared invariants."""
    out = ["```mermaid", "flowchart LR"]
    prev = None
    for num, label, _fn in c_run.STAGES:
        decl = invariants.DECLARED.get(label)
        bits = [f"{num} · {label}<br/>shape: {decl.shape}" if decl else f"{num} · {label}"]
        if decl:
            bits.append(f"idem: {decl.idempotent.status} · disj: {decl.disjoint.status}"
                        f" · dir: {decl.directional.status}")
        node = _node("st", label)
        out.append(f'  {node}["{"<br/>".join(bits)}"]')
        if prev is not None:
            out.append(f"  {prev} --> {node}")
        prev = node
    out.append("```")
    return "\n".join(out)


FIGS = {
    "maps-import-order": fig_import_order,
    "maps-subjects": fig_subjects,
    "maps-boundaries": fig_boundaries,
    "maps-schedule": fig_schedule,
    "maps-stages": fig_stages,
}


# ── the authored declarations ────────────────────────────────────────────────

# The value charset is deliberate: it matches a path and nothing else, so the
# prose above these figures can name the convention (`%% path:`) without being
# read as a declaration of one.
DECL = re.compile(r"%%\s*(path|para|withheld):\s*([\w./-]+)")


def declared_findings() -> list[str]:
    """Every `%% path:`/`%% para:` in the authored figures, checked.

    A node that names a path is a claim about the tree, and a claim about the
    tree is checkable. `path:` is repo-relative; `para:` is a PARA folder, which
    lives OUTSIDE the repository by construction, so what is checked there is
    that the master config declares it."""
    if not AUTHORED.exists():
        return [f"{roots.rel(AUTHORED)}: the authored figures are missing"]
    text = AUTHORED.read_text(encoding="utf-8")
    config = roots.MASTER_CONFIG
    if not config.exists():
        config = config.with_name(config.name.replace(".sh", ".example.sh"))
    # The PARA folders are declared in TWO files, and both are searched: the
    # master config's tables carry the internal layout, the profile's storage
    # block carries the mount a folder is reached through (`archive_mount`).
    profile = roots.PROFILE_FILE if roots.PROFILE_FILE.exists() else roots.PROFILE_EXAMPLE
    declared = "\n".join(p.read_text(encoding="utf-8") for p in (config, profile))
    out = []
    for kind, value in DECL.findall(text):
        if kind == "path":
            if not (roots.REPO / value).exists():
                out.append(f"{roots.rel(AUTHORED)}: `%% path: {value}` does not exist")
        elif kind == "withheld":
            # A path this figure stands on and the export does not carry: the
            # session record, the instance's own storage. Checked in the
            # instance, where the claim is about a tree that has it, and
            # skipped in the export, where the page says it does not travel.
            if roots.instance_here() and not (roots.REPO / value).exists():
                out.append(f"{roots.rel(AUTHORED)}: `%% withheld: {value}` does not exist "
                           f"in the instance either")
        elif f'["{value}"]' not in declared and f"{value}/" not in declared:
            out.append(f"{roots.rel(AUTHORED)}: `%% para: {value}` is not declared in "
                       f"{roots.rel(config)} or {roots.rel(profile)}")
    return out


# ── write, check, print ──────────────────────────────────────────────────────

def render_page(text: str) -> tuple[str, list[str]]:
    problems = []
    for tag in BLOCKS:
        body = FIGS[tag]()
        new = replace_block(text, tag, body)
        if new is None:
            problems.append(f"{roots.rel(PAGE)}: no `BEGIN:{tag} (generated)` marker")
            continue
        text = new
    return text, problems


def main() -> int:
    ap = argparse.ArgumentParser(prog="structure/maps.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 3 if the page is stale")
    ap.add_argument("--print", action="store_true", dest="show", help="print the figures")
    args = ap.parse_args()

    if args.show:
        for tag in BLOCKS:
            print(f"── {tag} ──")
            print(FIGS[tag]())
        return 0

    problems = declared_findings()
    for p in problems:
        print(f"  BAD    {p}", file=sys.stderr)

    current = PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""
    desired, marker_problems = render_page(current)
    problems += marker_problems
    for p in marker_problems:
        print(f"  BAD    {p}", file=sys.stderr)

    if current == desired:
        print(f"maps: {len(BLOCKS)} figure(s) in sync with {roots.rel(PAGE)}")
    elif args.check:
        print(f"  STALE  {roots.rel(PAGE)}", file=sys.stderr)
    else:
        PAGE.write_text(desired)
        print(f"maps: wrote {len(BLOCKS)} figure(s) into {roots.rel(PAGE)}")

    if problems:
        return 1
    if args.check and current != desired:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
