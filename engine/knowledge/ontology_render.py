"""Renderings of the ontology registers, one function per `familiar knowledge
ontology` view.

WHY HERE, AND NOT IN `cli.py`. Every rendering knows a register's COLUMNS --
which fields a facet prints, which a branch prints. That knowledge belongs
beside the registers, not in the command line that calls them: a field renamed
here changes one file, and `cli.py` keeps only the dispatch and the exit codes
(dev/architecture 4a).

WHY NOT INSIDE `ontology.py`. That module is the registers and the checks, at
1,600 lines; rendering is the one part no harness and no stage imports.
"""
from __future__ import annotations

from knowledge import ontology


def facets() -> list:
    out = [f"{'facet':<10} {'on':<28} {'domain':<52} column"]
    for name, f in zip(ontology.facet_ids(), ontology.facets()):
        dom = "|".join(f.domain) if f.domain else "(open, by design)"
        if len(dom) > 50:
            dom = dom[:47] + "..."
        out.append(f"{name:<10} {','.join(f.on):<28} {dom:<52} {f.column}")
        if f.derived_for or f.declared_for:
            out.append(f"{'':<10} derived: {','.join(f.derived_for) or '-'} · "
                       f"declared: {','.join(f.declared_for) or '-'} · "
                       f"layer: {f.layer} · reviewed: {f.reviewed}")
    return out


def subjects() -> list:
    out = []
    for s in ontology.subjects():
        out.append(f"{s.id:<12} {s.name:<16} {s.leaves} "
                   f"{'leaf' if s.leaves == 1 else 'leaves'}  "
                   f"(reviewed {s.reviewed})")
        out.append(f"{'':<12} {s.criteria}")
    out.append("")
    out.append(f"{len(ontology.subjects())} subjects under system/. "
               "`areas/` uses A-P unchanged; `projects/` is open.")
    return out


def relations() -> list:
    rows = ontology.relation_rows()
    walk = [(i, r) for i, r in rows if r.walkable]
    coin = [(i, r) for i, r in rows if not r.walkable]
    out = [f"walkable ({len(walk)}) -- these are edges:"]
    for i, r in walk:
        out.append(f"  {i:<14} {r.from_} -> {r.to:<22} "
                   f"{r.symmetry:<34} written by {r.writer}")
    out.append(f"coincidences ({len(coin)}) -- never walked, never edges:")
    for i, r in coin:
        out.append(f"  {i:<14} {r.from_} ~ {r.to:<22} {r.symmetry}")
    return out


def branches() -> list:
    out = []
    for name, b in zip(ontology.branch_ids(), ontology.branches()):
        out.append(f"{name + '/':<11} {b.name:<16} falsified when {b.falsified_when}")
        out.append(f"{'':<11} retirement: {b.retirement}")
    for name in ontology.LEGACY_BRANCHES:
        out.append(f"{name + '/':<11} (pre-O2 layout, {ontology.LEGACY_UNTIL})")
    return out


def violations() -> list:
    out = []
    for v in ontology.violations():
        out.append(f"{v.n:>3}  {v.state:<17} {v.what}")
        out.append(f"     → {v.recommendation}")
    out.append("")
    out.append(f"{len(ontology.violations())} entries, read from the module and "
               "not from SPECS.md. An undeclared breach is an error; one of "
               "these warns.")
    return out


VIEWS = {"facets": facets, "subjects": subjects, "relations": relations,
         "branches": branches, "violations": violations}
