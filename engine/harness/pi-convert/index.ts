/**
 * pi-convert -- orchestration item 10b: `read` on a document returns markdown.
 *
 * WHY. pi's `read` returns raw bytes for a `.docx` (a ZIP) or a `.pdf`, so no
 * agent, parent or `explore` child, can cite one. This hook replaces a
 * SUCCESSFUL `read` of a document with the document converted to markdown.
 * Converting needs no judgement, so it is a hook under the tool, not a role.
 *
 * WHY `tool_result`, NOT `tool_call`. Rewriting the path at `tool_call` would
 * make the permission check see the cache path, unless this extension loaded
 * after `pi-permission-system`, and pi documents no load order between a
 * package and an extension directory. At `tool_result` the guard has already
 * ruled on the ORIGINAL path: a blocked or failed `read` arrives with
 * `isError` and is left alone.
 *
 * CITABLE. The markdown is cached as a real file, named by the sha256 of the
 * document's bytes, and the result's first line names it. The line numbers of
 * the returned window are that file's line numbers, so a `ref+quote` citation
 * of `<cache>:<line>` verifies unchanged. Same bytes, same file: a document is
 * converted once.
 *
 * BACKENDS, measured in dev/orchestration/2026-10-20-pdf-convert.md: docling
 * for `.pdf` (headings, tables, OCR of scans; 7-21 s per paper on this CPU),
 * markitdown for the office formats (under 1 s). Both are uv tools on PATH.
 */
import { execFile } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// No import of `@earendil-works/pi-coding-agent`, for pi-guard's reason: this
// file lives outside Pi's module tree, reached through a loader shim.
type ExtensionAPI = any;

const HOME = os.homedir();
export const CACHE = path.join(process.env.XDG_CACHE_HOME || path.join(HOME, ".cache"), "pazras/convert");

// pi's own `read` window, so a converted read pages the way a text read does.
export const MAX_LINES = 2000;
export const MAX_BYTES = 50 * 1024;
const TIMEOUT_MS = 300_000; // docling's first run downloads its models: 47 s measured

/** argv for one conversion: write `src` as markdown to the file `out`. */
type Backend = { name: string; argv: (src: string, out: string) => [string, string[]] };

const MARKITDOWN: Backend = {
  name: "markitdown",
  argv: (src, out) => ["markitdown", [src, "-o", out]],
};
const DOCLING: Backend = {
  name: "docling",
  // docling names its output `<stem>.md` inside a directory; `convert` moves it.
  argv: (src, out) => ["docling", [src, "--to", "md", "--image-export-mode", "placeholder", "--output", out]],
};

export const BACKENDS: Record<string, Backend> = {
  ".pdf": DOCLING,
  ".docx": MARKITDOWN,
  ".pptx": MARKITDOWN,
  ".xlsx": MARKITDOWN,
  ".xls": MARKITDOWN,
  ".epub": MARKITDOWN,
};

export type Run = (cmd: string, args: string[]) => Promise<void>;

const execRun: Run = (cmd, args) =>
  new Promise((resolve, reject) =>
    execFile(cmd, args, { timeout: TIMEOUT_MS, maxBuffer: 16 * 1024 * 1024 }, (err, _out, stderr) =>
      err ? reject(new Error(`${cmd} failed: ${String(stderr || err.message).trim().split("\n").slice(-3).join(" ")}`)) : resolve()));

/** The document `read` was asked for, as an absolute path; pi strips a leading `@`. */
export function resolvePath(p: string, cwd: string): string {
  let s = p.startsWith("@") ? p.slice(1) : p;
  if (s === "~" || s.startsWith("~/")) s = path.join(HOME, s.slice(1));
  return path.resolve(cwd, s);
}

export function backendFor(file: string): Backend | undefined {
  return BACKENDS[path.extname(file).toLowerCase()];
}

/** Convert `file` once; return the cached markdown's path. */
export async function convert(file: string, run: Run = execRun, cacheDir: string = CACHE): Promise<string> {
  const backend = backendFor(file);
  if (!backend) throw new Error(`no backend for ${path.extname(file)}`);
  const hash = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex").slice(0, 16);
  const cached = path.join(cacheDir, `${hash}.md`);
  if (fs.existsSync(cached)) return cached;

  fs.mkdirSync(cacheDir, { recursive: true });
  const work = fs.mkdtempSync(path.join(cacheDir, ".work-"));
  try {
    const out = backend === DOCLING ? work : path.join(work, "out.md");
    const [cmd, args] = backend.argv(file, out);
    await run(cmd, args);
    const produced = backend === DOCLING ? path.join(work, `${path.parse(file).name}.md`) : out;
    if (!fs.existsSync(produced)) throw new Error(`${backend.name} wrote no markdown`);
    if (!fs.readFileSync(produced, "utf8").trim()) throw new Error(`${backend.name} found no text`);
    fs.renameSync(produced, cached); // atomic: a reader never sees half a file
    return cached;
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
}

/** The window `read` would show: lines `offset..` (1-indexed), capped like pi's. */
export function window(text: string, offset?: number, limit?: number): string {
  const lines = text.split("\n");
  if (lines.at(-1) === "") lines.pop();
  const start = Math.max(1, offset ?? 1);
  const end = Math.min(lines.length, start - 1 + Math.min(limit ?? MAX_LINES, MAX_LINES));
  const shown: string[] = [];
  let bytes = 0;
  for (let i = start; i <= end; i++) {
    bytes += Buffer.byteLength(lines[i - 1]) + 1;
    if (bytes > MAX_BYTES && shown.length) break;
    shown.push(lines[i - 1]);
  }
  const next = start + shown.length;
  const rest = lines.length - next + 1;
  if (rest > 0) shown.push("", `[${rest} more lines in file. Use offset=${next} to continue.]`);
  return shown.join("\n");
}

export default function piConvert(pi: ExtensionAPI): void {
  pi.on("tool_result", async (event: any, ctx: any) => {
    if (event.toolName !== "read" || event.isError) return;
    const input = event.input ?? {};
    if (typeof input.path !== "string") return;
    const file = resolvePath(input.path, ctx?.cwd || process.cwd());
    const backend = backendFor(file);
    if (!backend) return;
    try {
      const cached = await convert(file);
      const head = `[${input.path} converted to markdown by ${backend.name}. Cite lines as ${cached}:<line>; the line numbers below are that file's.]`;
      return { content: [{ type: "text", text: `${head}\n\n${window(fs.readFileSync(cached, "utf8"), input.offset, input.limit)}` }] };
    } catch (err: any) {
      // The raw bytes are useless to a model, so a failure replaces them too.
      return { content: [{ type: "text", text: `[${input.path}: conversion failed: ${err?.message ?? err}]` }], isError: true };
    }
  });
}
