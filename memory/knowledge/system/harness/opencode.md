---
title: opencode
summary: opencode — plugins, providers, config
origin: authored
authority: agent
trust: trusted
last_verified: 2026-10-09
use_count: 7
last_used: 2026-10-11
promoted_from: []           # 06_SYSTEM session 2026-08-29, commit 186c643; no journal entry covers it
source:
supersedes:
related: [orchestrators, boundaries, claude-code, hermes, context-budget, mcp-servers, pi, rtk]
tags: [opencode, plugins, harness]
scope: []
area: [B]
stability: evolving
verified_log: [2026-10-09, 2026-08-31]
---

# opencode

Config: `~/.config/opencode/opencode.json` → symlink into
`dotfiles/shared/ai/.config/opencode/`. Edit the dotfiles source.

## Plugin loading — and the trap

```json
"plugin": ["opencode-pty",
           "@ex-machina/opencode-anthropic-auth@latest",
           "oh-my-opencode-slim", "opencode-acp@latest"]
```

Plugins are named **as npm packages**, resolved into
`~/.cache/opencode/packages/<name>@latest/`. A bare name never resolves to a
local checkout.

> **Your fork is not what runs.** Verified 2026-08-29:
> opencode loads `oh-my-opencode-slim` **2.2.17** from the npm cache, while the
> fork at `02_AREAS/B_Tech/ai/oh-my-opencode-slim` is **2.1.0** — 850 commits
> behind upstream, 205 behind its own origin, sitting on branch
> `fix/gate-reminders-on-deepwork` with an **unpushed** commit
> (`aad721a fix: gate internal_reminders on deepwork sessions`).
>
> The fix is inert. The clone is a development checkout, nothing more.

To actually run local changes, one of: publish to the fork and point the plugin
entry at it; use a filesystem path or `file:` specifier if opencode supports one
(verify — undocumented); or `bun link` the local build. Until then, treat the
fork as a place to prepare PRs, not as deployed configuration.

### How to load a LOCAL plugin — verified 2026-08-31

Not through `plugin:`. Putting a bare local name there makes opencode create
`~/.cache/opencode/packages/<name>/` and `<name>@latest/`, try to fetch the
package from npm, **fail silently, and start anyway**. Both directories are
left empty, nothing is logged (opencode logs only `failed to load plugin`, and
this does not reach that path), and the plugin never runs. A symlink into
`~/.config/opencode/node_modules/` does not help: the `plugin:` array is not
resolved from there.

The mechanism that works is the **plugin directory**:

```
~/.config/opencode/plugin/<name>.js      # global
<project>/.opencode/plugin/<name>.js     # per project
```

Every module in it is loaded and its function exports are registered. Keep the
file a one-line re-export shim and version-control the real source elsewhere:

```js
export { FamiliarBoundaries } from "/home/<user>/06_SYSTEM/engine/boundaries/opencode-plugin/index.js";
```

Export exactly one function. A non-function export produces
`failed to load plugin ... "Plugin export is not a function"` — which is what
line 33691 of `~/.local/share/opencode/log/opencode.log` is.

**The failure mode to remember: a plugin that does not load is silent.** Do not
infer that a plugin is active because opencode started cleanly. Prove it by
making it deny something.

## Plugin hooks — verified 2026-08-31

`ROADMAP.md` listed these as unverified. Read from the installed SDK types at
`~/.config/opencode/node_modules/@opencode-ai/plugin/dist/index.d.ts` (v1.18.18):

| Hook | Use |
|---|---|
| `tool.execute.before(input {tool, sessionID, callID}, output {args})` | fires before every tool call; **throwing denies it** |
| `tool.execute.after(input, output {title, output, metadata})` | post-hoc; can rewrite results |
| `permission.ask(input, output {status})` | explicit `"deny"`, but only fires when a permission is actually asked |
| `chat.params(input {sessionID, agent, model, provider, message}, output)` | the only hook carrying the model — use it for per-session model tracking |
| `chat.message`, `chat.headers`, `event`, `config`, `tool`, `auth`, `provider` | the rest |

`tool.execute.before` carries **no model**, so anything model-dependent must
record it from `chat.params` keyed by `sessionID`.

In use: `engine/boundaries/opencode-plugin/` enforces `../../../../config/boundaries/read-write.yaml`
through `tool.execute.before`. A denial was observed live 2026-08-31.
See [[boundaries]].

### opencode's own permission layer fires first

`opencode run` auto-rejects permission prompts non-interactively. A read outside
the worktree hits `permission requested: external_directory (...); auto-rejecting`
**before** any plugin hook sees it. When testing a plugin denial, target a path
*inside* the worktree, or the rejection you observe is not yours.

## The default model has no working credential

Verified 2026-08-30 by running `opencode run`:

```
> build · claude-sonnet-5
Error: invalid x-api-key
```

`opencode.json` sets `"model": "anthropic/claude-sonnet-5"`, and
`~/.local/share/opencode/auth.json` does hold an `anthropic` entry — but the
key is rejected upstream. `deepseek/deepseek-v4-flash` works in the same
session, so this is credential-specific, not a gateway or plugin fault:

```bash
opencode run --model deepseek/deepseek-v4-flash "..."   # works
```

Until the anthropic key is refreshed, **every default-model opencode session
fails on its first turn.** Either re-authenticate (`opencode providers`) or
change the `model` default.

## Config notes

- `"agent": {"explore": {"disable": true}, "general": {"disable": true}}` —
  built-in agents are off; orchestration comes from oh-my-opencode-slim.
  See [[orchestrators]].
- `"compaction": {"auto": false}` — auto-compaction off. This was set because
  lore managed context; it **stays** off deliberately (user preference), so
  compaction is nobody's job here — the session must be kept clear by hand.
- XDG isolation test trap: opencode loads config from
  `$XDG_CONFIG_HOME/opencode/opencode.json` — a config at
  `$XDG_CONFIG_HOME/opencode.json` (missing the `opencode/` subdir) is silently
  ignored → `ProviderModelNotFoundError`. `~/.opencode/` is **not** controlled
  by `XDG_CONFIG_HOME`; load order is `~/.config/opencode/config.json →
  opencode.json → opencode.jsonc → project cwd opencode.json →
  ~/.opencode/opencode.json → opencode.jsonc`. Debug:
  `opencode debug --print-logs --log-level DEBUG`.
- `@loreai/opencode` was removed 2026-09-11 (it rewrote **every** provider's
  `baseURL` to the lore gateway in its `config` hook,
  `applyLoreProviderConfig`, src/internal.ts). Its removal is what makes
  `provider.<id>.options.baseURL` the working redirect again — the
  `familiar context harness` adapter depends on that, and an unknown custom
  provider no longer falls back to OpenAI's upstream and 401s.
- oh-my-opencode-slim subagent model arrays: `applyOverrides` sets
  `agent.config.model = undefined` for array models, so a subagent retries only
  the global session model; the fallback manager only covers foreground
  sessions. Keep the array in a separate `_modelArray` field and add a
  subagent-level fallback hook.
- `~/.config/opencode/oh-my-opencode-slim.json` holds the orchestrator prompt
  and subagent config.
- A bundled `history-search` tool lives at
  `dotfiles/shared/ai/.opencode/tool/history-search.ts` (65 KB, self-contained).
  Its source repo was retired 2026-08-29; the built tool still loads. Remove the
  `.ts` too if the tool is genuinely unwanted.

## Verification

```bash
grep -A6 '"plugin"' ~/.config/opencode/opencode.json
ls ~/.cache/opencode/packages/          # what actually loads
```

## Plugin hooks fire in `opencode run` — verified 2026-10-09, opencode 1.18.23

Probed with a project plugin (`.opencode/plugin/probe.js`) that logged from
`event`, `chat.params` and `tool.execute.before`, then with one that threw from
`tool.execute.before` on a path. Running
`opencode run --model local-ollama/qwen3:4b-instruct-2507-q4_K_M "..."`:

```
event                ✅  session.created … session.idle
chat.params          ✅
tool.execute.before  ✅  read {"filePath":"hello.txt"}
throw from the hook  ✅  ✗ Read secret.txt failed — Error: PROBE DENIED secret.txt
```

**The mechanism the boundary guard uses fires and denies in one-shot mode.**
`engine/boundaries/opencode-plugin/` itself was not driven end-to-end under
`opencode run`: every protected path sits outside a scratch worktree, and
opencode's `external_directory` auto-reject fires before any plugin (§opencode's
own permission layer). Level 2 for one-shot mode therefore rests on the same
hook, not on an observed familiar denial. The same probe on
2026-09-01 (an older opencode, `deepseek/deepseek-v4-flash`) saw the factory run
and no hook fire; the version that changed it is not known. Re-run the probe
after an opencode upgrade — a regression would be silent.

`session.idle` fires in one-shot mode too, so the capture hook can be tested
headlessly. A one-shot run on 2026-10-09 staged
`~/.local/share/pazras/transcripts/<ts>_opencode_<session>.jsonl`.

## Transcripts live in SQLite, and staging reads them

opencode keeps sessions in `~/.local/share/opencode/opencode.db`, not per-session
files. `engine/context/opencode_extract.py` reads one session's `message` and
`part` rows read-only and writes them in Claude Code's JSONL shape. A `tool`
part's `state.input` carries the call's arguments (`filePath` for
`read`/`edit`/`write`, `command` for `bash`, `path`/`pattern` for `grep`);
staging keeps those keys since 2026-10-09, so `familiar context pointers` and the
journal's `touches:` facet can read opencode sessions. Transcripts staged before
that date carry tool names only.
