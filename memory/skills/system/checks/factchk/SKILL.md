---
title: Claim check, both directions
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-20
use_count: 0
last_used:
promoted_from: []
source: https://github.com/lilmgenius/paperthin — skills/depth/factchk/SKILL.md
supersedes:
related: [mandela]
tags: [paperthin, verification, claims]
area: [B]
name: factchk
description: "Verify a claim asserted as real against sources in both directions before it ships: could the absurd be real, could the obvious be false? Fixes the mechanically clear errors and flags the judgment calls."
invocation: model
triggers: [fact check, fact-check this, verify this claim, is this actually true, double check the facts, check that against reality, could that be real, is that claim true]
antitriggers: [cite the sources, primary sources, code review, review the diff, literature review, data leakage, run the tests, debug this]
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/paperthin/skills/depth/factchk
upstream_pin: lilmgenius/paperthin@7d5dc62
license: MIT (© 2026 LilMGenius) — LICENSE in the clone
verified_log: [2026-10-20]
---

# Claim check, both directions

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/paperthin/skills/depth/factchk/SKILL.md`
- **Pinned:** `lilmgenius/paperthin@7d5dc62`, tag `v0.17.7`. Refresh with
  `git -C ~/04_RESOURCES/Software/paperthin fetch`, check out the new commit,
  re-read the body, then re-run `familiar skills index`.
- **Licence:** MIT (© 2026 LilMGenius) — LICENSE in the clone.

## Reachability

Model- or human-reachable; routed by the terms in `triggers:` above.

## When NOT to use this

- **Producing cited research** — `primary-source-research`. That skill gathers
  and lands findings; this one audits claims already made.
- **A deliberate fiction or an in-world premise** — flag it if it is unclear,
  never "correct" it. Upstream names this as its hardest call and it is.
- **A claim about the requester's intent** — that is reading the instruction,
  not checking the world.
- **Reviewing a change for defects** — `code-review`.

## Local notes

- **It executes `collaboration.md` §Verify and calibrate confidence.** That
  convention owns *how much* to verify and *how to label* the result (named
  source, epistemic label, dependency, counterfactual). This one owns *the act*
  of checking, and its addition is direction: priors fail both ways, so a claim
  that feels absurd gets checked as hard as one that feels obvious.
- **The two directions are not symmetric in practice.** The "obvious is false"
  half is the one that fires here: a length, a date, a licence term, an
  attribution carried across files because it was plausible.
- **Fix versus flag is the rule worth keeping.** A clear error (wrong date,
  dead URL, misattributed source) is corrected with the citation; a contested
  or interpretive claim is surfaced, never silently rewritten.
- **Its research child:** the `research` role (`pi-agent research`) returns
  verbatim extracts with URLs. `factchk` is what decides whether the result is
  enough to call a claim verified, so the two compose without overlap.

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*
