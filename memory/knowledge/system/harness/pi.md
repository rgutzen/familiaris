---
title: pi
summary: The `pi` harness — surfaces, subagents, the stow-safe subset
origin: derived
authority: agent
trust: trusted
last_verified: 2026-10-25
use_count: 11
last_used: 2026-10-20
promoted_from: []
source:
supersedes:
related: [claude-code, opencode, hermes, boundaries, context-budget, mcp-servers, rtk, delegation-and-asks, codex, agent-profiles, phone-relay]
tags: [pi, harness, subagent, guard, tokens]
scope: []
area: [B]
stability: evolving
verified_log: [2026-09-10, 2026-10-25]
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

## Mistral provider — tier gating (resolved 2026-10)

Pi's Mistral catalog lists every GA model (incl. `zai-glm-*`, `mistral-large-*`) for any key, but Mistral gates by entitlement: the authenticated `GET /v1/models` lists only what the org's plan covers. `403 tier_not_allowed/1910` = catalog says GA, account says no. Diagnose by probing the key: 403 = entitlement, 429 with `x-ratelimit-limit-req-minute: 0` = Free-plan 0-RPM on the big models. Fix lives in admin.mistral.ai → Subscription/Billing, not in Pi.

Resolved 2026-10: enabling prepaid-budget spend on API requests in the Mistral account unlocked GLM and Mistral models. Correction to an earlier docs reading: "PAYG isn't a separate plan" described billing mode, not catalog width — enabling API spend on prepaid credit *does* widen effective model access.

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

**`familiar-convert` makes `read` work on documents** (2026-10-20,
`engine/harness/pi-convert/`). Bare `read` returns raw bytes for a `.pdf` or
`.docx`. The hook replaces a successful read of `.pdf .docx .pptx .xlsx .xls
.epub` with markdown cached at `~/.cache/pazras/convert/<sha256>.md`, and the
result's first line names that file as the one to cite. docling converts PDFs
(7–21 s, once per file); markitdown converts the rest. Both are uv tools, so a
fresh machine needs them installed, and without them a document read returns
`conversion failed`. It hooks `tool_result`, so the permission system rules on
the original path (measured: a `~/03_ZETTEL/*.pdf` read stays denied). The
measurements are in `dev/orchestration/2026-10-20-pdf-convert.md`.

## Starting a pi process from the engine

**Every engine call to `pi` starts in `engine/harness/pi_call.py`.** The
`pi-spawn` check fails a commit that builds a `["pi", ...]` argv anywhere else.

- **Why one place.** `pi -p` reads a non-TTY stdin to EOF. A child that
  inherits an open pipe therefore hangs until its timeout. That happened to the
  bound-tool children of the orchestration eval, which waited 900 s on a socket
  handed over by a pi extension. The guard used to be written at each spawn site
  separately, and `pi --list-models` went without it.
- **What the module always sets:** stdin `/dev/null`, `NO_COLOR=1`, and
  stripping of stray ANSI escape codes.
- **What every caller must state:** `approve` and `session`. pi's `--approve`
  means trust project-local files; it is not a permission answer. `session` is
  `None` for `--no-session`, or a directory and id to keep the log.
- **Two levels.**
  - `run`/`spawn` report how the call ended. A timeout is exit code 124.
  - `answer` and `list_models` raise `PiError` on a timeout, a non-zero exit
    or an empty answer.
- **Sandboxing.** `wrap=` transforms the argv just before the spawn. That is
  how the eval runs a cell under bubblewrap.
- **One exception.** `familiar context harness` takes its argv and environment
  from the module but keeps its own `Popen` driver. That driver stops the child
  as soon as the stub has seen a request.
- **Tests** put a fake `pi` executable first on `PATH`.

## The declared loadout — what pi charges before you type

Pi declares every ACTIVE tool to the model on every request, and the total is
not in any config file: it is the sum of what each extension registered.

Measured 2026-10-25 from a session's own `toolsAdded`, the fixed prompt was
31,581 bytes / 7,999 tokens, of which **19,343 bytes / 5,079 tokens were tool
declarations** — 57% of the prefix, dominated by the MCP adapter's gateway
(3,257 chars for install/auth/status prose), the four `pi-web-access` tools
(11 KB of schema), and a duplicated 40-provider enum inside two of them.
After trimming: 16,860 bytes / 4,041 tokens, 7 tools, 1,121 tokens of tools.

- **`familiar context loadout [--session=PATH] [--cwd=DIR] [--check]`** replays
  the session pi writes and prints the table; `--check` exits 3 over caps
  (`context/loadout.BUDGETS`: sections 3,500, tools 1,500).
- **The levers**, in order of size: `~/.config/pi/web-search.json` with
  `"toolActivation": "dynamic"` + `"toolExposure": "deferred"` (only
  `web_enable` is declared); `engine/context/pi-loadout/` prunes the MCP
  gateway; `defaultTools` does **not** reach extension tools registered active,
  which is why the prune is code and not a setting.
- **claude-bridge adds 0 bytes**: `AskClaude` is disabled, and a bridge session
  declares the same tools as any other.

## Verification

```bash
pi --list-models
familiar context loadout --check
ls ~/.pi/agent/{SYSTEM.md,APPEND_SYSTEM.md,AGENTS.md,models.json,auth.json}
ls ~/.pi/agent/agents/*.md
```
