#!/usr/bin/env python3
"""The dependency order between the engine's code packages holds (R1j).

    lib <- knowledge <- harness <- context <- consolidation <- cli

A package may import itself and anything to its LEFT, never to its right. The
order is what made R2c's split possible: before it, `engine/consolidation/` held
two cycles (knowledge <-> consolidation, context <-> consolidation), and a
package that can import anything grows them back. Measured with `ast` over
every import statement, including ones inside functions -- a lazy import is
still a dependency, only a later one.

Tests are not checked: a test exercises its package from outside, and may
need a fixture from anywhere.

Usage:  import_order.py        exit 1 on any import against the order
"""
from __future__ import annotations

import ast
import pathlib
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[1]
ORDER = ("lib", "knowledge", "harness", "context", "consolidation", "cli")


def findings(engine: pathlib.Path = ENGINE) -> list[str]:
    out = []
    for rank, pkg in enumerate(ORDER):
        for f in sorted((engine / pkg).rglob("*.py")):
            rel = f.relative_to(engine)
            if "tests" in rel.parts or "__pycache__" in rel.parts:
                continue
            tree = ast.parse(f.read_text(), str(rel))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    names = [node.module]
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    if top in ORDER and ORDER.index(top) > rank:
                        out.append(f"{rel}:{node.lineno}: {pkg} imports {name}, "
                                   f"which sits to its right in "
                                   f"{' <- '.join(ORDER)}")
    return out


def main() -> int:
    found = findings()
    for line in found:
        print(line)
    print(f"import order: {len(found)} import(s) against {' <- '.join(ORDER)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
