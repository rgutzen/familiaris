---
title: Consolidation cycle — the nightly pass
summary: The nightly pass — what runs when, and what it is allowed to write
origin: authored
authority: agent
trust: trial
last_verified: 2026-09-11
use_count: 20
last_used: 2026-10-11
promoted_from: []
source:
supersedes:
related: [memory-mechanisms, memory-ranking, memory-architecture, prior-art-memory-systems, skill-routing, healthcheck, journal-index, scheduled-processes, memory-poisoning-posture, pointer-following, agent-prompt-dream-memory-consolidation]
tags: [consolidation, scheduling, sleep, pruning, cron]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving
verified_log: [2026-09-11, 2026-08-30]
---

# Consolidation cycle

One scheduled pass, nightly, replacing the four independent triggers in
`memory-mechanisms.md` (Loops A–D fired on "weekly", "after N entries", "the
timer"). **Decided 2026-08-30: consolidation is scheduled, never volume-driven** —
a volume trigger makes consolidation a function of how busy the week was, while
decay is a function of time, so the trigger and the formula would race.

The one place the sleep analogy is load-bearing: **prune by rank, not by an
absolute `R` threshold.** A cutoff calibrated at 40 leaves silently guts the tree
at 400, so the pass takes the bottom *percentile* of the scored set. The rest of
the vocabulary (replay, consolidation, downscaling) is used because it predicts
the *ordering*, which matters for a different reason: you cannot distil what has
not been ingested, or prune on a score computed before the distillation that
would have raised it.

## Stage order

Each stage is idempotent and may be interrupted; the next run resumes.

| # | Stage | Reads | Writes | LLM |
|---|---|---|---|---|
| 0 | **Preflight** | git status, lock file | lock, snapshot commit (if dirty) | no |
| 1 | **Replay** — transcripts → journal | staged transcripts | `journal/YYYY/MM/*.md` (append) | yes |
| 2 | **Aggregate** — usage → frontmatter | staged transcripts, `skill-usage.jsonl` | `use_count`, `last_used` | no |
| 3 | **Score** — compute F, U, R | all frontmatter | *nothing* | no |
| 4 | **Consolidate** — journal → knowledge | recent journal | `knowledge/**` (patch, append-only) | yes |
| 5 | **Associate** — co-location → links | usage log, `scope:` | `related:` (+ back-links) | no |
| 5 | **Conflicts** — declared precedence | `supersedes:`/`contradicts:` | `superseded_by:`, `trust:` | no |
| 6 | **Downscale** — apply the quadrant | scores | `trust` demotions, queues | no |
| 7 | **Reindex** — regenerate routers | frontmatter | `CONTEXT.md`, `INDEX.md`, trigger index | no |
| 8 | **Report** | everything above | dated report, `BRIEF.md`, posture findings | no |

**Two stages share id 5 and two share id 7**, deliberately: `--stages=5` has to
mean "the relation stages" and `--stages=7` "the derived indexes", and the
callables stay separate so one broken half cannot take the other down. Renumbering
was not an option — it would churn every report that names a stage. `conflict.py`
labels its proposals `5d`, continuing associate's 5a/5b/5c. **Stage 9 (lore triage)
was removed 2026-09-11** with lore itself; the id is not reused.

## What each stage may and may not do

**0 · Preflight.** A dirty tree is snapshotted, not refused — **decided
2026-09-07**: agent-own paths (`skills/`, `knowledge/`, `CLAUDE.md`) change from
ordinary work anywhere on the machine, so dirty is the common case, not the
exception the original design assumed. The snapshot is its own commit (`wip:
pre-sleep snapshot`, all paths), kept separate from the pass's commit so invariant
4 still holds. Exception: a dirty path whose mtime is under `QUIET_SECONDS`
(120 s) aborts the pass instead — a snapshot must not freeze a half-typed
sentence. Takes the lock that stops two nights overlapping after a suspend.

**1 · Replay.** One journal entry per staged transcript, citing the verbatim file
by id. Append-only; an existing entry is never rewritten. (Loop A.)

**2 · Aggregate.** Counts, per skill and leaf, the sessions that read it — from
the staged transcripts and `skill-usage.jsonl`, keyed by session — into
`use_count` / `last_used`. The only stage that writes frontmatter it did not
compute. (Loop B.)

**3 · Score.** Applies `memory-ranking.md`: F, U, R and the quadrant for every leaf
and skill, plus the never-verified and cold-start exempt sets. Writes nothing on
purpose — a pure function of the tree, so its output can be regenerated and diffed
without touching history.

**4 · Consolidate.** Extends `knowledge/` where a durable fact emerged.
**Proposes** changes to `../../../../config/practice/user/user-identity.md` and `conventions/**` into the
report — never writes them. The third target it used to have, `MEMORY.md`, was
deleted 2026-09-04; `memory-mechanisms.md` §Loop C records why the reference
outlived the file.

*The rule:* **a leaf is appended to or marked superseded, never rewritten
wholesale.** A patch may insert lines into a body, or revise a frontmatter value
for a marking key (`supersedes:`, `superseded_by:`, `trust:`) — nothing else. The
realistic breach is not a wholesale rewrite arriving as one; it is a rewritten
leaf pasted into `BODY:` where an addition was asked for, which produces a diff of
pure insertions and reads as a green add-hunk in the very report a human is asked
to accept. So replacement has its own legal route, `KIND: supersede-leaf` with
`SUPERSEDES:`, which creates the new leaf, records the precedence and leaves the
old text intact — without a legal route the only route is the illegal one.
Mechanism: `engine/consolidation/stages/consolidate.py`. *Lit:* ACE, ICLR 2026 (arXiv 2510.04618) —
brevity bias and context collapse are the failure modes of LLM-rewritten memory.

**5 · Associate.** Two jobs, both mechanical:
- **Back-link repair.** `related:` is bidirectional for `knowledge/**`: if A names
  B, B must name A, and the pass repairs the missing side. (From A-MEM's
  memory-evolution step; the cheap version needs no embeddings.)
- **Co-location proposals.** Leaves and skills that repeatedly co-occur in one
  `cwd` become `related:` candidates, and a leaf used far outside its `scope:`
  becomes a re-scoping candidate. **Proposals only** —
  `memory-ranking.md` §Declared scope vs measured co-location.

**5 · Conflicts.** The other half of id 5: deterministic, no LLM, no score, every
input frontmatter and every rule a comparison. Two relations, resolved differently
because they are different claims:

- `supersedes:` is **asymmetric and asserted** — the author has decided, so the
  pass only makes the tree consistent with a decision already made: close the
  `superseded_by:` back-pointer (the `related:` closure rule, one field over) and
  mark the superseded side `trust: deprecated`.
- `contradicts:` is **symmetric and unresolved** — *of two leaves making
  incompatible claims, the one verified more recently is the current one.*
  ISO-8601 on `last_verified`, the signal `F` already decays on read to a
  different end. Ties and missing dates are **undecidable**: report, never guess.

Applying `trust:` rather than proposing it is the one thing needing justification,
and the justification is the split below: a declared relation is not a number
nobody has validated. Worst case is a marked, reversible leaf — `deprecated` is
retained and is stage 6's demotion floor. It also *reports*, never resolves, pairs
of leaves sharing enough vocabulary to be about the same thing — deliberately
**not** called a conflict, because deterministic detection of a semantic
contradiction between two differently worded paragraphs does not exist and a check
claiming it would manufacture the distractor noise the L-track exists to remove.
Directive paths and `authority: human` are never written.
Alone: `familiar consolidation conflicts [--check] [--apply]`.

**6 · Downscale.** The quadrant table from `memory-ranking.md` applied to the
bottom percentile of the scored set:
- `low F, high U` → append to the re-verification queue
- `high F, low U` → propose demotion one step (`trusted → trial → deprecated`)
- `low F, low U` → propose archival
- `authority: human` → never touched; reported only
- **nothing is deleted, ever.** `deprecated` is retained for provenance.

**7 · Reindex.** Regenerates every `CONTEXT.md` categories block, the
`triggers → skill` table and `knowledge/INDEX.md`. Derived artifacts: markdown is
truth, indexes are disposable caches ([[memory-architecture]]).

**8 · Report.** Two artifacts for two readers, plus a check.

- The **dated report** is the human's: one file read over coffee, organised by
  what needs deciding. Every proposal from stages 4–6 lands here and nowhere else.
  **An unread report is the failure mode this design is most exposed to** — if it
  is never opened, proposals never land and the tree silently stops improving.
- The **brief** (`journal/reports/BRIEF.md`) is the agent's: a fixed path
  answering the three questions a session opens with — what changed, what's open,
  what failed — organised by what was asked rather than by what needs deciding,
  which is why neither is derivable from the other. Reachable as
  `familiar consolidation brief` and the `brief` MCP tool. **Deterministic**: git, the
  ledgers, and the pass's own record. A model could only paraphrase facts that
  are already exact, and the sleep-time-compute saving is kept where it is real —
  stage 1 has *already* paid a model call per transcript, so the brief harvests
  its `## Still open` / `## What failed or surprised` bullets verbatim, as
  attributed `path:line` pointers, rather than summarising them a second time.
  The path is stable and never dated: a session asking for the state of things
  must not first work out which night's file is current. *Lit:* Sleep-time
  Compute (arXiv 2504.13171) — benefit tracks query predictability.
- The **posture checks** run just before the report renders, so their findings
  are in both artifacts: `memory-poisoning-posture.md`. Not a gate — the pass's
  writes are constrained by the very mechanisms being checked, and aborting would
  delete the report that says the constraint slipped.

### What stage 4 may propose: crystallized, never scaffolding

Decided by the user 2026-08-31 (`dec-93009608`), and encoded in the stage-4 prompt
rather than left to judgement:

> A fact earns a knowledge leaf only if it stays true **after the current work
> finishes.**

Rejected on that basis: phase and milestone numbering, migration state, "currently
at step N", which items are open, what is built and what is not. That is
scaffolding — it goes stale in the tree within weeks and **nothing will notice**,
because a leaf decays by becoming false and no score detects a fact that merely
stopped mattering. It belongs in `ROADMAP.md`, which decays by deletion. The
durable version is the **rule it illustrates, not the state**: *"plans never live
in `knowledge/`, because a leaf decays by becoming false and a plan decays by being
done"* is crystallized; *"the phases are M0–M4"* is not.

## Invariants

1. **Only this pass mutates tracked files.** Hooks append to logs; they never edit
   frontmatter. Sessions run in parallel; a writing hook would race
   (`memory-mechanisms.md` §Division of labour).
2. **Directive paths are proposal-only** at every stage.
3. **`journal/**` is append-only and unscored.** Episodic memory does not decay
   here; the verbatim tier outside git is what gets pruned instead.
4. **The pass commits its own work as one commit**, so a bad night is one
   `revert` — a claim about the pass's commit specifically, not the night's only
   commit: preflight may have made an earlier `wip: pre-sleep snapshot` (stage 0),
   and the two are never merged.
5. **Stage order is load-bearing and `run.py`'s `STAGES` list is its single
   source.** A stage never spells its own name (`test_run` forbids
   `stages_run.append` inside `engine/consolidation/stages/`); `main()` appends `8 report`; preflight is
   stage 0.
6. **A raising stage is treated as never run and the loop continues** — one broken
   stage must not lose the rest. A preflight abort on dirty tree/lock exits **0**
   deliberately: non-zero fires the systemd `OnFailure` alert, and an alert that
   cries wolf is worse than no alert. Other aborts exit 2.
7. **Ledger reads never raise.** `ledger.read()` returns empty rows for a missing
   file and counts malformed lines, because "no ledger yet" and "corrupt ledger"
   are distinct states a stage must tell apart. `Dismissals.covers` takes
   `target_kind='leaf'|'opaque'` — opaque rows match target+kind within
   `OPAQUE_TTL_DAYS`, leaf rows by content hash. Parse ISO-UTC `Z` timestamps with
   `calendar.timegm`; `time.mktime` is wrong by the zone offset and skews across
   DST (measured 7200 s).
8. **Decisions are advisory to capture, enforced to surface.** `record_decision`
   surfaces nightly until the decision "lands" (its id appears under `memory/`
   outside `journal/reports/`). Enforcement covers only the not-losing half,
   because no hook can detect that the user settled a recurring question. An
   unreadable decision row is an error note.
9. **No stage may promote a leaf to `trust: trusted`.** Every trust transition
   the pass performs is a *demotion*, whose worst case is a true claim read with
   too much caution; promotion re-labels unreviewed text as ratified, which is
   the step that turns an injection into a standing belief. Refused at
   `frontmatter.set_fields` — the single write path every stage goes through — so
   an attempt raises and the report names it. `memory-poisoning-posture.md`.

The two rules that are *not* here — append-only, and declared-conflict precedence —
are stated once each under stages 4 and 5 above rather than twice. **Numbers 1–8
are referenced from code by number** (`git.py`, `tree.py`, `conflict.py`,
`preflight.py`, `test_preflight.py` all cite one), so renumbering them silently
breaks those references — a new invariant goes at 9, and a rule belonging to one
stage belongs in that stage's paragraph above, not in this list.

## Applies vs proposes

A change is mechanical only if it does **not** depend on a number nobody has
validated; unsure → proposal.

| Applies | Proposes into the report |
|---|---|
| journal entries (append), `use_count`/`last_used`, `verified_log`, back-link closure, routers, `BRIEF.md`, declared-supersession marking | `trust` demotions by score, archival, re-verification, `stability` migrations, `knowledge/**` extensions, stage 5d's non-declared findings |

The brief is on the left because nothing in it is derived: it is a regenerated
view of git and the ledgers, disposable in the same sense a router is.

**Stage 4 is proposal-only even though the original ruling named only
*scoring*-derived changes.** Its writes are *LLM*-derived, which is the larger
risk: a wrong number churns frontmatter, a wrong paragraph corrupts the knowledge
base and reads as authored. It emits an appliable patch instead, so accepting a
night is one command. Promote to unattended once the report has been read for a
few weeks.

## Idle days are skipped

A night on which nothing changed is **skipped entirely** — no scoring, no model
calls, no report, no commit. "Nothing changed" means no new staged transcript, no
new usage or decision line, and no new commit since the last completed pass,
compared by fingerprint. `Persistent=true` is what makes this matter: a laptop
that was off for a week fires a catch-up run on boot, and without the check that
run would spend two cloud calls concluding nothing — and, worse, let stage 6
propose demotions built on a week of decay the user had no chance to prevent.
(That second risk is handled more fundamentally by measuring utility in **active
days**, `memory-ranking.md` §Utility; the skip is about not doing pointless work
at all.) `--force` overrides for a deliberate rerun.

## Scheduling

systemd user timer, nightly, `Persistent=true` so a suspended or powered-off
laptop catches up on the next boot rather than skipping a night. Level 3
enforcement per `memory-mechanisms.md` — unskippable but asynchronous.

## Measurements that decided the design

- **Transcript chunking is unnecessary.** Dropping `tool_result` bodies and keeping
  prose turns reduces 5.42 MB to 26.6 kB — ~200× — so one model call per transcript
  fits comfortably. The chunking the M1 handoff anticipated was never needed.
- **The Python rewrite made capture faster, not slower**: median 15.4 ms against
  bash's 44.5 ms, because the bash path forked `sed`, `tr`, `awk` and `date` per
  invocation. Reproduce with `familiar checks selftest --hook-cost`.

## Where the rest lives

Module names below and above — `pass_ctx.py`, `git.py`, the rest — are files in
`engine/`; stage modules are in its
`engine/consolidation/stages/` subpackage.
Named bare rather than pathed for readability, and anchored here so a reader can
find each one. Anything written as a PATH resolves from the repository root.

This leaf is the spec. Everything a maintainer would otherwise re-derive is
documented by the module that owns it, so it is not copied here: `pass_ctx.py`
(one scored tree, and why an unscored document is not a state a stage can
observe), `git.py` (one git adapter, domain values, every call timed),
`invocation.py` (an undeclared flag is an error), `ledger.py` (one reader for the
append-only logs, and the read-side schema `capture.py` cannot import),
`frontmatter.py` (line-surgical writes, never a round-trip), `aggregate.py`
(recompute, never increment), `reindex.py` (plan decides every byte and writes
none), `report.py` (a dry run's report lands outside git), `brief.py` (why no model
writes the answers), `posture.py` (the threat model, and what the checks do not
cover), `selftest.py`, and the stage docstrings themselves. `selftest.py`'s
fixtures (`--signals`) and its latency measurement (`--hook-cost`) are what keep
the capture path honest; the M1 bash baseline they were once diffed against was
deleted on 2026-10-13, the migration it gated having finished in 2026-09.

## Verification

```bash
systemctl --user list-timers | grep familiar          # the nightly + weekly timers
familiar consolidation status
familiar consolidation run --dry-run --force                 # the whole pass, writing nothing
familiar consolidation brief                                 # the precomputed answers
familiar consolidation posture                               # exit 3 on a failed check
ls ~/06_SYSTEM/memory/journal/$(date +%Y/%m)/
```
