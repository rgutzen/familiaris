---
title: hermes
summary: hermes — local models, skills, bundles, prompt size
origin: derived             # promoted from a .lore.md store (D2->D3)
authority: agent
trust: trusted
last_verified: 2026-08-29
use_count: 4
last_used: 2026-10-11
promoted_from: []
source:
supersedes:
related: [claude-code, opencode, memory-architecture, boundaries, context-budget, mcp-servers, pi, codex]
tags: [hermes, signal, gateway, cron]
scope: []
area: [B]
stability: evolving
verified_log: [2026-08-29]
---

# hermes

Hermes Agent — messaging (Signal gateway), web search, cron, automation.
Config at `~/.hermes/config.yaml` (symlinked from dotfiles).

## Configuration gotchas

Pre-fill trap on local iGPU: the default toolset injects ~20k fixed prompt
tokens/turn (55KB tool-schema + AGENTS.md/skills/memory) → minutes of prefill.
`hermes --ignore-rules -t file,terminal` cuts to ~5k (confirmed 4+ min → ~14s
per turn). Aliases `hermes-fast`/`hermes-think` use `qwen-fast`/`qwen-thinking`.

- `fallback_providers` must be **top-level** in config.yaml, not nested under
  `model:` (bug #45309).
- All three web backend keys must be set explicitly — `web.backend`,
  `web.search_backend`, `web.extract_backend` — missing one disables web tools
  (bug #29617).
- Entry-point plugins are discovered but **not enabled by default**. `hermes
  plugin info` showing them as installed does not activate them. Add the name
  to `plugins.enabled` in config.yaml.
- `hermes config plugins` is invalid; valid subcommands: `show`, `edit`, `set`,
  `path`, `env-path`, `check`, `migrate`.

## Cron safety

Cron jobs may not contain gateway lifecycle commands (`restart`/`stop`/`kill`)
— Hermes blocks them to prevent agent-driven SIGTERM-respawn loops (#30719). A
cron script may only edit `.env`; the token takes effect on the next manual
`hermes gateway restart` run from a shell outside the gateway.

## Signal per-channel config (ChannelOverride)

Lookup priority: explicit `/model` slash command > `channel_overrides` in
config.yaml > global defaults. Keys: `model`, `provider`, `system_prompt`
**only** — no per-channel `workdir` or tool restrictions. Channel IDs: DM =
E.164 phone number, group = `"group:" + base64`. Aliases via
`~/.hermes/channel_aliases.json`. System prompt stacking: adapter
`context_prompt` + legacy `channel_prompts` (`config.extra`) +
`channel_overrides.system_prompt`. Access control: `SIGNAL_ALLOWED_USERS` and
`SIGNAL_GROUP_ALLOWED_USERS`; slash-command gating via `allow_admin_from` and
`user_allowed_commands` (non-admin always have `help` and `whoami`). No
enforced folder sandboxing — architecture assumes allowed contacts are trusted.
Logs: `~/.hermes/logs/gateway.log`.

## Safe update procedure

1. `hermes --version` + `git -C ~/.hermes/hermes-agent log --oneline -5`.
2. `git -C ~/.hermes/hermes-agent pull`.
3. `cd ~/.hermes/hermes-agent && uv pip install -e .`.
4. Check new keys (e.g. `channel_overrides`) against config.yaml.
5. `hermes gateway stop && hermes gateway start`.
Hermes guards missing keys, so existing config stays valid. Check `tests/` for
new test files to understand new feature behaviour.

## Memory format (matters for wiring)

Hermes reads `~/.hermes/memories/MEMORY.md` and `../../../../config/practice/user/user-identity.md` as **§-delimited**
entries (split on `"\n§\n"`). Cap: `memory_char_limit: 2200`,
`user_char_limit: 1375`. A file with no `§` is treated as a single entry. The
canonical `memory/` tree is markdown with no `§` — do **not** symlink the
two together; hermes would rewrite the markdown with `§` separators.

## signal-cli

`signal-cli link` does **not** take a phone number — passing one causes
'not registered'. It registers a secondary device; the number comes from the
primary during pairing. Terminal ASCII QR loses block precision: use
`qrencode -o /tmp/signal-qr.png -s 10 '<uri>'` and `xdg-open`. Shell timeouts
(~15–30s) kill signal-cli before provisioning completes — launch detached via
`setsid`, then poll `~/.hermes/accounts.json` (non-empty = paired). Native
binary (v0.14.5+, GraalVM) needs no Java runtime.
