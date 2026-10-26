"""capture — the hook-facing half of the memory back-end. Loops A, B and D.

THIS MODULE RUNS ON THE USER'S LATENCY BUDGET. Every Claude Code SessionEnd and
PostToolUse pays for its import. Keep it import-light: `sys` and `os` only, no
`re`, no `json`, nothing from the rest of the package. `python3 -X importtime`
is the check, and `familiar checks selftest --hook-cost` runs it.

GOVERNING RULE (memory-mechanisms.md): hooks only ever append to logs. Never
edit frontmatter or a knowledge leaf here -- sessions run in parallel and a writing
hook races.

Payload extraction deliberately replicates the M1 bash implementation's
`sed -nE 's/.*"key"...'` semantics rather than parsing JSON: the leading greedy
`.*` selects the RIGHTMOST match on each line. Byte-identical output against
the fixtures are the gate (see `familiar checks selftest --signals`), so
the quirk is reproduced on purpose. Fixing it is a separate, deliberate change.
"""
import os
import sys

WS = " \t"


def _skip_ws(s, i):
    while i < len(s) and s[i] in WS:
        i += 1
    return i


def _quoted_value_at(line, i, escapes=False):
    """Parse `: "value"` starting at index i (just past a key). None if no match."""
    i = _skip_ws(line, i)
    if i >= len(line) or line[i] != ":":
        return None
    i = _skip_ws(line, i + 1)
    if i >= len(line) or line[i] != '"':
        return None
    i += 1
    out = []
    while i < len(line):
        c = line[i]
        if c == '"':
            return "".join(out)
        if escapes and c == "\\" and i + 1 < len(line):
            out.append(c)
            out.append(line[i + 1])
            i += 2
            continue
        if c == "\\" and not escapes:
            # `[^"]+` in the bash class does match a backslash.
            out.append(c)
            i += 1
            continue
        out.append(c)
        i += 1
    return None


def extract(payload, key, escapes=False):
    """Rightmost `"key": "value"` per line, lines joined -- sed's semantics."""
    found = []
    needle = '"%s"' % key
    for line in payload.split("\n"):
        hit, start = None, 0
        while True:
            j = line.find(needle, start)
            if j < 0:
                break
            v = _quoted_value_at(line, j + len(needle), escapes)
            if v is not None:
                hit = v
            start = j + 1
        if hit is not None:
            found.append(hit)
    return "\n".join(found)


def extract_caller(payload):
    """`"caller" [^}]* "type": "v"` -- rightmost per line, as the bash regex."""
    found = []
    for line in payload.split("\n"):
        hit, start = None, 0
        while True:
            j = line.find('"caller"', start)
            if j < 0:
                break
            seg_end = line.find("}", j)
            # `[^}]*` cannot cross a `}`; the `"type"` must precede the first one.
            limit = len(line) if seg_end < 0 else seg_end
            k, tstart = None, j + len('"caller"')
            while True:
                t = line.find('"type"', tstart)
                if t < 0 or t > limit:
                    break
                v = _quoted_value_at(line, t + len('"type"'))
                if v is not None:
                    k = v
                tstart = t + 1
            if k is not None:
                hit = k
            start = j + 1
        if hit is not None:
            found.append(hit)
    return "\n".join(found)


# -- resolution-signal inference -------------------------------------------
# Which of the four signals in skill-routing.md Sec.Resolution order selected
# this skill, so M2 can promote browse-resolved selections into `triggers:`.
# Ported verbatim from M1; the honest limit stated there stands: this is an
# INFERENCE from what the hook can observe, not a record of the agent's
# reasoning. Deterministic and auditable, but it can be wrong.
STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "into", "when", "then",
    "have", "will", "your", "are", "not", "but", "all", "any", "can", "use",
    "using", "used", "its", "it", "a", "an", "of", "to", "in", "on", "at", "by",
    "or", "be", "is", "was", "as", "so", "if", "do", "does", "done",
}


def _flow_list(raw):
    """Split `a, b, "c, d"` honouring quotes -- same rule as frontmatter.py."""
    items, cur, quote = [], "", ""
    for ch in raw:
        if quote:
            if ch == quote:
                quote = ""
            else:
                cur += ch
        elif ch in "\"'":
            quote = ch
        elif ch == ",":
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    return [i.strip() for i in items if i.strip()]


def _skill_path(agents_dir, skill):
    """The `SKILL.md` of `skill`, under `skills/<branch>/<subject>/<name>/`.

    THREE levels since O6b, not two: the branch and the subject are both in the
    path (SPECS.md O6b), so the old two-level walk found nothing after the move
    and every invocation classified as `external`. `os.listdir` rather than
    `glob` -- this module is import-light on purpose (see the docstring).
    """
    base = os.path.join(agents_dir, "skills")
    if not os.path.isdir(base):
        return None
    for branch in sorted(os.listdir(base)):
        bp = os.path.join(base, branch)
        if not os.path.isdir(bp):
            continue
        for subject in sorted(os.listdir(bp)):
            cand = os.path.join(bp, subject, skill, "SKILL.md")
            if os.path.isfile(cand):
                return cand
    return None


def classify_signal(agents_dir, skill, args, cwd, caller):
    path = _skill_path(agents_dir, skill)
    if not path:
        return "external"                       # not ours; our routers did not pick it
    if caller and caller != "direct":
        return "explicit"                       # signal 1
    if args:
        lower = args.lower()
        try:
            with open(path, "r") as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("triggers:") and "[" in s and s.endswith("]"):
                        inner = s[s.index("[") + 1:-1]
                        for t in _flow_list(inner):
                            if t.lower() in lower:
                                return "trigger"     # signal 3
                        break
        except OSError:
            pass
    # Signal 2 names a BRANCH in `_scope-bindings.md` (Q4, O6b); the subject is
    # accepted too, because the binding file is the human's and a finer prior is
    # a legitimate thing to write there.
    up = os.path.dirname
    subject = os.path.basename(up(up(path)))
    branch = os.path.basename(up(up(up(path))))
    if cwd:
        bindings = os.path.join(agents_dir, "skills", "_scope-bindings.md")
        try:
            with open(bindings, "r") as fh:
                for line in fh:
                    s = line.strip().rstrip(",").strip()
                    if not (s.startswith('"') and s.endswith('"') and "::" in s):
                        continue
                    glob, _, rhs = s[1:-1].partition("::")
                    glob = "".join(c for c in glob if c.isalnum() or c in "_/.-")
                    glob = glob.rstrip("*").rstrip("/")
                    if glob and glob in cwd and (branch in rhs or subject in rhs):
                        return "scope"               # signal 2
        except OSError:
            pass
    return "browse"                             # signal 4 -- trigger candidate


def extract_terms(args):
    """Candidate trigger vocabulary, as a JSON array literal.

    Bounded (12 terms, >=4 chars, stopworded) so the log cannot become a second
    transcript. Without it `signal:browse` says promotion is due but not what
    to promote.
    """
    out, seen = [], set()
    tok = ""
    for ch in args.lower() + " ":
        if ch.isalnum() and ch.isascii():
            tok += ch
            continue
        if tok:
            if tok not in STOPWORDS and len(tok) >= 4 and tok not in seen:
                seen.add(tok)
                out.append(tok)
            tok = ""
        if len(out) >= 12:
            break
    return "[" + ",".join('"%s"' % t for t in out[:12]) + "]"


# -- entry point ------------------------------------------------------------
def _utc(fmt):
    import time
    return time.strftime(fmt, time.gmtime())


def _json_str(s):
    """Minimal JSON string escaping, by hand -- no `json` import on the
    capture path (module docstring). Values interpolated into skill-usage.jsonl
    (cwd, skill name, ...) are not guaranteed free of `"`, `\\` or control
    characters; without escaping, one such byte produces an invalid JSON line
    or silently splits it in two, since every downstream reader parses the
    file one `\\n`-terminated line at a time."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out)


# `capture`'s flags, declared like every other route's (dev/architecture 3a):
# an undeclared flag is an error, and that rule is `invocation`'s, not a second
# hand-written loop here. The import is local to `main` and costs ~2.7 ms on top
# of `lib.roots`, which the hook path pays anyway (measured 2026-10-20).
CAPTURE = None          # filled by `_spec()` on first use: `invocation` is not
                        # imported at module load, so this file stays inspectable


def _spec():
    global CAPTURE
    if CAPTURE is None:
        from lib import invocation
        CAPTURE = invocation.Spec(
            name="capture", usage="capture --harness=H --event=E",
            options=("--harness", "--event"))
    return CAPTURE


def main(argv, base_dir, agents_dir):
    from lib import invocation
    try:
        inv = invocation.parse(list(argv), _spec(), base_dir, agents_dir)
    except invocation.UsageError as exc:
        sys.stderr.write("[familiar] %s\n" % exc)
        return 1
    harness = inv.get("--harness")
    event = inv.get("--event")
    if not harness:
        sys.stderr.write("[familiar] capture requires --harness\n")
        return 1
    if not event:
        sys.stderr.write("[familiar] capture requires --event\n")
        return 1

    transcripts = os.path.join(base_dir, "transcripts")
    os.makedirs(transcripts, exist_ok=True)
    try:
        payload = sys.stdin.read()
    except Exception:
        payload = ""

    if event in ("session-end", "SessionEnd"):
        sid = extract(payload, "session_id") or "unknown"
        tpath = extract(payload, "transcript_path")
        cwd = extract(payload, "cwd")
        log = os.path.join(base_dir, "session.log")
        if tpath and os.path.isfile(tpath):
            dest = os.path.join(
                transcripts, "%s_%s_%s.jsonl" % (_utc("%Y%m%dT%H%M%SZ"), harness, sid))
            try:
                with open(tpath, "rb") as src, open(dest, "wb") as dst:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        dst.write(chunk)
            except OSError:
                sys.stderr.write(
                    "[familiar] transcript copy failed: %s -> %s\n" % (tpath, dest))
                return 2
            with open(log, "a") as fh:
                fh.write("%s\t%s\t%s\t%s\t%s\n"
                         % (_utc("%Y-%m-%dT%H:%M:%SZ"), harness, sid, cwd, dest))
            sys.stderr.write("[familiar] captured transcript: %s\n" % dest)
        else:
            with open(log, "a") as fh:
                fh.write("%s\t%s\t%s\t%s\t(no transcript path in payload)\n"
                         % (_utc("%Y-%m-%dT%H:%M:%SZ"), harness, sid, cwd))
            sys.stderr.write(
                "[familiar] no transcript_path in payload; logged session only\n")
        return 0

    if event in ("post-tool-use", "PostToolUse", "skill-use", "skill-invoke"):
        sid = extract(payload, "session_id") or "unknown"
        tname = extract(payload, "tool_name")
        skill = extract(payload, "skill") or tname
        cwd = extract(payload, "cwd")
        args = extract(payload, "args", escapes=True)
        caller = extract_caller(payload)
        signal = classify_signal(agents_dir, skill, args, cwd, caller) if skill else "unknown"
        line = ('{"ts":"%s","harness":"%s","skill":"%s","session":"%s","cwd":"%s",'
                '"signal":"%s","caller":"%s","terms":%s}\n'
                % (_utc("%Y-%m-%dT%H:%M:%SZ"), _json_str(harness), _json_str(skill),
                   _json_str(sid), _json_str(cwd), _json_str(signal),
                   _json_str(caller or "unknown"), extract_terms(args)))
        with open(os.path.join(base_dir, "skill-usage.jsonl"), "a") as fh:
            fh.write(line)
        return 0

    sys.stderr.write("[familiar] unknown capture event: %s\n" % event)
    return 2
