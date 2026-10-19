#!/usr/bin/env python3
"""vault.py -- the Obsidian vault is `memory/`, and only `memory/`.

WHAT THIS PROVES, AND WHAT IT CANNOT. A graph view shows the files under the
vault root and nothing else, so "the graph shows no `engine/` files" is a claim
about where the root IS. That is what this checks, because it is the part that
can regress silently and the part a person cannot see by opening the app:
`.obsidian/` sits in `memory/`, no other `.obsidian/` exists anywhere in the
repository, and Obsidian's per-machine state files are ignored by git.

It does NOT open Obsidian and look at the graph. Opening an app is not a check,
and a check that needed a GUI would run nowhere. Read the exit like this: the
files the graph is built from are proven to be `memory/`'s.

WHY IT IS A GATE AND NOT A NOTE (R3e, `ontology SPECS`). R1k moved the
vault from the repository root to `memory/` for one stated reason:
`showUnsupportedFiles: true` means a root vault would render `engine/`'s code as
notes. A second vault at `config/` was decided against the same day. Both are
one-line mistakes to make again -- `git mv memory/.obsidian .` does it -- and
neither announces itself: the app opens, shows a graph, and the graph is wrong.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))       # `lib/`, the house idiom
from lib import roots  # noqa: E402

# The vault, and the file that says so. `app.json` rather than the directory:
# an empty `.obsidian/` is not a configured vault, and Obsidian writes this one
# on first open.
APP = roots.MEMORY / ".obsidian" / "app.json"
# Per-machine UI state. Committing it means two machines fight over one file and
# the loser's panels move; the leaf names all four (`knowledge/system/knowledge/
# obsidian-vault.md` §Configuration).
IGNORED = ("workspace.json", "workspace-mobile.json", "plugins/", "graph.json")
GITIGNORE = REPO / ".gitignore"


def findings() -> list[str]:
    out: list[str] = []
    if not APP.is_file():
        out.append(f"{roots.rel(APP)} is missing: the vault root is "
                   f"`{roots.MEMORY_REL}/` and its config has to live there")

    # Every `.obsidian/` in the repository, wherever it is. A root one puts the
    # engine's code in a graph; a `config/` one was decided against (R1k).
    for p in sorted(REPO.glob("**/.obsidian")):
        if p.parent == roots.MEMORY:
            continue
        # The root's own name is read from `lib/roots`, never spelled: this is
        # engine code, and `root-literals` fails on a spelled root for the same
        # reason every other module asks. The message stays precise by naming
        # `roots.ENGINE_REL` instead of the word.
        out.append(f"{roots.rel(p)} is a second vault. The graph shows the "
                   f"files under a vault root, so this one renders whatever "
                   f"sits beside it -- `{roots.ENGINE_REL}/` code, at the "
                   f"repository root")

    if APP.is_file():
        try:
            json.loads(APP.read_text())
        except (OSError, ValueError) as exc:
            out.append(f"{roots.rel(APP)} does not parse ({exc}); Obsidian "
                       f"will rewrite it and the settings the tree depends on "
                       f"are gone")

    text = GITIGNORE.read_text() if GITIGNORE.is_file() else ""
    for name in IGNORED:
        # The path must be ignored AT the vault's location: a rule naming the
        # vault's old home ignores nothing and says so nowhere.
        want = f"{roots.MEMORY_REL}/.obsidian/{name}"
        if not re.search(rf"^{re.escape(want)}$", text, re.M):
            out.append(f"`.gitignore` does not ignore `{want}`: Obsidian's "
                       f"per-machine state would be committed")
    return out


def main() -> int:
    bad = findings()
    for b in bad:
        print(f"vault: {b}", file=sys.stderr)
    if bad:
        return 1
    print(f"vault: the vault root is {roots.MEMORY_REL}/, no second vault "
          f"exists, per-machine state is ignored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
