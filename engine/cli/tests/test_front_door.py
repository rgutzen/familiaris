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


def _shell_verbs() -> dict:
    """What each surviving shell back-end dispatches, read from its source.

    The two Python back-ends are gone (dev/architecture 3b): a route names the
    entry function itself, so there is no second table here to hold in
    agreement with `ROUTES`."""
    sysb = (ENGINE / "structure/pazras.sh").read_text()
    utils = (ENGINE / "host/pazras-utils.sh").read_text()
    main_case = sysb[sysb.index("# MAIN COMMAND HANDLER"):]
    return {
        "structure/pazras.sh": set(re.findall(r'^    "([\w-]+)"\)', main_case, re.M)),
        "host/pazras-utils.sh": set(re.findall(r'^    "([\w-]+)"\|', utils, re.M)),
    }


VERBS = _shell_verbs()


def test_every_exec_route_lands_on_a_verb_the_script_dispatches():
    for subject, verbs in P.ROUTES.items():
        for verb, route in verbs.items():
            kind, target, prefix, _, text = route
            assert kind in ("py", "exec"), (subject, verb)
            assert text, (subject, verb)
            if kind != "exec":
                assert target.count(":") == 1, (subject, verb, target)
                continue
            if target not in VERBS:
                # A direct script, not one dispatched by a shell back-end.
                assert prefix == [], (subject, verb, prefix)
                assert (ENGINE / target).is_file(), (subject, verb, target)
                continue
            assert prefix[0] in VERBS[target], (subject, verb, prefix)


def test_every_shell_verb_is_reachable():
    """Complete, not just correct: a script verb no route reaches is a command
    the one command line silently dropped."""
    routed = {(r[1], r[2][0]) for vs in P.ROUTES.values() for r in vs.values()
              if r[0] == "exec" and r[2]}          # a direct script has no prefix
    for script, verbs in VERBS.items():
        for v in verbs:
            assert (script, v) in routed, (script, v)


def test_every_python_route_names_a_callable():
    """The route table is the only declaration, so every target must resolve.
    `import` only here, not in `familiar`'s own import path."""
    sys.path.insert(0, str(ENGINE))
    for subject, verbs in P.ROUTES.items():
        for verb, route in verbs.items():
            if route[0] != "py":
                continue
            module, _, func = route[1].partition(":")
            if not route[2]:                 # the function parses its own flags
                assert callable(getattr(__import__(module, fromlist=["x"]), func)),                     (subject, verb)
                continue
            mod = __import__(module, fromlist=["x"])
            assert callable(getattr(mod, func)), (subject, verb, route[1])
            assert hasattr(mod, route[2]), (subject, verb, route[2])


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


@pytest.mark.parametrize("subject, verb, argv, code", [
    # A verb whose back-end once had its OWN sub-parsers lost the verb to the front
    # door and answered argparse's usage instead (relay, 2026-10-20): the route's
    # entry function gets only the words after the verb.
    ("relay", "status", ["--check"], 3),
    ("relay", "pause", [], 2),
    ("schedule", "sessions", ["list"], 0),
])
def test_a_verb_with_its_own_flags_reaches_its_entry(subject, verb, argv, code, tmp_path):
    r = subprocess.run([sys.executable, str(FRONT), subject, verb, *argv],
                       capture_output=True, text=True,
                       env={**os.environ, "PAZRAS_DATA_DIR": str(tmp_path / "data"),
                            "FAMILIAR_RELAY_SOCK": str(tmp_path / "no.sock")})
    assert r.returncode == code, (r.stdout, r.stderr)


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
    env = {**os.environ, "PAZRAS_MEMORY_DIR": str(vault)}   # what `familiar` reads
    r = subprocess.run([sys.executable, str(FRONT)] + argv, cwd=tmp_path,
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
