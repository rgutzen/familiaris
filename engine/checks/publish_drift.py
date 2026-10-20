#!/usr/bin/env python3
"""publish-drift -- has the private source moved since an artifact was published?

The public repositories are **generated artifacts**: `config/publication/export-state.json`
records, per artifact, the private paths it was exported from and a hash of their
contents at the moment of the publish. Publishing is a human act -- export, review
the diff, push -- so the failure mode is not a bad export. It is a *stale* one:
the private tree keeps moving, nobody re-publishes, and the public artifact
quietly stops being what the system runs. This turns "do not forget" into a gate.

WHY THE HASH IS OVER THE PRIVATE SOURCES, NOT THE EXPORTED BYTES. The export does
surgery -- a directory rename, path templating, a rewritten README, vendored
shared modules -- so comparing bytes would report drift on every run and teach the
reader to ignore it. The question this answers is narrower and answerable: have
the files this artifact was built from changed since the day it was published?

GATES: healthcheck and manual, never pre-commit. Between an edit and the next
publish the state is *supposed* to be stale; failing every commit in between is
how a gate becomes noise.

Usage:
    python3 engine/checks/publish_drift.py                      # report every artifact
    python3 engine/checks/publish_drift.py --json
    python3 engine/checks/publish_drift.py --record NAME --commit SHA [--note ...]
        stamp the state after a publish (the artifact now matches the sources)

Exit codes: 0 in sync · 1 drift · 2 usage or state error (per CLAUDE.md's
convention for a tool that reports rather than fixes).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from lib import roots  # noqa: E402

REPO = roots.REPO
STATE = roots.CONFIG / "publication" / "export-state.json"

# `"source": "classification"` means "resolve the list from the publication
# classification at read time". The umbrella is the whole tree, so its sources
# ARE `config/publication/publish.yaml`'s own output, and copying that output into
# the state file would be a second place for the export's shape to be wrong.
# The failure a copy produces is specific and expensive: an edit to a private
# file that never travels -- `config/profile.yaml`, the practice tree -- would
# report drift on a gate whose whole value is that its red line means something.
# The classification is an input to the export as well as the thing that lists
# them, so it is hashed with them: a reclassification changes what is published.
CLASSIFICATION = "classification"

# Directories that are never part of an export: caches, not sources.
SKIP = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def classification_paths() -> list[str]:
    """The private paths a whole-tree publish is made from, repo-relative.

    Imported rather than re-implemented: `publish_audit` owns the one reader of
    the classification, and a second reading of the same file is how the two
    would come to disagree.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import publish_audit as audit  # noqa: E402
    cfg = audit.load()
    rules = audit.rules(cfg)
    out = []
    for rel in audit.tracked():
        rule, _why = audit.classify(rel, rules)
        if rule is not None and rule.cls != "omit":
            out.append(rel)
    return out + [audit.CLASSIFICATION.relative_to(REPO).as_posix()]


def sources(art: dict) -> list[str]:
    """An artifact's private sources, resolving the `classification` sentinel."""
    src = art.get("source")
    return classification_paths() if src == CLASSIFICATION else list(src or [])


def source_hash(root: pathlib.Path, paths: list[str]) -> tuple[str, int]:
    """One hash over the given files and directories, order-independent.

    Paths and contents both enter the hash, so a rename is drift and so is an
    edit. Missing paths are drift too: a source that moved out from under an
    artifact is the loudest case of all.
    """
    entries: list[tuple[str, str]] = []
    missing: list[str] = []
    for raw in paths:
        p = root / raw
        if not p.exists():
            missing.append(raw)
            continue
        files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file())
        for f in files:
            if any(part in SKIP for part in f.parts):
                continue
            rel = f.relative_to(root).as_posix()
            entries.append((rel, hashlib.sha256(f.read_bytes()).hexdigest()))
    entries.sort()
    digest = hashlib.sha256()
    for rel, sha in entries:
        digest.update(f"{rel}\0{sha}\n".encode())
    return f"sha256:{digest.hexdigest()}", len(missing)


def load_state(path: pathlib.Path = STATE) -> dict:
    if not path.exists():
        raise SystemExit(f"publish-drift: no state file at {path.relative_to(REPO)}")
    return json.loads(path.read_text())


def check(root: pathlib.Path = REPO, state: dict | None = None) -> list[dict]:
    """One finding per artifact whose sources no longer hash to the record.

    A RETIRED artifact is listed and not measured. It stopped being an
    independent artifact -- it is a pointer to the umbrella now -- so its
    freshness is not a question this gate can answer, and its entry stays
    because it records what that export did. The reason is mandatory: an
    artifact that quietly stops being checked is the drift this gate exists to
    make visible, one level up.
    """
    state = state if state is not None else load_state()
    findings = []
    for name, art in sorted(state.get("artifacts", {}).items()):
        if art.get("retired"):
            findings.append({"artifact": name, "repo": art.get("repo"),
                             "retired": art["retired"]})
            continue
        now, missing = source_hash(root, sources(art))
        findings.append({
            "artifact": name,
            "repo": art.get("repo"),
            "clone": art.get("clone"),
            "published_commit": art.get("commit"),
            "published_at": art.get("published_at"),
            "records": art.get("hash"),
            "now": now,
            "drift": now != art.get("hash") or missing > 0,
            "missing_paths": missing,
        })
    return findings


def retirement_findings(state: dict) -> list[str]:
    """The declared retirements, and the one thing they must not say.

    A reason is mandatory, because the declaration is the only thing standing
    between a live gate and a name nobody checks any more. The other direction
    -- a retirement that names an artifact nobody has -- is not checkable here:
    nothing knows what artifacts exist except this file, so it can only be
    caught by reading it.
    """
    out = []
    for name, art in sorted(state.get("artifacts", {}).items()):
        why = art.get("retired")
        if why is None:
            continue
        if len(str(why).split()) < 5:
            out.append(f"{name} is retired without a reason: {why!r}")
    return out


def record(name: str, commit: str, note: str | None, state_path: pathlib.Path = STATE) -> int:
    state = load_state(state_path)
    art = state["artifacts"].get(name)
    if art is None:
        raise SystemExit(f"publish-drift: unknown artifact {name!r} "
                         f"(known: {', '.join(sorted(state['artifacts']))})")
    if art.get("retired"):
        raise SystemExit(
            f"publish-drift: {name!r} is RETIRED -- {art['retired']} Recording "
            f"a hash against it would re-arm a gate that no longer describes "
            f"anything: there is no artifact to be stale.")
    now, missing = source_hash(REPO, sources(art))
    if missing:
        raise SystemExit(f"publish-drift: {missing} source path(s) missing for {name!r}")
    art["hash"] = now
    art["commit"] = commit
    art["published_at"] = __import__("datetime").date.today().isoformat()
    if note:
        art["note"] = note
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"publish-drift: recorded {name} at {commit} ({now})")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", metavar="NAME")
    ap.add_argument("--commit", metavar="SHA")
    ap.add_argument("--note")
    args = ap.parse_args(argv)

    if args.record:
        if not args.commit:
            print("publish-drift: --record needs --commit", file=sys.stderr)
            return 2
        return record(args.record, args.commit, args.note)

    findings = check()
    contradictions = retirement_findings(load_state())
    drifted = [f for f in findings if f.get("drift")]
    if args.json:
        print(json.dumps({"artifacts": findings, "problems": contradictions},
                         indent=2))
        return 1 if drifted or contradictions else 0
    for line in contradictions:
        print(f"STATE    {line}")
    for f in findings:
        if f.get("retired"):
            print(f"retired  {f['artifact']:<24} {f['repo'] or '?'}")
            print(f"        {f['retired']}")
            continue
        mark = "DRIFT " if f["drift"] else "in sync"
        print(f"{mark}  {f['artifact']:<24} {f['repo'] or '?'}")
        print(f"        published {f['published_at']} at {str(f['published_commit'])[:12]}")
        if f["drift"]:
            print(f"        sources now {f['now']}")
            print(f"        recorded     {f['records']}")
            if f["missing_paths"]:
                print(f"        {f['missing_paths']} source path(s) are gone")
            # The procedure, spelled out where the drift is reported: the
            # reader who sees DRIFT is the one who needs the commands, and the
            # clone's location is a fact of the state file, not of memory.
            # The full recipe is docs/how-to/publish-the-tree.md.
            clone = f.get("clone") or "<publish clone>"
            eng = roots.ENGINE_REL
            print(f"        → republish (docs/how-to/publish-the-tree.md):\n"
                  f"          python3 {eng}/publication/publish.py --to {clone}\n"
                  f"          git -C {clone} diff            # read all of it\n"
                  f"          git -C {clone} add -A && git -C {clone} commit -m '…'"
                  f" && git -C {clone} push origin main\n"
                  f"          python3 {eng}/checks/publish_drift.py --record "
                  f"{f['artifact']} --commit $(git -C {clone} rev-parse HEAD)")
    return 1 if drifted or contradictions else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
