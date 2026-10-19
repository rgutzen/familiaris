"""Stage 7b -- Knowledge index. One flat, on-demand index of `knowledge/`.

memory/knowledge/system/knowledge/knowledge-index.md. Replaces blanket injection with ONE level of progressive
disclosure: `CONTEXT.md` names this file, this file names every leaf,
the agent reads the leaf it needs. Nothing about `knowledge/` is injected into
any prompt.

WHY ONE LEVEL AND NOT TWO. Zhao, Wang & Chen 2026 (arXiv 2607.17598) measured
disclosure depth directly: one level suffices, and a second routing level
"never helps and sometimes breaks accuracy outright". So this index REPLACES
the `CONTEXT.md -> knowledge/<branch>/CONTEXT.md -> leaf` walk for the model
rather than sitting on top of it; the branch routers stay on disk for human and
Obsidian navigation, reached from this file's header. Adding this index while
keeping the branch hop in `CONTEXT.md` would have built exactly the
two-level router that paper says not to build.

WHY AN INDEX AT ALL. Anthropic, "Effective context engineering" -- a finite
attention budget spent on the smallest high-signal set, retrieved just in time.
Chroma's "Context Rot" (18 models) is the cost of the alternative: topically
adjacent entries that do not answer the question degrade accuracy more as the
input grows, which is what lore's 72-entry per-turn block was
(journal/2026/09/2026-09-10_lore-reevaluation.md).

THE BUDGET IS THE FEATURE. `INDEX_BUDGET_TOKENS` is the whole point of the
file: an index that grows without bound is the injected block again, just
voluntary. Over budget is a CONTENT problem only a human can fix -- by
shortening summaries or splitting a branch -- so it is reported loudly and the
file is still written (a stale index is worse than an oversized one).

NOTHING IS AUTHORED HERE. Every cell comes from the leaf: `summary:` if the
author wrote one, else `title:`, else the H1. Trigger terms are `triggers:` if
declared, else `tags:`. A generator that invents a summary would be writing
knowledge into a derived artifact, and the next rebuild would silently rewrite
it -- markdown is truth, indexes are disposable caches
(memory-architecture.md).

WHAT COUNTS AS A LEAF is `tree.SKIP_NAMES`, imported rather than re-derived, so
the index and the scoring pass cannot disagree about the population.

Same shape as `reindex.py`, deliberately: `plan()` decides and writes nothing,
`Plan.apply()` writes, `main()` is a CLI adapter, `run()` is the stage. Nothing
here exits, and nothing raises past the caller: a malformed leaf is a Problem,
not a dead nightly pass.

Exit codes: 0 ok - 1 error or over budget - 3 --check found drift.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import sys

from knowledge.frontmatter import read as read_frontmatter
from knowledge.tree import SKIP_NAMES
from lib import roots

DEFAULT_ROOT = roots.vault_root()

# memory/knowledge/system/knowledge/knowledge-index.md says "~1-2k-token index". 2000 is the ceiling, not the target.
INDEX_BUDGET_TOKENS = 2000
# Tokens are an ESTIMATE here. `pazras-context` counts with tiktoken; this
# package must stay importable from a systemd timer with nothing installed, so
# it uses the 4-chars-per-token rule of thumb. Calibrated against o200k_base on
# the real index 2026-09-11: 5,173 chars, estimate 1,294 tok, tiktoken 1,312 --
# the estimate runs ~1.4% LOW on table-heavy markdown, so the budget wants a
# little margin rather than being run right up to. Chars are exact and are what
# the report leads on.
CHARS_PER_TOKEN = 4
# Enough to disambiguate, few enough that the terms column cannot eat the
# budget. A leaf needing more than this is two leaves.
MAX_TERMS = 8
# One line means one line. Longer summaries are reported, never silently cut,
# because a truncated summary is the context-collapse failure ACE names.
MAX_SUMMARY_CHARS = 110

BANNER = ("<!-- GENERATED FILE — do not hand-edit. Rebuild: "
          "`familiar knowledge index` -->")
BRANCH_TAG = "BRANCHES"

# `<!-- LAYER 3 · Per-tool behaviour and traps -->` in each branch router. The
# branch's one-line description already exists there; restating it here would
# be the same fact in two places, which is rule 1 of knowledge/CONTEXT.md.
LAYER_COMMENT = re.compile(r"^<!--\s*LAYER\s+\d+\s*·\s*(?P<blurb>[^>]*?)\s*-->\s*$", re.M)
H1 = re.compile(r"^#\s+(.+)$", re.M)


@dataclasses.dataclass
class Problem:
    """Something the caller must decide how loudly to say -- same contract as
    `reindex.Problem`: this module reports, the caller picks the volume."""
    level: str                  # error | warn | note
    what: str
    path: pathlib.Path | None = None


@dataclasses.dataclass
class Leaf:
    rel: str                    # relative to memory/knowledge/
    branch: str
    summary: str
    terms: list


@dataclasses.dataclass
class Plan:
    root: pathlib.Path
    writes: list                # [(path, content)]
    problems: list
    leaves: list
    branches: dict              # name -> blurb
    index_chars: int = 0

    @property
    def failed(self) -> bool:
        return any(p.level == "error" for p in self.problems)

    @property
    def index_tokens(self) -> int:
        return -(-self.index_chars // CHARS_PER_TOKEN)   # ceil

    @property
    def over_budget(self) -> bool:
        return self.index_tokens > INDEX_BUDGET_TOKENS

    @property
    def drift(self) -> list:
        return [p for p, new in self.writes
                if not p.exists() or p.read_text() != new]

    def apply(self) -> list:
        changed = []
        for path, new in self.writes:
            if not path.exists() or path.read_text() != new:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new)
                changed.append(path)
        return changed


# ── reading the tree ─────────────────────────────────────────────────────
def branch_blurb(router: pathlib.Path) -> str:
    """The branch's one-line description -- from the SCHEMA where it declares
    one, and only then from the router's `LAYER n · …` comment.

    O3a reversed this. The comment used to be the source, which made the
    description a hand-edited fact in a file this module regenerates: exactly
    the drift the phase removes, and it went wrong the moment O2b deleted the
    three branch routers and the table started printing `system/ —`. The
    register is the artifact now, and the router is one of its two readers.

    The fallback is kept rather than dropped: a directory under `knowledge/`
    that names no declared branch is already an ERROR in `ontology check`, and
    printing nothing for it here would hide it behind a second failure.
    """
    name = router.parent.name
    branch = _BRANCHES().get(name)
    if branch is not None:
        return " ".join(branch.criteria.split())
    try:
        text = router.read_text()
    except OSError:
        return ""
    m = LAYER_COMMENT.search(text)
    return m.group("blurb").strip() if m else ""


def _BRANCHES() -> dict:
    """The branch register, imported late.

    `ontology` reads four YAML files at import; this module is also a plain CLI
    (`familiar knowledge index`) and importing it must not depend on the
    registers parsing. A register that fails to load is `ontology
    selfcheck`'s to report, not this module's to crash on.
    """
    try:
        from knowledge import ontology
        return dict(ontology.BRANCHES)
    except Exception:              # noqa: BLE001 - see docstring
        return {}


# Which branch routers this module WRITES. `areas/` is deliberately not one:
# `knowledge-index.md` §Known duplication records that it indexes Areas A-P
# rather than leaves, so generating it "would destroy human judgement to remove
# a cosmetic repeat". A generator that overwrote it would be solving a
# duplication problem by deleting the thing that is not duplicated.
GENERATED_ROUTERS = ("system",)


def leaf_summary(path: pathlib.Path, fm: dict, problems: list) -> str:
    """One line for this leaf, taken from it and never invented.

    `summary:` is the author's own one-liner and wins. `title:` is the next
    best -- the tree's titles are already written as sentences ("Context budget
    — what each harness spends before work, measured"). The H1 and then the
    filename are the fallbacks for a leaf that carries no frontmatter at all,
    which is separately reported: such a leaf is invisible to maintenance.
    """
    for key in ("summary", "title"):
        val = str(fm.get(key) or "").strip().strip('"')
        if val:
            return val
    text = path.read_text()
    m = H1.search(text)
    if m:
        return m.group(1).strip()
    problems.append(Problem(
        "warn", f"no summary, title or H1 — indexed by filename only: {path}", path))
    return path.stem.replace("-", " ")


def leaf_terms(fm: dict) -> list:
    """Trigger vocabulary: `triggers:` if the author declared any, else `tags:`.

    Same two-population idea as the skill trigger index -- a match here is
    EXPLAINABLE, you can name the term that fired, which an embedding score
    cannot do.
    """
    terms = fm.get("triggers") or fm.get("tags") or []
    if isinstance(terms, str):
        terms = [terms]
    seen, out = set(), []
    for t in terms:
        t = str(t).strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:MAX_TERMS]


def load_leaves(root: pathlib.Path, problems: list) -> list:
    """Every knowledge leaf, as index rows. Population defined by `tree`."""
    kdir = root / "knowledge"
    out = []
    for p in sorted(kdir.rglob("*.md")):
        # `_`-prefixed is the tree's own convention for a template or a draft
        # (`_leaf-template.md`); `SKIP_NAMES` lists the named exceptions and is
        # shared with scoring so the two cannot disagree on the population.
        if p.name in SKIP_NAMES or p.name.startswith("_"):
            continue
        rel = p.relative_to(kdir).as_posix()
        fm = read_frontmatter(p)
        summary = leaf_summary(p, fm, problems)
        if len(summary) > MAX_SUMMARY_CHARS:
            problems.append(Problem(
                "warn", f"summary is {len(summary)} chars (max {MAX_SUMMARY_CHARS}) "
                        f"— add a shorter `summary:` to {rel}", p))
        if not fm:
            problems.append(Problem(
                "warn", f"no frontmatter — invisible to maintenance: {rel}", p))
        out.append(Leaf(rel=rel, branch=rel.split("/")[0] if "/" in rel else ".",
                        summary=summary, terms=leaf_terms(fm)))
    return out


# ── rendering ────────────────────────────────────────────────────────────
def render_index(leaves: list, branches: dict) -> str:
    by_branch: dict = {}
    for leaf in leaves:
        by_branch.setdefault(leaf.branch, []).append(leaf)

    out = ["# Knowledge Index", "", BANNER,
           "<!-- READ ON DEMAND, WHOLE. This is the ONLY index between "
           "CONTEXT.md and a leaf: -->",
           "<!-- one level of disclosure, never two "
           "(knowledge/system/knowledge/knowledge-index.md). -->", "",
           "Every fact this tree holds, one line each. Paths are relative to "
           f"`{roots.rel(roots.KNOWLEDGE)}/`.",
           "**Read the leaf** — a row is a pointer, never the claim. Match the "
           "task's vocabulary",
           "against the trigger terms; a match is **explainable**. No match "
           "anywhere means the",
           "fact is not here — try `familiar knowledge journal search`, or say it is "
           "unknown.", "",
           f"{len(leaves)} leaves in {len(branches)} branches.", ""]

    for name in sorted(by_branch):
        blurb = branches.get(name, "")
        out += [f"## `{name}/` — {blurb}" if blurb else f"## `{name}/`", "",
                "| Leaf | What it holds | Trigger terms |", "|---|---|---|"]
        for leaf in sorted(by_branch[name], key=lambda x: x.rel):
            out.append(f"| `{leaf.rel}` | {leaf.summary} | "
                       f"{', '.join(leaf.terms) or '—'} |")
        out.append("")

    empty = sorted(b for b in branches if b not in by_branch)
    if empty:
        out += ["Branches with no leaves yet: "
                + ", ".join(f"`{b}/`" for b in empty) + ".", ""]
    out += ["Branch routers (`<branch>/CONTEXT.md`) are for human and Obsidian "
            "navigation. A model",
            "that has read this file has already routed; descending into one is "
            "a second",
            "routing level and buys nothing.", ""]
    return "\n".join(out)


def render_branches(leaves: list, branches: dict) -> str:
    counts: dict = {}
    for leaf in leaves:
        counts[leaf.branch] = counts.get(leaf.branch, 0) + 1
    rows = ["| Branch | Holds | n |", "|---|---|---|"]
    for name in sorted(branches):
        rows.append(f"| `{name}/` | {branches[name] or '—'} | "
                    f"{counts.get(name, 0)} |")
    return "\n".join(rows)


def render_branch_router(name: str, leaves: list) -> str:
    """One branch router, wholly from the schema. O3a.

    Rows are the branch's SUBJECT folders, not its leaves: the router's job is
    to triage, and `INDEX.md` is the one index between here and a leaf. A
    subject with no folder yet is listed as declared-and-empty rather than
    omitted -- `publication` exists in the register and its absence from the
    disk is a fact about the tree, not about the vocabulary.
    """
    from knowledge import ontology
    branch = ontology.BRANCHES[name]
    counts: dict = {}
    for leaf in leaves:
        if leaf.branch != name:
            continue
        parts = leaf.rel.split("/")
        if len(parts) > 1:
            counts[parts[1]] = counts.get(parts[1], 0) + 1

    out = [f"# `{name}/` — {branch.name}", "", BANNER,
           f"<!-- LAYER 3 · {' '.join(branch.criteria.split())} -->", "",
           f"**Looking for a fact, not a folder? Read `../INDEX.md`.** This "
           f"router triages {name}'s subjects; the index lists every leaf. "
           f"A model that has read the index has already routed.", "",
           "| Subject | | Falsified when | n |", "|---|---|---|---|"]
    for sid, s in ontology.SUBJECTS.items():
        n = counts.get(sid, 0)
        crit = " ".join(s.criteria.split())
        # A subject with no leaves is named WITHOUT the trailing slash. It is
        # not a folder yet, and writing `publication/` would make this
        # generated file add a permanent entry to `links --check`'s decision
        # list -- a pointer that resolves to nothing, by construction, for as
        # long as the subject stays empty. That list is a signal; a generator
        # is the last thing that should be adding noise to it.
        where = f"`{sid}/`" if n else f"`{sid}`"
        out.append(f"| {where} | {s.name} | {crit} | {n or '—'} |")
    out += ["",
            f"{sum(counts.values())} leaves in {len(counts)} of "
            f"{len(ontology.SUBJECTS)} subjects. A subject folder appears on "
            f"its first leaf, so `—` means declared and not yet written, "
            f"never missing.", ""]
    return "\n".join(out)


def replace_block(text: str, tag: str, content: str) -> str | None:
    """None when the marker is absent -- the caller records a problem. Same
    contract, and the same reason, as `reindex.replace_block`: a missing marker
    must not raise SystemExit past the pass's per-stage guard."""
    pat = re.compile(
        rf"(<!-- BEGIN:{tag} \(generated\) -->\n).*?(\n<!-- END:{tag} -->)", re.S)
    if not pat.search(text):
        return None
    return pat.sub(lambda m: m.group(1) + content + m.group(2), text)


# ── planning ─────────────────────────────────────────────────────────────
def plan(root: pathlib.Path = None) -> Plan:
    """Decide everything; write nothing."""
    root = pathlib.Path(root or DEFAULT_ROOT)
    kdir = root / "knowledge"
    problems: list = []
    if not kdir.is_dir():
        return Plan(root=root, writes=[],
                    problems=[Problem("error", f"no knowledge tree at {kdir}", kdir)],
                    leaves=[], branches={})

    branches = {p.name: branch_blurb(p / "CONTEXT.md")
                for p in sorted(kdir.iterdir()) if p.is_dir()}
    for name, blurb in branches.items():
        if not blurb:
            problems.append(Problem(
                "warn", f"branch `{name}/` has no `LAYER n · …` comment in its "
                        f"router; indexed without a description",
                kdir / name / "CONTEXT.md"))
    leaves = load_leaves(root, problems)

    index = render_index(leaves, branches)
    writes = [(kdir / "INDEX.md", index)]

    router = kdir / "CONTEXT.md"
    try:
        text = router.read_text()
    except OSError as exc:
        problems.append(Problem("error", f"branch router unreadable: {exc}", router))
    else:
        new = replace_block(text, BRANCH_TAG, render_branches(leaves, branches))
        if new is None:
            problems.append(Problem(
                "error", f"marker BEGIN:{BRANCH_TAG} not found in {router} — the "
                         f"branch table cannot be regenerated until it is restored",
                router))
        else:
            writes.append((router, new))

    # O3a: the branch routers that are generated, whole, from the schema.
    for name in GENERATED_ROUTERS:
        if (kdir / name).is_dir():
            writes.append((kdir / name / "CONTEXT.md",
                           render_branch_router(name, leaves)))

    p = Plan(root=root, writes=writes, problems=problems, leaves=leaves,
             branches=branches, index_chars=len(index))
    if p.failed:
        p.writes = []               # cannot render correctly: write nothing
    elif p.over_budget:
        problems.append(Problem(
            "warn", f"INDEX.md is ~{p.index_tokens} tok, over the "
                    f"{INDEX_BUDGET_TOKENS} budget — shorten summaries or split "
                    f"a branch; it is the always-reachable file every routed "
                    f"session pays. **The trigger: when the coded "
                    f"{INDEX_BUDGET_TOKENS}-token ceiling is exceeded, split into "
                    f"PER-BRANCH indexes** — no new judgement needed, because by "
                    f"then the sorting rule is explicit (O3d). Routing down a "
                    f"branch and pre-filtering a vector search are the same "
                    f"operation; the branch is the facet.", kdir / "INDEX.md"))
    return p


# ── CLI ──────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    """Thin adapter over `plan`. Healthcheck depends on these exit codes:
    0 ok, 1 error or over budget, 3 drift under --check."""
    ap = argparse.ArgumentParser(prog="familiar knowledge index")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit 3; write nothing")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    p = plan()
    for prob in p.problems:
        if prob.level != "note":
            print(f"!! {prob.what}", file=sys.stderr)
    if p.failed:
        return 1

    if args.check:
        for path in p.drift:
            print(f"DRIFT {path.relative_to(p.root)}")
        print(f"{len(p.drift)} of {len(p.writes)} generated files would change")
        if p.drift:
            return 3
        return 1 if p.over_budget else 0

    roots.guard_vault_write(p.root, "knowledge index")
    drift = p.drift
    p.apply()
    print(f"knowledge index: {len(p.leaves)} leaves in "
          f"{len(p.branches)} branches")
    print(f"  index   knowledge/INDEX.md  {p.index_chars} chars "
          f"(~{p.index_tokens} tok, "
          f"{'OK' if not p.over_budget else 'OVER BUDGET'}, "
          f"budget {INDEX_BUDGET_TOKENS})")
    print(f"  table   knowledge/CONTEXT.md  §Branch counts")
    print(f"  rewritten: {len(drift)}")
    return 1 if p.over_budget else 0


# ── stage entry point ────────────────────────────────────────────────────
def run(ctx) -> bool:
    """Stage 7 of the pass, second generator. Derived artifact: regenerate,
    never hand-edit."""
    p = plan(ctx.agents)
    for prob in p.problems:
        ctx.note("7", prob.what, prob.level)

    if p.failed:
        ctx.note("7", "knowledge/INDEX.md was NOT regenerated — it still "
                      "describes the tree as it was before tonight", "error")
    elif ctx.dry_run:
        if p.drift:
            ctx.note("7", f"knowledge/INDEX.md and/or its branch table have "
                          f"drifted ({len(p.drift)} file(s)); a real run would "
                          f"regenerate them")
    else:
        changed = p.apply()
        if changed:
            ctx.act("7", ", ".join(sorted(c.name for c in changed)),
                    f"regenerated the knowledge index — {len(p.leaves)} leaves, "
                    f"~{p.index_tokens} tok")
    return True
