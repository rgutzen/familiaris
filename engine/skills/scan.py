#!/usr/bin/env python3
"""Static skill scan and the digest ledger — `familiar skills scan`.

The gate this implements, decided 2026-10-24 (see `memory/skills/_scans.json`
§policy): a skill may be admitted, and may be promoted to `trust: trusted`, only
when no HIGH or CRITICAL *static* finding is undispositioned. Nothing else
gates. The semantic analyzers were measured against this library and produced
zero true HIGHs over 54 real scans while producing 19 HIGH labels that were
opinions about documentation; they are available by hand (`--llm`) and their
findings are advisory.

Two things here are not about detection:

1. **The digest.** 30 of 40 skills are `mode: link`: the body an agent reads
   lives upstream and changes under us on a `git pull` (or a `fetch` in
   `~/04_RESOURCES`). A review of a body that later changed is a claim about a
   version that no longer exists. `--check` fails when the bytes differ from
   the ones scanned, which is the assertion that actually holds.
2. **The target.** The artifact to scan is the one an agent executes: our
   directory for `vendor`/`derive`/`authored`, `upstream_path` for `link`.
   Scanning our adoption record alone would have missed the one real finding in
   this library, which was in an upstream body.

False positives are recorded, not silently dropped: a finding excluded by rule
carries `gate_excluded` with the reason, so the exclusion is auditable instead
of invisible.

Exit codes: 0 clean, 1 a gating finding is undispositioned, 2 the scanner is
missing or failed, 3 drift under `--check`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from lib import roots  # noqa: E402

LEDGER = roots.MEMORY / "skills/_scans.json"
SKILLS = roots.MEMORY / "skills"
SCANNER = "skillspector"

# Findings whose id begins with one of these never gate. `AE` is the scanner
# reporting that it could not inspect a reference — a coverage claim, and
# coverage is 0% on every Markdown-only skill (measured 2026-10-24), so gating
# on it would gate on the scanner's own limits. The rest never appear from a
# static run; they are listed because a hand `--llm` run writes into the same
# ledger and must not change the gate.
NON_GATING_IDS = ("AE", "SQP", "SDI", "TP")

# Files that are data, not instructions. diagram-design's body scan returned 13
# HIGH; 12 were SVG section comments in `assets/` and a regex inside a code
# sample in `references/`. The finding stays in the ledger with the reason.
NON_GATING_PATHS = ("assets/", "examples/")
NON_GATING_SUFFIXES = (".html",)

GATE_SEVERITIES = ("HIGH", "CRITICAL")


# ── digest ───────────────────────────────────────────────────────────────
def digest(path: pathlib.Path) -> tuple[str, int, int]:
    """Content identity of a directory: every file, its path, its bytes.

    Paths are relative and sorted, so a rename changes the digest and a `touch`
    does not. A directory that does not exist has no digest — that is a fact
    worth recording, not an error to swallow.
    """
    if not path.is_dir():
        return "", 0, 0
    h = hashlib.sha256()
    n = size = 0
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        try:
            data = f.read_bytes()
        except OSError:
            continue  # unreadable is unread; the file count still counts it
        n += 1
        size += len(data)
        h.update(f.relative_to(path).as_posix().encode() + b"\0")
        h.update(hashlib.sha256(data).hexdigest().encode() + b"\n")
    return "sha256:" + h.hexdigest(), n, size


# ── the scanner ──────────────────────────────────────────────────────────
def scanner_version(binary: str) -> str:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True,
                             timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    last = out.stdout.strip().split()[-1] if out.stdout.strip() else "unknown"
    return last.lstrip("v")


def scan_dir(binary: str, path: pathlib.Path, llm: bool) -> dict:
    """One scan, JSON only. Raises RuntimeError when the scanner cannot run.

    The report is written to a temporary file and deleted: the ledger keeps the
    findings and the digest, never the raw report. A scan of the same bytes by
    the same scanner version reproduces it, so storing 20 KB of JSON per skill
    would buy nothing and rot.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "report.json"
        cmd = [binary, "scan", str(path), "--format", "json", "--output", str(out)]
        if not llm:
            cmd.append("--no-llm")
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"{binary}: {exc}") from exc
        if not out.exists():
            raise RuntimeError(f"{binary} exited {proc.returncode} with no report: "
                               f"{(proc.stderr or proc.stdout).strip()[:300]}")
        report = json.loads(out.read_text())
    return report


def classify(finding: dict, target: str) -> dict:
    """A ledger finding: always recorded, only sometimes gating.

    Exclusion is a named rule with a written reason, never a drop. A `false`
    gate on a finding a reader cannot see the reason for is the same failure as
    no ledger at all.
    """
    fid = str(finding.get("id") or "")
    path = str(finding.get("location", {}).get("file") or "")
    reason = None
    if fid.startswith(NON_GATING_IDS):
        reason = ("out of scope: coverage self-report or an opinion about "
                  "documentation, not evidence about the skill")
    elif target == "body" and (path.startswith(NON_GATING_PATHS)
                               or path.endswith(NON_GATING_SUFFIXES)):
        reason = "out of scope: data or example asset, not an instruction the agent executes"
    return {
        "source": "static",
        "target": target,
        "id": fid,
        "severity": finding.get("severity"),
        "category": finding.get("category"),
        "pattern": (finding.get("pattern") or "")[:120],
        "file": path,
        "line": finding.get("location", {}).get("start_line"),
        "fingerprint": finding.get("match_fingerprint"),
        "explanation": (finding.get("explanation") or "")[:600],
        "gates": reason is None and finding.get("severity") in GATE_SEVERITIES,
        "gate_excluded": reason,
        "disposition": None,
        "reason": None,
        "by": None,
        "at": None,
    }


def _shown(path: pathlib.Path) -> str:
    """A path as the ledger spells it: `~`-relative, so the record survives a move."""
    try:
        return "~/" + path.resolve().relative_to(pathlib.Path.home()).as_posix()
    except ValueError:
        return str(path)


def scan_entry(binary: str, path: pathlib.Path, target: str, llm: bool) -> dict:
    report = scan_dir(binary, path, llm)
    sha, n, size = digest(path)
    findings = [classify(f, target) for f in report.get("issues", [])]
    meta = report.get("metadata", {})
    return {
        "path": _shown(path),
        "digest": sha,
        "files": n,
        "bytes": size,
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "semantic" if llm else "static",
        "degraded": bool(meta.get("llm_degraded")),
        "risk": report.get("risk_assessment"),
        "findings": findings,
    }


# ── ledger ───────────────────────────────────────────────────────────────
def load_ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"schema": 3, "skills": {}}


def save_ledger(ledger: dict) -> None:
    ledger["schema"] = 3
    ledger["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=1) + "\n")
    tmp.replace(LEDGER)


def carry_dispositions(new: dict, old: dict | None) -> None:
    """A human decision survives a rescan when the finding is still there.

    The match is the scanner's `match_fingerprint`, which is stable across line
    moves inside the same pattern and location. A disposition that silently
    reset on every rescan would make the record worthless exactly when it
    matters — after an edit.
    """
    if not old:
        return
    known = {f.get("fingerprint"): f for f in old.get("findings", []) if f.get("disposition")}
    for f in new.get("findings", []):
        prior = known.get(f.get("fingerprint"))
        if prior:
            for key in ("disposition", "reason", "by", "at"):
                f[key] = prior.get(key)


def gate_of(entry: dict) -> tuple[str, int]:
    open_high = sum(
        1
        for block in (entry.get("record"), entry.get("body"))
        if block
        for f in block.get("findings", [])
        if f.get("gates") and not f.get("disposition")
    )
    return ("blocked" if open_high else "pass"), open_high


def refresh_gate(entry: dict) -> None:
    entry["gate"], entry["open_high"] = gate_of(entry)


# ── commands ─────────────────────────────────────────────────────────────
def _rel_of(path: pathlib.Path) -> str | None:
    """The ledger key for a path, when it is a skill directory in this tree."""
    try:
        rel = path.resolve().relative_to(SKILLS.resolve()).as_posix()
    except ValueError:
        return None
    return rel if (path / "SKILL.md").exists() and rel.count("/") == 2 else None


def _fm(path: pathlib.Path) -> dict:
    out, text = {}, path.read_text().splitlines()
    for line in text[1:]:
        if line == "---":
            break
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.split(" #")[0].strip()
    return out


def _body_path(fm: dict) -> pathlib.Path | None:
    if fm.get("mode") != "link" or not fm.get("upstream_path"):
        return None
    return pathlib.Path(fm["upstream_path"].replace("~", str(pathlib.Path.home())))


def scan_skill(binary: str, rel: str, ledger: dict, llm: bool) -> dict:
    """Scan the record, and the body when the body lives upstream."""
    path = SKILLS / rel
    fm = _fm(path / "SKILL.md")
    old = ledger["skills"].get(rel)
    record = scan_entry(binary, path, "record", llm)
    carry_dispositions(record, (old or {}).get("record"))
    entry = {
        "origin": fm.get("origin"),
        "trust": fm.get("trust"),
        "mode": fm.get("mode", "vendor"),
        "source": fm.get("source") or None,
        "record": record,
        "body": None,
    }
    body = _body_path(fm)
    if body is not None:
        if body.is_dir():
            block = scan_entry(binary, body, "body", llm)
            block["pin"] = fm.get("upstream_pin")
            carry_dispositions(block, (old or {}).get("body"))
        else:
            block = {"path": _shown(body), "missing": True, "digest": "",
                     "pin": fm.get("upstream_pin"), "findings": []}
        entry["body"] = block
    # A run that asks for no semantic analysis must not erase the semantic
    # evidence an earlier run paid for. It is kept, and marked stale when the
    # bytes it describes are no longer the bytes on disk.
    if old and old.get("record", {}).get("semantic"):
        sem = old["record"]["semantic"]
        sem["stale"] = old["record"].get("digest") != record["digest"]
        record["semantic"] = sem
    refresh_gate(entry)
    return entry


def skills_in_tree() -> list[str]:
    """Every routed skill, through the one walker that already knows the layout."""
    from consolidation.stages.reindex import load_skills, Problem  # local: heavy import
    problems: list = []
    found = load_skills(roots.MEMORY, problems)
    for p in problems:
        if p.level != "note":
            print(f"!! {p.what}", file=sys.stderr)
    return sorted(f["_path"].split("/", 1)[1].rsplit("/", 1)[0]
                  for v in found.values() for f in v)


def print_entry(rel: str, entry: dict) -> None:
    print(f"{entry['gate'].upper():8} {rel}  [{entry.get('origin')}/{entry.get('trust')}]")
    for label in ("record", "body"):
        block = entry.get(label)
        if not block:
            continue
        if block.get("missing"):
            print(f"    {label}: MISSING {block['path']}")
            continue
        n = len(block.get("findings", []))
        print(f"    {label}: {block.get('files')} file(s), "
              f"{block.get('bytes')} bytes, {n} finding(s), {block.get('scanned_at')}")
        for f in block.get("findings", []):
            if f.get("gates") and not f.get("disposition"):
                print(f"      {f['severity']:8} {f['id']:6} {f['pattern'][:46]:48} "
                      f"{f['file']}:{f['line']}")
            elif f.get("disposition"):
                print(f"      {f['severity']:8} {f['id']:6} {f['pattern'][:46]:48} "
                      f"-> {f['disposition']}")


def cmd_scan(args) -> int:
    binary = os.environ.get("SKILLSPECTOR_BIN", SCANNER)
    if not shutil.which(binary) and not pathlib.Path(binary).exists():
        print(f"!! {binary} not found. Install it pinned:\n"
              "   uv tool install 'skillspector @ "
              "git+https://github.com/NVIDIA/skillspector.git@d7338f5'",
              file=sys.stderr)
        return 2

    ledger = load_ledger()
    if args.check:
        return cmd_check(ledger)

    ledger["scanner"] = {
        "tool": SCANNER,
        "version": scanner_version(binary),
        "install": "uv tool install 'skillspector @ "
                   "git+https://github.com/NVIDIA/skillspector.git@d7338f5'",
    }
    ledger["policy"] = {
        "gate": "HIGH or CRITICAL static finding with no human disposition",
        "excluded": {"ids": list(NON_GATING_IDS),
                     "paths": list(NON_GATING_PATHS) + list(NON_GATING_SUFFIXES)},
        "semantic": "advisory only (--llm); never gates",
        "target": "record + upstream body for mode: link",
    }

    targets: list[str] = []
    if args.all:
        targets = skills_in_tree()
    elif args.changed:
        targets = [rel for rel in skills_in_tree() if _is_changed(ledger, rel)]
    else:
        for raw in args.paths:
            path = pathlib.Path(raw).expanduser().resolve()
            rel = _rel_of(path)
            if rel is None:
                print(f"!! {raw} is not skills/<branch>/<subject>/<name>/", file=sys.stderr)
                return 2
            targets.append(rel)
    if not targets:
        print("nothing to scan: name a skill, --all, or --changed", file=sys.stderr)
        return 2

    failed = 0
    for rel in targets:
        try:
            entry = scan_skill(binary, rel, ledger, args.llm)
        except RuntimeError as exc:
            print(f"!! {rel}: {exc}", file=sys.stderr)
            failed += 1
            continue
        ledger["skills"][rel] = entry
        print_entry(rel, entry)

    save_ledger(ledger)
    blocked = [r for r in targets if ledger["skills"][r]["gate"] == "blocked"]
    print(f"\n{len(targets)} scanned, {len(blocked)} blocked, {failed} failed")
    return 1 if blocked else (2 if failed else 0)


def _is_changed(ledger: dict, rel: str) -> bool:
    entry = ledger["skills"].get(rel)
    if not entry:
        return True
    path = SKILLS / rel
    if digest(path)[0] != entry.get("record", {}).get("digest"):
        return True
    body = _body_path(_fm(path / "SKILL.md"))
    if body is not None and entry.get("body") and not entry["body"].get("missing"):
        return digest(body)[0] != entry["body"].get("digest")
    return False


def cmd_check(ledger: dict) -> int:
    """Drift fails; so does an open HIGH on a skill that claims `trust: trusted`.

    A `trial` skill with an open finding is the expected state — it is how a
    finding waits for a human — so it is reported and does not fail. Failing a
    commit for it would apply pressure to disposition without reading, which is
    the failure mode the whole record exists to prevent. The trust claim is the
    thing that must not be made without evidence.
    """
    if not ledger.get("skills"):
        print("no ledger: run `familiar skills scan --all` first", file=sys.stderr)
        return 2
    live = set(skills_in_tree())
    drift, missing, open_, trusted_open = [], [], [], []
    for rel, entry in sorted(ledger["skills"].items()):
        if rel not in live:
            missing.append(rel)
            continue
        if _is_changed(ledger, rel):
            drift.append(rel)
        if entry.get("gate") == "blocked" and entry.get("open_high"):
            open_.append(rel)
            if entry.get("trust") == "trusted":
                trusted_open.append(rel)
    for rel in drift:
        print(f"DRIFT   {rel} — scanned bytes are not the bytes on disk; rescan")
    for rel in missing:
        print(f"STALE   {rel} — in the ledger, no longer a skill")
    for rel in open_:
        mark = "BLOCKED" if rel in trusted_open else "open   "
        print(f"{mark} {rel} — {ledger['skills'][rel]['open_high']} undispositioned "
              f"HIGH/CRITICAL (trust: {ledger['skills'][rel].get('trust')})")
    print(f"{len(ledger['skills'])} in ledger, {len(drift)} drifted, "
          f"{len(missing)} stale, {len(open_)} with an open HIGH, "
          f"{len(trusted_open)} of them trusted")
    return 3 if (drift or missing) else (1 if trusted_open else 0)


def cmd_status(ledger: dict) -> int:
    skills = ledger.get("skills", {})
    if not skills:
        print("no ledger: run `familiar skills scan --all` first", file=sys.stderr)
        return 2
    for rel, entry in sorted(skills.items()):
        print_entry(rel, entry)
    gated = sum(1 for e in skills.values() if e.get("gate") == "blocked")
    print(f"\n{len(skills)} skills, {gated} blocked")
    return 1 if gated else 0


def cmd_accept(args) -> int:
    ledger = load_ledger()
    entry = ledger.get("skills", {}).get(args.skill)
    if not entry:
        print(f"!! {args.skill} is not in the ledger", file=sys.stderr)
        return 2
    hits = [
        f for block in (entry.get("record"), entry.get("body")) if block
        for f in block.get("findings", [])
        if f.get("fingerprint", "").startswith(args.fingerprint)
    ]
    if len(hits) != 1:
        print(f"!! {len(hits)} findings match {args.fingerprint!r}; "
              f"give more of the fingerprint", file=sys.stderr)
        return 2
    finding = hits[0]
    finding["disposition"] = args.disposition
    finding["reason"] = args.reason
    finding["by"] = args.by
    finding["at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    refresh_gate(entry)
    save_ledger(ledger)
    print(f"{args.skill}: {finding['id']} {finding['severity']} -> {args.disposition}; "
          f"gate {entry['gate']}")
    return 0


def cmd_list_accept(ledger: dict) -> int:
    for rel, entry in sorted(ledger.get("skills", {}).items()):
        for block in (entry.get("record"), entry.get("body")):
            for f in (block or {}).get("findings", []):
                if f.get("gates") and not f.get("disposition"):
                    print(f"{rel}  {f['fingerprint']}  {f['severity']:8} "
                          f"{f['id']:6} {f['pattern'][:40]}  {f['file']}:{f['line']}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        prog="familiar skills scan",
        description="Scan a skill's record and body; record the result in the digest ledger.")
    ap.add_argument("paths", nargs="*", metavar="skills/<branch>/<subject>/<name>")
    ap.add_argument("--all", action="store_true", help="scan every skill in the tree")
    ap.add_argument("--changed", action="store_true",
                    help="scan only skills whose bytes differ from the ledger")
    ap.add_argument("--check", action="store_true",
                    help="report drift and undispositioned HIGH/CRITICAL; write nothing")
    ap.add_argument("--status", action="store_true", help="the ledger, per skill")
    ap.add_argument("--open", dest="open_", action="store_true",
                    help="list the findings that still gate, with their fingerprints")
    ap.add_argument("--accept", metavar="SKILL", help="record a disposition for one skill")
    ap.add_argument("--fingerprint", default="", help="the finding's match_fingerprint (prefix)")
    ap.add_argument("--disposition", default="accepted",
                    choices=("accepted", "false-positive", "fixed"))
    ap.add_argument("--reason", default="")
    ap.add_argument("--by", default="user")
    ap.add_argument("--llm", action="store_true",
                    help="also run the semantic analyzers (advisory; needs a provider)")
    args = ap.parse_args(argv)

    if args.status:
        return cmd_status(load_ledger())
    if args.open_:
        return cmd_list_accept(load_ledger())
    if args.accept:
        if not args.fingerprint or not args.reason:
            ap.error("--accept needs --fingerprint and --reason")
        return cmd_accept(args)
    return cmd_scan(args)


if __name__ == "__main__":
    sys.exit(main())
