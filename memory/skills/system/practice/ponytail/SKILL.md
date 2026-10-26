---
title: Ponytail — lazy senior dev mode
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-18
use_count: 0
last_used:
promoted_from: []
source: https://github.com/DietrichGebert/ponytail — skills/ponytail/SKILL.md
supersedes:
related: [research-software-engineering, ponytail-audit]
tags: [engineering, minimalism, yagni, deletion]
area: [B]
name: ponytail
description: "Subtraction axis for coding: the smallest complete change, deletion over addition, and the request questioned in ultra."
invocation: model
triggers: [ponytail, be lazy, laziest senior dev, yagni, smallest change, smallest solution, simplest solution that works, over-engineered, scope creep, speculative feature, don't add features]
antitriggers: [research software, building block, reusable component, generalise, api design, refactor pipeline, spike, debug a failure, write a test]
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/ponytail/skills/ponytail
upstream_pin: DietrichGebert/ponytail@09c434a
license: MIT — LICENSE in the clone
verified_log: [2026-10-18]
---

# Ponytail — lazy senior dev mode

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/ponytail/skills/ponytail/SKILL.md`
- **Pinned:** `DietrichGebert/ponytail@09c434a` (2026-10-18). Refresh with
  `git -C ~/04_RESOURCES/Software/ponytail fetch --depth 1`, check out the new
  commit, re-read the body, then re-run `familiar skills index`.
- **Licence:** MIT.

## Reachability

Model- or human-reachable. Routed by the terms in `triggers:` above.

## When to use this

Writing, fixing or refactoring application and automation code, where the
failure mode is *addition*: extra options, speculative features, wrappers,
"for later" scaffolding, a dependency for six lines. The upstream triggers are
narrow on purpose — the model reaches for it when the user's own vocabulary
says "be lazy", or when a change is visibly growing past its job.

## When NOT to use this

- **Research software where generalisation is the requirement.** See the
  tension below; `research-software-engineering` and the solution hierarchy in
  `../../../../../../config/practice/conventions/code-style.md` govern there.
- **Diagnosing a failure** → `systematic-debugging`. Ponytail shortens the fix,
  it does not find the fault.
- **Reviewing a finished change** → `code-review`. Related but a different
  reflex, and its triggers are disjoint.

## Local notes

**What this adds.** `code-style.md`'s solution hierarchy (L0 reorganisation …
L7 new abstraction) governs *how much new structure* to build. It has no level
for *"nothing should exist"*. That is the gap ponytail fills: its ladder starts
at "does it need to exist?" and it ranks deletion above addition. The two ladders
compose — read ponytail's first, then descend code-style's.

**The tension, do not paper over it.** `code-style.md` asks for *building
blocks*: reusable, flexible components, both a high-level convenience function
and low-level blocks, explicit assumptions. Ponytail asks for the minimum that
solves today's task and no configurability. Both are right about different
objects — ponytail about *an existing repo growing*, code-style about *a library
whose whole purpose is reuse*. When they conflict, code-style wins and the
`antitriggers` above are what stop ponytail firing; if it fires anyway and the
change is genuinely a building block, say so and build the block.

**Session persistence is not adopted.** Upstream says the mode is active "for
the whole session until the user says stop ponytail". Not here: this skill
applies to the change at hand and ends with it. A disposition that silently
outlives the task would contradict `authority: agent` — it would apply a style
the user did not ask for to work they did not want it applied to.

**`shortcut:` comment convention is in force** — `shortcut: <the limit>,
<when to upgrade>` — for shortcuts taken under this skill. Nothing writes those
markers yet, so `ponytail-debt` was not adopted alongside; when markers start
appearing, adopt that ledger.

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*
