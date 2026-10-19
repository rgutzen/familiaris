"""selftest -- the gates that hold the capture path in place.

  --signals    every fixture payload must classify to the signal it was
               written for: trigger, scope, browse, explicit, external. (Until
               2026-10-13 this was `--parity`, and it diffed the Python capture
               against the M1 bash baseline. That baseline was deleted with
               `familiar`'s rename, the migration it gated having finished in
               2026-09; the per-fixture assertion is the half that still says
               something.)
  --hook-cost  the capture path runs on the user's latency budget; decision 3
               of the M2 handoff accepted ~30 ms. Measure it, do not assume it.
  --invariants what each stage of the pass declares it guarantees, checked:
               idempotence (plan/apply/plan is empty) and error/act
               disjointness, plus the declaration audit itself -- a stage in
               run.STAGES with no entry in stages/invariants.DECLARED fails.
               See that module for why: three silent defects shipped in one
               module because nothing required a stage to state its invariants.
  --schema     capture WRITES skill-usage.jsonl and `ledger` READS it, and they
               cannot share code: capture may not import `json` (its latency
               budget). Two writers of one format that cannot share an
               implementation is drift waiting to happen, so the contract is
               declared read-side as `ledger.USAGE_FIELDS` and checked here.

Capture is the only part of the memory system that was working before M2. The
rewrite is not allowed to regress it, and "it looked fine" is not a gate.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
PY = HERE / "familiar-memory.py"

# One payload per resolution signal in skill-routing.md Sec.Resolution order.
# `caller.type` and the `args` vocabulary are what steer the classification.
# The named skill must have LIVE triggers: `systematic-debugging` was deprecated
# on 2026-09-02 (superseded by `diagnosing-bugs`) and its triggers stripped, at
# which point this fixture silently reclassified trigger -> scope.
PAYLOADS = {
    "trigger": {
        "session_id": "signals-trigger", "tool_name": "Skill",
        "cwd": "/home/rg/01_PROJECTS/demo",
        "tool_input": {"skill": "diagnosing-bugs",
                       "args": "chase the root cause of this traceback",
                       "caller": {"type": "direct"}},
        "skill": "diagnosing-bugs",
        "args": "chase the root cause of this traceback",
        "caller": {"type": "direct"},
    },
    "scope": {
        "session_id": "signals-scope", "tool_name": "Skill",
        "cwd": "/home/rg/06_SYSTEM/memory",  # not-a-root: a recorded session's cwd, fixture data
        "skill": "adopt-skill", "args": "tidy up the thing",
        "caller": {"type": "direct"},
    },
    "browse": {
        "session_id": "signals-browse", "tool_name": "Skill",
        "cwd": "/tmp",
        "skill": "diagnosing-bugs", "args": "help me understand this module",
        "caller": {"type": "direct"},
    },
    "explicit": {
        "session_id": "signals-explicit", "tool_name": "Skill",
        "cwd": "/tmp",
        "skill": "adopt-skill", "args": "adopt skill from repo",
        "caller": {"type": "slash_command"},
    },
    "external": {
        "session_id": "signals-external", "tool_name": "Skill",
        "cwd": "/tmp",
        "skill": "not-a-canonical-skill", "args": "whatever this is",
        "caller": {"type": "direct"},
    },
}

from lib import invocation

SPEC = invocation.Spec(
    name="selftest",
    usage="selftest [--all] [--signals] [--schema] [--hook-cost] [--invariants]",
    flags=("--all", "--signals", "--schema", "--hook-cost", "--invariants"))

TS = re.compile(r'"ts":"[^"]*"')


def _run(cmd, payload, data_dir):
    env = dict(os.environ, PAZRAS_DATA_DIR=str(data_dir))
    subprocess.run(cmd, input=payload.encode(), env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    log = data_dir / "skill-usage.jsonl"
    return log.read_text().strip().split("\n")[-1] if log.exists() else ""


def signals() -> int:
    bad = 0
    print("capture signals: 5 payloads, each into its own path\n")
    for name, obj in PAYLOADS.items():
        payload = json.dumps(obj)
        with tempfile.TemporaryDirectory() as a:
            got = _run([str(PY), "capture", "--harness=claude", "--event=PostToolUse"],
                       payload, pathlib.Path(a))
        g = TS.sub('"ts":"-"', got)
        print("  %-9s %s" % (name, g))
        # The point of the fixture is that each payload exercises its own path.
        sig = json.loads(g).get("signal") if g else None
        if sig != name:
            print("    !! classified %r, fixture intends %r" % (sig, name))
            bad += 1

    # SessionEnd writes a different log; check that half too.
    se = json.dumps({"session_id": "signals-se", "transcript_path": "/nonexistent",
                     "cwd": "/tmp"})
    with tempfile.TemporaryDirectory() as a:
        env = dict(os.environ, PAZRAS_DATA_DIR=a)
        subprocess.run([str(PY), "capture", "--harness=claude", "--event=SessionEnd"],
                       input=se.encode(), env=env, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
        line = (pathlib.Path(a) / "session.log").read_text().split("\t", 1)[-1]
    ok = bool(line.strip())
    bad += not ok
    print("  %-9s %s\n    %s" % ("sessionend", "OK" if ok else "EMPTY", line.strip()))

    print("\n%s" % ("CAPTURE SIGNALS OK" if not bad
                    else "CAPTURE SIGNALS FAILED (%d)" % bad))
    return 0 if not bad else 1


def hook_cost(n: int = 20) -> int:
    """Wall-clock for one capture invocation, plus the import breakdown."""
    payload = json.dumps(PAYLOADS["browse"])
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, PAZRAS_DATA_DIR=d)
        for cmd, label in ((PY, "python"),):
            times = []
            for _ in range(n):
                t0 = time.perf_counter()
                subprocess.run([str(cmd), "capture", "--harness=claude",
                                "--event=PostToolUse"], input=payload.encode(), env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               check=False)
                times.append((time.perf_counter() - t0) * 1000)
            times.sort()
            print("  %-8s median %6.1f ms   min %6.1f   max %6.1f   (n=%d)"
                  % (label, times[n // 2], times[0], times[-1], n))

        out = subprocess.run([sys.executable, "-X", "importtime", str(PY), "capture",
                              "--harness=claude", "--event=PostToolUse"],
                             input=payload.encode(), env=env,
                             capture_output=True, check=False)
    rows = []
    for line in out.stderr.decode().split("\n"):
        p = line.split("|")
        if len(p) == 3 and "cumulative" not in line:
            try:
                rows.append((int(p[1]), p[2].strip()))
            except ValueError:
                pass
    rows.sort(reverse=True)
    print("\n  heaviest imports on the capture path (cumulative us):")
    for us, mod in rows[:8]:
        print("    %8d  %s" % (us, mod))
    heavy = {m for _, m in rows} & {"json", "argparse", "re", "pathlib", "subprocess"}
    if heavy:
        print("\n  !! capture imports %s -- the hook path is meant to stay clear of these"
              % ", ".join(sorted(heavy)))
    return 0


def schema() -> int:
    """What capture writes is what the ledger expects -- including the legacy
    shape, which must stay readable rather than being tidied away."""
    from consolidation import ledger
    bad = 0
    print("schema: capture output vs ledger.USAGE_FIELDS\n")

    with tempfile.TemporaryDirectory() as d:
        base = pathlib.Path(d)
        _run([str(PY), "capture", "--harness=claude", "--event=PostToolUse"],
             json.dumps(PAYLOADS["browse"]), base)
        got = ledger.read(base, ledger.USAGE)
        if got.malformed or len(got) != 1:
            print(f"  written line  MISMATCH — {len(got)} row(s), "
                  f"{got.malformed} malformed")
            bad += 1
        else:
            fields = tuple(got.rows[0])
            ok = set(fields) == set(ledger.USAGE_FIELDS)
            bad += not ok
            print(f"  written line  {'OK' if ok else 'MISMATCH'}")
            if not ok:
                missing = sorted(set(ledger.USAGE_FIELDS) - set(fields))
                extra = sorted(set(fields) - set(ledger.USAGE_FIELDS))
                print(f"    capture writes : {', '.join(fields)}")
                print(f"    ledger expects : {', '.join(ledger.USAGE_FIELDS)}")
                if missing:
                    print(f"    !! capture stopped writing: {', '.join(missing)}")
                if extra:
                    print(f"    !! capture writes an undeclared field: "
                          f"{', '.join(extra)} — declare it in ledger.USAGE_FIELDS")

    # The pre-2026-08-30 shape. These lines are most of the real usage data the
    # system has; a reader that demanded the full field set would drop them.
    with tempfile.TemporaryDirectory() as d:
        base = pathlib.Path(d)
        legacy = {k: "x" for k in ledger.USAGE_FIELDS_LEGACY}
        legacy["ts"] = "2026-08-29T07:19:41Z"
        ledger.append(base, ledger.USAGE, legacy)
        (base / ledger.USAGE).open("a").write("{not json\n")
        got = ledger.read(base, ledger.USAGE)
        ok = len(got) == 1 and got.malformed == 1 and got.rows[0]["ts"][:4] == "2026"
        bad += not ok
        print(f"  legacy line   {'OK' if ok else 'MISMATCH'} — "
              f"{len(got)} readable, {got.malformed} counted unreadable")
        if not ok:
            print("    !! a legacy line must read cleanly and a broken line must "
                  "be COUNTED, never silently dropped")

    print("\n%s" % ("SCHEMA OK" if not bad else "SCHEMA FAILED (%d)" % bad))
    return 0 if not bad else 1


def invariants() -> int:
    """The stage-invariant gate. Failures here are defects in the pass itself,
    not in its inputs, so this is the one selftest that can fail on a tree the
    user has never touched."""
    from consolidation.stages import invariants as inv_mod

    print("invariants: declared stage guarantees, checked against a fixture\n")
    findings = inv_mod.run_all()
    errors = [f for f in findings if f.level == "error"]

    for label, decl in sorted(inv_mod.DECLARED.items()):
        marks = []
        for name, short in (("idempotent", "idem"), ("disjoint", "disj"),
                            ("directional", "dir")):
            marks.append(f"{short}={getattr(decl, name).status}")
        print("  %-16s %-14s %s" % (label, decl.shape, "  ".join(marks)))

    if findings:
        print()
        for f in findings:
            print(f"  {f.level.upper():5} [{f.invariant}] {f.stage}")
            print(f"        {f.detail}")

    print("\n%s" % ("INVARIANTS OK — %d stage(s) declared" % len(inv_mod.DECLARED)
                    if not errors
                    else "INVARIANTS FAILED (%d)" % len(errors)))
    return 0 if not errors else 1


def main(inv) -> int:
    want = set(inv.flags)
    if not want or "--all" in want:
        want = {"--signals", "--schema", "--hook-cost", "--invariants"}
    rc = 0
    if "--signals" in want:
        rc |= signals()
    if "--schema" in want:
        print()
        rc |= schema()
    if "--invariants" in want:
        print()
        rc |= invariants()
    if "--hook-cost" in want:
        print("\nhook cost (capture, one invocation):")
        rc |= hook_cost()
    return rc
