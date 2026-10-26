---
title: Skill adoption
summary: Vetting a skill arriving from anywhere — provenance and supply chain
origin: authored
authority: human
trust: trusted
last_verified: 2026-08-28
use_count: 9
last_used: 2026-10-15
promoted_from: []           # authored 2026-08-28; no journal entry for that session
source:
supersedes:
related: [skill-routing, knowledge-vs-skills, memory-mechanisms]
tags: [skills, adoption, provenance, supply-chain]
scope: ["06_SYSTEM/memory/skills/**"]
area: [B]
stability: stable
verified_log: [2026-08-28]
---

# Skill adoption

How a skill enters `memory/skills/`, and why that is not the same as copying
someone else's `SKILL.md` into this repo.

## The objection, and its limit

*"Importing external skills means maintaining re-retrievable knowledge."*

True for exactly one thing: **copying an actively-maintained upstream body into
this repo.** That creates a fork that goes stale against a maintainer with more
capacity than we have.

It does not apply to what we actually store. The adopted record holds the
**adaptation** — scope bindings, antitriggers tuned against the other ~648
skills, trust tier, `use_count` history, citations into `knowledge/`, and notes
like "failed on the iGPU". None of that exists upstream, so none of it is
re-retrievable.

> **Do not fork the body — wrap it.** What enters is an *adoption record*,
> not necessarily a copy.

## Import modes

Mode is decided by upstream's licence and trackability, **not by preference**.

| Mode | Body lives | Use when | Cost |
|---|---|---|---|
| `link` | upstream, in place | maintained upstream, pinnable, or licence forbids copying | zero drift |
| `vendor` | copied into this repo | upstream unmaintained/gone, we diverged, or offline need | we own updates |
| `derive` | generated here | built from a book, course, docs or repo by a builder skill | we own it fully |
| `authored` | here, written by us | no external source | we own it fully |

Evidence this matters: `~/.claude/plugins/.../skills/pdf/SKILL.md` declares
`license: Proprietary`. It **must** be `link`. Meanwhile
`anthropic-agent-skills` is a git repo (pin the commit); `~/.hermes/skills` is
not (nothing to pin — prefer `link` and re-check on upgrade).

A `link` record still carries our full frontmatter. That is the point.

## Adoption scenarios

| # | Scenario | Typical mode | Origin |
|---|---|---|---|
| 1 | Marketplace / hub install | `link` | imported |
| 2 | Good `SKILL.md` found in a repo or gist | `vendor` | imported |
| 3 | Distilled from documentation | `derive` | derived |
| 4 | Distilled from a book or course | `derive` | derived |
| 5 | hermes synthesised it from repeated actions | `link` or `vendor` | learned |
| 6 | A pattern recurring across projects (third repo to need it) | `authored` | learned |
| 7 | Written deliberately | `authored` | authored |
| 8 | Forked from an existing skill and adapted | `vendor` | imported |

Scenario 6 is the promotion path from episodic to durable: when the same trap or
procedure is hit in three different projects, it has earned a skill. That
signal used to be detectable by counting a per-repo `.lore.md` store, which was
retired 2026-09-11 ([[memory-architecture]] §The four domains); today the same
judgement comes from the journal (`journal search`) and the consolidation pass,
and `the promotion stage` surfaces the candidate.

## The gate

Five stages. **The gate is proportional to origin** — a skill you wrote does not
need a supply-chain review.

| Stage | Does what | Who |
|---|---|---|
| 00 intake | fetch, hash, dedup check, licence, upstream pin | script |
| 01 classify | subject (its folder), scope, triggers, antitriggers | agent |
| 02 review | safety, boundary check, cite-not-restate; the scan records it | agent + human + `skills scan` |
| 03 install | frontmatter, place, regenerate routers | script |
| 04 trial | accrue `use_count`, record notes, promote or deprecate | runtime + cron |

| Origin | 00 | 01 | 02 | 03 | 04 |
|---|---|---|---|---|---|
| `authored` | skip | self | skip | ✓ | optional |
| `learned` | skip | ✓ | light | ✓ | ✓ |
| `derived` | source provenance only | ✓ | ✓ | ✓ | ✓ |
| `imported` | ✓ | ✓ | **full** | ✓ | ✓ |

### The scan is the instrument, not the gate

`familiar skills scan` runs skillspector (static) over the artifact an agent will
read — our record, plus the upstream body when `mode: link` — and writes
`memory/skills/_scans.json` pinned to a digest of the bytes it saw. That record is
the point: 30 of 40 skills are `link`, so a body can change under us, and
"reviewed" was previously unfalsifiable. `--check` fails when the bytes on disk
are not the bytes that were scanned, and when a `trust: trusted` skill has an
undispositioned HIGH.

What it does not do is decide. Measured on 2026-10-24 over 84 scans: 40
HIGH/CRITICAL labels, one real finding, and the semantic tier (`--llm`, by hand,
advisory) contributed none while emitting 19 labels that were opinions about
documentation. Static catches invisible payloads — zero-width, bidi, hidden
comments, encoded blobs — which no reader can do, and exact jailbreak phrasing,
which any rewrite evades. Read the body as well; the scanner is a record and a
tripwire, not a reviewer.

### Why stage 02 is not bureaucracy

A `SKILL.md` is **executable text from a stranger** — instructions that will
govern agent behaviour, sometimes with tool access. Importing one is a
supply-chain event, not a download. Stage 02 asks: does it instruct actions
outside its stated purpose, does it exfiltrate, does it disable safeguards, does
it restate facts that belong in `knowledge/`. Imported skills enter at
`trust: quarantine` or `trial` — never `trusted` on their own say-so.

## Tooling split

Divide by what is mechanical versus what is judgement.

**Script** — `familiar skills adopt` (deterministic, reproducible):
fetch and hash; detect duplicates (`xlsx` already exists 4×); capture licence,
upstream remote and commit; scaffold frontmatter from the template; **detect
trigger collisions against every existing skill**; place or link; regenerate the
routers. **No outward symlinks** — zero-install since 2026-08-30, see
`skill-routing.md`. It must **refuse to guess** — on ambiguity it stops and
reports rather than inventing a subject or a trigger.

**Agent** — the adoption skill (judgement):
writing `triggers`/`antitriggers` that do not collide across a 648-skill
library; the stage-02 safety read; choosing `link` vs `vendor`; spotting facts
that should be cited from `knowledge/` rather than restated; writing the
"When NOT to use this" section.

**Human** — promoting `trial` → `trusted`, at any time and for any reason. One
lever, and not a queue: the threshold below promotes without being asked, so a
human promotion is the exception the automation cannot make, not a step every
skill waits for (user, 2026-10-15: both paths stand).

**Not jinja.** The frontmatter scaffold is `../../../skills/_skill-template.md` plus variable
substitution; adding a template engine adds a dependency to a bash system for
string replacement. Use the template file and `sed`/`envsubst`.

## The recursion

The adoption mechanism is itself a skill — and it is the one skill that must be
`authored`, never imported. A trust boundary cannot be installed from outside
the trust boundary.

## Verification

```bash
# every canonical skill declares a mode and an origin
grep -L "^origin:" ~/06_SYSTEM/memory/skills/*/*/SKILL.md
# no vendored skill carries a non-permissive licence
grep -rl "license:.*Proprietary" ~/06_SYSTEM/memory/skills/
```

## Adoption policy (decided 2026-08-28)

### Adopt on first use, automatically

Do not sweep all 648 skills into the library. A skill is adopted the first time
it is actually used — that way the library that forms is the one in use, and
every record carries real usage data from the start.

Mechanised as **Loop D** (see [[memory-mechanisms]]): the usage hook notices an
invocation of a skill with no adoption record, and appends an adoption request.
The timer creates a stub record — `mode: link`, `origin: imported`,
`trust: trial`, pinned to whatever upstream it came from — and queues it for
enrichment. The adoption skill then fills the routing surface.

A stub is not a bypass of the gate: a stub is `trial`, never `trusted`, and an
`imported` stub still owes its stage-02 review before promotion.

### Promotion is automatic; deletion never is

Policy: **as automatic as possible**, made safe by an asymmetry. The human may
promote a skill at any time as well; the two paths are not in competition, and
a human promotion is not undone by the threshold (user, 2026-10-15).

| Transition | Who | Why |
|---|---|---|
| `trial` → `trusted` | **automatic**, on usage threshold | cheap if wrong — a bad skill gets routed to, then demoted |
| `trusted` → `trial` | **automatic**, on disuse | reversible |
| `trial` → `deprecated` | **automatic**, on long disuse | reversible; still on disk, just not routed |
| `deprecated` → deleted | **human only** | **not reversible** |
| stage-02 safety review | **never automatic** for `imported` | see below |

Promotion errors are recoverable by demotion. Deletion errors are not.
`deprecated` is therefore a *state*, not a removal — the record stays, carrying
its provenance and history, and simply stops being routed to.

Two constraints on the automation, both consequences of facts recorded elsewhere:

1. **`use_count` is biased both ways.** Since 2026-10-09 it counts sessions that
   read the `SKILL.md` ([[memory-ranking]]): a read to maintain the skill counts,
   and a human's read or a hermes session does not.
   Demotion may therefore *lower trust* but must never delete, and a skill with
   `authority: human` or `pinned` is exempt from automatic demotion entirely.
2. **The safety review cannot be automated away.** Trust *level* is a quality
   judgement and can move on usage evidence. The stage-02 review is a
   supply-chain check on executable text from a stranger — and pruning cannot
   undo having already run malicious instructions. Quality is recoverable;
   compromise is not.

## Why this leaf never names the skill

[[knowledge-vs-skills]]: skills point at knowledge; knowledge never points at
skills. The rule exists so a skill can be renamed or replaced without editing
the knowledge that describes what it does — and a prose mention creates exactly
the coupling the rule forbids. This leaf therefore says "the adoption skill"
and lets `skills/TRIGGERS.md` resolve the name. Raised by the 2026-08-31
consolidation report; do not put the name back.
