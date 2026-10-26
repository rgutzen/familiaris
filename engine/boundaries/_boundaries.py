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
        digest.update(VOCABULARY.read_bytes() + b"\0")   # a vocabulary edit needs a recompile
    except OSError:
        pass
    try:
        digest.update(ENTITY_REGISTER.read_bytes())
    except OSError:
        pass          # absent is a change too, and the next compile says so
    return digest.hexdigest()


def vocabulary() -> dict:
    """The compiled vocabulary, validated. Every value is configuration: a new
    push verb or mutating command is an edit here and a recompile, not a code
    change (dev/architecture 2c)."""
    try:
        cfg = _miniyaml.load(VOCABULARY.read_text())
    except OSError:
        die(f"no vocabulary at {roots.rel(VOCABULARY)} -- the rules' words have no meaning")
    except Exception as exc:                     # a parse error carries its line
        die(f"{roots.rel(VOCABULARY)}: {exc}")
    return _check_vocabulary(cfg, roots.rel(VOCABULARY))


def _text_list(value, where: str) -> list:
    """A block sequence of non-empty strings. `_miniyaml` returns every scalar as
    TEXT, so a flow list would arrive as one string -- and the parser now raises
    on those (`_reject_flow`), which is the point: a vocabulary that quietly
    means something else is the failure this file would be guarding."""
    if not isinstance(value, list) or not value:
        die(f"{where}: expected a list, got {value!r}")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            die(f"{where}: every entry must be a non-empty string, got {item!r}")
    return [item.strip() for item in value]


def _str_map(value, where: str) -> dict:
    if not isinstance(value, dict) or not value:
        die(f"{where}: expected a mapping, got {value!r}")
    return {str(k): _text_list(v, f"{where}.{k}") for k, v in value.items()}


def _git_rules(value, where: str) -> dict:
    """`{subcommands: [..], with_flag: {commit: [--amend]}}`, both optional but
    at least one present: a git rule that names nothing reads as a rule and
    does nothing."""
    if not isinstance(value, dict):
        die(f"{where}: expected a mapping, got {value!r}")
    out = {}
    if "subcommands" in value:
        out["subcommands"] = _text_list(value["subcommands"], f"{where}.subcommands")
    if "with_flag" in value:
        out["with_flag"] = _str_map(value["with_flag"], f"{where}.with_flag")
    if not out:
        die(f"{where}: needs `subcommands:` or `with_flag:`")
    extra = set(value) - {"subcommands", "with_flag"}
    if extra:
        die(f"{where}: unknown key(s) {sorted(extra)}")
    return out


def _host_escape(value, where: str) -> dict:
    """`shell.host_escape`: which container launches reach the host. Every key
    is required: a section missing `flags:` would read as a rule and wave
    `--privileged` through."""
    lists = ("engines", "subcommands", "flags", "mount_flags", "whole", "beneath")
    if not isinstance(value, dict):
        die(f"{where}: expected a mapping, got {value!r}")
    extra = set(value) - set(lists) - {"flag_values"}
    if extra:
        die(f"{where}: unknown key(s) {sorted(extra)}")
    out = {k: _text_list(value.get(k), f"{where}.{k}") for k in lists}
    out["flag_values"] = _str_map(value.get("flag_values"), f"{where}.flag_values")
    return out


def _tools(value, where: str) -> dict:
    """One harness's tool map: `shell:` (tool -> command field) and `paths:`
    (tool -> {fields, ops}), or a hermes-style `translate_to:` + `tools:`."""
    if not isinstance(value, dict):
        die(f"{where}: expected a mapping, got {value!r}")
    if "translate_to" in value:
        out = {"translate_to": str(value["translate_to"])}
        tools = value.get("tools")
        if not isinstance(tools, dict) or not tools:
            die(f"{where}: `translate_to:` needs a `tools:` mapping")
        out["tools"] = {}
        for name, spec in tools.items():
            if not isinstance(spec, dict) or "as" not in spec:
                die(f"{where}.{name}: needs `as:` (the target harness's tool)")
            fields = spec.get("fields")
            if not isinstance(fields, dict):
                die(f"{where}.{name}: needs `fields:` mapping its argument to the target's")
            out["tools"][name] = {"as": str(spec["as"]),
                                  "fields": {str(k): str(v) for k, v in fields.items()}}
        return out
    out = {}
    if "shell" in value:
        out["shell"] = {str(k): str(v) for k, v in (value["shell"] or {}).items()} or die(
            f"{where}.shell: expected at least one tool")
    paths = value.get("paths")
    if not isinstance(paths, dict) or not paths:
        die(f"{where}: needs a `paths:` mapping")
    out["paths"] = {}
    for tool, spec in paths.items():
        if not isinstance(spec, dict):
            die(f"{where}.{tool}: expected a mapping with `fields:` and `ops:`")
        fields = _text_list(spec.get("fields"), f"{where}.{tool}.fields")
        ops = set(_text_list(spec.get("ops"), f"{where}.{tool}.ops"))
        bad = ops - OPERATIONS
        if bad:
            die(f"{where}.{tool}.ops: {sorted(bad)} not in {sorted(OPERATIONS)}")
        out["paths"][tool] = {"fields": fields, "ops": sorted(ops)}
    return out


def _check_vocabulary(cfg: dict, where: str) -> dict:
    if not isinstance(cfg, dict):
        die(f"{where}: expected a mapping")
    if str(cfg.get("version", "1")) != VOCABULARY_VERSION:
        die(f"{where}: unsupported version {cfg.get('version')!r}")
    out: dict = {}

    modes = cfg.get("modes")
    if not isinstance(modes, dict) or not modes:
        die(f"{where}: needs a `modes:` mapping")
    out["modes"] = {}
    for name, ops in modes.items():
        denies = set(_text_list(ops, f"{where}.modes.{name}"))
        bad = denies - OPERATIONS
        if bad:
            die(f"{where}.modes.{name}: {sorted(bad)} not in {sorted(OPERATIONS)}")
        out["modes"][str(name)] = sorted(denies)

    shell = cfg.get("shell")
    if not isinstance(shell, dict):
        die(f"{where}: needs a `shell:` mapping")
    out["shell"] = {"writes": _text_list(shell.get("writes"), f"{where}.shell.writes"),
                    "writes_with_flag": _str_map(shell.get("writes_with_flag"),
                                                 f"{where}.shell.writes_with_flag")}
    # Optional, so a vocabulary written before 8i still compiles; a judge that
    # meets a `no-delete` rule without them fails CLOSED.
    for key in ("deletes", "delete_safe", "delete_wrappers", "delete_shells"):
        if shell.get(key) is not None:
            out["shell"][key] = _text_list(shell.get(key), f"{where}.shell.{key}")
    for key in ("push", "git_writes"):
        section = shell.get(key)
        if not isinstance(section, dict) or set(section) != {"git"}:
            die(f"{where}.shell.{key}: expected `git:` only")
        out["shell"][key] = {"git": _git_rules(section["git"], f"{where}.shell.{key}.git")}
    out["shell"]["host_escape"] = _host_escape(shell.get("host_escape"),
                                               f"{where}.shell.host_escape")

    tools = cfg.get("tools")
    if not isinstance(tools, dict) or not tools:
        die(f"{where}: needs a `tools:` mapping")
    out["tools"] = {name: _tools(spec, f"{where}.tools.{name}") for name, spec in tools.items()}
    return out


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
                  if not p.name.endswith(".example.yaml") and p.name != VOCABULARY.name)


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

MODEL_CLASSES = {"all", "local", "remote"}

# Where the vocabulary lives. It is a DOMAIN file's neighbour but not a domain:
# `sources()` skips it, because it holds no rules -- it holds what the words in
# the rules MEAN (mode -> denied operations, the commands that write or push,
# each harness's tool -> path field). `compile.py` copies it into
# `boundaries.json` and both judges read it from there.
VOCABULARY = SOURCE_DIR / "vocabulary.yaml"
VOCABULARY_VERSION = "1"
OPERATIONS = {"read", "write", "push", "escape", "delete"}

# How hard a matching rule bites. Orthogonal to MODES: the mode says WHICH
# operations a rule covers, the decision says what happens when one matches.
#   deny — refuse outright; the agent cannot proceed and must ask.
#   ask  — surface a confirmation prompt to the user, who approves or refuses.
# `ask` exists because a rule whose own reason says "ask the user" but which
# compiles to a hard deny can never be satisfied, and an unsatisfiable rule
# trains an agent to read the boundary as noise.
DECISIONS = {"deny", "ask"}


# ── load and validate ────────────────────────────────────────────────────────

# The one place "push" is spelled out for the gotgenes bash surface. These
# patterns must stay in sync with wards's GIT_WRITE regex and the
# opencode plugin's GIT_WRITE — all three are interpretations of the same
# `no-push` rule and disagreeing about "what is a push" is a boundary leak.
# ` *` (space + star) also matches the bare command, so `git push *` gates
# `git push` with no args as well as `git push origin main`.
PUSH_PATTERNS = (
    "git push *",
    "git rebase *",
    "git filter-branch *",
    "git filter-repo *",
    "git commit --amend *",
)

# The prefix the rtk extension puts on a command it rewrites (`rtk rewrite`).
RTK_PREFIX = "rtk "

def escape_patterns(he: dict) -> list[str]:
    """gotgenes bash globs for `no-host-escape`, from `shell.host_escape`.

    COARSER THAN THE TWO JUDGES, in both directions. A glob cannot tokenise:
    `*docker *--pid*host*` also asks for `--pid=1 --network host`, a flag in a
    second command after `;` still counts, and a subcommand is not required.
    The other way, an alias or a variable that hides the engine word passes.
    The leading `*` covers `rtk`, `sudo` and `bash -c '...'` prefixes, so no
    RTK twin is needed here.
    """
    home = os.path.expanduser("~")

    def spell(entry: str) -> list[str]:
        if entry == "~" or entry.startswith("~/"):
            rest = entry[1:]
            return [entry, "$HOME" + rest, "${HOME}" + rest, home + rest]
        return [entry]

    # A `whole` entry is hit by itself or any directory above it, exactly.
    exact = set()
    for entry in he["whole"]:
        exact.update(spell(entry))
        parts = os.path.expanduser(entry).rstrip("/").split("/")
        exact.update("/".join(parts[:i]) or "/" for i in range(1, len(parts)))
    below = [s for entry in he["beneath"] for s in spell(entry)]

    out = []
    for e in he["engines"]:
        for flag in he["flags"]:
            out.append(f"*{e} *{flag}*")
        for flag, values in he["flag_values"].items():
            for v in values:
                for form in dict.fromkeys((v, v.lower())):
                    out.append(f"*{e} *{flag}*{form}*")
        for flag in he["mount_flags"]:
            if flag == "--mount":
                for src in sorted(exact):
                    for key in ("source", "src"):
                        out += [f"*{e} *--mount*{key}={src},*",
                                f"*{e} *--mount*{key}={src} *",
                                f"*{e} *--mount*{key}={src}"]
                for src in below:
                    for key in ("source", "src"):
                        out.append(f"*{e} *--mount*{key}={src}*")
                continue
            joins = (" ", "=", "") if not flag.startswith("--") else (" ", "=")
            for j in joins:
                for src in sorted(exact):
                    out.append(f"*{e} *{flag}{j}{src}:*")
                for src in below:
                    out.append(f"*{e} *{flag}{j}{src}*")
    return list(dict.fromkeys(out))




def bash_pattern_rules(rules: list[dict], vocab: dict) -> dict:
    """gotgenes bash glob -> the index of the rule that emitted it.

    The pattern is what an ask shows (`rule : *docker *--privileged*`); the rule
    is where its `reason` and `instead` live. Deriving the map here, beside the
    pattern generation itself, keeps ONE copy of both: an ask's audit line quotes
    the rule without a second text anywhere. Only model-agnostic rules reach the
    gotgenes surface; the model axis is the Pi guard's job.
    """
    index = {}
    for i, r in enumerate(rules):
        if r["models"] != "all":
            continue
        if r["mode"] == "no-push":
            for pat in PUSH_PATTERNS:
                index[pat] = i
                index[f"{RTK_PREFIX}{pat}"] = i
        elif r["mode"] == "no-host-escape":
            for pat in escape_patterns(vocab["shell"]["host_escape"]):
                index[pat] = i
    return index


def load() -> dict:
    """Every domain file, validated and merged into one rule list."""
    files = sources()
    if not files:
        die(f"no *.yaml in {SOURCE_DIR}")

    vocab = vocabulary()
    out: list[dict] = []
    providers: list[str] = []
    chain: list[str] = []
    for path in files:
        cfg = _miniyaml.load(path.read_text())
        out += _load_one(path, cfg, vocab)
        for prov in (cfg.get("local_providers") or []):
            if prov not in providers:
                providers.append(prov)
        # pi's authorizerChain: an ORDERED list, so the files are read in
        # sources() order and a name is kept where it first appears.
        for link in (cfg.get("authorizer_chain") or []):
            if link not in chain:
                chain.append(link)

    out += directive_rules()

    return {
        "generated_from": (f"{roots.rel(roots.BOUNDARIES)}/*.yaml + "
                           f"{roots.rel(VOCABULARY)} + {roots.rel(ENTITY_REGISTER)}"),
        "generated_by": f"{roots.ENGINE_REL}/boundaries/compile.py",
        "do_not_edit": f"Edit {roots.rel(roots.BOUNDARIES)}/*.yaml and re-run boundaries/compile.py.",
        "source_sha256": source_digest(),
        "version": 1,
        "local_providers": providers,
        "authorizer_chain": chain,
        "vocabulary": vocab,
        "rules": out,
        # Which rule owns an ask's pattern. Derived, never written in a YAML:
        # only the pattern generator knows, and the ask's audit line reads it.
        "bash_pattern_rules": bash_pattern_rules(out, vocab),
    }


def _load_one(path: Path, cfg: dict, vocab: dict) -> list[dict]:
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
        if mode not in vocab["modes"]:
            die(f"{where}: rule {n}: mode {mode!r} not one of "
                f"{sorted(vocab['modes'])} (declared in the vocabulary)")
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
            "denies": vocab["modes"][mode],
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
    (`context/navigation.ALWAYS_LOADED`), so an agent that could not READ them
    could not work. What the user decides is who may WRITE.

    Returns [] when the register declares none, rather than dying: a compile
    that emits nothing is visible in the advisory and in `--explain`, while a
    guard that refuses to start is a session with no boundary at all.
    """
    # The register is read through `knowledge.ontology`, imported HERE and not
    # at module load (dev/architecture 4d): importing that module costs +19.3 ms
    # and `guard.py` imports this one on every tool call, while `directive_rules`
    # runs only at compile time.
    from knowledge import ontology
    try:
        entries = ontology.entity_register()
    except OSError:
        die(f"no entity register at {roots.rel(ENTITY_REGISTER)} -- the "
            f"directive kinds cannot be derived")
    except Exception as exc:                    # a parse error carries its line
        die(f"{roots.rel(ENTITY_REGISTER)}: {exc}")

    out = []
    for eid, e in entries:
        if not e.directive:
            continue
        head = paths.literal_head(str(e.pattern or ""))
        if not head:
            die(f"entity {eid!r} is directive but its pattern "
                f"{e.pattern!r} names no directory")
        root = str(e.root or roots.MEMORY_REL)
        if root not in (roots.MEMORY_REL, ROOT_REPO):
            die(f"entity {eid!r}: unknown root {root!r}; the register "
                f"speaks {roots.MEMORY_REL!r} and {ROOT_REPO!r}")
        rel = f"{roots.MEMORY_REL}/{head}" if root == roots.MEMORY_REL else head
        # INSTALL, not the checkout: these rules protect the tree the harnesses
        # actually read, and `roots.tilde` names it the same way.
        path = roots.INSTALL / rel
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
