---
title: Single source of truth repair
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-20
use_count: 0
last_used:
promoted_from: []
source: https://github.com/lilmgenius/paperthin — skills/breadth/ssotize/SKILL.md
supersedes:
related: [adopt-skill]
tags: [paperthin, ssot, consolidation]
area: [B]
name: ssotize
description: "Find where one fact lives, get approval for the consolidation plan, then collapse the scattered copies into one home and reference it. Starts read-only; mutates only after approval."
invocation: model
triggers: [source of truth, single source of truth, deduplicate, duplication across files, scattered copies, one canonical home, find the canonical, same fact in several places, drifted copies]
antitriggers: [nightly pass, consolidation queue, promotion, ranking, code review, review the diff, literature review, delete duplicates]
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/paperthin/skills/breadth/ssotize
upstream_pin: lilmgenius/paperthin@7d5dc62
license: MIT (© 2026 LilMGenius) — LICENSE in the clone
verified_log: [2026-10-20]
---

# Single source of truth repair

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/paperthin/skills/breadth/ssotize/SKILL.md`
- **Pinned:** `lilmgenius/paperthin@7d5dc62`, tag `v0.17.7`. Refresh with
  `git -C ~/04_RESOURCES/Software/paperthin fetch`, check out the new commit,
  re-read the body, then re-run `familiar skills index`.
- **Licence:** MIT (© 2026 LilMGenius) — LICENSE in the clone.

## Reachability

Model- or human-reachable; routed by the terms in `triggers:` above.

## When NOT to use this

- **The nightly consolidation pass** — `familiar consolidation run`, its queue
  and its conflicts stage. That is automatic and confined to
  `memory/knowledge/`; this is manual and spans any artifact.
- **A fact that has drifted stale** — one copy, wrong content. That is a
  rewrite of the home, not a consolidation of copies.
- **One copy with no second home.** An empty audit is the correct result;
  never invent scatter to justify the pass.
- **A knowledge leaf that links a skill.** That is the one declared direction
  ([[knowledge-vs-skills]]), not duplication.

## Local notes

- **The rule this executes is already knowledge; the record does not restate
  it.** `[[knowledge-vs-skills]]` owns the fact/procedure split, and the
  generated routers (`familiar knowledge index`, `familiar skills index`) are
  what make one home *enforced* for the leaves. What was missing is the repair
  procedure for a fact that lives in several artifacts, and that is what this
  adds.
- **Two-method re-enumeration is the step most likely to be skipped, and it is
  the one that pays.** A synonym the first sweep missed is exactly the copy that
  survives a consolidation and goes stale alone.
- **The approval gate is not decorative.** It is the only thing separating this
  from a script that deletes copies; keep step 8 before step 9 unconditionally.
- **Contradictions are not duplicates.** Two copies that disagree need the
  user's call on which value is true; a silent pick is a fabricated fact with a
  citation to itself.
- **Scope here:** configs, conventions, SPECS, skills and docs. Never a
  `03_ZETTEL` path — no read, no write.

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*
