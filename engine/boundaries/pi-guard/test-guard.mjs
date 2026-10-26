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

// ── the parity corpus (boundaries.md §Parity corpus) ─────────────────────────
// One fixture, run by every judge. A case whose `expected_fail` names this judge
// must still FAIL here; one that starts passing is reported, so the entry goes.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
const PARITY = JSON.parse(readFileSync(
  fileURLToPath(new URL("../fixtures/parity.json", import.meta.url)), "utf8")).cases;
const VAULT_NAME = "03_" + "ZETTEL";
const expand = (v) => v.replaceAll("{VAULT_NAME}", VAULT_NAME)
  .replaceAll("{VAULT}", HOME + "/" + VAULT_NAME)
  .replaceAll("{CWD}", CWD).replaceAll("{HOME}", HOME);
// pi-guard enforces only the model axis (`models: local|remote`); a `models: all`
// rule is gotgenes' job, so such a case expects `allow` HERE. `find` IS pi's
// glob tool ("Find paths using glob patterns", docs/cli.md) and carries both a
// `path` and a `pattern`, which the vocabulary checks -- a corpus case that used
// to be skipped for pi now runs.
const PI = { read: ["read", { path: "path" }], write: ["write", { path: "path" }],
             edit: ["edit", { path: "path" }], grep: ["grep", { pattern: "pattern", path: "path" }],
             find: ["find", { path: "path", pattern: "pattern" }],
             bash: ["bash", { command: "command" }] };
let skipped = 0;
for (const c of PARITY) {
  const toolName = (c.tool_by_judge && c.tool_by_judge.pi) || c.tool;
  if (!PI[toolName]) { skipped++; continue; }
  const [tool, fields] = PI[toolName];
  const input = Object.fromEntries(Object.entries(c.args).map(([k, v]) => [fields[k], expand(v)]));
  const got = await run(tool, input, c.model === "local" ? "ollama" : "deepseek");
  // A case may state this judge's own answer, for a reason in `why` -- pi does
  // not judge `models: all` rules, but an unparseable command still fails closed.
  const stated = c.expect_by_judge && c.expect_by_judge.pi;
  const want = stated ? stated !== "allow" : (c.rule === "all" ? false : c.expect !== "allow");
  const known = (c.expected_fail || {}).pi;
  const ok = known ? got !== want : got === want;
  fail += !ok;
  console.log(`${known && ok ? "xfail" : ok ? "ok  " : "FAIL"}  parity: ${c.label.padEnd(26)} ` +
              `expect=${(want ? "BLOCK" : "allow").padEnd(5)} got=${got ? "BLOCK" : "allow"}` +
              (known ? `  (known: ${known})` : ""));
}
console.log("\nFAILURES:", fail, `/ ${CASES.length + PARITY.length - skipped} cases ` +
            `(${PARITY.length - skipped} parity, ${skipped} skipped: no such pi tool)`);
process.exit(fail ? 1 : 0);
