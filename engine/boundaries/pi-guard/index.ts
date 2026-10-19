/**
 * familiar-guard — the model-axis half of BOUNDARIES.yaml for Pi.
 *
 * gotgenes' pi-permission-system enforces the model-AGNOSTIC rules
 * (`models: all` — no-push, no-read-write, no-write) from a config.json
 * emitted by `boundaries-compile`. It has no model axis, and its
 * authorizerChain seam is consulted only on `ask` cases, so it cannot express
 * "deny a REMOTE read of ~/.ssh". That is the one real gap, and this is the
 * guard that fills it.
 *
 * It reads the SAME compiled rule set as the Claude Code hook and the opencode
 * plugin (06_SYSTEM/config/boundaries/boundaries.json). No rule is
 * written twice. It enforces ONLY the rules whose `models` is `local` or
 * `remote` — the model-agnostic ones are gotgenes' job, and re-enforcing them
 * here would double-prompt or contradict the gotgenes config.
 *
 * Interception point: Pi's `tool_call` hook fires before a tool executes and
 * can block via `{ block: true, reason }`. The active model comes from
 * `ctx.model`, whose shape is `{ provider, id }` — verified against Pi
 * 0.84.4's `model_select` event (`event.model.provider` / `.id`).
 *
 * Pi has a real confirmation prompt, so a `decision: ask` rule is honoured as
 * a prompt (ctx.ui.confirm), NOT degraded to a refusal the way opencode's
 * throw-only channel forces. A `deny` blocks outright.
 *
 * KNOWN WEAKER THAN THE CLAUDE CODE GUARD: the bash scan here is a token split
 * plus a substring backstop (no shlex), matching the opencode plugin's
 * acknowledged limit. The tool-path checks are equivalent.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// Deliberately no import of `@earendil-works/pi-coding-agent`: this file lives
// OUTSIDE Pi's module tree (version-controlled in 06_SYSTEM, reached through a
// loader shim), so a peer-dep import would have to resolve across trees. The
// runtime deps are node builtins only, exactly like the opencode plugin; the
// `pi`/`ctx` shapes are used loosely instead of typed.
type ExtensionAPI = any;

const HOME = os.homedir();
// The roots this extension needs, declared once each. It cannot import
// lib/roots.py, so test_roots.py holds these to it instead.
const ENGINE = path.join(HOME, "06_SYSTEM/engine"); // roots-twin: ENGINE
const MEMORY = path.join(HOME, "06_SYSTEM/memory"); // roots-twin: MEMORY
// A twin, not a join off ENGINE: R2e moved the compiled rules to config/ and
// this line kept the old path. A missing file means "nothing to enforce", so
// the guard failed OPEN, silently, from 2026-10-07 to 2026-10-11.
const RULES = path.join(HOME, "06_SYSTEM/config/boundaries/boundaries.json"); // roots-twin: BOUNDARIES_JSON
const HATCH = path.join(HOME, ".pi", "agent", "guard.disabled");

// Pi's path-bearing built-ins (the six gotgenes gates), each with `input.path`
// and its read/write effect. grep's `pattern` is a content regex, not a path,
// and is deliberately absent. This list matches PATH_BEARING_TOOLS in
// gotgenes/pi-packages — keep the two in agreement or the gates disagree.
const TOOLS: Record<string, { fields: string[]; ops: string[] }> = {
  read:  { fields: ["path"], ops: ["read"] },
  grep:  { fields: ["path"], ops: ["read"] },
  find:  { fields: ["path"], ops: ["read"] },
  ls:    { fields: ["path"], ops: ["read"] },
  write: { fields: ["path"], ops: ["write"] },
  edit:  { fields: ["path"], ops: ["read", "write"] },
};

const HEREDOC = /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1[\s\S]*?^\t*\2$/gm;
// Word-for-word the mutators from wards / the opencode plugin.
const MUTATORS = new Set(["rm", "rmdir", "mv", "cp", "dd", "truncate", "shred",
  "tee", "chmod", "chown", "chgrp", "ln", "mkdir", "touch", "install",
  "unlink", "rsync", "mkfs", "sponge"]);
const REDIRECT = /(?:^|[\s;&|(])\d*>>?\s*(?!&)([^\s;&|<>()]+)/g;

type Cfg = { local_providers: string[]; rules: Rule[] };
type Rule = {
  mode: string;
  models: string;
  decision: string;
  reason: string;
  instead?: string;
  see?: string;
  denies: string[];
  paths: { display: string; abs: string; real: string | null }[];
};

let cache = { mtime: 0, cfg: null as Cfg | null };

function config(): Cfg | null {
  try {
    const m = fs.statSync(RULES).mtimeMs;
    if (m !== cache.mtime) {
      cache = { mtime: m, cfg: JSON.parse(fs.readFileSync(RULES, "utf8")) };
    }
    return cache.cfg;
  } catch {
    return null;
  }
}

function expand(token: string, cwd: string): string[] {
  let t = token.replaceAll("${HOME}", HOME).replaceAll("$HOME", HOME);
  if (t === "~") t = HOME;
  else if (t.startsWith("~/")) t = path.join(HOME, t.slice(2));
  if (path.isAbsolute(t)) return [path.normalize(t)];
  return [path.normalize(path.join(cwd, t)), path.normalize(path.join(HOME, t))];
}

function under(rulePath: { abs: string; real: string | null }, target: string): boolean {
  const bases = [rulePath.abs, rulePath.real].filter(Boolean) as string[];
  return bases.some((b) =>
    target === b || target.startsWith(b.replace(/\/$/, "") + "/"));
}

function hitsPath(rule: Rule, value: unknown, cwd: string): boolean {
  if (typeof value !== "string" || !value) return false;
  return expand(value, cwd).some((c) =>
    rule.paths.some((p) => under(p, c)));
}

function tokens(cmd: string): string[] {
  return cmd.match(/'[^']*'|"[^"]*"|\S+/g)?.map((t) => t.replace(/^['"]|['"]$/g, "")) ?? [];
}

function spellings(p: { abs: string; real: string | null }): string[] {
  const out = [p.abs];
  if (p.real) out.push(p.real);
  if (p.abs.startsWith(HOME + "/")) {
    const rel = p.abs.slice(HOME.length + 1);
    out.push("~/" + rel, "$HOME/" + rel);
  }
  return out;
}

function commandHits(cmd: string, rule: Rule, cwd: string): boolean {
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

function commandWrites(cmd: string, rule: Rule, cwd: string): boolean {
  const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
  REDIRECT.lastIndex = 0;
  let m;
  while ((m = REDIRECT.exec(stripped)) !== null) {
    if (hitsPath(rule, m[1].replace(/^['"]|['"]$/g, ""), cwd)) return true;
  }
  if (tokens(stripped).some((t) => MUTATORS.has(path.basename(t)))) return true;
  return /\bsed\b[^;&|]*\s-\S*i/.test(stripped);
}

function reason(rule: Rule, what: string): string {
  const bits = [`\`${rule.mode}\`: ${what}.`, rule.reason];
  if (rule.instead) bits.push(`Instead: ${rule.instead}.`);
  if (rule.see) bits.push(`See ${rule.see}.`);
  bits.push(
    `This rule lives in ${path.relative(HOME, MEMORY)}/boundaries/*.yaml, which is the user's to change. Do not retry with a different spelling — ask.`,
  );
  return bits.join(" ");
}

export default function familiarGuard(pi: ExtensionAPI): void {
  pi.on("tool_call", async (event, ctx) => {
    if (fs.existsSync(HATCH)) return;
    const cfg = config();
    if (!cfg) return;

    // Classify local/remote from the active model's provider, matching
    // boundaries.json's `local_providers` list. Fails to `remote`:
    // more rules apply there, so an unknown model is guarded, not waved through.
    const provider = String(ctx.model?.provider ?? "").toLowerCase();
    const local = (cfg.local_providers ?? []).some((p) =>
      provider.includes(String(p).toLowerCase()));
    const klass = local ? "local" : "remote";
    const rules = cfg.rules.filter((r) => r.models === klass);
    if (!rules.length) return;

    const cwd = ctx.cwd || process.cwd();
    const tool = String(event.toolName ?? "").toLowerCase();
    const input = (event.input ?? {}) as Record<string, unknown>;

    const block = (rule: Rule, what: string) => {
      const msg = reason(rule, what);
      return rule.decision === "ask"
        ? ctx.ui.confirm("the wards", msg)
            .then((ok) => (ok ? undefined : { block: true, reason: msg }))
        : { block: true, reason: msg };
    };

    if (tool === "bash") {
      const cmd = String(input.command ?? "");
      for (const rule of rules) {
        if (!commandHits(cmd, rule, cwd)) continue;
        if (rule.denies.includes("read")) return block(rule, "this command reaches a path the rule covers");
        if (rule.denies.includes("write") && commandWrites(cmd, rule, cwd)) {
          return block(rule, "this command appears to write under a protected path");
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
        if (hitsPath(rule, input[field], cwd)) {
          return block(rule, `${tool}.${field} would ${overlap.join("/")} \`${input[field]}\``);
        }
      }
    }
  });
}
