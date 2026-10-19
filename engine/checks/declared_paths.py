#!/usr/bin/env python3
"""Every list of paths this codebase declares, and whether those paths exist.

WHY THIS EXISTS. `memory/MEMORY.md` was deleted on 2026-09-04. Stage 4 of the
nightly pass kept reading it, kept cap-checking it against nothing, and kept
offering it as a `TARGET:` for a week. Its 2026-09-10 proposal would have
RE-CREATED it: the patch is `--- /dev/null` -> `+++ b/agents/MEMORY.md`. No gate
saw this, and none could have, because a DELETED NAME IS INVISIBLE TO EVERY
GATE BY DESIGN:

  * `familiar context links --check` gates on FIXABLE broken pointers and orphaned
    leaves only. `MEMORY.md` was written as a bare name, and bare names are
    informational on purpose -- there are 126 of them, and failing on all of
    them would bury the six that matter. It appeared in the report as
    `MEMORY.md x10` and exited 0. That is correct design and must not be
    "fixed" by turning the linker into noise.
  * nothing else reads a Python constant at all.

So the only available defence is the other direction: NOTHING MAY DEPEND ON A
NAME THAT NO LONGER EXISTS. `pazras.py` learned exactly this lesson one layer
up -- `ALWAYS_LOADED` now asserts each declared name is present, because the
budget check "stayed green against files that were gone" when USER.md and
MEMORY.md moved. That lesson was never generalised down to the rest of the
codebase's declared lists. This module is the generalisation, with one owner.

THE RULE is not "every declared path exists". Some are legitimately absent: a
deny-list names a tombstone precisely so it can never come back, and a
historical prefix is kept as evidence of a fix. And a third state was added by
the publication: a path this tree HAS and the published tree deliberately does
not, because the classification omits it. The rule is:

    EVERY DECLARED PATH EXISTS, OR IS DECLARED DELIBERATELY ABSENT WITH A
    REASON, OR IS DECLARED OMITTED FROM THE PUBLISHED TREE WITH A REASON.

A list silently containing a name nothing has checked is the bug. So is a
reason that has gone stale -- if a name declared absent comes BACK, the
declaration is wrong and this module says so, because a tombstone that has been
resurrected is the more dangerous of the two states. The third state is checked
in both directions for the same reason: an `omitted` entry that is missing HERE
is a claim about a tree that does not exist, and one that is present in the
export means the classification changed under it.

WHY IT DISCOVERS RATHER THAN ENUMERATES. A hand-written registry of lists has
the same defect as the lists it guards: a new one gets added and nobody notices.
So the constants are found by walking the AST of both packages for module-level
uppercase collections of path-shaped strings. A list found with no POLICY entry
is an ERROR -- the `checks.py --audit` idiom, one level down. Adding a
declared-path list therefore forces a decision about what its entries mean.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
AGENTS = REPO / "memory"

sys.path.insert(0, str(REPO / "engine"))
from lib import roots  # noqa: E402

# The publication classification. Named here because a finding that says "fix
# the classification" has to say where the classification is.
PUBLICATION = roots.DEV / "publication" / "publish.yaml"

PACKAGES = tuple(f"engine/{p}" for p in (
    "lib", "knowledge", "harness", "context", "consolidation", "cli"))

# The shell side, NAMED rather than discovered -- and that asymmetry is a
# measured decision, not laziness. Nine uppercase tables exist across
# `engine/**/*.sh`, and in eight of them the keys are directory NAMES and the
# values are `type:frequency:description` prose. Walking them the way the AST
# walk works would extract `dotfiles:Symlinked to B_Tech/dotfiles for version
# control` as a path, and the cost of a generic shell walk is therefore eight
# policies saying "this is prose" -- the noise failure this module warns about
# in `links --check`, imported into the one place that is supposed to be quiet.
#
# What a shell table declares is a FIELD, so the field is what is named. The
# limitation is real and stated here rather than hidden: a NEW table in a NEW
# shell file is not discovered, and nothing forces a policy for it. What is
# covered is the one table whose paths something depends on -- `PAZRAS_TIMERS`
# generates twenty systemd units, and `exec=` and `doc=` become `ExecStart=`
# and `Documentation=` in them.
#
# THIS IS THE GATE VIOLATION 6 NEEDED. `doc=` named
# `knowledge/operations/consolidation-cycle.md` for the 26 days after the leaf
# moved to `meta/`, and nothing could see it: `declared_paths` read Python only,
# and `links --check` walks `memory/` only, so a `engine/` file naming a moved
# leaf fell between the two. Both halves of that gap are closed by naming the
# field, not by widening the linker.
SHELL_FIELDS: dict[str, tuple[str, ...]] = {
    "config/structure/pazras-master-config.sh:PAZRAS_TIMERS": ("exec", "doc"),
}

# What a list's entries are measured against.
R_AGENTS = "memory"      # relative to memory/
R_REPO = "repo"          # relative to the repository root
R_HOME = "home"          # relative to `%h`, the systemd unit's home directory
R_ABS = "abs"            # already absolute, or resolved by the module itself

# What kind of thing the entries are.
K_EXISTS = "exists"      # a path; must be present unless excused below
K_NAMES = "names"        # a FILENAME filter; existence is meaningless
K_EXTERNAL = "external"  # outside this repo; nothing here can check it

# ── retired paths ────────────────────────────────────────────────────────────
#
# The inverse of everything above, and O2f's exit. A tombstone in `absent`
# says "this name must not come BACK"; these say "nothing may still POINT at
# it". The difference matters because a moved directory leaves no hole -- the
# reference simply resolves to nothing at the moment it is used, which for
# `source "$HOME/.pazras-system/core/pazras-config-loader.sh"` is 03:30 and for
# `bootstrap.sh` is a fresh machine that quietly enables no timers at all.
#
# O2f moved nine files and added NO COMPATIBILITY SHIM, on the reasoning that a
# shim becomes permanent and the caller list was small enough to exhaust. This
# is what makes that reasoning safe: a missed caller fails loudly in review
# instead of silently at 03:30.
#
# Scoped to TRACKED files (`git ls-files`). An untracked scratch file or a
# machine-local settings file is not the repository's claim about itself, and
# failing a shared gate on one would make the gate personal.
# R2e (2026-10-07): a setting left the engine for `config/<subject>/`, where
# a decision belongs. One reason for all of them.
R2E_WHY = (
    "R2e moved what the USER decided out of `engine/` into `config/<subject>/` "
    "(ontology SPECS R1k, R2e): the master config and the PARA READMEs "
    "to `config/structure/`, the backup and mirror excludes to "
    "`config/backup/`, the systemd units to `config/schedule/`, and the "
    "compiled `boundaries.json` to `config/boundaries/`. No shim.")

# R2c (2026-10-07): `scripts/` became `engine/<subject>/`. One reason for
# every old prefix, because they retired together.
# R2f (2026-10-07): the three pre-O2 branches. `meta/` and `operations/`
# became `system/<subject>/` and `tools/` became `system/harness/` (O2 dissolved
# them; R1d named the subjects). The old spelling sends a reader to a directory
# that is not there, which in a claim is a defect.
# R3a (2026-10-07): the subject ids were the last names from before R1d.
# `tree` became `knowledge`, `pass` became `consolidation` and `data` became
# `backup`, in the register and in the folders at once, because the folder is
# the label.
R3A_WHY = (
    "R1d renamed the subject and R3a moved its folder in the same commit "
    "(ontology SPECS R3a). The id is what a reference resolves to, so "
    "the old folder name is a directory nothing is filed under.")

R2F_WHY = (
    "O2 dissolved the branch; R2f repathed every live reference to "
    "`knowledge/system/<subject>/` (ontology SPECS R2f). The journal "
    "and dev/ keep the spelling because they are records, not claims, and a "
    "test's synthetic fixture is `RETIRED_SYNTHETIC`.")

# O6b (2026-10-09): `memory/skills/<category>/<name>/` became
# `memory/skills/<branch>/<subject>/<name>/` -- the same three branches and
# subjects the knowledge tree files under, with `category:` deleted in
# the same move (the subject is the path; `facets.yaml` declares `subject` as
# `where: path`, `derived_for: [skill]`, so no field is left to disagree with
# the folder).
#
# `skills/productivity/` is the one old category deliberately NOT listed here,
# and the reason is a live file: six imported skills carry the upstream
# provenance `skills/productivity/<name>` in `source:`, `upstream_path:` and
# their body pointer, because our category names mirrored the upstream repo's.
# A substring rule cannot tell the upstream path from the retired one, so the
# entry would refuse the record of where those skills came from. Named here so
# the omission is on the record rather than in it.
O6B_WHY = (
    "O6b filed every skill under `skills/<branch>/<subject>/`, so the old "
    "category folder it was in does not exist (ontology SPECS O6b). "
    "The subject is the path now, which is what retires the spelling.")

R2C_WHY = (
    "R2c moved `scripts/` to `engine/<subject>/` (ontology SPECS R1f, "
    "R1k): `scripts/memory/` split into `engine/{lib,knowledge,harness,"
    "context,consolidation,cli}/`, `scripts/shell/` became `engine/host/`, "
    "`scripts/mail/` was removed, and `pazras_memory`/`pazras_context` are no "
    "longer module names. No shim was added.")

R3B_WHY = (
    "R3b dissolved `agents/` (ontology SPECS R3b, R1k): the journal, "
    "knowledge and skills went to `memory/`, the registers to "
    "`config/knowledge/`, the boundaries to `config/boundaries/`, the user "
    "profile and conventions to `config/practice/`, the subagents to "
    "`config/harness/subagents/` (since moved to `config/orchestration/`), and the router to the repository root. "
    "`memory/` changes with use and `config/` when the user decides.")

RETIRED: dict[str, str] = {
    "scripts/core/":
        "split by O2f into `engine/checks/` (the threshold: what gates a "
        "commit) and `engine/structure/` (the bones: what the tree IS). It "
        "held two subjects, which is the same class of error as a leaf filed "
        "in the wrong branch.",
    "scripts/hooks/":
        "the pre-commit hook IS the threshold gate, so O2f filed it under "
        "`engine/checks/pre-commit` rather than in a directory named after "
        "the mechanism that happens to invoke it. `.git/hooks/pre-commit` is "
        "a symlink and was recreated by hand.",
    ".pazras-system/core/":
        "the stow'd spelling of the same split. `~/.pazras-system` was one "
        "symlink to `engine/`, so the segment moved with the directory; this "
        "entry exists because the sourcers spelled it this way and a grep for "
        "`scripts/core/` did not find them. The symlink itself was dropped "
        "2026-10-13: `familiar` is installed into `~/.local/bin` instead.",
    "06_SYSTEM/scripts": R2C_WHY,
    ".pazras-system/shell/": R2C_WHY,
    "pazras_memory": R2C_WHY,
    "pazras_context": R2C_WHY,
    "scripts/pazras-system": R2C_WHY,
    "scripts/README.md": R2C_WHY,
    "scripts/memory/": R2C_WHY,
    "scripts/context/": R2C_WHY,
    "scripts/shell/": R2C_WHY,
    "scripts/lib/": R2C_WHY,
    "scripts/checks/": R2C_WHY,
    "scripts/structure/": R2C_WHY,
    "scripts/boundaries/": R2C_WHY,
    "scripts/backup/": R2C_WHY,
    "scripts/generated/": R2C_WHY,
    "scripts/mail/": R2C_WHY,
    "engine/generated/systemd/": R2E_WHY,
    "engine/structure/pazras-master-config.sh": R2E_WHY,
    "engine/backup/backup-excludes.txt": R2E_WHY,
    "engine/backup/mirror-excludes.txt": R2E_WHY,
    "engine/boundaries/generated/": R2E_WHY,
    "06_SYSTEM/READMEs/": R2E_WHY,
    "knowledge/meta/": R2F_WHY,
    "knowledge/operations/": R2F_WHY,
    "knowledge/tools/": R2F_WHY,
    "knowledge/system/tree/": R3A_WHY,
    "knowledge/system/pass/": R3A_WHY,
    "knowledge/system/data/": R3A_WHY,
    "06_SYSTEM/agents": R3B_WHY,
    "agents/knowledge/": R3B_WHY,
    "agents/journal/": R3B_WHY,
    "agents/skills/": R3B_WHY,
    "agents/ontology/": R3B_WHY,
    "agents/boundaries/": R3B_WHY,
    "agents/user/": R3B_WHY,
    "agents/conventions/": R3B_WHY,
    "agents/subagents/": R3B_WHY,
    "agents/CONTEXT.md": R3B_WHY,
    "agents/AGENTS.md": R3B_WHY,
    "agents/README.md": R3B_WHY,
    "skills/development/": O6B_WHY,
    "skills/os/": O6B_WHY,
    "skills/research/": O6B_WHY,
    "skills/system/adopt-skill/": O6B_WHY,
    "skills/system/personalize-context/": O6B_WHY,
    "skills/system/prompt-engineering/": O6B_WHY,
    "PAZRAS_AGENTS_DIR": R3B_WHY,
}

# Where a retired path may still be NAMED, because naming is not depending.
# The journal is append-only -- rewriting it would falsify the record -- and
# `dev/` is this track's own working notes, which discuss the move by name.
# `config/knowledge/violations.yaml` records where a defect WAS.
# `memory/knowledge/system/consolidation/_data/` holds the ontology track's raw
# measurement envelopes (O4b, O4d, O5c): they quote the tree as it was when the
# run was made, and editing them would falsify the measurement.
#
# The last two are the register itself and its test: a list of retired names
# cannot be written without writing the names, and neither can the test that
# proves the list works. They are exempt for THAT reason and no other, which
# `test_only_the_register_and_its_test_are_exempt_from_themselves` pins -- so
# the exemption cannot quietly grow to cover a file that merely finds the gate
# inconvenient.
# A file that BUILDS a tree rather than pointing at this one: a test's
# fixture is synthetic data in `tmp_path`, and the third kind the SPECS item
# names -- "only shaped like paths". Demanding that a fixture mock the current
# layout would be this gate mistaking its subject. One rule, not a list of
# fifteen convenient files (which is what `RETIRED_EXEMPT` is guarded against).
RETIRED_SYNTHETIC = re.compile(r"(?:^|/)tests/|(?:^|/)test_[^/]*\.py$")

RETIRED_EXEMPT = ("memory/journal/", "dev/", "config/knowledge/violations.yaml",
                  "memory/knowledge/system/consolidation/_data/",
                  "engine/checks/declared_paths.py",
                  "engine/checks/tests/test_declared_paths.py")


@dataclasses.dataclass(frozen=True)
class Policy:
    """What one declared list means, and which of its entries may be missing.

    `absent` maps an entry to the sentence that justifies its absence. A reason
    is mandatory and is checked for being a sentence rather than a placeholder:
    the whole failure this module exists for is an absence nobody wrote down.

    `omitted` maps an entry to the sentence that justifies its absence FROM THE
    PUBLISHED TREE, where the entry is present in this one. `absent` says "this
    name is gone from the world"; `omitted` says "this name is ours, and the
    publication classification keeps it off the public tree". The two are
    checked against different trees, which is why they are two fields and not
    one with a flag: an `absent` entry that exists anywhere is a resurrected
    tombstone, and an `omitted` entry that is missing here is a claim about a
    tree that was never built.
    """

    kind: str
    root: str = R_AGENTS
    why: str = ""                      # required for K_NAMES and K_EXTERNAL
    absent: dict = dataclasses.field(default_factory=dict)
    omitted: dict = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        if self.kind in (K_NAMES, K_EXTERNAL) and not self.why:
            raise ValueError(f"kind {self.kind!r} requires a `why`")
        for field in (self.absent, self.omitted):
            for name, reason in field.items():
                if len(reason.split()) < 5:
                    raise ValueError(
                        f"the reason for {name!r} being absent is not a reason: "
                        f"{reason!r}")
        for name in set(self.absent) & set(self.omitted):
            raise ValueError(
                f"{name!r} is in both `absent` and `omitted`: the two answer "
                f"different questions -- gone from the world, or gone from "
                f"the published tree -- and one entry cannot be both")


# ── the policies ─────────────────────────────────────────────────────────────
#
# Keyed `module.path:CONSTANT`, where the module path is relative to the repo.
# Every reason below is copied from the decision that produced it, not invented
# here -- if this file and the module's own comment disagree, the module is the
# source and this is the bug.

POLICIES: dict[str, Policy] = {
    # -- the always-loaded set, in all four places that name it -------------
    # Repo-relative since R3b: the router sits at the root and the user's
    # directives under `config/practice/` (see `pazras.ALWAYS_LOADED`).
    "engine/context/navigation.py:ALWAYS_LOADED": Policy(K_EXISTS, root=R_REPO),
    "engine/context/navigation.py:CAPS": Policy(K_EXISTS, root=R_REPO),
    "engine/consolidation/posture.py:ALWAYS_LOADED": Policy(K_EXISTS, root=R_REPO),
    "engine/context/l1.py:PI_INLINE": Policy(K_EXISTS, root=R_REPO),
    "engine/context/l1.py:CLAUDE_ALREADY_HAS": Policy(K_EXISTS, root=R_REPO),
    # The two routers' lists of always-reachable pages. `read-write.md` is the
    # deny-list's own prose -- `read-write.yaml` and this document are omitted
    # together, because both spell out the paths this machine refuses to let a
    # model write.
    "engine/context/route.py:CANONICAL": Policy(
        K_EXISTS, root=R_REPO,
        omitted={
            "config/boundaries/read-write.md":
                "the prose half of the deny-list, omitted with the YAML half: "
                "both name the paths this machine's boundaries refuse, so the "
                "published tree carries neither."}),
    "engine/context/route.py:EXPECTED": Policy(
        K_EXISTS, root=R_REPO,
        omitted={
            "config/boundaries/read-write.md":
                "the same document as CANONICAL above, and omitted for the "
                "same reason: it is the prose half of this machine's "
                "deny-list."}),

    # -- write authority ----------------------------------------------------
    # `posture.DIRECTIVE` is gone from here in R3d: it is DERIVED from the
    # entity register now (`ontology.directive_dirs()`), so it is not a literal
    # an AST can read, and its existence is asserted by the check that uses it
    # rather than by a policy on a constant. What is left is the one literal:
    # the repo-root file no entity kind covers. The register is the source, and
    # `engine/boundaries/_boundaries.py` reads the same one for the harness
    # `ask` rules.
    "engine/consolidation/posture.py:DIRECTIVE_FILES": Policy(
        K_EXISTS, root=R_REPO,
        why="the directive files that are not an entity kind: `ROADMAP.md` is "
            "declared directive in the router and has no `pattern:`, so no "
            "derivation reaches it. A path here must EXIST -- it is a claim "
            "about the present, and the historical spellings the same check "
            "matches are deliberately not in this list.",
        omitted={
            "ROADMAP.md":
                "the roadmap plans THIS instance's tracks, with their dates and "
                "their open items, and the classification omits it: the "
                "published tree is steered by the README's own table instead."}),
    "engine/consolidation/posture.py:WRITABLE_ROOTS": Policy(
        K_EXISTS, root=R_REPO),
    "engine/consolidation/posture.py:GENERATED": Policy(
        K_EXISTS, root=R_REPO),
    "engine/consolidation/stages/conflict.py:DIRECTIVE": Policy(
        K_EXISTS,
        absent={"knowledge/conventions/":
                "same historical prefix as posture.DIRECTIVE, for the same "
                "reason: it names where the conventions used to live, so a "
                "leaf that still sits there is refused rather than marked."}),

    # -- the deny-list that produced this module ----------------------------
    "engine/consolidation/stages/consolidate.py:OFF_LIMITS": Policy(
        K_EXISTS,
        absent={
            "MEMORY.md":
                "a TOMBSTONE. Deleted 2026-09-04 when the always-loaded set "
                "moved into pazras-context's compiled L1. It is named here so "
                "that a model proposing it as a TARGET is refused -- which is "
                "exactly what stage 4 tried to do on 2026-09-10, with a patch "
                "reading `--- /dev/null`. If this file ever exists again, the "
                "entry is wrong and this check must fail.",
            "USER.md":
                "a TOMBSTONE, same move: its content is now "
                "`user/user-identity.md`, which is directive and capped. A "
                "proposal naming the old path must be dropped, not redirected.",
            "knowledge/conventions/":
                "the historical conventions prefix, as in conflict.DIRECTIVE "
                "-- kept so a stale proposal that names it is refused."}),

    # -- filename filters, where existence says nothing ---------------------
    "engine/knowledge/tree.py:SKIP_NAMES": Policy(
        K_NAMES, why="filenames matched anywhere in the tree, not paths. "
                     "`INDEX.md` exists at one place and `_subject.md` at "
                     "many; asking whether the NAME exists is not a question. "
                     "Imported rather than re-derived by conflict.py and "
                     "knowledge_index.py, which is what keeps them in step."),
    # The ontology's two reference routers. Not paths and not filenames: they are
    # the FIRST SEGMENT of a path, used to decide whether a reference is rooted
    # in the repository or in `memory/`, and whether it is inside the tree at
    # all. The ontology is also where the classes they name are declared, so a
    # directory appearing here and nowhere else is already reported by
    # `ontology check` -- which is the check that would notice one going.
    "engine/knowledge/ontology.py:AGENT_TOPS": Policy(
        K_NAMES, why="first path segments under memory/, not paths: the set "
                     "that decides whether `knowledge/x.md` means "
                     "`memory/knowledge/x.md`. Every entry is an entity home in "
                     "the same module's ENTITIES register, and "
                     "`ontology check` fails on a document under none of them."),
    "engine/knowledge/ontology.py:REPO_TOPS": Policy(
        K_NAMES, why="first path segments at the repository root, not paths: "
                     "`dev/`, `engine/` and `memory/` are how a reference is "
                     "told from one rooted in `memory/`. A missing directory "
                     "here is reported by `ontology.places_findings` (R2b) and by the "
                     "structural check, not by an existence test on a name."),
    "engine/consolidation/posture.py:GENERATED_NAMES": Policy(
        K_NAMES, why="`CONTEXT.md` by name, at every level of the tree: these "
                     "are routers regenerated whole by stage 7, so a pass "
                     "commit touching one is a derived artifact and not an "
                     "unattended prose edit."),
    "engine/context/links.py:EXEMPT_NAMES": Policy(
        K_NAMES, why="templates, matched by name wherever they sit. A template "
                     "is deliberately unreachable from any router, so it must "
                     "not be reported as an orphan."),
    "engine/context/links.py:EXTENSIONS": Policy(
        K_NAMES, why="file suffixes, not paths — the set of files the linker "
                     "will read at all."),
    "engine/context/links.py:ROOTS": Policy(
        K_EXISTS, root=R_REPO,
        # These are resolved per-directory by the linker rather than being two
        # paths, but both spellings exist at the tree root, so the check is
        # meaningful there and would catch the router being renamed.
    ),
    "engine/context/links.py:STRICT_SOURCES": Policy(
        K_EXISTS,
        # The files that receive the stricter pointer rule (a path that
        # resolves to nothing gates `links --check`). Existence is not a
        # formality here: a strict source that is renamed stops being checked,
        # and the check goes QUIET rather than red -- the more dangerous
        # direction, the same property that makes a `see:` target matter.
        omitted={
            "README.md":
                "this leaf says how THIS vault's memory tree is arranged, and "
                "the classification omits it with the journal and the "
                "Obsidian config: the export carries knowledge/ and skills/ "
                "and nothing above them."}),
    "engine/context/links.py:GENERATED_OUTPUTS": Policy(
        K_NAMES,
        why="basenames matched anywhere in the tree, not paths, so existence is "
            "not a question they can answer. `BRIEF.md` is the nightly pass's "
            "stable report name (memory/brief.py's NAME constant) and lives at "
            "journal/reports/BRIEF.md once a pass has run; its absence between "
            "runs is normal. tests/test_links.py mirrors the name against "
            "brief.py so a rename cannot leave a silent exemption behind."),

    # -- the shell side: what the twenty generated units point at -----------
    "config/structure/pazras-master-config.sh:PAZRAS_TIMERS": Policy(
        K_EXISTS, root=R_HOME,
        # `exec=` and `doc=` become `ExecStart=%h/...` and
        # `Documentation=file:%h/...` in `config/schedule/`. An
        # `exec=` that does not resolve is a timer that fails at 03:30 with
        # status 203; a `doc=` that does not resolve is silent, which is why it
        # was wrong for 26 days. Both are checked, and neither may be excused
        # without a reason -- the generated units are not the record, this
        # table is.
    ),

    # -- outside this repo --------------------------------------------------
    "engine/consolidation/stages/replay.py:EXCLUDE_CWD": Policy(
        K_EXTERNAL, why="PAZRAS Areas in the user's HOME, not in this "
                        "repository, and the point of the list is that the "
                        "pass must never read them. Checking they exist would "
                        "mean stat-ing paths this code is forbidden to touch — "
                        "see config/boundaries/. An Area that is renamed stops "
                        "being excluded silently; that is a real risk and it "
                        "is accepted here rather than hidden, because the "
                        "alternative is worse."),
}


@dataclasses.dataclass
class Finding:
    where: str
    detail: str
    level: str = "error"


# ── discovery ────────────────────────────────────────────────────────────────

def _path_shaped(values) -> bool:
    """Is this collection of strings about files at all?

    Deliberately generous: a false positive costs one POLICY entry saying "these
    are not paths", which is cheap and is itself a useful record. A false
    negative is a list nobody checks, which is the bug.
    """
    return any("/" in v or v.endswith((".md", ".py", ".json", ".sh", ".jsonl",
                                       ".yaml", ".yml", ".txt", ".bash"))
               for v in values)


def discover(repo: pathlib.Path = REPO) -> dict[str, list[str]]:
    """`{module.py:CONSTANT: [entries]}` for every declared path list.

    Reads the AST rather than importing: the two packages are separate sys.path
    roots with no common parent, and importing both to read two constants would
    make this check depend on the pass being importable — which is the thing it
    is supposed to be able to run before.
    """
    found: dict[str, list[str]] = {}
    for pkg in PACKAGES:
        for p in sorted((repo / pkg).rglob("*.py")):
            try:
                tree = ast.parse(p.read_text())
            except (OSError, SyntaxError):
                continue
            for node in tree.body:
                if not isinstance(node, ast.Assign):
                    continue
                for target in node.targets:
                    if not isinstance(target, ast.Name) or not target.id.isupper():
                        continue
                    values = _strings(node.value)
                    if values and _path_shaped(values):
                        rel = p.relative_to(repo).as_posix()
                        found[f"{rel}:{target.id}"] = values
    found.update(_shell_fields(repo))
    return found


_ROW = re.compile(r'^\s*\["([^"]+)"\]\s*=\s*"(.*)"\s*$')

# A file the classification RENAMES rather than omits: it ships as an EXAMPLE,
# with the same shape and the same table, and its values templated. The key in
# `SHELL_FIELDS` and `POLICIES` stays the INSTANCE's spelling in both trees, so
# one policy covers one file; resolving the name is what keeps "a policy with no
# constant behind it" meaning what it says, in the tree that ships the file.
#
# No separate check is needed for this map, because both ways it can go wrong
# are already covered: if the classification changes the name, the read fails
# and the policy-without-a-source warning fires, and a target that also existed
# in the instance would be a new tracked path, which `publish-audit` fails on.
RENAMED = {
    "config/structure/pazras-master-config.sh":
        "config/structure/pazras-master-config.example.sh",
}


def source_text(key: str, repo: pathlib.Path = REPO) -> str | None:
    """The text of the file a `<path>:<TABLE>` key names, or None.

    The instance's own name wins where it exists, so this tree reads its own
    file and never the example beside it; the rename is followed only where the
    declared path is absent, which is the generated tree. A caller that gets
    None has a real absence to report.
    """
    rel = key.rsplit(":", 1)[0]
    for name in (rel, RENAMED.get(rel)):
        if name is None:
            continue
        try:
            return (repo / name).read_text()
        except OSError:
            continue
    return None


def _shell_fields(repo: pathlib.Path) -> dict[str, list[str]]:
    """`{file:TABLE: [paths]}` for the named fields of each shell table.

    A row is `["unit"]="k=v;k=v;..."`, so the paths are in the VALUES, not the
    keys -- the opposite of the dict convention in `_strings`, where a key is
    the declared path and the value is a number. An `exec=` carries arguments
    (`familiar backup verify 5%%`), so only its first token is a path.

    A named table that has gone missing is not silently skipped: the key is
    absent from the result, and `check` already reports a policy with no
    constant behind it.
    """
    out: dict[str, list[str]] = {}
    for key, fields in SHELL_FIELDS.items():
        rel, table = key.rsplit(":", 1)
        text = source_text(key, repo)
        if text is None:
            continue
        lines = text.splitlines()
        inside = False
        paths: list[str] = []
        for line in lines:
            if re.match(rf"^\s*(declare\s+(-\w+\s+)*)?{table}=\(", line):
                inside = True
                continue
            if inside:
                if line.strip() == ")":
                    break
                row = _ROW.match(line)
                if not row:
                    continue
                for part in row.group(2).split(";"):
                    name, _, value = part.partition("=")
                    if name.strip() in fields and value.strip():
                        paths.append(value.split()[0])
        if inside:
            out[key] = paths
    return out


def _strings(value) -> list[str]:
    """The string entries of a literal collection; dict KEYS for a dict.

    A dict's keys are the declared paths (`CAPS` maps a path to its cap); its
    values are numbers and say nothing about the tree.
    """
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        elts = value.elts
    elif isinstance(value, ast.Dict):
        elts = value.keys
    else:
        return []
    return [e.value for e in elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)]


# ── the check ────────────────────────────────────────────────────────────────

def _where(path: pathlib.Path, repo: pathlib.Path) -> str:
    """The path as the reader should see it: repo-relative, or absolute.

    An R_HOME entry resolves outside the repository as soon as one names
    something other than `06_SYSTEM/...` -- `%h/.local/bin/x` is a legitimate
    `exec=`. `relative_to` RAISES there, so the reporting path would crash on
    exactly the entry it was added to report.
    """
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve(entry: str, root: str, repo: pathlib.Path) -> pathlib.Path:
    # R_HOME: the units write `%h/<entry>`, and the repository is the HOME
    # directory the master config calls the SYSTEM's (`PAZRAS_STRUCTURE`:
    # `["06_SYSTEM"]="system:…"`). So an entry spells the install's own name
    # first -- `06_SYSTEM/engine/familiar` -- and the rest of it is
    # repo-relative.
    #
    # RESOLVING EVERY R_HOME ENTRY AGAINST `repo.parent` IS WHAT BROKE AWAY
    # FROM `~/06_SYSTEM`, and it is right only while the repository is named
    # `06_SYSTEM` and sits in $HOME. From a linked worktree (measured
    # 2026-10-14, `dev/publication/2026-10-14_recut.md` §2) the same entry
    # asked for `…/worktrees/06_SYSTEM/engine/familiar` and the check reported
    # 14 paths as missing: a gate describing a tree that does not exist rather
    # than a repository that is wrong. A stranger's clone at any other path had
    # the same failure with no way to read it. An entry that does NOT start
    # with the system directory is genuinely outside the repository
    # (`%h/.local/bin/x`) and still resolves against the parent.
    if root == R_HOME:
        install = _install_home(repo)
        if install and (entry == install or entry.startswith(install + "/")):
            return repo / entry[len(install):].lstrip("/")
        return repo.parent / entry.rstrip("/")
    base = {R_AGENTS: repo / "memory", R_REPO: repo}[root]
    return base / entry.rstrip("/")


# The one table whose `exec=`/`doc=` paths become `%h`-relative systemd
# directives, and therefore the one place that has to know what the repository
# is called at `$HOME`. Read from the same file the paths come from, so a
# rename of the system directory is one edit and not two.
_SYSTEM_HOME = re.compile(r'^\s*\["([^"]+)"\]="system:', re.M)


def _install_home(repo: pathlib.Path) -> str | None:
    """The directory name the master config gives the repository itself.

    `None` when that file is not readable (a unit-test fixture, a tree that
    has not got that far), which leaves the `repo.parent` resolution in place
    rather than inventing a name from nothing.
    """
    key = next(iter(SHELL_FIELDS), "")
    text = source_text(key, repo) if key else None
    if text is None:
        return None
    m = _SYSTEM_HOME.search(text)
    return m.group(1) if m else None


# A retired name must START a path segment: `subagents/CONTEXT.md` contains
# `agents/CONTEXT.md` and names a live file (found when R3b retired the
# vault's old name). A left boundary can only remove findings, never add one.
_RETIRED_AT = {dead: re.compile(r"(?<![\w-])" + re.escape(dead))
               for dead in RETIRED}


def retired_findings(repo: pathlib.Path = REPO) -> list[Finding]:
    """Every tracked file that still points at a path O2f retired.

    Reads the file list from git rather than walking, so the check is about
    what the repository CLAIMS and not about whatever happens to be lying in
    the working tree -- and falls back to the walk in a tree that is not a
    checkout, which is what a published tree is. A gate that silently becomes a
    no-op is the failure mode this whole module was written for, so the fallback
    reports which answer it got rather than an empty list.
    """
    try:
        if not pathlib.Path(repo).is_dir():
            raise OSError(f"no directory at {repo}")
        names = roots.tracked(None, repo)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [Finding("RETIRED", f"cannot list tracked files ({exc}), so the "
                                   "retired-path check did not run", "warn")]
    findings = []
    for name in names:
        if not name or any(name.startswith(x) or name == x
                           for x in RETIRED_EXEMPT):
            continue
        if RETIRED_SYNTHETIC.search(name):
            continue
        p = repo / name
        try:
            text = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for dead, why in RETIRED.items():
                if _RETIRED_AT[dead].search(line):
                    findings.append(Finding(
                        f"{name}:{lineno}",
                        f"names the retired path `{dead}` -- {why} "
                        f"O2f added no compatibility shim, so this reference "
                        f"resolves to nothing the moment it is used."))
    return findings


def check(repo: pathlib.Path = REPO) -> list[Finding]:
    findings: list[Finding] = []
    found = discover(repo)

    for key in sorted(set(found) - set(POLICIES)):
        findings.append(Finding(
            key,
            f"declares path-shaped strings and has no policy: "
            f"{', '.join(found[key])}. Say in engine/checks/declared_paths.py "
            f"what these are — paths that must exist, filenames, or something "
            f"outside this repo — so that a name going missing cannot pass "
            f"silently. This is how memory/MEMORY.md stayed live for a week "
            f"after it was deleted."))

    for key in sorted(set(POLICIES) - set(found)):
        findings.append(Finding(
            key,
            "has a policy but no longer exists in the source. Either the "
            "constant was renamed — in which case this policy is now guarding "
            "nothing — or it was removed and the entry is stale.", "warn"))

    for key in sorted(set(found) & set(POLICIES)):
        pol = POLICIES[key]
        if pol.kind in (K_NAMES, K_EXTERNAL):
            continue
        mine = roots.instance_here()
        for entry in found[key]:
            path = _resolve(entry, pol.root, repo)
            if entry in pol.omitted:
                # The classification omits it, so the two trees disagree BY
                # DESIGN -- and each disagreement has a name. Missing HERE is a
                # claim about a tree that was never built; present in the EXPORT
                # means the classification moved and this register did not.
                if path.exists() and not mine:
                    findings.append(Finding(
                        key,
                        f"`{entry}` is declared omitted from the published "
                        f"tree, and it is HERE. This is a generated tree, so "
                        f"the classification is not omitting it any more -- "
                        f"either fix the classification in "
                        f"{roots.rel(PUBLICATION)} or drop the entry from "
                        f"`omitted`."))
                elif not path.exists() and mine:
                    findings.append(Finding(
                        key,
                        f"`{entry}` is declared omitted from the published "
                        f"tree, and this checkout does not have it either. The "
                        f"reason on record is "
                        f"\"{pol.omitted[entry]}\" -- and it can only be "
                        f"true of a path that exists here."))
                continue
            excused = entry in pol.absent
            if path.exists() and excused:
                findings.append(Finding(
                    key,
                    f"`{entry}` is declared deliberately absent, and it "
                    f"EXISTS. The reason on record is stale: \"{pol.absent[entry]}\" "
                    f"A resurrected tombstone is the dangerous direction — "
                    f"something is now reachable that a list says is gone."))
            elif not path.exists() and not excused:
                findings.append(Finding(
                    key,
                    f"`{entry}` does not exist ({_where(path, repo)}). "
                    f"Either restore it, drop it from the list, or declare it "
                    f"deliberately absent with the reason, in "
                    f"engine/checks/declared_paths.py."))
    findings += retired_findings(repo)
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="declared_paths")
    ap.add_argument("--list", action="store_true",
                    help="print every declared list and its policy")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    found = discover()
    if args.list:
        for key in sorted(found):
            pol = POLICIES.get(key)
            kind = pol.kind if pol else "!! NO POLICY"
            print(f"  {kind:9} {key}")
            for entry in found[key]:
                marks = []
                if pol and entry in pol.absent:
                    marks.append("absent(ok)")
                if pol and entry in pol.omitted:
                    marks.append("omitted(published)")
                mark = " ".join(marks)
                print(f"            {entry:42} {mark}")
        return 0

    findings = check()
    errors = [f for f in findings if f.level == "error"]
    for f in findings:
        print(f"  {f.level.upper():5} {f.where}")
        print(f"        {f.detail}")
    print(f"\ndeclared paths: {len(found)} list(s), "
          f"{sum(len(v) for v in found.values())} entr(ies), "
          f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
