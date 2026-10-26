#!/usr/bin/env python3
"""deepen_probe -- the improver, held to its contract on three fixtures.

WHY A PROBE AND NOT AN ASSERTION ON A LIVE CALL. `deepen.md` is prose: what can
regress without anyone noticing is the SHAPE the `rewrite` contract checks (the
labelled lines, one block, the `kept:` quotes drawn from the task) and the role
text that asks for it. Neither shape depends on which model answered, but the
DEFAULT RUN IS NOT FREE: it goes through the binding, so `--check` spends one real
call per fixture on the chain `role:deepen` resolves to (today deepseek-flash) and
is therefore a gate a person runs, never CI. `--free` is the offline path -- the
local 30B through `pi-agent` -- and it asserts nothing, so `--check --free` reports
and exits 0.

WHAT IT CANNOT SEE. Whether a rewrite is DEEPER. A 30B produced a well-formed
rewrite that narrowed an open question into `grep 'drop'` and then reported
`self: no weak instruction found`. So `--judge` exists as a separate, opt-in run
on the role's own model: only there are the content expectations asserted, and
only a person's reading should ever be the final word.

Exit codes follow `skills index --check`: 0 ok, 1 a harness error, 3 a fixture
whose reply broke its contract. `--check` is the gate; a bare run prints the
replies so a person can read them.

    python3 engine/orchestration/deepen_probe.py --check
    python3 engine/orchestration/deepen_probe.py --only vague      # print one reply
    python3 engine/orchestration/deepen_probe.py --free            # local, asserts nothing
    python3 engine/orchestration/deepen_probe.py --judge           # the role's model
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from orchestration import bindings                                    # noqa: E402

LOCAL = "qwen3:30b-a3b-thinking-2507-q4_K_M"
FAMILIAR = pathlib.Path(__file__).resolve().parents[1] / "familiar"

# Each fixture: the prompt, and the strings its reply must contain when a model
# capable of reading the field runs it. The `expect` lines hold on ANY model
# because they are the contract's own vocabulary.
FIXTURES = [
    {
        "name": "vague",
        "text": "have a look at the consolidation staging and tell me if it is fine",
        "expect": ["field:", "check:", "```"],
        "judge": ["raw:", "reject:"],
    },
    {
        "name": "followup",
        "text": "and can a leaf vanish without a trace?",
        "expect": ["field:", "check:", "```", "kept:"],
        "judge": ["kept:"],
    },
    {
        "name": "already-deep",
        # Self-contained on purpose: an improver with no tools cannot read a file, and
        # a prompt that needs one gets "I cannot read files", which tests nothing.
        "text": "Name the two confounds that would make a rise in 40 Hz gamma "
                "uninformative about local circuit activity, and say which "
                "measurement separates them. Cite the effect size that would settle it.",
        "expect": ["field:", "```"],
        "judge": ["reject: none", "add: none"],
    },
]


def reply_of(stdout: str) -> str:
    """The child's reply: everything above the `binding:` line the runner appends.
    Cutting there rather than filtering prefixes -- a reply's own indented bullets
    once vanished into the runner's indented problem list."""
    lines = stdout.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("binding: "):
            return "\n".join(lines[:i]).rstrip()
    return stdout.rstrip()


def run_one(fx: dict, free: bool, cwd: pathlib.Path, timeout: float) -> tuple:
    """(the reply, the contract verdict). Through the BINDING by default -- the
    production path, so the chain, its fallbacks and the contract all run -- and
    through `pi-agent` with the local 30B under `--free`, which asserts nothing."""
    if free:
        proc = subprocess.run(
            [*bindings.pi_agent(), "deepen", fx["text"], "--model", LOCAL,
             "--cwd", str(cwd), "--no-log", "--timeout", str(timeout)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        reply, rc = reply_of(proc.stdout), proc.returncode
    else:
        proc = subprocess.run(
            [sys.executable, str(FAMILIAR), "orchestration", "bindings", "run",
             "role:deepen", fx["text"], "--cwd", str(cwd), "--timeout", str(timeout)],
            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        reply, rc = reply_of(proc.stdout), proc.returncode
    if rc != 0 and not reply.strip():
        raise RuntimeError(proc.stderr.strip() or f"the child exited {rc}")
    return reply, bindings.verify("rewrite", reply, cwd, task=fx["text"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="hold the improver to its contract")
    ap.add_argument("--check", action="store_true", help="exit 3 when a fixture fails")
    ap.add_argument("--only", help="run one fixture by name")
    ap.add_argument("--free", action="store_true",
                    help="the local 30B through pi-agent: prints the replies, asserts nothing")
    ap.add_argument("--judge", action="store_true",
                    help="also fail a fixture whose reply misses its judgement "
                         "expectations; meaningless with --free, which asserts nothing")
    ap.add_argument("--cwd", default=str(bindings.roots.INSTALL))
    ap.add_argument("--timeout", type=float, default=600.0)
    a = ap.parse_args(argv)
    role = bindings.source_text("role:deepen")
    if not role:
        print("deepen_probe: no role:deepen -- run from the repository", file=sys.stderr)
        return 1
    failures = 0
    for fx in FIXTURES:
        if a.only and fx["name"] != a.only:
            continue
        try:
            reply, verdict = run_one(fx, a.free, pathlib.Path(a.cwd), a.timeout)
        except RuntimeError as e:
            print(f"{fx['name']}: harness error: {e}", file=sys.stderr)
            failures += 1
            continue
        # The SHAPE is asserted on any model; the `judge` lines only under --judge.
        # --free asserts nothing, so --check --free reports and exits 0 — the note
        # below and the exit code must not disagree.
        missing = [w for w in fx["expect"] if w not in reply]
        hint = [w for w in fx["judge"] if w not in reply]
        ok = True if a.free else (verdict.ok and not missing
                                  and not (a.judge and hint))
        print(f"{fx['name']}: {'ok' if ok else 'FAIL'} -- {verdict.summary}")
        for p in verdict.problems:
            print(f"  contract: {p}")
        if missing:
            print(f"  missing from the reply: {missing}")
        if hint:
            tag = ("judge: missing from the reply" if a.judge and not a.free
                   else "a person would look for")
            print(f"  {tag}: {hint}")
        if not a.check or a.only:
            print(reply)
        failures += 0 if ok else 1
    if a.check:
        print(f"deepen probe: {failures} fixture(s) failing"
              f"{' (free: nothing asserted)' if a.free else ''}"
              f"{' (judge: content asserted)' if a.judge and not a.free else ''}")
        return 0 if failures == 0 else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
