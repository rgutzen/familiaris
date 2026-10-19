---
title: USER.md vs conventions/ — what goes where
summary: Filing into `config/practice/user/`, `config/practice/conventions/` or `knowledge/` — which store owns it
origin: authored
authority: agent
trust: trial
last_verified: 2026-09-03
use_count: 6
last_used: 2026-10-09
promoted_from: []
source:
supersedes:
related: [knowledge-vs-skills, memory-architecture, memory-mechanisms, context-budget]
tags: [user, conventions, filing, icm, layers]
scope: ["06_SYSTEM/memory/**"]
area: [B]
stability: stable
verified_log: [2026-09-03, 2026-08-31]
---

# USER.md vs conventions/ — what goes where

Six directive files describe the user and how to behave, and it is easy to
put a fact in the wrong one. This leaf is the filing rule. It is the sibling of
[[knowledge-vs-skills]]: same job, different pair.

## The three-way test

Ask in this order and stop at the first yes.

| # | Test | Home |
|---|---|---|
| 1 | Would this still be true if the user had never used an AI? | **`../../../../config/practice/user/user-identity.md`** |
| 2 | Does it govern the **exchange** — turn-taking, tone, disagreement, how much to ask? | **`../../../../config/practice/conventions/collaboration.md`** |
| 3 | Does it govern **text written into the user's system** — docs, leaves, commits? | **`../../../../config/practice/conventions/voice.md`** |
| 4 | Does it govern **code**, or what documentation must contain? | **`../../../../config/practice/conventions/code-style.md`** |

`../../../../config/practice/user/user-identity.md` is a *description of a person*. The three conventions are
*instructions to an agent*. That is the whole distinction, and it survives
cases the tests do not obviously cover.

## Why the split is not arbitrary: load cost

`../../../../config/practice/user/user-identity.md` is **Layer 1 — always loaded, every session, every harness**, under a
hard 1,375-char cap. `conventions/**` is **Layer 3 — loaded on entry to a
relevant task.** So the split is not only about meaning; it is about what every
session pays for.

> **Put a behaviour rule in `../../../../config/practice/user/user-identity.md` only when getting it wrong is
> unrecoverable.** Writing into `~/03_ZETTEL`, or sending personal material to
> a cloud model, cannot be undone by a later correction. Everything else —
> tone, hedging, how to disagree — is recoverable within the same turn, so it
> belongs in `../../../../config/practice/conventions/collaboration.md` and `../../../../config/practice/user/user-identity.md` carries at most a pointer.

The cap enforces this. When `../../../../config/practice/user/user-identity.md` overflows, the displacement rule sends
the overflow into a `knowledge/` leaf; in practice that leaf is almost always
one of the three conventions.

## What belongs in each

### `../../../../config/practice/user/user-identity.md` — who they are
Identity and domain · what they work on · environment (machine, OS, harnesses,
editors) · values that shape decisions · **hard data boundaries**, because
those are the unrecoverable ones · one pointer line naming `../../../../config/practice/conventions/`.

Filing doctrine: a behaviour rule belongs in USER.md **only when getting it
wrong is unrecoverable** (writing into `~/03_ZETTEL`, sending personal data to
a cloud model). Tone/how-to-disagree is recoverable in-turn and lives in
`../../../../config/practice/conventions/`. Never restate a rule that has a canonical home — a pointer line
is the replacement, not a paraphrase.

### `../../../../config/practice/conventions/collaboration.md` — how to interact
Role division (who holds scientific judgment) · prohibited moves (praise,
uncritical agreement, superlatives) · preferred formulations · how to present
options and trade-offs · how to correct yourself · when to ask versus decide ·
how much to verify before asserting.

### `../../../../config/practice/conventions/voice.md` — how text written *into the system* reads
House style for durable artifacts, **not** a mimicry profile for writing as the
user — see `../../../../config/practice/conventions/voice.md` §Scope. Register in conversation is `../../../../config/practice/conventions/collaboration.md`.
Sentence shape · how a rule is stated (with its reason attached) · how limits
are expressed · commit-message shape · what is absent from the register ·
recorded **non**-rules, such as "spelling is mixed; do not normalise it".

### `../../../../config/practice/conventions/code-style.md` — how the code reads
Priority order · composition · the solution hierarchy · scientific correctness
· performance · what a docstring must *contain*.

**Where `../../../../config/practice/conventions/voice.md` and `../../../../config/practice/conventions/code-style.md` meet:** a docstring is both. `../../../../config/practice/conventions/voice.md`
governs how its sentences read; `../../../../config/practice/conventions/code-style.md` governs what it must contain
(Diátaxis, parameters with units). Neither restates the other.

### `../../../../config/practice/user/user-voice.md` — how text published *under the user's name* reads

Added 2026-08-31 (was `MY-VOICE.md`). Distinct from `../../../../config/practice/conventions/voice.md`, and the pair is
the easiest mis-file in the set:

| | `../../../../config/practice/conventions/voice.md` | `../../../../config/practice/user/user-voice.md` |
|---|---|---|
| Governs | text written **into the system** — leaves, commits, docs | text published **under the user's name** — essays, papers, talks, correspondence |
| Is | house style for an agent's own output | a profile of how *this person* writes |
| Failure | a leaf that reads like marketing | a draft that does not sound like them |

Extracted from eleven self-written samples rather than from self-report, on the
same principle the interview method uses: **ranked examples beat adjectives**,
because people describe their own style unreliably. `trust:` records whether it
is ratified; it was ratified 2026-08-31.

**The standing rule lives in the file itself: an agent drafts, the user
approves before anything is sent or published.**

### `../../../../config/practice/user/user-mission.md` — what the user is *for*

Added 2026-08-31 (was `MISSION.md`), distilled from the user's own mission
manifest. Not a behaviour rule and not a description of working style: it is
the standing *why* that a long-running task can be checked against. Consulted
when a decision turns on priorities rather than on facts, which is why it is
not in the always-loaded layer.

## Which of the six is loaded when

| File | Layer | Cost |
|---|---|---|
| `../../../../config/practice/user/user-identity.md` | 1 — always, every session, every harness | hard cap 1,375 chars |
| `../../../../config/practice/conventions/collaboration.md`, `../../../../config/practice/conventions/voice.md`, `../../../../config/practice/conventions/code-style.md` | 3 — on entry to a relevant task | free until read |
| `../../../../config/practice/user/user-voice.md` | 3 — only when drafting under the user's name | free until read |
| `../../../../config/practice/user/user-mission.md` | 3 — only when a decision turns on priorities | free until read |

Nothing was added to Layer 1 by either new file, which is the point: the
always-loaded budget did not move.

## Known duplication, 2026-08-31 — resolved 2026-09-02/03

`../../../../config/practice/user/user-identity.md` §"How to work with them" restated `../../../../config/practice/conventions/collaboration.md` §Working style
almost verbatim — verify before asserting, say plainly when broken, keep
corrections brief. Both files are directive, so the fix was a **proposal**:

> Replace the paragraph with a pointer. It is ~230 chars of the 1,375 cap
> spent on a fact that already has a canonical home, and by test 1 it fails —
> it is an instruction to an agent, not a fact about a person.

**Resolved.** `../../../../config/practice/conventions/collaboration.md` was rewritten 2026-09-02 (its §Working style
was removed in the voice-style pass, commit `08f62e2`), and `../../../../config/practice/user/user-identity.md` now
carries one pointer line — "**How to work with them.** → .../collaboration.md" —
with no restated rules. The duplication this section warned about no longer
exists; it is kept as history because it is the worked example of the failure
`knowledge/CONTEXT.md` rule 1 names (one canonical home per fact).

## Cross-links

`related:` is bidirectional across `knowledge/**`, so every edge below must
exist in both files. `../../../../config/practice/user/user-identity.md` is not a leaf and has no frontmatter — it links
by naming paths in its prose.

```
USER.md ──────▶ conventions/            (one pointer line; outward only)

collaboration.md ◀──▶ voice.md          how the agent presents itself
collaboration.md ◀──▶ code-style.md     objective assessment applies to review
voice.md         ◀──▶ code-style.md     docstrings are prose and code

skills/**  ─────▶ conventions/**        skills CITE knowledge
conventions/** ─╳─▶ skills/**           never the reverse
```

**One violation currently exists.** `../../../../config/practice/conventions/code-style.md` has
`related: [research-software-engineering]` — a knowledge→skill link, which
[[knowledge-vs-skills]] forbids and which is redundant: that skill already
cites the leaf in its §Knowledge this cites. Directive; proposed, not
removed.

## Verification

```bash
wc -c ~/06_SYSTEM/memory/USER.md            # < 1375
# any behaviour rule in USER.md that is not a hard boundary is misfiled:
grep -nA3 'How to work with' ~/06_SYSTEM/memory/USER.md
# knowledge must never point at a skill:
grep -rn '^related:' ~/06_SYSTEM/memory/knowledge --include='*.md' \
  | grep -oE '\[.*\]' | tr -d '[]' | tr ',' '\n' | sed 's/ //g' | sort -u \
  | while read n; do [ -n "$n" ] && find ~/06_SYSTEM/memory/skills -type d -name "$n" \
  | grep -q . && echo "knowledge -> skill: $n"; done
```
