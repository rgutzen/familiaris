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
 * plugin (06_SYSTEM/config/boundaries/boundaries.json) and runs the SAME judge
 * as the opencode plugin (`../shared/judge.mjs`). No rule, no mutating command
 * and no push verb is written twice; the two evaluators are held equal by the
 * parity corpus. It enforces ONLY the rules whose `models` is `local` or
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
 * NO LONGER WEAKER: the shared judge tokenises a command line as POSIX does,
 * so the bash scan matches guard.py's `shlex.split`, and an unbalanced quote
 * fails closed, as it does there.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Judge, UNPARSED } from "../shared/judge.mjs";

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
// The compiled rules of the tree THIS FILE lives in, not of the install: the
// extension handed a copy of the engine must enforce that copy's config, and a
// worktree's suites were silently testing the main checkout's. Derived from the
// module's own path, so it cannot drift the way a twin does -- R2e moved these
// rules once and a hard-coded path failed OPEN, silently, for four days.
const RULES_TREE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const RULES = path.join(RULES_TREE, "config/boundaries/boundaries.json"); // not-a-root: RULES_TREE is the tree root; "config/" here is the segment under it, not a root spelled by this file

const HATCH = path.join(HOME, ".pi", "agent", "guard.disabled");

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

function reason(rule: Rule, what: string): string {
  // An unsplittable command matched no path, so the rule's reason and the
  // "do not retry" line would mislead: the fix is to balance a quote.
  if (what === UNPARSED) return `\`${rule.mode}\`: ${what}.`;
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
    // gotgenes' bash surface cannot express "a delete, EXCEPT under these
    // paths": its patterns are globs and carry no exception. So the delete rule
    // stays this guard's job even when it is model-agnostic (item 8i).
    const rules = cfg.rules.filter((r) => r.models === klass || r.mode === "no-delete");
    if (!rules.length) return;

    const cwd = ctx.cwd || process.cwd();
    const tool = String(event.toolName ?? "").toLowerCase();
    const input = (event.input ?? {}) as Record<string, unknown>;

    const judge = new Judge(cfg);
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
        const hit = judge.commandHits(cmd, rule, cwd);
        if (!hit) continue;
        if (hit === "unparsed") return block(rule, UNPARSED);
        if (rule.denies.includes("delete")) {
          if (rule.paths.some((p) => judge.under(p, path.normalize(cwd)))) {
            const why = judge.deletesOutsideSafe(cmd, cwd);
            if (why) return block(rule, why);
          }
          continue;
        }
        if (rule.denies.includes("read")) return block(rule, "this command reaches a path the rule covers");
        if (rule.denies.includes("write") &&
            (judge.redirectTargets(cmd).some((v) => judge.hitsPath(rule, v, cwd)) ||
             judge.commandWrites(cmd))) {
          return block(rule, "this command appears to write under a protected path");
        }
      }
      return;
    }

    const spec = judge.toolPaths("pi", tool);
    if (!spec) return;
    for (const rule of rules) {
      const overlap = [...spec.ops].filter((o) => rule.denies.includes(o));
      if (!overlap.length) continue;
      for (const field of spec.fields) {
        if (judge.hitsPath(rule, input[field], cwd)) {
          return block(rule, `${tool}.${field} would ${overlap.join("/")} \`${input[field]}\``);
        }
      }
    }
  });
}
