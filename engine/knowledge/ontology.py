
"""ontology -- the classes this system already has, stated so a check can read them.

THE PREMISE THIS REMOVES. The knowledge tree has always had an ontology: the
classes are the branch structure plus the frontmatter contract
(`memory/knowledge/_leaf-template.md`), and the graph is the edge keys of that
same frontmatter. None of it was STATED, so it was stated in three places that
disagreed -- the folder layout, the frontmatter contract, and two edge resolvers
whose world was smaller than both. This module is the one statement. It stores
nothing: markdown stays truth (`memory/knowledge/system/knowledge/memory-architecture.md`
§Governing rule), and nothing here parses a document to learn a class.

THE RULE THAT GOVERNS EVERY REGISTER.

    Every classifier here answers one question: what change reaches this?

  * ENTITIES  -- who may WRITE it. Validated (a frontmatter contract) or declared
                 (resolvable only, so an edge may point at it).
  * FACETS    -- what makes it FALSE. The frontmatter fields whose values are
                 claims about the world.
  * RELATIONS -- what it POINTS AT. The walkable edges, and the coincidences that
                 are retrieval priors and never edges.

One cut runs across all three identically -- ASSERTION (a claim, checkable,
actionable) vs COINCIDENCE (a prior, never actionable). A new field must declare
which cell it occupies; that governance rule exists because its absence produced
a measured defect: a draft vocabulary put cross-cutting CONCEPTS into the
exclusive CATEGORY register and was 37% ambiguous (`ontology PLAN` §The
cognitive layering).

WHAT IS NOT HERE. No store, no OWL, no SKOS, no triple store, no reasoner -- all
already rejected in `meta/prior-art-memory-systems.md` §Why the recurring
rejections. No compile step and no generated intermediate: boundaries compiles
YAML to JSON only because its reader is a guard hook that cannot import a parser
mid-session, and every consumer of this module is Python and imports the loader.
The only things that read the tree are the checks at the bottom, which REPORT.
Nothing here is auto-repaired: the pass reports and the human ratifies, the same
rule `associate.py` states for a dangling `related:` name ("a REPORT LINE, not a
deletion").

CONTENT IN YAML, BINDING IN PYTHON -- corrected 2026-09-30, before any code
(`ontology PLAN` §4). This module holds the BINDING: which key sits on
which entity, what a domain means, how a reference resolves. The CONTENT --
entities, facets, subjects, branches, relations, the naming rules and the
violations register -- lives in `config/knowledge/*.yaml`, one file per register,
DIRECTIVE. The split is this file's own governing rule applied to itself:
content changes when the USER ratifies a vocabulary change, binding changes when
the CODE changes.

The earlier draft put both in Python, argued from "stdlib-only" and "comments
beside values". Both arguments were weaker than presented: `_miniyaml` gives
YAML with no import at all, and the decisive reason for a file is that A TYPO IN
A PYTHON DICT CAN IMPORT SUCCESSFULLY AND MEAN SOMETHING DIFFERENT, in a module
an unattended 03:30 job imports. A config file refuses to load and names the
line. `_miniyaml` is promoted to `engine/lib/` for its second caller
(`generated_block.py`'s precedent) and is NOT extended: these files are
constrained to the subset it already reads, and a test asserts that.

THE VIOLATIONS REGISTER IS PRESCRIPTIVE. It carries every known breach, with a
recommendation and a state, so that A KNOWN GAP AND A NEW ONE DO NOT LOOK THE
SAME: an entry declared there warns and the build stays green; a value nobody
declared fails. That is the whole point of the register and the reason it is
data rather than prose in a checklist.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import fnmatch
import os
import pathlib
import re
import subprocess
import sys
import types

from knowledge import frontmatter
from knowledge.tree import SKIP_NAMES

# `_miniyaml` is shared with `engine/boundaries/compile.py`, and lives
# in `engine/lib/` because a second caller is what triggers an extraction in
# this repo (`generated_block.py`, 2026-09-05). The package's `__init__` puts
# `lib/` on the path, so no importer of this module can reach it without.
from lib import _miniyaml  # noqa: E402
from lib import paths, roots  # noqa: E402

REPO = roots.REPO
AGENTS = roots.MEMORY
M = roots.MEMORY_REL

# The register's word for "relative to the memory root", as `entities.yaml`
# spells it in `root:`. A vocabulary value, not a path: it is renamed with the
# register in R3b, and `roots` says where it points.
ROOT_MEMORY = "memory"  # not-a-root: the entities.yaml `root:` vocabulary
PROJECTS = pathlib.Path.home() / "01_PROJECTS"

# The date the whole register was ratified. Every entry repeats it rather than
# inheriting it, because `reviewed:` is per-entry by design: a subject whose
# criteria change next month must be able to say so without touching the rest
# (`ontology SPECS` O1m).
REVIEWED = "2026-09-30"

# A definition nobody has re-read in this long is a signal, not a broken build
# -- the healthcheck warns and exits 0 (SPECS.md O1m).
CADENCE_DAYS = 180

LAYERS = ("category", "concept", "association")
COLUMNS = ("assertion", "coincidence")

# `directive` is the write-authority predicate the dead guard in
# `associate.py` was reaching for: a document an agent may never edit. Asked of
# the ENTITY TYPE, so it cannot rot the way a hardcoded path prefix did.
STATE_OPEN = "open"
STATE_RATIFIED = "ratified"
STATE_EXCEPTION = "accepted-exception"
STATES = (STATE_OPEN, STATE_RATIFIED, STATE_EXCEPTION)


class Inconsistent(ValueError):
    """A register contradicts itself. `selfcheck()` raises rather than warns."""


# ── the entry shapes ─────────────────────────────────────────────────────────
# Frozen dataclasses and frozen mappings: a register is data declared once, and
# an accidental write to it would make the schema the thing that drifts.


@dataclasses.dataclass(frozen=True)
class Entity:
    criteria: str
    layer: str
    column: str
    validated: bool          # carries a frontmatter contract -> may be scored
    directive: bool          # the user owns it: agents propose, never edit
    pattern: str = ""        # glob, matched against `root`
    root: str = ROOT_MEMORY  # which tree the pattern is relative to
    id_rule: str = ""        # what the identifier is
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Facet:
    criteria: str
    on: tuple                # entity ids that carry it
    domain: tuple            # allowed values; () = open, by design
    where: str               # frontmatter | path
    layer: str
    column: str
    derived_for: tuple = ()  # entity ids whose value is computed from the path
    declared_for: tuple = ()  # entity ids whose value is written in frontmatter
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Subject:
    id: str
    name: str                # the display name, declared in config/knowledge/subjects.yaml
    criteria: str            # falsified when...
    leaves: int              # measured 2026-09-30; O2b ratifies by moving
    places: tuple = ()       # the directories this subject OCCUPIES (R1g)
    layer: str = "category"
    column: str = "assertion"
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Unmapped:
    """A directory no subject occupies, and why forcing one would be wrong."""
    id: str                  # the place itself, repo-relative
    reason: str
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Branch:
    criteria: str
    name: str
    falsified_when: str
    retirement: str
    layer: str = "category"
    column: str = "assertion"
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Relation:
    criteria: str
    from_: str               # entity ids, or "any"
    to: str
    symmetry: str
    writer: str
    column: str
    walkable: bool
    layer: str = "association"
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class NamingRule:
    id: int
    criteria: str
    checkable: bool
    layer: str = "category"
    column: str = "assertion"
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Violation:
    n: int
    criteria: str            # what the entry says, and why it is one
    what: str
    recommendation: str
    state: str
    surfaced_by: str         # naming | check | none -- which surface reports it
    layer: str = "category"
    column: str = "assertion"
    paths: tuple = ()        # the files the mechanical findings name
    rules: tuple = ()        # NAMING rule ids the file breaks
    facet: str = ""          # the facet whose value is out of domain
    value: str = ""          # the offending value
    edge: str = ""           # the relation key whose endpoint does not resolve
    reviewed: str = REVIEWED


@dataclasses.dataclass(frozen=True)
class Finding:
    """One thing a check noticed. `violation` is the register entry that
    declares it -- 0 means NOBODY declared it, which is an error, not a warning."""
    level: str               # warn | error
    code: str
    where: str
    detail: str
    violation: int = 0

    def line(self) -> str:
        tag = f" (violation {self.violation})" if self.violation else ""
        return f"{self.level}  {self.code:<16} {self.where}: {self.detail}{tag}"


def _frozen(mapping: dict) -> types.MappingProxyType:
    """A register that cannot be edited at run time. Written as a call rather
    than a literal dict, deliberately: this module holds the declared paths, and
    a module-level literal of path-shaped strings is exactly what
    `engine/checks/declared_paths.py` exists to make somebody declare."""
    return types.MappingProxyType(dict(mapping))


# ── ENTITIES: who may write it ───────────────────────────────────────────────
#
# ORDER IS DERIVED, NOT DECLARED. Two patterns overlap -- `journal/reports/*.md`
# is inside `journal/**/*.md` -- so matching walks the register by SPECIFICITY
# (fewest `**`, then fewest `*`) rather than by the order the entries happen to
# be written in. A schema whose meaning depends on dict insertion order is a
# schema that breaks the first time somebody sorts it.

# ── the loader: content in, registers out ───────────────────────────────────
#
# ONE ARTIFACT, TWO READERS. The CONTENT is `config/knowledge/*.yaml` --
# directive, ratified, changing when the user ratifies a vocabulary change.
# This module holds the BINDING: which key sits on which entity, what the domains
# mean, and the resolution rules. The split is the register's own governing rule
# applied to itself -- content and binding change for different reasons
# (`ontology PLAN` §4).
#
# WHY YAML AND NOT PYTHON. A typo in a Python dict can import successfully and
# MEAN SOMETHING DIFFERENT, in a module an unattended 03:30 job imports. A config
# file refuses to load and names the line. And read by WHICH parser matters:
# PyYAML is absent under `~/.local/share/mise/shims/python3`, the interpreter
# `familiar-memory.timer` runs under, so `engine/lib/_miniyaml.py` -- 4 KB, no
# import that can go missing -- reads it instead. The parser is NOT extended for
# these files; they are constrained to its subset and a test asserts that.

ONTOLOGY_DIR = pathlib.Path(os.environ.get(
    "PAZRAS_ONTOLOGY_DIR", str(roots.ONTOLOGY)))

# The one place each register's file and its top-level key are named.
FILES = _frozen({
    "ENTITIES": ("entities", "entities"),
    "FACETS": ("facets", "facets"),
    "SUBJECTS": ("subjects", "subjects"),
    "BRANCHES": ("subjects", "branches"),
    "RELATIONS": ("relations", "relations"),
    "NAMING": ("naming", "naming"),
    "VIOLATIONS": ("violations", "violations"),
    "UNMAPPED": ("subjects", "unmapped"),
})

# Which YAML keys are tuples, and of what. Spelled once rather than reasoned
# about per call site: `_miniyaml` returns every scalar as a string, so "6" and
# "true" arrive as text and something has to say what they are.
TUPLE_FIELDS = ("on", "domain", "derived_for", "declared_for", "paths", "rules",
                "places")
BOOL_FIELDS = ("validated", "directive", "walkable", "checkable")
INT_FIELDS = ("leaves", "n", "rules")


def read_register(path: pathlib.Path) -> dict:
    """One YAML file, parsed by `_miniyaml`. A parse error carries its line."""
    return _miniyaml.load(pathlib.Path(path).read_text())


def _coerce(cls, raw: dict, where: str, key: str = "id"):
    """A YAML mapping -> one register entry, with an UNKNOWN KEY refused.

    The refusal is the point of having a loader: a key that is misspelled in a
    config file would otherwise be silently ignored, and the entry would then
    mean something other than it looks like.
    """
    fields = {f.name for f in dataclasses.fields(cls)}
    got = dict(raw)
    if cls is Violation:
        got["n"] = got.pop("id")
    elif cls is NamingRule:
        got["id"] = int(got["id"])     # a rule is numbered, not named
    elif "id" not in fields:
        got.pop("id", None)
    if "from" in got:                      # `from` is a Python keyword
        got["from_"] = got.pop("from")
    unknown = set(got) - fields
    if unknown:
        raise Inconsistent(f"{where}: unknown key(s) {sorted(unknown)}; "
                           f"{cls.__name__} takes {sorted(fields)}")
    out = {}
    for name, value in got.items():
        if name in TUPLE_FIELDS:
            value = tuple(value or ())
            if name == "rules":
                value = tuple(int(x) for x in value)
        elif name == "domain" and value is None:
            value = ()
        elif name in BOOL_FIELDS:
            value = (value == "true") if isinstance(value, str) else bool(value)
        elif name in INT_FIELDS and isinstance(value, str):
            value = int(value)
        out[name] = value
    missing = {f.name for f in dataclasses.fields(cls)
               if f.default is dataclasses.MISSING and f.name not in out}
    if missing:
        raise Inconsistent(f"{where}: no {sorted(missing)}")
    return cls(**out)


def _load(directory=None) -> dict:
    """Every register, from `config/knowledge/`. Raises Inconsistent on drift."""
    d = pathlib.Path(directory or ONTOLOGY_DIR)
    out: dict = {name: {} for name in FILES}
    for name, (stem, key) in FILES.items():
        path = d / f"{stem}.yaml"
        try:
            data = read_register(path)
        except OSError as exc:
            raise Inconsistent(f"{path}: {exc}") from None
        except _miniyaml.YamlError as exc:
            raise Inconsistent(f"{path}: {exc}") from None
        rows = data.get(key)
        if not rows:
            raise Inconsistent(f"{path}: no `{key}:` section")
        cls = {"ENTITIES": Entity, "FACETS": Facet, "SUBJECTS": Subject,
               "BRANCHES": Branch, "RELATIONS": Relation,
               "NAMING": NamingRule, "VIOLATIONS": Violation,
               "UNMAPPED": Unmapped}[name]
        for row in rows:
            ident = row.get("id")
            if ident is None:
                raise Inconsistent(f"{path}: an entry under `{key}:` has no id")
            if name == "VIOLATIONS":
                row = dict(row, n=ident)
            key = int(ident) if name in ("NAMING", "VIOLATIONS") else ident
            out[name][key] = _coerce(cls, row, f"{path}:{key}:{ident}")
    return out


_REG = _load()
ENTITIES = _frozen(_REG["ENTITIES"])
FACETS = _frozen(_REG["FACETS"])
SUBJECTS = _frozen(_REG["SUBJECTS"])
BRANCHES = _frozen(_REG["BRANCHES"])
RELATIONS = _frozen(_REG["RELATIONS"])
NAMING = tuple(_REG["NAMING"][i] for i in sorted(_REG["NAMING"]))
VIOLATIONS = tuple(_REG["VIOLATIONS"][i] for i in sorted(_REG["VIOLATIONS"]))
UNMAPPED = _frozen(_REG["UNMAPPED"])

# A router asked to triage more than this many rows is reported, citing
# violation 10. The number is the tree's own (`knowledge/CONTEXT.md`: "roughly
# 12 leaves, or when its rows stop sharing a single question").
#
# THE ROW, NOT THE BRANCH. The rule asks how many rows ONE ROUTER has to
# triage, so the unit is the directory whose `CONTEXT.md` lists them -- for
# `system/` that is each subject, because `system/CONTEXT.md` lists thirteen
# subjects and the subject routers below it list the leaves. Measured by branch
# instead, `system/` reported 33 leaves against a router that never sees them.
# Same reading fixes `areas/<A>/`, which the branch-level count left unmeasured
# while warning about `system/`.
BRANCH_MAX = 12

# The pre-O2 layout, declared rather than merely tolerated. Before O2b moves the
# 31 leaves, every document sits under one of these; a document under a
# branch that is NEITHER declared here NOR in BRANCHES is an error, not a
# warning. That is the same "a known gap and a new one must not look the same"
# rule the violations register follows, applied to the transition itself.
LEGACY_BRANCHES = ("meta", "operations", "tools")
LEGACY_UNTIL = "O2b moves the 31 leaves into system/<subject>/"


def reload(directory=None) -> None:
    """Re-read the content files. For a test that wants to see them change."""
    global ENTITIES, FACETS, SUBJECTS, BRANCHES, RELATIONS, NAMING, VIOLATIONS
    global UNMAPPED
    _REG.update(_load(directory))
    ENTITIES = _frozen(_REG["ENTITIES"])
    FACETS = _frozen(_REG["FACETS"])
    SUBJECTS = _frozen(_REG["SUBJECTS"])
    BRANCHES = _frozen(_REG["BRANCHES"])
    RELATIONS = _frozen(_REG["RELATIONS"])
    NAMING = tuple(_REG["NAMING"][i] for i in sorted(_REG["NAMING"]))
    VIOLATIONS = tuple(_REG["VIOLATIONS"][i] for i in sorted(_REG["VIOLATIONS"]))
    UNMAPPED = _frozen(_REG["UNMAPPED"])
    _INDEX.clear()
    _PLACES.clear()
    SUBJECT_CRITERIA.clear()
    SUBJECT_CRITERIA.update({s.id: _criterion(s) for s in SUBJECTS.values()})
    ENTRY_SUBJECT_CRITERIA.clear()
    ENTRY_SUBJECT_CRITERIA.update(SUBJECT_CRITERIA)
    ENTRY_SUBJECT_CRITERIA["areas"] = ENTRY_AREAS_CRITERION


ENTRY_AREAS_CRITERION = (
    "Subject knowledge for one P.A.Z.R.A.S Area (A-P) rather than something "
    "about this system. Choosing this opens the Area question; it is not a "
    "subject of its own.")




# ── the criteria maps a `choice` question needs ──────────────────────────────
#
# ONE ARTIFACT, TWO READERS. `jev_schemas.py` builds its labelling questions
# from these maps by REFERENCE, and a test asserts identity (`is`), not equality:
# a copy that happens to match today is exactly the drift this track exists to
# prevent (`ontology SPECS` O1n, `dev/jev/SPECS.md` item 2c).
#
# They are plain dicts, not MappingProxyType: `schema_hash` JSON-serialises the
# question object, and a proxy is not serialisable.

def _criterion(s: Subject) -> str:
    """One subject as a labelling question sees it: its criteria, then its place.

    THE PLACE IS PART OF THE QUESTION. Both instructions tell the model that
    each subject "names a PLACE IN THE SYSTEM you could point at", and until
    2026-10-02 the map carried the criteria text alone, so the place was
    promised and never shown (`ontology SPECS` O4d). The `name` is NOT
    sent: it is a mnemonic ("the Grimoire"), and a metaphor gives a classifier
    a second, looser thing to match against. Composed here rather than in
    `jev_schemas`, so the identity rule still holds: the question's map IS
    this one.
    """
    text = " ".join(s.criteria.split())
    if not s.places:
        return text
    where = ", ".join(f"`{p}/`" for p in s.places)
    return f"{text} {'Place' if len(s.places) == 1 else 'Places'}: {where}."


SUBJECT_CRITERIA = {s.id: _criterion(s) for s in SUBJECTS.values()}

# `entry-subject` is the same subjects plus `areas` as a TERMINAL: a journal
# entry that is subject knowledge rather than something about this system opens
# the second question, over A-P.
ENTRY_SUBJECT_CRITERIA = dict(SUBJECT_CRITERIA, areas=ENTRY_AREAS_CRITERION)

# The Areas, read from the profile rather than declared again here. The Area
# vocabulary is deliberately personal and non-universal, and the profile is its
# single source (P1; before it, the master config); a second copy in this
# module would be the drift this schema exists to prevent, one register along.
AREA_CRITERIA = {}


def _area_criteria() -> dict:
    """`{code: "Name -- description"}` for each Area in the profile.

    Read, never copied: `config/profile.yaml` (or the example a fresh clone
    runs on) is the one source of the Area vocabulary, and `familiar structure
    validate` checks it for duplicate codes. `roots.PROFILE` has already parsed
    it; a profile that did not parse yields no Areas, which `check` reports.
    """
    out = {}
    for name, fields in sorted(roots.PROFILE.areas.items()):
        label = name.split("_", 1)[1] if "_" in name else name
        out[fields["code"]] = f"{label} -- {fields['description']}"
    return out


AREA_CRITERIA.update(_area_criteria())     # filled in place, same object


def criteria(name: str) -> dict:
    """The `criteria` map for one labelling question. Identity-stable.

    Returns the SAME object on every call, which is what lets `jev_schemas`
    assert `is` rather than `==`. An unknown name raises: an undeclared question
    is an error, not a default.
    """
    if name == "subject":
        return SUBJECT_CRITERIA
    if name == "entry-subject":
        return ENTRY_SUBJECT_CRITERIA
    if name == "area":
        return AREA_CRITERIA
    raise Inconsistent(
        f"no criteria map for {name!r}. Known: subject, entry-subject, area.")


# ── accessors ────────────────────────────────────────────────────────────────
# Each answers a question a caller actually asks, so a caller never iterates a
# register to answer one it has to re-derive.

def subjects() -> tuple:
    """The subjects, in declaration order."""
    return tuple(SUBJECTS.values())


def facets() -> tuple:
    """The ten, in declaration order."""
    return tuple(FACETS.values())


def relations() -> tuple:
    """`(walkable, coincidences)` -- the two registers separately.

    Returned apart rather than filtered by the caller, because "an edge I may
    walk" and "a prior I may rank with" are different questions and the register
    is where the answer is decided.
    """
    walk = tuple(r for r in RELATIONS.values() if r.walkable)
    coin = tuple(r for r in RELATIONS.values() if not r.walkable)
    return walk, coin


def branches() -> tuple:
    return tuple(BRANCHES.values())


def places(subject_id: str) -> tuple:
    """The directories a subject OCCUPIES, or () for an unknown id.

    The place is what makes a filing judgement decidable rather than a matter
    of taste: `system/pass/` describes the code in `engine/consolidation/`, so a
    leaf's subject can be checked against where the thing it describes lives
    (`ontology SPECS` O2c). Since R1g every top-level directory has
    one owner or a declared reason for having none (`places_findings`), so
    a subject with no places -- `publication` -- is one with nothing built yet.
    """
    s = SUBJECTS.get(subject_id)
    return s.places if s else ()


def naming() -> tuple:
    return tuple(NAMING)


def violations() -> tuple:
    return tuple(VIOLATIONS)


def directive_types() -> tuple:
    """Entity ids an agent may never write. Asked of the register, so the
    `associate.py` guard cannot rot the way a hardcoded path prefix did, and
    so the boundary compiler derives the harness `ask` rules from the same
    answer (R1m, R3c)."""
    return tuple(k for k, e in ENTITIES.items() if e.directive)


def is_directive(rel: str) -> bool:
    """Is this document one an agent may never write? Asked by PATH, of the
    register -- the predicate `associate._is_conventions` was reaching for."""
    etype = _type_of(rel)
    return bool(etype) and ENTITIES[etype].directive


def directive_dirs() -> tuple:
    """The DIRECTORIES the register calls directive, repo-relative and with a
    trailing slash, which is the form a prefix test reads as one.

    Sorted and de-duplicated: two kinds can share a directory, and a prefix
    matched twice is a finding reported twice. `posture`'s property 4 is the
    first caller -- it matched a hardcoded tuple until R3d, and a tuple is a
    second register that cannot know a kind was added, moved or unmarked.
    """
    out = set()
    for e in ENTITIES.values():
        if not e.directive:
            continue
        head = paths.literal_head(e.pattern)
        if not head:
            continue
        rel = f"{roots.MEMORY_REL}/{head}" if e.root == ROOT_MEMORY else head
        out.add(rel + "/")
    return tuple(sorted(out))


# ── resolution: the entity an identifier or a path names ─────────────────────
# This is the seam the five false-positive queue items came from: the resolvers
# (`associate.py`, `conflict.py`) walked `tree.leaves()` and nothing else, so a
# name pointing at a real convention or a real file outside the tree read as
# dangling. The node set is declared here, once, and both resolvers read it.

_URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)

# The first path segment that says where a relative reference is rooted. A
# reference in this tree is written three ways -- `memory/knowledge/x.md`, the
# contract's `knowledge/x.md`, and the bare stem `related:` uses -- and a
# resolver that accepted one would report the other two as dangling.
REPO_TOPS = ("memory", "engine", "config", "dev", "backups",
             "dotfiles", "STRUCTURE.md", "README.md", "CLAUDE.md")
# What a bare reference like `knowledge/x.md` is rooted at: the memory
# tree's own top level. `conventions/`, `boundaries/`, `user/` and
# `subagents/` left it in R3b for `config/`, so they are reached from the
# repository root now, not from here.
AGENT_TOPS = ("knowledge", "journal", "skills", "README.md", "AGENTS.md")


def _clean(ref: str) -> str:
    return (ref or "").strip().strip("[]").strip().strip("\"'").strip()


def _segments_match(pat: list, parts: list) -> bool:
    """Glob match over `/`-separated segments, with `**` = zero or more.

    Written rather than delegated to `pathlib.PurePath.match`, whose `**`
    semantics are version-dependent -- a check that behaves differently on two
    interpreters is not a check.
    """
    if not pat:
        return not parts
    if pat[0] == "**":
        return any(_segments_match(pat[1:], parts[i:])
                   for i in range(len(parts) + 1))
    if not parts:
        return False
    if not fnmatch.fnmatchcase(parts[0], pat[0]):
        return False
    return _segments_match(pat[1:], parts[1:])


def _normalize(rel: str) -> str:
    """A repo-relative path, from either spelling the codebase uses.

    `tree.Doc.rel` is relative to `memory/` and carries no prefix
    (`knowledge/system/boundaries/boundaries.md`); everything this module produces is
    repo-relative (`memory/knowledge/system/boundaries/boundaries.md`). Accepting both here,
    once, is what keeps every caller from having to remember which it holds.
    """
    if rel.startswith((f"{M}/", "dev/")):
        return rel
    first = rel.split("/", 1)[0]
    return f"{M}/" + rel if first in AGENT_TOPS else rel


def _type_of(rel: str) -> str | None:
    """The entity type a REPO-relative path belongs to, or None.

    `root` is what makes `dev/<track>/` expressible at all: the track entity
    lives outside `memory/`, and a schema that could only describe the agent
    tree would have had to invent a second register for the one type the pass
    writes proposals about.
    """
    rel = _normalize(rel)
    rel = rel.rstrip("/") + ("/" if rel.endswith("/") else "")
    for etype, e in sorted(ENTITIES.items(),
                           key=lambda kv: (kv[1].pattern.count("**"),
                                           kv[1].pattern.count("*"))):
        if not e.pattern:
            continue
        if e.root == ROOT_MEMORY:
            if not rel.startswith(f"{M}/"):
                continue
            inner = rel[len(f"{M}/"):]
        else:
            inner = rel
        if _segments_match(e.pattern.split("/"), inner.split("/")):
            return etype
    return None



def _repo_rel(ref: str):
    """A path reference -> `(repo_relative_posix, inside_the_agent_tree)`,
    or None when the reference is not rooted in this repository at all."""
    cand = ref
    if cand.startswith("~"):
        cand = str(pathlib.Path(cand).expanduser())
    if cand.startswith("/"):
        try:
            return pathlib.Path(cand).relative_to(REPO).as_posix()
        except ValueError:
            return None
    first = pathlib.PurePosixPath(cand).parts[0] if cand else ""
    if first == M:
        return cand
    if first in AGENT_TOPS:
        return f"{M}/" + cand
    if first in REPO_TOPS:
        return cand
    return None


def _is_pathish(ref: str) -> bool:
    """Is this reference a PATH, or a name to look up?

    A single segment is a name even when it ends in `.md`: `supersedes:
    nowhere.md` is a dangling name in this tree, not a file outside it, and
    calling it `external` would bless a broken reference as a real one. Only a
    root (`~`, `/`, `.`), a separator, or a git remote makes it a path.
    """
    return (ref.startswith(("~", "/", ".")) or "/" in ref
            or ref.startswith("git@"))


class Index:
    """Every identifier in the tree, by stem and by path.

    Built once per pass stage rather than per reference: `related:` names are
    bare stems, and resolving each of ~150 of them against a fresh walk of the
    journal would be a glob per name.
    """

    def __init__(self, agents=None, base=None):
        self.agents = pathlib.Path(agents or AGENTS)
        self.base = pathlib.Path(base) if base else None
        self.stems: dict = {}
        self.types: dict = {}
        self.duplicates: dict = {}
        self._walk()

    def _add(self, rel: str, etype: str, ident: str):
        if ident in self.stems:
            self.duplicates.setdefault(ident, [self.stems[ident]]).append(
                (etype, rel))
            return
        self.stems[ident] = (etype, rel)
        self.types[rel] = etype

    def _walk(self):
        for rel, p in _walk_docs(self.agents):
            etype = _type_of(rel)
            if etype is None:
                continue
            ident = p.stem
            if etype == "skill":
                ident = (frontmatter.read(p).get("name") or p.parent.name)
            if etype == "report" and p.name.split(".")[-2:-1] == ["full"]:
                continue          # `*.full.md` is the same report, rendered wide
            self._add(rel, etype, ident)
        for d in sorted((REPO / "dev").glob("*")):
            if d.is_dir():
                self._add(f"dev/{d.name}/", "track", d.name)
        if self.base is not None:
            for p in sorted((self.base / "transcripts").glob("*.jsonl")):
                self._add(f"transcripts/{p.name}", "shadow", p.stem)

    def rel(self, rel: str) -> str | None:
        return self.types.get(rel)

    def stem(self, ident: str):
        return self.stems.get(ident)


_INDEX: dict = {}


def index(agents=None, base=None) -> Index:
    """The identifier index, memoised per (agents, base) pair.

    Memoised because a stage resolves hundreds of names; `reset()` exists so a
    caller that changes the tree mid-process (a test, or a pass that writes a
    leaf and then resolves it) can drop it deliberately rather than silently
    reading a stale world.
    """
    key = (str(pathlib.Path(agents or AGENTS)), str(base or ""))
    if key not in _INDEX:
        _INDEX[key] = Index(agents, base)
    return _INDEX[key]


def reset() -> None:
    """Forget every memoised index and criteria read."""
    _INDEX.clear()


def resolve(ref: str, agents=None, base=None, idx: Index | None = None):
    """`(entity_type, repo_relative_path)` for what `ref` names, or None.

    Three input shapes, in the order the tree contains them:
      * a URL or a `git@` remote            -> `external`, verbatim
      * a path                              -> typed by where it sits under
                                               `memory/`, else `external`
      * a bare stem                         -> looked up in the identifier set

    A bare stem that names nothing returns None: that is the dangling case the
    queue legitimately reports, and it must not be confused with `external`.
    An `memory/`-relative path that does not exist returns None too -- a typed
    path is a claim about a file, so it has to be a file.
    """
    s = _clean(ref)
    if not s:
        return None
    if _URL.match(s) or s.startswith("git@"):
        return ("external", s)
    if _is_pathish(s):
        rel = _repo_rel(s)
        if rel is None:
            # Not rooted here: outside `memory/`, which is what `external` is
            # FOR -- and it does not matter whether the file exists, because
            # this is the one region the boundary rules may forbid reading
            # (SPECS.md O1b).
            return ("external", s)
        etype = _type_of(rel)
        if etype and (REPO / rel).exists():
            return (etype, rel)
        if rel.startswith(f"{M}/") or etype:
            # A declared home, but no file: the leaf was renamed, or was never
            # written. That is the DANGLING case -- reporting it as `external`
            # would silently bless a reference to something that is gone.
            return None
        return ("external", s)
    hit = (idx or index(agents, base)).stem(
        s[:-3] if s.endswith(".md") else s)
    return hit


def resolve_type(ref: str, agents=None, base=None, idx: Index | None = None):
    """Just the type, or None."""
    hit = resolve(ref, agents=agents, base=base, idx=idx)
    return hit[0] if hit else None


def collisions(agents=None, base=None) -> list:
    """Identifiers claimed by more than one document.

    `related:` names bare stems, so a stem is the identifier (O1i): a collision
    between a leaf and a skill makes an edge ambiguous, and an ambiguous edge is
    a wrong edge eventually. Reported, never renamed.
    """
    idx = index(agents, base)
    return [(ident, claims) for ident, claims in sorted(idx.duplicates.items())]


def branch_of(rel: str) -> str | None:
    """The declared branch a repo-relative path sits under, or None.

    Only the three branches are returned; `None` means the document is under the
    pre-O2 layout (or somewhere undeclared, which a check must tell apart).
    Both trees carry the same three branches since O6b: `knowledge/<branch>/`
    and `skills/<branch>/` resolve the same way, which is the point of the
    parallel application.
    """
    inner = rel
    if inner.startswith(f"{M}/"):
        inner = inner[len(f"{M}/"):]
    parts = inner.split("/")
    if parts[0] in ("knowledge", "skills") and len(parts) > 1:
        return parts[1] if parts[1] in BRANCHES else None
    return None


def legacy_branch_of(rel: str) -> str | None:
    """The pre-O2 branch a leaf/skill sits under, or None."""
    if not rel.startswith(f"{M}/knowledge/"):
        return None
    parts = rel.split("/")
    if len(parts) > 2 and parts[2] in LEGACY_BRANCHES:
        return parts[2]
    return None


def subject_of(doc, rel: str = None, fm: dict = None) -> str | None:
    """The subject of one document, from the ONE place that knows which way.

    Derived from the path for a leaf or a skill (`system/<subject>/...`),
    declared in frontmatter for an episode or a report: an episode is captured
    with no category and is labelled LATER, so the path cannot carry it yet
    (capture -> associate -> categorise, SPECS.md O5a). One vocabulary, two
    resolution rules, stated here and nowhere else.

    Takes a `tree.Doc` or the `(etype, rel, fm)` triple -- the accessor is
    called from both sides of the pass and neither should have to unpack for
    the other.
    """
    if not isinstance(doc, str):
        etype = getattr(doc, "kind", None)
        rel = getattr(doc, "rel", rel)
        fm = getattr(doc, "fm", fm)
        if etype == "knowledge":
            etype = "leaf"
    else:
        etype = doc
    fm = fm or {}
    rel = rel or ""
    if etype in ("leaf", "skill"):
        parts = rel.split("/")
        for i, part in enumerate(parts):
            if part == "system" and i + 1 < len(parts):
                cand = parts[i + 1]
                return cand if cand in SUBJECTS else None
        return None
    if etype in ("episode", "report"):
        val = fm.get("subject")
        return val if isinstance(val, str) and val in SUBJECTS else (val or None)
    return None


def subject_at(rel: str) -> str | None:
    """The subject that OCCUPIES a repository-relative path, or None.

    THE THIRD RESOLUTION RULE, beside the two `subject_of` states: a leaf's
    subject is its folder and an episode's is declared, and this one answers for
    an ARBITRARY file. R1h's `touches:` needs it -- a session touches files, not
    documents -- so the facet's vocabulary and the tree's are the same
    vocabulary, read by a rule that works for any path at all.

    Built from `places:` (R1g), longest place first so a subject occupying a
    subdirectory wins over the root that contains it. `places_findings` already
    proves every top-level directory has exactly one owner, so an unmatched path
    means NO subject -- an Area directory, the user's own files, `dev/`. That
    None is the whole reason this is a function and not a default: a facet that
    invents a subject is wrong in the direction nothing detects.
    """
    rel = rel.strip("/")
    if not rel:
        return None
    for place, sid in _places_by_specificity():
        if rel == place or rel.startswith(place + "/"):
            return sid
    return None


_PLACES: list = []


def _places_by_specificity() -> list:
    """`((place, subject_id), ...)` with the longest place first, memoised.

    Memoised for the same reason `index()` is: stage 1 calls this once per
    touched path, thousands of times a night, over a register that cannot change
    mid-process. `reload()` drops it, so a test that edits the register sees it
    move.
    """
    if not _PLACES:
        _PLACES[:] = sorted(((p, s.id) for s in SUBJECTS.values()
                             for p in s.places),
                            key=lambda t: (-len(t[0]), t[0]))
    return _PLACES


# ── findings ─────────────────────────────────────────────────────────────────

def _is_member(p: pathlib.Path) -> bool:
    """Is this file a member of its folder's class?

    The exclusion set is IMPORTED from `tree.SKIP_NAMES`, not re-declared: the
    pass's population and the check's population must not be able to disagree
    about what a member is, and a second list is how they would. `README.md` is
    added here and not there because the pass never walks `journal/reports/`,
    while this check does -- a router is a routing artifact, not a report.
    """
    return p.name not in SKIP_NAMES and not p.name.startswith("_") \
        and p.name != "README.md"


def doc_dirs(repo: pathlib.Path) -> list:
    """The directories the registers point at, repo-relative.

    DERIVED from `ENTITIES` rather than listed here: each pattern's literal
    head IS the directory that kind lives in (`knowledge/**/*.md` ->
    `memory/knowledge`, `config/practice/conventions/*.md` ->
    `config/practice/conventions`). Until R3b one `rglob` over the vault was
    every document there was; the directive kinds are under `config/` now,
    and a walker that kept its own list would have to be edited every time a
    register gained a kind -- which is the drift `declared_paths` exists to
    catch, one layer down.
    """
    out = []
    for e in sorted(ENTITIES.values(), key=lambda e: e.pattern):
        if not e.pattern or not e.pattern.endswith(".md"):
            continue
        head = paths.literal_head(e.pattern)
        rel = "/".join(([roots.MEMORY_REL] if e.root == ROOT_MEMORY else []) + [head])
        if rel and rel not in out:
            out.append(rel)
    # Nested heads walk the same files twice -- `journal/**` and
    # `journal/reports/*` -- and every report would be indexed as its own
    # duplicate (19 `collision` errors, 2026-10-09). Keep the outermost.
    return [d for d in out
            if not any(d.startswith(o + "/") for o in out if o != d)]


def _walk_docs(agents: pathlib.Path):
    """`(repo-relative path, path)` for every document the registers govern."""
    repo = agents.parent
    for rel in doc_dirs(repo):
        root = repo / rel
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.md")):
            if _is_member(p):
                yield f"{rel}/{p.relative_to(root).as_posix()}", p


def _docs(agents: pathlib.Path):
    """Every document the registers govern, with its frontmatter.

    Walked here rather than through `tree.documents()`: that loader also scores
    (pulls git and the activity record) and is the pass's own population, while
    this is the CHECK's -- the same tree read for a different question. The
    exclusion set is imported, not re-declared, so the two cannot disagree about
    what a member is.
    """
    out = []
    for rel, p in _walk_docs(agents):
        etype = _type_of(rel)
        if etype is None:
            continue
        out.append((etype, rel, frontmatter.read(p)))
    return out


def _violation_for_facet(facet: str, value: str):
    for v in VIOLATIONS:
        if v.facet == facet and v.value == value:
            return v
    return None


def _violation_for_edge(rel: str, key: str):
    for v in VIOLATIONS:
        if v.edge == key and rel in v.paths:
            return v
    return None


def facet_findings(agents=None) -> list:
    """A declared facet carrying a value outside its domain.

    An out-of-domain value that a violation declares WARNS (with the register
    entry that declares it); one nobody declared is an ERROR. That is the single
    distinction this whole register exists for.
    """
    agents = pathlib.Path(agents or AGENTS)
    out = []
    for etype, rel, fm in _docs(agents):
        for name, facet in FACETS.items():
            if etype not in facet.on or name not in fm:
                continue
            if name in facet.derived_for and name not in facet.declared_for:
                continue
            if etype in facet.derived_for:
                continue
            raw = fm.get(name)
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                if not isinstance(value, str) or value == "":
                    continue
                if facet.domain and value not in facet.domain:
                    v = _violation_for_facet(name, value)
                    if v:
                        out.append(Finding(
                            "warn", f"facet:{name}", rel,
                            f"`{name}: {value}` is outside "
                            f"{'|'.join(facet.domain)}", v.n))
                    else:
                        out.append(Finding(
                            "error", f"facet:{name}", rel,
                            f"`{name}: {value}` is outside "
                            f"{'|'.join(facet.domain)} and no violation "
                            f"declares it"))
                elif name == "subject" and name not in SUBJECTS:
                    out.append(Finding(
                        "error", "subject", rel,
                        f"`subject: {value}` is not one of the registered subjects"))
    return out


def branch_findings(agents=None, projects=None) -> list:
    """Branches: undeclared layout, missing subjects, concentration, and a
    `projects/` leaf whose project is gone.

    The pre-O2 layout is a DECLARED gap (`LEGACY_BRANCHES`), so it warns once;
    a branch nobody declared is an error. `projects/` retires a leaf when its
    project ends, so a leaf whose project directory is gone is exactly the
    state the branch's retirement rule predicts and nobody notices.
    """
    agents = pathlib.Path(agents or AGENTS)
    projects = pathlib.Path(projects or PROJECTS)
    out = []
    legacy: dict = {}
    by_router: dict = {}
    for etype, rel, fm in _docs(agents):
        if etype in ("report", "episode", "convention", "identity", "ward"):
            continue
        branch = branch_of(rel)
        if branch is None:
            leg = legacy_branch_of(rel)
            if leg:
                legacy[leg] = legacy.get(leg, 0) + 1
            else:
                out.append(Finding(
                    "error", "branch", rel,
                    "sits under no declared branch and no declared legacy "
                    f"branch (branches: {', '.join(BRANCHES)}; legacy: "
                    f"{', '.join(LEGACY_BRANCHES)})"))
            continue
        # The concentration rule (violation 10, and knowledge/CONTEXT.md
        # §Splitting) counts LEAVES: it asks how many rows one router has to
        # triage. A skill is a different entity type with its own router
        # structure, so counting it here inflated `system/` from 31 to 61 on
        # O6b and said nothing about either tree.
        if etype != "skill":
            inner = rel[len(f"{M}/"):] if rel.startswith(f"{M}/") else rel
            by_router.setdefault("/".join(inner.split("/")[:-1]), []).append(rel)
        if branch == "projects":
            name = rel.split("projects/", 1)[1].split("/")[0]
            if name.endswith(".md"):
                name = name[:-3]
            if not (projects / name).exists():
                out.append(Finding(
                    "warn", "project", rel,
                    f"`projects/{name}` names a project whose directory "
                    f"({projects / name}) no longer exists -- at project end a "
                    "leaf promotes to `areas/` or is deleted with the project"))
        if branch in ("system", "areas") and subject_of(etype, rel, fm) is None:
            out.append(Finding(
                "warn", "subject", rel,
                f"under `{branch}/` but names no subject "
                f"({'|'.join(SUBJECTS)} for system/, A-P for areas/)"))
    if legacy:
        total = sum(legacy.values())
        out.append(Finding(
            "warn", "pre-o2-layout", f"{roots.MEMORY_REL}/knowledge/",
            f"{total} document(s) still under the pre-O2 layout "
            f"({', '.join(f'{k}/ ({n})' for k, n in sorted(legacy.items()))}) -- "
            f"{LEGACY_UNTIL}. Declared in LEGACY_BRANCHES, so it warns and does "
            f"not fail; a branch outside both lists is an error."))
    for group, rels in sorted(by_router.items()):
        if len(rels) > BRANCH_MAX:
            v = next((v for v in VIOLATIONS if v.n == 10), None)
            out.append(Finding(
                "warn", "branch-size", f"{roots.MEMORY_REL}/{group}/",
                f"{len(rels)} leaves against the tree's own ~{BRANCH_MAX} rule "
                f"-- the rows one router triages",
                10 if v else 0))
    # The pre-O2 layout is counted per legacy branch: it has no routers, and the
    # question there is how much is left to move.
    for branch, n in sorted(legacy.items()):
        if n > BRANCH_MAX:
            v = next((v for v in VIOLATIONS if v.n == 10), None)
            out.append(Finding(
                "warn", "branch-size", f"{roots.MEMORY_REL}/knowledge/{branch}/",
                f"{n} leaves against the tree's own ~{BRANCH_MAX} rule",
                10 if v else 0))
    return out


RELATION_KEYS = ("related", "supersedes", "contradicts", "promoted_from",
                 "superseded_by", "cites")


def relation_findings(agents=None, base=None) -> list:
    """Every relation endpoint resolves to a declared type, or to `external`.

    `source:` is deliberately NOT resolved: the live tree carries free text
    there (`see §Sources`), because it names MATERIAL rather than an identifier.
    A check that resolved it would either fail on the truth or need a
    prose-shaped exception for every leaf, and both are worse than saying so.
    """
    agents = pathlib.Path(agents or AGENTS)
    idx = index(agents, base)
    out = []
    for etype, rel, fm in _docs(agents):
        if not fm:
            continue
        for key in RELATION_KEYS:
            raw = fm.get(key)
            if raw in (None, "", []):
                continue
            refs = raw if isinstance(raw, list) else [raw]
            for ref in refs:
                ref = _clean(str(ref))
                if not ref:
                    continue
                if resolve(ref, agents=agents, base=base, idx=idx) is None:
                    v = _violation_for_edge(rel, key)
                    out.append(Finding(
                        "warn" if v else "error", f"edge:{key}", rel,
                        f"`{key}: {ref}` names nothing: no entity type resolves "
                        f"it and it is not a path outside the tree",
                        v.n if v else 0))
    return out


def _naming_targets(repo: pathlib.Path):
    """Every file and directory the naming rules govern.

    `memory/**` and `dev/**`: the tree, and the tracks that plan it. Hidden names
    (`.obsidian`) and `_`-prefixed names are non-members by rule 2 and are not
    governed. Recorded as a decision because it is one -- markdown under
    `engine/` is code, not a document.
    """
    for base in (M, roots.DEV_REL):
        root = repo / base
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(repo).as_posix()
            if any(part.startswith(".") or part == "__pycache__"
                   for part in p.relative_to(repo).parts):
                continue
            yield p, rel


_STRUCTURAL = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+)*$")
_CONTENT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TIMESTAMP = re.compile(r"-\d{8}T\d{6}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Rule 5's list. `reference_` is the measured case; the rest are the same
# mistake in the same shape -- a ROLE written as a filename prefix where a
# frontmatter facet already carries it. Named as data so a new role prefix is a
# decision rather than an omission.
FACET_PREFIXES = ("reference", "imported", "derived", "authored", "trusted")


def _violation_for_naming(rel: str, rule: int):
    for v in VIOLATIONS:
        if rel in v.paths and rule in v.rules:
            return v
    return None


def naming_findings(repo=None) -> list:
    """NAMING's checkable rules, against the tree and the tracks.

    One finding per (path, rule). A finding whose (path, rule) a VIOLATION
    declares warns; any other is an error, which is what makes this a check and
    not a report. Rules 4, 8 and 9 are judgements and are not grepped -- they
    are declared, dated and reviewed instead.

    The rules are tested in the order a name is read: is it a member (1, 2),
    does its case name its layer (3), does it lead with a date when it is an
    event (6), does it encode a facet (5).
    """
    repo = pathlib.Path(repo or REPO)
    out = []

    def note(code, rel, detail, rule):
        v = _violation_for_naming(rel, rule)
        out.append(Finding("warn" if v else "error", code, rel, detail,
                           v.n if v else 0))

    for p, rel in _naming_targets(repo):
        if p.is_dir():
            # A `_`-prefixed directory is a container of non-members (rule 2);
            # its own name is outside rule 7.
            if not p.name.startswith("_") and not _CONTENT.match(p.name):
                note("naming:7", rel,
                     "directories are lowercase-hyphenated (rule 7)", 7)
            continue
        name = p.name
        if name.startswith(("_", ".")):
            continue
        stem = name.split(".")[0]
        stem = _TIMESTAMP.sub("", stem)
        if _STRUCTURAL.match(stem):
            continue                    # rule 3: structural, one per folder
        head, sep, tail = stem.partition("_")
        if sep and not _ISO_DATE.match(head):
            note("naming:1", rel,
                 f"`_` separates FIELDS and `{head}` is not one (rule 1)", 1)
            if head in FACET_PREFIXES:
                note("naming:5", rel,
                     f"a filename may not encode what a facet carries: the "
                     f"`{head}_` prefix duplicates a frontmatter facet "
                     f"(rule 5)", 5)
        words = (head, tail) if sep else (stem,)
        if not all(w == "" or _CONTENT.match(w) for w in words):
            note("naming:3", rel,
                 "case carries layer: UPPERCASE.md is structural, "
                 "lowercase-hyphenated.md is a content member (rule 3)", 3)
            continue
        if rel.startswith(f"{M}/journal/2026/"):
            parts = rel.split("/")
            if len(parts) >= 6 and not _ISO_DATE.match(parts[-1][:10]):
                note("naming:6", rel,
                     "a journal entry leads with its ISO-8601 date (rule 6)", 6)
    return out


# What `places_findings` does not ask about: tool state in dot-directories
# (`.git`, `.obsidian`, `.claude`), and the roots themselves at the repository
# level -- a root is the level above a subject, not one of its places.
_PLACE_SKIP_PREFIX = "."


def _tracked_or_empty(d: pathlib.Path, repo: pathlib.Path) -> bool:
    """Is `d` part of the repository's shape, not a local leftover?

    A directory whose every file git ignores (`backups/`: a log and an old DB)
    is machine state. An EMPTY directory counts: it is what someone creates
    when they start a new folder, which is the moment a filing decision is
    owed -- and git, which never tracks an empty directory, cannot say so.
    """
    if not any(d.iterdir()):
        return True
    try:
        listed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard",
             "--", d.relative_to(repo).as_posix()],
            cwd=repo, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return True
    return listed.returncode != 0 or bool(listed.stdout.strip())


def _top_dirs(repo: pathlib.Path) -> list:
    """Every top-level directory of the repository root and of each root."""
    roots_rel = {roots.ENGINE_REL, roots.CONFIG_REL, roots.MEMORY_REL,
                 roots.DEV_REL}
    out = []
    for base in ("", roots.ENGINE_REL, roots.CONFIG_REL, roots.MEMORY_REL):
        d = repo / base
        if not d.is_dir():
            continue
        for child in sorted(d.iterdir()):
            rel = child.relative_to(repo).as_posix()
            if not child.is_dir() or child.name.startswith(_PLACE_SKIP_PREFIX) \
                    or child.name == "__pycache__" or rel in roots_rel:
                continue
            if _tracked_or_empty(child, repo):
                out.append(rel)
    return out


def places_findings(repo=None) -> list:
    """R1g/R2b: every top-level directory has exactly one owner, or a reason.

    Three errors, none declarable in the violations register, because each is
    a NEW gap rather than a known one:
      * a declared place that is neither a directory nor a symlink -- the
        folder moved and its filing lost its anchor;
      * a place claimed twice -- two subjects, or a subject and `unmapped:`;
      * a top-level directory nobody claims -- a new folder made without the
        filing decision `subjects.yaml` exists to record.

    A SYMLINK COUNTS, and it is a place even when it dangles. `unmapped:`
    carries `dotfiles` for the reason that it IS a link to a separate
    repository, and `is_dir()` answers about the target: on this machine the
    link resolves, in a worktree or a fresh clone it does not, and the check
    was reading the difference as a moved folder (measured 2026-10-14,
    the publication track's recut of 2026-10-14 (git history) §2). The anchor is the NAME --
    whether the link resolves is the business of whatever made it.
    """
    repo = pathlib.Path(repo or REPO)
    out = []
    owner: dict = {}
    claims = [(p, f"SUBJECTS:{s.id}") for s in SUBJECTS.values() for p in s.places]
    claims += [(u.id, "UNMAPPED") for u in UNMAPPED.values()]
    for place, who in claims:
        if place in owner:
            out.append(Finding(
                "error", "place-twice", who,
                f"`{place}` is claimed by {owner[place]} and by {who}: a "
                f"directory has one subject, or none with a reason"))
        owner.setdefault(place, who)
        if not ((repo / place).is_dir() or (repo / place).is_symlink()):
            out.append(Finding(
                "error", "place", who,
                f"place `{place}` is neither a directory nor a symlink under "
                f"the repository root -- a subject whose folder moved has "
                f"lost its anchor, and filing would keep pointing at nothing"))
    for rel in _top_dirs(repo):
        if rel not in owner:
            out.append(Finding(
                "error", "unplaced", rel,
                f"`{rel}/` is claimed by no subject and is not under "
                f"`unmapped:` in subjects.yaml -- add it to one subject's "
                f"`places:`, or to `unmapped:` with the reason it has none"))
    return out


def corpus(agents=None) -> list:
    """O4a: the 31 knowledge leaves as `(rel, subject)`, human-ratified.

    THE GROUND TRUTH FOR O4b, and the reason it is worth almost nothing to
    produce: O2b moved every leaf into `system/<subject>/`, and moving a leaf
    into a folder IS assigning its subject. The labelling was a by-product of a
    move that had to happen anyway, so this reads the ratification off the
    filesystem rather than asking anyone to sit down and tag 31 files.

    Which means the tree is now load-bearing in a way it was not before:
    MOVING A LEAF BEFORE O4 RUNS VOIDS THE FALSIFICATION, because it silently
    edits the answer key.

    `areas/` and `projects/` leaves are excluded -- their subject vocabulary is
    A-P and a project name, not the subjects, and O4b asks one question over
    `criteria("subject")`. Today both are empty, so the corpus is the whole
    tree; the filter is here so that stops being true safely.
    """
    agents = pathlib.Path(agents or AGENTS)
    out = []
    for etype, rel, fm in _docs(agents):
        if etype != "leaf" or branch_of(rel) != "system":
            continue
        out.append((rel, subject_of(etype, rel, fm)))
    return sorted(out)


def subject_dir_findings(agents=None) -> list:
    """O2d: every directory under `system/` is a declared subject.

    The other half of O2c's mirror, and the one the per-document walk cannot
    make. `branch_findings` reaches a subject folder only THROUGH a document in
    it, so an EMPTY folder under `system/` is invisible to it: `system/tooling/`
    with nothing in it yet is exactly how a new subject gets invented
    without passing through the register, and the first leaf filed there would
    then warn once and be filed anyway.

    The branch directory is the declared interface, not the leaf -- so this is
    the direction that is checked, and the empty case is the direction that is
    dangerous. The reverse (a declared subject with NO directory) is NOT an
    error: `publication` has none, because a subject folder appears on its
    first leaf and declaring one early would create one empty directory per
    subject
    to prove a register that already exists.

    Read from `SUBJECTS` rather than from a copied list, so the register and
    the tree are the same artifact with two readers.
    """
    agents = pathlib.Path(agents or AGENTS)
    root = agents / "knowledge" / "system"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if d.name in SUBJECTS:
            continue
        n = len(list(d.rglob("*.md")))
        out.append(Finding(
            "error", "subject-dir", f"{roots.MEMORY_REL}/knowledge/system/{d.name}/",
            f"is not a declared subject ({'|'.join(SUBJECTS)}). "
            + (f"It holds {n} document(s), each of which is reported "
               "separately; the directory itself is the thing to remove or "
               "declare." if n else
               "It is EMPTY, so no document reports it and nothing else "
               "would -- an undeclared subject invented by `mkdir` is what "
               "this catches.")))
    return out


def _register_entries() -> tuple:
    """The seven registers as `(label, entries)`, in declaration order.

    Seven and not the five O1a names: O1f needed the branches as data and O1k
    needed the violations as data, and a register that lives in prose instead of
    in the module is a register a check cannot read.
    """
    return (("ENTITIES", tuple(ENTITIES.items())),
            ("FACETS", tuple(FACETS.items())),
            ("SUBJECTS", tuple(SUBJECTS.items())),
            ("RELATIONS", tuple(RELATIONS.items())),
            ("BRANCHES", tuple(BRANCHES.items())),
            ("NAMING", tuple(enumerate(NAMING, 1))),
            ("VIOLATIONS", tuple((v.n, v) for v in VIOLATIONS)))


def review_findings(today=None) -> list:
    """Register entries whose `reviewed:` date is older than the cadence.

    A stale DEFINITION is a signal, not a broken build: this returns warnings,
    and the healthcheck prints them in its own section and exits 0 (O1m).
    """
    today = today or dt.date.today()
    out = []
    for reg, entries in _register_entries():
        for key, entry in entries:
            label = getattr(entry, "id", None) or key
            rev = getattr(entry, "reviewed", "")
            try:
                when = dt.date.fromisoformat(rev)
            except (TypeError, ValueError):
                out.append(Finding("error", "reviewed", f"{reg}:{label}",
                                   f"`reviewed:` is {rev!r}, not an ISO date"))
                continue
            age = (today - when).days
            if age > CADENCE_DAYS:
                out.append(Finding(
                    "warn", "cadence", f"{reg}:{label}",
                    f"not reviewed in {age} d (since {rev}); the cadence is "
                    f"{CADENCE_DAYS} d and a stale definition is a signal, not "
                    "a broken build"))
    return out


def structural_findings(agents=None, repo=None, base=None, projects=None,
                        today=None) -> list:
    """O1l's structural half, in one list: the branches, the subjects, the facet
    domains, the identifiers, the relation endpoints and the filenames."""
    agents = pathlib.Path(agents or AGENTS)
    repo = pathlib.Path(repo or REPO)
    out = []
    out += branch_findings(agents, projects)
    out += facet_findings(agents)
    for ident, claims in collisions(agents, base):
        out.append(Finding(
            "error", "collision", ident,
            "the stem is the identifier and two documents claim it: "
            + ", ".join(f"{t} {r}" for t, r in claims)
            + " -- an edge naming this stem is ambiguous"))
    out += relation_findings(agents, base)
    out += naming_findings(repo)
    out += places_findings(repo)
    out += subject_dir_findings(agents)
    return out


def review_lines(today=None) -> list:
    """What the healthcheck's ontology section prints: `ok `/`warn ` lines."""
    findings = review_findings(today)
    if not findings:
        n = sum(len(x) for x in (ENTITIES, FACETS, SUBJECTS, RELATIONS,
                                 VIOLATIONS)) + len(NAMING) + len(BRANCHES)
        return [f"ok ontology register reviewed within {CADENCE_DAYS} d "
                f"({n} entries, last review {REVIEWED})"]
    return [f"warn {f.where}: {f.detail}" if f.level == "warn"
            else f"warn {f.where}: {f.detail}" for f in findings]


# ── selfcheck: the registers versus each other ──────────────────────────────

def selfcheck(verbose: bool = True) -> list:
    """Coherence of the registers, and their counts. Raises on incoherence.

    An undeclared value is an error, not a default: if a register entry is
    missing its criteria, its layer, its column or its `reviewed:` date, this
    raises rather than printing a warning, because every later phase reads these
    registers and a silent hole is what a schema exists to prevent.
    """
    problems: list = []

    def check(label, key, entry):
        for field in ("criteria", "layer", "column", "reviewed"):
            val = getattr(entry, field, None)
            if not val:
                problems.append(f"{label}:{key} has no `{field}`")
        if getattr(entry, "layer", None) not in LAYERS:
            problems.append(f"{label}:{key} layer {getattr(entry, 'layer', None)!r}"
                            f" is not one of {LAYERS}")
        if getattr(entry, "column", None) not in COLUMNS:
            problems.append(f"{label}:{key} column "
                            f"{getattr(entry, 'column', None)!r} is not one of "
                            f"{COLUMNS}")
        try:
            dt.date.fromisoformat(str(getattr(entry, "reviewed", "")))
        except ValueError:
            problems.append(f"{label}:{key} reviewed is not an ISO date")

    for label, entries in _register_entries():
        for key, entry in entries:
            check(label, key, entry)
    for v in VIOLATIONS:
        if v.state not in STATES:
            problems.append(f"VIOLATIONS:{v.n} state {v.state!r} is not one of "
                            f"{STATES}")
        if v.state == STATE_OPEN and not v.recommendation:
            problems.append(f"VIOLATIONS:{v.n} is open with no recommendation")

    ids = [s.id for s in SUBJECTS.values()]
    keys = list(SUBJECTS)
    if len(set(ids)) != len(ids):
        problems.append("SUBJECTS: duplicate id")
    if ids != keys:
        problems.append("SUBJECTS: key and `id` disagree for at least one entry")
    for i in ids:
        if i != i.lower():
            problems.append(f"SUBJECTS:{i} is not lowercase")
    clash = set(ids) & set(BRANCHES)
    if clash:
        problems.append(f"SUBJECTS and BRANCHES share ids: {sorted(clash)}")

    for name, rel in RELATIONS.items():
        if rel.walkable and rel.column != "assertion":
            problems.append(f"RELATIONS:{name} is walkable but its column is "
                            f"{rel.column!r}")
        if not rel.walkable and rel.column != "coincidence":
            problems.append(f"RELATIONS:{name} is not walkable but its column "
                            f"is {rel.column!r}")
    walk, coin = relations()
    if set(id(r) for r in walk) & set(id(r) for r in coin):
        problems.append("RELATIONS: a relation appears in both registers")

    for name, facet in FACETS.items():
        for etype in facet.on:
            if etype not in ENTITIES:
                problems.append(f"FACETS:{name} is declared on unknown entity "
                                f"{etype!r}")
        both = set(facet.derived_for) & set(facet.declared_for)
        if both:
            problems.append(f"FACETS:{name} is both derived and declared for "
                            f"{sorted(both)} -- one vocabulary, one rule")
        if facet.domain and facet.column == "coincidence" and name != "area":
            problems.append(f"FACETS:{name} has a closed domain and is a "
                            f"coincidence only -- check the column")
    for name, e in ENTITIES.items():
        if e.directive and e.validated:
            problems.append(f"ENTITIES:{name} is directive AND validated")

    rules = [r.id for r in NAMING]
    if rules != list(range(1, len(NAMING) + 1)):
        problems.append(f"NAMING rule ids are not 1..N: {rules}")
    ns = [v.n for v in VIOLATIONS]
    if len(set(ns)) != len(ns):
        problems.append("VIOLATIONS: duplicate item number")
    if not AREA_CRITERIA:
        problems.append("AREAS: the profile yielded no Area codes; "
                        "AREA_CRITERIA is empty")
    for name, e in ENTITIES.items():
        if e.pattern and _type_of(f"{M}/" + e.pattern.replace("*", "x").lstrip("/")
                                  if e.root == ROOT_MEMORY else
                                  e.pattern.replace("*", "x")) is None:
            problems.append(f"ENTITIES:{name} pattern {e.pattern!r} matches "
                            f"nothing it is supposed to")

    if verbose:
        for label, entries in _register_entries():
            n = len(entries)
            print(f"{label:<11} {n:>3} entr{'y' if n == 1 else 'ies'}")
        print(f"{'LAYERS':<11} {len(LAYERS)}  {', '.join(LAYERS)}")
        print(f"{'COLUMNS':<11} {len(COLUMNS)}  {', '.join(COLUMNS)}")
    if problems:
        raise Inconsistent("ontology registers disagree with each other:\n  "
                           + "\n  ".join(problems))
    return problems
