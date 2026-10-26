#!/usr/bin/env python3
"""boundaries/compile.py — one config, three harnesses.

`config/boundaries/*.yaml` is the only place a boundary is written. Each file
is one domain (`read-write`, `git`); all of them compile together to every
surface that can enforce or state a rule:

  1. config/boundaries/boundaries.json   data for `wards`
     (Claude Code PreToolUse) and for the opencode plugin. Level 2 — enforced.
     ALL domains, merged: enforcement does not care which file a rule was in.
  2. ~/.pi/agent/extensions/pi-permission-system/config.json
     the gotgenes permission-system policy. Level 2 — enforced. Model-agnostic
     rules only (`models: all`); the local/remote axis is the Pi guard's job.
  3. config/boundaries/<domain>.md              generated prose, any harness.
     Level 4 — advisory, and labelled as such in the text itself. One per
     domain, beside its source and sharing its stem, so the extension is what
     tells source from output.
  4. a delimited block inside ~/.hermes/memories/MEMORY.md — hermes has no hook
     surface, so this is all it gets. Also level 4, also labelled, all domains.

THE ADVISORY IS DELIBERATELY THIN. It was 3.9 KB of preamble explaining the
enforcement model to a reader who mostly needs to know which paths are shut.
The explanation has one home — `knowledge/system/boundaries/boundaries.md` — and this file
points at it rather than restating it. Rules are what a reader came for.

Usage:
  compile.py                     regenerate every target
  compile.py --check             exit 1 if any target is stale
  compile.py --explain PATH [--model local|remote] [--op read|write|push]

Levels are the ones in memory/knowledge/system/consolidation/memory-mechanisms.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _boundaries import (SOURCE_DIR, JSON_TARGET, HERMES_MEMORY, advisory_target,
                         PI_PERMISSION_CONFIG, sources, BEGIN, BLOCK_ANY, END,
                         load, path_matches, applies, directive_rules,
                         ENTITY_REGISTER, DIRECTIVE_DOMAIN,
                         PUSH_PATTERNS, RTK_PREFIX, escape_patterns as _escape_patterns)
from lib.generated_block import splice
from lib import roots  # noqa: E402  (engine lib, on the path above)

# ── emitters ─────────────────────────────────────────────────────────────────

def emit_json(cfg: dict) -> str:
    return json.dumps(cfg, indent=2) + "\n"


def _rule_line(r: dict) -> str:
    who = {"all": "", "remote": " · remote models only", "local": " · local models only"}[r["models"]]
    how = " · asks, does not refuse" if r.get("decision") == "ask" else ""
    paths = ", ".join(f"`{p['display']}`" for p in r["paths"])
    line = f"- **{r['mode']}**{who}{how} — {paths}\n  {r['reason']}"
    if r.get("instead"):
        line += f"\n  → {r['instead']}"
    return line


def emit_advisory(cfg: dict, domain: str) -> str:
    rules = "\n".join(_rule_line(r) for r in cfg["rules"] if r["domain"] == domain)
    providers = ", ".join(cfg["local_providers"])
    # The directives domain has NO source of its own: its rules are derived
    # from the entity register, and the header must say so or a reader would
    # look for a `directives.yaml` that is not there (R1m).
    source = (f"{roots.rel(ENTITY_REGISTER)} (the entity register — one rule per "
              f"kind marked `directive: true`)"
              if domain == DIRECTIVE_DOMAIN else f"{domain}.yaml")
    return f"""# Boundaries — {domain}

<!-- GENERATED from {source} by {roots.ENGINE_REL}/boundaries/compile.py. Do not hand-edit. -->

Advisory: nothing here is enforced by the harness *reading* it. Claude Code and
opencode also enforce these at the tool call (`{roots.ENGINE_REL}/boundaries/guard.py`,
`{roots.ENGINE_REL}/boundaries/opencode-plugin/`); hermes and anything else rely on you.
`local` means inference on this machine ({providers}) — for a remote model the
same read leaves the machine and cannot be recalled. Why these exist, and what
they do not cover: [[boundaries]].

{rules}

A boundary in your way is a conversation with the user, not a puzzle to route
around. Ask.
"""


PI_PERMISSION_SCHEMA = (
    "https://raw.githubusercontent.com/gotgenes/pi-packages/main/packages/"
    "pi-permission-system/schemas/permissions.schema.json"
)


def _pi_path_patterns(rule: dict) -> list:
    """gotgenes path patterns for one rule's paths: the entry itself and
    everything beneath. `*` is greedy (crosses `/`); a bare directory pattern
    matches only the entry, so both are emitted."""
    out = []
    for p in rule["paths"]:
        d = p["display"].rstrip("/")
        out.append(d)
        out.append(d + "/*")
    return out


def emit_pi_permission(cfg: dict) -> str:
    """The gotgenes permission-system policy, from the same rules.

    ONLY model-agnostic rules (`models: all`) land here: no-push -> bash `ask`,
    no-read-write -> `path` deny, no-write -> `path_write` deny. The
    `models: local|remote` axis is NOT gotgenes' job (it has no model axis) —
    the Pazras-native Pi guard enforces those from config/boundaries/boundaries.json.

    ORDER IS SECURITY: gotgenes resolves last-match-wins, so the catch-all
    `allow` is written FIRST and every deny after it. A deny before the
    catch-all would be silently shadowed back to allow.
    """
    path_map = {"*": "allow"}
    path_read_map = {}
    path_write_map = {}
    bash_map = {"*": "allow"}

    for r in cfg["rules"]:
        if r["models"] != "all":
            continue                      # model axis -> the Pi guard's job
        action = "ask" if r.get("decision") == "ask" else "deny"
        if r["mode"] == "no-read-write":
            for pat in _pi_path_patterns(r):
                path_map[pat] = "deny"
        elif r["mode"] == "no-read":
            for pat in _pi_path_patterns(r):
                path_read_map[pat] = action
        elif r["mode"] == "no-write":
            for pat in _pi_path_patterns(r):
                path_write_map[pat] = action
        elif r["mode"] == "no-push":
            for pat in PUSH_PATTERNS:
                bash_map[pat] = action
                # The rtk pi extension rewrites a command BEFORE this gate sees
                # it (`git push x` -> `rtk git push x`), and a prefix pattern
                # does not match the rewritten form, so without this twin the
                # ask silently became `*: allow` (measured 2026-10-15).
                bash_map[f"{RTK_PREFIX}{pat}"] = action
        elif r["mode"] == "no-host-escape":
            for pat in _escape_patterns(cfg["vocabulary"]["shell"]["host_escape"]):
                bash_map[pat] = action

    permission = {"*": "allow", "path": path_map, "bash": bash_map}
    if path_read_map:
        permission["path_read"] = path_read_map
    if path_write_map:
        permission["path_write"] = path_write_map

    doc = {"$schema": PI_PERMISSION_SCHEMA, "permission": permission}
    if cfg.get("authorizer_chain"):
        # pi-permission-system's chain of `ask` reviewers (docs/configuration.md
        # §Authorizer chain). Naming a link is what gives it authority.
        doc["authorizerChain"] = list(cfg["authorizer_chain"])
    return json.dumps(doc, indent=2) + "\n"


def emit_hermes_block(cfg: dict) -> str:
    """Compact — hermes caps its memory store at 2200 chars (config.yaml)."""
    parts = []
    for r in cfg["rules"]:
        who = {"all": "", "remote": " [remote models]", "local": " [local models]"}[r["models"]]
        paths = " ".join(p["display"] for p in r["paths"])
        how = " [ask first]" if r.get("decision") == "ask" else ""
        parts.append(f"{r['mode']}{who}{how}: {paths}")
    body = "; ".join(parts)
    return (
        f"{BEGIN}\n"
        f"BOUNDARIES (ADVISORY — hermes has no hook surface; nothing here is enforced, "
        f"keeping it is your responsibility). {body}. "
        f"Reasons and what to do instead: {roots.tilde(roots.MEMORY)}/boundaries/.\n"
        f"{END}"
    )


# ── targets ──────────────────────────────────────────────────────────────────

def targets(cfg: dict):
    """(label, path, desired_full_text, spliced?) for each emitter."""
    yield "claude-code", JSON_TARGET, emit_json(cfg), False
    yield "pi", PI_PERMISSION_CONFIG, emit_pi_permission(cfg), False
    for path in sources():
        domain = path.stem
        yield f"advisory:{domain}", advisory_target(domain), emit_advisory(cfg, domain), False
    if directive_rules():
        # Generated, so it appears in `--check` like every other target; and it
        # is skipped rather than written when the register declares no
        # directive kind, so a change of vocabulary removes it at the next
        # compile instead of leaving a stale file claiming rules that are gone.
        yield (f"advisory:{DIRECTIVE_DOMAIN}", advisory_target(DIRECTIVE_DOMAIN),
               emit_advisory(cfg, DIRECTIVE_DOMAIN), False)
    if HERMES_MEMORY.exists():
        current = HERMES_MEMORY.read_text()
        yield "hermes", HERMES_MEMORY, splice(current, emit_hermes_block(cfg), BLOCK_ANY), True


def cmd_compile(cfg: dict, check: bool) -> int:
    stale = 0
    for label, path, desired, _ in targets(cfg):
        current = path.read_text() if path.exists() else None
        if current == desired:
            print(f"  ok     {label:<20} {path}")
            continue
        stale += 1
        if check:
            print(f"  STALE  {label:<20} {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(desired)
            print(f"  wrote  {label:<20} {path}")

    if not HERMES_MEMORY.exists():
        print(f"  skip   {'hermes':<20} {HERMES_MEMORY} does not exist")

    if check and stale:
        print(f"\n{stale} target(s) stale. Run: boundaries/compile.py", file=sys.stderr)
        return 1
    if check:
        print(f"\nAll targets in sync with {SOURCE_DIR.name}/.")
    return 0


# ── --explain ────────────────────────────────────────────────────────────────

def cmd_explain(cfg: dict, path: str, model: str, op: str | None) -> int:
    target = os.path.abspath(os.path.expanduser(path))
    ops = [op] if op else ["read", "write", "push"]
    print(f"path : {target}")
    print(f"model: {model}\n")
    denied_any = False
    for want in ops:
        hits = [
            r for r in cfg["rules"]
            if want in r["denies"]
            and applies(r, model)
            and any(path_matches(p, target) for p in r["paths"])
        ]
        if hits:
            denied_any = True
            r = hits[0]
            src = ", ".join(p["display"] for p in r["paths"])
            verdict = "NEEDS APPROVAL" if r.get("decision") == "ask" else "DENIED"
            print(f"  {want:<5} {verdict} by `{r['mode']}` on {src}")
            print(f"        {r['reason']}")
            if r.get("instead"):
                print(f"        instead: {r['instead']}")
        else:
            print(f"  {want:<5} allowed")
    return 1 if denied_any else 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="boundaries/compile.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if any target is stale")
    ap.add_argument("--explain", metavar="PATH", help="why is this path allowed, denied, or gated on approval")
    ap.add_argument("--model", choices=["local", "remote"], default="remote",
                    help="model class for --explain (default: remote)")
    ap.add_argument("--op", choices=["read", "write", "push"], help="restrict --explain to one operation")
    args = ap.parse_args()

    cfg = load()
    if args.explain:
        return cmd_explain(cfg, args.explain, args.model, args.op)
    return cmd_compile(cfg, args.check)


if __name__ == "__main__":
    sys.exit(main())
