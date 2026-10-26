---
title: The orchestration eval — running and reading it
summary: `familiar orchestration eval`: 14 replayed tasks, five arms, contained cells, and the traps in a row
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-15
verified_log: [2026-10-15]
use_count: 2
last_used: 2026-10-19
promoted_from: []
source: 06_SYSTEM/dev/orchestration/2026-10-15-eval.md
supersedes:
related: [orchestrators, the-loom, scheduled-sessions]
tags: [evaluation, benchmark, orchestration, bwrap, containment, adoption-rule]
triggers: [orchestration eval, eval --run, evaluation set, adoption rule, eval row, repo_touched, rerun spread, add an eval task]
scope: ["06_SYSTEM/engine/orchestration/eval.py", "06_SYSTEM/dev/orchestration/tasks/**"]
area: [B]
stability: evolving
---

# The orchestration eval — running and reading it

**The instrument behind every verdict in [[orchestrators]].** It replays
fourteen real tasks from this repository's history. Each arm runs the task in
an isolated tree under a containment boundary, and the task's own verifier
judges the tree. One JSON row per cell goes to
`<PAZRAS_DATA_DIR>/orchestration-eval.jsonl`.

## The set

| class | tasks | judged by |
|---|---|---|
| coding, single item | `hermes-guard-h1h2`, `orch-2b-dispatch-check`, `ontology-o6b-skills-move`, `ontology-o2a-stems` | a black-box `check-*.py` written from the item text |
| coding, multi-item | `orch-step3-keyless-waves`, `orch-step2-gate-skill-pointers` | the same, over the whole step |
| retrieval | `retrieval-category-readers`, `retrieval-jev-calls`, `retrieval-orchestration-config` | `path:line` recall against a key written first |
| batch | `batch-leaf-subject`, `batch-o4b-replay`, `batch-journal-tags` | labels agreeing with an existing key |
| web | `web-deepseek-routing`, `web-retention-terms` | URLs cited and facts stated |

The tasks live in `dev/orchestration/tasks/`, one directory each: prompt, base
commit, verifier. `eval --validate all` proves each verifier fails on its base
and passes with the reference change applied.

**Arms**:

- `baseline`: pi, Opus.
- `dispatch`: one model per item, from the tiers.
- `bindings`: `PI_BINDINGS=1`; retrieval and web only.
- `jev`: batch only.
- `reference`: opencode with oh-my-opencode-slim.

## Running it

```bash
engine/familiar orchestration eval --run --tasks=all --dry-run        # every command line, nothing spawned
engine/familiar orchestration eval --run --arms=baseline,dispatch --tasks=all
engine/familiar orchestration eval --run --tasks=<id>,<id> --attempt=2 # a rerun keeps its attempt number
```

A full run is ~50 cells and several hours. Run it as its own unit
(`systemd-run --user …`, or [[scheduled-sessions]]) so the session that
started it cannot take it down when it ends. Keep the repository quiet while it
runs (the guard below explains why).

## Containment

- **Isolation:** each cell's tree is `git archive <base>` in `/tmp`, one
  commit, with no route to a later commit.
- **The mask:** each cell's process runs under `bwrap`. The live checkout is
  read-only. `.git`, `dev/` and `memory/journal` are emptied, because they hold
  the answers. The machine's compiled permission policy and the hermes block
  are read-only, because a base-commit compiler once overwrote them, twice.
  The mask cannot run from a git worktree, where `.git` is a file.
- **The guard:** each row's `repo_touched` lists what moved in the repository
  during the cell. Its known false positive is the parent's own uncommitted
  edits, or the nightly pass's.

## Reading a row, and the traps

| field | means | trap |
|---|---|---|
| `model` / `pi_model` / `ran_model` | asked / passed to pi / what the log says answered | a mismatch is a finding |
| `usage.frontier`, `usd_frontier` | input + output + cache-write, at list price; cache-read kept apart | a model the catalogue lacks prices at $0: report it as unpriced, never as free |
| `attempt` | the run number | a rerun is an independent run, not a retry |
| `wall_seconds` | monotonic time | a machine suspend does not count, but a stale connection after it can fail a cell |
| `tools` | the tool names called | how to tell whether a bound tool fired |
| `verifier.tail` | the verifier's last lines, joined with ` \| ` | quote it, never paraphrase it |

**The adoption rule** is decision 29, quoted in [[orchestrators]]. Its
threshold is re-derived from the reruns: 1 − 2 × the median relative cost
difference between attempts, over agent cells only. Three kinds of pair are left
out, each for a stated reason: Jev is deterministic (it would pull the median
toward zero), the reference arm is unpriced, and a pair separated by a fixed
defect is not a repeat of the same arm. On 2026-10-16 that last exclusion was
needed: three reruns, added after the bound-child stdin defect was fixed, moved
the median from 0.078 to 0.119 if counted. **The recorded threshold is 0.84**
(1 − 2 × 0.0778 over 10 clean-repeat pairs). Counting the defect pairs gives
0.76. No verdict depends on the choice: dispatch sits at 0.100 and bindings at
1.008.

## Known state (2026-10-15)

- **The reference arm's lanes start** only since the preset moved to
  `deepseek/deepseek-flash`. Every reference row before that ran its
  orchestrator alone.
- **`batch-o4b-replay` reference has never written `labels.tsv`** (3 of 3).
- **Bound children no longer hang.** The 900 s timeouts came from stdin: a pi
  extension's `spawn` hands its child a socket that never closes, and `pi -p`
  reads a non-TTY stdin to EOF. pi-agent, `bindings run` and the extension now
  pass `/dev/null`. Any new spawn of `pi -p` needs the same.
- **The quota calibration** (Settings → Usage around one workload) has not
  been done.
