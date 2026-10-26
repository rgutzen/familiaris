/**
 * R3a spike -- can a pi dialog be raced between the terminal and a second answerer,
 * and the loser withdrawn? Not the extension (that is R3b); the measurement.
 *
 * The "phone" is a file: when $R3A_DIR/answer appears, its content answers the open
 * dialog. Every interception and its outcome goes to $R3A_DIR/log.jsonl.
 *
 * THE MECHANISM UNDER TEST. Every extension's `ctx.ui` is the runner's one
 * `uiContext` object (pi 1.3.0: `get ui() { return runner.uiContext }`), so
 * replacing its `select`/`confirm`/`input` here intercepts the dialogs of every
 * extension in the session, the permission system's included. The terminal dialog
 * is given an AbortSignal (pi's TUI `showExtensionSelector` honours `opts.signal`:
 * abort hides the selector and resolves undefined).
 */
import fs from "node:fs";
import path from "node:path";

type ExtensionAPI = any;

const DIR = process.env.R3A_DIR || "/tmp/r3a";
const log = (row: Record<string, unknown>) =>
  fs.appendFileSync(path.join(DIR, "log.jsonl"), JSON.stringify({ t: Date.now(), ...row }) + "\n");

function phone(signal: AbortSignal): Promise<string> {
  const file = path.join(DIR, "answer");
  return new Promise((resolve) => {
    const tick = setInterval(() => {
      if (signal.aborted) return clearInterval(tick);
      if (fs.existsSync(file)) {
        const value = fs.readFileSync(file, "utf8").trim();
        fs.unlinkSync(file);
        clearInterval(tick);
        resolve(value);
      }
    }, 200);
  });
}

function race(kind: string, title: string, local: (signal: AbortSignal) => Promise<any>,
              fromPhone: (v: string) => any, outer?: AbortSignal) {
  const localStop = new AbortController();
  const phoneStop = new AbortController();
  outer?.addEventListener("abort", () => localStop.abort(), { once: true });
  log({ ev: "intercepted", kind, title: String(title).slice(0, 200) });
  const l = local(localStop.signal).then((v) => ({ by: "terminal", v }));
  const p = phone(phoneStop.signal).then((v) => ({ by: "phone", v: fromPhone(v) }));
  return Promise.race([l, p]).then((won) => {
    if (won.by === "phone") localStop.abort();
    else phoneStop.abort();
    log({ ev: "resolved", kind, by: won.by, value: won.v });
    return won.v;
  });
}

function wrap(ui: any) {
  if (!ui || ui.__r3a) return;
  const select = ui.select.bind(ui), confirm = ui.confirm.bind(ui), input = ui.input.bind(ui);
  ui.select = (title: string, options: string[], opts: any = {}) =>
    race("select", title, (s) => select(title, options, { ...opts, signal: s }),
         (v) => (options.includes(v) ? v : undefined), opts?.signal);
  ui.confirm = (title: string, message: string, opts: any = {}) =>
    race("confirm", title, (s) => confirm(title, message, { ...opts, signal: s }),
         (v) => /^y/i.test(v), opts?.signal);
  ui.input = (title: string, placeholder?: string, opts: any = {}) =>
    race("input", title, (s) => input(title, placeholder, { ...opts, signal: s }),
         (v) => v, opts?.signal);
  ui.__r3a = true;
  log({ ev: "wrapped" });
}

export default function (pi: ExtensionAPI) {
  fs.mkdirSync(DIR, { recursive: true });
  pi.on("session_start", async (_e: any, ctx: any) => wrap(ctx.ui));
  pi.on("turn_start", async (_e: any, ctx: any) => wrap(ctx.ui));   // in case the object was replaced
  pi.registerCommand("r3a-confirm", {
    description: "spike: a third-party extension's own confirm dialog",
    handler: async (_args: string, ctx: any) => {
      const ok = await ctx.ui.confirm("r3a: a third-party dialog", "Proceed?");
      log({ ev: "command-result", ok });
      ctx.ui.notify(`r3a-confirm returned ${ok}`, "info");
    },
  });
}
