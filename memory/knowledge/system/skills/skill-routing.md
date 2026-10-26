---
title: Skill routing
summary: How a task reaches a skill: the four resolution signals, zero-install
origin: authored
authority: human
trust: trusted
last_verified: 2026-09-02
use_count: 17
last_used: 2026-10-15
promoted_from: []  # originated 2026-08-28; no journal entry for that session
source:
supersedes:
related: [memory-ranking, knowledge-vs-skills, consolidation-cycle, claude-code, memory-mechanisms, orchestrators, prior-art-memory-systems, skill-adoption, journal-index, voice, knowledge-index, pointer-following]
tags: [skills, routing, context, icm]
scope: ["06_SYSTEM/**"]
area: [B]
stability: evolving         # was stable: the measured token/library counts drift
verified_log: [2026-09-02, 2026-08-30]
---

# Skill routing

Selecting the right skill for a task, without paying for the library.

## The problem, in numbers

Two different numbers, and conflating them is the trap this section exists to
prevent.

**Cost if the whole library were installed** (measured 2026-08-28):

| | |
|---|---|
| `SKILL.md` files present on this machine | **648** |
| Description text, all sources | 153,093 chars ≈ **38,273 tokens** |
| Share of a 200k context, before the first user word | ~19% |
| Duplicates across sources | `xlsx`, `pdf`, `docx`, `skill-creator`, `github-code-review` — 4x each |

**Cost of what was actually installed** (measured 2026-08-30, `~/.claude/skills`):

| | chars | tokens |
|---|---|---|
| 11 canonical skills, symlinked from `memory/skills/` | 1,423 | **355** |
| 4 enabled plugin skills (`document-skills`, `claude-api`) | 4,073 | **1,018** |
| Tier-0 router budget (`skills/CONTEXT.md`) | — | **~400** |

Three facts follow, and they were not obvious before measuring:

1. Claude Code injects `name` + `description` for **every** installed skill at
   session start, unconditionally. There is no lazy loading of descriptions.
   Symlinking a skill into a harness home always costs its description.
2. **Injection cost is O(installed); routing cost is O(1).** The crossover is at
   roughly **13 skills** — below that, native injection is cheaper than the
   router; above it, the router wins and keeps winning.
3. The two mechanisms are **additive, not alternative**. While skills were both
   symlinked *and* routed, both costs were paid.

The library grows from three directions at once — **imported** external
expertise, **learned** skills that hermes synthesises from repeated actions
(`skills.creation_nudge_interval: 15`), and **derived** skills built by
skill-builders from books and courses. Injection cost scales linearly with a
library designed to grow without bound. It cannot be the mechanism.

## Zero-install

**Decided 2026-08-30.** Canonical skills are **not symlinked into any harness
home.** They are reached only by descent through `skills/CONTEXT.md`.

The 11 symlinks in `~/.claude/skills/` were removed the same day. At 11 skills
this *costs* about 45 tokens against native injection; the decision is made for
the library the system is being built for (several hundred skills), not for
today's, because retrofitting routing after the library has grown means
retrofitting it while every session is already paying 20k tokens.

**What this gives up:** Claude Code exposes `/name` only for *installed* skills,
so zero-install removes slash invocation of canonical skills — signal 1 in the
table below, the human-guidance channel. Accepted deliberately: a skill that
needs explicit invocation gets a **slash command** written for it, which is a
per-skill opt-in cost instead of a whole-library standing cost. Since
2026-09-02 that command is **generated**, not written — see §User-invoked
skills.

**Future option, not now:** once descent through the routers is itself the
bottleneck — plausibly past ~200 skills, where a subject can no longer be
browsed in one read — replace descent with a **local skill-retrieval agent**: a
small model over the trigger index and frontmatter, returning a skill id. It is
the right move only when the round trip costs less than the tokens it saves;
that is not true at 11 skills, and probably not at 50. Revisit with data from
the skill-usage log, not by intuition.

## User-invoked skills

**Adopted 2026-09-02**, from `mattpocock->skills`, whose one organising axis is
*who may invoke this*. It maps exactly onto the resolution order above: signal 1
is the human channel, signals 2–4 are the model's. So the axis is one
frontmatter field, not a second mechanism.

| `invocation:` | Reachable by | Indexed by |
|---|---|---|
| `model` (default) | model or human | routers + `../../../skills/TRIGGERS.md` |
| `user` | **human only** | nothing the model reads |

`user` is not a hint, it is structural. `~/06_SYSTEM/engine/consolidation/stages/reindex.py` filters the
population *before* rendering, so a user-invoked skill is absent from Tier 0's
counts, from its subject's Tier 2 table and from the trigger index. There is no
string for the model to match on and no row for it to browse to. The upstream
formulation is "user-invoked skills have no description, so nothing but the
human can reach them"; ours is stronger, because a skill the router never emits
cannot be reached even by a model that goes looking.

The human's own index is `../../../skills/USER-INVOKED.md` — generated, and pointed at by
nothing, so it costs no session tokens.

### Why a command and not an installed skill

Both harnesses can host a skill; only one can hide it.

| | Claude Code | opencode 1.18.23 |
|---|---|---|
| skill dirs read | `~/.claude/skills/` | `~/.claude/skills/`, `~/.memory/skills/`, `~/.config/opencode/skill/` |
| command dirs read | `~/.claude/commands/*.md` | `~/.config/opencode/{command,commands}/**/*.md`, symlinks followed |
| model can reach a *command* | only via the SlashCommand tool | **no model-facing command tool** |
| `disable-model-invocation` | supported | **absent** (0 occurrences in the binary; `allow_implicit_invocation` likewise) |

opencode has no way to hide an installed skill from the model, so installing
these as skills would break the invariant there. It also exposes no tool by
which a model can fire a command. A **command** is therefore the only construct
that is human-only in both harnesses at once — and on the Claude Code side
`disable-model-invocation: true` closes the one hole, the SlashCommand tool.

This is also why the commands are not symlinks into `skills/`: the two harnesses
want different frontmatter for the same skill, and one generated file per
harness is cheaper than a compatibility shim in either.

### The commands are generated, never hand-maintained

Same governing rule as the routers ([[memory-architecture]]: markdown is truth,
indexes are disposable caches). `familiar skills index` emits, for every
`invocation: user` skill, one file into each harness command home that exists.
Two guards, because these write outside the repo:

- **Never clobber.** A command file without the generated banner is left alone
  and reported. `~/.claude/commands/` is the human's directory first.
- **Clean up after itself.** A generated command whose skill is gone is removed;
  a hand-written one never is.

### The zero-install adapter

Upstream skills assume the whole upstream set is installed, so their bodies say
*"call the Skill tool with `grilling`"*. Under zero-install there is no such tool
entry. The generator resolves this at emit time: each command carries the
`related:` model-invoked skills of its record as an explicit name → body-path
table. The adaptation lives in the generated artifact, so the upstream body is
never edited and `git pull` stays a fast-forward.

## The principle

**Skill routing is knowledge routing.** It uses the same progressive-disclosure
shape as `knowledge/`, for the same reason: every token of irrelevant context is
a token of diluted attention.

| Tier | File | Cost | Loaded |
|---|---|---|---|
| 0 | `skills/CONTEXT.md` | ~550 tok | **on demand**, from `CONTEXT.md` |
| 1 | `skills/<branch>/CONTEXT.md` | ~200–500 tok | on branch match |
| 2 | `skills/<branch>/<subject>/CONTEXT.md` | ~200–500 tok | on subject match |
| 3 | `skills/<branch>/<subject>/<skill>/SKILL.md` | varies | on selection |

Under zero-install, **nothing about skills is loaded automatically** — Tier 0 is
itself on demand, reached from the routing table in `CONTEXT.md`. Standing
cost is therefore 0, against 38,273 if the library were installed.

Tier 0 names **branches, never skills**. That is what keeps it constant as the
library grows: at 11 skills or 600, it is the same file.

## Resolution order

Four signals, in strict precedence. Stop at the first that answers.

1. **Explicit human invocation** — a purpose-written slash command, a bundle,
   or "use X" by name. Always wins; never second-guessed. Since zero-install
   removed `/skill` for canonical skills, this channel now costs one command
   per skill that needs it — write the command rather than installing the skill.
2. **Scope binding** — the working directory pre-selects branches. Path-derived
   context is free: it costs no tokens and no model call. `03_ZETTEL/**` binds to
   read-only skills, enforcing the D1 boundary structurally rather than by
   instruction.
3. **Trigger match** — task vocabulary against the trigger index. `triggers`
   surface a skill; `antitriggers` suppress it. Antitriggers are what stop a
   library this size from becoming ambiguous.
4. **Subject browse** — read a branch router, then a subject one. Two round
   trips; correct when the first three miss.

When none resolve: **ask, or proceed without a skill.** Loading a
plausible-looking skill "just in case" is the failure this mechanism prevents.

## The router is generated, never hand-maintained

`skills/CONTEXT.md`, every branch router and every subject router are
**derived artifacts**, rebuilt
from frontmatter by `familiar skills index`. This follows the governing rule
in [[memory-architecture]]: markdown is truth, indexes are disposable caches.

A hand-maintained index over 648 growing skills drifts within weeks, and a stale
router is *worse than none* — the agent trusts it and stops looking. Generation
is what makes the mechanism survive growth.

## The trigger index

**Built 2026-08-30 (M1 Task 4).** `familiar skills index` emits
`skills/TRIGGERS.md` alongside the routers, built from `triggers:` /
`antitriggers:` frontmatter: 75 trigger terms and 51 antitriggers over 11
skills, plus an §Ambiguous terms section listing any term that selects more
than one skill (currently none). A term that is ambiguous cannot resolve at
signal 3 alone and must fall through to browse.

It is **read on demand, never injected** — so it costs zero always-loaded tokens
and may grow to any size. Being lexical it is also deterministic and auditable:
a match can be explained by naming the term that fired, which an embedding
similarity cannot.

This is the deliberate answer to "should routing use RAG?" for `skills/` and
`knowledge/`: **no.** Over a curated corpus with a hand-designed hierarchy and
declared trigger vocabulary, exact lexical matching beats vector retrieval and
needs no model, no index rebuild and no service. Embedding retrieval is reserved
for `journal/` — unbounded, unindexable by hand, and where exact recall is the
whole point. See [[memory-architecture]] §D4.

## Trigger promotion — signal 4 should become signal 3

Resolution order is a cost gradient: signal 2 is free, signal 3 costs a grep,
signal 4 costs a round trip. Nothing currently moves a decision *down* that
gradient, so a browse that resolves correctly today costs the same tomorrow.

Adopted 2026-08-30 from Zheng et al. §6, after Kahneman's dual-process theory:
migrate work from slow deliberate System II into fast intuitive System I, so a
decision once reasoned about becomes cheap. Here:

> When a skill is selected by **subject browse** (signal 4), the vocabulary
> that led there is a `triggers:` candidate. The consolidation pass proposes it;
> next occurrence resolves at signal 3 for free.

**Implemented 2026-08-30.** `skill-usage.jsonl` lines now carry three more
keys: `signal` (`external|explicit|trigger|scope|browse|unknown`), `caller`
(the raw `caller.type` from the Skill tool input) and `terms` (up to 12
stopworded tokens from the invocation args). `terms` is what makes `signal`
actionable — without it the pass would know promotion is due but not what to
promote.

> **The signal is INFERRED, not reported.** A `PostToolUse` hook cannot see the
> agent's reasoning; it sees `caller`, `args` and `cwd`. `pazras-memory`
> reproduces the resolution order over those three and records the first that
> fits. It is deterministic, auditable and free — and it can be wrong. Read
> `browse` as *"no declared trigger term matched the args"*, which is exactly
> the condition trigger promotion tests for, rather than as proof a browse
> happened.

Guard against runaway: a proposed trigger that would also match an existing
`antitriggers:` entry is dropped, not promoted. Proposals go to the nightly
report, never straight into frontmatter.

## Provenance and lifecycle

Skills arrive from sources with very different trust, so `origin` and `trust` are
separate fields. A `learned` skill is narrow but highly trusted for this user; an
`imported` skill is broad but unvetted.

```
imported ──▶ quarantine ──▶ trial ──▶ trusted ──▶ deprecated
                              ▲          │
                              └──────────┘   demoted on disuse
```

- `quarantine` — never loaded without announcing it first.
- `trial` — usable; the agent reports afterwards whether it helped.
- `trusted` — routed to freely.
- `deprecated` — retained for provenance, never routed to.

Promotion and demotion are driven by `use_count` / `last_used`, which hermes
already models (`learning_graph.py`: `SkillNode.use_count`, `state`,
`pinned`, `related_skills`). Reuse that vocabulary rather than inventing a
parallel one.

## Deduplication

Four copies of `xlsx` is four chances to route to the stale one. One canonical
copy per skill in `memory/skills/`; every harness reaches it **by path, through
the routers** — not by symlink, since 2026-08-30. Hermes-bundled skills are the
deliberate exception: they stay upstream-managed in `~/.hermes/skills/` and are
referenced, not copied, so they do not go stale.

Plugin skills are a separate budget the routers do not control. The four enabled
`anthropic-agent-skills` skills cost 1,018 tokens per session — three times the
entire canonical library. Disabling an unused plugin is cheaper than any
routing change.

## Prior art on this machine

Do not rebuild these:

- `~/.hermes/.skills_prompt_snapshot.json` — a working two-tier index:
  `category_descriptions` (15, ~569 tok) over `skills` (82, ~6,747 tok), plus a
  `manifest` of path → [hash, size] for change detection.
- `~/.hermes/hermes-agent/agent/skill_bundles.py` — named sets of skills under one slash command
  (`~/.hermes/skill-bundles/*.yaml`). This is signal 1 already implemented.
- `conditions: {requires_tools, requires_toolsets, fallback_for_*}` and
  `platforms` — conditional gating, already in the snapshot schema.

## Verification

```bash
find ~/06_SYSTEM/memory/skills -name SKILL.md | wc -l
wc -c ~/06_SYSTEM/memory/skills/CONTEXT.md      # must stay under 2400 chars
familiar skills index --check               # 0 = routers match frontmatter
ls ~/.claude/skills/                            # must contain NO canonical skill
ls ~/.claude/commands/ ~/.config/opencode/command/   # one file per user-invoked skill
grep -L 'GENERATED by' ~/.claude/commands/*.md       # hand-written ones; the generator skips these
```
