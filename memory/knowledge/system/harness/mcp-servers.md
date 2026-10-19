---
title: mcp servers
summary: MCP servers — wiring, boundary enforcement, per-harness traps
origin: authored
authority: agent
trust: trusted
last_verified: 2026-09-11
use_count: 7
last_used: 2026-10-09
promoted_from: []
source:
supersedes:
related: [pi, hermes, opencode, claude-code, journal-index, boundaries]
tags: [mcp, retrieval, pi, hermes, opencode, claude-code, harness]
scope: []
area: [B]
stability: evolving
verified_log: [2026-09-11]
---

# MCP servers

The first MCP server this machine runs:
`engine/cli/familiar-mcp.sh` (`engine/context/mcp_server.py`), exposing
three tools. They return `path`/`start_line`/`end_line` pointers, never a copy
of the text as ground truth — the same rule `journal_index.py` states for its
own CLI. This leaf is the general "how MCP actually works across the four
harnesses" reference; server-specific detail stays in
[[journal-index]].

| Tool | What it answers | Cost |
|---|---|---|
| `brief` | what changed, what's open, what failed — **ask this first** | one file read; the nightly pass already computed it (L5) |
| `journal_search` | meaning-based lookup in `memory/journal/`, optionally within one `branch` (`system`/`areas`/`projects`/`unknown`) or one `touches` subject | one embedding call against the M4 index |
| `grep` | literal/regex lookup anywhere under `06_SYSTEM` | ripgrep |

`brief` is first because searching for the state of the system re-derives work
the pass has done ([[consolidation-cycle]] §stage 8). The other two are
for questions the brief does not already answer.

**Every `journal_search` hit carries a `provenance` field**, and the server's
instructions say why: `memory/journal/` is an episodic record machine-distilled
from transcripts that quote web pages, repositories and tool output. A snippet
reads exactly like an instruction if nothing says otherwise, so the label
travels with the result rather than living only in a leaf —
[[memory-poisoning-posture]], property 5. Directives for agents live
only in directive files.

**Its two filters are the caller's, and each hit reports the facet it was
selected by.** `branch` comes from the entry's own `cwd:`; `touches` from the
subjects stage 1 read out of the session's tool calls ([[journal-index]]
§The facets). Either filters BEFORE ranking, so `top` counts inside the subset,
and a value outside the register is an error rather than an empty page — a
facet that is silently empty and a query with no hits are the same picture
otherwise. `touches` is sparse by construction: an entry distilled before the
field existed carries none, and the server says so instead of answering "no
hits".

## Why MCP here, not a subagent

A subagent (`../../../../config/orchestration/CONTEXT.md`) is for a child that discards far
more than it returns — recon condensed to a cited summary. A search result
*is* what the caller needs verbatim: a `path:line` pointer. Routing that
through a second model call risks paraphrasing the one thing the tool exists
to preserve exactly, and pays a model load to do it. MCP returns structured
data with no LLM in the loop.

## Boundary enforcement lives in the server, not a harness hook

`wards`'s own docstring: "MCP tools take arbitrary input shapes and are
NOT covered by any check here." A harness-side hook only fires for tool names
it already knows, so a per-harness reimplementation would be four partial
guards. `engine/cli/familiar-mcp.sh` imports `engine/boundaries/_boundaries.py`
directly (`compiled()`, `path_matches()`, `applies()`) and checks every path
argument itself, model class fixed to `"remote"` — no rule in
`../../../../config/boundaries/read-write.yaml` is `models: local`-only, so remote is already the superset,
matching wards's own fail-closed default when it cannot resolve the
calling model. Any future MCP server on this machine should do the same:
import `_boundaries`, do not reinvent path matching.

## Per-harness wiring — what actually works, verified 2026-09-11

| Harness | Client | Config | Command used |
|---|---|---|---|
| Claude Code | native | `~/.claude.json` → `mcpServers` (user scope) | `claude mcp add -s user familiar-mcp -- <shim>` |
| opencode | native | `opencode.json` → `mcp.<name>` (`type: "local"`) | hand-edited the dotfiles-canonical `opencode.json` |
| hermes | native, "built-in MCP client" per its own `AGENTS.md` | `~/.hermes/config.yaml` → `mcp_servers` | `hermes mcp add <name> --command <shim>` (interactive `Enable all N tools? [Y/n]` — pipe `y` for non-interactive use) |
| pi | **no native client** — confirmed absent from `pi --help`; the `mcpServers` string found in the pi binary is a Gemini Enterprise catalog-import transform, unrelated | `npm:pi-mcp-adapter` extension (`pi install npm:pi-mcp-adapter`), reads the standard `~/.config/mcp/mcp.json` | `pi install npm:pi-mcp-adapter`; adapter exposes one proxy tool (`mcp`) that searches/calls the underlying server's tools on demand, not N tools injected into every session |

**pi has no native MCP client.** `pi.md`'s "Pi has no native subagents by
design ... use external tools" pattern repeats here: `pi-mcp-adapter` (npm,
actively maintained, last published 2026-09-10) is the external bridge, same
shape as `pi-agent` compensating for the missing subagent primitive. It is
deliberately low-cost — one ~200-token proxy tool instead of the full tool
schema of every connected server, which is the opposite failure mode from
lore's blanket-injection problem ([[knowledge-index]]).

**`hermes mcp add` rewrites the whole config file and drops comments.**
Verified live 2026-09-11: registering the server reordered
`hermes/config.yaml`'s keys and silently stripped the hand-written comment
block above `hooks:` (the actual `hooks`/`plugins` *content* survived — first
read of the diff looked like data loss, it was cosmetic). Any comment near a
key `hermes mcp`/`hermes tools` touches should be treated as **not
durable** — expect to re-add it after the next CLI-driven config write.

**hermes toolset gating:** `-t <toolset>` restricts to named built-in
toolsets (`file`, `terminal`, …) and does **not** include MCP servers by
default — pass the MCP server's own name as an extra toolset, e.g.
`-t file,familiar-mcp`, or omit `-t` entirely (full default toolset, ~20k
tokens, the fixed-prefill trap `hermes.md` already documents on the local
iGPU — expect minutes, not seconds, with a local model).

**opencode's default model has no working credential** (`opencode.md`) — use
`--model deepseek/deepseek-v4-flash` (or any working provider) to verify a
tool call live.

## Verification

```bash
# raw JSON-RPC handshake through the launch shim
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | ~/06_SYSTEM/engine/cli/familiar-mcp.sh

# a real client, list + call both tools (needs `pip install mcp` or `uv run --with mcp`)
python3 -c '
import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
async def main():
    p = StdioServerParameters(command="/home/<user>/06_SYSTEM/engine/cli/familiar-mcp.sh")
    async with stdio_client(p) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        print([t.name for t in (await s.list_tools()).tools])
asyncio.run(main())'

# per harness, live
claude -p --dangerously-skip-permissions "call mcp__familiar-mcp__journal_search with query X"
opencode run --model deepseek/deepseek-v4-flash "call the familiar knowledge journal_search tool with query X"
hermes chat -q "call the familiar knowledge journal_search tool with query X" --oneshot -t file,familiar-mcp
pi -p --provider deepseek --model deepseek-v4-flash "use the mcp tool to call journal_search with query X"
```
