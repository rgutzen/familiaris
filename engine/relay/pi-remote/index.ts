/**
 * familiar-remote -- an interactive pi session reaches the phone while the user is away
 * (dev/remote R3b; the measurement it rests on is dev/remote/2026-10-20-race.md).
 *
 * PRESENCE, per session. Away when the terminal had no input for `away_after`
 * (config/relay/relay.yaml), when `hyprlock` runs, or when the phone sent `/away`
 * and this terminal had no input since. Local input is presence again.
 *
 * WHAT GOES TO THE PHONE WHILE AWAY:
 *
 * 1. Extension dialogs -- `ask_user`, any extension's `select`/`confirm`/`input`.
 *    Every extension shares the runner's one `uiContext`, so its methods are
 *    wrapped here: the terminal dialog shows as always, and once the user is away
 *    (at the start, or later while it is still open) the same ask goes to the
 *    relay. The first answer wins; the terminal dialog is closed through its
 *    AbortSignal, or the phone message is withdrawn.
 * 2. Permission asks -- through the `familiar-remote` chain link, because in the
 *    terminal pi-permission-system draws its ask with `ui.custom`, which nothing
 *    can carry to a phone. Away: the link asks the relay and returns allow, or
 *    deny with the worded reason; if the user comes back first, the phone ask is
 *    withdrawn and the link defers, so the terminal dialog appears. Present: it
 *    defers at once. The package caps a link's `allow` on `path` and
 *    `external_directory` to a terminal dialog (bounded delegation, by design).
 *    The link grants nothing until named in `authorizerChain` (R3d).
 * 3. Turn ends -- at `agent_end`, the last assistant text, as an `input` ask; a
 *    reply becomes the next user message (`pi.sendUserMessage`). A new turn or
 *    local input withdraws it.
 *
 * WITHOUT A RELAY nothing changes: a phone ask that cannot connect never
 * answers, so the terminal is the only answerer, as before this extension.
 *
 * KNOWN LIMIT: a permission ask that appeared while the user was present has
 * already been deferred to the terminal dialog; walking away from it later does
 * not move it to the phone (the custom dialog cannot be raced, see 1/2 above).
 */
import { execFile } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import os from "node:os";

// No import of pi's packages: this file lives outside pi's module tree (pi-guard's reason).
type ExtensionAPI = any;

export const LINK = "familiar-remote";
const SERVICES_KEY = Symbol.for("@gotgenes/pi-permission-system:session-services");
// The installed tree's settings, like every extension here (pi-guard's twin rule).
const CONFIG = path.join(os.homedir(), "06_SYSTEM/config/relay/relay.yaml"); // roots-twin: RELAY_CONFIG
const LATE_CHECK_MS = 15_000;
const RECONNECT_MS = 10_000;
export const PERMISSION_OPTIONS = ["Yes", "No", "No, provide reason"];
/** A capped ask's "Yes": the package turns a link's allow on the path and
 * external_directory families into `defer` (R3a), so the phone can deny such an ask
 * but only hand an approval to the terminal. Said on the button, not after it
 * (R3c, 2026-10-21: the message closed as "Yes" while the dialog waited). */
export const CAPPED_YES = "Yes (confirm at the terminal)";

export function capped(details: any): boolean {
  const s = String(details?.surface ?? details?.payload?.request?.surface ?? "");
  return s.startsWith("path") || s.startsWith("external_directory");
}

export function permissionOptions(details: any): string[] {
  return capped(details) ? [CAPPED_YES, "No", "No, provide reason"] : PERMISSION_OPTIONS;
}

// --- configuration and presence ----------------------------------------------------

/** `away_after` in seconds from relay.yaml (a quoted or bare number); 600 if absent. */
export function awayAfterSeconds(text: string): number {
  const m = /^\s*away_after:\s*"?(\d+)"?\s*$/m.exec(text);
  return m ? Number(m[1]) : 600;
}

export interface Presence {
  now: number;            // ms
  lastInput: number;      // ms
  awayAfterS: number;
  locked: boolean;        // hyprlock runs
  awaySince: number | null; // s, from the relay (`/away`), or null
}

/** Why the user counts as away, or null when present. */
export function awayReason(p: Presence): string | null {
  if (p.locked) return "the screen is locked";
  if (p.awaySince !== null && p.awaySince * 1000 > p.lastInput) return "/away from the phone";
  if (p.now - p.lastInput >= p.awayAfterS * 1000) return `no input for ${p.awayAfterS}s`;
  return null;
}

// --- rendering a permission ask, and reading the answer ---------------------------

/** The lines the phone shows: tool, rule, and the value the ask is about. */
export function permissionTitle(details: any): string {
  const r = details?.payload?.request ?? {};
  const lines = ["Permission Required"];
  const tool = details?.toolName ?? r.toolName;
  if (tool) lines.push(`tool    : ${tool}`);
  const surface = details?.surface ?? r.surface;
  if (surface && surface !== tool) lines.push(`surface : ${surface}`);
  if (r.matchedPattern) lines.push(`rule    : ${r.matchedPattern}`);
  const value = details?.command ?? details?.path ?? details?.target ?? r.executedUnit ?? details?.value;
  if (value) lines.push(`${details?.path ? "path   " : "command"} : ${String(value)}`);
  if (capped(details)) lines.push("(a path approval is confirmed at the terminal; the phone can deny it)");
  return lines.join("\n");
}

/** A relay answer as a chain verdict. A worded reply is a denial whose reason the model reads. */
export function verdict(answer: any): { kind: "allow" } | { kind: "deny"; reason?: string } | { kind: "defer" } {
  if (!answer || answer.cancelled) return { kind: "defer" };
  if (answer.value === "Yes") return { kind: "allow" };
  if (answer.value === CAPPED_YES) return { kind: "defer" };
  const words = String(answer.text ?? "").trim();
  if (words) return { kind: "deny", reason: `The user answered from the phone: ${words}` };
  if (answer.value === "No" || answer.value === "No, provide reason") {
    return { kind: "deny", reason: "The user denied this from the phone." };
  }
  return { kind: "defer" };
}

// --- the relay, over its socket ----------------------------------------------------

export function sockPath(env = process.env): string {
  if (env.FAMILIAR_RELAY_SOCK) return env.FAMILIAR_RELAY_SOCK;
  const runtime = env.XDG_RUNTIME_DIR || `/run/user/${process.getuid?.() ?? 1000}`;
  return path.join(runtime, "familiar-relay.sock");
}

function request(obj: object): Promise<any> {
  return new Promise((resolve) => {
    const s = net.createConnection(sockPath());
    let buf = "";
    s.setTimeout(5000, () => { s.destroy(); resolve(null); });
    s.on("error", () => resolve(null));
    s.on("data", (d) => {
      buf += d.toString();
      const i = buf.indexOf("\n");
      if (i >= 0) { s.end(); try { resolve(JSON.parse(buf.slice(0, i))); } catch { resolve(null); } }
    });
    s.on("connect", () => s.write(JSON.stringify(obj) + "\n"));
  });
}

/** An ask that resolves with the relay's answer; `withdraw` closes it. Reconnects with
 * the same id until answered or withdrawn; a relay that never comes never answers. */
export function phoneAsk(req: Record<string, unknown>) {
  let done = false;
  let sock: net.Socket | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const answer = new Promise<any>((resolve) => {
    const connect = () => {
      if (done) return;
      let buf = "";
      sock = net.createConnection(sockPath());
      sock.on("connect", () => sock!.write(JSON.stringify({ op: "ask", ...req }) + "\n"));
      sock.on("data", (d) => {
        buf += d.toString();
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, i); buf = buf.slice(i + 1);
          try {
            const msg = JSON.parse(line);
            if (msg.op === "answer" && msg.id === req.id) { done = true; sock?.end(); resolve(msg); }
          } catch { /* not ours */ }
        }
      });
      const retry = () => { if (!done) timer = setTimeout(connect, RECONNECT_MS); };
      sock.on("error", retry);
      sock.on("close", () => { if (!done) retry(); });
    };
    connect();
  });
  const withdraw = (reason: string) => {
    if (done) return;
    done = true;
    if (timer) clearTimeout(timer);
    sock?.destroy();
    void request({ op: "withdraw", id: req.id, reason });
  };
  return { answer, withdraw };
}

// --- the extension ------------------------------------------------------------------

export default function familiarRemote(pi: ExtensionAPI) {
  let lastInput = Date.now();
  let awayAfterS = 600;
  try { awayAfterS = awayAfterSeconds(fs.readFileSync(CONFIG, "utf8")); } catch { /* default */ }
  let locked = false;
  let tag = "pi";
  let cwd = process.cwd();
  let n = 0;
  let turnAsk: ReturnType<typeof phoneAsk> | undefined;
  const backListeners = new Set<() => void>();

  const pollLock = () => execFile("pgrep", ["-x", "hyprlock"], (err) => { locked = !err; });
  const lockTimer = setInterval(pollLock, 5000);
  lockTimer.unref?.();

  async function away(): Promise<string | null> {
    const st = await request({ op: "status" });
    return awayReason({ now: Date.now(), lastInput, awayAfterS, locked,
                        awaySince: typeof st?.away_since === "number" ? st.away_since : null });
  }

  function onInput() {
    lastInput = Date.now();
    turnAsk?.withdraw("the user typed at the terminal");
    turnAsk = undefined;
    for (const f of backListeners) f();
  }

  const id = (kind: string) => `${tag}/${kind}/${++n}-${crypto.randomBytes(3).toString("hex")}`;

  /** Race a terminal dialog with the phone; the phone joins once the user is away. */
  function race<T>(kind: string, title: string, options: string[],
                   local: (signal: AbortSignal) => Promise<T>,
                   fromPhone: (a: any) => T, outer?: AbortSignal): Promise<T> {
    const stop = new AbortController();
    outer?.addEventListener("abort", () => stop.abort(), { once: true });
    let phone: ReturnType<typeof phoneAsk> | undefined;
    let settled = false;
    return new Promise<T>((resolve) => {
      const finish = (v: T, by: string) => {
        if (settled) return;
        settled = true;
        clearInterval(late);
        if (by === "phone") stop.abort();
        else phone?.withdraw("answered at the terminal");
        resolve(v);
      };
      const join = async () => {
        if (phone || settled || !(await away())) return;
        phone = phoneAsk({ id: id(kind), session: tag, kind, title, options,
                           context: `interactive pi session ${tag}\ncwd ${cwd}` });
        phone.answer.then((a) => { if (!a?.cancelled) finish(fromPhone(a), "phone"); });
      };
      const late = setInterval(join, LATE_CHECK_MS);
      local(stop.signal).then((v) => finish(v, "terminal"));
      void join();
    });
  }

  function wrap(ui: any) {
    if (!ui || ui.__familiarRemote || typeof ui.select !== "function") return;
    const select = ui.select.bind(ui), confirm = ui.confirm.bind(ui), input = ui.input.bind(ui);
    ui.select = (title: string, options: string[], opts: any = {}) =>
      race("select", title, options, (s) => select(title, options, { ...opts, signal: s }),
           (a) => (options.includes(a.value) ? a.value : undefined), opts?.signal);
    ui.confirm = (title: string, message: string, opts: any = {}) =>
      race("confirm", `${title}\n${message ?? ""}`.trim(), [],
           (s) => confirm(title, message, { ...opts, signal: s }), (a) => Boolean(a.confirmed), opts?.signal);
    ui.input = (title: string, placeholder?: string, opts: any = {}) =>
      race("input", title, [], (s) => input(title, placeholder, { ...opts, signal: s }),
           (a) => (a.value ?? a.text ?? undefined), opts?.signal);
    ui.__familiarRemote = true;
    try { ui.onTerminalInput?.(() => { onInput(); return undefined; }); } catch { /* not a TUI */ }
  }

  /** The chain link: away, the phone answers a permission ask; present or back, defer. */
  async function authorize(details: any, _query: unknown, log: any) {
    const why = await away();
    if (!why) return { kind: "defer" as const };
    const ask = phoneAsk({ id: id("perm"), session: tag, kind: "select",
                           title: permissionTitle(details), options: permissionOptions(details),
                           context: `interactive pi session ${tag} (away: ${why})\ncwd ${cwd}\n` +
                                    JSON.stringify(details?.payload?.request ?? {}, null, 1) });
    let back: () => void = () => {};
    const returned = new Promise<null>((resolve) => { back = () => resolve(null); backListeners.add(back); });
    const answer = await Promise.race([ask.answer, returned]);
    backListeners.delete(back);
    if (answer === null) {
      ask.withdraw("the user is back at the terminal");
      log?.review?.("familiar_remote.defer", { requestId: details?.requestId, reason: "the user came back" });
      return { kind: "defer" as const };
    }
    const v = verdict(answer);
    log?.review?.(`familiar_remote.${v.kind}`, { requestId: details?.requestId, by: "phone",
                                                 waited_s: answer?.waited_s ?? null });
    return v;
  }

  let dispose: (() => void) | undefined;
  pi.events?.on?.("permissions:ready", (data: any) => {
    const sessionId = data?.sessionId;
    if (dispose || !sessionId) return;
    try {
      const map = (globalThis as any)[SERVICES_KEY];
      dispose = map?.get?.(sessionId)?.registerAuthorizer?.(LINK, authorize);
    } catch { /* a duplicate or no service: nothing registered, asks reach the terminal */ }
  });

  pi.on("session_start", async (_e: any, ctx: any) => {
    cwd = ctx?.cwd ?? cwd;
    const sid = String(ctx?.sessionManager?.getSessionId?.() ?? crypto.randomBytes(2).toString("hex"));
    tag = `${path.basename(cwd)}-${sid.replace(/[^a-z0-9]/gi, "").slice(-4)}`;
    if (ctx?.mode === "tui") wrap(ctx.ui);
  });
  pi.on("turn_start", async (_e: any, ctx: any) => {
    if (ctx?.mode === "tui") wrap(ctx.ui);       // the object can be replaced on reload
  });
  pi.on("agent_start", async () => { turnAsk?.withdraw("a new turn started"); turnAsk = undefined; });
  pi.on("agent_end", async (event: any, ctx: any) => {
    if (ctx?.mode !== "tui" || !(await away())) return;
    const last = [...(event?.messages ?? [])].reverse().find((m: any) => m?.role === "assistant");
    const content = last?.content;
    const text = typeof content === "string" ? content
      : (content ?? []).filter((c: any) => c?.type === "text").map((c: any) => c.text).join("");
    turnAsk = phoneAsk({ id: id("turn"), session: tag, kind: "input",
                        title: `waits for you\n${String(text).slice(-600)}`, options: [] });
    const mine = turnAsk;
    mine.answer.then((a) => {
      if (turnAsk !== mine || a?.cancelled) return;
      turnAsk = undefined;
      const reply = String(a?.value ?? a?.text ?? "").trim();
      if (reply) pi.sendUserMessage(reply);
    });
  });
  pi.on("session_shutdown", () => {
    dispose?.(); dispose = undefined;
    turnAsk?.withdraw("the session ended");
    clearInterval(lockTimer);
  });
}
