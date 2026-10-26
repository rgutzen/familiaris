/**
 * pi-asks -- item 8d's first half: the delegation surfaces, decided by RULE.
 *
 * WHAT ASKS, MEASURED 2026-10-15. A delegation does not ask because it is a
 * delegation: `"*": "allow"` covers `pi-agent` and `familiar orchestration
 * bindings run`, and a `bound_*` tool or a `/bound-*` command spawns its child
 * from node, outside the bash gate altogether. Every delegation ask in the
 * package's review log (2026-09-05 to 2026-10-15) was raised by the WRAPPER
 * around the call -- `time pi-agent ...`, `cd ... && ... ; echo rc=$?`, a
 * backgrounded block -- which pi-permission-system floors to `ask` whatever
 * the rules say (docs/configuration.md §Fail-closed behavior: "An `allow` is
 * clamped to `ask`"). So a declared `"pi-agent *": "allow"` would change
 * nothing; the floor is lifted only by a chain link that sees the unit the
 * package unwrapped (`payload.request.executedUnit`) and recognises it.
 *
 * THE LINK, `familiar-delegations`, grants exactly this and defers on the rest:
 *   - the gate surface is `bash`,
 *   - the ask came from an INDIRECTION floor or a partial parse
 *     (`<indirection-bash-wrapper>`, `<unparsed-bash-subtree>`) -- never from a
 *     rule the user wrote (class A), and never from `<opaque-bash-wrapper>`
 *     (`bash -c '...'`, `eval`: the inner program is not parsed, so nothing
 *     here could know what runs),
 *   - every statement of the unwrapped unit is a delegation (`DELEGATIONS`) or
 *     an inert companion (`cd <dir>`, `echo ...`, `wait`, `true`, or a reader a
 *     pipe ends in: `tail`, `head`, `wc`, `grep`), and the unit
 *     carries no command substitution (`$(`, a backtick) and no process
 *     substitution.
 * A redirect is allowed: its target is still gated by the path surfaces, which
 * this link never sees and the chain owner caps anyway (an `allow` on a `path`
 * or `external_directory` family is downgraded to `defer`).
 *
 * GRANTS NOTHING UNTIL NAMED. Registration alone gives a link no authority
 * (configuration.md §Authorizer chain, invariant 3): the operator lists
 * `familiar-delegations` in `authorizerChain`. A missing name is skipped
 * fail-safe, so removing this extension means MORE prompting, never less.
 *
 * EVERY RULING IS LOGGED to the package's own review log through the injected
 * `AuthorizerLog` (`familiar_delegations.allow` / `.defer`, with the reason),
 * and the decision itself reaches 8e's decision log as `authorizer_allowed`.
 *
 * NOT HERE: judging the residue with Jev (8d's second half). It needs this
 * link's numbers first: what the floors ask that is NOT a delegation.
 */

export const LINK = "familiar-delegations";
export const FLOORS = ["<indirection-bash-wrapper>", "<unparsed-bash-subtree>"];

/** argv prefixes (after the basename of argv[0]) that are a delegation. */
export const DELEGATIONS: readonly (readonly string[])[] = [
  ["pi-agent"],
  ["familiar", "orchestration", "bindings", "run"],
  ["familiar", "orchestration", "bindings", "--resolve"],
];
// Companions that run nothing of their own: `cd`, a report, a wait, and the
// readers a pipe may end in. `sh`, `xargs`, `tee` are not here.
const INERT = ["cd", "echo", "wait", "true", "tail", "head", "wc", "grep"];
// `&` ends a statement (background) unless it is part of a redirect (`2>&1`, `&>`).
const SPLIT = /\s*(?:&&|\|\||\||;|\n|(?<![<>])&(?![>&]))\s*/;

function words(statement: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quote = "";
  for (const ch of statement) {
    if (quote) { if (ch === quote) quote = ""; else cur += ch; continue; }
    if (ch === '"' || ch === "'") { quote = ch; continue; }
    if (ch === " " || ch === "\t") { if (cur) { out.push(cur); cur = ""; } continue; }
    cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

/** The statement's command, its leading env assignments and redirects dropped. */
function argv(statement: string): string[] {
  const w = words(statement).filter((t) => !/^\d*[<>]/.test(t));
  while (w.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(w[0])) w.shift();
  return w;
}

export function isDelegation(statement: string): boolean {
  const a = argv(statement);
  if (!a.length) return false;
  const head = [a[0].split("/").pop() ?? "", ...a.slice(1)];
  return DELEGATIONS.some((p) => p.every((word, i) => head[i] === word));
}

/** Null when the link should allow; otherwise the reason it defers. */
export function deferReason(surface: unknown, pattern: unknown, unit: unknown): string | null {
  if (surface !== "bash") return "not the bash surface";
  if (typeof pattern !== "string" || !FLOORS.includes(pattern)) {
    return pattern === "<opaque-bash-wrapper>" ? "an opaque wrapper: the inner program is not parsed"
      : "a rule asked (class A), or no floor";
  }
  if (typeof unit !== "string" || !unit.trim()) return "no executed unit";
  if (/\$\(|`|<\(|>\(/.test(unit)) return "a command or process substitution";
  const statements = unit.split(SPLIT).map((s) => s.trim()).filter(Boolean);
  if (!statements.some(isDelegation)) return "no delegation in the unit";
  const other = statements.find((s) => !isDelegation(s) && !INERT.includes(argv(s)[0] ?? ""));
  return other ? `a statement that is not a delegation: ${other.slice(0, 80)}` : null;
}

export async function authorize(details: any, _query: unknown, log: any) {
  const r = details?.payload?.request ?? {};
  const why = deferReason(r.surface, r.matchedPattern, r.executedUnit ?? details?.command);
  const facts = { requestId: details?.requestId, pattern: r.matchedPattern ?? null,
                  unit: String(r.executedUnit ?? details?.command ?? "").slice(0, 300) };
  if (why === null) {
    log?.review?.("familiar_delegations.allow", { ...facts, reason: "a delegation this system owns" });
    return { kind: "allow" as const };
  }
  log?.debug?.("familiar_delegations.defer", { ...facts, reason: why });
  return { kind: "defer" as const };
}

/** The package's process-global service map (src/service.ts, `SESSION_SERVICES_KEY`).
 * Read directly rather than through `import("@gotgenes/pi-permission-system")`,
 * which cannot resolve from this file: the package is installed under
 * ~/.pi/agent/npm/, and this source lives in 06_SYSTEM. The docs' own
 * explanation (cross-extension-api.md §How It Works) is that the accessor reads
 * exactly this slot. */
export const SERVICES_KEY = Symbol.for("@gotgenes/pi-permission-system:session-services");

export function service(sessionId: string): any {
  const map = (globalThis as any)[SERVICES_KEY];
  return typeof map?.get === "function" ? map.get(sessionId) : undefined;
}

export default function (pi: any) {
  let dispose: (() => void) | undefined;
  pi.events?.on?.("permissions:ready", (data: any) => {
    const sessionId = data?.sessionId;
    if (dispose || !sessionId) return;           // ready may repeat: register once
    try {
      dispose = service(sessionId)?.registerAuthorizer?.(LINK, authorize);
    } catch {
      // A duplicate or a missing service: nothing registered, the ask reaches the user.
    }
  });
  pi.on?.("session_shutdown", () => { dispose?.(); dispose = undefined; });
}
