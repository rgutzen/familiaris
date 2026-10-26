/**
 * judge.mjs — the one rule judge the JS/TS harnesses share.
 *
 * Three bash judges used to exist: guard.py (Claude Code, Python) and a copy
 * each in the opencode plugin and pi-guard, whose headers said of themselves
 * "KNOWN WEAKER THAN THE CLAUDE CODE GUARD" and "word-for-word the mutators".
 * Copying one regex three times copied its bugs three times, and the parity
 * corpus (fixtures/parity.json) found the copies had drifted: `\rm` passed the
 * JS judges and was caught in Python.
 *
 * This module is the second judge, not a third: opencode and pi both import it.
 * The Python one stays because a Python hook cannot import JavaScript; the two
 * are held equal by the corpus, which every judge runs.
 *
 * WHERE THE WORDS COME FROM. Nothing here names a mutating command, a push
 * verb or a tool's path field. Those are the VOCABULARY, compiled from
 * `config/boundaries/vocabulary.yaml` into `boundaries.json` by
 * `boundaries/compile.py` (dev/architecture 2c/2d). What stays in this file is
 * MECHANISM: how a command line is read.
 *
 * THE TOKENISER IS A POSIX SPLIT, matching Python's `shlex.split`, because the
 * corpus holds this judge to guard.py: single quotes, double quotes, backslash
 * escapes, and an unbalanced quote reported rather than guessed at (every
 * caller then fails closed, as guard.py does).
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const HOME = os.homedir();

// Heredoc bodies are DATA written somewhere else, not paths being opened.
export const HEREDOC = /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1[\s\S]*?^\t*\2$/gm;
// Any `>` counts, not only one after whitespace (`echo x>path`), and an arrow
// (`->`, `=>`) is not a redirect. Same expression as guard.py's REDIRECT.
export const REDIRECT = /(?<![-=])\d*>>?\s*(?!&)([^\s;&|<>()]+)/g;

/**
 * POSIX-style split, as `shlex.split` does it: whitespace separates, single
 * quotes are literal, double quotes allow \" and \\, and a backslash outside
 * quotes escapes the next character. `ok` is false when a quote is unbalanced
 * or the line ends on a backslash. Unlike `shlex.split`, a word-start `#`
 * comments out the line; guard.py's `_uncomment` is the twin.
 */
/** What every harness says when `commandHits` returns "unparsed". */
export const UNPARSED =
  "this command could not be parsed (an unbalanced quote or a trailing backslash), " +
  "so the wards fail closed; no path was matched. Balance the quote and run it again";

export function splitPosix(cmd) {
  const out = [];
  let cur = "";
  let cur_has = false;
  let quote = null;
  for (let i = 0; i < cmd.length; i++) {
    const ch = cmd[i];
    if (quote === "'") {
      if (ch === "'") quote = null;
      else { cur += ch; cur_has = true; }
      continue;
    }
    if (quote === '"') {
      if (ch === '"') { quote = null; continue; }
      if (ch === "\\" && i + 1 < cmd.length) {
        const next = cmd[i + 1];
        cur += next === '"' || next === "\\" || next === "$" || next === "`" ? next : "\\" + next;
        cur_has = true; i++; continue;
      }
      cur += ch; cur_has = true; continue;
    }
    // A `#` that starts a word opens a comment, as in bash. Its quotes do not
    // count (the apostrophe in "spec's" is not an open quote), but its words
    // are still tokens: where this split and bash disagree about a quote
    // (`$'\''`), the "comment" may be code, and dropping it would hide a path.
    if (ch === "#" && !cur_has) {
      let end = cmd.indexOf("\n", i);
      if (end === -1) end = cmd.length;
      for (const w of cmd.slice(i + 1, end).split(/\s+/)) {
        const t = w.replace(/['"]/g, "");
        if (t) out.push(t);
      }
      i = end - 1;
      continue;
    }
    if (ch === "'" || ch === '"') { quote = ch; cur_has = true; continue; }
    if (ch === "\\") {
      if (i + 1 >= cmd.length) return { tokens: [], ok: false };
      cur += cmd[i + 1]; cur_has = true; i++; continue;
    }
    if (/\s/.test(ch)) {
      if (cur_has) { out.push(cur); cur = ""; cur_has = false; }
      continue;
    }
    cur += ch; cur_has = true;
  }
  if (quote !== null) return { tokens: [], ok: false };
  if (cur_has) out.push(cur);
  return { tokens: out, ok: true };
}

function escapeRe(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A flag as a token: a long flag must be the whole token, a short one may lead
 *  a cluster (`-i` matches `-i.bak`). Same rule as guard.py's `_flag_re`. */
export function flagRe(flag) {
  const esc = escapeRe(flag);
  return flag.startsWith("--")
    ? `(?:^|[\\s;&|(])${esc}(?=$|[\\s;&|)])`
    : `(?:^|[\\s;&|(])${esc}`;
}

function requireList(v, what) {
  if (!Array.isArray(v)) throw new Error(`vocabulary: ${what} must be a list`);
  return v;
}

export class Judge {
  /** `cfg` is the compiled boundaries.json. Throws when the vocabulary is
   *  missing: a judge that silently enforces nothing is the failure this file
   *  exists to prevent. */
  constructor(cfg, { home = HOME } = {}) {
    this.cfg = cfg;
    this.home = home;
    const vocab = cfg && cfg.vocabulary;
    if (!vocab) throw new Error("compiled boundaries carry no vocabulary — run boundaries/compile.py");
    this.vocab = vocab;
    this.writes = new Set(requireList(vocab.shell.writes, "shell.writes"));
    // `delete` is its own operation (8i): the words that destroy, and the paths
    // where destroying is routine. Both come from the vocabulary, never here.
    this.deleteWords = new Set(vocab.shell.deletes || []);
    this.deleteSafe = vocab.shell.delete_safe || [];
    this.deleteWrappers = new Set(vocab.shell.delete_wrappers || []);
    this.deleteShells = new Set(vocab.shell.delete_shells || []);
    this.writesWithFlag = vocab.shell.writes_with_flag || {};
    this.gitPush = this._gitRe(vocab.shell.push.git);
    this.gitWrites = this._gitRe(vocab.shell.git_writes.git);
    this.escape = vocab.shell.host_escape;
    if (!this.escape) throw new Error("vocabulary: shell.host_escape is missing");
    this.engineWord = new RegExp("\\b(?:" + this.escape.engines.map(escapeRe).join("|") + ")\\b");
  }

  _gitRe(spec) {
    if (!spec) return null;
    const parts = [];
    const subs = spec.subcommands || [];
    if (subs.length) {
      parts.push("\\bgit\\b[^;&|]*\\b(?:" + subs.map(escapeRe).join("|") + ")\\b");
    }
    for (const [sub, flags] of Object.entries(spec.with_flag || {})) {
      for (const flag of requireList(flags, `shell.push.git.with_flag.${sub}`)) {
        parts.push(`\\bgit\\b[^;&|]*\\b${escapeRe(sub)}\\b[^;&|]*` + flagRe(flag));
      }
    }
    return parts.length ? new RegExp(parts.join("|")) : null;
  }

  /** The rules that apply to a call from a model class (`local`/`remote`). */
  rulesFor(klass) {
    return (this.cfg.rules || []).filter((r) => r.models === "all" || r.models === klass);
  }

  /** `{fields, ops}` for one of a harness's tools, or null. */
  toolPaths(harness, tool) {
    const spec = this.vocab.tools?.[harness]?.paths?.[tool];
    return spec ? { fields: spec.fields, ops: new Set(spec.ops) } : null;
  }

  expand(token) {
    let t = String(token).replaceAll("${HOME}", this.home).replaceAll("$HOME", this.home);
    if (t === "~") t = this.home;
    else if (t.startsWith("~/")) t = path.join(this.home, t.slice(2));
    if (path.isAbsolute(t)) return [path.normalize(t)];
    return [path.normalize(t)];
  }

  under(rulePath, target) {
    for (const key of ["abs", "real"]) {
      const base = rulePath[key];
      if (base && (target === base || target.startsWith(base.replace(/\/$/, "") + "/"))) return true;
    }
    return false;
  }

  /** The candidate absolute paths a token could mean. A relative name is
   *  resolvable from the cwd OR from $HOME (`ls 03_ZETTEL` from anywhere),
   *  which is what guard.py's `candidates()` does and the corpus tests. */
  candidates(token, cwd) {
    const t = this.expand(token)[0];
    if (path.isAbsolute(t)) return [t];
    return [path.normalize(path.join(cwd, t)), path.normalize(path.join(this.home, t))];
  }

  hitsPath(rule, value, cwd) {
    if (typeof value !== "string" || !value) return false;
    return this.candidates(value, cwd).some((c) => rule.paths.some((p) => this.under(p, c)));
  }

  spellings(p) {
    const out = [p.abs];
    if (p.real) out.push(p.real);
    if (p.abs.startsWith(this.home + "/")) {
      const rel = p.abs.slice(this.home.length + 1);
      out.push("~/" + rel, "$HOME/" + rel);
    }
    return out;
  }

  /** `true` if the command references a path the rule covers, `"unparsed"`
   *  if it cannot be split (truthy, so a caller that ignores the difference
   *  still fails closed; one that reads it says why instead of naming a path
   *  the command never touched). */
  commandHits(cmd, rule, cwd) {
    const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
    const { tokens, ok } = splitPosix(stripped);
    if (!ok) return "unparsed";                 // fail closed, as guard.py does
    for (const tok of tokens) if (this.hitsPath(rule, tok, cwd)) return true;
    for (const p of rule.paths) {
      for (const form of this.spellings(p)) {
        if (new RegExp(escapeRe(form) + "($|[/\\s'\";)&|])").test(stripped)) return true;
      }
    }
    return false;
  }

  /** Is this operand inside a path where destroying is routine? */
  safeTarget(candidate, cwd) {
    let p = String(candidate);
    if (p.startsWith("~")) p = p.replace(/^~/, os.homedir());
    if (!path.isAbsolute(p)) p = path.join(cwd, p);
    p = path.normalize(path.resolve(p));
    // A safe entry covers the path itself AND everything below it, so
    // `node_modules/.cache` is as routine as the cache. Every ancestor is
    // tested, which is how a glob entry matches at any depth.
    const parts = p.split("/");
    const ancestors = parts.map((_, i) => parts.slice(0, i + 1).join("/") || "/");
    for (const entry of this.deleteSafe) {
      const base = entry.replace(/\/$/, "");
      const glob = /[*?[]/.test(entry)
        ? new RegExp("^" + base.split("").map((c) => c === "*" ? ".*" : c === "?" ? "." : escapeRe(c)).join("") + "$")
        : null;
      for (const cand of ancestors) {
        if (glob ? glob.test(cand) : cand === base) return true;
      }
    }
    return false;
  }

  /** The delete or move in one command run, or null when it is all routine.
   *  Same algorithm as guard.py's `deletes_outside_safe`; the corpus holds the
   *  two equal. A DELETE is not a write: `mkdir` and `rm` cost different things. */
  deletesOutsideSafe(cmd, cwd) {
    if (!this.deleteWords.size) return "the vocabulary names no delete commands";
    const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
    const { tokens, ok } = splitPosix(stripped);
    if (!ok) {
      const hit = [...this.deleteWords].find((w) => new RegExp("\\b" + escapeRe(w) + "\\b").test(stripped));
      return hit ? `an unparseable command names \`${hit}\`` : null;
    }
    // splitPosix keeps `a;rm b` as `a;`, `rm`, `b`: a separator is an ending, not
    // a token of its own, so runs break where a token ends with one.
    const runs = [[]];
    for (const raw of tokens) {
      const t = raw.replace(/[;&|]+$/, "");
      if (t) runs[runs.length - 1].push(t);
      if (t !== raw || [";", "&&", "||", "|", "&"].includes(raw)) runs.push([]);
    }
    for (const run of runs) {
      let i = 0;
      while (i < run.length) {
        const word = path.basename(run[i]);
        if (this.deleteWrappers.has(word) || /^[A-Za-z_][A-Za-z0-9_]*=/.test(run[i])) { i++; continue; }
        break;
      }
      if (i >= run.length) continue;
      const word = path.basename(run[i]);
      if (this.deleteWords.has(word)) {
        const operands = run.slice(i + 1).filter((t) => !t.startsWith("-"));
        if (!operands.length) return "a delete with no visible target";
        for (const op of operands) {
          if (!this.safeTarget(op, cwd)) return `this command deletes or moves \`${op}\``;
        }
        continue;
      }
      if (this.deleteShells.has(word) && run.includes("-c")) {
        const text = run.slice(i + 1).join(" ");
        const named = [...this.deleteWords]
          .find((w) => new RegExp("\\b" + escapeRe(w) + "\\b").test(text));
        if (named) {
          return `a \`${word} -c\` string deletes (${named}), so the target is only known at run time`;
        }
      }
    }
    return null;
  }

  /** Does the command mutate at all? Consulted only for a `no-write` rule,
   *  after `commandHits` has established that it touches the path. */
  commandWrites(cmd) {
    const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
    const { tokens, ok } = splitPosix(stripped);
    if (!ok) return true;                       // fail closed
    if (tokens.some((t) => this.writes.has(path.basename(t)))) return true;
    for (const [word, flags] of Object.entries(this.writesWithFlag)) {
      for (const flag of flags) {
        if (new RegExp(`\\b${escapeRe(word)}\\b[^;&|]*` + flagRe(flag)).test(stripped)) return true;
      }
    }
    for (const re of [this.gitWrites, this.gitPush]) if (re && re.test(stripped)) return true;
    return false;
  }

  /** The redirect targets of a command, for the rule-local half of a write test. */
  redirectTargets(cmd) {
    const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
    const out = [];
    const re = new RegExp(REDIRECT.source, "g");
    let m;
    while ((m = re.exec(stripped)) !== null) out.push(m[1].replace(/^['"]|['"]$/g, ""));
    return out;
  }

  /** Why this command starts a container that reaches the host, or null.
   *  Same algorithm as guard.py's `Vocab.escapes`; the corpus holds them equal. */
  escapes(cmd, cwd, depth = 0) {
    const stripped = cmd.replace(HEREDOC, "<<STRIPPED");
    const { tokens: raw, ok } = splitPosix(stripped);
    if (!ok) {                                  // fail closed
      return this.engineWord.test(stripped) ? "an unparseable command names a container engine" : null;
    }
    const tokens = [];                          // null marks a separator
    for (const t of raw) {
      if ([";", "&&", "||", "|", "&"].includes(t)) { tokens.push(null); continue; }
      const s = t.replace(/[;&|]+$/, "");
      if (s) tokens.push(s);
      if (s !== t) tokens.push(null);
    }
    if (depth < 3) {
      for (const t of tokens) {
        if (t && /\s/.test(t) && this.engineWord.test(t)) {
          const why = this.escapes(t, cwd, depth + 1);
          if (why) return why;
        }
      }
    }
    const engines = new Set(this.escape.engines);
    const subs = new Set(this.escape.subcommands);
    for (let i = 0; i < tokens.length; i++) {
      if (!tokens[i] || !engines.has(path.basename(tokens[i]))) continue;
      let end = i + 1;
      while (end < tokens.length && tokens[end] !== null && !engines.has(path.basename(tokens[end]))) end++;
      const window = tokens.slice(i + 1, end);
      if (!window.some((t) => subs.has(t))) continue;
      const why = this._escapeWindow(window, cwd);
      if (why) return why;
    }
    return null;
  }

  _escapeWindow(window, cwd) {
    const he = this.escape;
    const value = (j, flag) => {
      const t = window[j];
      if (t === flag) return j + 1 < window.length ? window[j + 1] : null;
      if (t.startsWith(flag + "=")) return t.slice(flag.length + 1);
      if (!flag.startsWith("--") && t.startsWith(flag) && t.length > flag.length) return t.slice(flag.length);
      return null;
    };
    const norm = (v) => {
      v = v.toUpperCase().replaceAll(":", "=");
      return v.startsWith("CAP_") ? v.slice(4) : v;
    };
    for (let j = 0; j < window.length; j++) {
      const t = window[j];
      for (const flag of he.flags) {
        if (t === flag || t.startsWith(flag + "=")) return `the container is started with \`${flag}\``;
      }
      for (const [flag, allowed] of Object.entries(he.flag_values)) {
        const v = value(j, flag);
        if (v !== null && allowed.map(norm).includes(norm(v))) return `the container is started with \`${flag} ${v}\``;
      }
      for (const flag of he.mount_flags) {
        const v = value(j, flag);
        if (v === null) continue;
        const src = mountSource(v, flag === "--mount");
        if (src === null) continue;
        const hit = this._hostPath(src, cwd);
        if (hit) return `the container binds \`${src}\` from the host, which ${hit}`;
      }
    }
    return null;
  }

  _expandAt(token, cwd) {
    let t = String(token).replaceAll("${HOME}", this.home).replaceAll("$HOME", this.home);
    if (t === "~") t = this.home;
    else if (t.startsWith("~/")) t = path.join(this.home, t.slice(2));
    return path.normalize(path.resolve(cwd, t)).replace(/(.)\/$/, "$1");
  }

  _hostPath(src, cwd) {
    const p = this._expandAt(src, cwd);
    const under = (a, b) => a.startsWith(b.replace(/\/$/, "") + "/");
    for (const entry of this.escape.whole) {
      const e = this._expandAt(entry, cwd);
      if (p === e || p === "/" || under(e, p)) return `contains \`${entry}\``;
    }
    for (const entry of this.escape.beneath) {
      const e = this._expandAt(entry, cwd);
      if (p === e || under(p, e)) return `lies in \`${entry}\``;
    }
    return null;
  }

  pushes(cmd) {
    return !!(this.gitPush && this.gitPush.test(cmd.replace(HEREDOC, "<<STRIPPED")));
  }
}

/** The host path a mount flag binds, or null (a named volume, a non-bind). */
function mountSource(v, isMount) {
  if (isMount) {
    const kv = Object.fromEntries(v.split(",").filter((p) => p.includes("=")).map((p) => {
      const k = p.indexOf("=");
      return [p.slice(0, k), p.slice(k + 1)];
    }));
    if (kv.type !== "bind") return null;
    return kv.source || kv.src || null;
  }
  const src = v.split(":")[0];
  return "/~$.".includes(src[0] || "!") ? src : null;
}

/** Read the compiled rules, re-reading only when the file changes. */
export function configReader(rulesPath) {
  let cache = { mtime: -1, cfg: null };
  return function read() {
    try {
      const mtime = fs.statSync(rulesPath).mtimeMs;
      if (mtime !== cache.mtime) {
        cache = { mtime, cfg: JSON.parse(fs.readFileSync(rulesPath, "utf8")) };
      }
      return cache.cfg;
    } catch {
      return null;              // no compiled rules -> nothing to enforce
    }
  };
}
