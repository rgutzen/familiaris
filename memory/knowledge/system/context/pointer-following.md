---
title: Pointer following — was the pointer actually read?
summary: Measured follow rates over the staged transcript corpus, and the always-on decision they inform
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-09
verified_log: [2026-10-09, 2026-09-11]
use_count: 6
last_used: 2026-10-11
promoted_from: []
source:
supersedes:
related: [context-budget, memory-mechanisms, memory-architecture, consolidation-cycle, skill-routing]
tags: [context, always-on, pointers, measurement, baseline]
scope: ["06_SYSTEM/memory/**"]
area: [B]
stability: evolving
---

# Pointer following — was the pointer actually read?

The design question this leaf exists for: **the always-on layer assumes the
model looks when it needs to.** Nothing measured that. `familiar context route`
measures *delivery* — whether a file's bytes are in the request body — and
says so itself: *"whether the model OBEYED what it was given… is behavioural
and would need a live model, a bill, and a nondeterministic answer."*

That half is measurable anyway, and the evidence was already on disk. Every
staged transcript carries raw `tool_use` blocks **with their inputs**;
`transcripts.py` drops those inputs in its *reduction*, so the model is not
handed `cat` output — but the reduction is in memory, and the verbatim tier
keeps everything. So this needed a script, not an instrumentation project.

```bash
familiar context pointers [--since=YYYY-MM-DD] [--until=YYYY-MM-DD] [--top=N] [--json]
```

## What the number means, and the one limitation that shapes how to read it

A reference to a path is **not** proof the model read it. A deliberate read, a
`cat` inside a loop over a directory, a `grep -r` whose argument mentions the
tree, and a heredoc body quoting a path in prose all look identical. So every
count here is an **upper bound** on following.

What it can prove is the negative, and the negative is the direction the
always-on question turns on: **a path referenced zero times was not
followed.**

Classes, and the middle two are why the report needs the live tree rather than
a list:

| Class | Meaning |
|---|---|
| `always-on` | in `posture.ALWAYS_LOADED` — already in the prompt. Touching it is the model re-reading what it was given |
| `routed` | named by `CONTEXT.md`'s routing table or by `knowledge/INDEX.md`. The model had a reason to look |
| `cold` | named by neither. Reached because the model already knew or guessed the path — this is what proves a pointer worked without being needed |
| `stale` | not in the tree at all. Reported with the dates it was tried, because a model following a pointer written when the file was there is a different finding from a pointer that rotted |

The two anchors are read from the files themselves. `knowledge/INDEX.md`
announces *"Paths are relative to `~/06_SYSTEM/memory/knowledge/`"*; the
routing table is relative to `memory/`. Resolving either against the other's
root drops every entry silently and reclassifies a whole branch as cold —
which the first version of the report did, and which is why
`pointers.route_token` and `pointers.normalise` are two functions.

## Baseline — the OLD regime, measured 2026-09-11

**Read this as a baseline and nothing else.** `knowledge/INDEX.md` (L2) and
the MCP memory server both landed 2026-09-11, so almost all of this corpus
predates them. It is the state of the pointer design *before* the mechanisms
that are supposed to make pointers work.

| | corpus ≤ 2026-09-10 | ≥ 2026-09-11 |
|---|---|---|
| staged transcripts | 180 | 34 |
| sessions touching `memory/` | 71 (39%) | 12 (35%) |
| distinct `memory/` paths | 110 | 50 |
| references, `always-on` | 24 | 14 |
| references, `routed` | 168 | 65 |
| references, `cold` | 179 | 51 |
| references, `stale` | 341 | 42 |
| `mcp__pazras-memory__*` calls, ever | **2** | — |

Measured with `familiar context pointers`. The window split is exact:
`--until=2026-09-10` / `--since=2026-09-11`. Whole-corpus totals, for a
like-for-like re-measure: 214 staged transcripts, 83 touching (38%), 131
distinct paths, and 38 / 233 / 230 / 383 references across always-on / routed
/ cold / stale.

### One correction to these numbers, kept because the cause is instructive

A first version counted 86 `always-on` and 570 `stale` references. Both were
wrong, for the same reason: **a heredoc body is stdin, not argv.** A shell
command *writing* a file that happens to mention a path is indistinguishable,
to a regex over the command text, from a command opening it — and `cat >
doc.md <<'EOF' … EOF` full of prose about the tree is exactly how this tree
gets written. Measured share: 18% of all bash path references.

It mattered most in the class that decides the question. The always-on files
are the ones most often *written about*, so heredoc inflation distorts
`always-on` worst — 86 became 38. `pointers.strip_heredocs` removes the bodies
and keeps the opening line, which is still an argument.

### A second correction: the counter was blind to one harness (2026-10-09)

`scan` counted `tool_use` blocks. Pi spells the same block `toolCall`, so every
Pi session — 19 of the 314 staged — contributed **zero** calls, zero references,
and no place in "sessions touching the tree". The failure had no symptom: a
harness whose blocks a reader does not recognise looks exactly like a session
that opened nothing, and this report's own limit (*"a path referenced zero times
was not followed"*) made that silence read as a finding.

It was found by needing the same walk for something else — `touches:`, the
subject facet stage 1 writes into a journal entry. The walk now lives once, in
`transcripts._turns`, and both readers use it.

**Re-measured 2026-10-09, whole corpus: 314 staged transcripts, 19,932 tool
calls, 145 touching the tree (46%), 159 distinct paths, and 167 / 355 / 620 /
704 references across always-on / routed / cold / stale** (127 → 139 sessions
reaching a cold path).

Read that as a like-for-like re-measure of the *mechanism*, not of the regime:
both numbers moved at once, because the corpus grew from 214 to 314 transcripts
since 2026-09-11 **and** the counter was seeing one harness less. The classes,
the ~10:1 bash-over-read ratio, and the negative signal are what this report is
for; the absolute counts in the baseline table above were produced by the blind
counter and are not comparable to these without re-running `--until=2026-09-10`.

### What the numbers say

- **Following happens through `bash`, not the read tool.** 808 of 884 references
  corpus-wide, about 10:1. A counter that instrumented the harness's read tool
  would have measured a tenth of the traffic and reported it as a finding. Both
  channels are counted, and the MCP-namespaced spellings of both.
- **61% of sessions never touch `memory/` at all**, and the share is stable across
  the boundary (39% / 35%). Expected, and not the finding. Sessions doing project
  work (`data-activist-demo`, `DynVision`) reach the tree essentially never.
- **The top-referenced paths are the memory system's own documentation.** 58
  references to [[consolidation-cycle]] under its OLD home in the
  `operations/` branch, 36 under the current one, and references to `MEMORY.md`.
  The observer is the observed: these are sessions maintaining this system, not
  sessions using it.
- **The single most-referenced path no longer exists.** 58 references, 2026-08-30
  to 2026-09-09, to [[consolidation-cycle]] where it used to live under
  `knowledge/system/` -- it moved to `knowledge/system/` in `66135b7`. Written
  that way on purpose, because backticking the dead path would make the linker
  read this sentence as a pointer to it and flag the evidence as drift. The
  references are concentrated before the move, which is the honest reading, but
  the last one is 2026-09-09, five days after it, so something was still pointing
  at the old location. What remains in the tree is in `journal/**`, which is
  append-only and correct.
- **Stale attempts fall by roughly a third per session** -- 341 in 180 sessions
  (1.9) against 42 in 34 (1.2). Suggestive, not conclusive: the newer window is
  34 sessions and most of them are this system's own maintenance.
- **The one tool built for pointer-following has been called twice.** Two calls
  ever to `mcp__pazras-memory__*` (one `journal_search`, one `grep`). That is a
  fact about adoption, not about the mechanism -- but it is the mechanism the
  cold case depends on, so it is the thing to watch.

### What the numbers do NOT say

- They do not say pointers are not followed. `cold` references number 179 in the
  baseline window, in a corpus where no index existed: the model was reaching
  leaves it had no written route to, which is pointer-following working without a
  pointer.
- They are not evidence about L2 or the MCP server, which postdate 95% of the
  corpus. **Re-measure after two weeks of real work** and compare against the
  table above; that comparison is the reason the baseline is written down.
- They do not answer the compliance question for the `✗` lines in
  `../../../../config/practice/conventions/collaboration.md`. An agent violating a `✗` line does so
  visibly in its output, and output is exactly what this instrument does not read.

## The decision this informs

Three options, with the honest cost of each. **Every 1,000 tokens of always-on
is paid by every session in every repository**, which is why the choice is by
*consequence of being missed* and never by size.

1. **Keep L2 as it is** — index plus on-demand. Cost: the measured follow rate.
   Right if the cold numbers above are the real signal, since they say the model
   reaches what it needs.
2. **Promote a small set to always-on**, chosen by consequence of being missed.
   Cost: the budget, paid unconditionally. Ratified only against a follow rate
   that is low *and* a fact whose absence is expensive.
3. **Split by consequence** — always-on for the `../../../../config/practice/conventions/collaboration.md`
   `✗` lines and the routing entry point; on-demand for everything else. This is
   the likely answer, and it is a
**policy** decision, not a mechanism one, so it belongs to the user.

The option not on this list, because the evidence does not support it: moving
anything *out* of `../../../../config/practice/conventions/collaboration.md` behind a pointer. It is the
strongest always-on candidate in the tree — every line is a behaviour that has
actually gone wrong — and it is the untested part of the rationale rather than
the refuted part.

### Constraint on any proposal here

`../../../../config/practice/user/user-identity.md` (cap 1,375 chars, currently 827) and `conventions/**`
are **directive**: agents propose, never write. The compiled always-loaded
set is `posture.ALWAYS_LOADED` in `engine/consolidation/posture.py`,
mirrored from `engine/context/navigation.py`. A proposal that
moves facts into either file must be checked against the cap and handed to the
user, not applied.

## Status

**Decision not yet taken.** The instrument exists, the baseline is recorded,
and the choice among the three options above is the user's. Until it is
decided, the default is option 1 — L2 unchanged — because it is the current
state and the measurement does not by itself argue for changing it.

## Verification

```bash
familiar context pointers --top=20
familiar context pointers --until=2026-09-10   # the baseline window above
familiar context pointers --since=2026-09-11   # the new regime, once it has data
familiar context pointers --json | jq '.mcp_calls'
```

