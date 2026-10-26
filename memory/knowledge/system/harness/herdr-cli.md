---
title: herdr-cli
summary: herdr CLI and socket surfaces: pane run word-splitting, metadata tokens, agent state
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-24
use_count: 0
last_used:
promoted_from: []
source: https://herdr.dev
supersedes:
related: [pi, agent-profiles]
tags: [herdr, terminal, panes, agents, session, metadata, harness]
triggers: [herdr, pane run, report-metadata, agent state, screen detection, herdr session, sidebar]
scope: []
area: [B]
stability: evolving
verified_log: [2026-10-24]
---

# herdr-cli

herdr (0.9.1 here) is a terminal workspace manager: sessions, spaces, tabs and
panes over a socket API, with a client CLI for each. The stem is `herdr-cli`
because `herdr` already names the track, `06_SYSTEM/dev/herdr/` — one stem, one
document. Every command below is a
socket call, so the JSON on stdout is the API's own shape, not a rendering.
The local setup — sessions per context, generated theme, layout profiles, the
sidebar rows — is designed in `06_SYSTEM/dev/herdr/DESIGN.md`; this leaf holds
only what an agent gets wrong.

## What an agent must know

- **`pane run` word-splits its arguments. Quoting does not survive.** `herdr
  pane run <pane> bash -lc 'pi --model x'` executes `bash -lc pi` and silently
  drops `--model x`; the process starts with its defaults and nothing reports an
  error. Verified 2026-10-24 against two panes that came up on the wrong model.
  For anything quote-sensitive, use `pane send-text <pane> '<literal line>'`
  then `pane send-keys <pane> enter`. `send-keys enter` needs a beat after
  `send-text` when the shell is still processing, so check the pane before
  concluding the command failed: the line sits in the editor unfired.
- **`report-metadata` tokens are display-only and keyed by pane.**
  `herdr pane report-metadata <pane> --source <id> --token k=v` (repeat
  `--token`; `--clear-token k` removes one). `--source` namespaces the writer,
  so two reporters do not fight. Read them back from `herdr agent list` or
  `herdr api snapshot` under `tokens`, never from the screen. Mixing
  `--clear-token` and `--token` in one call cleared the other tokens in
  practice; send one intent per call.
- **A process inherits `HERDR_PANE_ID`, so it reports against the pane that
  spawned it.** A test `pi` launched from inside a herdr pane writes its model
  and session name onto *that* pane's row. Unset `HERDR_ENV` and
  `HERDR_PANE_ID` (`env -u HERDR_ENV -u HERDR_PANE_ID …`) for any probe that
  must not touch the sidebar.
- **Agent state has two possible sources; `herdr agent explain` says which.**
  `screen_detection_skip_reason: full_lifecycle_hook_authority` means a harness
  integration reports state over the socket and screen scraping is off —
  `agent list` then carries `screen_detection_skipped: true`. The pi integration
  is `~/.pi/agent/extensions/herdr-agent-state.ts`, installed by
  `herdr integration install pi`; **herdr overwrites that file**, so custom
  hooks go beside it under another name, never inside it.
- **`config.toml` has no include mechanism.** The local `config.toml` is
  generated: a tracked `config.toml.base` plus a `[theme.custom]` block written
  by an Omarchy theme hook. Editing the generated file loses the change on the
  next theme set. `herdr config check` validates syntax, not intent: a row
  referencing an unknown token still passes.

## Verification

- Version and surfaces: `herdr --version`; `herdr pane --help`.
- Live state: `herdr api snapshot` (agents, panes, tabs, tokens),
  `herdr agent list`, `herdr agent explain <pane>`.
- Config: `herdr config check`.
- The `pane run` trap: `herdr pane run <pane> printf '%s\n' 'a b'` and read the
  pane — the quoting is gone.
