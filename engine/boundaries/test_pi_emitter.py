#!/usr/bin/env python3
"""Regression suite for the Pi emitter in boundaries-compile.

Covers emit_pi_permission() — the gotgenes config.json half of the compile —
and the division of labour between it and the Pi guard: model-AGNOSTIC rules
land in config.json, model-axis rules (models: local|remote) do NOT.

Run: python3 -m pytest engine/boundaries/test_pi_emitter.py -q
   (or directly: python3 engine/boundaries/test_pi_emitter.py)
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from lib import roots  # noqa: E402  (`engine/` is on the path, above)

# The compiler is `boundaries/compile.py` and is imported by path, the way a
# script is. Its module-level code (imports, constants, emitters) is
# side-effect free — only `main()` under `__name__ == "__main__"` does I/O.
_spec = importlib.util.spec_from_loader(
    "boundaries_compile",
    importlib.machinery.SourceFileLoader("boundaries_compile", HERE + "/compile.py"),
)
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)

cfg = bc.load()
doc = json.loads(bc.emit_pi_permission(cfg))
perm = doc["permission"]

fail = 0
skipped = 0


def check(label, cond, needs=None):
    """`needs` names the private input this assertion reads, or None.

    A PUBLISHED tree has none of them: the deny-list is this machine's and the
    classification omits it, so the rules the vault and restic assertions are
    about are simply not in the config there. Those assertions SKIP rather than
    pass -- and they still print, because an assertion that vanishes from the
    output is a coverage gap nobody can see, while a silent pass is worse. What
    travels -- the emitter's own shape, the push patterns, the catch-all
    ordering, the model axis -- runs wherever this does.
    """
    global fail, skipped
    if needs and not roots.instance_here():
        print(f"SKIP  {label}  ({needs} is not in this tree)")
        skipped += 1
        return
    ok = bool(cond)
    fail += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {label}")


# ── model-agnostic rules land in config.json ─────────────────────────────────

# no-read-write (D1, models: all) -> `path` deny, both the entry and children.
check("D1 vault path deny", perm["path"].get("~/03_ZETTEL") == "deny",
      needs="this machine's deny-list")
check("D1 vault path deny /*", perm["path"].get("~/03_ZETTEL/*") == "deny",
      needs="this machine's deny-list")

# no-write (restic, models: all) -> `path_write` deny, not `path`.
check("restic path_write deny",
      perm["path_write"].get("~/.local/share/restic") == "deny",
      needs="this machine's deny-list")
check("restic path_write deny /*",
      perm["path_write"].get("~/.config/restic/*") == "deny",
      needs="this machine's deny-list")

# no-push (models: all, decision: ask) -> bash `ask` on every push spelling.
for pat in bc.PUSH_PATTERNS:
    check(f"push ask: {pat}", perm["bash"].get(pat) == "ask")

# ── model-axis rules must NOT land in config.json (the Pi guard's job) ───────

check("personal docs NOT in path", "Personal-Documents" not in json.dumps(perm))
check("ssh NOT in path", "/.ssh" not in json.dumps(perm))
check("loredb NOT in path", "loredb" not in json.dumps(perm))
check("credentials NOT in path", ".hermes/.env" not in json.dumps(perm))

# ── ordering: catch-all `allow` first (last-match-wins) ──────────────────────
path_keys = list(perm["path"].keys())
check("path catch-all first", path_keys[0] == "*" and perm["path"]["*"] == "allow")
bash_keys = list(perm["bash"].keys())
check("bash catch-all first", bash_keys[0] == "*" and perm["bash"]["*"] == "allow")

# ── the guard and gotgenes must not overlap on any rule ──────────────────────
all_rules = cfg["rules"]
agnostic = {r["mode"] for r in all_rules if r["models"] == "all"}
axised = {r["mode"] for r in all_rules if r["models"] != "all"}
check("no mode appears in both", not (agnostic & axised))

# ── a template is not an input ───────────────────────────────────────────────
# `rules.example.yaml` travels (the deny-list does not), so this runs in both
# trees: it is the one place where a case about `sources()` is cheaper than a
# new suite, because this suite already drives `bc.load()` un-skipped in the
# export. What it protects: the example is a file the reader COPIES to a name
# of their own, and a compiler that read it would enforce paths nobody chose
# and leave every rule standing twice.
check("*.example.yaml is not a source",
      all(not p.name.endswith(".example.yaml") for p in bc.sources()))
check("the example travels and is not loaded",
      (roots.CONFIG / "boundaries" / "rules.example.yaml").exists()
      and "rules.example" not in json.dumps(cfg))

print()
print(f"FAILURES: {fail}" + (f", {skipped} skipped -- the assertion measures "
                              f"this instance" if skipped else ""))
sys.exit(1 if fail else 0)
