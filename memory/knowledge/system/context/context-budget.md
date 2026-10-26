---
title: Context budget — what each harness spends before work, measured
summary: What a harness and a route cost in tokens; the `pazras-context` audit
origin: authored
authority: agent
trust: trial
last_verified: 2026-09-03
use_count: 14
last_used: 2026-10-19
promoted_from: []
source: []
supersedes: []
related: [memory-architecture, memory-mechanisms, claude-code, opencode, hermes, ollama-local, user-vs-conventions, knowledge-index, pi, pointer-following, codex]
tags: [context, tokens, audit, harness, overhead, claude-code, opencode, codex, hermes]
scope: ["06_SYSTEM/**"]
area: [B]
stability: stable
verified_log: [2026-09-03]
---

# Context budget — what each harness spends before work, measured

How much fixed context each harness puts in front of the model on the first
turn, measured 2026-09-03 by intercepting the actual request. The method,
the numbers, and the seams. Rerun with:

```bash
cd ~/06_SYSTEM
engine/familiar context harness --cwd=~/06_SYSTEM          # ~4 min; headless paths
engine/familiar context harness --interactive --cwd=~/06_SYSTEM   # claude TUI
engine/familiar context tree --check                       # static PAZRAS tree cost
engine/familiar context route --check                      # is the tree delivered?
```

## Fixed prefix, measured 2026-09-03 (empty temp dir = harness floor)

| harness | bytes | ~tokens | largest sink |
|---|---|---|---|
| opencode | 82,534 | 19,490 | vendor system prompt 43,328 B (9,967 tok) — one undifferentiated block |
| hermes | 62,193 | 15,541 | tool schemas 41,914 B (67%); skills index 6,999 B |
| claude (TUI) | 105,743 | 24,633 | tool schema Artifact 37,994 B (8,853 tok) |
| claude (`-p`) | 50,731 | 11,752 | tool schemas 26,774 B (54%) |
| codex | 48,268 | 10,732 | vendor prompt 20,903 B; `multi_agent_v1` tool 10,301 B |

**Interactive vs headless is the single biggest disclosure in this audit.**
Claude Code interactive TUI ≈ **24.6k tok**; headless `claude -p` ≈ **12.6k**
in the same cwd — a 1.95x gap. The 3.5x figure in the first audit compared
floor `-p` against real-session transcripts. Real-session calibration from
transcripts: min 35,435 · median 45,151 · max 65,761 (API-reported).

## PAZRAS tree cost (static)

**Re-measured 2026-10-09** with `engine/context/tokens.py`, the same estimator
`familiar context tree` uses.

```
  L0  CONTEXT.md                                          664 tok  budget   800  ok
  L1  user-identity.md + collaboration.md               1,918 tok  budget 2,000  ok
        always loaded, total                           2,582 tok
  cap user/user-identity.md    828 chars / 1,375  ok
```

The 2026-09-03 figures were 1,541 tok for L0+L1 (CONTEXT.md 706 + USER.md 263 +
**MEMORY.md 569**). Two things changed them: `MEMORY.md` was deleted 2026-09-04
(so that term is gone, not renamed), and `../../../../config/practice/conventions/collaboration.md` was
promoted into L1 the same day. The names a budget check measures are asserted
present, because this exact table once stayed green for a day while measuring
files that had moved — `pazras.py` §ALWAYS_LOADED records that.

Worst-case cost of answering one routing-table question, **2,582–6,783 tok**
(lower bound re-measured 2026-10-09; upper bound from 2026-09-11; was
1,538–6,059). Whole tree (90 files, incl. this leaf) ≈ **113,235 tok** —
the point of the routing tables. The whole-tree figure moves on any editing day,
so it is a checkpoint rather than a budget: the two budgets that gate are the L0
and L1 lines above, and `tree --check` is what asserts them.

Biggest leaves: [[boundaries]] 4,271 · [[consolidation-cycle]] 3,967 ·
[[skill-routing]] 3,949 · `skills/system/knowledge/paper-review/SKILL.md` 3,514 ·
[[memory-ranking]] 3,335. [[consolidation-cycle]] grew ~1,950 tok on 2026-09-11
when L3/L4 landed and was trimmed back the same day (5,810 → 3,967) by deleting
the parts that duplicated the module docstrings which own them — see its
§Where the rest lives. The lore leaf was the second-largest until it was deleted
with lore 2026-09-11.

## Per-harness redirect seams (each one cost time to find)

| Harness | Seam | Trap |
|---|---|---|
| claude `-p` | `--settings '{"env":{"ANTHROPIC_BASE_URL":…}}'` | `~/.claude/settings.json` carries an `env` block and settings env beats process env — exporting the var alone does nothing |
| claude TUI | pty, answer trust dialog + custom-API-key dialog | TUI renders **without inter-word spaces** — match space-free markers (`Yes,Itrustthisfolder`, `automodeon`) on the fully-stripped screen |
| opencode | `XDG_CONFIG_HOME` → copy of `~/.config/opencode`, then rewrite `provider.<p>.options.baseURL` | that override was inert while `@loreai/opencode` was installed (it rewrote every baseURL); it is the seam again since 2026-09-11 |
| codex | `-c model_providers.pazctx={…}` | `wire_api="chat"` is **rejected** by codex 0.149.1 — must be `"responses"` |
| hermes | not intercepted — `hermes prompt-size --json` | native, offline, exact; reports **bytes** only |

## Routing findings

1. **Layer 1 delivery is uneven, and "configured" is not "delivered".** The
   only evidence that settles it is the request body. As of 2026-09-03:
   Claude Code expands `CONTEXT.md` only, so the L1 files arrived as a
   **pointer** — routing probe verdict **warn**. `familiar context l1` (added
   2026-09-04) exists to close that: it splices `@`-imports into
   `~/.claude/CLAUDE.md` and names the paths in opencode's `instructions`
   field. hermes is **skipped** — its sanitizer `[BLOCKED]`s any spliced block
   (`l1.py` has the root cause). Re-run the probe before trusting any of this.
   **Open question, and the reason it is stated here rather than settled:** a
   pointer is cheap only if the reader follows it, and the recent evidence is
   that readers often do not. See `pointer-following.md`.
2. codex not wired to PAZRAS at all. Out of scope.
3. hermes ships the tree as pointer files of its own (`~/.hermes/memories/
   {USER,MEMORY}.md`), and `boundaries-compile` splices a delimited advisory
   block into the second. But `hermes prompt-size` reports the memory block as
   327 chars while the file is 1,165 — the compiled block may not be reaching
   the prompt. Unverified.
4. opencode's first request on a fresh session is a title generator (2.4 KB, no
   tools). `select_primary` picks the first tooled request.

## Optimization levers, measured 2026-09-03

The always-loaded pair is now CONTEXT.md 664 + (user-identity.md +
collaboration.md) 1,918 = **2,582 tok** (re-measured 2026-10-09). Each lever
below is independent; the always-read budget is the thing every session pays, so
a cut here beats a cut anywhere in L3.

| Lever | Δ (tok/session) | Owner | Effort |
|---|---|---|---|
| Trim [[consolidation-cycle]] — largest leaf at 5,810 tok | **done 2026-09-11: −1,843** | agent | done |
| Move CONTEXT.md §Write-authority table behind a pointer | **done** (table in `README.md` §Write authority; `CONTEXT.md` 586/800) | human (CONTEXT.md) | done |
| USER.md §How-to-work-with-them — already a pointer (resolved 2026-09-03) | 0 (done) | — | — |
| Promote `../../../../config/practice/conventions/collaboration.md` always-on core to L1 | **done 2026-09-04** (+1,670 incl. user-identity) | human | done |

**A cut is not free if it makes the reader look something up that it then does
not.** Every ✗ marker in `../../../../config/practice/conventions/collaboration.md` is a failure mode observed in real
interaction, and moving those behind a pointer is the change most likely to
invalidate the file's whole purpose. Evaluate before trimming.

The write-authority trim is already in force: `README.md` §Write authority holds
the table, and `CONTEXT.md` keeps one pointer line to it. Measured 2026-10-07 —
the table costs **158 tok** where it is read only when writing to the tree;
`CONTEXT.md` is 586/800, and restoring the table in place of the pointer would
take it to ~744/800. The original −173 figure was a 2026-09-03 estimate, not a before/after
measurement.

## What the numbers mean

- The harness fixed prefix is **1.9x–2.6x the whole PAZRAS always-loaded
  budget** per session, and 15–40x per real session.
- Tool schemas dominate Claude Code (Artifact alone is 8,853 tok); the vendor
  system prompt dominates opencode.
- The routing probe only verifies *delivery*, never *compliance* — whether the
  model obeys what it was handed is a behavioural question this tool cannot
  answer. **That gap is now the load-bearing one:** the L2 index and the L3
  mechanisms are all "delivered" by construction, and nothing here measures
  whether a pointer gets followed.

## Design rules for the audit tool (`pazras-context`)

- **Intercept, never reconstruct** — on-disk counting gave a ~3× error; the
  request body (stub SSE recorder, three dialects, zero API cost, offline) is
  the only artefact that cannot be wrong.
- **cwd is part of the measurement**; an empty temp dir default is the harness
  floor.
- **`unattributed` is a deliberate bucket** — never guess an owner to force a
  100% total.
- **Bytes are exact, tokens an estimate** (tiktoken o200k_base); tables lead
  with bytes.
- **The route probe tests delivery, never compliance.** Routers are parsed
  from markdown, not hand-listed.

## Verification

```bash
cd ~/06_SYSTEM
engine/familiar context harness --interactive --cwd=~/06_SYSTEM
engine/familiar context tree --check
engine/familiar context route --check
```
