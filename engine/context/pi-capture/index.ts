/**
 * familiar-capture — Loop A for Pi. Mirrors the opencode plugin's `session.idle`
 * capture (06_SYSTEM/engine/boundaries/opencode-plugin/index.js): logs one
 * session-end line per session so a day spent in Pi counts as ACTIVE in the
 * ranking (`familiar context capture --harness=pi --event=session-end`).
 *
 * UNLIKE opencode, this DOES stage a transcript. Pi writes a real per-session
 * JSONL file (`ctx.sessionManager.getSessionFile()`), so the payload's
 * `transcript_path` points straight at it -- capture.py copies it verbatim,
 * same as Claude Code's SessionEnd. The line SHAPE differs from Claude
 * Code's (`type: "message"` envelopes, `message.role` nested, `toolCall`
 * blocks instead of `tool_use`); `engine/context/transcripts.py` `meta()` and
 * `reduce()` understand both shapes, so stage 1 (replay) needs no per-harness
 * branch of its own.
 *
 * Interception point: Pi's `session_shutdown` fires once per session close
 * (`reason`: quit/reload/new/resume/fork) — the nearest analogue to Claude
 * Code's SessionEnd and opencode's `session.idle`. Session id derived the
 * same way @loreai/pi does it (packages/pi/src/index.ts):
 * `sessionIDFor(ctx.sessionManager.getSessionFile())`.
 */
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import os from "node:os";

// Deliberately no import of `@earendil-works/pi-coding-agent`: this file
// lives OUTSIDE Pi's module tree (version-controlled in 06_SYSTEM, reached
// through a loader shim) — same split as familiar-guard. The `pi`/`ctx`
// shapes are used loosely instead of typed.
type ExtensionAPI = any;

// The root this extension needs. It cannot import lib/roots.py, so
// test_roots.py holds it to it instead.
const ENGINE = `${os.homedir()}/06_SYSTEM/engine`; // roots-twin: ENGINE
const CAPTURE_BIN = `${ENGINE}/familiar`;

function sessionIDFor(file: string | undefined): string {
  if (!file) return "unknown";
  return crypto.createHash("sha256").update(file).digest("hex").slice(0, 16);
}

const seenShutdown = new Set<string>();

export default function familiarCapture(pi: ExtensionAPI): void {
  pi.on("session_shutdown", async (_event: any, ctx: any) => {
    try {
      const sessionFile: string | undefined = ctx?.sessionManager?.getSessionFile?.();
      const sessionId = sessionIDFor(sessionFile);
      if (seenShutdown.has(sessionId)) return;
      seenShutdown.add(sessionId);
      const payload = JSON.stringify({
        session_id: sessionId,
        cwd: ctx?.cwd ?? process.cwd(),
        transcript_path: sessionFile ?? "",
      });
      // Detached and ignored: capture runs on the user's latency budget, and
      // a failure to log must never surface in, or block, session shutdown.
      const child = spawn(
        CAPTURE_BIN,
        ["context", "capture", "--harness=pi", "--event=session-end"],
        { stdio: ["pipe", "ignore", "ignore"], detached: true },
      );
      child.on("error", () => {});
      child.stdin.on("error", () => {});
      child.stdin.end(payload);
      child.unref();
    } catch {
      // never let capture break shutdown
    }
  });
}
