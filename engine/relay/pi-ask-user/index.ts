/**
 * pi-ask-user -- the agent's way to ask the user a question and wait (dev/remote R2b).
 *
 * WHY A TOOL. A scheduled session used to be told "record the question, do not
 * wait": nobody was there to answer. With the relay, someone is -- on the phone,
 * maybe hours later. `ask_user` calls pi's own dialogs (`ui.select` with options,
 * `ui.input` without), so the SAME call is a terminal dialog in an interactive
 * session and an `extension_ui_request` under `--mode rpc`, which the scheduler's
 * driver (engine/schedule/rpc.py) forwards to the relay. Nothing here knows about
 * Telegram.
 *
 * NO UI, NO ANSWER. Under `pi -p` there is no dialog; the tool says so instead of
 * inventing an answer, and the model is told to record the question.
 *
 * LOADED BY FLAG for scheduled runs (`pi --mode rpc -e <this file>`), so it
 * reaches no interactive session until a loader shim is installed (R3b's step).
 */

// No import of `@earendil-works/pi-coding-agent` or `typebox`, for pi-guard's
// reason: this file lives outside Pi's module tree. The parameters are written
// as the JSON Schema TypeBox would produce.
type ExtensionAPI = any;

const PARAMETERS = {
  type: "object",
  properties: {
    question: {
      type: "string",
      description: "The question, self-contained: it may be read hours later, on a phone.",
    },
    options: {
      type: "array",
      items: { type: "string" },
      description: "Up to 6 short answers. Omit for a free-text answer.",
    },
  },
  required: ["question"],
};

function text(t: string, details: Record<string, unknown>) {
  return { content: [{ type: "text", text: t }], details };
}

export default function askUser(pi: ExtensionAPI) {
  pi.registerTool({
    name: "ask_user",
    label: "Ask the user",
    description:
      "Ask the user a question and wait. Use it when a decision belongs to the user. " +
      "The answer may take hours; work on what does not depend on it meanwhile.",
    promptSnippet: "Ask the user a decision question and wait for the answer",
    parameters: PARAMETERS,
    executionMode: "sequential",

    async execute(_id: string, params: any, _signal: unknown, _onUpdate: unknown, ctx: any) {
      const question = String(params?.question ?? "").trim();
      const options: string[] = Array.isArray(params?.options)
        ? params.options.map((o: unknown) => String(o)).filter((o: string) => o).slice(0, 6)
        : [];
      if (!question) {
        throw new Error("ask_user needs a question");
      }
      if (!ctx?.hasUI) {
        return text(
          "No user can be asked in this mode (no UI). Record the question where the user will read it, and continue with what does not depend on it.",
          { question, options, answer: null },
        );
      }
      const title = `The agent asks:\n${question}`;
      // A select's free-text reply arrives as a cancel at the driver unless an option
      // offers it; "Other (reply in words)" makes a worded answer reachable both on
      // the phone and in the terminal (a follow-up input asks for the words).
      if (options.length) {
        const other = "Other (reply in words)";
        const picked = await ctx.ui.select(title, [...options, other]);
        if (picked === undefined) {
          return text("The user dismissed the question without answering.", { question, options, answer: null });
        }
        if (picked !== other) {
          return text(`The user answered: ${picked}`, { question, options, answer: picked });
        }
      }
      const words = await ctx.ui.input(options.length ? `${question}\n(your answer, in words)` : title);
      if (words === undefined || String(words).trim() === "") {
        return text("The user dismissed the question without answering.", { question, options, answer: null });
      }
      return text(`The user answered: ${words}`, { question, options, answer: String(words) });
    },
  });
}
