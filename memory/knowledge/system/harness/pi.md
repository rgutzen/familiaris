---
title: pi
summary: The `pi` harness — surfaces, subagents, the stow-safe subset
origin: derived
authority: agent
trust: trusted
last_verified: 2026-09-10
use_count: 3
last_used: 2026-09-29
promoted_from: []
source:
supersedes:
related: [claude-code, opencode, hermes, boundaries, context-budget, mcp-servers, rtk]
tags: [pi, harness, subagent, guard, tokens]
scope: []
area: [B]
stability: evolving
verified_log: [2026-09-10]
---

# pi

The `pi` coding harness (`~/.pi/agent/`), fourth alongside Claude Code, opencode
and hermes. Exported from lore's per-project store on 2026-09-10 so
the facts live in git, not the store — that store was retired the next day.

## Agent surfaces

- `~/.pi/agent/SYSTEM.md` **replaces** the system prompt verbatim;
  `APPEND_SYSTEM.md` appends.
- `AGENTS.md` loads verbatim with **no `@`-imports** — pointers to
  `~/06_SYSTEM/CONTEXT.md` must be plain text (`l1.py` emits them).
- `models-store.json` is a read-only auto-cache; custom providers register in
  `~/.pi/agent/models.json` (created manually).
- `auth.json` appears only after the user runs `pi /login`.

Ollama provider schema (models.json):

```json
"providers": {"ollama": {"baseUrl": "http://localhost:11434/v1",
  "api": "openai-completions", "apiKey": "ollama",
  "compat": {"supportsDeveloperRole": false, "supportsReasoningEffort": false}}}
```

`baseUrl` carries `/v1` because it is Pi's model connection, and it is what the
`familiar context harness` adapter rewrites to intercept Pi's prefix.

## Subagents

`pi install npm:@mjakl/pi-subagent` (in-process alternative:
`@gotgenes/pi-subagents`). Defined in `~/.pi/agent/agents/<name>.md` frontmatter:
`name`, `description`, `model` (defaults to parent model; per-call override;
provider prefix OK, e.g. `ollama/qwen3:4b…`), `tools` comma-list (defaults
read,bash,edit,write; optional grep,find,ls; `noTools:true` disables all),
`inactivityTimeout` (process tree killed on no RPC stdout — stderr and parent
progress do **not** keep alive).

Child = separate headless pi process (RPC): no shared memory, no sibling
visibility, `PI_OFFLINE=1` skips startup network. Parent receives only a concise
text summary per call — long bash output never bulks the main context.

Guard detection: only `subagents:child:bound` proves a child is guarded
(`session-created`/`disposed` fire before binding / in `finally`, so a guarded
and unguarded child look identical at those two moments). `bound` is optional —
an implementation that never emits it is still conformant (ADR 0012 decision 5),
so its absence is not proof of an unguarded child. Emit after `bindExtensions()`
resolves, success path only.

Qwen3-4B trap: malformed tool-call JSON is the classic small-model failure.
Ollama needs its jinja tool template, llama.cpp needs `--jinja` — smoke-test
before trusting.

## Stow ruling (secret-safe subset only)

`~/.pi/agent/AGENTS.md` is stowed to the public dotfiles canonical
(`dotfiles/shared/ai/.pi/agent/AGENTS.md`); `l1.py` writes through the symlink.
The gotgenes `pi-permission-system/config.json` is the other stow-safe artifact.

**The two extensions this system adds are stowed too** — the dotfiles' `ai`
package carries them beside `rtk.ts`, as one-line re-exports of the
version-controlled implementations at `engine/context/pi-capture/` and
`engine/boundaries/pi-guard/`. Stow links only the files the package holds, so
adding that directory cannot publish the rest of the tree.

Nothing else: `~/.pi/agent/` also holds `auth.json` (live key), `sessions/`,
`models-store.json` — a naive `stow shared/ai/.pi` publishes credentials.

**No extension is a hard dependency, and that is the risk.** Pi loads whatever
`index.ts` it finds under its extensions directory: a missing shim is not an
error, it is a missing guard and a missing capture. That is why they are in the stow package —
`bootstrap.sh --dry-run` then names one that is gone.

## Verification

```bash
pi --list-models
ls ~/.pi/agent/{SYSTEM.md,APPEND_SYSTEM.md,AGENTS.md,models.json,auth.json}
ls ~/.pi/agent/agents/*.md
```
