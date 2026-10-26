// pi-trigger's fire and its arm (14a): a fire either sends the hint or records a withheld entry.
// Run: node engine/orchestration/trigger/pi-trigger/test-trigger.mjs   (node >= 23 strips the types)
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import factory, { FAMILIAR, TRIGGER, withheld, setDraw, setRunner } from "./index.ts";

// The factory stands down inside a pi-agent child; a gate run there must still test it.
delete process.env.PI_OFFLINE;

let n = 0;
const t = (name, fn) => { fn(); n++; console.log(`ok    ${name}`); };

/** A stub pi: records hooks, messages and appended entries. */
function stub() {
  const hooks = {}, sent = [], appended = [];
  const pi = {
    on: (name, fn) => { hooks[name] = fn; },
    sendMessage: (m, o) => sent.push([m, o]),
    appendEntry: (type, data) => appended.push([type, data]),
  };
  factory(pi);
  return { hooks, sent, appended };
}

/** One user turn that crosses both floors at its sixth read. */
function crossTurn({ hooks }) {
  hooks.input({ source: "interactive" });
  const text = "x".repeat(Math.ceil(TRIGGER.minBytes / TRIGGER.minFiles) + 1);
  for (let i = 0; i < TRIGGER.minFiles; i++) {
    hooks.tool_call({ toolName: "read", input: { path: `f${i}.md` } });
    hooks.tool_result({ content: [{ type: "text", text }] });
  }
}

t("the share is the ruled third, and the draw decides the arm", () => {
  assert.equal(TRIGGER.withhold, 0.33);
  assert.equal(withheld(0.0), true);
  assert.equal(withheld(0.329), true);
  assert.equal(withheld(0.33), false);
  assert.equal(withheld(0.5, 0), false);
});

t("a nudged fire sends one hint and appends nothing", () => {
  setDraw(() => 0.9);
  const s = stub();
  crossTurn(s);
  assert.equal(s.sent.length, 1);
  assert.equal(s.sent[0][0].customType, "explore-trigger");
  assert.deepEqual(s.sent[0][1], { triggerTurn: false });
  assert.equal(s.appended.length, 0);
});

t("a withheld fire sends nothing and records the fire with its details", () => {
  setDraw(() => 0.1);
  const s = stub();
  crossTurn(s);
  assert.equal(s.sent.length, 0);
  assert.equal(s.appended.length, 1);
  const [type, data] = s.appended[0];
  assert.equal(type, "explore-trigger-withheld");
  assert.equal(data.files, TRIGGER.minFiles);
  assert.ok(data.bytes >= TRIGGER.minBytes);
  assert.equal(data.withhold, 0.33);
});

t("one fire per turn, whichever the arm", () => {
  setDraw(() => 0.1);
  const s = stub();
  crossTurn(s);
  s.hooks.tool_result({ content: [{ type: "text", text: "more" }] });
  assert.equal(s.appended.length + s.sent.length, 1);
});

// The session-end close (12a / 15b): a log pi never wrote -- an empty session --
// is skipped quietly; a real log runs `delegations --write --parent <file>`.

/** A session log in its own temp dir, removed once `body` returns. */
function withLog(body) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-trigger-test-"));
  const file = path.join(dir, "session.jsonl");
  fs.writeFileSync(file, "");
  try {
    body(file);
    return file;
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** What the hook printed to stderr while `body` ran. */
function errorsOf(body) {
  const errors = [], saved = console.error;
  console.error = (m) => errors.push(m);
  try {
    body();
  } finally {
    console.error = saved;
  }
  return errors;
}

/** The shutdown handler's `ctx` for a session whose file is `file`. */
const ctx = (file) => ({ sessionManager: { getSessionFile: () => file } });

t("an empty session's close spawns nothing and stays silent", () => {
  const s = stub();
  const calls = [];
  setRunner((command, args) => calls.push([command, args]));
  let errors;
  try {
    errors = errorsOf(() => s.hooks.session_shutdown({}, ctx("/no/such/log.jsonl")));
  } finally {
    setRunner(null);
  }
  assert.deepEqual(calls, []);
  assert.deepEqual(errors, []);
});

t("a session with a log runs `delegations --write --parent <file>`", () => {
  const s = stub();
  const calls = [];
  setRunner((command, args) => calls.push([command, args]));
  let file;
  try {
    file = withLog((f) => s.hooks.session_shutdown({}, ctx(f)));
  } finally {
    setRunner(null);
  }
  assert.deepEqual(calls,
    [[FAMILIAR, ["orchestration", "delegations", "--write", "--parent", file]]]);
});

t("a failed close is reported, never thrown", () => {
  const s = stub();
  setRunner(() => { throw new Error("boom"); });
  let errors;
  try {
    errors = errorsOf(() => withLog((f) => s.hooks.session_shutdown({}, ctx(f))));
  } finally {
    setRunner(null);
  }
  assert.deepEqual(errors, ["familiar-trigger: delegation log not closed: boom"]);
});

t("an ephemeral session names no file, so nothing spawns", () => {
  const s = stub();
  const calls = [];
  setRunner((command, args) => calls.push([command, args]));
  try {
    s.hooks.session_shutdown({}, ctx(""));
    s.hooks.session_shutdown({}, {});            // no sessionManager at all
  } finally {
    setRunner(null);
  }
  assert.deepEqual(calls, []);
});

setDraw(Math.random);
console.log(`${n} passed`);
