---
title: Memory-poisoning posture
summary: Why an injected claim cannot become this system's belief — five structural checks, and their limits
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-24
verified_log: [2026-10-24, 2026-09-11]
use_count: 3
last_used: 2026-10-16
promoted_from: []
source: arXiv 2607.06595, arXiv 2606.24775
supersedes:
superseded_by: []
contradicts: []
related: [memory-architecture, memory-mechanisms, consolidation-cycle, prior-art-memory-systems, boundaries, journal-index, publication-model]
tags: [security, memory, poisoning, injection, provenance, trust, consolidation]
triggers: [memory poisoning, prompt injection, indirect injection, trust promotion, provenance, unreviewed write access, curator authority, distilled_by, posture check]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving
---

# Memory-poisoning posture

**The threat.** Persistent, auto-written memory converts a *one-shot* prompt
injection into a *stateful* compromise: text an attacker got into one session
is distilled, stored, and read back later as this system's own belief
(arXiv 2607.06595). The input is not hypothetical — every staged transcript
quotes web pages, repositories, issue threads and tool output, and stage 1
sends all of it to a model whose answer is committed unattended. That model is
`config/profile.yaml`'s `models.consolidation`, and it ships **local** (P5): a
fresh clone discloses nothing, and pointing it at a provider is a deliberate act
with a stated cost, never a default.

**The posture is authority, not detection.** There is no reliable classifier
for "this paragraph is an injection", and a check claiming to be one would
manufacture exactly the distractor noise this posture exists to remove — the same
reasoning that stops stage 5d guessing at semantic contradictions. So nothing
here scans text for badness. What is checked is the structure that makes a
successful injection **inert**.

## The five properties

`familiar consolidation posture` (also run inside stage 8, findings into the report and
the brief). Each is a fact about paths and provenance, and each fails loudly.

| # | Property | Why it is the one that matters | Where it is enforced |
|---|---|---|---|
| 1 | Nothing machine-written is injected | An injected claim must still be *fetched* by a model that chose to | L2 removed blanket injection; the check intersects `ALWAYS_LOADED` with what pass commits have written |
| 2 | Promotion is human-gated | `trust: trusted` is what turns provisional text into established fact | `frontmatter.set_fields` raises `PromotionRefused`; every stage goes through it |
| 3 | The curator never edits prose unattended | The one route from a model's words to a leaf's body runs through a person applying a patch | every pass commit under `knowledge/**` must be a frontmatter change |
| 4 | The pass writes no human-owned path | `user/**`, `conventions/**`, `boundaries/**` are directive; `ROADMAP.md` is editable when a human is watching and closed to the pass, which has no one to flag an edit to | checked against history, not against the `OFF_LIMITS` tuple that claims it |
| 5 | Machine-written journal entries are marked | Lets retrieval tell a session the text is an unreviewed distillation | `distilled_by:`; surfaced per hit by `journal_search`'s `provenance` field |

Properties 1–4 make a poisoned claim inert. Property 5 makes it **survivable**
rather than merely rare: a reader who is told which text was never reviewed can
apply the right scepticism to it.

## Two asymmetries the design rests on

**Demotion is safe to automate; promotion is not.** Every trust transition the
pass performs is downward — stage 5d marks a superseded leaf `deprecated`,
stage 6 proposes one step down. The worst case of a wrong demotion is a true
claim read with too much caution. The worst case of a wrong promotion is
unreviewed text re-labelled as ratified, which is precisely the step that
converts an injection into a standing belief. Hence the gate sits at the single
write path rather than being asked for in each stage's prose.

**A directive is dangerous; a record is not.** `journal/**` is written
unattended and is fully searchable, so it is the one large machine-written
corpus a session reads. It is safe only because it is an *episodic record* —
what was said, on a date, by a session. The MCP server says this in its
instructions and per result, because the property is not self-evident from a
snippet: a distilled bullet reads exactly like an instruction if nothing says
otherwise.

## What this does NOT cover

State the limits, or the checks become a claim they cannot support.

- **It does not mean no transcript carried an injection.** It means an injected
  claim cannot reach a prompt unasked, cannot label itself trusted, and cannot
  become leaf prose without a human applying a patch.
- **A human who applies `report --patch` unread has bypassed property 3.** The
  gate is a person reading a diff; nothing enforces that they read it. This is
  the largest residual exposure and it is a process risk, not a code one.
- **Stage 1 sends transcript text to whatever model the profile names.** Under
the shipped local default nothing leaves the machine; a provider's model is
faster and distils better, and the difference is that the reading is disclosure
to a third party. Handled separately by `replay._excluded_paths` reading the
compiled boundaries, not by anything here.
- **Property 4 is checked over the last 60 pass commits**, not all history. One
  historical breach is known and recorded: 2026-08-31 (`86ddb90`) wrote
  `verified_log:` into three convention leaves, because the conventions then
  lived *inside* `knowledge/`. Moving them out of the scored tree is what fixed
  it — a structural fix, not a rule. The check reports it at `warn` and says so.
- **`authority: human` leaves inside `knowledge/**` still receive mechanical
  frontmatter** (`use_count`, `last_used`, `verified_log`). This is sanctioned
  by `consolidation-cycle.md` §Status, where `verified_log` is listed under
  *Applies*; `authority: human` is never-touched at stage 6 specifically. Not a
  contradiction, but the two rules are easy to read as one.

## Do not swap in a memory product

Rejected by this posture's line and in `prior-art-memory-systems.md`: no
architecture dominates (arXiv 2606.24775, 12 systems / 5 workloads / 11
datasets), and Mem0 / Zep / MemOS each reinstate the authority inversion these
five checks exist to prevent — an LLM curator with unreviewed write access to
every future prompt. That configuration is what the 2026-09-10 re-evaluation
measured and removed.

## Verification

```bash
familiar consolidation posture            # exit 0 clean or warn-only, 3 on a failure
cd ~/06_SYSTEM/engine/consolidation && python -m pytest engine/consolidation/tests/test_posture.py -q
```

A security check that has never been seen to fail is a comment: every property
above is exercised in `engine/consolidation/tests/test_posture.py` on a tree where it is **broken**
as well as one where it holds.
