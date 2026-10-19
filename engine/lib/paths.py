"""paths.py -- one reading of a glob pattern, shared.

The entity register stores a `pattern:` per kind and more than one module has
to know WHICH DIRECTORY that pattern lives in: `ontology.doc_dirs` walks them
to find every document the registers govern, and `_boundaries.directive_rules`
turns the directive ones into harness `ask` rules. Two readings of
`config/practice/user/*.md` that disagree is a boundary that does not cover
what the register says it does, so the reading lives here, once.

Stdlib only, and no imports from this package: the guard runs on every tool
call and a missing import is a hook that fails open.
"""
from __future__ import annotations


def literal_head(pattern: str) -> str:
    """The directory a pattern starts in: every segment before the first one
    carrying a wildcard.

    `knowledge/**/*.md` -> `knowledge`, `config/practice/user/*.md` ->
    `config/practice/user`, `journal/reports/*.md` -> `journal/reports`.
    A pattern with no wildcard at all is a path, and its head is itself --
    minus a filename, which is not a directory.
    """
    if not pattern:
        return ""
    head: list[str] = []
    for seg in pattern.split("/"):
        if "*" in seg or "?" in seg:
            break
        head.append(seg)
    if len(head) == len(pattern.split("/")) and head and "." in head[-1]:
        head.pop()                      # a literal filename, not a directory
    return "/".join(head)
