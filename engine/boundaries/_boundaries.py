"""Shared loader for config/boundaries/*.yaml.

Imported by BOTH `boundaries-compile` (which emits the compiled artefacts) and
`wards` (which enforces them). They cannot disagree about what a rule
means, because there is one implementation of "what a rule means".

ONE DOMAIN PER FILE, ALL FILES COMPILED TOGETHER. `read-write.yaml` holds
filesystem access, `git.yaml` holds publication. They were one file until
2026-09-04, when the name `read-write` stopped covering a `no-push` rule it
contained. Splitting by domain keeps each filename honest as rules accumulate;
merging them here keeps enforcement single -- the guard sees one rule list and
does not know or care which file a rule arrived in.

Rules are merged in filename order and each carries the `domain` it came from,
which is what lets the advisory copies be emitted per domain while the guard's
JSON and hermes' block stay whole.

Stdlib only, on purpose: the guard runs as a PreToolUse hook on every single
tool call, and an import that can go missing mid-session is a hook that can
fail open without anyone noticing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# `_miniyaml` moved to `engine/lib/` on 2026-09-30, when the ontology became its
# second caller: one parser for the YAML subset every config in this repo uses,
# not two copies that can drift. The `generated_block.py` precedent exactly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import _miniyaml  # noqa: E402
from lib import paths, roots  # noqa: E402

REPO = roots.REPO
SOURCE_DIR = roots.BOUNDARIES
# The entity register. Its DIRECTIVE kinds are compiled into `ask` rules below,
# so the file is part of this compile's input and part of its digest.
ENTITY_REGISTER = roots.ONTOLOGY / "entities.yaml"
# The domain the derived rules carry, and the advisory they get of their own:
# no `*.yaml` declares them, because nothing human wrote them. One domain per
# source, and this is the one source that is a register.
DIRECTIVE_DOMAIN = "directives"
# The register's `root:` vocabulary, which is not `roots.*`'s: `repo` means
# "from the repository root", `memory` means "from the vault".
ROOT_REPO = "repo"
JSON_TARGET = roots.BOUNDARIES_JSON
HERMES_MEMORY = Path.home() / ".hermes" / "memories" / "MEMORY.md"
# Pi's gotgenes permission-system reads its policy from this file, independent
# of where the package itself is installed (npm packages land under
# ~/.pi/agent/npm/; config stays under extensions/<name>/config.json).
PI_PERMISSION_CONFIG = (Path.home() / ".pi" / "agent" / "extensions"
                        / "pi-permission-system" / "config.json")


def source_digest() -> str:
    """One hash over every input to the compile: the domain files in the order
    `load()` reads them, then the entity register.

    `load()` and this must agree byte-for-byte or the guard re-parses the YAML
    on every single tool call, so the digest is computed in one place and used
    by both. The REGISTER is in it because `load()` derives rules from it: a
    register edit that did not move the digest would leave the guard enforcing
    yesterday's directive paths from a compiled file it believed was current
    -- the drift-with-a-warning this function exists to prevent, one layer up.

    Reading bytes, not parsing: this runs on the fast path of every tool call.
    """
    digest = hashlib.sha256()
    for path in sources():
        digest.update(path.read_bytes())
    digest.update(b"\0" + DIRECTIVE_DOMAIN.encode() + b"\0")
    try:
        digest.update(ENTITY_REGISTER.read_bytes())
    except OSError:
        pass          # absent is a change too, and the next compile says so
    return digest.hexdigest()


def sources() -> list[Path]:
    """Every domain file, in a stable order. A new domain is a new file here
    and needs no code change.

    `*.example.yaml` is NOT a domain. `rules.example.yaml` is the template an
    install copies to `read-write.yaml` and edits (P5), and compiling it would
    do two wrong things at once: enforce paths the reader never chose -- level
    2 rules, in `boundaries.json`, on a fresh clone -- and leave a second
    copy of every rule standing beside the file they copied it to, with an
    advisory of its own under the stem `rules.example.md`. The stem is why
    the skip is here and not at the call sites: `domain = path.stem` would
    otherwise put a dot in a filename."""
    return sorted(p for p in SOURCE_DIR.glob("*.yaml")
                  if not p.name.endswith(".example.yaml"))


def advisory_target(domain: str) -> Path:
    """The compiled prose copy sits beside its source and shares its stem, so
    `read-write.yaml` -> `read-write.md`. Extension tells source from output."""
    return SOURCE_DIR / f"{domain}.md"


BEGIN = f"<!-- BEGIN GENERATED boundaries — {roots.from_home(roots.BOUNDARIES)}/ -->"
END = "<!-- END GENERATED boundaries -->"
# Match any generation's opening marker, not just this one's. When BEGIN's text
# changed on 2026-09-04 the splice failed to find the old block, appended a
# second one, and hermes carried two contradictory copies until someone looked.
BLOCK_ANY = re.compile(
    r"<!-- BEGIN GENERATED boundaries.*?<!-- END GENERATED boundaries -->\n?", re.S)

MODES = {
    # mode           -> which operations it denies
    "no-read-write": {"read", "write"},
    "no-read":       {"read"},
    "no-write":      {"write"},
    "no-push":       {"push"},
}
MODEL_CLASSES = {"all", "local", "remote"}

# How hard a matching rule bites. Orthogonal to MODES: the mode says WHICH
# operations a rule covers, the decision says what happens when one matches.
#   deny — refuse outright; the agent cannot proceed and must ask.
#   ask  — surface a confirmation prompt to the user, who approves or refuses.
# `ask` exists because a rule whose own reason says "ask the user" but which
# compiles to a hard deny can never be satisfied, and an unsatisfiable rule
# trains an agent to read the boundary as noise.
DECISIONS = {"deny", "ask"}


# ── load and validate ────────────────────────────────────────────────────────

def load() -> dict:
    """Every domain file, validated and merged into one rule list."""
    files = sources()
    if not files:
        die(f"no *.yaml in {SOURCE_DIR}")

    out: list[dict] = []
    providers: list[str] = []
    for path in files:
        cfg = _miniyaml.load(path.read_text())
        out += _load_one(path, cfg)
        for prov in (cfg.get("local_providers") or []):
            if prov not in providers:
                providers.append(prov)

    out += directive_rules()

    return {
        "generated_from": (f"{roots.rel(roots.BOUNDARIES)}/*.yaml + "
                           f"{roots.rel(ENTITY_REGISTER)}"),
        "generated_by": f"{roots.ENGINE_REL}/boundaries/compile.py",
        "do_not_edit": f"Edit {roots.rel(roots.BOUNDARIES)}/*.yaml and re-run boundaries/compile.py.",
        "source_sha256": source_digest(),
        "version": 1,
        "local_providers": providers,
        "rules": out,
    }


def _load_one(path: Path, cfg: dict) -> list[dict]:
    domain = path.stem
    where = f"{path.name}"

    if str(cfg.get("version")) != "1":
        die(f"{where}: unsupported version {cfg.get('version')!r}; this compiler speaks 1")
    if not isinstance(cfg.get("rules"), list) or not cfg["rules"]:
        die(f"{where}: no rules")

    default_models = (cfg.get("defaults") or {}).get("models", "all")
    out = []
    for n, rule in enumerate(cfg["rules"], 1):
        if not isinstance(rule, dict):
            die(f"{where}: rule {n} is not a mapping")
        if ("path" in rule) == ("paths" in rule):
            die(f"{where}: rule {n}: give exactly one of `path:` or `paths:`")
        paths = [rule["path"]] if "path" in rule else rule["paths"]
        if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
            die(f"{where}: rule {n}: `paths:` must be a list of non-empty strings")

        mode = rule.get("mode")
        if mode not in MODES:
            die(f"{where}: rule {n}: mode {mode!r} not one of {sorted(MODES)}")
        models = rule.get("models", default_models)
        if models not in MODEL_CLASSES:
            die(f"{where}: rule {n}: models {models!r} not one of {sorted(MODEL_CLASSES)}")
        decision = rule.get("decision", "deny")
        if decision not in DECISIONS:
            die(f"{where}: rule {n}: decision {decision!r} not one of {sorted(DECISIONS)}")
        if not rule.get("reason"):
            die(f"{where}: rule {n}: every rule needs a `reason:` — it is what the denial quotes")

        expanded = []
        for p in paths:
            # A rule path that is not absolute is INSIDE the installed tree,
            # not inside whatever directory the compiler happened to run from.
            # `os.path.abspath` resolved it against the cwd, so the compiled
            # JSON named the checkout the compile ran in: from a worktree the
            # guard protected the worktree's copy of `engine/harness/jev.py`
            # and the main tree was unguarded, and a fresh clone regenerated a
            # different file than the one committed (measured 2026-10-14,
            # the publication track's recut of 2026-10-14 (git history) §2). INSTALL is the tree
            # the harnesses read, and it is the same constant in every
            # checkout, which is what makes `compile.py --check` portable.
            expanded_p = os.path.expanduser(p)
            if not os.path.isabs(expanded_p):
                expanded_p = str(roots.INSTALL / expanded_p)
            abs_p = os.path.abspath(expanded_p)
            real_p = os.path.realpath(abs_p)
            expanded.append({
                "display": p,
                "abs": abs_p,
                "real": real_p if real_p != abs_p else None,
            })
        out.append({
            "domain": domain,
            "paths": expanded,
            "mode": mode,
            "denies": sorted(MODES[mode]),
            "decision": decision,
            "models": models,
            "reason": " ".join(rule["reason"].split()),
            "instead": rule.get("instead"),
            "see": rule.get("see"),
        })

    return out


# ── the directive rules, derived from the entity register ────────────────────

# `_miniyaml` returns every scalar as TEXT, so a boolean arrives as "true".
# Spelled here rather than imported from `ontology.BOOL_FIELDS`: the guard runs
# on every tool call and imports nothing above `lib`.
TRUE = "true"


def directive_rules() -> list[dict]:
    """One `ask` rule per entity kind the register declares DIRECTIVE (R1m).

    R1m replaced an instruction with a mechanism. "Human-owned" was a sentence
    in a file an agent was asked to obey -- level 4, advisory, unenforceable in
    the harness. The register already knew which kinds those were, so the rules
    are DERIVED from it: a kind marked `directive: true` becomes
    `no-write` + `decision: ask` over its own pattern's directory, and a kind
    the user stops marking directive stops being asked about at the next
    compile. A hand-written list here would be a second register.

    `no-write`, never `no-read`: the directive files are the always-loaded set
    (`context/pazras.ALWAYS_LOADED`), so an agent that could not READ them
    could not work. What the user decides is who may WRITE.

    Returns [] when the register declares none, rather than dying: a compile
    that emits nothing is visible in the advisory and in `--explain`, while a
    guard that refuses to start is a session with no boundary at all.
    """
    try:
        entries = (_miniyaml.load(ENTITY_REGISTER.read_text()) or {}).get("entities") or []
    except OSError:
        die(f"no entity register at {roots.rel(ENTITY_REGISTER)} -- the "
            f"directive kinds cannot be derived")
    except Exception as exc:                    # a parse error carries its line
        die(f"{roots.rel(ENTITY_REGISTER)}: {exc}")

    out = []
    for e in entries:
        if not isinstance(e, dict) or str(e.get("directive", "false")) != TRUE:
            continue
        head = paths.literal_head(str(e.get("pattern") or ""))
        if not head:
            die(f"entity {e.get('id')!r} is directive but its pattern "
                f"{e.get('pattern')!r} names no directory")
        root = str(e.get("root") or roots.MEMORY_REL)
        if root not in (roots.MEMORY_REL, ROOT_REPO):
            die(f"entity {e.get('id')!r}: unknown root {root!r}; the register "
                f"speaks {roots.MEMORY_REL!r} and {ROOT_REPO!r}")
        rel = f"{roots.MEMORY_REL}/{head}" if root == roots.MEMORY_REL else head
        # INSTALL, not the checkout: these rules protect the tree the harnesses
        # actually read, and `roots.tilde` names it the same way.
        path = roots.INSTALL / rel
        eid = e.get("id")
        out.append({
            "domain": DIRECTIVE_DOMAIN,
            "derived_from": f"entities.yaml:{eid}",
            "paths": [{"display": roots.tilde(roots.REPO / rel),
                       "abs": os.path.abspath(path),
                       "real": None}],
            "mode": "no-write",
            "denies": ["write"],
            "decision": "ask",
            "models": "all",
            "reason": (
                f"`{eid}` is a DIRECTIVE kind ({roots.rel(ENTITY_REGISTER)}): "
                f"these are the user's own files, and an agent proposes a "
                f"change to them, never makes one. Derived from the register, "
                f"so it is the user's to move or to stop marking directive."),
            "instead": "say what you would change and let the user make the "
                       "edit, or file it as a proposal",
            "see": roots.rel(ENTITY_REGISTER),
        })
    return out


def die(msg: str) -> None:
    print(f"boundaries/compile.py: {SOURCE_DIR.name}: {msg}", file=sys.stderr)
    sys.exit(2)




# ── matching ─────────────────────────────────────────────────────────────────

def path_matches(rule_path: dict, target: str) -> bool:
    """True if `target` is the rule path or lives under it."""
    for key in ("abs", "real"):
        base = rule_path.get(key)
        if base and (target == base or target.startswith(base.rstrip("/") + "/")):
            return True
    return False


def applies(rule: dict, model_class: str) -> bool:
    return rule["models"] in ("all", model_class)


def compiled() -> dict:
    """The rule set to enforce, guaranteed current.

    Reads the compiled JSON (fast path) but checks its `source_sha256` against
    the live YAML. On a mismatch the YAML wins and is parsed directly: a stale
    compile must never cause the *wrong* rules to be enforced, and must never
    cause every tool call to be denied either. Drift costs a warning and a few
    milliseconds, not correctness.
    """
    live = source_digest()
    try:
        cfg = json.loads(JSON_TARGET.read_text())
        if cfg.get("source_sha256") == live:
            return cfg
        print("guard.py: boundaries.json is stale; parsing "
              f"{roots.rel(roots.BOUNDARIES)}/*.yaml directly. Run boundaries/compile.py.", file=sys.stderr)
    except Exception:
        pass
    return load()
