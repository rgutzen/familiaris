/** Unit test for the familiar-boundaries opencode plugin, run without opencode.
 *  Exercises the same hook opencode calls: tool.execute.before(input, output).
 *  Run: node engine/boundaries/opencode-plugin/test-plugin.mjs
 */
import { server } from "./index.js";
import os from "node:os";

const HOME = os.homedir();
const VAULT = HOME + "/03_" + "ZETTEL";
const PII = HOME + "/04_RESOURCES/Personal-Documents";
const RESTIC = HOME + "/.local/share/restic";
const CWD = HOME + "/06_SYSTEM";

const hooks = await server({ directory: CWD, worktree: CWD });
const before = hooks["tool.execute.before"];
const params = hooks["chat.params"];

// Two sessions: one on a remote provider, one on the local Ollama provider.
await params({ sessionID: "remote", provider: { info: { id: "deepseek" } } });
await params({ sessionID: "local", provider: { info: { id: "local-ollama" } } });

const CASES = [
  ["D1 read",              "remote", "read",  { filePath: VAULT + "/n.md" },            true],
  ["D1 read (local too)",  "local",  "read",  { filePath: VAULT + "/n.md" },            true],
  ["D1 bash tilde",        "remote", "bash",  { command: "ls ~/03_" + "ZETTEL" },       true],
  ["D1 write",             "remote", "write", { filePath: VAULT + "/x.md" },            true],
  ["personal doc, remote", "remote", "read",  { filePath: PII + "/t/x" },             true],
  ["personal doc, LOCAL",  "local",  "read",  { filePath: PII + "/t/x" },             false],
  ["ssh key, remote",      "remote", "read",  { filePath: HOME + "/.ssh/id_ed25519" },  true],
  ["ssh key, LOCAL",       "local",  "read",  { filePath: HOME + "/.ssh/id_ed25519" },  false],
  ["restic read",          "remote", "read",  { filePath: RESTIC + "/p/config" },       false],
  ["restic 2>&1 pipe",     "remote", "bash",  { command: "restic -r " + RESTIC + "/p snapshots 2>&1 | head" }, false],
  ["restic rm",            "remote", "bash",  { command: "rm -rf " + RESTIC + "/p" },   true],
  ["restic write",         "remote", "write", { filePath: RESTIC + "/p/config" },       true],
  ["git push",             "remote", "bash",  { command: "git push origin main" },      true],
  ["git rebase",           "remote", "bash",  { command: "git rebase -i main" },        true],
  ["git commit",           "remote", "bash",  { command: "git commit -m x" },           false],
  ["grep for literal",     "remote", "grep",  { pattern: "03_" + "ZETTEL", path: CWD }, false],
  ["agents leaf",          "remote", "read",  { filePath: CWD + "/memory/knowledge/INDEX.md" },  false],
  ["unrelated bash",       "remote", "bash",  { command: "git status" },                false],
];

let fail = 0;
for (const [label, session, tool, args, expect] of CASES) {
  let denied = false, msg = "";
  try {
    await before({ tool, sessionID: session, callID: "c" }, { args });
  } catch (e) {
    denied = true;
    msg = e.message.slice(0, 60);
  }
  const ok = denied === expect;
  if (!ok) fail++;
  console.log(`${ok ? "ok  " : "FAIL"}  ${label.padEnd(22)} ${session.padEnd(6)} ` +
              `expect=${(expect ? "DENY" : "allow").padEnd(5)} got=${denied ? "DENY" : "allow"}`);
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
// opencode's channel is a throw: `ask` and `deny` both arrive as a refusal.
const OC = { read: ["read", { path: "filePath" }], write: ["write", { path: "filePath" }],
             edit: ["edit", { path: "filePath" }], glob: ["glob", { pattern: "pattern" }],
             grep: ["grep", { pattern: "pattern", path: "path" }], bash: ["bash", { command: "command" }] };
for (const c of PARITY) {
  const [tool, fields] = OC[c.tool];
  const args = Object.fromEntries(Object.entries(c.args).map(([k, v]) => [fields[k], expand(v)]));
  let denied = false;
  try { await before({ tool, sessionID: c.model, callID: "p" }, { args }); } catch { denied = true; }
  const want = c.expect !== "allow";
  const known = (c.expected_fail || {}).opencode;
  const ok = known ? denied !== want : denied === want;
  if (!ok) fail++;
  console.log(`${known && ok ? "xfail" : ok ? "ok  " : "FAIL"}  parity: ${c.label.padEnd(26)} ` +
              `expect=${(want ? "DENY" : "allow").padEnd(5)} got=${denied ? "DENY" : "allow"}` +
              (known ? `  (known: ${known})` : ""));
}
console.log("\nFAILURES:", fail, `/ ${CASES.length + PARITY.length} cases (${PARITY.length} parity)`);
process.exit(fail ? 1 : 0);
