"""posture -- the memory-poisoning threat model, as checks. L9; the leaf is
memory/knowledge/system/consolidation/memory-poisoning-posture.md.

THE THREAT, in one sentence: persistent auto-written memory converts a
one-shot prompt injection into a STATEFUL compromise -- text an attacker got
into one session is distilled, stored, and read back as this system's own
belief in every session after (arXiv 2607.06595). The input is not
hypothetical: every staged transcript quotes web pages, repositories, issue
threads and tool output, and stage 1 sends all of it to a model whose answer is
committed unattended. WHICH model is the one seam that changes this sentence:
`config/profile.yaml`'s `models.consolidation` ships local (P5), so nothing
leaves the machine until its owner points it at a provider -- a deliberate act
with a stated cost, and not a property of the pass.

THE POSTURE IS AUTHORITY, NOT DETECTION. There is no reliable classifier for
"this paragraph is an injection", and a check that claimed to be one would
manufacture exactly the distractor noise this posture exists to remove -- the same
reasoning that keeps stage 5d from guessing at semantic contradictions. So
nothing here scans text for badness. What it checks is the four structural
properties that make a successful injection INERT, each of which is a fact
about paths and provenance, and each of which fails loudly:

  1. Nothing machine-written is injected.   An injected leaf must still be
     FETCHED by a model that chose to. L2 removed blanket injection; this check
     is what keeps it removed, by intersecting the always-loaded set with the
     set of paths the nightly pass has actually written in its own history.
  2. Promotion is human-gated.              `trust: trusted` is the label that
     turns provisional text into established fact. No stage may write it
     (frontmatter.PROMOTED_TRUST); this asserts the refusal behaviourally.
  3. The curator never edits prose unattended. Every pass commit under
     `knowledge/**` must be a FRONTMATTER change. Body text arrives only as a
     stage-4 patch a human applies -- so the one path from a model's words to a
     leaf's prose runs through a person.
  4. Directive paths are untouched.         Evidence from history, not from the
     OFF_LIMITS tuple that claims it.

And one labelling property, which is what makes a poisoned entry survivable
rather than merely rare:

  5. Machine-written journal entries are marked as such (`distilled_by:`), so
     retrieval can tell a session that a passage is an unreviewed distillation
     of a transcript rather than something a human wrote.

WHY NOT SWAP IN A MEMORY PRODUCT. Explicitly rejected by the L9 ROADMAP line
and by `knowledge/system/consolidation/prior-art-memory-systems.md`: no architecture dominates
(arXiv 2606.24775), and Mem0/Zep/MemOS each reinstate the authority inversion
these five checks exist to prevent -- an LLM curator with unreviewed write
access to every future prompt.

FINDINGS, NOT EXCEPTIONS. Every check returns a Finding or None and never
raises; `check()` returns the list. A posture failure is reported into the
night's report and the brief, and does NOT abort the pass: the pass's writes
are already constrained by the mechanisms being checked, so aborting would
remove the report that says the constraint slipped.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
import sys

from knowledge import frontmatter, ontology
from lib import git, invocation
from lib import roots

# The always-loaded set: the only bytes under `memory/` that reach a model's
# context without the model asking for them. Mirrored from
# `engine/context/navigation.py` ALWAYS_LOADED, and the mirror is
# itself check 1's first assertion -- a file added there and not here would
# otherwise silently widen the injected surface.
ALWAYS_LOADED = ("CONTEXT.md",
                 "config/practice/user/user-identity.md",
                 "config/practice/conventions/collaboration.md")
CONTEXT_SOURCE = roots.ENGINE / "context/navigation.py"

# How the nightly pass names its own commits (run._commit). Preflight's
# `wip: pre-sleep snapshot` is deliberately NOT here: it commits the HUMAN's
# uncommitted work, so its paths say nothing about what the pass writes.
PASS_COMMIT_GREP = "^memory: nightly consolidation"
HISTORY_LIMIT = 60

# The directive paths, ASKED OF THE ENTITY REGISTER (`entities.yaml`), and
# prefix-matched against repo-relative paths. R3d: this was a tuple, which is a
# second register -- it could not know that a kind had been added, moved or
# stopped being marked directive, and after R3b it named paths that had already
# left. `DIRECTIVE_FILES` is the part no entity kind covers: a repo-root file the
# router declares directive, which is a declaration in `CONTEXT.md` rather than
# a register entry.
DIRECTIVE_FILES = ("ROADMAP.md",)


def directive_prefixes() -> tuple:
    """Every path property 4 protects: the register's directories, plus the
    repo-root files no entity kind covers.

    A FUNCTION, not a constant, and that is the R3d point twice over: the
    register can change under a running process, and a frozen tuple is a
    register nobody can update without restarting the pass.
    """
    return ontology.directive_dirs() + DIRECTIVE_FILES

# THE BRIDGE. A pass commit is a record, and the paths in it are the paths of
# its DATE -- so a path a later move renamed is still what history says. These
# are those spellings: where the directive files lived when a pass commit wrote
# them. Built from the vault's name before R3b, spelled here and in
# `pointers.PRE_R3B`, because `declared_paths.RETIRED` refuses the literal
# everywhere else -- this is a record of where a breach WAS, which is what a
# retired path is FOR, and the one thing that check cannot tell apart from a
# live dependency. Deliberately not a declared path list: `declared_paths` asks
# about the present, and these are absent by design.
#
# THE EVIDENCE IS WHY IT IS KEPT. `86ddb90` (2026-08-31) is the single
# historical breach this check knows about: the pass wrote `verified_log:` into
# three convention files. Without the bridge, R3b's repath of the constant made
# that finding vanish -- and the check reported a clean history it had not
# verified, which is worse than reporting nothing.
_HISTORICAL_VAULT = "agents"          # the vault's name before R3b
DIRECTIVE_HISTORICAL = (f"{_HISTORICAL_VAULT}/knowledge/conventions/",)

# What a writing stage can reach at all: `tree.documents` walks exactly these
# two, so a directive path is out of reach precisely while it is outside them.
# That is the STRUCTURAL protection, and check 4's live half asserts it.
WRITABLE_ROOTS = ("memory/knowledge/", "memory/skills/")

# Generated whole by stage 7, so their bodies legitimately change under a pass
# commit. They are derived artifacts rather than claims, and are read on demand
# rather than injected -- outside check 3's subject by name, not by a
# line-shaped heuristic that would also hide a real prose edit.
GENERATED = ("memory/knowledge/INDEX.md",)
GENERATED_NAMES = ("CONTEXT.md",)

# A `knowledge/**` diff line the pass is allowed to make: a frontmatter key, or
# the `---` fence itself. Anything else is prose, and prose is check 3's whole
# subject. `-` and `+` are treated identically -- a deletion of prose is as much
# an unattended edit as an insertion.
_FM_LINE = re.compile(r"^[+-](?:---\s*$|[a-z_]+:)")


@dataclasses.dataclass
class Finding:
    check: str
    detail: str
    level: str = "error"           # error | warn


# -- 1. nothing machine-written is injected ----------------------------------

def check_injected_surface(repo: pathlib.Path) -> list[Finding]:
    out: list[Finding] = []
    try:
        src = CONTEXT_SOURCE.read_text()
    except OSError:
        out.append(Finding("injected-surface",
                           f"cannot read {CONTEXT_SOURCE} to confirm the "
                           f"always-loaded set; this check is unverified",
                           "warn"))
        declared = set(ALWAYS_LOADED)
    else:
        m = re.search(r"ALWAYS_LOADED\s*=\s*\(([^)]*)\)", src)
        declared = set(re.findall(r"[\"']([^\"']+)[\"']", m.group(1))) if m else set()
        if not m:
            out.append(Finding("injected-surface",
                               "ALWAYS_LOADED not found in "
                               f"{CONTEXT_SOURCE.name}; the injected set cannot "
                               f"be confirmed", "warn"))
        elif declared != set(ALWAYS_LOADED):
            out.append(Finding(
                "injected-surface",
                f"the always-loaded set has drifted: familiar-context compiles "
                f"{sorted(declared)}, this check knows {sorted(ALWAYS_LOADED)}. "
                f"Reconcile before trusting the rest of this check."))
    written = machine_written(repo)
    for rel in sorted(declared or set(ALWAYS_LOADED)):
        full = rel
        if full in written:
            out.append(Finding(
                "injected-surface",
                f"`{full}` is injected into every session AND has been written "
                f"by the nightly pass ({written[full]}). Machine-written text "
                f"is reaching prompts unasked -- the configuration L2 removed."))
    return out


def machine_written(repo: pathlib.Path) -> dict[str, str]:
    """repo-relative path -> the pass commit that most recently wrote it.

    Evidence, not declaration: what a stage's constants say it writes and what
    history shows it wrote are exactly the two things a drifting control makes
    disagree.
    """
    out: dict[str, str] = {}
    for c in git.commits_matching(repo, PASS_COMMIT_GREP, HISTORY_LIMIT):
        for p in c.paths:
            out.setdefault(p, f"{c.sha}, {c.date}")
    return out


# -- 2. promotion is human-gated ---------------------------------------------

def check_promotion_gate() -> list[Finding]:
    """Behavioural, not a grep: call the write path and require the refusal.

    A grep for the constant would pass on a build where the guard was moved,
    renamed or short-circuited -- which is the only way this control realistically
    fails, since nothing writes `trusted` today.
    """
    sample = "---\ntitle: probe\ntrust: trial\n---\nbody\n"
    for value in frontmatter.PROMOTED_TRUST:
        try:
            frontmatter.set_fields(sample, {"trust": value})
        except frontmatter.PromotionRefused:
            continue
        except Exception as exc:                       # noqa: BLE001
            return [Finding("promotion-gate",
                            f"writing `trust: {value}` raised "
                            f"{type(exc).__name__} instead of PromotionRefused; "
                            f"the gate is not the thing stopping it")]
        return [Finding("promotion-gate",
                        f"`frontmatter.set_fields` accepted `trust: {value}`. "
                        f"A stage can now promote its own text to established "
                        f"fact without a human.")]
    return []


# -- 3. the curator never edits prose unattended -----------------------------

def check_curator_writes(repo: pathlib.Path) -> list[Finding]:
    out: list[Finding] = []
    for c in git.commits_matching(repo, PASS_COMMIT_GREP, HISTORY_LIMIT):
        for path in c.paths:
            if not path.startswith(roots.rel(roots.KNOWLEDGE) + "/") or not path.endswith(".md"):
                continue
            if path in GENERATED or path.rsplit("/", 1)[-1] in GENERATED_NAMES:
                continue
            prose = [l for l in git.diff_lines(repo, c.sha, path)
                     if l[1:].strip() and not _FM_LINE.match(l)]
            if prose:
                out.append(Finding(
                    "curator-writes",
                    f"pass commit `{c.sha}` ({c.date}) changed PROSE in "
                    f"`{path}`, not just frontmatter — {len(prose)} line(s), "
                    f"first: {prose[0][:80]!r}. Stage 4 is proposal-only; a body "
                    f"edit must arrive as a patch a human applies."))
    return out[:5]


# -- 4. directive paths are untouched ----------------------------------------

def check_directives(repo: pathlib.Path) -> list[Finding]:
    """Three halves, because "it happened", "it can happen" and "the register and
    the tree disagree" are different claims.

    MISSING (error): a directory the register calls directive and the tree does
    not hold. The register is the user's declaration, so this is the check that
    it still describes the tree. When the paths were a tuple, `declared_paths`
    asserted their existence instead; R3d moved the assertion here, where the
    subject lives, rather than leaving it on a constant that no longer exists.

    LIVE (error): a directive path that still exists INSIDE a writable root is
    reachable by a writing stage tonight. Since R3b the directive kinds live
    under `config/**`, which no writing stage walks, so this half holds
    STRUCTURALLY -- and it is now evaluated over the register's directories,
    which are the `config/**` ones.

    HISTORICAL (warn): a pass commit that once wrote a directive path, matched
    in the spelling of ITS date (`DIRECTIVE_HISTORICAL`). It cannot be undone
    and re-reporting it as an error every night is the repeats-its-own-settled-
    findings failure `consolidation-cycle.md` names, so it is recorded at `warn`
    and says whether the exposure still exists.
    """
    out = []
    prefixes = directive_prefixes()
    for owned in ontology.directive_dirs():
        if not (repo / owned).is_dir():
            out.append(Finding(
                "directive",
                f"`{owned}` is declared directive in the entity register and "
                f"does not exist. Either the kind moved and its pattern did "
                f"not, or the directory went and the register still claims it."))
    for owned in prefixes:
        if not (repo / owned).exists():
            continue
        if owned.startswith(WRITABLE_ROOTS):
            out.append(Finding(
                "directive",
                f"`{owned}` is directive ({roots.MEMORY_REL}/README.md §4) and sits inside "
                f"`{[r for r in WRITABLE_ROOTS if owned.startswith(r)][0]}`, "
                f"which `tree.documents` walks — a writing stage can reach it. "
                f"Move it out of the scored tree, as the conventions were."))
    breaches = sorted((p, w) for p, w in machine_written(repo).items()
                      if p.startswith(prefixes + DIRECTIVE_HISTORICAL))
    if breaches:
        listed = "; ".join(f"`{p}` ({w})" for p, w in breaches[:4])
        still = [p for p, _ in breaches if (repo / p).exists()
                 and p.startswith(WRITABLE_ROOTS)]
        out.append(Finding(
            "directive",
            f"{len(breaches)} directive path(s) were written by a past pass: "
            f"{listed}"
            + ("" if not breaches[4:] else f" and {len(breaches) - 4} more")
            + (f". {len(still)} of them are STILL inside the scored tree."
               if still else
               ". None is still inside the scored tree — the exposure was closed "
               "by moving those files out of it, not by a rule."),
            "warn"))
    return out[:6]


# -- 5. machine-written journal entries are marked ----------------------------

def check_journal_provenance(agents: pathlib.Path, limit: int = 40) -> list[Finding]:
    """Entries carrying neither `distilled_by:` nor an authored marker.

    This is the labelling control, and its value is what it lets RETRIEVAL say:
    a passage a session gets back can be flagged as an unreviewed distillation
    of a transcript rather than as something a human wrote. An unmarked entry
    defeats that, so it is a `warn` -- a gap in labelling, not a breach.
    """
    root = agents / "journal"
    if not root.is_dir():
        return []
    unmarked = []
    entries = sorted((p for p in root.rglob("*.md")
                      if "reports" not in p.relative_to(root).parts
                      # Routers and READMEs are navigation, not entries; they
                      # have no session to be distilled from and carrying a
                      # `distilled_by:` would be a lie.
                      and p.name not in ("CONTEXT.md", "README.md")),
                     reverse=True)[:limit]
    for p in entries:
        fm = frontmatter.read(p)
        # `session:` counts: an entry naming the session it came from is
        # traceable to a transcript, which is the fact a reader needs. It is
        # what pre-2026-09 entries carry instead of `distilled_by:`, and the
        # MCP server's `_provenance` reads the same two fields in the same
        # order -- the label and the check must not disagree about what marked
        # means.
        if not (fm.get("distilled_by") or fm.get("session")
                or fm.get("author") or fm.get("origin")):
            unmarked.append(p)
    if not unmarked:
        return []
    rels = ", ".join(f"`{p.relative_to(agents.parent).as_posix()}`"
                     for p in unmarked[:4])
    return [Finding(
        "journal-provenance",
        f"{len(unmarked)} of the {len(entries)} most recent journal entries "
        f"carry no provenance field (`distilled_by:`), so retrieval cannot tell "
        f"a session whether the text was distilled by a model or written by a "
        f"human: {rels}", "warn")]


# -- the gate ----------------------------------------------------------------

CHECKS = ("injected-surface", "promotion-gate", "curator-writes",
          "directive", "journal-provenance")


def check(repo, agents) -> list[Finding]:
    """Every check, in declaration order. Never raises."""
    repo, agents = pathlib.Path(repo), pathlib.Path(agents)
    out: list[Finding] = []
    for fn in (lambda: check_injected_surface(repo),
               check_promotion_gate,
               lambda: check_curator_writes(repo),
               lambda: check_directives(repo),
               lambda: check_journal_provenance(agents)):
        try:
            out += fn()
        except Exception as exc:                       # noqa: BLE001
            out.append(Finding("posture", f"a check raised "
                                          f"{type(exc).__name__}: {exc}", "warn"))
    return out


def run(ctx) -> None:
    """Called by the pass (stage 8). Findings become report notes.

    Deliberately NOT a gate. The pass's writes are constrained by the very
    mechanisms this checks, so aborting on a finding would delete the report
    that says the constraint slipped -- and the finding is about history, which
    aborting cannot undo.
    """
    findings = check(ctx.repo, ctx.agents)
    if not findings:
        ctx.note("8", f"security posture: {len(CHECKS)} checks pass "
                      f"({', '.join(CHECKS)}) — "
                      f"knowledge/system/consolidation/memory-poisoning-posture.md")
        return
    for f in findings:
        ctx.note("8", f"security posture · {f.check}: {f.detail}", f.level)


# -- the vault contract (P1) ---------------------------------------------------
#
# WHAT A SECOND INSTALL NEEDS BEFORE ANYTHING ELSE: which paths the engine
# expects, which it rewrites, which the nightly pass may touch and which belong
# to the person. Those facts were already here and in the registers -- the
# always-loaded set, the directive paths, the writable roots, the generated
# files -- so the contract is DERIVED from them, never written beside them
# (`dev/publication` design round 1, Q5). A hand-written copy would be the
# fourth statement of the same rules, and the first one to drift.
#
# ON DRIFT, REFUSE. A generated file a person has edited is not overwritten
# silently; its generator's `--check` reports the drift and the person decides.
# That is the rule the contract states for every generated path, and the one
# this file's own generator follows: `vault --check` exits 3 on drift, and
# without `--write` nothing is written.

VAULT_FILE = roots.VAULT_EXAMPLE
VAULT_HEADER = (f"# {VAULT_FILE.name} -- the vault contract, GENERATED by "
                "`familiar consolidation vault --write`.\n"
                f"# Do not hand-edit: it is derived from {roots.rel(pathlib.Path(__file__))}, "
                f"{roots.rel(roots.LIB)}/roots.py\n"
                f"# and {roots.rel(roots.ONTOLOGY)}/{{entities,subjects}}.yaml, and "
                "`vault --check` fails on drift.\n")


# How a generated markdown file says so in its own first lines -- the marker
# every generator here writes (`<!-- GENERATED from … -->`,
# `<!-- GENERATED FILE — do not hand-edit -->`). Asking the files is the
# derivation: a generator added later is in the contract the day its first
# output is committed, with no list here to update.
_GENERATED_MARK = "<!-- GENERATED"


def _generated() -> list:
    """Every path a generator rewrites whole: the pass's own (GENERATED, and
    the routers by name under each writable root), every markdown file under
    `config/` and the writable roots that declares itself generated in its
    header, and the compiled boundary target, which is JSON and cannot."""
    out = list(GENERATED) + [f"{r}**/{n}" for r in WRITABLE_ROOTS for n in GENERATED_NAMES]
    for top in [roots.CONFIG] + [roots.REPO / r for r in WRITABLE_ROOTS]:
        for path in sorted(top.rglob("*.md")):
            rel = roots.rel(path)
            if path.name in GENERATED_NAMES or rel in out:
                continue
            try:
                head = path.read_text(encoding="utf-8").split("\n", 5)[:5]
            except (OSError, UnicodeDecodeError):
                continue
            if any(line.startswith(_GENERATED_MARK) for line in head):
                out.append(rel)
    if roots.BOUNDARIES_JSON.exists():
        out.append(roots.rel(roots.BOUNDARIES_JSON))
    return out


def vault_contract() -> dict:
    """The contract as a mapping, in the order a reader needs it."""
    homes = {name.lower(): roots.rel(getattr(roots, name)) + ("" if getattr(roots, name).suffix else "/")
             for name in ("ROUTER", "JOURNAL", "KNOWLEDGE", "SKILLS", "ONTOLOGY",
                          "BOUNDARIES", "USER", "CONVENTIONS", "SUBAGENTS")}
    return {
        "version": "1",
        "on_drift": "refuse",
        "homes": homes,
        "always_loaded": list(ALWAYS_LOADED),
        "human_owned": list(directive_prefixes()),
        "machine_writable": list(WRITABLE_ROOTS),
        "generated": _generated(),
        "places": {s.id: [p + "/" for p in s.places]
                   for s in ontology.subjects() if s.places},
    }


def render_vault(contract: dict) -> str:
    """The contract as `_miniyaml`'s subset: block mappings and sequences."""
    notes = {
        "on_drift": "a generated file a person edited is reported, never overwritten",
        "homes": f"the named homes the engine opens ({roots.rel(roots.LIB)}/roots.py)",
        "always_loaded": "reaches every session unasked; nothing machine-written may be here",
        "human_owned": "directive: an agent proposes, the user edits (entities.yaml)",
        "machine_writable": "the nightly pass writes frontmatter here, never prose",
        "generated": "rewritten whole by a generator; see on_drift",
        "places": "which subject owns which directory (subjects.yaml)",
    }
    out = [VAULT_HEADER]
    for key, value in contract.items():
        if key in notes:
            out.append(f"\n# {notes[key]}")
        if isinstance(value, dict):
            out.append(f"{key}:")
            for k, v in value.items():
                if isinstance(v, list):
                    out.append(f"  {k}:")
                    out += [f"    - {item}" for item in v]
                else:
                    out.append(f"  {k}: {v}")
        elif isinstance(value, list):
            out.append(f"{key}:")
            out += [f'  - "{item}"' if "*" in item else f"  - {item}" for item in value]
        else:
            out.append(f"{key}: {value}")
    return "\n".join(out) + "\n"


VAULT_SPEC = invocation.Spec(name="vault", usage="vault [--check] [--write]",
                             flags=("--check", "--write"))


def vault_main(inv) -> int:
    want = render_vault(vault_contract())
    have = VAULT_FILE.read_text() if VAULT_FILE.exists() else ""
    if inv.has("--check"):
        if have == want:
            print(f"{roots.rel(VAULT_FILE)}: in sync with its sources")
            return 0
        print(f"{roots.rel(VAULT_FILE)}: DRIFT from posture/roots/registers. "
              f"Run: familiar consolidation vault --write", file=sys.stderr)
        return 3
    if inv.has("--write"):
        VAULT_FILE.write_text(want)
        print(f"wrote {roots.rel(VAULT_FILE)}")
        return 0
    sys.stdout.write(want)
    return 0


# -- CLI ---------------------------------------------------------------------

SPEC = invocation.Spec(name="posture", usage="posture")


def main(inv) -> int:
    findings = check(inv.agents.parent, inv.agents)
    print("familiar consolidation posture — the memory-poisoning checks")
    print(f"  repo: {inv.agents.parent}")
    by_check = {name: [] for name in CHECKS}
    for f in findings:
        by_check.setdefault(f.check, []).append(f)
    for name, fs in by_check.items():
        mark = "ok  " if not fs else ("WARN" if all(f.level == "warn" for f in fs)
                                      else "FAIL")
        print(f"  [{mark}] {name}")
        for f in fs:
            print(f"         {f.detail}")
    if not findings:
        print("\nAll checks pass. What this does NOT mean: that no transcript "
              "carried an injection.\nIt means an injected claim cannot reach a "
              "prompt unasked, cannot label itself trusted,\nand cannot become "
              "leaf prose without a human applying a patch.")
        return 0
    return 3 if any(f.level == "error" for f in findings) else 0
