#!/usr/bin/env python3
"""Every tracked path is classified for publication, and every rule still bites.

WHY THIS EXISTS. The public tree is a *generated* artifact: `publish.py` writes
it from this repository, a human reads the diff and pushes. The failure that
matters is therefore not a bad export -- a human reads that -- it is the file
NOBODY THOUGHT OF. An allow-list is the only shape that fails closed on it:
`dev/publication/publish.yaml` classifies every tracked path as `public`,
`example` or `omit`, and this audit fails on a path the file does not name.

THE PATTERN IS THE THIRD USE OF ONE IDIOM, deliberately:
  * `checks.py --audit` fails on a test file no registry entry runs;
  * `declared_paths.py` fails on a declared path that is missing or a
    declaration that has gone stale;
  * this module does both, over the publication classification.
A rule that matches NO tracked path is an error for the same reason a
tombstone that has been resurrected is: the file it was written for is gone,
and a rule left standing describes an export that no longer exists. Deletions
are the one edit nobody re-reads.

WHAT IT ASKS, in full:
  * every tracked path is classified, by exactly one winning rule;
  * every rule matches at least one tracked path;
  * every rule carries a `why`, because the classification is a decision and
    the reason is what a later session reviews;
  * `example` means the bytes change on the way out, so it needs either an
    `as:` or a `substitute:`;
  * a `substitute:` on a `public` rule is a contradiction -- the file is
    copied as-is or it is not;
  * no two rules claim the same path at the same specificity;
  * an `as:` target is inside the tree, is claimed once, and lands somewhere
    the export does not also delete;
  * every `places:` entry in `config/knowledge/subjects.yaml` is covered by a
    rule. That is the seam to the register: a new folder forces a filing
    decision there (`ontology check`) and a publication decision here.

Usage:
    python3 engine/checks/publish_audit.py            # exit 1 on any finding
    python3 engine/checks/publish_audit.py --list     # the classification, by rule
"""
from __future__ import annotations

import argparse
import dataclasses
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lib import _miniyaml, roots  # noqa: E402

CLASSIFICATION = roots.DEV / "publication" / "publish.yaml"

CLASSES = ("public", "example", "omit")
# The one class that changes bytes; the other two are copies and omissions.
CHANGING = "example"


@dataclasses.dataclass(frozen=True)
class Rule:
    """One line of the classification: a path, a class, and the reason."""

    section: str            # "directories" | "overrides"
    path: str               # a directory prefix (`engine/`) or an exact path
    cls: str
    why: str
    as_: str = ""                        # `example`: where the copy lands
    substitute: tuple = ()               # `example`: (from, to) literals
    prune_absent_places: bool = False    # `example`: the register surgery
    prune_absent_edges: bool = False     # `example`: frontmatter edges whose
                                         # target does not travel
    index: int = 0                       # position in the file, for reporting

    @property
    def prefix(self) -> bool:
        return self.section == "directories" or self.path.endswith("/")

    def matches(self, rel: str) -> bool:
        if self.prefix:
            return rel == self.path or rel.startswith(self.path)
        return rel == self.path

    @property
    def specificity(self) -> int:
        return len(self.path)


def load(path: pathlib.Path = CLASSIFICATION) -> dict:
    try:
        cfg = _miniyaml.load(path.read_text())
    except OSError as exc:
        raise SystemExit(f"publish-audit: cannot read {path} ({exc})")
    except _miniyaml.YamlError as exc:
        raise SystemExit(f"publish-audit: {path}: {exc}")
    return cfg or {}


def _subs(raw, where: str) -> tuple:
    """`(from, to, drop_line)` triples, validated here rather than at the
    substitution.

    WHY `drop_line` EXISTS. `_miniyaml` does not process `\n` inside a quoted
    scalar -- its docstring promises "no quoting subtleties beyond a single
    surrounding pair" -- so a `from:` that wants to remove a WHOLE line cannot
    spell the newline it has to take with it. It could spell the line and leave
    a blank one behind, which is how the classification removed this install's
    two `.claude` backup rows and did not: the rows carried a trailing `\n`
    escape that the parser kept literal, so they matched nothing for the whole
    of P2-P4 while `structure validate` warned on every fresh clone about a
    path the reader does not have. The mechanism says the newline now, and
    `publish.py` fails on any `from:` that matches nothing, so the next one is
    loud in the same commit it is written in."""
    out = []
    for i, s in enumerate(raw or [], 1):
        if not isinstance(s, dict) or not s.get("from"):
            raise SystemExit(f"publish-audit: {where}: substitute {i} needs "
                             f"`from:` and `to:`")
        drop = str(s.get("drop_line", "")).strip().lower() in ("true", "yes", "1")
        if drop and s.get("to"):
            # Two mechanisms for one entry: which one wins is the ambiguity the
            # `example`-without-`as_`-or-`substitute` rule exists to prevent.
            raise SystemExit(f"publish-audit: {where}: substitute {i} has both "
                             f"`to:` and `drop_line:`; drop_line removes the "
                             f"line and its newline, so there is nothing to "
                             f"replace it with")
        out.append((s["from"], s.get("to", ""), drop))
    return tuple(out)


def rules(cfg: dict) -> list[Rule]:
    out: list[Rule] = []
    for section in ("directories", "overrides"):
        for i, raw in enumerate(cfg.get(section) or [], 1):
            where = f"{section}[{i}]"
            if not isinstance(raw, dict) or not raw.get("path"):
                raise SystemExit(f"publish-audit: {where}: needs a `path:`")
            out.append(Rule(
                section=section,
                path=raw["path"],
                cls=raw.get("class", ""),
                why=" ".join(str(raw.get("why") or "").split()),
                as_=raw.get("as", "") or "",
                substitute=_subs(raw.get("substitute"), where),
                prune_absent_places=str(raw.get("prune_absent_places", "")) == "true",
                prune_absent_edges=str(raw.get("prune_absent_edges", "")) == "true",
                index=i,
            ))
    return out


def tracked(repo: pathlib.Path = roots.REPO) -> list[str]:
    """The paths the repository CLAIMS, not whatever is lying in the checkout."""
    try:
        out = subprocess.run(("git", "-C", str(repo), "ls-files", "-z"),
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"publish-audit: cannot list tracked files ({exc}); "
                         f"an allow-list audit that cannot see the list it "
                         f"audits must not report success")
    return [p for p in out.split("\0") if p]


def classify(rel: str, all_rules: list[Rule]) -> tuple[Rule | None, str]:
    """The winning rule for one path, or (None, why not).

    An override beats a directory default; within a section the longest path
    wins, because that is the rule the author wrote most precisely. A tie is
    an error rather than a coin toss -- two rules of equal specificity for one
    path is a classification that cannot be read off the file.
    """
    hits = [r for r in all_rules if r.matches(rel)]
    if not hits:
        return None, "unclassified"
    top_section = "overrides" if any(r.section == "overrides" for r in hits) \
        else "directories"
    top = [r for r in hits if r.section == top_section]
    width = max(r.specificity for r in top)
    winners = [r for r in top if r.specificity == width]
    if len(winners) > 1:
        return None, ("two rules claim it at the same specificity: "
                      + ", ".join(w.path for w in winners))
    return winners[0], ""


def _places(repo: pathlib.Path = roots.REPO) -> list[str]:
    """Every directory the ontology register files: `places:` and `unmapped:`."""
    path = repo / roots.CONFIG_REL / "knowledge" / "subjects.yaml"
    try:
        cfg = _miniyaml.load(path.read_text()) or {}
    except (OSError, _miniyaml.YamlError) as exc:
        raise SystemExit(f"publish-audit: cannot read {roots.rel(path)} ({exc})")
    out = [p for s in cfg.get("subjects") or [] for p in (s.get("places") or [])]
    out += [u["id"] for u in cfg.get("unmapped") or [] if u.get("id")]
    return out


def _covers(r: Rule, place: str) -> bool:
    """Do a rule and a place overlap? Prefix either way, at a segment edge."""
    if r.prefix:
        return place == r.path.rstrip("/") or place.startswith(r.path)
    return r.path == place or r.path.startswith(place + "/") \
        or place.startswith(r.path + "/")


def findings(repo: pathlib.Path = roots.REPO,
             cfg: dict | None = None) -> list[str]:
    cfg = load() if cfg is None else cfg
    all_rules = rules(cfg)
    files = tracked(repo)
    out: list[str] = []

    if str(cfg.get("version")) != "1":
        out.append(f"version: {cfg.get('version')!r} is not 1 -- this audit "
                   f"speaks the classification's first version")
    if not all_rules:
        out.append(f"{roots.rel(CLASSIFICATION)}: no rules; every path would "
                   f"be unclassified, which is the failure this file exists "
                   f"to make loud")

    seen_paths: set = set()
    for r in all_rules:
        where = f"{r.section}[{r.index}] {r.path or '<no path>'}"
        if r.path != r.path.strip() or r.path.startswith("/") \
                or ".." in r.path.split("/"):
            out.append(f"{where}: a classification path is repository-relative "
                       f"and repo-internal")
        if r.path in seen_paths:
            out.append(f"{where}: classified twice in the same section")
        seen_paths.add(r.path)
        if r.cls not in CLASSES:
            out.append(f"{where}: class {r.cls!r} is not one of "
                       f"{' / '.join(CLASSES)}")
        if not r.why:
            out.append(f"{where}: no `why:` -- the classification is a "
                       f"decision, and a later session has only the reason to "
                       f"review it by")
        changes = bool(r.as_ or r.substitute or r.prune_absent_places
                       or r.prune_absent_edges)
        if r.cls != CHANGING and changes:
            out.append(f"{where}: class {r.cls!r} with a surgery -- a copied "
                       f"file is copied as-is; the class that changes bytes "
                       f"is `{CHANGING}`")
        if r.cls == CHANGING and not changes:
            out.append(f"{where}: `example` and nothing changes -- give it an "
                       f"`as:` (a new name), a `substitute:` or the register "
                       f"surgery, or classify it `public`")

    for rel in files:
        rule, why = classify(rel, all_rules)
        if rule is None:
            out.append(f"{rel}: {why} -- add it to a `directories:` default in "
                       f"{roots.rel(CLASSIFICATION)}, or to `overrides:` with "
                       f"its class and the reason. `omit` is the honest answer "
                       f"when it is not obvious.")

    owners: dict = {}
    for r in all_rules:
        n = sum(1 for rel in files if r.matches(rel))
        if n == 0:
            out.append(f"{r.section}[{r.index}] {r.path}: matches no tracked "
                       f"path -- the thing it classified was deleted or "
                       f"renamed, and a rule left standing describes an "
                       f"export that no longer exists")
        if r.as_:
            if not r.as_.strip() or r.as_.startswith("/") or ".." in r.as_.split("/"):
                out.append(f"{r.section}[{r.index}] {r.path}: `as:` must be a "
                           f"repository-relative path")
            elif r.as_ in owners:
                out.append(f"{r.section}[{r.index}] {r.path}: `as:` {r.as_} is "
                           f"already written by {owners[r.as_]}")
            else:
                owners[r.as_] = r.path
                dest, dest_why = classify(r.as_, all_rules)
                if dest is None:
                    out.append(f"{r.section}[{r.index}] {r.path}: `as:` "
                               f"{r.as_} is {dest_why} -- the export would "
                               f"write a file nothing classifies")
                elif dest.cls == "omit":
                    out.append(f"{r.section}[{r.index}] {r.path}: `as:` "
                               f"{r.as_} lands under {dest.path} ({dest.cls}) "
                               f"-- the export deletes there")

    for place in _places(repo):
        if not any(_covers(r, place) for r in all_rules):
            out.append(f"{place}: a place in {roots.rel(roots.ONTOLOGY)}/"
                       f"subjects.yaml that no `directories:` rule covers -- "
                       f"the register forces a filing decision, and the "
                       f"export owes the same for publication")

    produced: set = set()
    for i, raw in enumerate(cfg.get("regenerate") or [], 1):
        where = f"regenerate[{i}]"
        if not isinstance(raw, dict) or not raw.get("run"):
            out.append(f"{where}: needs a `run:` -- the argv of a command "
                       f"that runs IN THE TARGET and writes the file")
            continue
        if not str(raw.get("why") or "").strip():
            out.append(f"{where}: no `why:` -- a generated file in the export "
                       f"is a decision like any other")
        for rel in raw.get("produces") or []:
            if rel.startswith("/") or ".." in rel.split("/"):
                out.append(f"{where}: `produces: {rel}` is not a "
                           f"repository-relative path")
            elif rel in produced:
                out.append(f"{where}: {rel} is already produced by an "
                           f"earlier step")
            produced.add(rel)
    return out


def _grouped(all_rules: list[Rule], files: list[str]) -> list[tuple[Rule, list[str]]]:
    buckets: dict = {}
    for r in all_rules:
        buckets[(r.section, r.index)] = (r, [])
    for rel in sorted(files):
        rule, _ = classify(rel, all_rules)
        if rule is not None:
            buckets[(rule.section, rule.index)][1].append(rel)
    return [b for _, b in sorted(buckets.items())]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true",
                    help="print the classification, one line per rule")
    args = ap.parse_args(argv)

    if args.list:
        cfg = load()
        all_rules = rules(cfg)
        files = tracked()
        for r in all_rules:
            n = sum(1 for rel in files if r.matches(rel))
            print(f"{r.cls:8s} {n:4d}  {r.path}"
                  + (f"  -> {r.as_}" if r.as_ else ""))
        print(f"\n{roots.rel(CLASSIFICATION)}: {len(all_rules)} rule(s), "
              f"{len(files)} tracked file(s), "
              f"{sum(1 for f in files if classify(f, all_rules)[0] is None)} "
              f"unclassified")
        return 0

    problems = findings()
    for p in problems:
        print(f"  {p}")
    print(f"publish audit: {len(problems)} finding(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
