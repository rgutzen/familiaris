/**
 * familiar-bindings — option T's tool resolver for Pi (item 6b).
 *
 * Each ACTIVE `tool:` binding in config/orchestration/bindings.yaml becomes one
 * tool, `bound_<name>`, whose call runs
 *   familiar orchestration bindings run tool:<name> <task>
 * i.e. a CHILD through pi-agent on the bound model. The parent's model never
 * changes (PLAN.md §Bindings, rule 1); the child's reply comes back with a
 * `binding:` line saying which model ran, how it was chosen, and whether the
 * reply kept its contract (exit 4 = it did not: do not trust the text).
 *
 * A bound `command:` or `skill:` (item 6c) becomes a slash command: `/<name>` for
 * a command, `/bound-<name>` for a skill (`/skill:<name>` is pi's own, and skills
 * are not installed in pi). Its handler runs the same `bindings run <on> <args>`
 * and puts the child's reply into the session as a message, without a turn: the
 * parent's model never changes. A command, not a tool, because a human names a
 * skill here, and a command costs the parent no schema tokens.
 *
 * OFF BY DEFAULT. A registered tool costs its schema in every parent session,
 * and option 0 has not yet shown T saves anything (decision 1). The tools load
 * only with PI_BINDINGS=1, which is how 4c's "pi + bindings" arm differs from
 * the baseline. A pi-agent child (PI_OFFLINE=1) never loads them, so a bound
 * child cannot bind again.
 *
 * The table is read once, at load, through `--tools-json`: the Python side owns
 * the schema and the roster, so nothing here re-implements either.
 */
import { execFileSync, spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

type ExtensionAPI = any;
type Cmd = { command: string; on: string; contract: string; description: string };
type Bound = { name: string; on: string; contract: string; description: string };

const FAMILIAR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../familiar");

/** This session's log, read at start; empty until then, and for an ephemeral one. */
let sessionFile = "";

function active<T>(flag: string): T[] {
  try {
    const out = execFileSync(FAMILIAR, ["orchestration", "bindings", flag],
      { encoding: "utf8", timeout: 15000 });
    return JSON.parse(out);
  } catch (e) {
    console.error(`familiar-bindings: no tools: ${(e as Error).message}`);
    return [];
  }
}

function runBound(on: string, task: string, signal?: AbortSignal) {
  const args = ["orchestration", "bindings", "run", on, task, "--cwd", process.cwd()];
  // 12a: the child's delegation line names this session. pi sets PI_SESSION_FILE
  // for a `bash` tool call but not for a process an extension spawns, so the
  // extension passes what it read from `sessionManager` down the same chain.
  const env = { ...process.env, ...(sessionFile ? { PI_SESSION_FILE: sessionFile } : {}) };
  return new Promise<{ code: number; out: string; err: string }>((resolve) => {
    // stdin "ignore": an inherited pipe never closes, and `pi -p` below waits for its EOF
    const child = spawn(FAMILIAR, args, { signal, env, stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", (code) => resolve({ code: code ?? 1, out, err }));
    child.on("error", (e) => resolve({ code: 1, out, err: String(e) }));
  });
}

export default function (pi: ExtensionAPI) {
  if (process.env.PI_BINDINGS !== "1" || process.env.PI_OFFLINE === "1") return;
  pi.on("session_start", (_event: any, ctx: any) => {
    const file = ctx?.sessionManager?.getSessionFile?.();
    if (typeof file === "string") sessionFile = file;
  });
  for (const b of active<Bound>("--tools-json")) {
    pi.registerTool({
      name: `bound_${b.name}`,
      label: `bound ${b.name}`,
      description: `Delegate a ${b.name} to a cheaper child model (binding ${b.on}). ` +
        `It returns: ${b.description} Prefer it over reading many files yourself.`,
      parameters: {
        type: "object",
        properties: { task: { type: "string", description: "what to find, in one request" } },
        required: ["task"],
      },
      async execute(_id: string, params: { task: string }, signal?: AbortSignal) {
        const { code, out, err } = await runBound(b.on, params.task, signal);
        const text = code === 0 ? out
          : code === 4 ? `${out}\n(the child broke its contract: do not trust this text)`
          : `bound_${b.name} failed (exit ${code}): ${err.trim() || out.trim()}`;
        return { content: [{ type: "text", text }], details: { on: b.on, exit: code } };
      },
    });
  }
  for (const c of active<Cmd>("--commands-json")) {
    pi.registerCommand(c.command, {
      description: c.description,
      handler: async (args: string, ctx: any) => {
        ctx.ui.notify(`${c.on}: running as a child...`, "info");
        const { code, out, err } = await runBound(c.on, args.trim());
        const text = code === 0 ? out
          : code === 4 ? `${out}\n(the child broke its contract: do not trust this text)`
          : `${c.on} failed (exit ${code}): ${err.trim() || out.trim()}`;
        pi.sendMessage({ customType: "bound-result", content: text, display: true,
          details: { on: c.on, exit: code } }, { triggerTurn: false });
      },
    });
  }
}
