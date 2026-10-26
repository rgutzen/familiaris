---
title: Dispatch a SPECS.md
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-16
use_count: 12
last_used: 2026-10-20
promoted_from: []           # authored 2026-10-13, dev/orchestration item 2d
source:
supersedes:
related: [wizard]
tags: [orchestration, specs, dispatch, models, planning]
area: [B]
name: dispatch
description: Cross from planning to implementation — write a SPECS.md whose items carry touches, depends, model and verify, check it with dispatch, then implement item by item.
triggers: [write specs, implement the specs, dispatch, parallelise, which model for]
antitriggers: [quick fix, one-liner]
scope: []
platforms: []
requires_tools: []
verified_log: [2026-10-16, 2026-10-13]
---

# Dispatch a SPECS.md

The switch from planning to implementation, for any project. The **contract**
(which fields an item carries) is data in `config/orchestration/specs.yaml`;
`familiar orchestration specs --explain` prints it. This skill is the
**procedure**. It does not restate the contract.

## When to use this

- A plan is agreed and the work spans several steps or sessions.
- Someone asks which model should do a piece of work.
- Work could run in parallel, and you need to know whether it may.

## When NOT to use this

- A quick fix or a one-liner: implement it directly.
- The intent is not fixed yet: run `grilling` first. This skill starts where
  the interview ends.
- The architecture is open: run `wizard` first. A spec cannot fix a decision
  nobody has taken.

## Procedure

1. **Write the items.** One checkbox per exit criterion, with a bold head that
   opens with its id: `- [ ] **2a · the contract.**`. Under it go four indented
   lines, `touches:`, `depends:`, `model:` and `verify:`. Their syntax is
   whatever `specs --explain` prints.
2. **Fill `touches:` and `depends:` with the user.** You hold the whole
   context; dispatch only sees the text. A dependency you leave out becomes a
   parallel conflict later.
3. **Fill `model:` from the catalogue, never from memory.**
   - `familiar orchestration models --explain <id>` prints a model's
     capabilities as percentiles, with their counts. A task class
     (`edit · read · test · docs · batch`) lists the capabilities it needs.
   - `familiar orchestration models --resolve <id>` says whether the active
     profile (`PI_PROFILE`, unset means `private`) can call the model.
   - Default to the cheapest model whose `verify:` alone can judge its output.
     Use the frontier model when the item leaves a design decision open.
   - Write `user` for anything only the user may do: a push, a directive file,
     another repository, spending money.
   - *unknown* in `--explain` means no benchmark covers that capability. It
     does not mean weak.
4. **Make `verify:` a command** that fails before the item is done and passes
   after it. Write `manual: <what is read>` only when the exit is a reading.
5. **Check:** `familiar orchestration dispatch --check <SPECS.md>`. It refuses
   an item that lacks a field and names the item and the field. Fix the spec
   until it exits 0, then ratify it with the user.
6. **Implement in `depends:` order.**
   - When an item's `model:` is not the current session's model, delegate it
     (`pi-agent`, or a `pi -p --model <provider>/<id>` child), or ask the user
     to switch.
   - Review the child's work, then re-run its `verify:` yourself.
   - If an item turns out to need a different model, say so and propose the
     change. Never edit the field quietly.
7. **Tick only after `verify:` ran.** Run it through the wrapper, which records
   the outcome as a label and, on a failure, prints the next rung of the
   escalation ladder:

   ```bash
   engine/familiar orchestration verify <SPECS.md> <item> --class <c> --effort <e>
   ```

   Quote the command and its output in the item, and commit per item.

## Notes

- **Parallel writers are a hypothesis**, not a default
  (`dev/orchestration/PLAN.md` §Dispatch). Items in one wave run in parallel
  only if their `touches:` are disjoint. Parallel reads are proven.
- **A model outside the profile** resolves only with `--approve=<reason>`,
  which logs the approval. Never borrow a key silently (decision 26).
- **Dispatch proper** (waves, Jev's probes, the suggested model) is built:
  `familiar orchestration dispatch <SPECS.md>` prints the waves and each item's
  declared vs suggested model. How the pieces fit, and what the eval found:
  [[the-loom]], [[orchestrators]].
