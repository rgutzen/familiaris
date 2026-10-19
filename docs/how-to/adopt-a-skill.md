# Adopt a skill

A skill is a procedure — how to do something — that a task reaches on demand.
Adopting one means taking instructions written by someone else and putting them
where a model will follow them, so the gate is proportional to where the skill
came from and never optional for one that arrived from outside.

Two halves, and it is worth knowing which is which. The judgement — mode, subject,
triggers, the safety read — is itself a skill:
`memory/skills/system/skills/adopt-skill/SKILL.md`, and a session asked to adopt
something should read it first. The mechanical half is one command,
`familiar skills index`, which regenerates every router from the library.

**`familiar skills adopt` does not exist.** `[[skill-adoption]]` designs it, and
the CLI has one verb under `skills`: `index`. The five steps that are judgement
are done by reading and writing; the two that are deterministic are the commands
below.

A skill can be added in place, in your own tree — the library is what it edits.
The run below used a scratch clone, because `skills index` also writes slash
commands into a harness home when a skill is `invocation: user`:

```console
$ export HOME=/tmp/apothecary/home
$ git clone <repo> $HOME/06_SYSTEM
$ cd $HOME/06_SYSTEM
```

## 1 · Is it a skill, or a claim?

A fact goes in the knowledge tree; a procedure goes here. The test is which
question the artefact answers — "what is true" or "what do I do" — and a fact
filed as a procedure is unfindable, because knowledge is searched by subject and
skills are selected by task
([`knowledge-vs-skills`](../../memory/knowledge/system/knowledge/knowledge-vs-skills.md)).

## 2 · Where it goes

```console
$ find memory/skills/system -maxdepth 1 -mindepth 1 -type d -printf '%f\n' | sort
checks
harness
host
knowledge
practice
skills
```

The path is `memory/skills/<branch>/<subject>/<name>/SKILL.md`, and all three
segments come from the register: `<branch>` is one of `system`, `areas`,
`projects`, and `<subject>` is a subject declared in
`config/knowledge/subjects.yaml`. There is no `category:` field to write — the
subject *is* the path, so the two cannot disagree.

A folder the register does not know is skipped with a warning rather than filed
under a guess:

```console
$ python3 engine/familiar skills index
!! subject 'not-a-subject' is not one of the subjects in subjects.yaml, skipped: skills/system/not-a-subject/table-lint/SKILL.md
```

If no subject fits, the register is the thing to change, and it is directive:
propose the subject and let the user decide.

## 3 · Pick the mode, from the licence and the upstream

Mode is not a preference. It follows from what upstream is and what its licence
permits, and it decides whether you keep a copy of the body at all.

| Mode | Body lives | Use when |
|---|---|---|
| `link` | upstream, in place | maintained upstream and pinnable, or the licence forbids copying |
| `vendor` | copied into the tree | upstream unmaintained or gone, or you have diverged |
| `derive` | here, generated | built from a book, a course or a repo by a builder |
| `authored` | here, written by you | no external source |

**Do not fork the body.** What enters the library is an *adoption record*: scope
bindings, trigger vocabulary, trust tier, usage history, the upstream pin. None
of that exists upstream, so none of it is re-retrievable, and a copied body goes
stale against a maintainer with more capacity than you have.

## 4 · Write the record

The frontmatter is `memory/skills/_skill-template.md` with the values filled in.
Everything below the routing surface is provenance:

```yaml
---
title: Table lint
origin: imported           # imported | authored | learned | derived
authority: agent           # human skills are never auto-pruned
trust: trial               # quarantine | trial | trusted | deprecated
last_verified:
use_count: 0
source: https://example.invalid/agentskills — skills/table-lint
name: table-lint
description: Check a Markdown table's columns line up before it is committed.
invocation: model          # model | user — `user` is hidden from every router
triggers: [lint a table, column alignment, table columns line up]
antitriggers: [format a paragraph, css grid, matrix algebra]
mode: link
upstream_path: ~/04_RESOURCES/Software/agentskills/table-lint
upstream_pin: example/agentskills@abc1234
license: MIT
---

# Table lint

**Adoption record — mode `link`.** The body lives upstream, at
`~/04_RESOURCES/Software/agentskills/table-lint/SKILL.md`, and is not copied here.

## When to use this

Before committing a Markdown table whose columns were hand-edited.

## When NOT to use this

Not for a table the system generated: a generated table is aligned by its
renderer, and a linter that rewrites it is a second source of truth.

## Instructions

Read the upstream body and follow it.
```

Three of those fields are the ones that decide whether the skill is ever found:
**`triggers`** are the vocabulary a task must contain, **`antitriggers`** are the
vocabulary that suppresses it, and **`invocation: user`** removes it from every
router and generates a slash command instead. Triggers are a budget: a generic
term that fires a dozen skills is worse than no term.

Leave a `description:` unquoted. The frontmatter reader strips a trailing comment
but not surrounding quotes, so a quoted description reaches the router with its
quotes in it — visible today in the shipped `code-review` row.

## 5 · Read the body before you trust it

A `SKILL.md` is executable text from a stranger that will govern agent
behaviour, sometimes with tool access. Importing one is a supply-chain event,
not a download. Four questions, in `adopt-skill`'s own words: does it instruct
actions outside its stated purpose, does it exfiltrate, does it disable
safeguards, does it restate facts that belong in the knowledge tree?

An imported skill enters at `trust: quarantine` or `trial`, never `trusted` on
its own say-so. The review is the one stage that cannot be automated away:
quality is recoverable by demotion, and having already run malicious
instructions is not.

## 6 · Regenerate the routers

```console
$ python3 engine/familiar skills index --check
DRIFT skills/CONTEXT.md
DRIFT skills/system/CONTEXT.md
DRIFT skills/system/practice/CONTEXT.md
DRIFT skills/TRIGGERS.md
4 of 8 generated files would change, 0 stale

$ python3 engine/familiar skills index
skills index: 9 routed skills in 4 subjects, 0 user-invoked
  Tier 0  skills/CONTEXT.md  2324 chars (OK, budget 2400)
  Tier 1  skills/system/CONTEXT.md
  Tier 2  skills/system/harness/CONTEXT.md
  Tier 2  skills/system/knowledge/CONTEXT.md
  Tier 2  skills/system/practice/CONTEXT.md
  Tier 2  skills/system/skills/CONTEXT.md
  index   skills/TRIGGERS.md
  index   skills/USER-INVOKED.md  (human-facing; not a router)
  cmds    claude-code  /tmp/apothecary/home/.claude/commands  skipped (no harness home)
  cmds    opencode     /tmp/apothecary/home/.config/opencode/command  skipped (no harness home)
  rewritten: 4
```

Nothing here is hand-edited: the banner in each file says so. The Tier 0 line
shows the budget being spent — the number is the always-on cost of the library's
front page, and it is capped, because every session pays it.

The `cmds` rows are the only writes this command makes outside the tree, and only
for `invocation: user` skills; a reader with no harness home gets `skipped`
rather than an invented directory.

## 7 · Confirm the route

A skill is reached by descent, so check that each step of the descent now knows
about it. Tier 0 names branches, never skills; the subject router names the
skill; the trigger index is the vocabulary lookup.

```console
$ grep table-lint memory/skills/system/practice/CONTEXT.md
| `table-lint` | Check a Markdown table's columns line up before it is committed. | imported (link) | trial |

$ grep 'lint a table' memory/skills/TRIGGERS.md
| lint a table | `table-lint` | practice | trial |
```

`skills/TRIGGERS.md` also carries the collision report, and this is the line to
read after every adoption:

```console
$ sed -n '/## Ambiguous terms/,+2p' memory/skills/TRIGGERS.md
## Ambiguous terms

None — every trigger term selects exactly one skill.
```

A term listed there selects two skills and cannot resolve on vocabulary alone.
The fix is a narrower trigger, not a louder one.

## Lifecycle, and who decides what

Promotion to `trusted` happens on use — automatically, when the usage threshold
is crossed — and the user may promote a skill at any time as well; demotion on
disuse is automatic in the same way. Both are reversible, and neither ends with a
deletion. Deletion is the human's, because nothing else is. `invocation: user`
skills and `authority: human` skills are exempt from automatic demotion.

## Honest limits

**What is measured and what is judgement.** The commands above were run on this
tree: the drift report, the router rows, the trigger index, and the warning for
an undeclared subject. The safety read is a reading, and its quality rests on the
reader.

**`adopt-skill` names one file the export omits.** Its step 8 points at
`config/boundaries/read-write.yaml`, which holds this machine's own deny-list and
does not travel. In a published tree, read `config/boundaries/rules.example.yaml`
for the shape of a rule; the file your own rules go in is the one you copy it to.

**Only `system/` is populated here.** The `areas` and `projects` branches exist in
the register and in the knowledge tree; this library files everything under
`system/` today.

## Read next

- [the Apothecary](../explanation/lore/skills.md) — why zero-install, and what
  the routing costs
- [`skill-routing`](../../memory/knowledge/system/skills/skill-routing.md) — the
  four resolution signals and the measured budget
- [`skill-adoption`](../../memory/knowledge/system/skills/skill-adoption.md) —
  the modes, the scenarios and the proportional gate
