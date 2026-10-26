#!/usr/bin/env python3
"""publish.py -- write the public tree from this repository, into a clone.

THE MODEL. This repository is ground truth: everything is edited and committed
here. The public repository is a GENERATED output -- a clone that this script
refreshes, that a human reads the diff of, and that a human pushes. Nothing is
ever edited only in public, and this script never commits and never pushes.

WHAT IT DOES, in order:
  1. read the classification (`config/publication/publish.yaml`) and the tracked
     file list, and fail on anything unclassified (`publish_audit.py`, the same
     loader -- one schema, one meaning);
  2. build the tree in a scratch directory: copy `public` paths, apply the
     recorded surgery for `example` paths, and prune the register declarations
     whose place does not exist in the export;
  3. run the `regenerate:` steps IN THE SCRATCH TREE, so a generated file
     (`knowledge/INDEX.md` and the skill routers) is the target's own, not this
     machine's;
  4. diff the scratch tree against the target and print the three counts;
  5. write it, prune only what a previous run recorded in the marker, and read
     the result back with `publish_scan.py` -- the leak scanner runs on the
     GENERATED tree, never on this one.

WHY THE SCRATCH TREE AND NOT A DIRECT WRITE. A generated file is not a copy:
`knowledge/INDEX.md` lists the leaves that travel, and the skill routers list
the skills that travel. Building the whole tree in the scratch directory means
the diff compares finished trees -- `publish.py --to X` twice in a row reports
0 added, 0 removed, 0 modified, and that is a measurement rather than a hope.

WHAT IT MAY DELETE. Only paths a previous run wrote down in
`<target>/.familiaris-export`. The failure mode this avoids is a script that
eats a human's file: a file the marker does not list is never touched, and a
target that is neither empty nor a previous export is refused outright.

Usage:
    python3 engine/publication/publish.py --to ../familiaris          # write
    python3 engine/publication/publish.py --to ../familiaris --check   # diff only
Exit codes: 0 clean · 1 leak or export error · 2 usage.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "checks"))
from lib import roots  # noqa: E402
from knowledge import frontmatter  # noqa: E402
from knowledge import ontology  # noqa: E402
import publish_audit as audit  # noqa: E402  (the classification's one reader)
import leak_gate  # noqa: E402  (the push gate the clone is armed with)

# The frontmatter keys that name something else (config/knowledge/relations.yaml
# is the register they come from). The `same-*` relations are derived facets and
# are not written by hand, so they are not here.
EDGE_FIELDS = ("related", "supersedes", "superseded_by", "contradicts",
               "promoted_from", "source", "cites")

MARKER = ".familiaris-export"
# The leak scanner is deliberately THIS tree's: its private pattern file and the
# declarations it measures against live under `dev/`, which the export has not
# got, so the instance runs the scan on a tree it names with `--tree`.
SCANNER = roots.ENGINE / "checks" / "publish_scan.py"
# The registry is the opposite case, and the difference is the whole point:
# the exported tree runs its OWN `checks.py`, so what executes is what a reader
# of the published tree could have run. Spelled RELATIVE to the stage -- a
# constant resolved against this worktree would run the instance's registry
# with `cwd` in the stage, and every check would then measure this machine
# while the report said the export was clean. That is the one failure an export
# gate must not have, so the path is built from the stage every time.
CHECKS_REL = pathlib.Path(roots.ENGINE_REL) / "checks" / "checks.py"
# The gate the stage runs on itself. `export` is `pre-commit` minus the suites
# that would call this module back -- the one place a self-including gate cannot
# work, declared in `checks.py` where the gate's membership lives.
GATE = "export"
SKIP = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

# The environment the regenerate steps run in. `PYTHONDONTWRITEBYTECODE` keeps
# `__pycache__` out of the scratch tree -- a bytecode cache in the exported
# tree would otherwise be synced to the target, carrying the scratch path in
# every `co_filename`.
STEP_ENV = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}


@dataclasses.dataclass
class Step:
    run: list
    why: str
    produces: list
    sandbox_home: bool
    env: dict


@dataclasses.dataclass
class Exported:
    """One file of the generated tree and how it got there."""

    path: str
    source: str = ""            # the private path it was copied from
    surgery: str = ""           # what changed on the way out, if anything


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── building the tree ────────────────────────────────────────────────────────

def _place_exists(present: set[str], place: str) -> bool:
    """Is a declared place a directory in the export?

    A directory is not a tracked thing, so it exists here when something
    inside it travels -- which is the same question `ontology check` asks of
    the tree it is given.
    """
    return any(p == place or p.startswith(place + "/") for p in present)


def prune_absent_places(text: str, present: set[str]) -> tuple[str, list[str]]:
    """Keep only the register's declarations whose place travels.

    `subjects.yaml` claims every directory for exactly one subject, or lists it
    under `unmapped:` with the reason. An exported tree has no `memory/journal/`
    and no `config/schedule/`, so the declarations that name them describe a
    tree that is not there -- `ontology check` in the target fails on exactly
    that, and the honest fix is a register that describes the tree it ships
    with. Line-oriented on purpose: the entries are block sequences of scalars
    and of mappings, and a YAML round-trip would rewrite the parts that did not
    change.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    dropped: list[str] = []
    section = subsection = None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 0 and stripped.endswith(":"):
            section, subsection = stripped[:-1], None
            out.append(line)
            i += 1
            continue
        m = re.match(r"^-\s+id:\s*(\S+)$", stripped)
        if section == "unmapped" and m:
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                    break
                j += 1
            if _place_exists(present, m.group(1)):
                out.extend(lines[i:j])
            else:
                dropped.append(m.group(1))
            i = j
            continue
        if section == "subjects":
            if m:
                subsection = None
            elif stripped == "places:":
                subsection = "places"
            elif subsection == "places" and re.match(r"^-\s+\S+$", stripped):
                place = stripped[2:].strip()
                if _place_exists(present, place):
                    out.append(line)
                else:
                    dropped.append(place)
                i += 1
                continue
        out.append(line)
        i += 1
    return "".join(out), dropped


def _resolves(ref: str, stems: set, present: set) -> bool:
    """Does an edge's target exist in the export?

    The same two shapes the ontology resolves: a URL or a `git@` remote is
    `external` and always resolves; a path resolves against the exported files
    (repo-relative, or relative to the memory root, which is how `journal/...`
    is spelled); a bare name resolves against the identifiers the exported
    documents define -- their stems, and a skill's `name:`.
    """
    s = ref.strip()
    if not s or s.startswith(("git@", "http://", "https://")):
        return True
    if "/" in s or s.startswith(("~", ".")):
        return s in present or any(p.endswith("/" + s) for p in present)
    return s in stems


def _exported_stems(stage: pathlib.Path) -> set:
    """Every identifier the target's own leaves and skills resolve.

    Walked through the ontology's own document walk, so "what resolves" is one
    definition and not two -- against the SCRATCH tree, which is the tree the
    check in the target will read.
    """
    stems = set()
    for _rel, p in ontology._walk_docs(stage / roots.MEMORY_REL):
        fm = frontmatter.read(p)
        if fm.get("name"):
            stems.add(str(fm["name"]))
        stems.add(p.stem)
    return stems


def prune_absent_edges(text: str, stems: set, present: set) -> tuple[str, list]:
    """Drop the frontmatter edges whose target did not travel.

    An edge is a CLAIM: this leaf relates to that one. In the exported tree
    "that one" is private, so the claim is false there -- and the ontology
    check in the target fails on exactly that, because a dangling `related:`
    is a broken reference rather than a missing file. Written through
    `frontmatter.set_fields`, which keeps every other byte: key order, the
    trailing `# 06_SYSTEM session …` provenance comments, the body.
    """
    fm = frontmatter.parse(text)
    if not fm:
        return text, []
    updates = {}
    dropped = []
    for field in EDGE_FIELDS:
        value = fm.get(field)
        if not isinstance(value, list):
            continue
        kept = [v for v in value if _resolves(str(v), stems, present)]
        if len(kept) != len(value):
            dropped += [f"{field}:{v}" for v in value if v not in kept]
            updates[field] = kept
    if not updates:
        return text, []
    return frontmatter.set_fields(text, updates), dropped


def _substitute(data: bytes, subs: tuple, rel: str) -> tuple[bytes, int]:
    """Apply the classification's surgery to one file.

    A `from:` (or `drop_line:`) that matches NOTHING is an error, not a
    no-op. The classification is a promise about the bytes on disk, and a rule
    that stopped matching is a file that changed under it: the surgery then
    silently does not happen, the exported file keeps a string the
    classification says it loses, and nothing reports it. That is not
    hypothetical -- two rows in the master config carried a literal `\n` for
    three steps (see `publish_audit._subs`) and the export shipped a backup row
    for a path a reader does not have. The leak scanner is the net that catches
    the disclosure case; this is the check that catches the rest, at the moment
    the rule is written.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise SystemExit(f"publish: {rel}: a `substitute:` on a file that is "
                         f"not UTF-8 text; the classification asks for a "
                         f"surgery this file cannot take")
    n, dead = 0, []
    for old, new, drop in _triples(subs):
        if drop:
            # The whole line, and the newline that ends it: `^old\n` with the
            # anchor at a line start, so a `from:` that is only a fragment of
            # the line matches nothing and is reported as dead.
            count = len(re.findall("^" + re.escape(old) + r"\r?\n", text, re.M))
            text = re.sub("^" + re.escape(old) + r"\r?\n", "", text, flags=re.M)
        else:
            count = text.count(old)
            text = text.replace(old, new)
        if count == 0:
            dead.append(old)
        n += count
    if dead:
        raise SystemExit(
            f"publish: {rel}: {len(dead)} substitution(s) match nothing in this "
            f"file -- the file changed under the classification, or `from:` "
            f"does not spell what it thinks it does:\n" +
            "\n".join(f"    {d!r}" for d in dead) +
            f"\n  Fix the classification or delete the entry; a rule that "
            f"matches nothing is not a no-op, it is an edit that silently did "
            f"not happen.")
    return text.encode("utf-8"), n


def _triples(subs: tuple) -> tuple:
    """Accept `(from, to)` and `(from, to, drop_line)`.

    The two-element form is what the classification carried before `drop_line`
    existed, and the publish's own tests build rules by hand."""
    return tuple((s if len(s) == 3 else (s[0], s[1], False)) for s in subs)


def build(stage: pathlib.Path, cfg: dict, rules, sources: list[tuple[str, object]],
          workspace: pathlib.Path) -> tuple[dict, list[str], dict]:
    """Write the generated tree into `stage`.

    Returns (files, surgery lines, per-file hash) where `files` maps the
    exported path to how it got there.
    """
    files: dict[str, Exported] = {}
    surgery: list[str] = []
    present = set()
    for rel, rule in sources:
        dest = rule.as_ if rule.as_ else rel
        present.add(dest)

    defs: list[tuple[pathlib.Path, object]] = []
    for rel, rule in sources:
        dest = rule.as_ if rule.as_ else rel
        src = roots.REPO / rel
        data = src.read_bytes()
        note = ""
        if rule.substitute:
            data, n = _substitute(data, rule.substitute, rel)
            note = f"{len(rule.substitute)} substitution(s), {n} occurrence(s)"
        if getattr(rule, "prune_absent_places", False):
            text, dropped = prune_absent_places(data.decode("utf-8"), present)
            data = text.encode("utf-8")
            note = ("register pruned: " + ", ".join(f"`{d}` dropped"
                                                    for d in sorted(dropped))
                    if dropped else "register pruned: nothing was absent")
            surgery.append(f"{dest}: {note}")
        target = stage / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        shutil.copymode(src, target)
        files[dest] = Exported(path=dest, source=rel, surgery=note)
        if getattr(rule, "prune_absent_edges", False) and dest.endswith(".md"):
            defs.append((target, rule))
        if rule.as_:
            surgery.append(f"{rel} -> {dest} (renamed, {rule.cls})")

    # After every file is in place: an edge resolves against the whole export,
    # so pruning while copying would judge a leaf against half a tree.
    if defs:
        stems = _exported_stems(stage)
        for path, _rule in defs:
            text, dropped = prune_absent_edges(path.read_text(), stems, present)
            if dropped:
                path.write_text(text)
                rel = path.relative_to(stage).as_posix()
                surgery.append(f"{rel}: edges pruned ({', '.join(sorted(dropped))})")

    for step in steps(cfg):
        before = {p: sha256(p.read_bytes()) for p in stage.rglob("*") if p.is_file()}
        env = dict(os.environ, **STEP_ENV)
        env.update({k: v.format(stage=stage, home=workspace / "home",
                                target=stage) for k, v in step.env.items()})
        if step.sandbox_home:
            home = workspace / "home"
            home.mkdir(parents=True, exist_ok=True)
            env["HOME"] = str(home)
            env.pop("XDG_CONFIG_HOME", None)
            env.pop("XDG_CACHE_HOME", None)
            env.pop("XDG_DATA_HOME", None)
            env.pop("XDG_STATE_HOME", None)
        result = subprocess.run([str(a) for a in step.run], cwd=stage, env=env,
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout, result.stderr, sep="", file=sys.stderr)
            raise SystemExit(f"publish: regenerate step `{' '.join(map(str, step.run))}` "
                             f"failed in the scratch tree (exit {result.returncode})")
        after = {p: sha256(p.read_bytes()) for p in stage.rglob("*") if p.is_file()}
        touched = [p.relative_to(stage).as_posix() for p in after
                   if before.get(p) != after[p]]
        for rel in sorted(touched):
            files[rel] = Exported(path=rel, source="",
                                  surgery=f"regenerated by `{' '.join(map(str, step.run))}`")
        surgery.append(f"regenerate: {' '.join(map(str, step.run))} -> "
                       f"{len(touched)} file(s) ({', '.join(sorted(touched)) or 'none'})")
        # A step may also REMOVE a derived file: the knowledge index drops a subject's
        # index when none of its leaves travel (split per subject, 2026-10-21). An
        # entry kept for it would be a managed file the target never receives.
        gone = sorted(rel for rel in files if not (stage / rel).exists())
        for rel in gone:
            del files[rel]
        if gone:
            surgery.append(f"regenerate: {' '.join(map(str, step.run))} removed "
                           f"{len(gone)} file(s) ({', '.join(gone)})")
        for want in step.produces:
            if not (stage / want).exists():
                raise SystemExit(f"publish: the regenerate step claims to write "
                                 f"{want}, and it did not -- the step and the "
                                 f"classification disagree")
    return files, surgery, present


def steps(cfg: dict) -> list[Step]:
    out = []
    for i, raw in enumerate(cfg.get("regenerate") or [], 1):
        if not isinstance(raw, dict) or not isinstance(raw.get("run"), list):
            raise SystemExit(f"publish: regenerate[{i}] needs a `run:` block "
                             f"sequence -- the argv of one command")
        out.append(Step(
            run=list(raw["run"]),
            why=" ".join(str(raw.get("why") or "").split()),
            produces=list(raw.get("produces") or []),
            sandbox_home=str(raw.get("sandbox_home", "")) == "true",
            env={k: str(v) for k, v in (raw.get("env") or {}).items()
                 if isinstance(raw.get("env"), dict)},
        ))
    return out


# ── comparing and writing ────────────────────────────────────────────────────

@dataclasses.dataclass
class Diff:
    added: list
    removed: list
    modified: list

    def counts(self) -> tuple[int, int, int]:
        return len(self.added), len(self.removed), len(self.modified)


def _tree_files(root: pathlib.Path) -> dict:
    out = {}
    for p in root.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        if any(part in SKIP for part in p.relative_to(root).parts):
            continue
        out[p.relative_to(root).as_posix()] = sha256(p.read_bytes())
    return out


def diff(stage: pathlib.Path, target: pathlib.Path,
         managed: set[str]) -> Diff:
    """What the target would gain, lose and change.

    A file is only ever REMOVED if a previous export wrote it: the marker is
    the whole permission slip, and a human's file in the target is not in it.
    """
    want, have = _tree_files(stage), _tree_files(target)
    added = sorted(set(want) - set(have))
    removed = sorted(p for p in set(have) - set(want) if p in managed)
    modified = sorted(p for p in set(want) & set(have) if want[p] != have[p])
    return Diff(added, removed, modified)


def _sync(stage: pathlib.Path, target: pathlib.Path, d: Diff) -> None:
    for rel in d.added + d.modified:
        src, dest = stage / rel, target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    for rel in d.removed:
        (target / rel).unlink()


def _prune_dirs(target: pathlib.Path, managed: set[str]) -> list[str]:
    """Remove directories this tool emptied -- never a directory with content."""
    gone = []
    candidates = sorted({str(pathlib.PurePosixPath(p).parent) for p in managed},
                        key=len, reverse=True)
    for c in candidates:
        d = target / c
        while d != target and d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                break
            gone.append(d.relative_to(target).as_posix())
            d = d.parent
    return gone


def read_marker(target: pathlib.Path) -> dict:
    try:
        return json.loads((target / MARKER).read_text())
    except (OSError, ValueError):
        return {}


def check_target(target: pathlib.Path) -> None:
    """Empty, a clone of the public repository, or a previous export. Else stop."""
    if not target.exists():
        return
    if not target.is_dir():
        raise SystemExit(f"publish: {target} is not a directory")
    if read_marker(target):
        return
    entries = [p for p in target.iterdir() if p.name != ".git"]
    if not entries:
        return
    if (target / ".git").exists():
        return
    raise SystemExit(
        f"publish: {target} is not empty, is not a git clone and carries no "
        f"{MARKER} marker -- refusing to write into a directory that looks "
        f"like someone's. Pass a clone of the public repository, an empty "
        f"directory, or a target this tool wrote before.")


def write_marker(target: pathlib.Path, files: dict, source_hash: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    marker = {
        "$comment": (f"Written by {roots.ENGINE_REL}/publication/publish.py. "
                     f"`managed` is the list of paths this tool wrote and may "
                     f"delete; anything not listed here is never touched."),
        "tool": f"{roots.ENGINE_REL}/publication/publish.py",
        "version": 1,
        "source_hash": source_hash,
        "files": len(files),
        "managed": sorted(files),
    }
    text = json.dumps(marker, indent=2) + "\n"
    path = target / MARKER
    if not path.exists() or path.read_text() != text:
        path.write_text(text)


# ── the report ───────────────────────────────────────────────────────────────

def source_hash(sources: list[tuple[str, object]], cfg_path: pathlib.Path) -> str:
    """One hash over the private inputs: what this export was made of.

    `publish_drift.py --record` is the durable version of this number, stamped
    into `config/publication/export-state.json` after the human pushes. This is
    the same question asked at the moment of writing: are the sources a
    different shape than last time?
    """
    digest = hashlib.sha256()
    for rel, _ in sorted(sources):
        digest.update(f"{rel}\0{sha256((roots.REPO / rel).read_bytes())}\n".encode())
    digest.update(f"classification\0{sha256(cfg_path.read_bytes())}\n".encode())
    return f"sha256:{digest.hexdigest()}"


def _scan(target: pathlib.Path, quiet: bool = False) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(SCANNER), "--tree", str(target)],
                            capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).rstrip()


def gate(stage: pathlib.Path) -> str:
    """Run the exported tree's OWN gate on the stage, and return its verdict.

    WHY THIS RUNS AT ALL, AND WHY HERE. The exported tree carries a gate whose
    whole job is to say whether it can be trusted; a publish is the only moment
    that claim can be checked against the bytes that are about to travel, and
    the cheap place to stop is before the copy rather than in a reader's hands.
    So the gate runs on the SCRATCH tree, and a red one aborts the publish with
    nothing written.

    It is the tree's gate and not this instance's, and the path is what makes
    that true: `CHECKS_REL` is resolved against the STAGE, so the registry that
    runs is the one the export carries. The stage has no `dev/`, so the checks
    whose subject lives only here declare that and skip -- loudly, with a count.
    What remains is what a reader of the published tree could have run.

    `PYTHONDONTWRITEBYTECODE` because the gate imports the stage's own modules,
    and a bytecode cache written into the stage would carry the scratch path in
    every `co_filename` -- the same reason the regenerate steps set it.
    """
    env = dict(os.environ, **STEP_ENV)
    result = subprocess.run([sys.executable, str(stage / CHECKS_REL), "--run", GATE],
                            cwd=stage, env=env, capture_output=True, text=True)
    out = result.stdout + result.stderr
    verdict = [ln for ln in out.splitlines() if ln.startswith("checks.py:")]
    if result.returncode != 0:
        for ln in out.splitlines():
            print(f"    {ln}")
        raise SystemExit(
            f"publish: the exported tree fails its own gate (exit "
            f"{result.returncode}); nothing was written into the target. Fix "
            f"what the gate names, or, if a check measures this instance and "
            f"does not say so, declare it -- a check that reports green here "
            f"while measuring this machine is worse than a red one.")
    return verdict[-1] if verdict else f"exit {result.returncode}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", required=True, metavar="PATH",
                    help="the clone of the public repository, or an empty directory")
    ap.add_argument("--check", action="store_true",
                    help="report the diff; write nothing")
    args = ap.parse_args(argv)

    target = pathlib.Path(args.to).expanduser().absolute()
    if target.resolve() == roots.REPO.resolve():
        raise SystemExit("publish: --to is this repository; the export goes to "
                         "a clone of the public one")
    check_target(target)

    cfg = audit.load()
    rules = audit.rules(cfg)
    problems = [f for f in audit.findings(roots.REPO, cfg)]
    if problems:
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit("publish: the classification does not hold; fix "
                         f"{roots.rel(audit.CLASSIFICATION)} first "
                         f"({roots.rel(roots.ENGINE / 'checks' / 'publish_audit.py')})")

    sources = []
    for rel in audit.tracked():
        rule, why = audit.classify(rel, rules)
        if rule is None:
            raise SystemExit(f"publish: {rel}: {why}")
        if rule.cls != "omit":
            sources.append((rel, rule))

    workspace = pathlib.Path(tempfile.mkdtemp(prefix="familiaris-publish-"))
    stage = workspace / "export"
    stage.mkdir()
    try:
        files, surgery, _ = build(stage, cfg, rules, sources, workspace)
        verdict = gate(stage)
        managed_before = set(read_marker(target).get("managed") or [])
        d = diff(stage, target, managed_before)
        added, removed, modified = d.counts()

        commit = subprocess.run(
            ("git", "-C", str(roots.REPO), "rev-parse", "--short", "HEAD"),
            capture_output=True, text=True).stdout.strip() or "unknown"
        print(f"publish: {target}")
        print(f"  source      {roots.rel(roots.REPO)} @ {commit}"
              f"  {source_hash(sources, audit.CLASSIFICATION)}")
        print(f"  files       {len(files)} written"
              f" ({sum(1 for f in files.values() if f.source)} copied, "
              f"{sum(1 for f in files.values() if not f.source)} generated)")
        print(f"  gate        {verdict}")
        print(f"  added       {added}")
        print(f"  removed     {removed}")
        print(f"  modified    {modified}")
        if args.check:
            for p in d.added:
                print(f"    + {p}")
            for p in d.removed:
                print(f"    - {p}")
            for p in d.modified:
                print(f"    ~ {p}")
        print(f"  surgery     {len(surgery)} step(s)")
        for s in surgery:
            print(f"    {s}")
        if args.check:
            print("  (--check: nothing written)")
            if not target.exists():
                print(f"  scan        skipped: {target} does not exist yet, so "
                      f"there is nothing to read back")
                return 0
            code, out = _scan(target)
            print("  " + out.replace("\n", "\n  ") if out else "")
            return code

        target.mkdir(parents=True, exist_ok=True)
        _sync(stage, target, d)
        gone = _prune_dirs(target, managed_before | set(files))
        if gone:
            print(f"  pruned      {len(gone)} empty director(ies): "
                  f"{', '.join(gone)}")
        write_marker(target, files, source_hash(sources, audit.CLASSIFICATION))
        if (target / ".git").exists():
            # The push that publishes this tree starts HERE, so the gate belongs
            # here. Arming it from this install (not from the export's own copy)
            # is what lets the hook read the private pattern register; the
            # alternative is a human remembering, which is the failure mode this
            # whole track exists to remove.
            hook = leak_gate.arm(target)
            print(f"  hook        pre-push armed ({hook})")
        code, out = _scan(target)
        print("  " + out.replace("\n", "\n  ") if out else "")
        return code
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
