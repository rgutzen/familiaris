---
title: Evaluation — is each component worth it?
summary: Is a component worth it: the registry, the readings, the review, the verdict, and what a sample size allows
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-25
verified_log: [2026-10-25]
use_count: 0
last_used:
promoted_from: []
source: 06_SYSTEM/dev/evaluation/PLAN.md
supersedes:
related: [healthcheck, orchestrators, orchestration-eval, delegation-and-asks, the-loom, scheduled-processes]
tags: [evaluation, metrics, verdict, ab-test, bandit, withholding, cost-per-verified]
triggers: [is it worth it, evals review, evals verdict, component registry, components.yaml, evaluation.jsonl, cost per verified result, keep change or drop, which experiment design, sample size]
scope: ["06_SYSTEM/engine/checks/evaluation.py", "06_SYSTEM/config/checks/**"]
area: [B]
stability: evolving
---

# Evaluation — is each component worth it?

**The healthcheck asks *is it working?*; this layer asks *is it worth it?*** Each
component Familiaris adds is measured on the user's real usage, read weekly, and
ends a monthly review with a verdict: keep, change or drop. Its parts:

- **the registry**, `config/checks/components.yaml`: per component, the
  question, the design, the instrument and the pre-registered floors;
- **the record**, `<PAZRAS_DATA_DIR>/evaluation.jsonl`, with reading rows and
  verdict rows.

The layer rewrites no instrument. An adapter in `engine/checks/evaluation.py`
turns one instrument's output into readings.

```
instruments (unchanged) ─► adapter ─► reading rows ─► review (the user) ─► verdict row
                                       weekly, $0       monthly, ~15 min     + decision + leaf row
```

## Commands

| command | does |
|---|---|
| `familiar checks evals list [--check] [--metrics]` | the registry; `--check` exits 1 on a malformed entry; `--metrics` prints the vocabulary |
| `familiar checks evals read [--dry-run]` | one batch from every adapter; the `familiar-evals` timer runs it on Mondays |
| `familiar checks evals review [--json]` | the monthly screen |
| `familiar checks evals verdict <c> keep\|change\|drop --why …` | records the user's ruling |

## Reading a reading

| field | means | trap |
|---|---|---|
| `metric` | a name from the vocabulary; `usd_per_verified` is the primary outcome (ruled 2026-10-22) | a metric outside the vocabulary is refused |
| `value`, `n`, `n_all` | the number, the attempts it rests on, and all attempts | `n` is much smaller than `n_all` when few attempts carry a verdict |
| `interval` | the 95% Wilson interval, for a share | at n = 12, 67% is anything from 39% to 86% |
| `gate` | the instrument's own gate (5d's 30 fires or 60 sessions, a label bar) | a reading taken through a closed gate is displayed, never decided on |
| `arm` | a per-option breakdown (a ran model), or the randomised arm | a floor reads the total row (`arm` null) unless it names a qualifier |
| `note` | why there is no value, and what was excluded | an unpriced model or an all-zero usage is excluded and counted, never $0 |

## Reading the review

| state | means |
|---|---|
| `GAP` | no instrument; the line names the cheapest source. The gap list is generated from the registry |
| `NEVER READ` | an instrument exists, and no batch has run |
| `NO RULE` | measured, with no floor pre-registered: descriptive only |
| `HELD` | a floor's reading has no value, a closed gate, or `n` below the floor's `n>=` or else the entry's `min_n` |
| `READABLE: proposed keep` | every floor passes; a verdict is due |
| `READABLE: proposed change or drop` | a floor fails; the user chooses which |
| `coverage-limited` | fewer than 80% of attempts carry a verdict. A heuristic floor (`used`) only bounds uptake from below, so it can support *keep* but never *drop* |

**Display weekly, decide at the gate.** A weekly reading never triggers a
verdict. This generalises 5d's "recorded whole" ruling of 2026-10-22, and it
guards against peeking: about 20 components re-read every week would cross some
threshold by chance.

## Where a verdict lands

`evals verdict` writes two of the four places itself and prints the rest:

1. a `verdict` row in the ledger;
2. a `consolidation decision`;
3. the row to paste into the verdict table of the leaf named in `lands:`
   ([[orchestrators]] for the Loom's components);
4. for `change` or `drop`, a reminder to schedule the work: an item in the
   owner's `SPECS.md`, or a line in `ROADMAP.md` §Known gaps.

The leaf row matters because `~/.local/share/pazras/` is in no backup (ROADMAP
§Known gaps). A verdict lasts 90 days by default (`--review-by`). A version
change to the component moves its `since:` and starts a new population.

## Which design answers which question

| question | design | needs |
|---|---|---|
| Is an offer the agent may decline worth making? | randomised withholding; ITT always, LATE when the uptake gap is ≥ 0.10 | the decision point logs its arm (14a's nudge) |
| Which of N alternatives fills one slot? | Thompson sampling inside a tier | an automatic verifier on every arm, and ≥ 80% of attempts verified |
| Is version 2 better than version 1? | fixed A/B by session-id hash, n fixed in advance | both versions can run concurrently |
| What does it cost to carry? | static measurement | none |
| Is it used at all? | observational | no causal claim |
| What does it do where it should act? | campaign (paired probes, `feat/benchmarking`) | no log carries the outcome |

**A bandit over unverified arms is biased.** An arm whose failures are never
seen keeps its prior, and the sampler keeps choosing it.

## What a sample size allows

Binary outcome, 95% Wilson; two arms at α = 0.05 and 80% power.

| n per arm | ± on one rate | smallest detectable difference | a verdict may say |
|---|---|---|---|
| < 10 | ± 0.26–0.33 | ≥ 0.6 | counts only: 0/10 allows a true rate up to 0.31; only *drop for non-use* |
| 30 | ± 0.14–0.17 | 0.29–0.36 | gross effects; *keep* on a floor's lower bound |
| 100 | ± 0.08–0.10 | 0.16–0.20 | a 20-point difference |
| 300 | ± 0.05–0.06 | 0.09–0.11 | a 10-point difference |

At 2026-10 usage (about 10 sessions and 7 fires a day), most verdicts rest on
cost and use rather than on 10-point quality differences.

**A LATE needs far more than a share.** It divides the arms' log-bytes contrast
by their uptake gap, so at a gap of 0.35 its noise is about three times the
ITT's. At 15 withheld fires, 5d's LATE had a 95% bootstrap interval of
[0.07, 28], and it moved from 0.39 to 1.85 within one day. The table below is a
simulation at the observed spreads: sd of log-bytes 0.99 nudged and 1.57
withheld, delegation 0.48 vs 0.13, two nudged fires per withheld fire.

| withheld fires | P(a no-effect nudge, LATE 1.0, reads as passing ≤ 0.5) | P(a halving one, 0.25, reads as passing) |
|---|---|---|
| 15 | 0.28 | 0.69 |
| 60 | 0.14 | 0.86 |
| 150 | 0.05 | 0.96 |
| 300 | 0.01 | 0.99 |

The registry sets `effect <= 0.50 late n>=150`. A floor's `n>=` suffix
overrides its entry's `min_n` for that floor alone, so uptake and compression
keep the default 30. A true LATE at the floor reads 50/50 at any n: the rule
separates effects a factor of two either side of the floor, not effects near
it.

## Known state (2026-10-25)

- **Measured:** `delegation-nudge` (adapter over `orchestration report`'s
  window) and `dispatch` (over the `verify` labels). Six components have an
  instrument that is not yet migrated; eight are gaps.
- **First realised cost per verified result** (dry run, 44 `verify` labels):
  claude-opus-5-5 $17.60, deepseek-flash $0.24. They ran different items, so
  the ratio is not a model comparison.
- **The adapter must not call `orchestration report`'s main.** It rewrites
  `report-last.json`, and the weekly healthcheck's `report --check` compares
  against that file. `log.scan()` is the read-only path.
- **The timer is live since 2026-10-25** (Mondays 08:00). Applying a future
  unit change follows the same sequence:
  `familiar schedule timers --check`, then `--apply-dotfiles --yes`, review
  and commit the dotfiles, then `bash ~/02_AREAS/B_Tech/dotfiles/bootstrap.sh`
  (it restows, which links the new file, and enables every table timer).
  `enable` before the restow fails with "does not exist" ([[scheduled-processes]]).
- **Staging units from a git worktree rewrites every unit's header**, because
  the generator writes `${STAGING#$HOME/}` into it. Render from the install, or
  revert the incidental diffs.
