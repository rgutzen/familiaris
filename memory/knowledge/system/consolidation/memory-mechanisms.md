---
title: Memory mechanisms — capture, feedback, consolidation
summary: Hooks and timers: what is actually enforced, and what is only asked for
origin: authored
authority: human
trust: trusted
last_verified: 2026-08-30
use_count: 13
last_used: 2026-10-11
promoted_from: []  # originated 2026-08-28; no journal entry for that session
source:
supersedes:
related: [memory-architecture, skill-routing, skill-adoption, consolidation-cycle, memory-ranking, boundaries, claude-code, user-vs-conventions, context-budget, memory-poisoning-posture, pointer-following, agent-prompt-dream-memory-consolidation, rtk]
tags: [hooks, automation, enforcement, consolidation]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving         # was stable: carries hook wiring + harness status, which upstream owns
verified_log: [2026-08-30]
---

# Memory mechanisms

How usage feeds back into the system automatically, and what "enforced"
actually means.

## What can and cannot be enforced

This is the crux. Only the top three levels are enforcement.

| Level | Mechanism | Implemented by | Can an agent skip it? |
|---|---|---|---|
| 1 · Structural | symlinks, generated files, permissions | `engine/structure/pazras-structure-gen.sh` (stow targets), the generators in §Cross-harness wiring, `~/02_AREAS/B_Tech/dotfiles` | **No** — nothing to skip |
| 2 · Harness-executed | hooks (`SessionEnd`, `PostToolUse`, `PreToolUse`) | `~/.claude/settings.json` → `engine/boundaries/guard.py`, `engine/familiar context capture`, `engine/boundaries/opencode-plugin/` | **No** — the harness runs them |
| 3 · Scheduled | systemd user timer | `engine/schedule/timers-gen.sh` generates the units; `familiar consolidation run` and `healthcheck.sh` are what they run | **No**, but asynchronous |
| 4 · Instructional | rules written in markdown | `CONTEXT.md`, `conventions/**`, every leaf in this tree | **Yes** — advisory only |

> **Everything written in markdown is a request, not a guarantee.** Any
> behaviour that must happen belongs at level 1–3. Putting "always update
> a knowledge leaf" in a `CONTEXT.md` and calling it enforced is the failure this table
> exists to prevent.

### The level claims are checked, and several were wrong

*Written 2026-09-11. The column above is the exit criterion for this file: a
level claim must name the file that implements it, and a claim with no file is
either a plan (it belongs in `../../../../ROADMAP.md`) or a lie.*

A level is a claim about whether a behaviour can be skipped, and until now the
table asserted its own levels with nothing behind them — which made the whole
table level 4. Three instances, all verified:

- **The pass's own correctness was level 4 and is now 2 and 3.** Stage 5d
  shipped on 2026-09-11 with three silent defects and a green 333-test suite.
  Nothing required a stage to state what it guarantees, so the invariants
  existed only in the author's head — author judgement, level 4 in this table's
  own terms, and the first thing to go under context pressure. Now:
  `engine/consolidation/stages/invariants.py` declares them, and an
  undeclared stage is an error rather than a default; it runs from
  `engine/checks/checks.py`, which is level 2 (pre-commit) and level 3 (weekly
  healthcheck).
- **Dependence on a deleted name was level 4 and is now 2 and 3.**
  `memory/MEMORY.md` was deleted on 2026-09-04 and stage 4 kept reading it,
  cap-checking it against nothing, and offering it as a `TARGET:` for a week;
  one proposal would have re-created it. No gate could see it, because a bare
  name is informational in the linker by design. Now
  `engine/checks/declared_paths.py` asserts every declared path either exists or
  is declared deliberately absent **with a reason**, and it is wired into both
  gates.
- **The level claims in *this file* were level 4.** Machine-checked in the
  direction that is checkable: `engine/context/links.py`
  (`STRICT_SOURCES`) fails `familiar context links --check` when a path in this
  file or its four siblings resolves to nothing. Those five files describe this
  repository's own mechanisms, so a path in one of them is a claim a reader is
  meant to follow to the implementing code. Scoped to PATHS rather than bare
  names, and measured rather than assumed: a bare-name rule flags thirteen
  places in these files, nine of which are lines that *record* a removal.

The generalisation, which is the point: **a mechanism claim names the file that
implements it, and a check fails when it cannot.** Everything else in this
section is that rule applied.

### Why 333 green tests did not catch the three stage-5d defects

*Asked as "why did the 279-test suite not catch these?". The count is stale —
the suite is 333 — and the question has a sharper answer than "not enough
tests", which the coverage picture shows.*

**None of the three defects was ever in a commit.** Verified against the whole
history: `engine/consolidation/stages/conflict.py` appears in exactly one
commit (`064aec9`) across all 162, and that commit contains the fixed module and
the tests that found the bugs together. All three were caught during development,
in the working tree, before anything was committed.

So the suite did not miss them at a commit boundary. What was absent is a
mechanism that REQUIRES the properties to be asserted:

- `python3 engine/checks/checks.py --audit` reports every test file under
  `engine/**` is run by a registry entry — and it reported that while each
  defect existed, because it measures coverage of FILES, not of properties.
  Coverage was never the gap.
- The tests that found the three bugs —
  `test_the_superseded_leaf_is_the_one_marked_not_the_superseder`,
  `test_applying_twice_changes_nothing_the_second_time`,
  `test_a_cycle_is_an_error_and_nothing_in_it_is_marked` — are all present in
  `engine/consolidation/tests/test_conflicts.py` today, added in that same commit. They work. The
  reason they existed is that the author chose to write them, and choosing which
  properties matter is judgement: level 4 in this file's own table, and the
  first thing to go under context pressure.

The counterfactual is what makes it a mechanism problem rather than a story
about one careful afternoon. Had those three tests not been written, all three
defects would have shipped and every gate would have stayed green: run 2 of the
`run --check` suite would not notice a marking re-applied nightly, and
`--audit` would not notice the absence of a property nobody had named. That is
now closed for the properties that are generic — idempotence, error/act
disjointness, and direction over generated relation graphs — by
`engine/consolidation/stages/invariants.py`, where a stage that declares
nothing is an error.

The part that is still level 4, stated so it is not mistaken for covered: a
property specific to one module's domain has to be named by a person.
`invariants.py` forces the declaration and checks the generic three; it cannot
invent the fourth.

## The division of labour

**Hooks capture. Cron consolidates.**

Loops A-D below describe *what* each feedback path does. **When** they run is no
longer per-loop: as of 2026-08-30 they are stages of one nightly pass — see
`consolidation-cycle.md`. Ignore the per-loop trigger wording ("weekly", "after
N entries") that survives below; the schedule is the pass.

Capture must be synchronous, cheap, and never call an LLM — it runs on the
user's latency budget. Consolidation is expensive, lossy and asynchronous.

A second rule follows from concurrency: **hooks only ever append to logs; only
the scheduled job mutates tracked files.** Multiple sessions run in parallel; a
hook that edited frontmatter or a knowledge leaf directly would race and produce
git conflicts.

## Loop A — transcripts into the journal

Measured: `~/.claude/projects/` holds 8.1 MB across 12 sessions, with single
transcripts at **3.0 MB**. Raw transcripts must never enter git.

Three tiers of episodic record:

| Tier | Location | In git | Retention |
|---|---|---|---|
| verbatim | `~/.local/share/pazras/transcripts/` | no | prune after N months |
| distilled | `memory/journal/YYYY/MM/*.md` | **yes** | permanent |
| pointer | `knowledge/INDEX.md` | yes | regenerated |

- **Capture** (level 2): a `SessionEnd` hook copies the transcript to the
  verbatim tier and appends one line to the session log. No LLM, no parsing.
- **Consolidate** (level 3): the timer distils new transcripts into one journal
  entry per session — what was done, decisions taken, what failed — citing the
  verbatim file by id so exact recall stays possible.

The journal is therefore already consolidated. Verbatim recall means opening the
staged transcript, which is deliberately outside git.

## Loop B — usage into `use_count`

**Since 2026-10-09 the main source is reads, not invocations** (M2a). Stage 2
counts, per document, the sessions whose staged transcript shows a `read` or
`bash` call naming it — a `SKILL.md` or a knowledge leaf — and folds in the
invocation log below, keyed by session. The log held 2 lines in six weeks: the
library is read through the router, never installed as harness skills, so the
`Skill` event almost never fires. Implemented by
`engine/consolidation/stages/aggregate.py` and `engine/context/pointers.py`
(`reads`).

- **Capture** (level 2): a `PostToolUse` hook matching skill invocations appends
  one JSON line to `~/.local/share/pazras/skill-usage.jsonl`:
  `{ts, harness, skill, session, cwd, signal, caller, terms}`. Append-only — no
  locking, no races. `signal`/`caller`/`terms` were added 2026-08-30 and drive
  trigger promotion ([[skill-routing]]); lines written before that date lack
  them, so any consumer must tolerate their absence.
- **Consolidate** (level 3): the timer aggregates reads and the log and writes
  `use_count` and `last_used` into each skill's and leaf's frontmatter, then
  regenerates the routers.
- **Promote/demote** (human): `trial` → `trusted` stays a human decision.
  Demotion on disuse may be proposed automatically, never applied.

## Loop C — journal into `knowledge/`

- **Trigger** (level 3): nightly, as stage 4 of the consolidation pass.
  *(Was "weekly, or after N new journal entries" — superseded 2026-08-30:
  volume triggers make consolidation a function of how busy the week was,
  while decay is a function of time. See `consolidation-cycle.md`.)*
- **Action**: `familiar consolidation run` (stage 4) reads recent journal entries and:
  - extends `knowledge/` where a durable fact has emerged — **appending to a
    leaf or marking one superseded, never rewriting it wholesale** (L3, and see
    `consolidation-cycle.md` §What stage 4 may propose);
  - **proposes** changes to `../../../../config/practice/conventions/` and `../../../../config/practice/user/user-identity.md` — never writes them,
    per the write-authority table;
  - surfaces facts that recur across projects as candidates for a `knowledge/`
    leaf or a skill (the D2→D3 promotion signal; the per-repo store that used to
    make it countable was retired 2026-09-11).

`MEMORY.md` used to be a third target here: a 2200-char pointer file in
`memory/`, kept under the cap by **displacement** — overflow moved into a
`knowledge/` leaf and left a pointer, never truncated. It was **deleted
2026-09-04** (commit `66135b7`): `memory/` serves every agent on this machine and
the always-on layer is compiled by `familiar context l1` from `CONTEXT.md` +
`../../../../config/practice/user/user-identity.md` + `../../../../config/practice/conventions/collaboration.md`, so a file nothing
loads was ~569 tokens of session floor for no reader. Stage 4 kept reading and
cap-checking it for another week, and one of its proposals would have re-created
it as a leaf-shaped orphan; the reference is now dropped like any other
non-target. The displacement principle survives where it was always load-bearing
— see [[context-budget]].

## Cross-harness wiring

One implementation, three thin adapters. Each harness adapter does nothing but
call `familiar context capture --harness=<name> --event=<event>`.

| Harness | Surface | Status |
|---|---|---|
| Claude Code | `~/.claude/settings.json` — `SessionEnd`, `PostToolUse`, `PreToolUse` | wired. `SessionEnd` and `PostToolUse`/`Skill` run capture; `PreToolUse` runs `wards` (the boundary hook, level 2 — see [[boundaries]]), dippy, and `rtk hook claude` |
| opencode | plugin hooks | wired: `session.idle` in `engine/boundaries/opencode-plugin/` logs the session and stages it through `opencode_extract`; fires in the TUI and in `opencode run` (verified 2026-10-09) |
| hermes | `config.yaml` `hooks:` (shell hooks) | `on_session_end` runs capture and `hermes-session`; `~/.hermes/hooks/` is not the surface |

**Entry-point wiring is separate from capture wiring, and is complete.** All
three harnesses resolve `CONTEXT.md`, each verified by running it
(2026-08-30): Claude Code and opencode through an `@`-import in their global
instruction file, hermes through §-delimited pointer entries in
`~/.hermes/memories/{MEMORY,USER}.md` — **not** a symlink, because hermes
splits on `"\n§\n"` and would rewrite the canonical markdown. Capture hooks
are wired in Claude Code, opencode, hermes and pi; every harness but hermes
feeds `use_count` through its staged transcripts (Loop B).

`codex` is unmeasured: no capture hook is known, and nothing here has
verified one (`session.log` holds no codex line as of 2026-10-09). `pi`
captures through `engine/context/pi-capture/`. Stated rather than omitted, because an absent
row reads as either "nothing to say" or "covered" and it is neither.

## Boundaries are structural, and declared once

The D1 boundary — `~/03_ZETTEL` is human-only, no agent reads or writes it —
was a **level 4** rule until 2026-08-30 (written in `../../../../config/practice/user/user-identity.md`, therefore
advisory and skippable under context pressure). It became level 2 that day, and
on 2026-08-31 it stopped being a special case: **every** boundary is now one
row of `../../../../config/boundaries/read-write.yaml`, compiled outward by
`engine/boundaries/compile.py`.

| Harness | Level | Mechanism |
|---|---|---|
| Claude Code | **2** | `engine/boundaries/guard.py`, a `PreToolUse` hook |
| opencode | **2** | `engine/boundaries/opencode-plugin/`, `tool.execute.before` |
| hermes | **4** | generated prose. A blocking `pre_tool_call` shell hook exists and is unused — [[boundaries]] §hermes |

Denials observed live in Claude Code (all four modes) and opencode
(bash + tool-path halves) on 2026-08-31.

**This is the clearest case in this file of why the level table matters.** The
same sentence is enforcement in two harnesses and a polite request in the
third, and only the generated text is allowed to say which — because it is
generated from the thing that knows.

Rules, modes, the local-vs-remote model axis, and the honest limits:
[[boundaries]]. Do not restate a boundary here or anywhere else; point at the
config.

## Honest limits

State these rather than implying the loop is airtight:

- A hard kill loses the session; only clean exits fire `SessionEnd`.
- `use_count` is **biased both ways**, so demotion must never be automatic on
  it. Low: a read the human makes is invisible, a relative path after a `cd`
  is not resolved, and hermes staging drops tool arguments, so hermes sessions
  count for nothing. High: a session that reads a document to maintain it
  counts as a use.
- Reads replaced the skill-invocation event as the source on 2026-10-09, so
  opencode (which has agents, not skills — no invocation event exists) and pi
  now contribute through their staged transcripts. Only hermes does not.

## Verification

```bash
systemctl --user list-timers | grep familiar
wc -l ~/.local/share/pazras/skill-usage.jsonl
ls ~/06_SYSTEM/memory/journal/$(date +%Y/%m)/
wc -c ~/06_SYSTEM/config/practice/user/user-identity.md   # must stay under 1375 — BYTES
```

**The cap is bytes, not characters.** hermes' `memory_char_limit` says "2200
chars", but the check above is `wc -c`, which counts bytes; em-dashes and arrows
make the two disagree by ~20. Where a cap is enforced, bytes is the conservative
reading that satisfies both. Found 2026-08-31 while updating the (since-deleted)
`MEMORY.md` to the byte.

## Loop D — adopt on first use

Closes the gap between "a skill was used" and "the library knows about it".

- **Capture** (level 2): the Loop B usage hook already sees every invocation.
  When the skill has no adoption record, it appends an adoption request to the
  same log — no extra hook, no extra latency.
- **Consolidate** (level 3): the timer creates a stub record — `mode: link`,
  `origin: imported`, `trust: trial`, pinned to its upstream — and queues it for
  enrichment by the adoption skill (the library names it; this leaf does not —
  [[knowledge-vs-skills]], direction is one-way).
- **Enrich** (agent): routing surface, antitriggers, stage-02 review if
  `imported`. Until then the stub is `trial` and is never routed to as trusted.

This is what makes "adopt on first use" a mechanism rather than an intention.

## Retention policy for the verbatim tier

`~/.local/share/pazras/transcripts/` grows without bound; it is outside git
precisely so it can be pruned. The timer deletes staged transcripts older than
N months **only if** a distilled journal entry citing them exists. If
distillation failed, the verbatim record is kept — never prune the source of a
consolidation that did not happen.
