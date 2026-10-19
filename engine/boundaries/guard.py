#!/usr/bin/env python3
"""guard.py — structural enforcement of every rule in config/boundaries/.

Claude Code `PreToolUse` hook, and hermes `pre_tool_call` shell hook. Denies any
tool call that crosses a boundary the user declared in `config/boundaries/*.yaml`,
and quotes that rule's own `reason:` back, so a denial is legible instead of
mysterious. A hermes payload is translated into Claude Code's shape on the way in
(`from_hermes`) and the verdict back into hermes's on the way out (`decide`); the
rules in between do not know which harness asked.

Generalised from `zettel-guard` (2026-08-31), which enforced one hard-coded
rule. The hard parts are unchanged and were kept deliberately: the per-tool
PATH_FIELDS map, heredoc stripping, shlex tokenisation with fail-closed on
unbalanced quotes, and the honest limits below.

Escape hatch:  touch ~/.claude/guard.disabled
Re-arm:        rm ~/.claude/guard.disabled
               (~/.claude/zettel-guard.disabled is still honoured for one
                cycle, so an existing hatch does not silently stop working.)

HONEST LIMITS — say these rather than implying the guard is a sandbox:
  * A guard is not a sandbox. The tool-path checks are airtight; the Bash
    scanning is best-effort against DRIFT, not against an adversary. An agent
    set on routing around it can encode a path.
  * Read/write classification of a Bash command is heuristic. `no-read` rules
    therefore deny ANY reference to the path — a false positive there costs a
    question to the user, a false negative costs an irreversible disclosure.
  * PATH_FIELDS covers built-in tools. MCP tools take arbitrary input shapes
    and are NOT covered by any check here.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _boundaries import compiled, path_matches, applies  # noqa: E402
from lib import roots  # noqa: E402  (on the path via _boundaries)

HATCHES = ("~/.claude/guard.disabled", "~/.claude/zettel-guard.disabled")

# Per-tool: which tool_input fields name a PATH, and what the tool DOES with it.
# Grep's `pattern` is a content regex, not a path — searching other files for a
# literal string is fine and must stay allowed.
PATH_FIELDS = {
    "Read":         (["file_path"],                   {"read"}),
    "Glob":         (["pattern", "path"],             {"read"}),
    "Grep":         (["path", "glob"],                {"read"}),
    "Write":        (["file_path"],                   {"write"}),
    "Edit":         (["file_path"],                   {"read", "write"}),
    "NotebookEdit": (["notebook_path", "file_path"],  {"read", "write"}),
}

# hermes tool -> (the Claude Code tool whose rules apply, hermes field -> Claude
# field). `execute_code` is Python, scanned like a shell command: the same
# best-effort drift protection, with the same limit. `patch` in V4A mode names
# its files in the patch body, which `from_hermes` extracts.
HERMES_TOOLS = {
    "read_file":    ("Read",  {"path": "file_path"}),
    "write_file":   ("Write", {"path": "file_path"}),
    "patch":        ("Edit",  {"path": "file_path"}),
    "search_files": ("Grep",  {"path": "path"}),
    "terminal":     ("Bash",  {"command": "command"}),
    "execute_code": ("Bash",  {"code": "command"}),
}
V4A_HEADER = re.compile(r"^\s*\*\*\*\s*(?:Update|Add|Delete|Move) File:\s*(.+?)\s*$", re.M)

# Set by main(): "claude" or "hermes". decide() answers in this dialect.
DIALECT = "claude"

# Heredoc bodies are DATA written somewhere else, not paths being opened.
# Scanning them stops the knowledge base from documenting its own boundaries,
# which is a bug, not safety. The redirect target of `cat > ~/x <<EOF` sits
# outside the body and is still scanned.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\t*\2$", re.S | re.M)

# Command words that mutate a filesystem path. Used only to decide whether a
# Bash command counts as a WRITE for `no-write` rules — a rule that must keep
# allowing reads, or it is useless (you could not run `restic check` otherwise).
MUTATORS = {
    "rm", "rmdir", "mv", "cp", "dd", "truncate", "shred", "tee", "chmod",
    "chown", "chgrp", "ln", "mkdir", "touch", "install", "unlink", "rsync",
    "mkfs", "sponge",
}

# `git push` and the history rewrites. USER.md: committing and branching are
# free; publishing and rewriting are the user's call.
GIT_WRITE = re.compile(
    r"\bgit\b[^;&|]*\b(push|filter-branch|filter-repo|rebase)\b"
    r"|\bgit\b[^;&|]*\bcommit\b[^;&|]*--amend"
)


# ── model class ──────────────────────────────────────────────────────────────

def model_class(payload: dict, local_providers: list) -> str:
    """`local` if inference runs on this machine, else `remote`.

    The PreToolUse payload carries no model field (verified 2026-08-31 by
    dumping one). It does carry `transcript_path`, and every assistant record
    in that JSONL has `message.model`. So the LIVE model is resolvable, which
    beats assuming one class per harness.

    Fails to `remote`: that is the class more rules apply to, so an
    unresolvable model is guarded, not waved through.
    """
    tp = payload.get("transcript_path")
    if not tp:
        return "remote"
    try:
        with open(tp, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 65536))
            chunk = fh.read().decode("utf-8", "ignore")
    except OSError:
        return "remote"
    for line in reversed(chunk.splitlines()):
        try:
            rec = json.loads(line)
        except Exception:
            continue                      # truncated first line, or not JSON
        msg = rec.get("message")
        if rec.get("type") == "assistant" and isinstance(msg, dict) and msg.get("model"):
            name = str(msg["model"]).lower()
            return "local" if any(str(p).lower() in name for p in local_providers) else "remote"
    return "remote"


# ── path resolution ──────────────────────────────────────────────────────────

def candidates(token: str, cwd: str) -> list:
    """Every absolute path a token could plausibly name.

    A bare directory name is resolved against BOTH the cwd and $HOME: it is a
    valid relative path from either, and the original zettel-guard counted it
    for exactly that reason. Deliberately generous — this is drift protection.
    """
    home = os.path.expanduser("~")
    t = token.replace("$HOME", home).replace("${HOME}", home)
    t = os.path.expanduser(t)
    if os.path.isabs(t):
        return [os.path.normpath(t)]
    return [os.path.normpath(os.path.join(cwd, t)),
            os.path.normpath(os.path.join(home, t))]


def spellings(rule_path: dict) -> list:
    """Literal forms of a rule path that a raw command might contain."""
    home = os.path.expanduser("~")
    out = [rule_path["abs"]]
    if rule_path.get("real"):
        out.append(rule_path["real"])
    if rule_path["abs"].startswith(home + "/"):
        rel = rule_path["abs"][len(home) + 1:]
        out += ["~/" + rel, "$HOME/" + rel]
    return out


def command_hits(cmd: str, rule: dict, cwd: str) -> bool:
    """True if a shell command references any path this rule covers."""
    cmd = HEREDOC.sub("<<STRIPPED", cmd)
    try:
        tokens = shlex.split(cmd)
    except ValueError:                    # unbalanced quotes — fail closed
        return True
    for tok in tokens:
        for cand in candidates(tok, cwd):
            if any(path_matches(p, cand) for p in rule["paths"]):
                return True
    # Substrings the tokenizer cannot reach — inside $(...), concatenations.
    for p in rule["paths"]:
        for form in spellings(p):
            if re.search(re.escape(form) + r"($|[/\s'\";)&|])", cmd):
                return True
    return False


# A redirect that names a FILE. `(?!&)` excludes fd duplication — `2>&1` is not
# a write, and treating it as one denied `restic ... snapshots 2>&1 | head` on
# the first live test of the no-write mode.
REDIRECT = re.compile(r"(?:^|[\s;&|(])\d*>>?\s*(?!&)([^\s;&|<>()]+)")


def command_writes(cmd: str, rule: dict, cwd: str) -> bool:
    """Heuristic: does this command mutate a path THIS RULE covers?

    Only consulted for `no-write` rules, and only after the command is known
    to reference the path — a rule that denied reads too would make
    `restic check` impossible, which is the opposite of protecting a backup.

    Two signals, in order of precision:
      1. a redirect whose target resolves under the rule's path — exact;
      2. a mutating command word anywhere in a line that touches the path —
         coarse, and deliberately so. `rm /tmp/x && ls <protected>` is denied.
    """
    cmd = HEREDOC.sub("<<STRIPPED", cmd)
    for m in REDIRECT.finditer(cmd):
        for cand in candidates(m.group(1).strip("'\""), cwd):
            if any(path_matches(p, cand) for p in rule["paths"]):
                return True
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return True
    if any(os.path.basename(t) in MUTATORS for t in tokens):
        return True
    return bool(re.search(r"\bsed\b[^;&|]*\s-\S*i", cmd))


# ── hermes ───────────────────────────────────────────────────────────────────

def from_hermes(tool: str, ti: dict) -> list:
    """`(claude_tool, claude_input)` pairs for one hermes call; [] if unmapped.

    A list because one V4A patch can touch several files, and each is judged.
    `search_files` with `target: files` matches file NAMES, so its `pattern` is
    a path glob there and is checked as `Glob`'s; with `target: content` it is
    a regex over contents and stays allowed, as `Grep`'s does.
    """
    if tool == "search_files" and ti.get("target") == "files":
        return [("Glob", {"pattern": ti.get("pattern"), "path": ti.get("path")})]
    if tool not in HERMES_TOOLS:
        return []
    claude, fields = HERMES_TOOLS[tool]
    out = [(claude, {c: ti[h] for h, c in fields.items() if h in ti})]
    if tool == "patch" and isinstance(ti.get("patch"), str):
        for m in V4A_HEADER.finditer(ti["patch"]):
            for target in m.group(1).split("->"):
                out.append(("Edit", {"file_path": target.strip()}))
    return out


# ── decision ─────────────────────────────────────────────────────────────────

def decide(rule: dict, what: str) -> None:
    """Emit the rule's decision. `deny` refuses; `ask` prompts the user."""
    decision = rule.get("decision", "deny")
    if decision == "ask":
        msg = [f"Confirm — `{rule['mode']}`: {what}.", rule["reason"]]
    else:
        msg = [f"Blocked by wards — `{rule['mode']}`: {what}.", rule["reason"]]
    if rule.get("instead"):
        msg.append(f"Instead: {rule['instead']}.")
    if rule.get("see"):
        msg.append(f"See {rule['see']}.")
    if decision == "ask":
        msg.append("Approving here is the user's call. Do not re-run it another "
                   "way if they decline.")
    else:
        msg.append(f"This rule lives in {roots.from_home(roots.BOUNDARIES)}/, which is "
                   "the user's to change. Do not retry with a different spelling — ask.")
    if DIALECT == "hermes":
        # hermes has no confirm decision, so `ask` blocks: the direction the Bash
        # classifier already errs in. Exit 2 blocks even if stdout is lost.
        json.dump({"decision": "block", "reason": " ".join(msg)}, sys.stdout)
        sys.exit(2)
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": " ".join(msg),
        }
    }, sys.stdout)
    sys.exit(0)


def main() -> None:
    for hatch in HATCHES:
        if os.path.exists(os.path.expanduser(hatch)):
            sys.exit(0)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)                       # no payload to judge — do not block blindly

    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        sys.exit(0)

    cfg = compiled()
    cwd = payload.get("cwd") or os.getcwd()
    # No transcript_path arrives from hermes, so it resolves to `remote` — the
    # class more rules apply to.
    klass = model_class(payload, cfg.get("local_providers") or [])
    rules = [r for r in cfg["rules"] if applies(r, klass)]

    global DIALECT
    if payload.get("hook_event_name") == "pre_tool_call":
        DIALECT = "hermes"
        for claude_tool, claude_ti in from_hermes(tool, ti):
            judge(claude_tool, claude_ti, rules, cwd)
        sys.exit(0)
    judge(tool, ti, rules, cwd)
    sys.exit(0)


def judge(tool: str, ti: dict, rules: list, cwd: str) -> None:
    """Exit through decide() if this call crosses a rule; return if it does not."""
    if tool == "Bash":
        cmd = str(ti.get("command", ""))
        for rule in rules:
            if "push" in rule["denies"]:
                if GIT_WRITE.search(HEREDOC.sub("<<STRIPPED", cmd)) and \
                        any(path_matches(p, cwd) for p in rule["paths"]):
                    decide(rule, "this command pushes or rewrites git history")
                continue
            if not command_hits(cmd, rule, cwd):
                continue
            if "read" in rule["denies"]:
                decide(rule, "this command reaches a path the rule covers")
            if "write" in rule["denies"] and command_writes(cmd, rule, cwd):
                decide(rule, "this command appears to write under a protected path")
        return

    fields, tool_ops = PATH_FIELDS.get(tool, (None, None))
    if not fields:
        return

    for rule in rules:
        overlap = tool_ops & set(rule["denies"])
        if not overlap:
            continue
        for field in fields:
            value = ti.get(field)
            if not isinstance(value, str) or not value:
                continue
            for cand in candidates(value, cwd):
                if any(path_matches(p, cand) for p in rule["paths"]):
                    decide(rule, f"{tool}.{field} would {'/'.join(sorted(overlap))} `{value}`")


if __name__ == "__main__":
    main()
