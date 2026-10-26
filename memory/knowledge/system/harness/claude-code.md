---
title: claude code
summary: Claude Code — hooks, skills, plugins, settings
origin: derived             # promoted from a .lore.md store (D2->D3); see report on the origin enum
authority: agent
trust: trusted
last_verified: 2026-08-29
use_count: 10
last_used: 2026-10-15
promoted_from: []
source:
supersedes:
related: [hermes, opencode, memory-mechanisms, skill-routing, boundaries, context-budget, mcp-servers, pi, rtk, codex, agent-profiles]
tags: [claude, cli, acp, hooks]
scope: []
area: [B]
stability: evolving
verified_log: [2026-08-29]
---

# claude code

Claude Code CLI. Settings at `~/.claude/settings.json` (symlinked from
dotfiles). Global memory at `~/.claude/CLAUDE.md` (supports `@path` imports).

## ACP / headless traps

Claude Code's TUI emits words separated by cursor positioning, not spaces — the
ANSI-stripped screen is space-free (`Yes,Itrustthisfolder`). Match markers after
stripping ANSI **and** collapsing whitespace, against space-free strings. The
trust dialog defaults to **No, exit** (plain `\r` exits; send `\x1b[B\r`);
"custom API key" dialog → `\x1b[A\r`. Readiness is the stable footer
(`auto mode on`), never the placeholder. Sleep each loop iteration.
Measured fixed prefix 2026-08-30: TUI 24,633 tok vs headless `claude -p` 12,649
(~1.95×; TUI-only schemas: Artifact 8,853, SendFeedback, AskUserQuestion).

- `@agentclientprotocol/claude-agent-acp` does **not** use
  `CLAUDE_CODE_OAUTH_TOKEN` — it uses `ANTHROPIC_API_KEY` or `claude auth
  login`. No OAuth env var is supported.
- First run of `claude-agent-acp` downloads a ~1GB native binary; skip it with
  `CLAUDE_CODE_EXECUTABLE=/path/to/claude`.
- Headless `claude -p` must **never inherit stdin** — a child that eats the
  operator's terminal can swallow a typed confirmation. Use
  `stdin=DEVNULL`; keep confirmation prompts fail-safe by construction.
- Headless `claude -p` treats MCP tool results as untrusted data — prefix with
  an ignore-embedded-instructions guard.

## "Connection lost before a response" — was the lore gateway (fixed 2026-09-11)

**Root-caused and closed.** This was the recurring `API Error: Connection lost
before a response was produced.` on claude-bridge + Opus — Claude Code's
**client wording** (binary 2.1.263) for the default pre-response branch: the
stream died with thinking-only content and Claude Code's own watchdogs did not
fire (their variants say "stalled…"; first-party byte idle is 180s), i.e.
external severance.

Chain: pi → pi-claude-bridge spawns Claude Code inheriting `process.env`,
including `ANTHROPIC_BASE_URL=127.0.0.1:3207` +
`_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1` → lore gateway →
api.anthropic.com. Prime culprit (code-path inference; `LORE_DEBUG` was off):
the gateway's hardcoded `FOREGROUND_SSE_INACTIVITY_MS=120_000` (pipeline.ts
~11296, no env override, resets only on upstream events) aborted an upstream
read silent >120s during Opus extended thinking; the client-facing 30s SSE ping
keepalives never reset it.

**Kept as the record of what it cost**: it killed 8 consecutive
lore-reevaluation sessions on 2026-09-09
(`memory/journal/2026/09/2026-09-10_lore-reevaluation.md`). The gateway was
unwired from every harness on 2026-09-11, so the failure mode is gone with it —
if this string reappears, look at whatever now sits between the client and
api.anthropic.com rather than at Claude Code.

## Hooks

`settings.json` hooks are harness-executed capture points: `PreToolUse`,
`PostToolUse`, `SessionEnd`. Capture hooks call
`familiar context capture --harness=claude --event=<event>`; they append to logs
only, never mutate tracked files.

## Hooks configured here (2026-08-30)

`~/.claude/settings.json` → `hooks`:

| Event | Matcher | Command |
|---|---|---|
| `PreToolUse` | `Bash` | dippy (`~/04_RESOURCES/Templates/Dippy/bin/dippy-hook`) |
| `PreToolUse` | `Read\|Edit\|Write\|NotebookEdit\|Glob\|Grep\|Bash` | `engine/boundaries/guard.py` — every rule in `../../../../config/boundaries/read-write.yaml` ([[boundaries]]) |
| `PostToolUse` | `Skill` | `familiar context capture --event=skill-use` |
| `SessionEnd` | — | `familiar context capture --event=session-end` |

Both `PreToolUse` entries fire on Bash; they are independent and neither
short-circuits the other.

**Skill injection.** Claude Code injects `name` + `description` for every skill
under `~/.claude/skills` **and** every enabled plugin's skills, at session start,
unconditionally — there is no lazy loading of descriptions. This is why
canonical skills are not installed here ([[skill-routing]]
§Zero-install).

`omarchy` and `diagnose-crash` — placed in `~/.claude/skills/` by the
`omarchy` pacman package itself, independent of the dotfiles stow package —
were the one remaining exception until 2026-09-01, when both were onboarded
into `memory/skills/system/host/` (`mode: link`, pinned to the package rather than a
commit — see those two records) and the `~/.claude/skills/{omarchy,
diagnose-crash}` symlinks removed[^pending]. What remains actually installed
now: only enabled plugins, at ~1,018 tok/session (see below).

[^pending]: **Removal not yet verified in this session** — the safety
classifier gating Bash's write/mutate path was intermittently unavailable for
the whole 2026-09-01 build, so `rm ~/.claude/skills/omarchy
~/.claude/skills/diagnose-crash` could not be confirmed to have actually run.
`ls ~/.claude/skills/` should show neither — if it still does, that `rm` is
still owed ([[skill-routing]]'s own verification command names exactly this
check).

Backup of the pre-hook settings: `~/.claude/settings.json.bak-20260830`.

## Plugin skill budget — see [[context-budget]]

**Measured live, not counted from disk.** The current per-session cost of the
harness's skill listing, plugin injections and the full fixed prefix is measured
by intercepting the real request — `engine/consolidation/pazras context harness`
([[context-budget]] records the 2026-09-03 figures and the
headless-vs-TUI gap).

The measurement that *matters* here is the 2026-09-01 one: disabling unused
plugins is the single lever that beats any routing change, because enabled
plugins inject their skills' `name` + `description` into **every** session and
the canonical routers do not control them.

| Plugin | Exposed skills | ~tokens/session (2026-09-01) |
|---|---|---|
| `document-skills` | xlsx, docx, pptx, pdf | **745** |
| `claude-api` | claude-api | 271 |
| `claude-code-setup` | 1 | 95 |
| `claude-md-management` | 1 | 89 |
| `20minds` | decide, research | 61 |
| **total** | **9** | **~1,262** |

Grown from ~1,018 at the 2026-08-30 measurement. **`document-skills` and
`claude-api` were disabled on 2026-09-01** on the strength of this measurement,
leaving ~246 tok/session from `claude-code-setup`, `claude-md-management` and
`20minds`. `enabledPlugins` in `~/.claude/settings.json` is the switch; the
change takes effect for new sessions.

**Do not measure this from the plugin cache directory.** `anthropic-agent-skills`
is cloned once per plugin, so `claude-api/` and `document-skills/` each contain
the *same* full 20-skill tree on disk; counting those gives ~3,800 tokens, three
times the real figure. Only the skills actually surfaced in the session's skill
list are injected.
