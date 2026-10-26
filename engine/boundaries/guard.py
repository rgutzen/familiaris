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

import fnmatch
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

# The vocabulary — what the words in a rule MEAN — is configuration, compiled
# into `boundaries.json` from `config/boundaries/vocabulary.yaml` (dev/architecture
# 2c/2d). Nothing in this file names a mutating command, a push verb or a tool's
# path field: those are the user's to edit. What stays here is MECHANISM — how a
# command line is read (quotes, heredocs, redirects).

def _flag_re(flag: str) -> str:
    """A compiled fragment matching `flag` as a token. A long flag must be the
    whole token (`--` is not `--detach`); a short one may lead a cluster
    (`-i` matches `-i.bak`)."""
    esc = re.escape(flag)
    if flag.startswith("--"):
        return r"(?:^|[\s;&|(])" + esc + r"(?=$|[\s;&|)])"
    return r"(?:^|[\s;&|(])" + esc


def _git_re(spec: dict):
    """`\bgit\b ... <subcommand>` for the bare ones, plus `<sub> ... <flag>` for
    each entry under `with_flag:` (a reset only counts when it is `--hard`)."""
    parts = []
    subs = spec.get("subcommands") or []
    if subs:
        parts.append(r"\bgit\b[^;&|]*\b(?:" + "|".join(map(re.escape, subs)) + r")\b")
    for sub, flags in (spec.get("with_flag") or {}).items():
        for flag in flags:
            parts.append(r"\bgit\b[^;&|]*\b" + re.escape(sub) + r"\b[^;&|]*"
                         + _flag_re(flag))
    return re.compile("|".join(parts)) if parts else None


def _uncomment(cmd: str) -> str:
    """Bash comments, read as judge.mjs's `splitPosix` reads them, for `shlex.split`.

    A `#` that starts a word, outside quotes, runs to the end of the line. Its
    quotes are dropped, since the apostrophe in "spec's" is not an open quote and
    left in it fails the split closed against every rule. Its words are kept:
    where shlex and bash disagree about a quote (`$'\\''`), the "comment" may be
    code, and dropping it would hide a path. Not `shlex(comments=True)`: that
    ends a line at any `#`, so `a#b` would become `a`.
    """
    out, quote, word, i, n = [], None, False, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if quote:
            if ch == quote:
                quote = None
            elif quote == '"' and ch == "\\" and i + 1 < n:
                out.append(ch)
                i += 1
                ch = cmd[i]
        elif ch == "#" and not word:
            end = cmd.find("\n", i)
            end = n if end == -1 else end
            out.append(re.sub(r"['\"\\]", "", cmd[i + 1:end]))
            i = end
            continue
        elif ch in "'\"":
            quote, word = ch, True
        elif ch == "\\" and i + 1 < n:
            out.append(ch)
            i += 1
            ch, word = cmd[i], True
        else:
            word = not ch.isspace()
        out.append(ch)
        i += 1
    return "".join(out)


class Vocab:
    """The compiled vocabulary, with the patterns built once per process."""

    def __init__(self, data: dict):
        self.data = data
        shell = data["shell"]
        self.writes = frozenset(shell["writes"])
        self.deletes = frozenset(shell.get("deletes") or ())
        self.delete_safe = tuple(shell.get("delete_safe") or ())
        self.delete_wrappers = frozenset(shell.get("delete_wrappers") or ())
        self.delete_shells = frozenset(shell.get("delete_shells") or ())
        self.writes_with_flag = shell["writes_with_flag"]
        self.git_push = _git_re(shell["push"]["git"])
        self.git_writes = _git_re(shell["git_writes"]["git"])
        self.tools = data["tools"]
        self.escape = shell["host_escape"]
        self.engine_word = re.compile(
            r"\b(?:" + "|".join(map(re.escape, self.escape["engines"])) + r")\b")

    def tool_paths(self, harness: str, tool: str):
        """`(fields, ops)` for one of a harness's tools, or `(None, None)`."""
        spec = ((self.tools.get(harness) or {}).get("paths") or {}).get(tool)
        if not spec:
            return None, None
        return spec["fields"], set(spec["ops"])

    def hermes_tool(self, tool: str):
        """`(the target harness's tool, {hermes field: target field})`, or None."""
        spec = ((self.tools.get("hermes") or {}).get("tools") or {}).get(tool)
        return (spec["as"], spec["fields"]) if spec else None

    def _safe_target(self, candidate: str, cwd: str) -> bool:
        """Is this operand inside a path where destroying is routine?"""
        p = os.path.expanduser(candidate) if candidate.startswith("~") else candidate
        if not os.path.isabs(p):
            p = os.path.join(cwd, p)
        p = os.path.normpath(os.path.abspath(p))
        # A safe entry covers the path itself AND everything below it: a cache
        # directory's contents (`node_modules/.cache`) are as routine as the
        # cache. Compared on every ancestor, so a glob matches at any depth.
        parts = p.split("/")
        ancestors = ["/".join(parts[:i]) or "/" for i in range(1, len(parts) + 1)]
        for entry in self.delete_safe:
            base = entry.rstrip("/")
            for cand in ancestors:
                if any(ch in entry for ch in "*?["):
                    if fnmatch.fnmatch(cand, base):
                        return True
                elif cand == base:
                    return True
        return False

    def _delete_run(self, run: list, cwd: str) -> str | None:
        """One simple command: is its COMMAND WORD a delete, after wrappers?"""
        i = 0
        while i < len(run):
            word = os.path.basename(run[i])
            if word in self.delete_wrappers or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", run[i]):
                i += 1
                continue
            break
        if i >= len(run):
            return None
        word = os.path.basename(run[i])
        if word in self.deletes:
            operands = [t for t in run[i + 1:] if not t.startswith("-")]
            if not operands:
                return "a delete with no visible target"
            for op in operands:
                if not self._safe_target(op, cwd):
                    return f"this command deletes or moves `{op}`"
            return None
        if word in self.delete_shells and "-c" in run:
            # The string is one token, so the delete word is inside it, not a
            # token of its own: `bash -c 'rm -rf ~/x'`.
            text = " ".join(run[i + 1:])
            named = [w for w in self.deletes if re.search(r"\b" + re.escape(w) + r"\b", text)]
            if named:
                return (f"a `{word} -c` string deletes ({named[0]}), so the target is only "
                        f"known at run time")
        return None

    def deletes_outside_safe(self, cmd: str, cwd: str) -> str | None:
        """Why this command destroys something outside the safe list, or None.

        A DELETE is not a write: `mkdir` and `rm` share a word list in the old
        vocabulary and their consequences do not. Operands are resolved against
        the command's cwd, so `rm dotfiles` in $HOME is named in full; an
        unparseable command that mentions a delete fails closed.
        """
        if not self.deletes:
            return "the vocabulary names no delete commands"
        stripped = HEREDOC.sub("<<STRIPPED", cmd)
        try:
            lex = shlex.shlex(_uncomment(stripped), posix=True, punctuation_chars=True)
            lex.whitespace_split = True          # `;` and `&&` become tokens of their own
            tokens = list(lex)
        except ValueError:
            words = [w for w in self.deletes if re.search(r"\b" + re.escape(w) + r"\b", stripped)]
            return f"an unparseable command names `{words[0]}`" if words else None
        run: list = []
        for tok in tokens:
            if tok in (";", "&&", "||", "|", "&", ";;"):
                why = self._delete_run(run, cwd)
                if why:
                    return why
                run = []
            else:
                run.append(tok)
        return self._delete_run(run, cwd)

    def command_writes(self, cmd: str) -> bool:
        """Does this command mutate a path at all? Consulted only after the
        command is known to reference a path the rule covers."""
        stripped = HEREDOC.sub("<<STRIPPED", cmd)
        try:
            tokens = shlex.split(_uncomment(stripped))
        except ValueError:                # unbalanced quotes — fail closed
            return True
        if any(os.path.basename(t) in self.writes for t in tokens):
            return True
        for word, flags in self.writes_with_flag.items():
            for flag in flags:
                if re.search(r"\b" + re.escape(word) + r"\b[^;&|]*"
                             + _flag_re(flag), stripped):
                    return True
        for pattern in (self.git_writes, self.git_push):
            if pattern is not None and pattern.search(stripped):
                return True
        return False

    def escapes(self, cmd: str, cwd: str, depth: int = 0):
        """Why this command starts a container that reaches the host, or None.

        Reads `shell.host_escape`. A window runs from an engine word to the next
        separator or engine word, and counts only if it holds a subcommand
        (`run`, `exec`, ...). A token that is itself a command line
        (`bash -c '...'`, `ssh host '...'`) is read again, three levels deep.
        """
        he = self.escape
        stripped = HEREDOC.sub("<<STRIPPED", cmd)
        try:
            raw = shlex.split(_uncomment(stripped))
        except ValueError:                # unbalanced quotes — fail closed
            if self.engine_word.search(stripped):
                return "an unparseable command names a container engine"
            return None
        tokens = []                       # None marks a separator
        for t in raw:
            if t in (";", "&&", "||", "|", "&"):
                tokens.append(None)
                continue
            s = t.rstrip(";&|")
            if s:
                tokens.append(s)
            if s != t:
                tokens.append(None)
        if depth < 3:
            for t in tokens:
                if t and any(c.isspace() for c in t) and self.engine_word.search(t):
                    why = self.escapes(t, cwd, depth + 1)
                    if why:
                        return why
        engines = set(he["engines"])
        starts = [i for i, t in enumerate(tokens) if t and os.path.basename(t) in engines]
        for i in starts:
            end = i + 1
            while end < len(tokens) and tokens[end] is not None \
                    and os.path.basename(tokens[end]) not in engines:
                end += 1
            window = tokens[i + 1:end]
            if not set(window) & set(he["subcommands"]):
                continue
            why = self._escape_window(window, cwd)
            if why:
                return why
        return None

    def _escape_window(self, window: list, cwd: str):
        he = self.escape

        def value(j: int, flag: str):
            """The value of `flag` at window[j] (`--f=v`, `--f v`, `-vX`), or None."""
            t = window[j]
            if t == flag:
                return window[j + 1] if j + 1 < len(window) else None
            if t.startswith(flag + "="):
                return t[len(flag) + 1:]
            if not flag.startswith("--") and t.startswith(flag) and len(t) > len(flag):
                return t[len(flag):]
            return None

        def norm(v: str) -> str:
            v = v.upper().replace(":", "=")
            return v[4:] if v.startswith("CAP_") else v

        for j, t in enumerate(window):
            for flag in he["flags"]:
                if t == flag or t.startswith(flag + "="):
                    return f"the container is started with `{flag}`"
            for flag, allowed in he["flag_values"].items():
                v = value(j, flag)
                if v is not None and norm(v) in {norm(a) for a in allowed}:
                    return f"the container is started with `{flag} {v}`"
            for flag in he["mount_flags"]:
                v = value(j, flag)
                if v is None:
                    continue
                src = _mount_source(v, flag == "--mount")
                if src is None:
                    continue
                hit = self._host_path(src, cwd)
                if hit:
                    return f"the container binds `{src}` from the host, which {hit}"
        return None

    def _host_path(self, src: str, cwd: str):
        """Why a bind source exposes the host, or None."""
        p = _expand(src, cwd)
        for entry in self.escape["whole"]:
            e = _expand(entry, cwd)
            if p == e or p == "/" or e.startswith(p.rstrip("/") + "/"):
                return f"contains `{entry}`"
        for entry in self.escape["beneath"]:
            e = _expand(entry, cwd)
            if p == e or p.startswith(e.rstrip("/") + "/"):
                return f"lies in `{entry}`"
        return None


def _expand(token: str, cwd: str) -> str:
    home = os.path.expanduser("~")
    t = os.path.expanduser(token.replace("${HOME}", home).replace("$HOME", home))
    return os.path.normpath(os.path.join(cwd, t))


def _mount_source(v: str, is_mount: bool):
    """The host path a mount flag binds, or None (a named volume, a non-bind)."""
    if is_mount:
        kv = dict(p.split("=", 1) for p in v.split(",") if "=" in p)
        if kv.get("type") != "bind":
            return None
        return kv.get("source") or kv.get("src")
    src = v.split(":", 1)[0]
    return src if src[:1] in ("/", "~", "$", ".") else None


# Heredoc bodies are DATA written somewhere else, not paths being opened.
# Scanning them stops the knowledge base from documenting its own boundaries,
# which is a bug, not safety. The redirect target of `cat > ~/x <<EOF` sits
# outside the body and is still scanned.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1.*?^\t*\2$", re.S | re.M)

V4A_HEADER = re.compile(r"^\s*\*\*\*\s*(?:Update|Add|Delete|Move) File:\s*(.+?)\s*$", re.M)

# Set by main(): "claude" or "hermes". decide() answers in this dialect.
DIALECT = "claude"


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


# What decide() says when command_hits() returns "unparsed"; judge.mjs's
# UNPARSED is the twin.
UNPARSED = ("this command could not be parsed (an unbalanced quote or a trailing "
            "backslash), so the wards fail closed; no path was matched. Balance "
            "the quote and run it again")


def command_hits(cmd: str, rule: dict, cwd: str) -> "bool | str":
    """True if a shell command references any path this rule covers, "unparsed"
    if it cannot be split (truthy: still fail-closed, but decide() can say why
    instead of naming a path the command never touched)."""
    cmd = HEREDOC.sub("<<STRIPPED", cmd)
    try:
        tokens = shlex.split(_uncomment(cmd))
    except ValueError:                    # unbalanced quotes — fail closed
        return "unparsed"
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
# Any `>` counts, not only one after whitespace: `echo x>path` writes too, and
# the old `(?:^|[\s;&|(])` prefix let it through in every judge (parity corpus,
# 2026-10-20). Only an arrow (`->`, `=>`) is not a redirect.
REDIRECT = re.compile(r"(?<![-=])\d*>>?\s*(?!&)([^\s;&|<>()]+)")


def command_writes(cmd: str, rule: dict, cwd: str, vocab: "Vocab") -> bool:
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
    return vocab.command_writes(cmd)


# ── hermes ───────────────────────────────────────────────────────────────────

def from_hermes(tool: str, ti: dict, vocab: "Vocab") -> list:
    """`(claude_tool, claude_input)` pairs for one hermes call; [] if unmapped.

    A list because one V4A patch can touch several files, and each is judged.
    `search_files` with `target: files` matches file NAMES, so its `pattern` is
    a path glob there and is checked as `Glob`'s; with `target: content` it is
    a regex over contents and stays allowed, as `Grep`'s does.
    """
    if tool == "search_files" and ti.get("target") == "files":
        return [("Glob", {"pattern": ti.get("pattern"), "path": ti.get("path")})]
    mapped = vocab.hermes_tool(tool)
    if mapped is None:
        return []
    claude, fields = mapped
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
    if what == UNPARSED:
        # No path matched, so the rule's reason and "do not retry" would mislead.
        msg = msg[:1]
    elif decision == "ask":
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
    vocab = Vocab(cfg["vocabulary"])

    global DIALECT
    if payload.get("hook_event_name") == "pre_tool_call":
        DIALECT = "hermes"
        for claude_tool, claude_ti in from_hermes(tool, ti, vocab):
            judge(claude_tool, claude_ti, rules, cwd, vocab)
        sys.exit(0)
    judge(tool, ti, rules, cwd, vocab)
    sys.exit(0)


def judge(tool: str, ti: dict, rules: list, cwd: str, vocab: "Vocab") -> None:
    """Exit through decide() if this call crosses a rule; return if it does not."""
    if tool == "Bash":
        cmd = str(ti.get("command", ""))
        for rule in rules:
            if "escape" in rule["denies"]:
                if any(path_matches(p, cwd) for p in rule["paths"]):
                    why = vocab.escapes(cmd, cwd)
                    if why:
                        decide(rule, why)
                continue
            if "delete" in rule["denies"]:
                if any(path_matches(p, cwd) for p in rule["paths"]):
                    why = vocab.deletes_outside_safe(cmd, cwd)
                    if why:
                        decide(rule, why)
                continue
            if "push" in rule["denies"]:
                if vocab.git_push is not None and \
                        vocab.git_push.search(HEREDOC.sub("<<STRIPPED", cmd)) and \
                        any(path_matches(p, cwd) for p in rule["paths"]):
                    decide(rule, "this command pushes or rewrites git history")
                continue
            hit = command_hits(cmd, rule, cwd)
            if not hit:
                continue
            if hit == "unparsed":
                decide(rule, UNPARSED)
            if "read" in rule["denies"]:
                decide(rule, "this command reaches a path the rule covers")
            if "write" in rule["denies"] and command_writes(cmd, rule, cwd, vocab):
                decide(rule, "this command appears to write under a protected path")
        return

    fields, tool_ops = vocab.tool_paths("claude-code", tool)
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
