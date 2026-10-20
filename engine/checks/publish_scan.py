#!/usr/bin/env python3
"""Scan a GENERATED tree for what should not have left this machine.

WHY IT RUNS ON THE OUTPUT. Every other gate in this registry reads this
repository. The leak scanner reads the tree `engine/publication/publish.py`
wrote -- a clone of the public repository, or an empty directory -- because the
question is not "is this repository clean" (it is not, and must not be: it
holds journals, mail filters, the user's own paths) but "is what we are about
to push clean".

SECOND GATE, NOT THE FIRST. `publish_audit.py` is the primary gate: an
allow-list that fails on a path nobody classified. A clean scan never excuses
an unclassified path -- a scanner only finds the shapes someone thought of,
which is exactly the failure mode the allow-list exists to avoid. The two
answer different questions and neither replaces the other.

PATTERNS, and their two sources:
  * built in here -- the shapes that are wrong in any tree: an email address,
    an IPv4 address, an absolute home path, a private key, a token, a restic
    passphrase assignment.
  * `config/publication/leak-patterns.txt` -- this instance's real names, device
    names and provider names. PRIVATE, never exported (`dev/` is omitted by
    the classification), because a pattern file that names what must not travel
    is itself the thing that must not travel.

DECLARED VERSUS UNDECLARED. The export at P0 ships files whose strings are
this instance's -- addresses P1 templates, device names P5's provider selector
removes, prose P4 rewrites. Publishing them silently would be the wrong
answer; failing on all of them would make the gate useless and teach the
reader to ignore it. So a hit is DECLARED in
`config/publication/leak-exceptions.txt`, with the count observed at declaration
time and the reason, and this scanner fails on:
  * a hit no declaration covers (a new leak);
  * a declared (path, pattern) whose count has GROWN (the declaration is not a
    licence for more);
  * a declaration that no longer hits at all (stale -- the file was templated
    or deleted, and a declaration that has outlived its subject describes a
    tree that no longer exists).
That is the same two-directional rule `declared_paths.py` follows, and the
same reason: a known gap and a new one must not look the same.

Usage:
    python3 engine/checks/publish_scan.py --tree /tmp/fam-clone
    python3 engine/checks/publish_scan.py --tree /tmp/fam-clone --quiet
Exit codes: 0 clean (declared hits are clean) · 1 undeclared or stale · 2 usage.
"""
from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lib import roots  # noqa: E402

PATTERN_FILE = roots.CONFIG / "publication" / "leak-patterns.txt"
EXCEPTION_FILE = roots.CONFIG / "publication" / "leak-exceptions.txt"

# Never scanned: the export writes none of these, and a bytecode cache carries
# the absolute source path in `co_filename` (the survey's 2.4x inflation).
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", "node_modules", ".venv"}

# Names that are a PLACEHOLDER for an account rather than an account. A test
# fixture says `/home/someone`; a real machine says its user's name. The shape
# check cannot tell them apart, so the generic ones are named here and everything
# else stays a hit -- a fixture naming a real stranger is a hit too, and that
# is the correct reading of "an absolute home path in a published tree".
PLACEHOLDER_HOMES = {
    "user", "u", "you", "yourname", "me", "someone", "someuser", "username",
    "example", "test", "tester", "runner", "home", "name", "alice", "bob",
}

# Addresses that cannot disclose anything: the RFC 2606/6761 reserved names,
# and RFC 1918's documentation range is NOT included -- a private network
# address in a published file is a fact about the network it sits on.
RESERVED_MAIL = (
    "example.com", "example.net", "example.org", "localhost",
)
RESERVED_SUFFIX = (".invalid", ".test", ".example", ".local", ".localhost")

# Addresses that are not a host: loopback and the wildcard bind.
NOT_A_HOST = {"127.0.0.1", "0.0.0.0", "255.255.255.255"}

# The shapes that are wrong in ANY tree. Each is `(name, pattern, keep)`; the
# name is what a declaration names, so it is stable and short, and `keep`
# filters the shape's false positives -- the reserved names above.
BUILTIN = (
    # An email address, but not a VCS remote: `git@github.com:owner/repo` is a
    # URL, and every skill's frontmatter carries one. The TLD must be
    # alphabetic, so a `package@1.18.18` version string is not an address.
    ("email", r"(?<![\w.+@-])(?!git@)[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9-]+\.)+"
              r"[A-Za-z]{2,}",
     lambda s: not (s.split("@", 1)[1].lower() in RESERVED_MAIL
                    or s.split("@", 1)[1].lower().endswith(RESERVED_SUFFIX))),
    ("ipv4", r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
             r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}(?![\w.])",
     lambda s: s not in NOT_A_HOST and not s.startswith("127.")),
    ("home-path", r"/(?:home|Users)/[A-Za-z][\w.-]*",
     lambda s: s.rsplit("/", 1)[1].lower() not in PLACEHOLDER_HOMES),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", None),
    ("token", r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"
             r"|(?<![\w-])sk-[A-Za-z0-9-]{20,}"
             r"|AKIA[0-9A-Z]{16}"
             r"|xox[baprs]-[A-Za-z0-9-]{10,}", None),
    ("restic-passphrase", r"(?:RESTIC_PASSWORD|RESTIC_PASS|restic[-_ ]pass"
                          r"(?:phrase|word))\s*[:=]\s*\S+", None),
)


@dataclasses.dataclass(frozen=True)
class Hit:
    path: str
    line: int
    name: str
    text: str


@dataclasses.dataclass(frozen=True)
class Declaration:
    path: str
    name: str
    count: int
    why: str


def spell(path: pathlib.Path) -> str:
    """A path as the reader should see it: repo-relative, or absolute.

    The pattern and exception files can be pointed anywhere (a test's tmp
    directory), and a message that raises `ValueError` on the path it was
    written to report is worse than no message.
    """
    try:
        return path.relative_to(roots.REPO).as_posix()
    except ValueError:
        return str(path)


def _rows(path: pathlib.Path) -> list[list[str]]:
    """Tab-separated rows, `#` comments and blank lines skipped."""
    try:
        text = path.read_text()
    except OSError:
        return []
    out = []
    for raw in text.splitlines():
        line = raw.split("#")[0].rstrip()
        if not line.strip():
            continue
        out.append([c.strip() for c in line.split("\t") if c.strip()])
    return out


def patterns(path: pathlib.Path | None = None) -> list[tuple]:
    """The built-in shapes plus this instance's private ones.

    A private file that cannot be read is a failure, not an empty set: the
    names and devices it lists are the patterns with real disclosure value, and
    a scanner that silently dropped them would report a clean tree it never
    looked at.
    """
    path = PATTERN_FILE if path is None else path
    out = [(name, re.compile(rx), keep) for name, rx, keep in BUILTIN]
    if not path.exists():
        raise SystemExit(f"publish-scan: no pattern file at {spell(path)} "
                         f"-- the instance's own names and device names are the "
                         f"patterns that matter most, and an empty set is not a "
                         f"clean scan")
    for row in _rows(path):
        if len(row) < 2:
            raise SystemExit(f"publish-scan: {spell(path)}: every line is "
                             f"`name<TAB>regex`: {row}")
        out.append((row[0], re.compile(row[1]), None))
    return out


def declarations(path: pathlib.Path | None = None) -> list[Declaration]:
    """`path<TAB>pattern<TAB>count<TAB>reason` -- absent file means none."""
    path = EXCEPTION_FILE if path is None else path
    out = []
    for row in _rows(path):
        if len(row) < 4:
            raise SystemExit(f"publish-scan: {spell(path)}: every line is "
                             f"`path<TAB>pattern<TAB>count<TAB>reason`: {row}")
        out.append(Declaration(row[0], row[1], int(row[2]), row[3]))
    return out


def _text_files(tree: pathlib.Path):
    for p in sorted(tree.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(tree).parts):
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:          # binary: a PNG, a sqlite db
            continue
        try:
            yield p, raw.decode("utf-8")
        except UnicodeDecodeError:
            continue


def scan_texts(pairs, pats: list[tuple] | None = None) -> list[Hit]:
    """The scan itself, over `(path, text)` pairs.

    Separate from `scan()` because the pairs do not have to come from a
    directory: `leak_gate.py` feeds it the blobs of a commit or a push range,
    where the path is the one the repository knows and there is no tree to walk.
    One implementation of "is this a hit", so the two gates cannot disagree.
    """
    pats = patterns() if pats is None else pats
    out = []
    for rel, text in pairs:
        for n, line in enumerate(text.splitlines(), 1):
            for name, rx, keep in pats:
                for m in rx.finditer(line):
                    if keep is not None and not keep(m.group(0)):
                        continue
                    out.append(Hit(rel, n, name, m.group(0)[:60]))
    return out


def scan(tree: pathlib.Path, pats: list[tuple] | None = None) -> list[Hit]:
    pats = patterns() if pats is None else pats
    return scan_texts(((p.relative_to(tree).as_posix(), text)
                       for p, text in _text_files(tree)), pats)


def findings(tree: pathlib.Path, hits: list[Hit], decls: list[Declaration],
             advice: str | None = None) -> tuple[list[str], list[str]]:
    """(problems, notes). Every problem names the file and what to do.

    `advice` replaces the closing sentence, for a caller whose register is not
    this export's (`leak_gate.py` scans a push, where the fix may be a file of
    that repository's own).
    """
    tail = advice or (f"Either it should not travel (fix the classification, or "
                      f"the file's surgery, in "
                      f"{spell(roots.DEV / 'publication' / 'publish.yaml')}) or it is "
                      f"a known residue: declare it in "
                      f"{spell(EXCEPTION_FILE)} with its count and the reason.")
    problems: list[str] = []
    notes: list[str] = []
    counted: dict = {}
    for h in hits:
        counted[(h.path, h.name)] = counted.get((h.path, h.name), 0) + 1
    declared = {(d.path, d.name): d for d in decls}
    for h in hits:
        if (h.path, h.name) not in declared:
            problems.append(
                f"{h.path}:{h.line}: {h.name}: {h.text!r} -- no declaration "
                f"covers this. {tail}")
    for key, d in declarations_by_key(decls).items():
        n = counted.get(key, 0)
        if n == 0:
            problems.append(
                f"{d.path}: declared {d.name} x{d.count}, but nothing in "
                f"{tree} matches -- the declaration outlived its subject "
                f"(templated away, renamed or deleted). Remove it from "
                f"{spell(EXCEPTION_FILE)}, or re-declare what is left.")
        elif n > d.count:
            problems.append(
                f"{d.path}: {d.name} x{n}, declared x{d.count} -- MORE than the "
                f"declaration covers. A declaration is not a licence for the "
                f"next occurrence: fix the new one, or raise the count and say "
                f"why in {spell(EXCEPTION_FILE)}.")
        elif n < d.count:
            notes.append(f"{d.path}: {d.name} x{n}, declared x{d.count} -- "
                         f"lower than declared; lower the count so the "
                         f"declaration stays a measurement.")
        else:
            notes.append(f"{d.path}: {d.name} x{n} (declared) -- {d.why}")
    return problems, notes


def declarations_by_key(decls: list[Declaration]) -> dict:
    return {(d.path, d.name): d for d in decls}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tree", required=True,
                    help="the GENERATED tree to scan, never this repository")
    ap.add_argument("--quiet", action="store_true",
                    help="print the summary line only")
    args = ap.parse_args(argv)

    tree = pathlib.Path(args.tree).expanduser()
    if not tree.is_dir():
        print(f"publish-scan: {tree} is not a directory", file=sys.stderr)
        return 2
    if tree.resolve() == roots.REPO.resolve():
        print("publish-scan: that is this repository, not a generated tree -- "
              "the scanner reads what publish.py wrote, and this tree holds "
              "the journal, the mail filters and the user's own paths on "
              "purpose", file=sys.stderr)
        return 2

    hits = scan(tree)
    problems, notes = findings(tree, hits, declarations())
    files = sum(1 for _ in _text_files(tree))
    if not args.quiet:
        for h in hits:
            print(f"  hit  {h.path}:{h.line}: {h.name}: {h.text!r}")
        for n in notes:
            print(f"  ok   {n}")
    for p in problems:
        print(f"  LEAK {p}")
    print(f"publish scan: {files} file(s), {len(hits)} hit(s), "
          f"{len(notes)} declared, {len(problems)} undeclared or stale "
          f"({len(declarations())} declaration(s))")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
