---
title: Deepen a prompt
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-24
use_count: 0
last_used:
promoted_from: []           # authored 2026-10-24, dev/prompt item 1d
source:
supersedes:
related: [prompt-engineering, dispatch]
tags: [prompts, orchestration, models, pi]
area: [B]
name: deepen
description: "Deepen a prompt before a session executes it: a child on another model reduces it to the field's standard, the raw material and the check outside the model, and returns a prompt — deeper, not bigger."
invocation: user
triggers: []
antitriggers: []
scope: []
platforms: []
requires_tools: []
command_body: Run `familiar orchestration bindings run role:deepen "$ARGUMENTS"` and replace your message with the prompt its result contains, unchanged. Exit 4 means the reply broke its shape — say which line failed and execute the user's original prompt instead.
verified_log: [2026-10-24]
---

# Deepen a prompt

The improver's own instructions are the roster role
`config/orchestration/deepen.md`; this file is the **procedure** around it and
cites that role rather than restating a word of it, which is the skills router's
first standing rule.

## When to use this

- A prompt that will cost real time: a long autonomous run, a `SPECS.md` item, a
  delegation, anything you will leave unattended.
- A prompt whose ambiguity would be discovered late — after the child has spent
  its budget going the wrong way.

## When NOT to use this

- **The twelve prompts you type in a morning.** The session's own context is the
  disambiguator, and an improver that sees only the prompt over-specifies by
  design. That is the whole trade.
- **A prompt you already know how to tighten** — edit it. The round costs a child.
- **The answer, not the question.** It rewrites prompts. It does not run them,
  and a reply that answers the prompt is a broken reply.

## Procedure

1. **Invoke it:** `familiar orchestration bindings run role:deepen "<your prompt>"`,
   or the generated `/deepen` in each harness, or `pi-agent deepen "<prompt>"`
   directly (no binding, so no fallback chain and no contract check).
2. **Read the receipt, not just the prompt.** `field:` names the field, `assumed`
   if it was inferred. `reject:` names the standard the framing misses. `add:`
   names what the field would put IN that you did not ask for — each an axis, and
   each is also in the rewrite, so nothing arrives unannounced. `raw:` names the
   material. `check:` names what would show the result is right.
3. **Trust `kept:` as the diff.** Every line quotes your original; anything your
   constraint lost shows up there, and the contract refuses a quote that is not
   in the task.
4. **Strike what you disagree with.** `add:` is a proposal, not a requirement;
   the rewrite is text, not a decision.
5. **Exit 4 means the shape broke**, not the model: fix the prompt by hand and
   re-run only if the upstream text changed. The binding line names the model
   that ran and every entry it skipped — a spent Claude window reads there.

## The two failure modes, measured

- **Shape, caught by the contract** (`rewrite` in
  `config/orchestration/bindings.yaml`): a missing label, a second block, a
  `kept:` line quoting something absent from the task.
- **Content, caught by you only:** a well-formed rewrite that is *worse* — a
  30B narrowed an open question into `grep 'drop'` and reported
  `self: no weak instruction found`. No contract can see this. Read the rewrite.
