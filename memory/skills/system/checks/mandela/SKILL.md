---
title: Leakage audit
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-20
use_count: 0
last_used:
promoted_from: []
source: https://github.com/lilmgenius/paperthin — skills/depth/mandela/SKILL.md
supersedes:
related: [factchk]
tags: [paperthin, verification, eval, science]
area: [B]
name: mandela
description: "Audit an eval, metric or experiment for leakage: does independent ground-truth enter, or are model, scorer and designer only confirming each other? Returns only the patterns that fire, each with an independence fix. Read-only."
invocation: model
triggers: [data leakage, leakage audit, is my eval leaky, holdout validity, benchmark validity, how will we know it worked, eval is too clean, validation independence]
antitriggers: [code review, review the diff, fact check, literature review, peer review, statistical power, unit test]
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/paperthin/skills/depth/mandela
upstream_pin: lilmgenius/paperthin@7d5dc62
license: MIT (© 2026 LilMGenius) — LICENSE in the clone
verified_log: [2026-10-20]
---

# Leakage audit

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/paperthin/skills/depth/mandela/SKILL.md`
- **Pinned:** `lilmgenius/paperthin@7d5dc62`, tag `v0.17.7`. Refresh with
  `git -C ~/04_RESOURCES/Software/paperthin fetch`, check out the new commit,
  re-read the body (a pulled body is unreviewed text), then re-run
  `familiar skills index`.
- **Licence:** MIT (© 2026 LilMGenius) — LICENSE in the clone.

## Reachability

Model- or human-reachable; routed by the terms in `triggers:` above.

## When NOT to use this

- **Reviewing a change for defects** — `code-review`.
- **Checking whether a sentence is true** — `factchk`; this audit asks whether a
  *measurement* can be independent, not whether a claim holds.
- **Judging whether a study has enough power** — a different axis. Power and
  leakage fail separately; a leaky holdout with α=0.05 does not become sound
  when powered.
- **The knowledge tree's internal consistency** — `familiar consolidation
  conflicts` and `familiar context links` are the mechanical checks; this is
  for a validation design, not a document set.

## Local notes

- **Read-only, and it stays that way.** The fix for every pattern it names is a
  change to the experiment, which is the owner's decision.
- **Boundary judgement, 2026-10-20: the eight patterns stay in the upstream
  body as its steps.** They are not promoted to a knowledge leaf. A checklist
  you run is procedural; it moves to `knowledge/areas/` the day a second skill
  needs the same list, and not before.
- **The fresh-context auditor is available here.** Where the body offers one
  blind `N=1` re-run of the taxonomy, use a child (`pi -p -nc`, or `pi-agent`
  with the `review` role for a diff-shaped input). A cheap reader is enough: the
  taxonomy is the instruction, and the blindness is the value.
- **Where it earns its keep on this machine:** `familiar orchestration eval`'s
  own judgments, any train/holdout split in a paper under review, and an A/B
  whose result arrives too clean.

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*
