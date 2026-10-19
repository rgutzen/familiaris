/**
 * Unit test for the familiar-guard extension, run without Pi.
 *
 * Exercises the same hook Pi calls — `tool_call` — with a fake `pi` event
 * emitter and `ctx`. The guard's deny channel is either `{ block: true }`
 * (deny) or `ctx.ui.confirm()` (ask), so the harness records whichever the
 * guard chose.
 *
 * Run: node engine/boundaries/pi-guard/test-guard.mjs
 */
import os from "node:os";

const HOME = os.homedir();
const VAULT = HOME + "/03_" + "ZETTEL";
const PII = HOME + "/04_RESOURCES/Personal-Documents";
const SSH = HOME + "/.ssh";
const CWD = HOME + "/06_SYSTEM";

// Load the guard without Pi: the index.ts imports only node builtins.
const { default: factory } = await import("./index.ts");

let handler;
const pi = { on: (_ev, fn) => { handler = fn; } };

const confirmations = [];
const ctx = {
  model: { provider: "deepseek", id: "deepseek-chat" },
  cwd: CWD,
  ui: { confirm: async (_title, body) => { confirmations.push(body); return false; } },
};

factory(pi);

async function run(tool, input, provider) {
  confirmations.length = 0;
  ctx.model = { provider, id: "x" };
  const event = { toolName: tool, input };
  let res = await handler(event, ctx);
  if (res === undefined && confirmations.length) {
    // ctx.ui.confirm returned false -> the guard blocks.
    res = { block: true, reason: confirmations[0] };
  }
  return !!(res && res.block);
}

const CASES = [
  // models: all rules are gotgenes' job — this guard must NOT fire on them.
  ["D1 read (models:all)",   "remote", "read",  { path: VAULT + "/n.md" },        false],
  ["D1 write (models:all)",  "remote", "write", { path: VAULT + "/x.md" },        false],
  ["git push (models:all)",  "remote", "bash",  { command: "git push origin main" }, false],
  ["restic write (all)",     "remote", "write", { path: HOME + "/.local/share/restic/p" }, false],
  // models: remote — this guard's territory.
  ["personal doc read, remote", "remote", "read", { path: PII + "/t/x" },     true],
  ["personal doc read, LOCAL",  "ollama", "read", { path: PII + "/t/x" },     false],
  ["ssh key read, remote",   "remote", "read",  { path: SSH + "/id_ed25519" },    true],
  ["ssh key read, LOCAL",    "ollama",  "read",  { path: SSH + "/id_ed25519" },    false],
  ["personal doc bash cat, remote", "remote", "bash", { command: "cat " + PII + "/t/x" }, true],
  ["personal doc bash cat, LOCAL",  "ollama", "bash", { command: "cat " + PII + "/t/x" }, false],
  ["ssh bash cat, remote",   "remote", "bash",  { command: "cat " + SSH + "/id_ed25519" }, true],
  ["ssh bash cat, LOCAL",    "ollama",  "bash",  { command: "cat " + SSH + "/id_ed25519" }, false],
  ["hermes env, remote",     "remote", "bash",  { command: "cat ~/.hermes/.env" }, true],
  // The model axis must NOT leak into models:all surfaces.
  ["vault read (all), remote", "remote", "read", { path: VAULT + "/n.md" },       false],
  ["unrelated bash",         "remote", "bash",  { command: "git status" },        false],
  ["agents leaf read",       "remote", "read",  { path: CWD + "/memory/knowledge/INDEX.md" }, false],
];

let fail = 0;
for (const [label, provider, tool, input, expect] of CASES) {
  const got = await run(tool, input, provider);
  const ok = got === expect;
  fail += !ok;
  console.log(`${ok ? "ok  " : "FAIL"}  ${label.padEnd(26)} ${provider.padEnd(6)} ` +
              `expect=${(expect ? "BLOCK" : "allow").padEnd(5)} got=${got ? "BLOCK" : "allow"}`);
}
console.log("\nFAILURES:", fail, `/ ${CASES.length} cases`);
process.exit(fail ? 1 : 0);
