---
title: Orchestrators — an open design question
summary: Subagents, delegation, multi-agent config — an open design question
origin: authored
authority: human
trust: trial
last_verified: 2026-08-29
use_count: 4
last_used: 2026-10-12
promoted_from: []           # 06_SYSTEM session 2026-08-29; no journal entry covers it
source:
supersedes:
related: [knowledge-vs-skills, skill-routing, opencode]
tags: [orchestrators, subagents, harness, open-question]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving
verified_log: [2026-08-29]
---

# Orchestrators — an open design question

**Status: not decided.** Recorded so the question is not rediscovered later.

Agent orchestration is currently defined per harness, in three incompatible
places, none of which the canonical system knows about:

| Harness | Where orchestration lives |
|---|---|
| opencode | `~/.config/opencode/oh-my-opencode-slim.json` — orchestrator prompt, subagent roster, model bindings; built-in `explore`/`general` agents disabled |
| Claude Code | agent types in `.claude/agents/*.md` and plugin-provided agents |
| hermes | subagent + delegation config in `config.yaml` (`delegation.max_iterations`) |

This is the same fragmentation that motivated `memory/` for knowledge and
skills: three harnesses, three formats, nothing shared, everything relearned.

## Are orchestrators skills?

They look skill-shaped — a procedure, a routing surface, a "when to use". By the
test in [[knowledge-vs-skills]] they assert *do this, then this*, so they are
procedural, not declarative.

But two properties separate them from skills:

1. **They bind to a model and a budget**, not just to a task. A subagent
   definition names which model runs it, with what iteration limit and tool
   access. Skills are model-agnostic by design.
2. **They compose other units.** An orchestrator's job is deciding *what to
   delegate and to whom* — it operates one level above the skill library, and
   would route *into* it.

That second point matters: if orchestrators lived in `skills/`, the router would
have to route to the thing that does the routing.

## Candidate resolutions

| Option | For | Against |
|---|---|---|
| `memory/orchestrators/` as a fourth store | honest about the model/budget binding; mirrors why skills stayed separate from knowledge | a third store to maintain, with its own router |
| a `skills/orchestration/` category | no new machinery; reuses the adoption and lifecycle loop | conflates "what to do" with "who should do it"; recursive routing |
| canonical prompts only, harness config generated from them | one source, three generated configs — the pattern already used everywhere here | needs a generator per harness; formats are undocumented and move |

**Leaning:** the third. It matches the governing rule — markdown is truth,
harness config is a derived artifact — and it sidesteps the recursion by keeping
orchestrators out of the skill router entirely. It is also the most work, and
should not start until M2's generator (`familiar skills index`) exists
and has proved the pattern on something simpler.

## Prerequisite

Before designing anything: audit what the three harnesses actually define today,
including whether their formats are documented or reverse-engineered. The
opencode orchestrator prompt in `oh-my-opencode-slim.json` is the largest piece
and the least portable.

**Do not start this before M2.**
