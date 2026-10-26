---
title: Multi-lens split
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-20
use_count: 0
last_used:
promoted_from: []
source: https://github.com/lilmgenius/paperthin — skills/mesh/prism/SKILL.md
supersedes:
related: [shower]
tags: [paperthin, review, judgement]
area: [B]
name: prism
description: "Split one artifact across 2 to 5 independent failure-mode lenses and return where they converge, where they split, and the single question that resolves the split. Never an average."
invocation: user
triggers: []
antitriggers: []
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/paperthin/skills/mesh/prism
upstream_pin: lilmgenius/paperthin@7d5dc62
license: MIT (© 2026 LilMGenius) — LICENSE in the clone
verified_log: [2026-10-20]
---

# Multi-lens split

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/paperthin/skills/mesh/prism/SKILL.md`
- **Pinned:** `lilmgenius/paperthin@7d5dc62`, tag `v0.17.7`. Refresh with
  `git -C ~/04_RESOURCES/Software/paperthin fetch`, check out the new commit,
  re-read the body, then re-run `familiar skills index`.
- **Licence:** MIT (© 2026 LilMGenius) — LICENSE in the clone.

## Reachability

**Human only.** Excluded from every router and from `../../../TRIGGERS.md`; the
model cannot see it or fire it on its own. Reached as `/prism` in each harness,
generated from this record.

## When NOT to use this

- **A diff, against repo standards and its spec** — `code-review`. That one
  runs fixed axes in parallel children; this one draws lenses for the artifact
  in hand and returns the open question instead of a findings list.
- **Whether the artifact reads to a stranger** — `shower`. Comprehension is one
  small lens here, not the question being asked.
- **The lenses would share one failure mode.** Two names for one failure is one
  lens; upstream's own rule is to merge them, and a two-lens run that agrees is
  a single opinion with extra steps.
- **You want a verdict.** The output is a picture of the disagreement and the
  question that resolves it, never a score, a majority, or an average.

## Local notes

- **User-invoked on purpose, upstream and here.** Plural lenses are an opt-in
  spend and their convergence must never pass as automatic proof. Firing it
  unasked would put a proof-shaped ritual in the model's reach.
- **No triggers and no antitriggers, by design.** `invocation: user` removes it
  from the trigger index entirely, so the vocabulary would be dead weight.
- **Cheap by construction.** The lenses run in this session, one line each.
  Where a lens needs an independent reader, hand it to a child (`pi -p -nc`);
  do not turn every lens into a subagent.
- **Where it pays here:** a SPECS.md before dispatch, a skill body before
  adoption, a design leaf before it becomes load-bearing.

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*
