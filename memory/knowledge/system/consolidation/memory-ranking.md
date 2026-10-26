---
title: Memory ranking — one score for retention, one prior for retrieval
summary: Scoring, decay, pruning, and the order retrieval returns things in
origin: authored
authority: agent
trust: trial
last_verified: 2026-08-30
use_count: 5
last_used: 2026-10-13
promoted_from: []
source:
supersedes:
related: [memory-mechanisms, consolidation-cycle, knowledge-vs-skills, skill-routing, prior-art-memory-systems, memory-architecture]
tags: [ranking, decay, pruning, retrieval, spatial]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving
verified_log: [2026-08-30]
---

# Memory ranking

Two different questions, deliberately not one number:

- **Retention** — should this leaf still be here? Answered by `R`, below.
- **Retrieval** — should this leaf be read *now*? Answered by `R × S`, where `S`
  is a spatial prior derived from where the agent is working.

`the prune stage` uses `R`. Routing uses `R × S`. Nothing else invents a
heuristic; if a new signal is wanted it is added here or not at all.

## Which fields feed the score, and who writes them

`stability` and `origin` are **inputs only** — the consolidation pass reads them
and never writes them. This is what keeps the formula from chasing its own tail.

| Field | Written by | Role |
|---|---|---|
| `use_count` | consolidator (Loop B): sessions that read the document | utility magnitude |
| `last_used` | consolidator (Loop B): the latest such session's date | utility recency |
| `last_verified` | agent or human, on an actual check | correspondence recency |
| `stability` | author. Consolidator **proposes only** — see §Stability migration | sets the freshness half-life |
| `trust` | human promotes; consolidator may only *propose* | gate multiplier |
| `authority` | human | exemption flag |
| `origin` | set once at adoption, immutable | provenance; not scored |

## Freshness — F ∈ [0,1]

How likely the claim is still true. Exponential decay on an explicit half-life,
so the value is **recomputable from markdown alone** — no stored counter to
drift, no per-event multiplier to replay.

```
F = 2 ^ ( -Δv / H )        Δv = days since last_verified
```

| `stability` | H (half-life) | For |
|---|---|---|
| `permanent` | — (never decays) | settled decisions, provenance, closed questions |
| `stable` | 365 d | facts about this machine that change yearly |
| `evolving` | 90 d | tool behaviour, config, anything upstream owns |
| `volatile` | 30 d | in-flight state, versions, "currently true" |
| *(skills, no `stability`)* | 180 d unless declared | |

Four compartments rather than two, adopted 2026-08-30 from Wang et al.'s
*Drosophila* γ-lobe mapping (`prior-art-memory-systems.md` §2): a **spectrum**
of decay rates beats one tuned compromise, because a single rate is
simultaneously too fast for settled facts and too slow for volatile ones.

**Missing `last_verified` → F is undefined, not zero.** The leaf is flagged
`never-verified`, queued for verification, and **exempt from pruning**. You
cannot prune on a signal that was never collected. This is deliberate: a fake
number here would be indistinguishable from a real one six months later.

## Utility — U ∈ [0,1]

```
u_mag = min(1, ln(1 + use_count) / ln(1 + 10))
u_rec = 2 ^ ( -Δu / 180 d )        Δu = days since last_used
U     = u_mag × u_rec
```

**Δu is measured in ACTIVE days, not calendar days** (corrected 2026-09-01).
An active day is one on which this machine shows evidence of work — a session,
a skill invocation, or a commit. A leaf must never be demoted for days the
laptop was closed: there was no opportunity to use it, so idle time is not
evidence of disuse. A 32-day absence containing 2 working days costs 0.8% of
`u_rec`, not 12%.

> **`F` deliberately still decays on calendar days.** The asymmetry is the
> point: the world drifts while you are away — tools update, configs rot, a
> claim goes stale unattended — but a skill cannot be used on a day the machine
> was off. Staleness is about the world; disuse is about you.

Active days are **recomputed** from the session log, the usage log and git
commit dates, so there is no counter to drift — the same property that keeps
`F` recomputable from `last_verified` alone.

**Cold-start exemption.** If the leaf is younger than 60 **active** days, `U` is
undefined and the leaf is exempt. Without this, everything written last week is the top
pruning candidate — the standard failure of usage-based memory maintenance.

`use_count` counts **sessions that read the document** in the staged
transcripts, plus skill invocations, one per session (decided 2026-10-09 —
the invocation log alone held 2 lines in six weeks and cannot fill). It is
biased both ways (`memory-mechanisms.md` §Honest limits): maintenance reads
count, human reads and hermes sessions do not. Low `U` may therefore *propose*
demotion and may never delete.

## Trust gate — T

| `trust` | T | Effect |
|---|---|---|
| `trusted` | 1.0 | routed freely |
| `trial` | 0.7 | routed, outcome reported afterwards |
| `quarantine` | 0.0 | never routed without announcing first |
| `deprecated` | 0.0 | retained for provenance, never routed |

## Retention score — R

```
R = T × ( w_F · F  +  w_U · U )
```

Weights follow the primary-decay-signal row already in [[knowledge-vs-skills]]
— they are not a new decision, only its arithmetic:

| Store | w_F | w_U | Because |
|---|---|---|---|
| `knowledge/**` | 0.60 | 0.40 | staleness is primary; a wrong fact is the harm |
| `skills/**` | 0.35 | 0.65 | disuse is primary; `use_count` governs the lifecycle |
| `journal/**` | — | — | **not scored.** Episodic, append-only, exempt by design |

**The quadrant boundary is not specified anywhere in this leaf.** The table
below says "low" and "high" and never says where the line falls. M2 uses
`0.5`, the midpoint of [0,1] and nothing more. It is the most arbitrary number
in the pass and it decides which quadrant a document lands in, so the report
names it as unvalidated alongside `H`, `C_ref` and `s_min`.

## The action comes from the quadrant, not from R

`R` ranks a worklist. What to *do* depends on which component is low, because
the two failures need opposite repairs.

| F | U | State | Action |
|---|---|---|---|
| low | high | used, but probably stale | **re-verify** — highest priority |
| high | low | true, but nobody needs it | prune candidate → propose demotion |
| low | low | stale and unused | archive candidate |
| high | high | healthy | leave alone |

Hard rules that override the table:

- `authority: human` → never auto-anything. Report only.
- **Nothing is deleted.** Demotion walks `trusted → trial → deprecated`;
  `deprecated` is kept for provenance. This is the displacement rule applied to
  lifecycle instead of to size.
- A leaf that is `never-verified` or inside the cold-start window is exempt from
  both columns.

## Stability migration

`stability` is the one scoring input the consolidator may not write — that rule
stops the formula from adjusting its own decay rate to flatter itself, and it
stands. But the compartment a leaf *belongs* in is an empirical question, and
the author's initial guess is often wrong.

Resolution: **the pass proposes; the human applies.** Both properties hold.

| Observation | Proposal |
|---|---|
| declared `stable`, failed verification ≥2 times in a year | demote to `evolving` |
| declared `evolving`, unchanged across ≥3 verifications | promote to `stable` |
| declared anything, `supersedes` chain ≥2 deep | demote one step — it churns |
| `authority: human` | never proposed; reported only |

Proposals land in the nightly report (`consolidation-cycle.md` stage 8), never
in frontmatter. A migration that is never confirmed simply does not happen.

### Precedence is a different question from freshness

`F` says how much to trust a claim. It does not say which of two claims is the
surviving one, and the nightly pass has to answer that too — a settled policy
contradicted by a leaf is still contradicted however fresh both sides are. That
is **stage 5d** (`consolidation-cycle.md` §5 · Conflicts), and it reads the same
field to a different end:

> Of two leaves that declare each other in `contradicts:`, the one with the
> later `last_verified` is the current one. The loser is marked
> `superseded_by:` + `trust: deprecated`; nothing is deleted.

Three things this deliberately does not do. It does not apply to `supersedes:`,
which is a decision the author already made and which the stage only makes
consistent. It does not fire on a tie, a missing date or a future date — an
undecidable ordered pair is reported, never guessed, because picking a winner
between two claims is worse than naming the conflict. And `stability` does not
enter it: `permanent` means "does not decay", not "wins", and a leaf not checked
against the world in a year is not current because it is old.

Note the one consequence for this table: a leaf marked `deprecated` by 5d stops
being a demotion candidate in stage 6, because it is already at the floor. That
is why 5d runs before it.

**Verification history is kept as of M2 (2026-08-31):** `verified_log:` holds
the last three `last_verified` values, most recent first, written by the pass
alone. Entry 0 mirrors `last_verified`, which is exactly what lets the *next*
pass detect that it changed — the history is therefore recomputable from
markdown, with no state file to drift. Three entries because the table above
asks for "unchanged across ≥3 verifications".

## Spatial prior — S

The retrieval multiplier. Every term is computed from the **path and filename
alone**: no model call, no embedding, no index to rebuild. That is the whole
argument for it — it is the only useful retrieval signal available *before* the
first token is generated.

Four coordinate systems exist on this machine, and they are independent:

| Axis | Source | Distance |
|---|---|---|
| **path** | PARA tree, `NN_CATEGORY/X_Area/…` | tree distance: `(depth_a − lcp) + (depth_b − lcp)`, normalised by `depth_a + depth_b` |
| **area** | Area code A–P (`pazras-master-config.sh`) | `0` if equal, else `1` |
| **id** | Zettel `A.1.2.3_name.md` — a dotted hierarchical address | shared dotted prefix: `A.1.2.3` vs `A.1.2.7` = 1; vs `A.4.0.1` = 3 |
| **time** | `journal/YYYY/MM/YYYY-MM-DD_*`, `01_PROJECTS/YYYY-QN_*` | `|Δdays|` on a 365 d half-life |

```
S = max( s_min, exp( -( w_p·d_path + w_a·d_area + w_i·d_id + w_t·d_time ) ) )
s_min = 0.25
```

**`s_min` is what makes this a prior and not a filter.** A leaf about restic
learned in `06_SYSTEM/` is still true in `01_PROJECTS/`. Hard-filtering by scope
would rebuild the exclusive-boxes failure that the P.A.Z.R.A.S philosophy
explicitly rejects (`06_SYSTEM/CLAUDE.md` §Philosophy) — and would do it
invisibly, because the agent never sees what was filtered out.

Area is a *separate axis from path* on purpose: a project under `01_PROJECTS/`
belongs to an Area it does not live under. Path is positional; Area is semantic.

## Declared scope vs measured co-location

`scope:` is the leaf's **claim** about where it applies. The skill-usage log
(`{ts, harness, skill, session, cwd}` — already captured, see
`memory-mechanisms.md` Loop B) is the **observation** of where it was used.

Where the two disagree, that is a filing signal, not an error:

- used far outside its declared `scope:` → the scope is too narrow, widen it
- never used inside its declared `scope:` → it is mis-filed, or it is dead
- two leaves repeatedly co-occurring in one directory → propose a `related:` link

The last one gives an association that was **measured rather than asserted**,
and it is the cheap local substitute for embedding similarity over `knowledge/`.
Proposals only; `related:` edits land through the consolidation pass.

## Status

Formula authored 2026-08-30, **implemented 2026-08-31** in
`engine/consolidation/ranking.py` as a pure function that writes
nothing. Constants (`H`, `C_ref`, `s_min`, the weights, the quadrant midpoint)
remain first estimates — the skill-usage log held 2 lines when they were
chosen, one of them a test.

**The `U` source changed on 2026-10-09.** On that date the invocation log still
held 2 lines and all 61 documents were cold-start exempt, so no constant could
have been fitted from it. Reads replaced it: the first measurement found 64
staged sessions reading 44 of 63 documents (31 leaves, 13 skills), the top
reads inflated by the 2026-10 restructure. `C_ref`, the `u_rec` half-life and
the weights get fitted from these counts in M2b, from 2026-10-28.

**On 2026-08-31 the whole tree scored as exempt**: all 34 documents are inside
the 60-day cold-start window, so `U` is undefined and nothing is a pruning
candidate. That is the formula working, not failing — it is the exemption doing
the job it was added for. No constant can be validated until the tree ages past
the window and the log has content; M2 Task 7 sets that at two weeks minimum of
report-only running.

## Verification

```bash
familiar consolidation report --full | grep -i 'use_count'   # sessions and documents counted tonight
grep -rL '^last_verified: [0-9]' ~/06_SYSTEM/memory/knowledge --include='*.md'  # never-verified set
```
