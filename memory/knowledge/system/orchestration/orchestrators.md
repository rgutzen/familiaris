---
title: Orchestration — what was tried, and the verdicts
summary: Which ways of splitting agent work across models paid here, which did not, and on what evidence
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-15
verified_log: [2026-10-15, 2026-08-29]
use_count: 11
last_used: 2026-10-19
promoted_from: []
source: 06_SYSTEM/dev/orchestration/2026-10-15-eval.md
supersedes:
related: [the-loom, orchestration-eval, delegation-and-asks, opencode, scheduled-sessions, knowledge-vs-skills, skill-routing]
tags: [orchestrators, subagents, delegation, dispatch, verdicts, evaluation]
triggers: [orchestration verdict, should I delegate, multi-agent, subagent, dispatch adopted, bindings rejected, oh-my-opencode-slim]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving
---

# Orchestration — what was tried, and the verdicts

**The answer, as of 2026-10-15: route each piece of work to the cheapest model
adequate for its class, and do not delegate by default.** Dispatch (one model
per `SPECS.md` item, chosen from a tier) is adopted. Every other arrangement
measured was rejected, or is still waiting for its data. This leaf is the
decision record. The mechanism is [[the-loom]], the instrument is
[[orchestration-eval]], and the permission side is [[delegation-and-asks]].

## The verdicts

| strategy | verdict | evidence |
|---|---|---|
| **dispatch**: each item runs on its class's tier-1 model (`selection.yaml`), unless the plan declares one | **adopted**, all four classes | 13 vs 12 passes over 14 paired tasks (12 vs 12 counting reruns); median frontier cost **0.10×** the Opus baseline; tokens 1.49× |
| **bindings (T)**: tools such as `read` and `fetch` bound to a cheap child model | **rejected as tested** | cost 1.008×. The parent calls a bound tool rarely (4 of 9 cells). The first two calls hung on a defect, fixed since: the child read an inherited stdin. After the fix, one bound call cut its cell to ~0.49×, but the median over the arm's tasks stays ~1.0× |
| **Jev as labeller** for batch classification | **rejected** | 1 vs 3 passes, reproduced on the rerun (22/33 and 19–20/31 against bars of 29 and 27) |
| **oh-my-opencode-slim** (the reference orchestrator) | **rejected as installed** | 10 vs 12 passes; unpriced model; its subagent lanes could not start (fixed afterwards: `deepseek/deepseek-v4-flash` → `deepseek/deepseek-flash`) |
| **delegation on a count trigger (B)** | **pending: 5d** | the trigger fires on 28.7% of turns (recorded rate 27%); uptake and compression are being logged since 2026-10-15 |
| automatic quota fallback | **not needed yet** | 0 of 70 eval cells were refused for the Claude window; the switch to `deepseek-flash` stays manual |

**The rule that produced the verdicts**, decision 29: a strategy becomes the
default for a class only if

- its pass count is at least the baseline's **and** its median paired frontier
  **cost** (API-equivalent $, at list price) is at most **0.84×** the
  baseline's, **or**
- it passes at least 2 more tasks.

0.84 is 1 − 2 × the median run-to-run spread of the reruns (0.079). Cost, not
tokens: moving a class to a cheaper model is the point, and a token rule would
reject every tier step that does not also shorten the transcript.

**Live verdicts since 2026-10-25 come from the evaluation layer**
([[component-evaluation]]). `familiar checks evals review` reads `delegation-nudge` (5d)
and `dispatch` against their floors, and a ruled verdict adds its row to the
table above.

## What the verdicts do not say

- **Fourteen tasks decide a default, not a law.** No arm passed a sign test:
  dispatch has 1 discordant pair. The partial arms (5 and 3 pairs) cannot pass
  one at any outcome.
- **Dispatch's coding savings come from two sources.** Three tasks ran on
  `deepseek-flash`, a CN vendor reading this repository's code (allowed under
  the private profile, decision 19). Three ran on the model their original item
  declared. Both halves cleared 0.84.
- **Latency is outside the rule.** Dispatch's `deepseek-flash` coding cells
  took 2–4.5× the baseline's wall-clock.
- **T's rejection is about uptake, not about what a call costs.** The 900 s
  timeouts were a defect: `pi -p` read the extension's never-closing stdin
  socket. It is fixed (`stdin=DEVNULL`). A fixed bound call answered in 25 s and
  halved its cell's cost. T would pay only if the parent called the bound tools
  more often.
- **The reference arm can be re-run** now that its lanes start; until it is,
  oh-my-opencode-slim's delegation is unmeasured here.
- **`jit-agents` (option F) was never run.** The question it carried over —
  *does a generated, task-specific prompt beat a routing table?* — is still open.
- **No eval task is a high-difficulty `edit`**, so the tier that selects
  `claude-opus-5-5` was never exercised as a dispatch arm.

## Design principles (settled 2026-10-12)

These were decided in `dev/orchestration/PLAN.md` and live only there, which is
about to be deleted. They are the frame every verdict above was reached in.

| principle | what it rules out |
|---|---|
| **All workloads are in scope** — interactive coding, research and reading, batch — and **a strategy is applied only where evidence shows it works** | enabling anything on plausibility. The eval was built to satisfy this clause, not to decorate the track |
| **The binding cost is frontier tokens and the user's attention.** Transfer to the user's AI ventures is a secondary value | optimising for token counts alone, and arms that buy a saving with more interruptions |
| **pi first.** Other harnesses wait | writing a generator per harness before one harness is measured |
| **`jit-agents` merged into this track** as an option to evaluate; `dev/jit-agents/` retired as a track | a second, parallel research track. It was never measured; see below |
| **`oh-my-opencode-slim` is the reference to measure against**, not a deletion | deleting a working orchestrator because it is not the one this system builds |
| **Local models reading local files is a future extension**: hardware may improve within ~6 months, and a local-model → local-files interface is valued as a **security layer** | sending repository content to a remote vendor when a local reader would do |

Orchestration is a **core feature**, not a utility: it has a subject in the
ontology, its own folders, and a name — [[the-loom]].

## Where orchestration lives, per harness

| harness | where | status |
|---|---|---|
| pi | `config/orchestration/` (roles, catalogue, tiers, bindings) + `engine/orchestration/` | the canonical home, harness-agnostic by decision 20 |
| opencode | `~/.config/opencode/oh-my-opencode-slim.json` (dotfiles), preset `deepseek` | used by hand and as the eval's reference arm |
| Claude Code | `.claude/agents/*.md`, plugin agents | outside this track |
| hermes | `delegation.*` in `config.yaml` | outside this track |

## Rejected before measuring (not reopened without new evidence)

- **Orchestrators as skills**: they bind to a model and a budget, and they route
  *into* the skill library, so a skill router would route to its own router.
  The Loom keeps roles as `config/orchestration/*.md` and the router in
  `selection.yaml`.
- **One quality scalar per model**: replaced by capabilities scored through
  their benchmarks (decision 21), and by measured `pass_rate` once
  [[the-loom]]'s labels reach 30 items.
- **A capability floor as a gate**: it left one eligible model for `edit` and
  none for `read`. Selection is policy instead (decision 27).
- **A hot model switch on failure**: it forfeits the prompt cache and changes
  `ran_model` mid-item. Escalation is a re-dispatch with context (decision 28).
