"""The CLI stays keyless (item 2f), and the reachability of the key is bounded.

The spec's exit criterion was a literal grep:

    grep -rn "TYPESAFE_API_KEY\\|import jev\\|from .jev" engine/cli/cli.py

That grep was written before 2b added `jev check` -- which is *defined* to read
the key, and is the command that closes step 0d. So the literal form can no longer
hold, and copying it into a test would mean either deleting a required command or
writing a test that fails on correct code.

What the criterion MEANT is asserted here instead, and more tightly than the grep
could: the key is read by the two commands whose whole purpose is the live check,
and by nothing on the `queue`/`decide` path. An import is not the real question
anyway -- the real question is which executable path can reach `load_key`.
"""
import ast
import pathlib
import re

from cli import cli

CLI_PY = pathlib.Path(__file__).resolve().parents[1] / "cli.py"

def _modules(engine):
    """Every module of the six code packages, tests excluded. Until R2c this
    was the one memory package; the scan is as wide as before, plus
    the former context-audit modules -- wider, never looser."""
    for d in ("lib", "knowledge", "harness", "context", "consolidation", "cli"):
        for p in sorted((engine / d).rglob("*.py")):
            if "tests" not in p.relative_to(engine).parts:
                yield p
    yield engine / "familiar"        # the front door (R2d): keyless like the rest


# The only functions allowed to touch the key, and why each is allowed.
KEY_READERS = {
    "jev_cli": "`jev check` — GET /v1/models; this is what closes step 0d",
    "_jev_probe": "`jev probe` — one real call, the only proof the pin resolves",
}


def _functions_importing_jev():
    tree = ast.parse(CLI_PY.read_text())
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for n in ast.walk(node):
            if isinstance(n, ast.ImportFrom) and n.module == "jev":
                out.add(node.name)
            if isinstance(n, ast.ImportFrom) and \
                    any(a.name == "jev" for a in n.names):
                out.add(node.name)
    return out


def test_only_the_jev_check_commands_import_the_client():
    assert _functions_importing_jev() == set(KEY_READERS)


def test_the_decision_path_does_not_import_the_client():
    """`queue` and `decide` read a stored recommendation. They must never reach
    the key -- 2f's actual requirement, and the reason a nightly pass can store
    recommendations the CLI then reads for free."""
    for name in ("show_queue", "decide", "_walk", "_one_resolution", "dismiss",
                 "show_report", "status", "decision"):
        src = ast.get_source_segment(CLI_PY.read_text(),
                                     _find_function(name)) or ""
        assert "jev" not in src.replace("knowledge→skill", ""), (
            f"{name} mentions jev; the decision path must stay keyless")


def _find_function(name):
    for node in ast.walk(ast.parse(CLI_PY.read_text())):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in cli.py")


def test_load_key_is_called_only_from_the_declared_places():
    """One reader is what makes the mode check and the boundaries rule mean
    anything, so the call sites are enumerated rather than assumed.

    Three, and each has a reason:
      * `jev.py` defines it;
      * `cli.py`'s two `jev` check commands call it, and those ARE the live check;
      * `stages/recommend.py` calls it from the PASS, which is the one place a
        recommendation may be computed at all.
    """
    pkg = CLI_PY.parents[1]
    allowed = {"harness/jev.py", "cli/cli.py", "consolidation/stages/recommend.py"}
    callers = set()
    for p in _modules(pkg):
        rel = str(p.relative_to(pkg))
        if rel in allowed or p.name == "__init__.py":
            continue
        if "load_key" in p.read_text():
            callers.add(rel)
    assert callers == set(), f"undeclared key readers: {callers}"


def test_the_env_var_is_not_read_by_the_cli():
    """`TYPESAFE_API_KEY` in the environment would be a second credential path,
    invisible to the boundaries rule (which covers the file, not the variable)."""
    src = CLI_PY.read_text()
    assert "TYPESAFE_API_KEY" not in src
    assert "os.environ" not in src or "TYPESAFE" not in src


def test_the_client_is_the_only_module_naming_the_env_var():
    namers = [p.name for p in _modules(CLI_PY.parents[1])
              if "TYPESAFE_API_KEY" in p.read_text()]
    assert namers == ["jev.py"], namers
