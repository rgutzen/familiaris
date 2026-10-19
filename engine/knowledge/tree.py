"""tree -- THE universe: knowledge leaves and skills, as the written record holds them.

One place that knows what counts as a leaf, so no stage re-derives it and
they cannot disagree about the denominator.

THE WALK, NOT THE SCORE. Since R2c (`ontology SPECS`, R1j's order
`lib <- knowledge <- ... <- consolidation`) the scored view -- `ScoredTree`
and `load()` -- lives in `consolidation/ranking.py`, because ranking is the
act of writing, not the record. `documents()` returns UNSCORED documents and
its only caller outside this subject is `ranking.load`; a stage never holds a
Doc outside a ScoredTree (`pass_ctx.tree`).

EXCLUDED, deliberately:
  CONTEXT.md          routers -- derived artifacts, rebuilt by stage 7
  INDEX.md            knowledge/INDEX.md -- likewise derived, rebuilt by stage 7
                      (stages/knowledge_index.py). Scoring it would decay and
                      propose pruning a file regenerated from the very leaves
                      being scored, and it would index itself.
  _leaf-template.md   the template, not a leaf
  journal/**          append-only and unscored by invariant 3
                      (consolidation-cycle.md); episodic memory does not
                      decay here -- the verbatim tier outside git is pruned
"""
from __future__ import annotations

import datetime as dt
import pathlib

from knowledge import frontmatter
from lib import git

SKIP_NAMES = {"CONTEXT.md", "INDEX.md", "_leaf-template.md", "_skill-template.md",
              "_scope-bindings.md", "_subject.md"}


class Doc:
    """One scored document -- a knowledge leaf or a skill."""

    __slots__ = ("path", "rel", "fm", "kind", "name", "created", "scores")

    def __init__(self, path: pathlib.Path, root: pathlib.Path, kind: str):
        self.path = path
        self.rel = path.relative_to(root).as_posix()
        self.fm = frontmatter.read(path)
        self.kind = kind                        # "knowledge" | "skill"
        self.name = (self.fm.get("name") or path.parent.name) if kind == "skill" \
            else path.stem
        self.created: dt.date | None = None
        self.scores: dict = {}

    def get(self, key, default=None):
        return self.fm.get(key, default)

    def __repr__(self):
        return f"<Doc {self.kind} {self.name}>"


def documents(agents_dir: pathlib.Path) -> list[Doc]:
    """Every scorable document, unscored. Called by `ranking.load` alone: the
    only supported way for a stage to hold a Doc is inside a ScoredTree."""
    root = agents_dir
    repo = agents_dir.parent
    docs: list[Doc] = []
    for p in sorted((root / "knowledge").rglob("*.md")):
        if p.name in SKIP_NAMES:
            continue
        docs.append(Doc(p, root, "knowledge"))
    for p in sorted((root / "skills").rglob("SKILL.md")):
        docs.append(Doc(p, root, "skill"))

    first = git.first_added(repo)
    prefix = root.relative_to(repo).as_posix() + "/"
    for d in docs:
        d.created = first.get(prefix + d.rel)
        if d.created is None:
            try:
                d.created = dt.date.fromtimestamp(d.path.stat().st_mtime)
            except OSError:
                pass
    return docs
