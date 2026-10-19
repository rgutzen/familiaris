"""`familiar`, the one command line (R1l, R2d): its routes are real, complete,
and fail loudly on anything they do not declare."""
import importlib.machinery
import importlib.util
import os
import pathlib
import re
import subprocess
import sys

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[2]
FRONT = ENGINE / "familiar"


def _front():
    loader = importlib.machinery.SourceFileLoader("pazras_front", str(FRONT))
    spec = importlib.util.spec_from_loader("pazras_front", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


P = _front()


def _backend_verbs() -> dict:
    """What each back-end actually dispatches, read from its source."""
    mem = (ENGINE / "cli/familiar-memory.py").read_text()
    ctx = (ENGINE / "cli/familiar-context.py").read_text()
    sysb = (ENGINE / "structure/pazras.sh").read_text()
    utils = (ENGINE / "host/pazras-utils.sh").read_text()
    main_case = sysb[sysb.index("# MAIN COMMAND HANDLER"):]
    return {
        "familiar-memory": set(re.findall(r'if cmd == "([\w-]+)"', mem)),
        "familiar-context": set(re.findall(r'"([\w-]+)": \(cmd_', ctx)),
        "pazras": set(re.findall(r'^    "([\w-]+)"\)', main_case, re.M)),
        "pazras-utils": set(re.findall(r'^    "([\w-]+)"\|', utils, re.M)),
    }


VERBS = _backend_verbs()
# Back-end verbs deliberately without a route, each with its reason.
UNROUTED = {
    ("familiar-memory", "help"): "the back-end's own usage; `familiar` prints the table",
}


def test_every_route_lands_on_a_verb_its_backend_dispatches():
    for subject, verbs in P.ROUTES.items():
        for verb, (backend, prefix, text) in verbs.items():
            assert backend in P.BACKENDS, (subject, verb)
            assert prefix[0] in VERBS[backend], (subject, verb, prefix)
            assert text, (subject, verb)


def test_every_backend_verb_is_reachable():
    """Complete, not just correct: a back-end verb no route reaches is a
    command the one command line silently dropped."""
    routed = {(b, pre[0]) for vs in P.ROUTES.values() for b, pre, _ in vs.values()}
    for backend, verbs in VERBS.items():
        for v in verbs:
            assert (backend, v) in routed or (backend, v) in UNROUTED, (backend, v)


def test_the_subjects_are_the_engines_and_the_registers():
    """Subject ids are the engine's folder names (R1e). `skills` and
    `schedule` have places but no code package of their own."""
    for subject in P.ROUTES:
        assert (ENGINE / subject).is_dir() or subject == "skills", subject


@pytest.mark.parametrize("argv,code", [
    (["nope"], 1), (["knowledge", "nope"], 1), (["knowledge"], 1),
    (["knowledge", "--help"], 0), ([], 0)])
def test_undeclared_input_is_an_error_not_a_guess(argv, code):
    r = subprocess.run([sys.executable, str(FRONT)] + argv,
                       capture_output=True, text=True)
    assert r.returncode == code, r.stderr


def test_a_route_reaches_its_backend():
    r = subprocess.run([sys.executable, str(FRONT), "consolidation", "queue", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "queue" in (r.stdout + r.stderr)


def test_the_front_door_imports_nothing_before_routing():
    """The capture hook runs through here on every SessionEnd."""
    src = FRONT.read_text()
    head = src[:src.index("def usage")]
    imports = re.findall(r"^import (\w+)|^from (\w+)", head, re.M)
    assert {a or b for a, b in imports} == {"os", "sys"}


@pytest.mark.parametrize("argv", [
    ["context", "tree", "--json"],
    ["context", "links", "--json"],
])
def test_the_read_only_context_verbs_run_end_to_end(argv, tmp_path):
    """Dispatch is not execution. `context tree` answered every static check
    for weeks and crashed with a NameError the moment it ran: R2 renamed its
    module and this call site kept the old name, and nothing here ran a verb
    body. Run the read-only ones against a scratch vault.

    `l1 --check` is deliberately absent: exit 3 on drift is its contract.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "CONTEXT.md").write_text("# Vault\n")
    env = {**os.environ, "PAZRAS_AGENTS_DIR": str(vault)}
    r = subprocess.run([sys.executable, str(FRONT)] + argv, cwd=tmp_path,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
