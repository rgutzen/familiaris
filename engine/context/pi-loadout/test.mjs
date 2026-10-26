/**
 * Regression suite for the loadout prune. Run: node engine/context/pi-loadout/test.mjs
 *
 * The two things that can silently go wrong here are a prune that never fires
 * (the gateway returns and 3,257 characters come back with it) and a prune
 * that fires on every turn (a loader's tools vanish on the next one). Both are
 * asserted below; neither is visible from the prompt alone.
 */
const fail = [];

function check(label, ok, detail = "") {
  if (!ok) fail.push(label);
  console.log(`${ok ? "ok  " : "FAIL"}  ${label}${detail ? "  " + detail : ""}`);
}

const { default: factory } = await import("./index.ts");

function harness(initial) {
  const handlers = {};
  const state = { active: [...initial], setCalls: 0 };
  const pi = {
    on: (event, fn) => {
      (handlers[event] ??= []).push(fn);
    },
    getActiveTools: () => [...state.active],
    setActiveTools: (names) => {
      state.setCalls++;
      state.active = [...names];
    },
  };
  factory(pi);
  const fire = async () => {
    for (const fn of handlers.before_agent_start ?? []) await fn({}, {});
  };
  return { state, fire };
}

// 1. The gateway is pruned; the namespace proxy and a loader stay.
{
  const h = harness(["read", "bash", "mcp", "mcp__familiar_mcp", "web_enable"]);
  await h.fire();
  check("prunes mcp", !h.state.active.includes("mcp"), `active=${h.state.active.join(",")}`);
  check("keeps proxy", h.state.active.includes("mcp__familiar_mcp"));
  check("keeps loader", h.state.active.includes("web_enable"));
  check("keeps built-ins", h.state.active.includes("read") && h.state.active.includes("bash"));
}

// 2. A loader's additions survive the next turn.
{
  const h = harness(["read", "mcp"]);
  await h.fire();
  h.state.active.push("web_search", "fetch_content"); // what web_enable does
  await h.fire();
  check("later additions survive", h.state.active.includes("web_search"), `active=${h.state.active.join(",")}`);
  check("prune ran once", h.state.setCalls === 1, `setCalls=${h.state.setCalls}`);
}

// 3. No gateway registered: no call, no error.
{
  const h = harness(["read", "bash"]);
  await h.fire();
  check("no-op without gateway", h.state.setCalls === 0);
}

// 4. An API without the active set is a no-op, not a throw.
{
  let threw = false;
  const pi = { on: (_e, fn) => { try { fn({}, {}); } catch { threw = true; } } };
  factory(pi);
  check("survives a pi without the API", !threw);
}

console.log(`\nFAILURES: ${fail.length} / 8 checks`);
process.exit(fail.length ? 1 : 0);
