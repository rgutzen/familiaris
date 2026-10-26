"""8d's deterministic link (`familiar-delegations`): it grants the floor asks
whose unwrapped unit is a delegation this system owns, and defers on the rest.
The cases are the real asks from the package's review log (2026-09-05 to
2026-10-15), plus the ones that must never pass."""
import json
import pathlib
import shutil
import subprocess

import pytest

EXT = pathlib.Path(__file__).resolve().parents[1] / "pi-asks/index.ts"
IND, OPQ, SUB = "<indirection-bash-wrapper>", "<opaque-bash-wrapper>", "<unparsed-bash-subtree>"

CASES = [
    # (pattern, executedUnit, allowed?)
    (IND, 'pi-agent bash "Run: echo alpha" --session probe', True),
    (IND, 'pi-agent explore "Which file defines the l1 compiler targets?"', True),
    (IND, 'engine/familiar orchestration bindings run tool:read "Where is it set?"; echo rc=$?', True),
    (IND, 'cd ~/06_SYSTEM && engine/familiar orchestration bindings run command:verify "Run it."; echo rc=$?', True),
    (IND, 'pi-agent explore "x" > /tmp/orch/live.txt 2>&1 &\npi-agent review "y" > /tmp/r.txt 2>&1 &\nwait', True),
    (IND, 'PI_PROFILE=private pi-agent research "z"', True),
    (OPQ, "bash -ic 'pi-agent explore x'", False),
    ("git push *", "pi-agent explore x", False),
    (IND, 'pi-agent explore "x"; rm -rf /tmp/y', False),
    (IND, 'pi-agent explore "$(cat /etc/passwd)"', False),
    (IND, "pi-agent explore `id`", False),
    (IND, "env FOO=1 python -m pytest -q", False),
    (IND, "time rm -rf build", False),
    (SUB, "cd ~/06_SYSTEM && python3 - <<'PY'", False),
    (IND, "pi-agent explore x 2>&1 | tail -3", True),
    (IND, "pi-agent explore x | sh", False),
    (IND, "pi-agent explore x | xargs rm", False),
]

DRIVER = """
const m = await import(process.argv[1]);
const out = [];
for (const [pattern, unit] of JSON.parse(process.argv[2])) {
  const log = { review: (e, d) => out.push(["review", e, d.reason]), debug: (e, d) => out.push(["debug", e, d.reason]) };
  const v = await m.authorize({ requestId: "r", payload: { request: { surface: "bash", matchedPattern: pattern, executedUnit: unit } } }, null, log);
  out.push(["verdict", v.kind]);
}
const path = await m.authorize({ payload: { request: { surface: "path", matchedPattern: "*", executedUnit: "pi-agent x" } } }, null, {});
let registered = [], disposed = 0, shutdown = null;
const bus = {};
globalThis[m.SERVICES_KEY] = new Map([["s1", { registerAuthorizer: (n, f) => { registered.push(n); return () => { disposed += 1; }; } }]]);
m.default({ events: { on: (n, f) => { bus[n] = f; } }, on: (n, f) => { if (n === "session_shutdown") shutdown = f; } });
bus["permissions:ready"]({ sessionId: "s1" });
bus["permissions:ready"]({ sessionId: "s1" });
shutdown();
console.log(JSON.stringify({ out, path: path.kind, link: m.LINK, hooks: Object.keys(bus), registered, disposed }));
"""


def run_node(cases):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    p = subprocess.run([node, "--input-type=module", "-e", DRIVER, str(EXT),
                        json.dumps([[a, b] for a, b, _ in cases])],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_pi_asks_grants_only_a_delegation_behind_a_floor():
    got = run_node(CASES)
    verdicts = [x[1] for x in got["out"] if x[0] == "verdict"]
    assert verdicts == ["allow" if ok else "defer" for _p, _u, ok in CASES], \
        [(u[:40], v) for (_p, u, _o), v in zip(CASES, verdicts)]
    reviews = [x for x in got["out"] if x[0] == "review"]
    assert len(reviews) == sum(ok for *_x, ok in CASES), "every grant is in the review log"
    assert all(r[1] == "familiar_delegations.allow" and r[2] for r in reviews)
    assert got["path"] == "defer", "a path ask is never this link's"
    assert got["link"] == "familiar-delegations"
    assert got["hooks"] == ["permissions:ready"], "registers on ready, and only there"
    assert got["registered"] == ["familiar-delegations"], "ready repeats; the link registers once"
    assert got["disposed"] == 1
