/**
 * pi-emitter -- item 8e's decision log: one line per permission decision.
 *
 * WHY. The ask census (8c, `familiar orchestration asks --replay`) read the
 * transcripts, and a transcript records an ask only when it could not be shown
 * (a child, a non-interactive run) or was denied. A prompt the user ANSWERED
 * leaves no trace there, and a delegation that asks halts the session until it
 * is answered -- so the census saw 1 event where the package's own review log
 * holds 709 asks (measured 2026-10-15). The decision has to be written where it
 * is made, and `pi-permission-system` already broadcasts it: this extension
 * only listens.
 *
 * THE HOOK, AND WHERE IT WAS FOUND (@gotgenes/pi-permission-system 40.2.0):
 *   `permissions:decision` on `pi.events` -- docs/cross-extension-api.md
 *   §"Decision Broadcasts": emitted "after every gate resolution", payload
 *   `PermissionDecisionEvent` = { requestId, surface, value, result
 *   ("allow"|"deny"), resolution, origin, agentName, matchedPattern,
 *   forwarding? }; channel constant in src/service/permission-events.ts. The
 *   broadcast is best-effort and carries no protocolVersion, so every field is
 *   read defensively and a missing one is written as null, never guessed.
 *   `session_start` -- the session id, from `ctx.sessionManager.getSessionId()`,
 *   the read the package's own src/session/session-identity.ts makes. It is the
 *   uuid in the session log's file name, which is how `asks` joins the two.
 *
 * ONE LINE, APPEND-ONLY, `<PAZRAS_DATA_DIR>/permission-decisions.jsonl`:
 *   ts, surface, value, decision, reason, session   -- the item's six fields
 *   rule      the winning rule's pattern (`matchedPattern`): the census's
 *             classifier -- a pattern the user wrote is class A, the package's
 *             own shape guards (`<indirection-bash-wrapper>`, ...) and no
 *             pattern are class B
 *   origin, agent, forwarded, request, cwd, child, value_len
 * `value` is cut to VALUE_MAX characters (a heredoc is a command too); `value_len`
 * keeps the original length so the cut is visible.
 *
 * EVERY decision is written, `policy_allow` included: the census needs the
 * denominator (how many gates resolved without anyone being asked), and a filter
 * here would be a judgement the reader cannot undo.
 *
 * ON IN CHILDREN, unlike the trigger: a pi-agent child (PI_OFFLINE=1) is exactly
 * where an ask cannot be answered and kills the work (`confirmation_unavailable`),
 * which is the number 8d is sized by. `child` records which kind of session it was.
 *
 * A write failure is swallowed: a log must never block a permission decision,
 * and the package already says its listeners cannot.
 *
 * Tested without Pi: `line` and `logPath` are pure and exported, and the factory
 * takes a stub `pi` -- engine/orchestration/tests/test_decision_log.py drives it
 * through node. Loaded through a dotfiles shim, `familiar-decisions/index.ts`.
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

export const CHANNEL = "permissions:decision";
export const LOG_NAME = "permission-decisions.jsonl";
export const VALUE_MAX = 300;

type Env = Record<string, string | undefined>;

/** Where the log lives: beside the other append-only records (`ping`, the eval rows). */
export function logPath(env: Env = process.env): string {
  const data = env.PAZRAS_DATA_DIR || join(homedir(), ".local/share/pazras"); // roots-twin: DATA_DEFAULT
  return join(data, LOG_NAME);
}

function str(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

/** One decision as the line the log keeps. Pure: the clock, the session and the
 * environment are arguments. */
export function line(raw: unknown, session: string | null, now: Date,
                     env: Env = process.env, cwd: string = process.cwd()): Record<string, unknown> {
  const e = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  const value = str(e.value);
  const fwd = (typeof e.forwarding === "object" && e.forwarding !== null)
    ? e.forwarding as Record<string, unknown> : null;
  return {
    ts: now.toISOString(),
    surface: str(e.surface),
    value: value === null ? null : value.slice(0, VALUE_MAX),
    decision: str(e.result),
    reason: str(e.resolution),
    session,
    rule: str(e.matchedPattern),
    origin: str(e.origin),
    agent: str(e.agentName),
    forwarded: fwd ? (str(fwd.requesterSessionId) ?? str(fwd.requesterAgentName) ?? "?") : null,
    request: str(e.requestId),
    cwd,
    child: env.PI_OFFLINE === "1",
    value_len: value === null ? null : value.length,
  };
}

export default function (pi: any) {
  let session: string | null = null;
  const path = logPath();
  pi.on("session_start", (_event: unknown, ctx: any) => {
    try {
      session = ctx?.sessionManager?.getSessionId?.() || null;
    } catch {
      session = null;
    }
  });
  pi.events?.on?.(CHANNEL, (raw: unknown) => {
    try {
      mkdirSync(dirname(path), { recursive: true });
      appendFileSync(path, JSON.stringify(line(raw, session, new Date())) + "\n");
    } catch {
      // A log never blocks a decision.
    }
  });
}
