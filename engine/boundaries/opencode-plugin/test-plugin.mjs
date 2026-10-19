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
console.log("\nFAILURES:", fail, `/ ${CASES.length} cases`);
process.exit(fail ? 1 : 0);
