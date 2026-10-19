---
title: Research software engineering
origin: authored
authority: human
trust: trusted
last_verified: 2026-08-28
use_count: 0
last_used:
promoted_from: []           # authored; upstream repo in source: below
source: git@github.com:rgutzen/rse-ai-style-guide.git — rse-ai-style-guide.md
supersedes: ~/.claude/commands/rse-mode.md
related: []
tags: [python, research, reproducibility, scientific-computing]
area: [A, B]
name: research-software-engineering
description: Investigation-first workflow for developing, refactoring or reviewing Python research software.
triggers: [rse, research software, scientific python, refactor pipeline, computational model, reproducibility, hpc workflow, gpu pipeline, research code]
antitriggers: [quick script, one-off, throwaway, prototype, spike, debug a failure, write a test]
scope: []
platforms: []
requires_tools: []
verified_log: [2026-08-28]
---

# Research software engineering

The **workflow** for research software. Author: Robin Gutzen. MIT.

The always-on principles — building blocks, the solution hierarchy, scientific
correctness, performance, documentation — are **not** in this file. They live in
`../../../../../config/practice/conventions/code-style.md` and apply whether or not this skill is
invoked.

## When to use this

Developing, refactoring or reviewing open-source Python research software where
scientific correctness, reproducibility and maintainability by domain scientists
matter. Multi-step work with a real design decision in it.

## When NOT to use this

- A quick script or one-off analysis — the initialisation questions are overhead
- Validating an idea before building → `spike`
- A known failure needing diagnosis → `systematic-debugging`
- Writing tests for existing code → `test-driven-development`

## Knowledge this cites

- `../../../../../config/practice/conventions/code-style.md` — building blocks, solution
  hierarchy, scientific correctness, performance, Diátaxis. **Load with this.**
- `../../../../../config/practice/conventions/collaboration.md` — objective communication,
  role division.

## Instructions

### Task initialisation — ask all three, every major task

1. **"Should I maintain a roadmap document for this implementation?"**
   If yes, track design decisions, progress, issues, resolutions, API changes,
   benchmarks, test results. Offer to compile it into documentation afterwards.
2. **"What testing approach?"** Test-first (TDD) · test-last · none (justify).
3. **"What version control setup first?"** Feature branch · checkpoint commit ·
   no action.

### Investigation — understand before acting

**Never propose a solution before tracing the existing system.**

1. **Trace the complete flow.** Follow data and parameters from entry to final
   use. Identify existing mechanisms and intervention points. Understand why the
   current implementation exists.
2. **Analyse dependencies.** Review dependency files and imports. Learn the
   idioms of the main dependencies. Note domain-specific packages.
3. **Catalog existing infrastructure.** Search for related implementations,
   patterns, utilities, validators, configuration systems. Check whether an
   existing dependency already provides this.
4. **Understand in context.** What scientific requirement drives the change?
   What are the research-workflow implications? Can existing blocks compose it?
5. **Check what the tool already provides.** How do its designers expect this
   problem to be solved? What would an expert call the standard solution?

### Analysis — constraints, then the minimal solution

6. **Define constraints explicitly.** What must not change? What is
   user-configurable? What is the scope? Priority trade-offs? Building block or
   specific integration?
7. **Apply the solution hierarchy** from `../../../../../config/practice/conventions/code-style.md`, starting at Level 0.
   **State which level you chose and why the level below was rejected.**
8. **Evaluate reuse.** Does similar functionality exist? Can this be a reusable
   building block?
9. **Present 2–3 alternatives objectively**, ordered by complexity, with
   trade-offs and a recommendation.

### Implementation — incremental and validated

10. Start minimal — simplest solution for the immediate need.
11. Work with the grain; use tool-native features as intended.
12. Add generality only when multiple use cases have actually emerged.
13. **Validate scientifically** — known results, edge cases, boundaries.
14. Document the rationale: why this approach over the alternatives.
15. Commit at each significant milestone.

### Completion

16. If test-last was chosen, offer to write the tests now.
17. If a roadmap was kept, offer to compile it into documentation.
18. Finalise version control.
19. **Knowledge-transfer summary**: approach taken, assumptions made,
    transferable patterns. Anything durable is a promotion candidate for
    `knowledge/` — see [[memory-architecture]].

## Failure modes

- Proposing before tracing. The investigation phase is not optional.
- Jumping to Level 6–7 because it is more interesting than Level 0–2.
- Adding generality speculatively, before a second use case exists.
- Reporting success without scientific validation.
