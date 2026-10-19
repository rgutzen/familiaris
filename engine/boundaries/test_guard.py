#!/usr/bin/env python3
"""Regression suite for guard.py — one case per mode, plus the models axis.

Run: python3 -m pytest engine/boundaries/test_guard.py -q
   (or directly: python3 engine/boundaries/test_guard.py)

Supersedes test-zettel-guard.py, whose D1 cases are all carried over verbatim
in intent so a regression in the generalisation is visible.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "guard.py")
HOME = os.path.expanduser("~")
CWD = os.path.join(HOME, "06_SYSTEM")

# Assembled, so this file's own text is unambiguous when grepped.
VAULT = HOME + "/" + "03_" + "ZETTEL"
# R1m/R3c: the directive paths, whose rules are DERIVED from the entity
# register rather than written in a `*.yaml`.
PRACTICE = HOME + "/06_SYSTEM/config/practice"
DIRECTIVE_CONVENTIONS = PRACTICE + "/conventions"
DIRECTIVE_USER = PRACTICE + "/user"
DIRECTIVE_BOUNDARIES = HOME + "/06_SYSTEM/config/boundaries"
LEAF = HOME + "/06_SYSTEM/memory/knowledge/INDEX.md"
PII = HOME + "/04_RESOURCES/Personal-Documents"
SSH = HOME + "/.ssh"
RESTIC = HOME + "/.local/share/restic"


def fake_transcript(model: str) -> str:
    """A transcript whose last assistant record names `model`.

    This is how the guard resolves the live model class — see
    wards.model_class().
    """
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    fh.write(json.dumps({"type": "assistant", "message": {"model": model}}) + "\n")
    fh.close()
    return fh.name


LOCAL_T = fake_transcript("ollama/qwen3:4b-instruct")
REMOTE_T = fake_transcript("claude-opus-5")


def call(payload) -> str:
    """Return the guard's verdict: "allow", "deny" or "ask".

    The distinction matters: before `decision:` existed, any non-empty output
    meant refusal. A regression that softened a no-read-write rule to `ask`
    would have passed a boolean check silently.
    """
    r = subprocess.run([GUARD], input=json.dumps(payload),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"guard crashed: {r.stderr}")
    out = r.stdout.strip()
    if not out:
        return "allow"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def P(tool, ti, model="remote", cwd=CWD):
    return {"tool_name": tool, "tool_input": ti, "cwd": cwd,
            "transcript_path": LOCAL_T if model == "local" else REMOTE_T}


def bash(cmd, model="remote", cwd=CWD):
    return P("Bash", {"command": cmd}, model, cwd)


ALLOW, DENY, ASK = "allow", "deny", "ask"

CASES = [
    # ── mode: no-read-write (~/03_ZETTEL, all models) ────────────────────────
    ("D1 Read",                 P("Read",  {"file_path": VAULT + "/n.md"}), DENY),
    ("D1 Write",                P("Write", {"file_path": VAULT + "/x.md"}), DENY),
    ("D1 Edit",                 P("Edit",  {"file_path": VAULT + "/A.1.md"}), DENY),
    ("D1 Glob",                 P("Glob",  {"pattern": VAULT + "/**/*.md"}), DENY),
    ("D1 Grep path",            P("Grep",  {"pattern": "wave", "path": VAULT}), DENY),
    ("D1 local model too",      P("Read",  {"file_path": VAULT + "/n.md"}, "local"), DENY),
    ("D1 bash tilde",           bash("ls ~/03_" + "ZETTEL"), DENY),
    ("D1 bash absolute",        bash("cat " + VAULT + "/Working-Memory.md"), DENY),
    ("D1 bash bare token",      bash("ls 03_" + "ZETTEL"), DENY),
    ("D1 bash in $( )",         bash("echo $(wc -l " + VAULT + "/x.md)"), DENY),
    ("D1 bash $HOME",           bash("ls $HOME/03_" + "ZETTEL"), DENY),
    ("D1 heredoc REDIRECT",     bash("cat > " + VAULT + "/x.md <<'EOF'\nhi\nEOF"), DENY),
    ("D1 unbalanced quotes",    bash("cat '" + VAULT + "/x.md"), DENY),
    ("D1 heredoc BODY only",    bash("cat > /tmp/a <<'R'\n| `03_" + "ZETTEL/**` | none |\nR"), ALLOW),
    ("D1 Grep for literal",     P("Grep", {"pattern": "03_" + "ZETTEL", "path": CWD}), ALLOW),

    # ── mode: no-read, models: remote (~/04_RESOURCES/Personal-Documents) ────
    ("PII read, remote",        P("Read", {"file_path": PII + "/notes/x"}, "remote"), DENY),
    ("PII read, LOCAL",         P("Read", {"file_path": PII + "/notes/x"}, "local"), ALLOW),
    ("PII bash cat, remote",    bash("cat " + PII + "/README.md"), DENY),
    ("PII bash cat, LOCAL",     bash("cat " + PII + "/README.md", "local"), ALLOW),
    ("PII WRITE is allowed",    P("Write", {"file_path": PII + "/new.md"}, "remote"), ALLOW),

    # ── mode: no-read, models: remote (credentials) ──────────────────────────
    ("ssh key read, remote",    P("Read", {"file_path": SSH + "/id_ed25519"}, "remote"), DENY),
    ("ssh key read, LOCAL",     P("Read", {"file_path": SSH + "/id_ed25519"}, "local"), ALLOW),
    ("hermes env, remote",      bash("cat ~/.hermes/.env"), DENY),
    ("opencode auth, remote",   P("Read", {"file_path": HOME + "/.local/share/opencode/auth.json"}), DENY),

    # ── mode: no-write (~/.local/share/restic) ───────────────────────────────
    ("restic READ is allowed",  P("Read", {"file_path": RESTIC + "/pazras-home/config"}), ALLOW),
    ("restic check allowed",    bash("restic -r " + RESTIC + "/pazras-home check"), ALLOW),
    ("restic snapshots ok",     bash("restic -r " + RESTIC + "/pazras-home snapshots | head"), ALLOW),
    ("restic rm denied",        bash("rm -rf " + RESTIC + "/pazras-home"), DENY),
    ("restic redirect denied",  bash("echo x > " + RESTIC + "/pazras-home/config"), DENY),
    ("restic Write denied",     P("Write", {"file_path": RESTIC + "/pazras-home/config"}), DENY),
    ("restic mv denied",        bash("mv " + RESTIC + "/a " + RESTIC + "/b"), DENY),
    # 2>&1 is fd duplication, not a write. This was a live false positive.
    ("restic 2>&1 pipe ok",     bash("restic -r " + RESTIC + "/p snapshots --json 2>&1 | head -c 120"), ALLOW),
    ("restic out to /tmp ok",   bash("restic -r " + RESTIC + "/p snapshots > /tmp/out"), ALLOW),
    ("restic >> into repo",     bash("echo x >> " + RESTIC + "/p/config"), DENY),

    # ── mode: no-push (~) ────────────────────────────────────────────────────
    ("git push asks",         bash("git push origin main"), ASK),
    ("git push -u asks",      bash("git push -u origin HEAD"), ASK),
    ("git rebase asks",       bash("git rebase -i main"), ASK),
    ("git amend asks",        bash("git commit --amend -m x"), ASK),
    ("git filter-repo asks",  bash("git filter-repo --path x"), ASK),
    ("git commit allowed",      bash("git commit -m 'work'"), ALLOW),
    ("git branch allowed",      bash("git branch feat/x && git status"), ALLOW),
    ("git log allowed",         bash("git log --oneline -5"), ALLOW),
    ("push in heredoc ok",      bash("cat > /tmp/d <<'M'\nrun git push origin main\nM"), ALLOW),

    # ── directives: `ask`, derived from config/knowledge/entities.yaml (R1m) ──
    # The rules are not in any `*.yaml`; they are compiled from the entity kinds
    # marked `directive: true`. This suite is the check that the derivation
    # reaches the guard at all -- a register edit that stopped compiling would
    # leave these paths silently open, which is the failure `decision: ask`
    # exists to make visible.
    ("directive user edit",     P("Edit",  {"file_path": DIRECTIVE_USER + "/user-identity.md"}), ASK),
    ("directive user write",    P("Write", {"file_path": DIRECTIVE_USER + "/user-voice.md"}), ASK),
    ("directive conventions",   P("Edit",  {"file_path": DIRECTIVE_CONVENTIONS + "/voice.md"}), ASK),
    ("directive boundaries",    P("Write", {"file_path": DIRECTIVE_BOUNDARIES + "/read-write.yaml"}), ASK),
    ("directive bash redirect", bash("echo x > " + DIRECTIVE_CONVENTIONS + "/voice.md"), ASK),
    # Reading one is required: they are the always-loaded set. `no-write`, never
    # `no-read-write`, and this case is what keeps that true.
    ("directive READ allowed",  P("Read",  {"file_path": DIRECTIVE_USER + "/user-identity.md"}), ALLOW),
    ("directive grep allowed",  bash("grep -n voice " + DIRECTIVE_CONVENTIONS + "/voice.md"), ALLOW),

    # ── unrelated traffic must pass ──────────────────────────────────────────
    ("leaf read allowed",       P("Read", {"file_path": LEAF}), ALLOW),
    ("leaf write allowed",      P("Write", {"file_path": HOME + "/06_SYSTEM/memory/knowledge/areas/x.md"}), ALLOW),
    ("leaf bash write allowed", bash("echo x > " + CWD + "/memory/knowledge/system/knowledge/a.md"), ALLOW),
    ("bash unrelated",          bash("git status"), ALLOW),
    ("bash near-miss dir",      bash("ls ~/04_RESOURCES"), ALLOW),
    ("MCP-shaped tool passes",  P("mcp__x__y", {"file_path": VAULT + "/n.md"}), ALLOW),
]

# ── hermes dialect (`pre_tool_call` shell hook) ──────────────────────────────
# hermes blocks on exit 2 or a top-level `{"decision": "block"}`, and has no
# confirm, so `ask` must come back as a block. Both halves are asserted: a
# verdict hermes cannot parse is an allow.

def call_hermes(payload) -> str:
    r = subprocess.run([GUARD], input=json.dumps(payload),
                       capture_output=True, text=True)
    out = r.stdout.strip()
    if r.returncode == 0 and not out:
        return "allow"
    if r.returncode == 2 and json.loads(out).get("decision") == "block":
        return "block"
    raise SystemExit(f"guard answered hermes unparseably: rc={r.returncode} "
                     f"out={out!r} err={r.stderr}")


def H(tool, ti, cwd=CWD):
    return {"hook_event_name": "pre_tool_call", "tool_name": tool,
            "tool_input": ti, "session_id": "s", "cwd": cwd, "extra": {}}


BLOCK = "block"
V4A = ("*** Begin Patch\n*** Update File: " + VAULT + "/n.md\n@@\n-a\n+b\n"
       "*** End Patch")

HERMES_CASES = [
    ("H read_file vault",       H("read_file",  {"path": VAULT + "/n.md"}), BLOCK),
    ("H write_file vault",      H("write_file", {"path": VAULT + "/x.md", "content": "x"}), BLOCK),
    ("H patch replace vault",   H("patch", {"mode": "replace", "path": VAULT + "/n.md",
                                            "old_string": "a", "new_string": "b"}), BLOCK),
    ("H patch V4A vault",       H("patch", {"mode": "patch", "patch": V4A}), BLOCK),
    ("H search path vault",     H("search_files", {"pattern": "wave", "path": VAULT}), BLOCK),
    ("H search files glob",     H("search_files", {"pattern": VAULT + "/**/*.md",
                                                   "target": "files"}), BLOCK),
    ("H terminal vault",        H("terminal", {"command": "cat " + VAULT + "/n.md"}), BLOCK),
    ("H execute_code vault",    H("execute_code", {"code": "open('" + VAULT + "/n.md').read()"}), BLOCK),
    ("H PII read (remote)",     H("read_file",  {"path": PII + "/notes/x"}), BLOCK),
    ("H directive ask->block",  H("write_file", {"path": DIRECTIVE_USER + "/user-voice.md",
                                                 "content": "x"}), BLOCK),
    ("H directive read",        H("read_file",  {"path": DIRECTIVE_USER + "/user-identity.md"}), ALLOW),
    ("H leaf read",             H("read_file",  {"path": LEAF}), ALLOW),
    ("H search literal",        H("search_files", {"pattern": "03_" + "ZETTEL", "path": CWD}), ALLOW),
    ("H terminal unrelated",    H("terminal", {"command": "git status"}), ALLOW),
    ("H unmapped tool",         H("web_search", {"query": VAULT}), ALLOW),
]

# ── the derivation, register -> compiled rules (R1m) ─────────────────────────
# The cases above prove the guard ACTS on the derived rules. This proves the
# rules are the REGISTER's: one per kind marked `directive: true`, no more and
# no fewer. A `directive: true` that compiled to nothing would leave a path the
# register calls the user's own silently open, and nothing else would notice.

fail = 0


def derivation_checks():
    import _boundaries as B
    from lib import _miniyaml

    reg = _miniyaml.load(B.ENTITY_REGISTER.read_text())["entities"]
    want = {e["id"] for e in reg if str(e.get("directive")) == "true"}
    got = {r["derived_from"].split(":")[1] for r in B.directive_rules()}
    out = []
    out.append(("register kinds == derived rules", want == got,
                f"register {sorted(want)} vs rules {sorted(got)}"))
    out.append(("every derived rule asks",
                all(r["decision"] == "ask" and r["mode"] == "no-write"
                    and r["models"] == "all" for r in B.directive_rules()),
                "an ask rule must be ask+no-write+all, or a harness refuses it"))
    # `no-write`, never `no-read-write`: these files ARE the always-loaded set,
    # and a rule that denied reading them would be unsatisfiable.
    out.append(("derived rules deny writes only",
                all(r["denies"] == ["write"] for r in B.directive_rules()),
                "a directive file an agent cannot READ is a prompt it cannot obey"))
    json_rules = json.loads(B.JSON_TARGET.read_text())["rules"]
    out.append(("the compiled file is current",
                B.load() == json.loads(B.JSON_TARGET.read_text()),
                "run engine/boundaries/compile.py"))
    out.append(("the compiled file carries them",
                len([r for r in json_rules if r.get("domain") == B.DIRECTIVE_DOMAIN])
                == len(B.directive_rules()),
                "the guard reads the JSON; a rule only in `load()` is not enforced"))
    return out


for label, ok, why in derivation_checks():
    fail += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {label:<32} {'' if ok else why}")

for label, payload, expect in CASES:
    got = call(payload)
    ok = got == expect
    fail += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {label:<26} "
          f"expect={expect:<5} got={got}")

for label, payload, expect in HERMES_CASES:
    got = call_hermes(payload)
    ok = got == expect
    fail += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {label:<26} "
          f"expect={expect:<5} got={got}")

for t in (LOCAL_T, REMOTE_T):
    os.unlink(t)

print()
print("FAILURES:", fail, f"/ {len(CASES) + len(HERMES_CASES) + 5} checks "
      f"({len(CASES)} guard cases, {len(HERMES_CASES)} hermes cases, 5 derivation checks)")
sys.exit(1 if fail else 0)
