/**
 * familiar-boundaries — the opencode half of BOUNDARIES.yaml.
 *
 * Reads the SAME compiled rule set as the Claude Code hook
 * (06_SYSTEM/config/boundaries/boundaries.json, emitted by
 * `boundaries-compile`). No rule is written twice; there is one config.
 *
 * Interception point, verified against @opencode-ai/plugin@1.18.18's Hooks
 * interface: `tool.execute.before(input, output)` fires before every tool
 * call. Throwing from it aborts the call — that is the deny channel.
 *
 * The models axis: `tool.execute.before` carries no model, so the model is
 * recorded per session from `chat.params`, which does. Sessions with no
 * recorded model are treated as `remote`, the guarded default.
 *
 * KNOWN WEAKER THAN THE CLAUDE CODE GUARD: the bash scan here has no shlex, so
 * it is a token split plus a substring backstop rather than a real
 * tokenisation. The tool-path checks are equivalent; the bash half is not.
 * See 06_SYSTEM/memory/knowledge/system/boundaries/boundaries.md.
 */
import fs from "node:fs";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";

const HOME = os.homedir();
// The roots this plugin needs, declared once each. It cannot import
// lib/roots.py, so test_roots.py holds these to it instead.
const ENGINE = path.join(HOME, "06_SYSTEM/engine"); // roots-twin: ENGINE
const MEMORY = path.join(HOME, "06_SYSTEM/memory"); // roots-twin: MEMORY
// A twin, not a join off ENGINE: R2e moved the compiled rules to config/ and
// this line kept the old path. A missing file means "nothing to enforce", so
// the guard failed OPEN, silently, from 2026-10-07 to 2026-10-11.
const RULES = path.join(HOME, "06_SYSTEM/config/boundaries/boundaries.json"); // roots-twin: BOUNDARIES_JSON
const CAPTURE_BIN = path.join(ENGINE, "familiar");
const HATCH = path.join(HOME, ".config/opencode/guard.disabled");

// opencode tool id -> which argument fields name a path, and what the tool does.
// `grep.pattern` is a content regex, not a path, and is deliberately absent.
const TOOLS = {
  read:  { fields: ["filePath", "path"],            ops: ["read"] },
  list:  { fields: ["path"],                        ops: ["read"] },
  glob:  { fields: ["pattern", "path"],             ops: ["read"] },
  grep:  { fields: ["path", "include"],             ops: ["read"] },
  write: { fields: ["filePath", "path"],            ops: ["write"] },
  edit:  { fields: ["filePath", "path"],            ops: ["read", "write"] },
  patch: { fields: ["filePath", "path"],            ops: ["read", "write"] },
};

const HEREDOC = /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1[\s\S]*?^\t*\2$/gm;
const MUTATORS = new Set(["rm", "rmdir", "mv", "cp", "dd", "truncate", "shred",
  "tee", "chmod", "chown", "chgrp", "ln", "mkdir", "touch", "install",
  "unlink", "rsync", "mkfs", "sponge"]);
const GIT_WRITE = /\bgit\b[^;&|]*\b(push|filter-branch|filter-repo|rebase)\b|\bgit\b[^;&|]*\bcommit\b[^;&|]*--amend/;
const REDIRECT = /(?:^|[\s;&|(])\d*>>?\s*(?!&)([^\s;&|<>()]+)/g;

let cache = { mtime: 0, cfg: null };

function config() {
  try {
    const m = fs.statSync(RULES).mtimeMs;
    if (m !== cache.mtime) cache = { mtime: m, cfg: JSON.parse(fs.readFileSync(RULES, "utf8")) };
    return cache.cfg;
  } catch {
    return null;              // no compiled rules -> nothing to enforce
  }
}

function expand(token, cwd) {
  let t = token.replaceAll("${HOME}", HOME).replaceAll("$HOME", HOME);
  if (t === "~") t = HOME;
  else if (t.startsWith("~/")) t = path.join(HOME, t.slice(2));
  if (path.isAbsolute(t)) return [path.normalize(t)];
  // A bare name is a valid relative path from either the cwd or $HOME.
  return [path.normalize(path.join(cwd, t)), path.normalize(path.join(HOME, t))];
}

function under(rulePath, target) {
  for (const key of ["abs", "real"]) {
    const base = rulePath[key];
    if (base && (target === base || target.startsWith(base.replace(/\/$/, "") + "/"))) return true;
  }
  return false;
}

function hitsPath(rule, value, cwd) {
  if (typeof value !== "string" || !value) return false;
  return expand(value, cwd).some((c) => rule.paths.some((p) => under(p, c)));
}

function tokens(cmd) {
  return cmd.match(/'[^']*'|"[^"]*"|\S+/g)?.map((t) => t.replace(/^['"]|['"]$/g, "")) ?? [];
}

function spellings(p) {
  const out = [p.abs];
  if (p.real) out.push(p.real);
  if (p.abs.startsWith(HOME + "/")) {
    const rel = p.abs.slice(HOME.length + 1);
    out.push("~/" + rel, "$HOME/" + rel);
  }
  return out;
}

function commandHits(cmd, rule, cwd) {
  const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
  for (const tok of tokens(stripped)) if (hitsPath(rule, tok, cwd)) return true;
  for (const p of rule.paths) {
    for (const form of spellings(p)) {
      const esc = form.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (new RegExp(esc + "($|[/\\s'\";)&|])").test(stripped)) return true;
    }
  }
  return false;
}

function commandWrites(cmd, rule, cwd) {
  const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
  REDIRECT.lastIndex = 0;
  let m;
  while ((m = REDIRECT.exec(stripped)) !== null) {
    if (hitsPath(rule, m[1].replace(/^['"]|['"]$/g, ""), cwd)) return true;
  }
  if (tokens(stripped).some((t) => MUTATORS.has(path.basename(t)))) return true;
  return /\bsed\b[^;&|]*\s-\S*i/.test(stripped);
}

// opencode's only channel is the throw, which aborts the call. There is no
// confirmation prompt, so a rule with `decision: ask` degrades to a refusal
// here and says so — silently letting it through would be the worse failure.
function refuse(rule, what) {
  const head =
    rule.decision === "ask"
      ? `Needs the user's approval — \`${rule.mode}\`: ${what}. opencode has no confirmation prompt, so this is refused here; ask the user, or run it in Claude Code where the prompt exists.`
      : `Blocked by wards — \`${rule.mode}\`: ${what}.`;
  const bits = [head, rule.reason];
  if (rule.instead) bits.push(`Instead: ${rule.instead}.`);
  if (rule.see) bits.push(`See ${rule.see}.`);
  bits.push(`This rule lives in ${path.relative(HOME, MEMORY)}/boundaries/*.yaml, which is the user's to change. Do not retry with a different spelling — ask.`);
  throw new Error(bits.join(" "));
}

// ── Capture (Loop A) ─────────────────────────────────────────────────────
// `session.idle` is opencode's nearest analogue to Claude Code's SessionEnd:
// it fires when the assistant finishes and the session goes quiet.
//
// TWO INDEPENDENT SPAWNS. The first appends one session-log line unconditionally,
// which is enough to (a) record that work happened here and (b) make the day
// count as ACTIVE in the ranking. The second stages a transcript: opencode
// keeps sessions in a SQLite database (`~/.local/share/opencode/opencode.db`),
// not a per-session JSONL the way Claude Code does, so there is no file to
// copy -- `familiar context opencode-session` queries that DB for this one
// session_id (indexed, so DB size does not matter) and converts it to the
// same line shape `transcripts.py` reads for Claude Code. Kept as a separate
// spawn, not folded into the first: it is heavier (a DB open + two queries)
// and strictly best-effort -- if it fails, the ACTIVE-day log line from the
// first spawn still lands.
//
// Loop B (use_count) is IMPOSSIBLE here and is not attempted: opencode has
// agents, not skills, so there is no skill-invocation event to hook.
const seenIdle = new Set();

function captureSessionIdle(sessionID, cwd) {
  if (!sessionID || seenIdle.has(sessionID)) return;   // idle can fire repeatedly
  seenIdle.add(sessionID);
  try {
    const payload = JSON.stringify({ session_id: sessionID, cwd, transcript_path: "" });
    // Detached and ignored: capture runs on the user's latency budget, and a
    // failure to log must never surface in, or block, their session.
    const child = spawn(CAPTURE_BIN,
      ["context", "capture", "--harness=opencode", "--event=session-end"],
      { stdio: ["pipe", "ignore", "ignore"], detached: true });
    child.on("error", () => {});
    child.stdin.on("error", () => {});
    child.stdin.end(payload);
    child.unref();
  } catch {
    // never let capture break a session
  }
  try {
    const extract = spawn(CAPTURE_BIN,
      ["context", "opencode-session", `--session=${sessionID}`],
      { stdio: ["ignore", "ignore", "ignore"], detached: true });
    extract.on("error", () => {});
    extract.unref();
  } catch {
    // best-effort; the session-log line above already covers ACTIVE-day accounting
  }
}

export const FamiliarBoundaries = async ({ directory, worktree }) => {
  const modelBySession = new Map();
  const cwd = worktree || directory || process.cwd();

  return {
    event: async ({ event }) => {
      if (event?.type === "session.idle") {
        captureSessionIdle(event?.properties?.sessionID ?? event?.sessionID, cwd);
      }
    },

    // The only hook that carries the model. Recorded here, used below.
    "chat.params": async (input) => {
      const provider = input?.provider?.info?.id ?? input?.model?.providerID ?? "";
      modelBySession.set(input.sessionID, String(provider).toLowerCase());
    },

    "tool.execute.before": async (input, output) => {
      if (fs.existsSync(HATCH)) return;
      const cfg = config();
      if (!cfg) return;

      const provider = modelBySession.get(input.sessionID) ?? "";
      const local = (cfg.local_providers ?? []).some((p) => provider.includes(String(p).toLowerCase()));
      const klass = local ? "local" : "remote";
      const rules = cfg.rules.filter((r) => r.models === "all" || r.models === klass);

      const tool = String(input.tool || "").toLowerCase();
      const args = output?.args ?? {};

      if (tool === "bash") {
        const cmd = String(args.command ?? "");
        for (const rule of rules) {
          if (rule.denies.includes("push")) {
            if (GIT_WRITE.test(cmd.replace(HEREDOC, "<<STRIPPED")) &&
                rule.paths.some((p) => under(p, path.normalize(cwd)))) {
              refuse(rule, "this command pushes or rewrites git history");
            }
            continue;
          }
          if (!commandHits(cmd, rule, cwd)) continue;
          if (rule.denies.includes("read")) refuse(rule, "this command reaches a path the rule covers");
          if (rule.denies.includes("write") && commandWrites(cmd, rule, cwd)) {
            refuse(rule, "this command appears to write under a protected path");
          }
        }
        return;
      }

      const spec = TOOLS[tool];
      if (!spec) return;
      for (const rule of rules) {
        const overlap = spec.ops.filter((o) => rule.denies.includes(o));
        if (!overlap.length) continue;
        for (const field of spec.fields) {
          if (hitsPath(rule, args[field], cwd)) {
            refuse(rule, `${tool}.${field} would ${overlap.join("/")} \`${args[field]}\``);
          }
        }
      }
    },
  };
};

export const server = FamiliarBoundaries;
export default FamiliarBoundaries;
