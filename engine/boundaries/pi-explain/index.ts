/**
 * pi-explain -- item 8g: every ask carries two one-liners, `agent :` and
 * `independent :`.
 *
 * WHY. The dialog states what runs (`tool`, `rule`, `command`, `why`, `runs`,
 * `context`) and never states purpose; 667 of 715 recorded asks are the
 * package's own shape floors (8c), where the command looks arbitrary and the
 * missing fact is exactly why. The seam that would carry this upstream
 * (`PromptPayload.annotations`) has no producer or renderer in
 * `@gotgenes/pi-permission-system` 41.0.0 -- no `registerAnnotator`, every
 * builder sets `annotations: []` ([#654], ADR 0011 §8). Two public things do
 * exist: the `permissions:ui_prompt` broadcast and `ctx.ui.setWidget`, which
 * renders above the editor in the TUI **and** under RPC -- so this ships
 * without waiting for a release, and the phone path is one client change in
 * `engine/schedule/rpc.py` + `engine/relay` (see `annotate` there).
 *
 * LINE 1, `agent :` -- the requester's own words at the moment of the call, from
 * `ctx.sessionManager.getBranch()`, bound by a `toolCall` whose name is the
 * ask's tool and whose argument *string* equals or contains the ask's value
 * verbatim. Argument strings are compared, not `JSON.stringify(arguments)`: a
 * command with newlines is a heredoc, and JSON escapes them. Verified 2026-10-24
 * with a probe: at ask time the branch already holds the completed assistant
 * message carrying the pending call.
 *
 * THREE TIERS, because the first one is usually empty. Measured on the 06_SYSTEM
 * transcripts: 11 of 11 real asks logged `claim: null` -- the agent's tool-call
 * messages carry `thinking` blocks and no prose at all (147 assistant messages
 * in one session, one with text). So: (1) the text blocks of the carrying
 * message, labelled `agent :`; (2) failing that, the last sentence of its last
 * non-empty `thinking` block, labelled `agent (thinking) :` -- still the
 * requester's own words at that moment, and it is where an agent says what it is
 * about to try; (3) failing both, the nearest earlier assistant text, labelled
 * `agent (earlier) :`, because it is about an earlier step and saying otherwise
 * would be a lie. The row records which tier answered (`claim_source`).
 *
 * LINE 2, `independent :` -- one model call with **only the command string**: no
 * cwd, no rule, no agent name, no session, no line 1. Measured 2026-10-24 on ten
 * real commands from the ask log: `ollama/qwen2.5-coder:14b` names the concrete
 * target -- the address and port on a `/dev/tcp` ask -- in 3.3-4.4 s warm and
 * 14.2 s cold; the 4B answers in 0.4-1.5 s and summarises
 * intent better but dropped the address and the timeout on that same ask. The
 * 14B is the default because a security line's job is the concrete target (the
 * intent is line 1's); the 4B is the fallback. A pulled model is invisible until
 * it is in `~/.pi/agent/models.json` -- pi lists ollama models statically.
 *
 * INDEPENDENCE IS A SEPARATE INSTANCE, NOT A DIFFERENT BRAIN (user, 2026-10-24).
 * The call is a fresh `complete()` carrying one user message -- the command --
 * and our own system prompt: no session, no history, no claim, no rule. That is
 * what makes the reading independent, so the same model or the same provider is
 * allowed; what it is *not* is the requester's own context echoed back. The row
 * records the relationship (`same-model`, `same-provider`, `distinct-provider`)
 * so the log can say later whether it mattered, and no call is ever refused on
 * those grounds. Missing model, missing auth, a timeout (20 s, set by the
 * measured cold start) or a throw renders `unavailable (<reason>)` -- **never an
 * absent line**; a line that vanishes reads as agreement.
 *
 * NEVER BLOCKS THE ASK. `independent : reading…` goes up immediately, the
 * finished pair replaces it, and the widget clears on `permissions:decision` for
 * the same request. It cannot allow, deny, or suppress: it listens and writes.
 *
 * LOGGED. `<PAZRAS_DATA_DIR>/permission-explanations.jsonl`, one row per ask and
 * one `decision` row with the same request, so the question that sizes this is
 * answerable: does a disagreement between the two lines predict a denial, and
 * how often is the claim empty?
 *
 * BASH ONLY. 115 of the last 133 answered asks are bash, and a path or skill
 * ask's value is already the thing itself; this leaves those prompts untouched
 * rather than inventing a sentence for them.
 *
 * Tested without Pi: `explain`, `claimFrom`, `finish`, `widgetLines`, `line` and
 * `logPath` are pure or injected, and the factory takes a stub `pi`.
 * `engine/boundaries/test_pi_explain.py` drives it through node. Loaded through
 * a dotfiles shim, `~/.pi/agent/extensions/familiar-explain/index.ts`.
 */
import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { auditFor, type Audit, type RuleHint } from "./audit.ts";

export const UI_CHANNEL = "permissions:ui_prompt";
export const DECISION_CHANNEL = "permissions:decision";
export const LOG_NAME = "permission-explanations.jsonl";
export const WIDGET_KEY = "pi-explain";
export const DEFAULT_MODEL = "ollama/qwen2.5-coder:14b";
export const FALLBACK_MODEL = "ollama/qwen3:4b-instruct-2507-q4_K_M";
export const TIMEOUT_MS = 20_000;
export const VALUE_MAX = 300;
export const CLAIM_MAX = 220;
export const READING_MAX = 200;
export const WORDS_MAX = 15;
export const CONFIG_DIR = "pi-explain";
/** The compiled rule set, beside the judge the Pi guard already runs. */
export const RULES_TREE = dirname(dirname(dirname(dirname(fileURLToPath(import.meta.url)))));
export const RULES_PATH = join(RULES_TREE, "config/boundaries/boundaries.json"); // not-a-root: RULES_TREE is the tree root

/** The one prompt that keeps the reading literal, short, and free of judgement. */
export const SYSTEM_PROMPT = [
  "You are given one shell command and nothing else: no working directory, no session, no request.",
  `In at most ${WORDS_MAX} words, state the operation and any concrete target it names (host, address, path, branch, model).`,
  "No code, no backticks, no list, no judgement of whether it is safe, no recommendation.",
  "Do not resolve a path you cannot see.",
].join(" ");

type Env = Record<string, string | undefined>;

/** Where the log lives: beside the decision log it is analysed with. */
export function logPath(env: Env = process.env): string {
  const data = env.PAZRAS_DATA_DIR || join(homedir(), ".local/share/pazras"); // roots-twin: DATA_DEFAULT
  return join(data, LOG_NAME);
}

/** `<key>: <text>`: one labelled line per source, so a thought is not passed off
 * as a sentence the agent wrote to the reader. */
export function widgetLines(claim: string, reading: string, source = "text",
                            audit = ""): string[] {
  const label = source === "thinking" ? "agent (thinking) :"
    : source === "earlier" ? "agent (earlier) :" : "agent :";
  const lines = [`${label} ${claim || "(nothing stated)"}`, `independent : ${reading}`];
  if (audit) lines.push(`audit : ${audit}`);
  return lines;
}

export interface RuleSet {
  rules: RuleHint[];
  byPattern: Record<string, number>;
}

/** The compiled boundaries.json, read once; a missing file costs the rule tier. */
export function loadRules(path: string = RULES_PATH,
                          read: (p: string) => string = (p) => readFileSync(p, "utf8")): RuleSet | null {
  try {
    const doc = JSON.parse(read(path));
    const byPattern = (doc?.bash_pattern_rules ?? {}) as Record<string, number>;
    const rules = Array.isArray(doc?.rules) ? doc.rules as RuleHint[] : [];
    return { rules, byPattern };
  } catch {
    return null;
  }
}

function squash(s: string, max: number): string {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > max ? one.slice(0, max - 1).trimEnd() + "…" : one;
}

/** A budget in the unit that reads: `20 s`, `50 ms`. */
function duration(ms: number): string {
  return ms >= 1000 ? `${Math.round(ms / 1000)} s` : `${Math.round(ms)} ms`;
}

/**
 * The requester's claim, bound to the tool call the ask is about.
 *
 * Walks the branch backwards and stops at the newest assistant message that
 * carries a tool call. `bound` says whether the ask's value was found verbatim
 * in that call's arguments -- when it was not (a value rewritten by the gate, a
 * short value), the text is still the newest claim and the row records the
 * weaker binding rather than claiming a match it does not have.
 */
export function claimFrom(branch: unknown, toolName: string | null,
                          value: string): { claim: string; bound: boolean; source: string } {
  const raw = Array.isArray(branch) ? branch : ((branch as any)?.entries ?? []);
  const entries: any[] = Array.isArray(raw) ? raw : [];

  // The carrier: the newest assistant message whose call actually carries this
  // value -- a name-only match is kept as a fallback, because a gate may rewrite
  // the command it shows. Newest-to-oldest, and no drifting to earlier steps.
  let carrier = -1;
  let bound = false;
  let nameOnly = -1;
  let scanned = 0;
  for (let i = entries.length - 1; i >= 0 && scanned < 8; i--) {
    const m = entries[i]?.message ?? entries[i];
    if (!m || m.role !== "assistant" || !Array.isArray(m.content)) continue;
    const calls = m.content.filter((c: any) => c?.type === "toolCall");
    if (calls.length === 0) continue;
    scanned++;
    const named = calls.filter((c: any) => toolName === null || c?.name === toolName);
    if (named.length === 0) continue;
    if (nameOnly < 0) nameOnly = i;
    const hit = named.some((c: any) => Object.values(c?.arguments ?? {})
      .some((v: any) => typeof v === "string" && (v === value || v.includes(value))));
    if (hit) {
      carrier = i;
      bound = true;
      break;
    }
  }
  if (carrier < 0) carrier = nameOnly;
  const textOf = (m: any) => squash(m.content.filter((c: any) => c?.type === "text")
    .map((c: any) => String(c?.text ?? "")).join(" "), CLAIM_MAX);

  if (carrier >= 0) {
    const m = entries[carrier].message ?? entries[carrier];
    const said = textOf(m);
    if (said) return { claim: said, bound, source: "text" };
    const thoughts = m.content.filter((c: any) => c?.type === "thinking")
      .map((c: any) => String(c?.thinking ?? "")).filter((t: string) => t.trim());
    const last = thoughts[thoughts.length - 1];
    // A thought is only shown for the message that provably carries this value: a
    // thought from a rewritten or neighbouring call would be a guess dressed as
    // the agent's intent, which is worse than saying nothing.
    if (last && bound) {
      const sentence = tailSentence(last, CLAIM_MAX);
      if (sentence) return { claim: sentence, bound, source: "thinking" };
    }
  }
  const stop = carrier >= 0 ? carrier : entries.length;
  let seen = 0;
  for (let i = stop - 1; i >= 0 && seen < 8; i--) {
    const m = entries[i]?.message ?? entries[i];
    if (!m || m.role !== "assistant" || !Array.isArray(m.content)) continue;
    seen++;
    const said = textOf(m);
    if (said) return { claim: said, bound, source: "earlier" };
  }
  return { claim: "", bound, source: "none" };
}

/** The sentence a thought ends on: that is where an agent says what it will try. */
export function tailSentence(raw: string, max: number): string {
  const one = String(raw ?? "").replace(/\s+/g, " ").trim();
  if (!one) return "";
  const parts = one.split(/(?<=[.!?])\s+/).filter(Boolean);
  const tail = parts.length > 1 ? parts[parts.length - 1] : one;
  return squash(tail.length >= 20 ? tail : one.slice(-max), max);
}

/** One sentence, at most `WORDS_MAX` words, no code spans: the widget's half-line. */
export function finish(raw: unknown): string {
  let s = String(raw ?? "").replace(/[`*]/g, "").replace(/\s+/g, " ").trim();
  if (!s) return "";
  s = s.replace(/^(operation|reading|explanation|summary)\s*:\s*/i, "").replace(/^["']|["']$/g, "");
  const first = s.split(/(?<=[.!?])\s+/)[0] || s;
  const words = first.split(" ").filter(Boolean);
  const cut = words.length > WORDS_MAX ? words.slice(0, WORDS_MAX).join(" ") + "…" : first;
  return cut.length > READING_MAX ? cut.slice(0, READING_MAX - 1).trimEnd() + "…" : cut;
}

export interface Config {
  model: string;
  fallback: string;
  timeout_ms: number;
}

/** The default pair, a JSON file when present, and nothing else. */
export function loadConfig(env: Env = process.env, read: (p: string) => string = (p) => readFileSync(p, "utf8")): Config {
  const base: Config = { model: DEFAULT_MODEL, fallback: FALLBACK_MODEL, timeout_ms: TIMEOUT_MS };
  const home = env.HOME || homedir();
  const path = join(home, ".pi/agent/extensions", CONFIG_DIR, "config.json");
  try {
    const raw = JSON.parse(read(path));
    const pick = (k: keyof Config, d: number | string) => {
      const v = raw?.[k];
      return (typeof v === typeof d && String(v).length > 0) ? v as never : d as never;
    };
    return { model: pick("model", base.model), fallback: pick("fallback", base.fallback),
             timeout_ms: pick("timeout_ms", base.timeout_ms) };
  } catch {
    return base;
  }
}

/** One ask's log row. Pure: the clock and the environment are arguments. */
export function line(input: Record<string, unknown>, now: Date, env: Env = process.env): Record<string, unknown> {
  const value = typeof input.value === "string" ? input.value : null;
  return {
    ts: now.toISOString(),
    kind: "explain",
    request: input.request ?? null,
    session: input.session ?? null,
    surface: input.surface ?? null,
    value: value === null ? null : value.slice(0, VALUE_MAX),
    value_len: value === null ? null : value.length,
    claim: input.claim ?? null,
    claim_bound: input.claim_bound ?? false,
    claim_source: input.claim_source ?? null,
    independent: input.independent ?? null,
    audit: input.audit ?? null,
    audit_source: input.audit_source ?? null,
    audit_ops: input.audit_ops ?? null,
    independent_model: input.independent_model ?? null,
    independence: input.independence ?? null,
    latency_ms: input.latency_ms ?? null,
    rendered: input.rendered ?? false,
    agent: input.agent ?? null,
    forwarded: input.forwarded ?? null,
    child: env.PI_OFFLINE === "1",
  };
}

interface Deps {
  /** The `permissions:ui_prompt` payload. */
  event: any;
  /** The extension context: session branch, model registry, current model. */
  ctx: any;
  config: Config;
  /** Injected so a test needs no registry. */
  complete?: (model: any, request: any, opts: any) => Promise<any>;
  /** Already resolved by the caller, which needs it before the model answers. */
  claim?: { claim: string; bound: boolean; source: string };
  /** The compiled rule set, or null when boundaries.json could not be read. */
  rules?: RuleSet | null;
  /** Already resolved by the caller, so the placeholder can show it at once. */
  audit?: Audit;
}

/**
 * Independence is a separate instance carrying nothing but the command -- not a
 * different brain (user, 2026-10-24). So this classifies the relationship for the
 * log and never gates the call: the same model is allowed, as long as it reads the
 * command alone.
 */
export function independenceOf(reading: { provider?: string; id?: string } | undefined,
                              requester: { provider?: string; id?: string } | undefined): string {
  if (!requester?.provider) return "requester-unknown";
  if (reading?.provider !== requester.provider) return "distinct-provider";
  return reading?.id === requester.id ? "same-model" : "same-provider";
}

/**
 * Line 1 for this ask, synchronously: the factory needs it for the placeholder
 * that goes up before the model has answered.
 */
export function claimFor(ctx: any, event: any): { claim: string; bound: boolean; source: string } {
  const value = typeof event?.value === "string" ? event.value
    : (typeof event?.request?.value === "string" ? event.request.value : "");
  const toolName = typeof event?.request?.toolName === "string" ? event.request.toolName : null;
  const forwarded = event?.forwarding && typeof event.forwarding === "object" ? event.forwarding : null;
  let branch: unknown = null;
  try {
    branch = ctx?.sessionManager?.getBranch?.() ?? null;
  } catch {
    branch = null;
  }
  const found = claimFrom(branch, toolName, value);
  if (found.claim) return found;
  if (forwarded) {
    const who = forwarded.requesterAgentName || forwarded.requesterSessionId || "a subagent";
    return { claim: `(asked by ${who}; its words are not in this session)`, bound: false,
             source: "forwarded" };
  }
  return found;
}

export interface Explained {
  row: Record<string, unknown>;
  lines: string[];
  /** Cleared when the answer arrived before the widget was written. */
  requestId: string | null;
}

function textOf(response: any): string {
  const content = response?.content;
  if (typeof content === "string") return content;
  return (Array.isArray(content) ? content : [])
    .filter((c: any) => c?.type === "text").map((c: any) => String(c?.text ?? "")).join(" ");
}

/** The gate's own words for why this ask exists, when it has any. */
export function patternOf(event: any): string | null {
  const raw = event?.request?.matchedPattern ?? event?.matchedPattern;
  return typeof raw === "string" && raw ? raw : null;
}

/** Line 3 for this ask; pure and synchronous, so it can be shown immediately. */
export function auditForEvent(event: any, claimText: string, rules?: RuleSet | null): Audit {
  const value = typeof event?.value === "string" ? event.value : String(event?.request?.value ?? "");
  return auditFor({ command: value, pattern: patternOf(event), claim: claimText,
                    rules: rules?.byPattern ?? null, all: rules?.rules ?? null });
}

export async function explain({ event, ctx, config, complete, claim: givenClaim,
                               rules, audit: givenAudit }: Deps): Promise<Explained> {
  const requestId = typeof event?.requestId === "string" ? event.requestId : null;
  const surface = typeof event?.surface === "string" ? event.surface : null;
  const value = typeof event?.value === "string" ? event.value
    : (typeof event?.request?.value === "string" ? event.request.value : "");
  const forwarded = event?.forwarding && typeof event.forwarding === "object" ? event.forwarding : null;

  const claim = givenClaim ?? claimFor(ctx, event);
  const claimText = claim.claim;
  const audit = givenAudit ?? auditForEvent(event, claimText, rules);

  let reading = "";
  let modelName: string | null = null;
  let independence = "not-checked";
  let latency: number | null = null;
  const registry = ctx?.modelRegistry;
  const call = complete ?? registry?.complete?.bind(registry);

  const resolve = (ref: string) => {
    const slash = ref.indexOf("/");
    if (slash <= 0 || !registry?.find) return undefined;
    try {
      const found = registry.find(ref.slice(0, slash), ref.slice(slash + 1));
      return found && (registry.hasConfiguredAuth?.(found) ?? true) ? found : undefined;
    } catch {
      return undefined;
    }
  };

  if (!call) {
    reading = "unavailable (no model registry)";
  } else {
    const model = resolve(config.model) ?? resolve(config.fallback);
    if (!model) {
      reading = `unavailable (${config.model} not in the catalogue)`;
    } else {
      modelName = `${model.provider}/${model.id}`;
      independence = independenceOf(model, ctx?.model);
      {
        const ac = new AbortController();
        const cap = setTimeout(() => ac.abort(), config.timeout_ms ?? TIMEOUT_MS);
        const started = Date.now();
        try {
          const answer = await call(model,
            { systemPrompt: SYSTEM_PROMPT,
              messages: [{ role: "user", content: [{ type: "text", text: value }], timestamp: started }] },
            { signal: ac.signal });
          latency = Date.now() - started;
          reading = finish(textOf(answer)) || "unavailable (empty answer)";
        } catch (e: any) {
          latency = Date.now() - started;
          const why = ac.signal.aborted ? `timeout ${duration(config.timeout_ms ?? TIMEOUT_MS)}`
            : squash(String(e?.message ?? e ?? "error"), 60);
          reading = `unavailable (${why})`;
        } finally {
          clearTimeout(cap);
        }
      }
    }
  }

  const rendered = !!ctx?.hasUI;
  const row = line({
    request: requestId, session: ctx?.sessionManager?.getSessionId?.() ?? null,
    surface, value, claim: claimText || null, claim_bound: claim.bound,
    claim_source: claim.source,
    audit: audit.text || null, audit_source: audit.source, audit_ops: audit.ops.join(",") || null,
    independent: reading, independent_model: modelName, independence,
    latency_ms: latency, rendered, agent: event?.agentName ?? null,
    forwarded: forwarded ? (forwarded.requesterSessionId ?? forwarded.requesterAgentName ?? "?") : null,
  }, new Date());
  return { row, lines: widgetLines(claimText, reading, claim.source, audit.text), requestId };
}

export default function (pi: any) {
  let ctx: any = null;
  let rules: RuleSet | null = null;
  let config: Config = { model: DEFAULT_MODEL, fallback: FALLBACK_MODEL, timeout_ms: TIMEOUT_MS };
  let active: string | null = null;
  const path = logPath();

  const write = (row: Record<string, unknown>) => {
    try {
      mkdirSync(dirname(path), { recursive: true });
      appendFileSync(path, JSON.stringify(row) + "\n");
    } catch {
      // A log never blocks a permission decision.
    }
  };
  const show = (lines: string[] | undefined) => {
    try {
      if (ctx?.hasUI) ctx.ui.setWidget(WIDGET_KEY, lines);
    } catch {
      // An ask must appear even if the widget cannot.
    }
  };

  pi.on("session_start", (_event: unknown, c: any) => {
    ctx = c;
    config = loadConfig();
    rules = loadRules();
  });

  pi.events?.on?.(UI_CHANNEL, async (raw: unknown) => {
    const event = (raw ?? {}) as any;
    if (event.surface !== "bash") return;
    const requestId = typeof event.requestId === "string" ? event.requestId : null;
    active = requestId;
    const claim = claimFor(ctx, event);
    const audit = auditForEvent(event, claim.claim, rules);
    show(widgetLines(claim.claim, "reading…", claim.source, audit.text));
    const done = await explain({ event, ctx, config, claim, rules, audit });
    write(done.row);
    if (ctx?.hasUI && active === requestId) show(done.lines);
  });

  pi.events?.on?.(DECISION_CHANNEL, (raw: unknown) => {
    const event = (raw ?? {}) as any;
    const requestId = typeof event.requestId === "string" ? event.requestId : null;
    write({ ts: new Date().toISOString(), kind: "decision", request: requestId,
            session: ctx?.sessionManager?.getSessionId?.() ?? null,
            decision: event.result ?? null, resolution: event.resolution ?? null,
            rule: event.matchedPattern ?? null });
    if (requestId === active) {
      active = null;
      show(undefined);
    }
  });
}
