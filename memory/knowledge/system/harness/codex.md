---
title: codex
summary: The fifth harness — audited for cost, wired to nothing
origin: authored
authority: agent
trust: trusted
last_verified: 2026-10-15
use_count: 0
last_used:
promoted_from: []
source:
supersedes:
related: [claude-code, pi, opencode, hermes, context-budget, memory-mechanisms, boundaries, mcp-servers]
tags: [codex, harness, tokens, unaudited]
scope: []
area: [B]
stability: evolving
verified_log: [2026-10-15]
---

# codex

The fifth name in `engine/context/harnesses.py`'s roster (`ALL`) and the only one
this system does not wire to anything. It is measured for what it costs, and it
carries no always-on payload, no boundary hook and no capture path — a harness can
be in the roster without being an entry point, and this leaf exists so that fact
has a home.

## What is measured

- **Version and install:** `codex-cli 0.149.1`, from a version manager rather
  than the distribution (`mise`), so the binary is not at a system path.
- **Prefix cost:** 48,268 bytes, of which the vendor prompt is 20,903 and the
  `multi_agent_v1` tool 10,301 — measured, in
  [[context-budget]] with the other harnesses.
- **How the audit drives it:** `codex exec` with `-c
  model_providers.…` overrides on the command line, so nothing is written to
  `~/.codex/` to intercept a request — unlike Pi, whose provider lives in a
  config file.

## What is not

- **No capture.** No codex hook is known and none has been verified
  ([[memory-mechanisms]], 2026-10-09). Its sessions are therefore absent from the
  journal, and a consolidation night cannot replay them.
- **No boundary enforcement.** `engine/boundaries/guard.py` answers in the Claude
  Code and hermes dialects; codex has no hook surface here, so it is in the
  position hermes would be in without its `pre_tool_call` — a reader of the
  advisory, not an enforcer.
- **No always-on payload.** `engine/context/l1.py`'s `targets()` yields claude,
  opencode and Pi's two files. Codex reads none of them, and nothing in
  `config/practice/` reaches it either.

**The trap worth writing down:** codex 0.149.1 **rejects** `wire_api="chat"` and
requires `"responses"`, which is why the recorder answers the OpenAI *responses*
shape for it and the chat shape for hermes and opencode ([[context-budget]], the
recorder's own docstring).

## If it is to be wired

`engine/context/l1.py` for the payload, `engine/boundaries/` for a hook or an
advisory target, `engine/context/capture.py` plus an extractor for the journal —
the four places any harness touches, in
[the recipe](../../../../docs/how-to/add-a-harness.md). Until then the honest
description is this one: audited, not integrated.

## Verification

```bash
command -v codex && codex --version
ls ~/.codex/                    # sqlite stores, sessions, skills — no config.toml
grep -n 'targets' -A 25 engine/context/l1.py   # no codex entry
```
