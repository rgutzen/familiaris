/**
 * familiar-boundaries — the opencode half of BOUNDARIES.yaml.
 *
 * Reads the SAME compiled rule set as the Claude Code hook and pi-guard
 * (config/boundaries/boundaries.json, emitted by `boundaries-compile`), and runs
 * the SAME judge as pi-guard (`../shared/judge.mjs`). No rule, no mutating
 * command and no push verb is written twice: the rules and their vocabulary are
 * configuration, and two evaluators (Python and this shared one) are held equal
 * by the parity corpus in `../fixtures/parity.json`.
 *
 * Interception point, verified against @opencode-ai/plugin@1.18.18's Hooks
 * interface: `tool.execute.before(input, output)` fires before every tool
 * call. Throwing from it aborts the call — that is the deny channel.
 *
 * The models axis: `tool.execute.before` carries no model, so the model is
 * recorded per session from `chat.params`, which does. Sessions with no
 * recorded model are treated as `remote`, the guarded default.
 *
 * NO LONGER WEAKER: the shared judge tokenises a command line as POSIX does
 * (single and double quotes, backslash escapes, an unbalanced quote failing
 * closed), which is what `shlex.split` gives guard.py. The corpus found the old
 * gap -- `\rm` passed here and was caught in Python -- and holds it closed.
 * See 06_SYSTEM/memory/knowledge/system/boundaries/boundaries.md.
 */
import fs from "node:fs";
import { spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Judge, UNPARSED, configReader } from "../shared/judge.mjs";

const HOME = os.homedir();
// The roots this plugin needs, declared once each. It cannot import
// lib/roots.py, so test_roots.py holds these to it instead.
const ENGINE = path.join(HOME, "06_SYSTEM/engine"); // roots-twin: ENGINE
const MEMORY = path.join(HOME, "06_SYSTEM/memory"); // roots-twin: MEMORY
// The compiled rules of the tree THIS FILE lives in, not of the install: the
// plugin handed a copy of the engine must enforce that copy's config, and a
// worktree's suites were silently testing the main checkout's. Derived from the
// module's own path, so it cannot drift the way a twin does -- R2e moved these
// rules once and a hard-coded path failed OPEN, silently, for four days.
const RULES_TREE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const RULES = path.join(RULES_TREE, "config/boundaries/boundaries.json"); // not-a-root: RULES_TREE is the tree root; "config/" here is the segment under it, not a root spelled by this file

const CAPTURE_BIN = path.join(ENGINE, "familiar");
const HATCH = path.join(HOME, ".config/opencode/guard.disabled");

// The tool map is the VOCABULARY's now (`tools.opencode` in
// config/boundaries/vocabulary.yaml, compiled into boundaries.json), so a tool
// that gains a path field is a config edit. The compiled rules are re-read
// only when the file changes.
const config = configReader(RULES);

// The judge is SHARED with pi-guard (../shared/judge.mjs): one evaluator for
// both JS harnesses, held to guard.py by the parity corpus. What is left here
// is what only opencode needs: the throw channel, and the tool map's shape.
const judge = (cfg) => new Judge(cfg);

// opencode's only channel is the throw, which aborts the call. There is no
// confirmation prompt, so a rule with `decision: ask` degrades to a refusal
// here and says so — silently letting it through would be the worse failure.
function refuse(rule, what) {
  const head =
    rule.decision === "ask"
      ? `Needs the user's approval — \`${rule.mode}\`: ${what}. opencode has no confirmation prompt, so this is refused here; ask the user, or run it in Claude Code where the prompt exists.`
      : `Blocked by wards — \`${rule.mode}\`: ${what}.`;
  // An unsplittable command matched no path; the rule's reason would mislead.
  if (what === UNPARSED) throw new Error(head);
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

      const tool = String(input.tool || "").toLowerCase();
      const args = output?.args ?? {};

      const j = judge(cfg);
      if (tool === "bash") {
        const cmd = String(args.command ?? "");
        for (const rule of j.rulesFor(klass)) {
          if (rule.denies.includes("escape")) {
            if (rule.paths.some((p) => j.under(p, path.normalize(cwd)))) {
              const why = j.escapes(cmd, cwd);
              if (why) refuse(rule, why);
            }
            continue;
          }
          if (rule.denies.includes("push")) {
            if (j.pushes(cmd) && rule.paths.some((p) => j.under(p, path.normalize(cwd)))) {
              refuse(rule, "this command pushes or rewrites git history");
            }
            continue;
          }
          const hit = j.commandHits(cmd, rule, cwd);
          if (!hit) continue;
          if (hit === "unparsed") refuse(rule, UNPARSED);
          if (rule.denies.includes("delete")) {
            if (rule.paths.some((p) => j.under(p, path.normalize(cwd)))) {
              const why = j.deletesOutsideSafe(cmd, cwd);
              if (why) refuse(rule, why);
            }
            continue;
          }
          if (rule.denies.includes("read")) refuse(rule, "this command reaches a path the rule covers");
          if (rule.denies.includes("write") &&
              (j.redirectTargets(cmd).some((v) => j.hitsPath(rule, v, cwd)) || j.commandWrites(cmd))) {
            refuse(rule, "this command appears to write under a protected path");
          }
        }
        return;
      }

      const spec = j.toolPaths("opencode", tool);
      if (!spec) return;
      for (const rule of j.rulesFor(klass)) {
        const overlap = [...spec.ops].filter((o) => rule.denies.includes(o));
        if (!overlap.length) continue;
        for (const field of spec.fields) {
          if (j.hitsPath(rule, args[field], cwd)) {
            refuse(rule, `${tool}.${field} would ${overlap.join("/")} \`${args[field]}\``);
          }
        }
      }
    },
  };
};

export const server = FamiliarBoundaries;
export default FamiliarBoundaries;
