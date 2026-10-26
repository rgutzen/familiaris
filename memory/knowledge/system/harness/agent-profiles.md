---
title: Billing profiles
summary: Which account bills a pi session — and what a billing profile does and does not switch
origin: authored
authority: agent
trust: trusted
last_verified: 2026-10-21
verified_log: [2026-10-21]
use_count: 2
last_used: 2026-10-21
promoted_from: []
source: https://code.claude.com/docs/en/authentication
supersedes:
superseded_by: []
contradicts: []
related: [pi, claude-code, the-loom, delegation-and-asks]
tags: [profiles, billing, claude, accounts]
triggers: [billing profile, pi-work, second claude account, wrong account billed, claude config dir, profile login, team seat]
scope: []
area: [B]
stability: evolving
---

# Billing profiles

A billing profile decides **which account pays** for one pi process: a
subscription login for Claude, and one API key per keyed vendor. It is bound at
process start and cannot be changed inside a session — the second account is a
second `pi-<profile>` call, never a `/model` switch. See [[pi]] for the harness
itself.

## The chain

| Step | Mechanism | Set by |
|---|---|---|
| Which profile runs | the nearest `.pi-profile` at or above `$PWD`; `command pi` bypasses | `shared/bash/.config/bash/rc.d/40-ai.sh` |
| What the profile is | `PI_PROFILE=<name>` | `pi-profile` wrapper in the dotfiles `bin/` package |
| The Claude account | `CLAUDE_CONFIG_DIR` — one login per config directory | same wrapper |
| API keys | for every `<KEY>_<PROFILE>`, the personal `<KEY>` is unset; the alias `<provider>-<profile>` keeps the suffixed key | wrapper + `~/.pi/agent/extensions/provider-aliases.ts` |
| Model routing | a model on `<provider>` moves to `<provider>-<profile>` at session start | same extension |
| Whether a vendor is usable | `config/orchestration/profiles.yaml`: per profile, per vendor, `provider` plus `key_env` or `login` | [[the-loom]], read by `profiles.resolve` |

Claude needs no key and no alias: the account is a **login directory**, and
claude-bridge hands the whole environment to every Claude Code child
(`env: { ...process.env, ...CC_CHILD_ENV }` at both spawn sites in
`pi-claude-bridge/src/index.ts`). `provider-aliases.ts` therefore leaves
claude-bridge alone on purpose — an alias needs an API key, and a subscription
has none. DeepSeek and Mistral need aliases for the opposite reason: one
provider id cannot hold two keys.

Delegated work inherits the binding, never the parent's model: `pi-agent` states
that the child gets `PI_PROFILE` and `CLAUDE_CONFIG_DIR` (`engine/orchestration/pi-agent`),
so a child bills where its parent bills.

## What a profile does not switch

- **`~/.pi/agent/claude-bridge.json` is global** — `plan`,
  `pathToClaudeCodeExecutable`, `strictMcpConfig`, `askClaude`. claude-bridge
  merges `<project>/.pi/claude-bridge.json` over it (`loadConfig` in
  `src/config.ts`), which is the only per-directory hook that exists.
- **No per-profile pi state.** The installed pi build (2026-10-21) exposes no
  environment variable for its agent directory — a string scan finds
  `PI_SESSION_FILE` and `PI_SESSION_ID`, no agent- or config-dir override — so
  `settings.json`, extensions and sessions are shared by all profiles.
- **`plan` is not usage.** It gates only Opus 4.6 at 1M context
  (`PLAN_GATED_ONE_M` in `pi-claude-bridge/src/models.ts`); Opus 5.5/5/4.8/4.7
  and Sonnet 5.5/5 get 1M on every plan. A Team Standard seat therefore needs no
  override: Claude Code is included with every Team seat, and Premium buys
  usage, not models (source: support.claude.com article 12004354, verified
  2026-10-16). Decided 2026-10-21, `dec-02344804`.

## The traps

1. **An exported Anthropic credential outranks the login.** With
   `ANTHROPIC_API_KEY` set, `claude auth status` reports
   `loggedIn: true, authMethod: "api_key"` for a config directory that holds no
   credentials at all, and the session bills the API under the profile's name.
   Measured 2026-10-21. The wrapper warns on `ANTHROPIC_API_KEY`,
   `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL` and `CLAUDE_CODE_OAUTH_TOKEN`.
2. **The directory isolates claude.ai logins, not Console ones.** Anthropic's
   authentication docs say separate config directories keep two claude.ai
   sign-ins apart, and that Console sign-ins are stored outside the directory.
3. **A missing login is silent at startup.** claude-bridge registers its
   provider whether or not an account exists; the first turn is what fails.
   `profiles.resolve` is the check that names it before the turn:
   `unavailable in profile work: ~/.claude-work/.credentials.json does not
   exist`.

## Verification

```bash
pi-work status                                      # account the profile resolves to: email, org, subscriptionType
CLAUDE_CONFIG_DIR=~/.claude-work claude auth status  # the same, straight from Claude Code
cd ~/06_SYSTEM/engine && PI_PROFILE=work python3 -c \
 "import sys; sys.path.insert(0,'.'); from orchestration import profiles; print(profiles.resolve('claude-opus-5-5', profiles.active()).line())"
```

The billing proof is a file. Every turn mirrors its session into
`$CLAUDE_CONFIG_DIR/projects/<slug of the cwd>`, so after one turn in a work
tree that directory names the tree and `~/.claude/projects` does not grow. No
configuration review substitutes for it.
