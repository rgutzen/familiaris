/**
 * audit.ts -- line 3 of item 8h: what can be said about the command without a
 * model, and what the gate itself knows.
 *
 * WHY A THIRD LINE. Line 1 is the requester's claim, line 2 an independent
 * reading. Both describe; neither audits. The gap was visible in the phone test
 * of 2026-10-24: `docker version --privileged` was described truthfully by both
 * lines and approved, and only afterwards did the model observe that the flag
 * means nothing there. A reader cannot be asked to be a linter; a rule engine
 * can.
 *
 * THREE SOURCES, in order of authority:
 *   1. RULE. The ask's `matchedPattern` (e.g. `*docker *--privileged*`) maps,
 *      through `bash_pattern_rules` in the compiled boundaries.json, to the rule
 *      that emitted it -- and that rule's `reason` and `instead` are the user's
 *      own sentences, written with the incident that caused them. No model, no
 *      copy of the text: the mapping is derived at compile time.
 *   2. FLOOR. Most asks are the package's shape floors, which carry no rule. Their
 *      audit is the honest one: what the wrapper hides, and what a static scan
 *      can still see.
 *   3. OPS. Whatever the source, the command is scanned for irreversible
 *      operations (delete, move, write, network, privilege, history) and the
 *      result is set against the claim. A command whose ops the claim does not
 *      mention is the divergence this whole item exists to surface.
 *
 * EVIDENCE, NOT A VERDICT. The line never says "safe" or "approve": a verdict in
 * a security prompt teaches the reader to click yes, and a wrong one is worse
 * than no line. It names operations, targets and the rule's own reasoning, and
 * stops there.
 *
 * COST. Pure string work over a command line, ~0 ms, no process, no model, no
 * network: the measured 0.4-4 s reading latency does not change. It reuses
 * `shared/judge.mjs`'s tokeniser and redirect regex rather than growing a second
 * shell parser, so a fix to one is a fix to both.
 */
import { REDIRECT, splitPosix } from "../shared/judge.mjs";

export const SECTION_MAX = 200;
export const REASON_MAX = 118;
export const INSTEAD_MAX = 62;

/** What a matched pattern means when the gate has no rule behind it. */
export const FLOORS: Record<string, string> = {
  "<indirection-bash-wrapper>":
    "a wrapper (sudo, env, timeout, xargs, find -exec) hides the command, so the gate cannot decide",
  "<unparsed-bash-subtree>":
    "the text could not be parsed (quotes, substitution or heredoc), so the gate cannot tell what runs",
  "<opaque-bash-wrapper>":
    "an evaluated string (bash -c, eval) builds the command at run time, so the gate cannot decide",
};

/** Operations worth naming, with the words that recognise them in a command. */
const OPERATIONS: [string, RegExp][] = [
  ["delete", /\b(rm|rmdir|shred|unlink|truncate)\b|git clean|git reset --hard|--delete\b|-delete\b/],
  ["move", /\b(mv|rename)\b/],
  ["write", /\b(tee|dd|cp|install|chmod|chown|ln)\b|sed\s+-i|perl\s+-[a-z]*i\b|git checkout --/],
  ["network", /\b(curl|wget|ncat|netcat|nc|ssh|scp|sftp|rsync|telnet)\b|\/dev\/tcp/],
  ["privilege", /\b(sudo|doas)\b|--privileged\b|--device\b|--cap-add\b|--pid[= ]host|--network[= ]host/],
  ["history", /git (push|rebase|filter-branch|filter-repo)|git commit --amend|git stash (drop|clear)/],
  ["install", /\b(pacman\s+-S|apt\s+install|dnf\s+install|pip\s+install|npm\s+(install|i)\b|uv\s+add)\b/],
];

/** The claim words that count as naming an operation. */
const CLAIM_WORDS: Record<string, RegExp> = {
  delete: /delet|remov|clean|wipe|discard|prune|drop/,
  move: /move|rename|relocat|mv\b/,
  write: /writ|sav|creat|append|edit|generat|install|patch|rewrit|sync/,
  network: /fetch|download|upload|request|http|curl|wget|ssh|remote|network|push|pull|clone|sync/,
  privilege: /privileg|root|sudo|escalat|capab|device/,
  history: /push|rebase|amend|histor|rewrit|force/,
  install: /install|upgrad|package|dependenc/,
};

export interface RuleHint {
  reason?: string;
  instead?: string;
  domain?: string;
  mode?: string;
  decision?: string;
}

export interface Audit {
  text: string;
  source: "rule" | "floor" | "ops" | "none";
  ops: string[];
  pattern: string | null;
  /** The rule's own `reason`, whole, for the log. */
  reason: string | null;
}

function firstSentence(s: string, max: number): string {
  const one = String(s ?? "").replace(/\s+/g, " ").trim();
  if (!one) return "";
  const head = one.split(/(?<=[.!?])\s+/)[0] || one;
  return head.length > max ? head.slice(0, max - 1).trimEnd() + "…" : head;
}

/** The irreversible operations this command line names, in a stable order. */
export function opsOf(command: string): string[] {
  const cmd = String(command ?? "");
  const found = new Set<string>();
  for (const [name, re] of OPERATIONS) if (re.test(cmd)) found.add(name);
  // A redirect is a write unless every target is one of the shell's own sinks:
  // the same judgement judge.mjs makes before it calls a command mutating.
  const tokens = splitPosix(cmd).tokens;
  for (const m of cmd.matchAll(REDIRECT)) {
    const target = (m[1] || "").replace(/^["']|["']$/g, "");
    if (target && !/^(&\d|\/dev\/(null|stdout|stdin|stderr)|-)$/.test(target)) {
      found.add("write");
      break;
    }
  }
  if (tokens.includes(">") || tokens.includes(">>")) found.add("write");
  return OPERATIONS.map(([name]) => name).filter((n) => found.has(n));
}

/** The ops the claim does not name at all: the divergence worth showing. */
export function unclaimed(ops: string[], claim: string): string[] {
  if (!claim) return [];
  return ops.filter((op) => !(CLAIM_WORDS[op]?.test(claim) ?? false));
}

function clause(ops: string[]): string {
  return ops.length ? `ops ${ops.join(", ")}` : "no write, delete or network visible";
}

/**
 * Line 3 for one ask. `rules` is `bash_pattern_rules` from the compiled
 * boundaries.json (pattern -> index into `all`), `all` its `rules` array; both
 * absent when the file could not be read, which degrades to the floor text.
 */
export function auditFor(input: {
  command: string;
  pattern: string | null;
  claim: string;
  rules?: Record<string, number> | null;
  all?: RuleHint[] | null;
}): Audit {
  const { command, pattern, claim } = input;
  const ops = opsOf(command);
  const missing = unclaimed(ops, claim);
  // Only a divergence is worth the characters: when the claim names every op,
  // saying so spends the line's room to tell the reader nothing.
  const tail = missing.length ? ` · the claim names none of: ${missing.join(", ")}` : "";

  const index = pattern && input.rules ? input.rules[pattern] : undefined;
  const rule = typeof index === "number" ? input.all?.[index] : undefined;
  if (rule) {
    const reason = firstSentence(rule.reason ?? "", REASON_MAX);
    const instead = firstSentence(rule.instead ?? "", INSTEAD_MAX);
    const body = [reason, instead ? `instead ${instead}` : ""].filter(Boolean).join(" · ");
    const text = truncate(`${body}${tail}`, SECTION_MAX);
    return { text, source: "rule", ops, pattern, reason: rule.reason ?? null };
  }
  if (pattern || ops.length) {
    const why = pattern && FLOORS[pattern]
      ? FLOORS[pattern]
      : pattern ? `the gate's ${pattern.replace(/[<>]/g, "")} floor fired` : "";
    const body = [clause(ops), why].filter(Boolean).join(" · ");
    return { text: truncate(`${body}${tail}`, SECTION_MAX), source: pattern ? "floor" : "ops",
             ops, pattern, reason: null };
  }
  return { text: "", source: "none", ops: [], pattern, reason: null };
}

function truncate(s: string, max: number): string {
  const one = s.replace(/\s+/g, " ").trim();
  return one.length > max ? one.slice(0, max - 1).trimEnd() + "…" : one;
}
