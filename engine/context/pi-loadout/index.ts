/**
 * familiar-loadout — declare less than what is registered.
 *
 * WHY. Pi declares every active tool to the model on every request. The MCP
 * adapter's `mcp` gateway is one tool description doing the work of an install
 * path, a status query and eleven usage examples: 3,257 characters, measured
 * 2026-10-25 from a session's own `toolsAdded`. It is paid by every session,
 * including the ones that never touch an MCP server. `mcp__familiar_mcp`, the
 * namespace proxy for the one server configured here, is 634 characters and is
 * the call path the model actually uses. So the gateway is pruned, and the
 * call path stays.
 *
 * WHAT IS LOST. The model can no longer install an MCP endpoint from a URL, nor
 * start an OAuth flow. Both remain available as the `/mcp-adapter` commands,
 * and one invocation gets the tool back: `pi --tools read,bash,edit,write,mcp`.
 * This is the trade the orchestration policy already makes for every child
 * ("the narrowest set that does the job"): declared cost is paid per request,
 * an affordance is paid per use.
 *
 * ONCE, NOT PER RUN. `before_agent_start` fires for every turn, but pruning
 * there would also remove the tools a loader adds mid-session (`web_enable`
 * activates the four web tools; `tool_search` declares a match) on the next
 * turn. So the prune happens on the first run only; later activations persist
 * on that branch, which is what pi records in the session either way.
 *
 * NO FAILURE PATH INTO THE PROMPT. If a pi version lacks the active-set API,
 * this is a no-op: the extension can cost nothing, but it must never break a
 * session or inject text. Same posture as familiar-capture.
 */
type ExtensionAPI = any;

const PRUNE = ["mcp"];

export default function familiarLoadout(pi: ExtensionAPI): void {
  let done = false;
  pi.on("before_agent_start", async () => {
    if (done) return;
    done = true;
    try {
      const active: string[] | undefined = pi.getActiveTools?.();
      if (!active) return;
      const keep = active.filter((name) => !PRUNE.includes(name));
      if (keep.length !== active.length) pi.setActiveTools?.(keep);
    } catch {
      // never let the loadout break a run
    }
  });
}
