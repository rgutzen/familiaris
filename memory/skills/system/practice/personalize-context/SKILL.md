---
title: Personalise the always-loaded context
origin: authored
authority: human
trust: trial
last_verified: 2026-08-31
use_count: 5
last_used: 2026-10-09
promoted_from: []
source:
supersedes:
related: []
tags: [user, conventions, interview, meta]
area: [B]
name: personalize-context
description: Interview the user so they can write USER.md and the conventions leaves in their own words.
triggers: [personalise user.md, personalize user.md, edit user.md, write my conventions, voice.md, collaboration.md, tune my context, who am i file, agent should know about me]
antitriggers: [adopt a skill, write a skill, prompt engineering, knowledge leaf, journal entry]
scope: ["06_SYSTEM/memory/**"]
platforms: []
requires_tools: []
mode: authored
verified_log: [2026-08-31]
---

# Personalise the always-loaded context

## When to use this

The user wants to write or revise `../../../../../config/practice/user/user-identity.md`, `../../../../../config/practice/conventions/collaboration.md` or
`../../../../../config/practice/conventions/voice.md` — the directive files that describe them and govern
how you behave.

## When NOT to use this

Filing a *fact* into the tree — that is [[knowledge-vs-skills]]. Writing a new
skill — that is `adopt-skill`. Editing `../../../../../config/practice/conventions/code-style.md`, which is derived from
their RSE guide rather than from an interview.

## Knowledge this cites

- [[user-vs-conventions]] — the filing rule and
  the cross-link map. **Read it before step 1.**
- `../../../../../config/practice/conventions/voice.md` §Scope — voice is house style for
  artifacts, not a mimicry profile.

## The one rule

> **You interview. They write.** These files are directive and their value is
> that the words are theirs. Never draft a paragraph and ask them to approve
> it — that gets you their assent to your phrasing. Ask, transcribe **verbatim**,
> and read it back.

Do not edit any of the three files yourself unless they say "write that".

## Instructions

**1 · Read, then audit — do not propose yet.**
Read all three files plus [[user-vs-conventions]]. Apply its four-way test to
every existing paragraph and show one table: *paragraph → current file → test
says → misfiled?* Nothing else. Let them react before going further.

**2 · Do one file per sitting.** Order: `../../../../../config/practice/user/user-identity.md`, then `../../../../../config/practice/conventions/collaboration.md`,
then `../../../../../config/practice/conventions/voice.md`. Each is short; three at once produces mush.

**3 · `../../../../../config/practice/user/user-identity.md` — ask four questions, no more.**
- In one sentence, what are you working on that an agent should know?
- What would an agent get wrong about your setup if it assumed defaults?
- Which boundaries, if crossed, **cannot be undone**?
- What else did you nearly say — and could it be a pointer instead?

Cap is **1,375 chars**. Read the count back after each answer. At the cap,
displace into a leaf and leave one pointer line; never truncate.

**4 · `../../../../../config/practice/conventions/collaboration.md` — ask about failure, not preference.**
People describe their preferences badly and their irritations well.
- Show me a recent agent reply that annoyed you. What was wrong with it?
- When should I ask you versus decide myself?
- How much should I verify before asserting something?
- How should I tell you that you are wrong?

**5 · `../../../../../config/practice/conventions/voice.md` — ask for examples, never for adjectives.**
Self-reported style is unreliable; ranked samples are not.
- Name two files here you would be glad an agent had written, and two you
  would not. Then *you* extract what differs — do not ask them to.
- What must never appear in text written into your system?
- Confirm the scope: this is house style for artifacts, **not** you-mimicry.

Check any proposed rule against the corpus before writing it down. M1 found
British/American spelling runs ~50/50, so "always use -ise" would have been
invented. **A recorded non-rule is worth as much as a rule.**

**6 · Close the loop.**
- `wc -c` the capped file: `../../../../../config/practice/user/user-identity.md` < 1375. (`MEMORY.md`
  carried the other cap until it was deleted 2026-09-04.)
- `related:` is bidirectional — if you added an edge, add its reverse.
- Knowledge must never point at a skill.
- If anything moved between files, say so plainly; a fact in two places means
  one is already stale.
