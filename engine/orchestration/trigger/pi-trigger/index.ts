/**
 * pi-trigger -- item 5b's advisory hint: a count, not a judgement call.
 *
 * WHY. Across 112 pi sessions no session delegated real work
 * (`dev/orchestration/2026-10-12-delegation-usage.md`). An always-on sentence
 * ("Offload bulk recon ... with `pi-agent`") is not a trigger, so option B
 * replaces the judgement with a count: inside ONE USER TURN, `>= 6` distinct
 * files read AND `>= 80 KB` of tool output. When both cross, this extension sends
 * ONE hint naming the read-only role `explore` (5a: `config/orchestration/
 * explore.md`, model `deepseek-flash`) and the command to delegate with. Nothing
 * else happens: no tool is registered (a schema costs every parent session), no
 * file is written, and the model is free to ignore the hint. The replay that
 * produced the numbers, and the counter's rules, live in the sibling Python
 * package `engine/orchestration/trigger/__init__.py`; `familiar orchestration
 * trigger --replay 30` re-measures them.
 *
 * THE NUMBERS ARE THE REPLAYED PARAMETERS, not a policy (see `TRIGGER` below and
 * the Python module's docstring): `>= 6 files & >= 80 KB` is the row of
 * `2026-10-12-delegation-usage.md` §the table at lines ~40-70 that fired on 27% of
 * turns at 84% precision and 97% recall, chosen in `PLAN.md` §"Option B, decided
 * -- the trigger and its floor". A threshold change is a RE-CALIBRATION under a
 * new wording or method: it moves the precision and the recall in the record, so
 * it must be replayed and re-recorded, never tuned.
 *
 * WHAT IT COUNTS, AND WHY THE BASH RULE IS HERE. Files are the arguments of the
 * reading tools -- `read`'s `path`, `grep`'s `path`/`glob`, `find`'s `path`, `ls`'s
 * `path` -- PLUS the file arguments of `cat`/`sed`/`head`/`tail` inside `bash`, as
 * the 2026-10-12 replay did. The reading tools alone are not enough on this
 * machine: 11,167 `bash` calls against 532 reading-tool calls across the 154
 * session logs, so the four tools alone fire on 2 of 108 replayed turns (1.9%)
 * against the recorded 27% -- a property of the counting, not of the workload. The
 * replay reports both rates on every run. Bytes are the `len` of the `text` of
 * every tool result in the turn, which is the record's "all tool-result text":
 * `.length` here (UTF-16 code units), `len` in the Python replay (code points), so
 * the two disagree by a few characters on a non-BMP character -- measured
 * 2026-10-14 across 7,469 real results, 56 of them (0.8%), never near the 80 KB
 * floor. Per-entry cwd is not in a path string, so a relative and an absolute
 * spelling of one file count as two, exactly as in the record.
 *
 * THE HOOKS, AND WHERE EACH WAS FOUND (pi 1.1.0):
 *   `tool_call`    docs/extensions.md §"Choose an integration point" ("Observe or
 *                  modify lifecycle behavior" -> `pi.on()`), and its shape from
 *                  examples/extensions/permission-gate.ts (`event.toolName`,
 *                  `event.input`) and rtk.ts (`event.input.command`); the runtime
 *                  that emits it is `_beforeToolCall` in the pi 1.1.0 binary
 *                  (`emitToolCall({ type: "tool_call", toolName, toolCallId,
 *                  input })`).
 *   `tool_result`  examples/extensions/git-checkpoint.ts (`pi.on("tool_result",
 *                  async (_event, ctx) => ...)`), shape from `_afterToolCall` in
 *                  the binary (`{ type: "tool_result", toolName, toolCallId,
 *                  input, content, details, isError, usage }`) and from
 *                  `ToolResultEventBase` in
 *                  node_modules/@earendil-works/pi-coding-agent (0.79.8)
 *                  dist/core/extensions/types.d.ts (`content: (TextContent |
 *                  ImageContent)[]`). Bytes are computed from `event.content`'s
 *                  text blocks, NOT from `event.details`, so a redaction by a
 *                  later handler cannot change what the parent paid for.
 *   `input`        the hook that marks ONE USER TURN: examples/extensions/
 *                  input-transform.ts (`event.source`) and inline-bash.ts
 *                  (`event.text`), shape from the 0.79.8 types.d.ts `InputEvent`
 *                  (`text`, `source`, `streamingBehavior`) and from the binary's
 *                  `_runInputHandlers(text, images, source, streamingBehavior)`,
 *                  which runs on every prompt -- `sendUserMessage` passes
 *                  `source: "extension"`, so extension-injected content does not
 *                  reset the counters. pi's own `turn_start`/`turn_end` are one
 *                  assistant response, several per user prompt, so they cannot
 *                  split the turn the replay splits.
 *   `sendMessage`  `pi.sendMessage(message, options)` -- docs/extensions.md
 *                  §"Choose an integration point" -- with `{ triggerTurn: false }`,
 *                  the shape engine/orchestration/pi-bindings/index.ts uses. In
 *                  the binary's `sendCustomMessage`, `triggerTurn: false` appends
 *                  a `custom_message` entry (queued to the end of the assistant
 *                  turn while streaming) and never starts a model request of its
 *                  own, which is what makes the hint advisory.
 *
 * One limit of the split: a call another extension BLOCKS returns before the
 * result hook (the binary's `prepareToolCall` returns `kind: "immediate"` and
 * skips `_afterToolCall`), so its file is counted at `tool_call` while no
 * `tool_result` follows. The replay counts that call too -- the transcript records
 * the call even when its result is an error -- so the two agree, and the error is
 * at most one file above the floor.
 *
 * A THIRD OF THE FIRES ARE WITHHELD AT RANDOM (14a, ruled 2026-10-22). Comparing
 * turns that delegated with turns that did not compares tasks, not delegation:
 * the agent chooses which turns to delegate, and the big ones are likelier to.
 * So at a fire the hint is sent with probability `1 - withhold` and otherwise
 * withheld, and a withheld fire is still RECORDED -- `pi.appendEntry` of
 * `explore-trigger-withheld` (docs/session-format.md: a `custom` entry, durable
 * and outside the model's context) with the hint's own `details`. 5d's third
 * floor reads the two arms (`log.py`, the randomisation as an instrument).
 * `withhold: 0` restores the old behaviour.
 *
 * ON BY DEFAULT, because 5d measures its fires. A pi-agent child (PI_OFFLINE=1)
 * never loads it: a child's own reads are its work, and a hint inside a child
 * would spend the child's prompt budget to ask the child to delegate to itself.
 *
 * IT ALSO CLOSES THE DELEGATION LOG (12a). The log's `used` field is judged from
 * what the parent did after a child returned, so it can only be filled at the end
 * of the parent session. It used to wait for someone to run `delegations --replay`
 * by hand, and uptake therefore had no denominator. On `session_shutdown` this
 * extension runs `familiar orchestration delegations --write --parent <session>`,
 * which recomputes that session's delegation lines and upserts them. `--parent`
 * names the file rather than `--replay 1` so the write cannot race another session
 * that started later. The handler is synchronous and time-boxed: a pi that is
 * quitting must not wait on a log, and a failed write is reported, never fatal --
 * the log line the child wrote is already there, without `used`.
 *
 * A SESSION WITH NO LOG IS SKIPPED, NOT AN ERROR (2026-10-25). pi creates the
 * session file lazily, so a session in which nothing was sent closes with no file
 * on disk, and the write then failed with `delegations: no session log at ...` --
 * noise on every empty session's exit. An absent parent log means there are no
 * delegation lines to recompute (the parent log is `used`'s only source), so the
 * hook skips it quietly. `delegations` itself keeps exit 2 for an absent
 * `--parent`, where a manual caller's misspelt path must be heard, and where a
 * vanished log for a session that had turns is that caller's finding.
 *
 * Node test (no Pi needed): the factory and the pure counters are exported, so
 * `node -e 'await import("./index.ts")'` with stub hooks drives them directly.
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/**
 * THE REPLAYED PARAMETERS -- one block, mirroring
 * `engine/orchestration/trigger/__init__.py` (MIN_FILES / MIN_BYTES / ROLE /
 * DELEGATE / RECORDED_RATE / RATE_TOLERANCE). Source:
 * dev/orchestration/2026-10-12-delegation-usage.md, the row
 * `>= 6 files & >= 80 KB`; and dev/orchestration/PLAN.md §"Option B, decided".
 */
export const TRIGGER = {
  minFiles: 6,
  minBytes: 80 * 1024,
  role: "explore",
  command: 'pi-agent explore "<task>"',
  recordedRate: 0.27,
  rateTolerance: 0.2,
  withhold: 0.33,           // 14a: the share of fires that send no hint
  source: "2026-10-12-delegation-usage.md, row `>= 6 files & >= 80 KB`",
} as const;

/** Which argument of which reading-tool call names a file it reads. */
export const FILE_ARGS: Record<string, readonly string[]> = {
  read: ["path"],
  grep: ["path", "glob"],   // the search root, and the filter it restricts to
  find: ["path"],           // the search root; `pattern` is a glob, not a file
  ls: ["path"],             // the directory; absent = the cwd, which names no file
};

/** The record's bash rule: the file-dumping commands, and only those. */
export const BASH_READ_COMMANDS = ["cat", "sed", "head", "tail"];

const SEGMENT = /[;&|]{1,2}|\n/;
const HINT_TYPE = "explore-trigger";
const WITHHELD_TYPE = "explore-trigger-withheld";

/** The arm's draw; a test replaces it to choose the arm. */
let draw: () => number = Math.random;
export function setDraw(fn: () => number): void { draw = fn; }

/** 14a: whether this fire sends no hint. */
export function withheld(u: number = draw(), share: number = TRIGGER.withhold): boolean {
  return u < share;
}

/**
 * `sed`'s first non-flag argument is its script (`sed -n '1,200p' file`,
 * `sed -i '/re/d' file`), never a file: without this rule a quoted script
 * containing `/` is counted as a path. Mirrors the Python `SCRIPT_ARG`.
 */
export const SCRIPT_ARG: Record<string, number> = { sed: 1 };

/** One user turn's counters. */
export type Counter = { files: Set<string>; bytes: number; fired: boolean };

export function createCounter(): Counter {
  return { files: new Set<string>(), bytes: 0, fired: false };
}

/** The reading-tool rule: the file arguments of one call, per `FILE_ARGS`. */
export function readPaths(toolName: unknown, input: unknown): string[] {
  const keys = typeof toolName === "string" ? FILE_ARGS[toolName] : undefined;
  if (!keys || typeof input !== "object" || input === null) return [];
  const args = input as Record<string, unknown>;
  return keys.filter((key) => typeof args[key] === "string" && args[key] !== "")
    .map((key) => args[key] as string);
}

/** Split one command segment into tokens, dropping quotes. Not shlex: see below. */
function tokens(segment: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quote = "";
  for (const ch of segment) {
    if (quote) {
      if (ch === quote) quote = "";
      else cur += ch;
      continue;
    }
    if (ch === '"' || ch === "'") { quote = ch; continue; }
    if (ch === " " || ch === "\t") { if (cur) { out.push(cur); cur = ""; } continue; }
    cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

/**
 * The files a bash command reads, per `BASH_READ_COMMANDS`. The record's rule,
 * and deliberately a token rule: `;` `&&` `||` `|` and newline split the command,
 * a segment whose first token (basename) is a reading command contributes its
 * non-flag arguments -- minus `SCRIPT_ARG`'s script argument, minus a redirect
 * operator and its target -- when they contain `/` or `.`. A shell is not
 * parseable exactly, so this misses (`xargs cat`, a path in a variable) and can
 * over-count (a redirect target). Mirrors the Python `bash_read_paths`; the quote
 * handling is a plain scanner rather than `shlex`, which differs only for escapes
 * and nested quotes.
 */
export function bashReadPaths(command: unknown): string[] {
  if (typeof command !== "string") return [];
  const found = new Set<string>();
  for (const segment of command.split(SEGMENT)) {
    const argv = tokens(segment);
    if (argv.length === 0) continue;
    const cmd = argv[0].split("/").pop() ?? "";
    if (!BASH_READ_COMMANDS.includes(cmd)) continue;
    let scripts = SCRIPT_ARG[cmd] ?? 0;
    let skipNext = false;
    for (const token of argv.slice(1)) {
      if (skipNext) { skipNext = false; continue; }
      if (token.startsWith(">") || token.startsWith("<")) { skipNext = token.length === 1; continue; }
      if (token.startsWith("-")) continue;
      if (scripts > 0) { scripts -= 1; continue; }
      if (token.includes("/") || token.includes(".")) found.add(token);
    }
  }
  return [...found];
}

/** Every file one tool call names, both rules together. */
export function filesInCall(toolName: unknown, input: unknown): string[] {
  const out = readPaths(toolName, input);
  if (toolName === "bash" && typeof input === "object" && input !== null) {
    out.push(...bashReadPaths((input as Record<string, unknown>).command));
  }
  return out;
}

/** Tool-output bytes: the length of every text block of a tool result. */
export function textBytes(content: unknown): number {
  if (!Array.isArray(content)) return 0;
  let total = 0;
  for (const block of content) {
    if (typeof block === "object" && block !== null && (block as any).type === "text"
        && typeof (block as any).text === "string") {
      total += (block as any).text.length;
    }
  }
  return total;
}

/** Both floors hold, and the hint has not been sent for this turn. */
export function crossed(state: Counter, minFiles: number = TRIGGER.minFiles,
                        minBytes: number = TRIGGER.minBytes): boolean {
  return state.files.size >= minFiles && state.bytes >= minBytes;
}

export function reset(state: Counter): void {
  state.files.clear();
  state.bytes = 0;
  state.fired = false;
}

/** The advisory text: what was counted, who to delegate to, and how to verify. */
export function hint(state: Counter): string {
  return `This turn has read ${state.files.size} distinct files and taken in ` +
    `${Math.round(state.bytes / 1024)} KB of tool output. The rest can go to the ` +
    `read-only role \`${TRIGGER.role}\`, which keeps it out of this context:\n` +
    `  ${TRIGGER.command}\n` +
    `It replies with \`path:line\` + a verbatim quote per line; verify each quote.`;
}

export default function (pi: ExtensionAPI) {
  if (process.env.PI_OFFLINE === "1") return;
  const state = createCounter();
  // One user turn, one window: `input` fires on every human prompt (and, with
  // source "extension", on an extension-injected one, which is not a new turn).
  pi.on("input", (event: any) => {
    if (event?.source !== "extension") reset(state);
  });

  pi.on("tool_call", (event: any) => {
    for (const path of filesInCall(event?.toolName, event?.input)) state.files.add(path);
  });

  pi.on("tool_result", (event: any) => {
    state.bytes += textBytes(event?.content);
    if (state.fired || !crossed(state)) return;
    state.fired = true;
    const details = { files: state.files.size, bytes: state.bytes,
                      role: TRIGGER.role, source: TRIGGER.source };
    if (withheld()) {
      pi.appendEntry(WITHHELD_TYPE, { ...details, withhold: TRIGGER.withhold });
      return;
    }
    pi.sendMessage(
      { customType: HINT_TYPE, content: hint(state), display: true, details },
      { triggerTurn: false },
    );
  });

  // 12a: the parent says which log it is, so the delegation log can be closed
  // without anyone remembering to replay it.
  pi.on("session_shutdown", (_event: any, ctx: any) => {
    const file = ctx?.sessionManager?.getSessionFile?.();
    if (typeof file !== "string" || file === "") return;   // an ephemeral session has nothing on disk
    closeDelegations(file);
  });
}

/** The engine's entry point: this file's repository, or `familiar` on PATH. */
export const FAMILIAR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), "../../../familiar");

/** A command and its argv; a test replaces `runner` so the real `familiar` never runs. */
type Exec = (command: string, args: string[]) => unknown;

const execFamiliar: Exec = (command, args) =>
  execFileSync(command, args, { stdio: ["ignore", "ignore", "pipe"], timeout: 30000 });

let runner: Exec = execFamiliar;

/** The runner; `null` restores the real one (the `setDraw` pattern). */
export function setRunner(fn: Exec | null): void { runner = fn ?? execFamiliar; }

/**
 * Fill `used` for one parent session's delegation lines, in place.
 *
 * Synchronous on purpose: pi is shutting down and an async spawn would be killed
 * with it. A session file that does not exist -- pi never wrote it, so nothing
 * was sent -- is skipped quietly, and the rule's reason is in the header above.
 * A throw is caught and reported rather than propagated -- this hook is
 * bookkeeping, and a bookkeeping failure must not turn into an exit code.
 */
export function closeDelegations(file: string): void {
  if (!existsSync(file)) return;
  try {
    runner(FAMILIAR, ["orchestration", "delegations", "--write", "--parent", file]);
  } catch (e) {
    console.error(`familiar-trigger: delegation log not closed: ${(e as Error).message}`);
  }
}
