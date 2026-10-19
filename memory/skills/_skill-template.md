---
# ── shared leaf contract (identical in knowledge/_leaf-template.md) ──
title: Skill name
origin: authored          # authored | imported | learned | derived
                          #   authored — written by the user
                          #   imported — external source; unvetted until trialled
                          #   learned  — synthesised from repeated actions (hermes)
                          #   derived  — built by a skill-builder from a book/course
authority: agent          # agent | human — human skills are never auto-pruned
trust: trial              # quarantine | trial | trusted | deprecated
last_verified:            # correspondence signal — do its APIs/paths still exist
use_count: 0              # utility signal — PRIMARY for skill lifecycle
last_used:
promoted_from: []         # resolvable journal paths, not prose
source:                   # URL, repo, or material it was derived from
supersedes:
related: []               # sibling skills — builds the skill graph
tags: []
area: []                  # P.A.Z.R.A.S Area codes A-P this belongs to

# ── skill extension: the routing surface ──
name: skill-name
description: One line, under 120 chars. This is what the router indexes.
invocation: model                    # model | user
                                     #   model — the routers index it; model or human may reach it
                                     #   user  — HUMAN ONLY. Excluded from every router and from
                                     #           TRIGGERS.md, so the model cannot see it at all.
                                     #           Generates a slash command in each harness instead
                                     #           (signal 1, skill-routing.md §User-invoked skills).
triggers: [keyword, phrase, tool]    # vocabulary that should surface this skill
                                     #   ignored when invocation: user — nothing routes to it
antitriggers: []                     # vocabulary that should NOT — prevents misfires
scope: []                            # path globs where this applies; empty = anywhere
                                     #   a retrieval PRIOR, never a filter — memory-ranking.md
platforms: []                        # empty = portable
requires_tools: []                   # skill is invisible unless these exist
---

# Skill name

## When to use this

Concrete situations. Be specific enough that the router's trigger match is
reliable and generic matches do not fire.

## When NOT to use this

The cases most likely to be confused with the above. A mis-fired skill is an
**active hijack**, not inert noise — this section is what keeps a growing
library unambiguous.

## Knowledge this cites

Facts live in `knowledge/`, procedures live here. List the leaves this skill
depends on rather than restating them:

- `[[example-leaf]]` — why it is needed

## Instructions

The actual procedure. Steps, in order.

<!-- Primary decay signal for skills is DISUSE: an unused skill is a pruning
     candidate. But a skill referencing a dead API is a repair candidate
     however often it is invoked — hence last_verified above. -->
