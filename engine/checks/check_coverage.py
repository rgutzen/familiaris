#!/usr/bin/env python3
"""check_coverage -- every check mode `familiar` offers, against the registry.

THE QUESTION. `checks.py` is the registry of what is checked; `engine/familiar`
is the table of what can be checked. They were two lists kept by hand, and ten
check modes were added to the second and never to the first, so no gate ran
them. This module reads the second and fails when the first has not caught up.

WHAT COUNTS AS A CHECK MODE. A route has one when it accepts a flag from
`CHECK_FLAGS`, found where the flag is DECLARED -- the route's `Spec.flags`, or
the string constants of the function that parses its own argv (one call deep,
because a `main` often builds its parser in a helper) -- and never by running
the verb: `--help` on a verb that does work first would do the work. Every verb
under the subject `checks` is a check by definition, and each of its flags but
`--all` is a mode.

A check whose mode has no flag -- the verb is the check (`posture`,
`backup verify`), or the mode is a word (`ontology check`, `jev check`) -- cannot
be found that way, so `VERB_MODES` declares it. That is a discovery supplement,
not a second registry: the test requires each mode named there to be registered
or excluded like any other, and the verb's usage text to still contain the word,
so a rename breaks the declaration instead of hiding behind it.

EVERY MODE ENDS IN ONE OF TWO STATES: a registry entry whose command invokes it,
or an entry in `NOT_REGISTERED` with the reason. There is no third state, and
the test fails on a mode in neither and on an exclusion or an entry that names
something the route table no longer has.

    python3 engine/checks/check_coverage.py        the table
"""
from __future__ import annotations

import ast
import importlib
import importlib.machinery
import importlib.util
import inspect
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(HERE))

import checks  # noqa: E402

# The flags that mean "report, and exit non-zero on drift". `--validate` and
# `--gate` are the other spellings the route table uses today.
CHECK_FLAGS = frozenset({"--check", "--gate", "--validate"})

# Modes with no flag to find, keyed by route. "" is the verb itself.
VERB_MODES: dict[tuple[str, str], tuple[str, ...]] = {
    ("consolidation", "posture"): ("",),
    ("structure", "validate"): ("",),
    ("backup", "verify"): ("",),
    ("knowledge", "ontology"): ("check", "naming", "review", "selfcheck"),
    ("harness", "jev"): ("check",),
}

# A mode that is not registered, and why. Keyed (subject, verb, mode).
NOT_REGISTERED: dict[tuple[str, str, str], str] = {
    ("checks", "selftest", "--hook-cost"):
        "reports what the capture hook imports and exits 0 whatever it finds; "
        "it measures a cost rather than guarding a state, which is a "
        "performance evaluation (feat/perf-evals), not a gate",
    ("orchestration", "dispatch", "--check"):
        "checks ONE named SPECS.md; `--gate` (registered as specs-dispatchable) "
        "is the same check over every dev/*/SPECS.md",
}


def front_door():
    """`engine/familiar` as a module, without running it."""
    loader = importlib.machinery.SourceFileLoader("familiar_front_door",
                                                 str(ENGINE / "familiar"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _constants(fn, depth: int = 1) -> set[str]:
    """The `--flag` string constants in `fn`'s source, and in the functions of
    its own module that it calls, `depth` calls deep."""
    try:
        source = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return set()
    found = set(re.findall(r"""["'](--[a-z][a-z-]*)["']""", source))
    if depth:
        module = inspect.getmodule(fn)
        called = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
        for name in called:
            callee = getattr(module, name, None)
            if inspect.isfunction(callee) and callee is not fn \
                    and inspect.getmodule(callee) is module:
                found |= _constants(callee, depth - 1)
    return found


def _closure(fn, depth: int) -> list:
    """`fn` and the functions of its own module it calls, `depth` calls deep."""
    seen, frontier = [fn], [fn]
    for _ in range(depth):
        nxt = []
        for f in frontier:
            try:
                tree = ast.parse(textwrap.dedent(inspect.getsource(f)))
            except (OSError, TypeError):
                continue
            module = inspect.getmodule(f)
            for name in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}:
                callee = getattr(module, name, None)
                if inspect.isfunction(callee) and inspect.getmodule(callee) is module \
                        and callee not in seen:
                    seen.append(callee)
                    nxt.append(callee)
        frontier = nxt
    return seen


def _argparse_flags(fn, verb: str) -> set[str]:
    """The flags `add_argument` declares for `verb`, read from the source.

    Never by running the verb. A module that builds ONE parser for several verbs
    (`relay`'s `_parser()` gives each verb a subparser) must not hand every verb
    every verb's flags, so a flag declared on `X = sub.add_parser("name")` belongs
    to `name` alone and a flag on the top-level parser belongs to all.
    """
    owner: dict[str, str] = {}        # variable -> the subparser's name ("" = top level)
    declared: list[tuple[str, str]] = []
    for f in _closure(fn, 2):
        try:
            tree = ast.parse(textwrap.dedent(inspect.getsource(f)))
        except (OSError, TypeError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "add_parser" and node.value.args
                    and isinstance(node.value.args[0], ast.Constant)):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        owner[target.id] = node.value.args[0].value
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_argument"
                    and isinstance(node.func.value, ast.Name)):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and str(arg.value).startswith("--"):
                        declared.append((owner.get(node.func.value.id, ""), arg.value))
    subparsed = any(who for who, _ in declared)
    return {flag for who, flag in declared if not subparsed or who in ("", verb)}


def _route_module(name: str):
    """The module a `py` route names, imported the way the front door would.

    `checks` is two things in this process: the namespace package `engine/checks/`
    (the route `checks.evaluation:main`) and the registry `checks.py`, imported
    above under that bare name. Once the registry holds `sys.modules["checks"]`,
    `import checks.evaluation` fails with "'checks' is not a package", so a route
    under a shadowed package is loaded from its file, under a name of its own.
    """
    top = sys.modules.get(name.partition(".")[0])
    if top is None or hasattr(top, "__path__") or "." not in name:
        return importlib.import_module(name)
    alias = f"_route_{name.replace('.', '_')}"
    if alias not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            alias, ENGINE / (name.replace(".", "/") + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[alias] = module      # a dataclass resolves its module by name
        spec.loader.exec_module(module)
    return sys.modules[alias]


def _flags_of(route, verb: str) -> set[str]:
    """The flags a `py` route declares; the words of its help for an `exec` one."""
    kind, target, spec_attr = route[0], route[1], route[2]
    if kind != "py":
        return set(re.findall(r"--[a-z][a-z-]*", route[-1]))
    module_name, _, func = target.partition(":")
    module = _route_module(module_name)
    if spec_attr:
        return set(getattr(module, spec_attr).flags)
    fn = getattr(module, func)
    return _argparse_flags(fn, verb) | _constants(fn)


def discovered(routes) -> dict[tuple[str, str], tuple[str, ...]]:
    """(subject, verb) -> the check modes the route table gives it."""
    found: dict[tuple[str, str], tuple[str, ...]] = {}
    for subject, verbs in routes.items():
        for verb, route in verbs.items():
            flags = _flags_of(route, verb)
            if (subject, verb) == ("checks", "selftest"):
                modes = sorted(flags - {"--all", "--json"})   # every flag is a self-test
            else:
                modes = sorted(flags & CHECK_FLAGS)
            modes += list(VERB_MODES.get((subject, verb), ()))
            if modes:
                found[(subject, verb)] = tuple(dict.fromkeys(modes))
    return found


def covers(check, subject: str, verb: str, mode: str) -> bool:
    """Whether a registry entry invokes `familiar <subject> <verb> <mode>`."""
    cmd = tuple(str(p) for p in check.command)
    if len(cmd) < 3 or Path(cmd[0]).name != "familiar":
        return False
    return cmd[1] == subject and cmd[2] == verb and (mode == "" or mode in cmd[3:])


def coverage(routes=None, registry=None) -> list[dict]:
    """One row per (subject, verb, mode): who registers it, or why not."""
    routes = routes if routes is not None else front_door().ROUTES
    registry = registry if registry is not None else checks.CHECKS
    rows = []
    for (subject, verb), modes in discovered(routes).items():
        for mode in modes:
            hits = [c for c in registry if covers(c, subject, verb, mode)]
            rows.append({
                "subject": subject, "verb": verb, "mode": mode,
                "entries": [c.id for c in hits],
                "tiers": sorted({g for c in hits for g in c.gates if g in checks.TIERS},
                                key=checks.TIERS.index),
                "gates": sorted({g for c in hits for g in c.gates}),
                "runner": sorted({c.owner or "registry" for c in hits}),
                "excluded": NOT_REGISTERED.get((subject, verb, mode), ""),
            })
    return rows


def findings(routes=None, registry=None) -> list[str]:
    """What is wrong: an unregistered mode, or a declaration that went stale."""
    routes = routes if routes is not None else front_door().ROUTES
    registry = registry if registry is not None else checks.CHECKS
    problems = []
    rows = coverage(routes, registry)
    for r in rows:
        name = f"familiar {r['subject']} {r['verb']} {r['mode']}".rstrip()
        if not r["entries"] and not r["excluded"]:
            problems.append(
                f"{name}: a check mode no registry entry runs and no exclusion "
                f"explains. Add a Check to {checks.E}/checks/checks.py at the tier its "
                f"cost and drift call for, or a reason to NOT_REGISTERED.")
        if r["entries"] and r["excluded"]:
            problems.append(f"{name}: registered ({', '.join(r['entries'])}) AND excluded; "
                            f"drop the exclusion")
    modes = {(r["subject"], r["verb"], r["mode"]) for r in rows}
    for key in NOT_REGISTERED:
        if key not in modes:
            problems.append(f"NOT_REGISTERED names {' '.join(key)!r}, which the route "
                            f"table no longer has as a check mode")
    for (subject, verb), words in VERB_MODES.items():
        route = routes.get(subject, {}).get(verb)
        if route is None:
            problems.append(f"VERB_MODES names familiar {subject} {verb}, which is not a route")
            continue
        usage = _usage(route)
        for word in words:
            if word and not re.search(rf"\b{re.escape(word)}\b", usage):
                problems.append(f"VERB_MODES says familiar {subject} {verb} has the mode "
                                f"{word!r}, but its usage no longer mentions it")
    for c in registry:
        cmd = [str(p) for p in c.command]
        if len(cmd) >= 3 and Path(cmd[0]).name == "familiar":
            if cmd[2] not in routes.get(cmd[1], {}):
                problems.append(f"{c.id}: runs `familiar {cmd[1]} {cmd[2]}`, which is not a route")
    return problems


def _usage(route) -> str:
    """The text a reader sees for the verb: its Spec's usage, else its help."""
    spec_attr = route[2] if route[0] == "py" else ""
    if spec_attr:
        module = _route_module(route[1].partition(":")[0])
        return getattr(module, spec_attr).usage + " " + route[-1]
    if route[0] == "py":
        fn = getattr(_route_module(route[1].partition(":")[0]),
                     route[1].partition(":")[2])
        return (inspect.getdoc(fn) or "") + " " + route[-1] + " " + " ".join(_constants(fn))
    return route[-1]


def render(rows: list[dict]) -> str:
    out = [f"{'subcommand':44}{'mode':12}{'registry entry':30}{'tier / gates':26}runs it"]
    for r in rows:
        name = f"{r['subject']} {r['verb']}"
        entry = ", ".join(r["entries"]) or ("EXCLUDED" if r["excluded"] else "MISSING")
        tier = "/".join(r["tiers"]) or ",".join(r["gates"]) or "-"
        runner = ",".join(Path(x).name for x in r["runner"]) or "-"
        out.append(f"{name:44}{r['mode'] or '(verb)':12}{entry:30}{tier:26}{runner}")
        if r["excluded"]:
            out.append(f"    excluded: {r['excluded']}")
    return "\n".join(out)


def main() -> int:
    print(render(coverage()))
    problems = findings()
    for p in problems:
        print(f"coverage: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
