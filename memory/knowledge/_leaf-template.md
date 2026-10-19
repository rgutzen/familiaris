---
# ── shared leaf contract (identical in skills/_skill-template.md) ──
title: Short declarative name
summary: One line, under 110 chars — when a reader should open this leaf
                          #   THIS is what knowledge/INDEX.md indexes, so write
                          #   it as the row a searcher must recognise. Falls
                          #   back to title, then the H1, then the filename.
                          #   See [[knowledge-index]].
origin: authored          # authored | imported | learned | derived
authority: agent          # agent | human — human leaves are never auto-pruned
trust: trusted            # quarantine | trial | trusted | deprecated
last_verified: 2026-08-28 # correspondence signal — checked against the world
verified_log: []          # the last 3 `last_verified` values, most recent first.
                          #   Written by the consolidation pass ONLY; entry 0
                          #   mirrors last_verified, which is how the next pass
                          #   detects that it changed. Stability migration needs
                          #   verification HISTORY, not just the latest date —
                          #   see memory-ranking.md §Stability migration.
use_count: 0              # utility signal — how often retrieved
last_used:
promoted_from: []         # RESOLVABLE paths to the journal entries this
                          #   was distilled from — the route back to the episode
source:                   # URL or material, if external
supersedes:               # path(s) of a leaf this replaces. Read by the
                          #   conflict stage (consolidate/conflicts, L4) and by
                          #   downscale's churn check. A DECLARED precedence: the
                          #   pass marks the other side `superseded_by:` and
                          #   `trust: deprecated` on the strength of this line.
                          #   Empty means "nothing"; a wrong value silently
                          #   deprecates a live leaf, so do not guess here.
superseded_by: []         # DERIVED back-pointer, written by the pass — the
                          #   reverse of `supersedes:`, the same closure rule
                          #   `related:` has. Never author it by hand.
contradicts: []           # path(s) of leaves making a claim incompatible with
                          #   this one. Symmetric and unresolved by itself; the
                          #   conflict stage resolves it by ISO-8601 precedence
                          #   on `last_verified:` and marks the loser. Use this
                          #   when the winner is not yet known — `supersedes:`
                          #   asserts one, this one asks the pass to decide.
related: []               # bidirectional for knowledge — see consolidation-cycle.md
tags: []
triggers: []              # vocabulary that should surface this leaf in
                          #   knowledge/INDEX.md. Defaults to `tags` when empty;
                          #   capped at 8 terms, because the terms column must
                          #   not eat the index budget.
scope: []                 # path globs where this applies; empty = anywhere
area: []                  # P.A.Z.R.A.S Area codes A-P this belongs to

# ── knowledge extension ──
stability: evolving       # permanent | stable | evolving | volatile
                          #   sets the freshness half-life H in F = 2^(-Δv/H):
                          #   permanent never · stable 365 d · evolving 90 d
                          #   · volatile 30 d — see memory-ranking.md §Freshness.
                          #   Author-declared. The consolidation pass may only
                          #   PROPOSE a migration, never write this field.
---

# Title

One-paragraph statement of what this leaf is for. If a reader needs something
adjacent, point them at it here — outward only.

## Content

The knowledge itself. Concrete, verifiable, dated where it matters. Prefer
exact paths, commands and error strings over prose description.

**This is a claim, not a procedure.** If you are writing steps, it belongs in a
skill that *cites* this leaf — see [[knowledge-vs-skills]].

## Verification

How a future agent can check this is still true — a command, a file to stat,
a symbol to grep. Leaves that cannot be verified should say so explicitly.

Primary decay signal for knowledge is **staleness**: a leaf that fails
verification is a correction candidate; one that is never retrieved is a
pruning candidate. The arithmetic is in [[memory-ranking]];
`scope:`/`area:` feed the retrieval prior there, never a filter.
