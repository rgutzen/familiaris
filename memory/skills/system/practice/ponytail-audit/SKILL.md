---
title: Ponytail audit — whole-repo ranked report
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-18
use_count: 1
last_used: 2026-10-24
promoted_from: []
source: https://github.com/DietrichGebert/ponytail — skills/ponytail-audit/SKILL.md
supersedes:
related: [ponytail]
tags: [engineering, audit, bloat, deletion, repo-health]
area: [B]
name: ponytail-audit
description: "Whole-repo one-shot report: bugs, risk, load, missing tests, speed, and what to delete, merge or split — ranked, changes nothing."
invocation: model
triggers: [ponytail audit, audit this codebase, audit this repo, whole repo audit, repo quality audit, find bloat, what can I delete, dead code sweep, what should go, codebase has grown]
antitriggers: [code review, review the diff, review my changes, leakage audit, paper review, literature review, refactor pipeline, spike]
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/ponytail/skills/ponytail-audit
upstream_pin: DietrichGebert/ponytail@09c434a
license: MIT — LICENSE in the clone
verified_log: [2026-10-18]
---

# Ponytail audit — whole-repo ranked report

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/ponytail/skills/ponytail-audit/SKILL.md`
- **Pinned:** `DietrichGebert/ponytail@09c434a` (2026-10-18). Refresh with
  `git -C ~/04_RESOURCES/Software/ponytail fetch --depth 1`, check out the new
  commit, re-read the body, then re-run `familiar skills index`.
- **Licence:** MIT.

## Reachability

Model- or human-reachable. Routed by the terms in `triggers:` above.

## When to use this

A repo has grown and nobody knows what in it still earns its keep: "audit this
repo", "what can I delete", "this has grown out of control". Also when a
whole-repo sweep is wanted rather than a diff review.

## When NOT to use this

- **Reviewing a change** → `code-review` (standards + spec fidelity) or
  `ponytail` (which is the per-change reflex; this is the periodic sweep).
- **Module shape and seams** → `improve-codebase-architecture`. It surveys for
  deepening opportunities and is `invocation: user`; this one surveys for what
  is wrong or unnecessary. Different question, adjacent answer.
- **A typed claim-checking pass** → `factchk`.

## Local notes

**Scope the audit to this machine's repos.** Upstream assumes an application:
users, auth, money, background jobs, real load. Most targets here are personal
automation — one user, one process, cron. Answer its §1 load question
explicitly ("assumed load: one person, one process") and let that *demote* the
Scale and Risk groups rather than inventing findings for them. The lean group is
the one that pays here, and it is upstream's sixth of six — promote it to first
when the user's ask was bloat.

**It is a report, not a cleanup.** Upstream changes nothing, deliberately.
Every finding it produces is a to-do that competes with everything else, so the
report decays into shelfware unless the user immediately names the two or three
findings to act on. When this skill returns, ask which findings to fix in the
same turn; do not file the report and move on.

**Determinism beats the recurring judgement call.** A repo-wide lean sweep is a
recurring action, and this skill is a model judgement executed each time. Its
*findings* are the cheap part: dead code is detectable by tooling (`vulture` for
Python, `knip` for JS/TS, `shellcheck` plus unused-function greps for shell). If
this skill is used more than twice on the same repo, the proposal is to stop
auditing and add the mechanical detector to a check, then let this skill handle
only what the detector cannot see — duplication, one-implementation interfaces,
pass-through wrappers.

## Usage outcomes

**2026-10-24 — audited `06_SYSTEM` (whole repo, 1669 files, 69.5k lines of
Python).** Helped, unevenly. The value was in its *order*: putting correct and
safe ahead of lean turned up a live hole in the boundary guard's delete
vocabulary (four bulk-delete spellings pass with no prompt) that a
bloat-first sweep would not have looked for. The lean group, which was the
reason for the run, produced nothing — but only after its §3 rule ("grep the
whole tree before calling code unused") rejected four false positives that
the mechanical detectors handed over: 32 vulture hits routed by string in
`engine/familiar`'s ROUTES table, a `remote_*` provider-seam contract, two
loader functions called from `pazras.sh`, and a `dev/**/src` copy that is a
pinned eval fixture. That rule is the reason to keep this skill.
