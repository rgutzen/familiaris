#!/usr/bin/env python3
"""The engine names the user's instance only where the register declares it.

WHY. `engine/` is meant to be publishable as generic code: it changes when we
change what we built, not when one machine's disk is unplugged. The
publication survey (the engine/instance survey (git history), 2026-09-12)
measured what stands in the way, and R1k made the survey's own search a gate.

WHAT IT SEARCHES FOR, and where each part comes from (P2). Three parts, and
only the last is a literal:

  * the IDENTITY -- `identity.name` split into words and `identity.handle`,
    read from the profile through `lib/profile.identity_words`. The spelling is
the profile's; where the profile in force is the shipped example, the words are
placeholders and the identity part is empty, because the example names nobody.
  * the HOME PATH -- `pathlib.Path.home()`. The account the engine happens to
    run as is the one to search for, and no account is written here.
  * the RESIDUE -- the words that are neither identity nor an account: a
    device, a provider, a host. They belong to this machine's vocabulary, not
    to a person, and P5's provider selector retires them (see `RESIDUE`).

Before P2 all eight words were spelled here. The identity ones were
the user's name written into shipped code, in the file whose job is to find
them, and the home path was the account that owns this laptop.

case-sensitive, bytecode caches excluded -- they carry the absolute source path
in `co_filename`, which inflated `engine/**` by 2.4x in the first round.

WARN MODE, DELIBERATELY. Scrubbing is Track P's job, not this track's, so the
findings that exist today are DECLARED in `config/knowledge/violations.yaml`
(the entry whose `surfaced_by` is `instance-refs`) and reported as warnings.
This gate fails on anything NEW, and on a declaration that has gone stale --
the same two rules the violations register already follows, applied to a
measurement instead of a rule.

Usage:  instance_refs.py      exit 1 on anything undeclared
"""
from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lib import profile  # noqa: E402
from lib import roots  # noqa: E402
from knowledge import ontology as O  # noqa: E402

def rel(p):
    import os
    return os.path.relpath(os.path.realpath(p), roots.REPO)


# NOT identity, and not read from the profile: a device, a provider, a host.
# Leaving them here is a decision, not an oversight -- they belong to this
# machine's vocabulary rather than to its owner. Escaped deliberately: this is
# the tail of the regex below, not a list of strings.
#
# `proton` LEFT THIS LIST AT P5, which is what the previous version of this
# comment said would retire it: the provider is no longer named in the engine at
# all. The adapter that names it lives in `config/backup/remotes/`, which does
# not travel, and `engine/backup/` keeps the contract and a template. What
# remains is still this machine's: the archive disk, still named in comments
# the classification substitutes, and the institution leaves. The words
# themselves are below and nowhere else in this file.
RESIDUE = "bigfish|x280|neuroscien"

# Shorter than this is not a search. An unanchored one-character alternative
# matches the inside of every identifier in the tree, so the gate would report
# the tree's length rather than an instance -- and a gate that reports
# everything is a gate the reader learns to ignore. So a name word this short
# goes unsearched: a gap taken knowingly, because the other failure is worse.
MIN_WORD = 3


def identity(p=None) -> list:
    """The profile's identity words, minus the placeholders and the short ones."""
    p = roots.PROFILE if p is None else p
    return [w for w in profile.identity_words(p) if len(w) >= MIN_WORD]


def words(p=None) -> list:
    """The alternatives the pattern is built from, in the order they are read."""
    return ([re.escape(w) for w in identity(p)]
            + [re.escape(str(pathlib.Path.home()))]
            + RESIDUE.split("|"))


def pattern(p=None) -> re.Pattern:
    return re.compile("|".join(words(p)))


PATTERN = pattern()
# Bytecode caches only, exactly as the survey measured: pytest's caches
# carry the absolute source path, which inflated the first round by 2.4x.
# Tests are NOT skipped -- most of the residue IS fixture data that
# replays a real payload, and a measurement that dropped them would
# flatter the tree.
#
# THIS FILE AND ITS TEST ARE THE ONE EXEMPTION, and there is no way around it:
# a search for a set of strings must contain them, and a test for the counting
# must contain a countable payload. Exempt by name, not by shape -- the same
# discipline `declared_paths` uses for its own register.
SELF = (rel(__file__), f"{roots.ENGINE_REL}/checks/tests/test_instance_refs.py")
SKIP = ("__pycache__", ".pytest_cache") + SELF
SURFACE = "instance-refs"


def declared() -> tuple:
    """The files the register declares, or () when nothing is declared yet.

    `surfaced_by` is the register's own field for "which surface reports it",
    and asking for our own name keeps this gate from depending on an id.
    """
    for v in O.violations():
        if v.surfaced_by == SURFACE:
            return tuple(v.paths)
    return ()


def instance_here() -> bool:
    """Whether this checkout IS the instance the register entry measures.

    `dev/` is the marker: the classification omits it from the published tree,
    so a checkout without it is the GENERATED one. That matters here because
    entry 12 is this instance's measurement of its own engine -- the files it
    declares name the install that exported the tree, not the one reading it.
    The declarations are still true of the tree; a reader cannot satisfy them
    and cannot fix them either, so staleness is reported there and not failed.
    A NEW hit still fails in any tree: an account or a device named by generic
    engine code is a finding wherever it is read.

    The definition lives in `lib/roots` because eleven other checks need the
    same answer; this name stays as the local spelling of it.
    """
    return roots.instance_here()


def measure(tree: str = roots.ENGINE_REL) -> dict:
    out = {}
    for f in roots.tracked(tree):
        if any(s in f for s in SKIP):
            continue
        try:
            text = (roots.REPO / f).read_text()
        except (OSError, UnicodeDecodeError):
            continue
        n = len(PATTERN.findall(text))
        if n:
            out[f] = n
    return out


def findings(tree: str = roots.ENGINE_REL):
    """(undeclared files, stale declarations, the full measurement)."""
    found = measure(tree)
    known = declared()
    undeclared = sorted(f for f in found if f not in known)
    stale = sorted(f for f in known if f not in found)
    return undeclared, stale, found


def describe(p=None) -> str:
    """One line saying what this run searched for.

    Printed every time, because the identity part is the whole difference
    between the gate in the instance and the gate in the tree the example
    ships in, and a reader cannot tell those apart from a bare count. An empty
    identity part is a state to be seen, not one to be inferred.
    """
    p = roots.PROFILE if p is None else p
    where = "no profile"
    if p.source is not None:
        try:
            where = roots.rel(p.source)
        except ValueError:               # PAZRAS_PROFILE outside the repo
            where = str(p.source)
    found = identity(p)
    return ("searched: identity "
            + (f"{', '.join(found)} ({where})" if found
               else f"none -- {where} names nobody")
            + f"; home {pathlib.Path.home()}; residue {', '.join(RESIDUE.split('|'))}")


def main(argv) -> int:
    undeclared, stale, found = findings()
    mine = instance_here()
    total = sum(found.values())
    for f in undeclared:
        print(f"NEW   {f}: {found[f]} instance reference(s) -- `{roots.ENGINE_REL}/`"
              f" is generic code; parameterise it, or declare the file in the "
              f"`{SURFACE}` entry of {roots.rel(roots.ONTOLOGY)}/violations.yaml "
              f"with the reason it is instance by nature")
    for f in stale if mine else ():
        print(f"STALE {f}: declared in the `{SURFACE}` entry and no longer "
              f"contains one -- drop it from `paths:`")
    print(describe())
    print(f"instance references: {total} in {len(found)} file(s), "
          f"{len(found) - len(undeclared)} declared, {len(undeclared)} new, "
          f"{len(stale)} stale")
    if stale and not mine:
        print(f"note: no `{roots.DEV_REL}/` here, so the {len(stale)} stale "
              f"declaration(s) are the exporting instance's -- reported, not failed")
    fails = bool(undeclared) or (mine and bool(stale)) or not declared()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
