#!/usr/bin/env python3
"""No engine code spells a root's name; it asks `lib/roots` (R2a).

WHY. Phases R2 and R3 move every top-level home of this repository
(`ontology SPECS` R1k). A literal `"memory/"` in engine code is a place
that move must find by hand, and a missed one fails when it is used: at 03:30
for the nightly pass, on a fresh machine for bootstrap. `lib/roots.py` and
`lib/roots.sh` declare the roots once; this gate keeps them the only place.

WHAT COUNTS. A string literal in Python -- docstrings excluded, they are prose
-- or a non-comment line of shell, that contains a root's directory name as a
path prefix (`memory/...`, `"$HOME/06_SYSTEM/engine/..."`) or that IS the
name (`REPO / "agents"`). The names are read from roots.py, so after a move
this gate looks for the new spelling without being edited.

WHAT IS EXEMPT, and why each:
  * roots.py, roots.sh -- the declaration itself.
  * checks/declared_paths.py -- the RETIRED register and the policy table,
    whose keys are paths by definition.
  * a constant `declared_paths` holds a POLICY for -- it is read from the AST
    as literals and checked for existence, so a move that misses one already
    fails at pre-commit. Rewriting it through `roots` would blind that gate.
  * tests -- fixture trees are data about a layout, built in a tmp dir.
  * the master config -- configuration, not engine; it leaves the engine in
    R2e, and its `exec=` paths are checked by `declared_paths`.
  * generated files -- fix the generator, not the output.
  * a line carrying `# not-a-root: <reason>` -- a word that only looks like a
    root (pi's own `memory/` directory, a register's vocabulary). The reason
    is mandatory, so the exemption is a decision on the record.

Usage:  root_literals.py [--list]     exit 1 on any finding
"""
from __future__ import annotations

import ast
import io
import pathlib
import re
import sys
import tokenize

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lib import roots  # noqa: E402
import declared_paths  # noqa: E402

EXEMPT = (
    roots.rel(roots.LIB / "roots.py"),
    roots.rel(roots.LIB / "roots.sh"),
    roots.rel(HERE / "declared_paths.py"),
    roots.rel(roots.MASTER_CONFIG),
)
EXEMPT_PARTS = ("tests", "generated", "__pycache__")


def _pattern() -> re.Pattern:
    names = "|".join(re.escape(n) for n in sorted(
        {roots.ENGINE_REL, roots.MEMORY_REL, roots.CONFIG_REL, roots.DEV_REL}
        - {roots.DEV_REL}))
    # `dev/` is not a root this gate polices: nothing in the engine opens it
    # except ontology's document walk, and it does not move.
    # A root name as a path segment: followed by `/`, or ending the string
    # (`"~/06_SYSTEM/memory"`). Not preceded by a word character, so
    # `subagents/` and `~/.pi/agent/agents/`'s neighbours are not read as roots.
    return re.compile(rf"(?<![\w.-])(?:{names})/|(?:^|(?<=/))(?:{names})$")


MARK = re.compile(r"#\s*not-a-root:\s*\S")

# A BARE `"config"` is a finding only on a path-shaped line. The word is also
# an ordinary verb name (`familiar structure config`) and a front-door subject,
# and the bare-name form exists to catch `REPO / "agents"` -- a root used as
# a path component. A `<root>/...` prefix is a finding wherever it appears.
PATHISH_LINE = re.compile(r"/|REPO|roots\.|HERE|ENGINE|INSTALL|os\.path|"
                          r"pathlib|\.parent|Path\(")


def _is_finding(pat: re.Pattern, body: str, line: str) -> bool:
    if not pat.search(body):
        return False
    if "/" in body:
        return True
    return bool(PATHISH_LINE.search(line))


# A JS/TS harness plugin cannot import roots.py, so it declares the one root it
# needs on a line tagged `// roots-twin: NAME`. test_roots.py asserts each such
# value equals roots.NAME; this gate accepts the tagged line and nothing else.
TWIN = re.compile(r"//\s*roots-twin:\s*[A-Z_]+")


def _python(path: pathlib.Path, pat: re.Pattern):
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(path.read_text()).readline))
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):
        return
    # Since Python 3.12 an f-string is not one STRING token but START, MIDDLE*,
    # END, with the literal text in the MIDDLEs. Reading STRING alone missed
    # every f-string -- among them `checks.py`'s `f"engine/**/{pattern}"`,
    # the glob `--audit` walks, which would have matched nothing after R2c
    # and passed silently.
    middles = {getattr(tokenize, n) for n in ("FSTRING_MIDDLE", "TSTRING_MIDDLE")
               if hasattr(tokenize, n)}
    prev = None
    for t in toks:
        if t.type in middles:
            if _is_finding(pat, t.string, t.line) and not MARK.search(t.line):
                yield t.start[0], t.string.strip()[:80]
        elif t.type == tokenize.STRING:
            # A string that is a statement on its own is a docstring: prose.
            standalone = prev is None or prev.type in (
                tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.NL)
            body = t.string.lstrip("rbfuRBFU").strip("'\"")
            if not (standalone and t.string.lstrip("rbfuRBFU")[:3] in ('"""', "'''")) \
                    and _is_finding(pat, body, t.line) and not MARK.search(t.line):
                yield t.start[0], body.strip()[:80]
        if t.type not in (tokenize.COMMENT, tokenize.NL):
            prev = t


def _shell(path: pathlib.Path, pat: re.Pattern):
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if line.lstrip().startswith("#") or MARK.search(line):
            continue
        code = re.split(r"\s#", line, maxsplit=1)[0]
        if any(pat.search(w) for w in re.split(r"[\s\"'`;()]+", code) if "/" in w):
            yield n, code.strip()[:80]


def _policed() -> dict[str, set[int]]:
    """The lines of every constant `declared_paths` holds a policy for."""
    out: dict[str, set[int]] = {}
    for key in declared_paths.POLICIES:
        f, _, const = key.partition(":")
        try:
            tree = ast.parse((roots.REPO / f).read_text())
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else \
                [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == const for t in targets):
                out.setdefault(f, set()).update(
                    range(node.lineno, node.end_lineno + 1))
    return out


def _script(path: pathlib.Path, pat: re.Pattern):
    for n, line in enumerate(path.read_text().splitlines(), 1):
        s = line.lstrip()
        if s.startswith(("//", "*", "/*")) or TWIN.search(line) \
                or re.search(r"//\s*not-a-root:\s*\S", line):
            continue
        for lit in re.findall(r"([\"'`])((?:(?!\1).)*)\1", line):
            if pat.search(lit[1]):
                yield n, s[:80]
                break


def findings():
    pat = _pattern()
    policed = _policed()
    for f in roots.tracked(roots.ENGINE_REL):
        p = roots.REPO / f
        if f in EXEMPT or set(pathlib.PurePosixPath(f).parts) & set(EXEMPT_PARTS) \
                or p.name.startswith(("test_", "test-")) or p.is_symlink() or not p.is_file():
            continue
        if p.suffix in (".js", ".mjs", ".ts"):
            gen = _script(p, pat)
        elif p.suffix == ".py":
            gen = _python(p, pat)
        elif p.suffix == ".sh" or (p.suffix == "" and p.read_bytes()[:2] == b"#!"):
            first = p.read_text(errors="replace").split("\n", 1)[0]
            gen = _python(p, pat) if "python" in first else _shell(p, pat)
        else:
            continue
        for n, text in gen:
            if n not in policed.get(f, ()):
                yield f, n, text


def main(argv) -> int:
    found = list(findings())
    for f, n, text in found:
        print(f"{f}:{n}: {text}")
    print(f"root literals: {len(found)} finding(s) in engine code "
          f"(declare roots in {roots.rel(roots.LIB)}/roots.py)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
