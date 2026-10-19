---
title: Knowledge vs skills
summary: Filing something new: a claim goes in knowledge, a procedure in a skill
origin: authored
authority: human
trust: trusted
last_verified: 2026-08-30
use_count: 2
last_used: 2026-09-01
promoted_from: []  # originated 2026-08-28; no journal entry for that session
source:
supersedes:
related: [memory-ranking, skill-routing, memory-architecture, obsidian-vault, orchestrators, skill-adoption, user-vs-conventions, voice, file-naming, glossary]
tags: [knowledge, skills, architecture, icm]
scope: ["06_SYSTEM/**"]
area: [B]
stability: stable
verified_log: [2026-08-30]
---

# Knowledge vs skills

Both are markdown leaves with frontmatter, generated routers and a lifecycle.
They are still **separate stores**. This leaf says why, and where the line runs.

## The distinction

| | Knowledge | Skill |
|---|---|---|
| Asserts | *this is true* | *do this, then this* |
| Loaded to | inform reasoning | govern a sequence |
| Verified by | **correspondence** — check the world | **outcome** — run it |
| Primary decay signal | staleness (`last_verified`) | disuse (`use_count`) |
| Acquired | in one shot | through repetition |
| Mis-retrieval costs | inert noise, outweighed by context | **active hijack**, with side effects |
| ICM layer | 3 — reference, "what rules apply" | 2 — process, "what do I do" |

The blast-radius row is why skills carry `antitriggers` and knowledge does not.
A wrong fact is diluted by surrounding context; a wrongly-fired procedure takes
over and acts.

## The boundary rule

> **Knowledge is what a skill reads.**

A skill holds the *procedure* and cites knowledge leaves for the *facts*.
Never duplicate — reference. Direction is one-way (ICM Pattern 3): skills point
at knowledge; knowledge never points at skills.

Worked example. [[opencode]] holds the harness traps — the
`config.json` at the wrong path is silently ignored, an unknown custom provider
falls back to OpenAI's upstream and 401s. A `debug-opencode-provider` skill
holds the diagnostic procedure and cites that leaf. If the traps appear in
both, one is wrong and nobody knows which.

Filing test, in order:

1. Does it have steps? → skill
2. Is it a claim that could be checked against the world? → knowledge
3. Both? → knowledge leaf for the facts, skill for the procedure, skill cites leaf
4. Neither — an always-on disposition, like tone or code style? → knowledge,
   under `../../../../config/practice/conventions/`

Case 4 is the genuine grey area. `../../../../config/practice/conventions/voice.md` is arguably procedural,
but it is never *invoked* — it is an always-loaded constraint, not a sequence.
Dispositions are knowledge.

**The rule is detected, not declared in a key.** A knowledge leaf that links a
skill is proposed nightly as a `knowledge→skill link` item
(`engine/consolidation/stages/associate.py`), and a human decides it in the
queue. A `cites:` frontmatter key was planned to carry the same rule and was
dropped (user, 2026-10-09): nothing would write it, and a key with no writer is
decoration. Do not add it back without a writer.

## Why not merge them

Principled: verification differs, so lifecycle differs, so they cannot share a
maintenance policy. `the prune stage` must ask different questions of each.

Practical, and decisive: **skills are a harness primitive.** Claude Code
discovers `SKILL.md`; hermes has bundles, slash dispatch and a skills hub.
Merging into `knowledge/` forfeits native integration with all three harnesses.

## What they share — the leaf contract

Every memory object of either type carries this core:

```yaml
origin:        authored | imported | learned | derived
authority:     human | agent          # who may edit
trust:         quarantine | trial | trusted | deprecated
last_verified:                        # correspondence signal
use_count: 0                          # utility signal
last_used:
promoted_from: []                     # RESOLVABLE journal paths, not prose
supersedes:
related: []                           # bidirectional for knowledge
tags: []
scope: []                             # path globs — retrieval prior, never a filter
area: []                              # Area codes A-P
```

`scope:` and `area:` moved into the shared core on 2026-08-30: knowledge needs
the same positional signal skills already had. Both feed the spatial prior in
[[memory-ranking]].

**Both types carry both signals.** They differ only in which is *primary* for a
lifecycle decision:

- A knowledge leaf that is never retrieved is a pruning candidate; one that
  fails verification is a **correction** candidate.
- A skill that is never used is a pruning candidate; one that references a dead
  API is a **repair** candidate, however often it is invoked.

Type extensions on top of the core:

- Knowledge adds `stability` — how fast this class of fact rots. Four values
  since 2026-08-30 (`permanent`/`stable`/`evolving`/`volatile`), not two.
- Skills add `triggers`, `antitriggers`, `platforms`,
  `requires_tools` — the routing surface. (`category` was one of them until
  O6b deleted it: the subject is the path in both trees, so no field is left
  to disagree with the folder.) Since skills are no longer installed
  into any harness ([[skill-routing]] §Zero-install), this frontmatter is the
  *only* way a skill is found, so it is not optional.

## A frame that predicts the rules

The three stores map onto declarative, procedural and episodic memory, and the
mapping predicts retention rules that were arrived at independently:

| Store | Type | Predicted rule | Rule as written |
|---|---|---|---|
| `journal/` | episodic | append-only, never revised | "never rewrite or delete an entry" |
| `knowledge/` | semantic | consolidated from episodic, freely revised | "distillation flows upward" |
| `skills/` | procedural | acquired by repetition, resists revision | hermes builds skills from *repeated actions* |

Treat this as a design heuristic, not a claim about brains: when a decision
feels arbitrary, ask which memory type the object belongs to and let the
retention physics follow.

## Verification

Grep for any fact appearing in both a knowledge leaf and a `SKILL.md`. If one
exists, the skill should cite instead of restate.
