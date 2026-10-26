/**
 * pi-deepen — a prompt improved before the model sees it (dev/prompt item 1g).
 *
 * `/deepen <dump>` runs `familiar orchestration bindings run role:deepen` as a CHILD
 * and, by default, REFILLS THE EDITOR with the rewritten prompt instead of sending
 * it: `{action:"handled"}` starts no turn, so nothing reaches the model until the
 * user presses Enter. That is the whole design (PLAN.md §D7) — the rewrite is
 * editable first, and the receipt costs the executor zero tokens.
 *
 * `/deepen!` sends it at once (`transform`), for a prompt whose shape is obvious.
 *
 * WHAT IS SHOWN, AND WHERE. The receipt (`field:`, `reject:`, `add:`, `raw:`,
 * `check:`, `kept:`, `self:`) goes to a widget above the editor, because it is for
 * the user and not for the model. The original dump is kept with `appendEntry`,
 * which pi documents as NOT sent to the LLM, so the record survives at zero tokens
 * and the transcript holds only the prompt the user accepted.
 *
 * A FAILED CHILD NEVER SWALLOWS THE DUMP: exit 4 (the reply broke its `rewrite`
 * contract) and any other failure return `continue`, so the user's own text goes
 * through unchanged with a warning.
 *
 * OFF BY DEFAULT, like `familiar-bindings`: PI_DEEPEN=1 enables it. A pi-agent
 * child (PI_OFFLINE=1) never loads it, so a bound child cannot deepen again.
 */
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

type ExtensionAPI = any;

const FAMILIAR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../familiar");
const TRIGGER = /^\s*\/deepen(!)?\s+([\s\S]+)$/;
// Seconds. `bindings run` defaults to 900, and the input handler has not returned
// while the child runs, so the editor is blocked for that whole time.
const TIMEOUT = "180";
const RECEIPT_LINES = 16;   // what a widget shows without scrolling; past it the tail is kept

function runDeepen(task: string, cwd: string, signal?: AbortSignal) {
  const args = ["orchestration", "bindings", "run", "role:deepen", task,
                "--cwd", cwd, "--timeout", TIMEOUT];
  return new Promise<{ code: number; out: string; err: string }>((resolve) => {
    // stdin "ignore": an inherited pipe never closes and `pi -p` below waits for EOF
    const child = spawn(FAMILIAR, args, { signal, stdio: ["ignore", "pipe", "pipe"] });
    let out = "", err = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("close", (code) => resolve({ code: code ?? 1, out, err }));
    child.on("error", (e) => resolve({ code: 1, out, err: String(e) }));
  });
}

/**
 * The child's reply, split into the prompt and the receipt.
 *
 * The receipt mirrors the Python checker's rule (`bindings._sections`): a label OWNS
 * the lines under it until the next label. A measured reply writes `` `reject:` `` as
 * a heading with the findings as bullets, and a lines-only reader showed the label and
 * threw the findings away — the one thing the user is meant to audit.
 */
export function split(stdout: string): { prompt: string; receipt: string } {
  const lines = stdout.split("\n");
  const cut = lines.findIndex((l) => l.startsWith("binding: "));
  const reply = (cut === -1 ? lines : lines.slice(0, cut)).join("\n").trim();
  const fenced = /```[^\n]*\n([\s\S]*?)```/.exec(reply);
  const prompt = (fenced ? fenced[1] : reply).trim();
  const outside = fenced ? reply.replace(fenced[0], "") : reply;

  const LABEL = /^`?\s*(field|reject|add|raw|check|kept|self)\s*`?\s*:\s*(.*)$/;
  const receipt: string[] = [];
  let keep = false;
  for (const raw of outside.split("\n")) {
    // The role writes its labels backtick-wrapped — `field:` systems, or a bare
    // `reject:` heading — so unwrap the LABEL TOKEN before matching, or the
    // backticks it wraps the label in leak into the rendered value.
    const line = raw.trim().replace(/^[-*\u2022]\s+/, "")
      .replace(/^`([a-z]+):`?\s*(.*?)`?$/, "$1: $2");
    const m = LABEL.exec(line);
    if (m) {
      keep = true;
      receipt.push(`${m[1]}: ${m[2]}`.trimEnd());
      continue;
    }
    if (keep && line) receipt.push(`  ${line}`);
    // A blank line does NOT end a section: like bindings._sections, a label owns
    // every line beneath it until the next label.
  }
  // Past the widget's height, keep the TAIL: `kept:` and `self:` are the last two
  // labels and they are the audit. Cutting at a fixed line count dropped exactly
  // them on a maximal reply (5 labels, their bullets, the kept lines, self).
  if (receipt.length <= RECEIPT_LINES) return { prompt, receipt: receipt.join("\n") };
  const head = 4, tail = RECEIPT_LINES - head - 1;      // one line for the marker
  return { prompt, receipt: [...receipt.slice(0, head),
    `  … ${receipt.length - head - tail} line(s) elided …`,
    ...receipt.slice(-tail)].join("\n") };
}

/**
 * The child's reply above the `binding:` line
 */
export default function (pi: ExtensionAPI) {
  if (process.env.PI_DEEPEN !== "1" || process.env.PI_OFFLINE === "1") return;

  pi.on("input", async (event: any, ctx: any) => {
    if (event.source === "extension") return { action: "continue" };
    const m = TRIGGER.exec(event.text ?? "");
    if (!m) return { action: "continue" };
    const [, immediate, task] = m;

    ctx.ui.setStatus("deepen", "deepening…");
    const r = await runDeepen(task, process.cwd(), ctx.signal);
    ctx.ui.setStatus("deepen", undefined);

    if (ctx.signal?.aborted) {
      ctx.ui.notify("deepen: cancelled — your prompt is unchanged", "info");
      return { action: "continue" };
    }

    if (r.code !== 0) {
      const why = r.code === 4 ? "the reply broke its `rewrite` contract" : `exit ${r.code}`;
      // The runner prints the problems AFTER its `binding:` line; the reply above
      // it can hold indented lines of its own, which are not the diagnosis.
      const lines = r.out.split("\n");
      const cut = lines.findIndex((l) => l.startsWith("binding: "));
      const detail = r.code === 4
        ? (cut === -1 ? [] : lines.slice(cut + 1)).filter((l) => l.startsWith("  ")).join(" ")
        : r.err.trim();
      ctx.ui.notify(`deepen: ${why} — your prompt is unchanged${detail ? ` (${detail.trim()})` : ""}`, "warning");
      return { action: "continue" };
    }

    const { prompt, receipt } = split(r.out);
    pi.appendEntry("deepen", { original: task, receipt, exit: r.code });

    // Print and RPC modes have no editor: `handled` there would swallow the prompt
    // into nothing, so a harness that cannot refill the editor gets the rewrite as
    // an immediate transform instead.
    const editable = typeof ctx.ui?.setEditorText === "function"
      && typeof ctx.ui?.setWidget === "function";
    if (immediate || !editable) return { action: "transform", text: prompt };

    ctx.ui.setEditorText(prompt);
    if (receipt) ctx.ui.setWidget("deepen", receipt.split("\n"), { placement: "aboveEditor" });
    return { action: "handled" };
  });
}
