---
title: File naming — the seven rules, the hub files, and the `_refs` renames
summary: What a file may be called, which structural file means what, and the renames the rules imply
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-09
verified_log: [2026-10-09]
use_count: 4
last_used: 2026-10-13
promoted_from:
source:
supersedes: []
related: [pazras-structure, knowledge-index, knowledge-vs-skills, memory-architecture]
tags: [naming, conventions, structure, hub-files, rename]
triggers: [file naming, naming convention, README, CONTEXT, INDEX, hub file, _refs, rename a file, Title Case, lowercase-hyphenated]
scope: ["06_SYSTEM/**"]
area: [A, B]
stability: evolving
---

# File naming

The seven rules live in `config/knowledge/naming.yaml` and are checked by
`ontology check` (`naming-valid`). This leaf records the three things the
register alone does not: **which structural file means what** — the gap the
five folders with two hub files expose — **how a rule that is not checkable is
held**, and **the renames the rules imply**.

## The seven rules, in one table

| # | rule | checkable | example |
|---|---|---|---|
| 1 | `-` separates words, `_` separates fields | yes | `pazras-structure.md` · `2026-09-29_slug.md` |
| 2 | a leading `_` marks a NON-MEMBER of its folder | yes | `_leaf-template.md` · a `_refs` container |
| 3 | case carries layer: `UPPERCASE.md` structural, `lowercase-hyphenated.md` content | yes | `CONTEXT.md` vs `pazras-structure.md` |
| 4 | a stem identifies itself read alone | **no** — a judgement | `memory-ranking`, never `ranking` |
| 5 | a filename never encodes a facet | yes | `reference_…` duplicates `origin: imported` |
| 6 | dates are ISO-8601 and lead when the file is an event | yes | `2026-09-29_slug.md` |
| 7 | directories are lowercase-hyphenated; plural for collections | yes | `skills/` · `boundaries/` |

Rule 4 is the only one a check cannot apply, and it is declared as such in the
register (`checkable: false`) rather than silently skipped.

## Hub files — the rule rule 3 was missing

Rule 3 says `UPPERCASE.md` is structural, **"one per folder"**. The tree
violates that in five places, and no check enforces the clause:

| folder | structural files | why two |
|---|---|---|
| `.` | `CONTEXT.md` `README.md` | router + human entry |
| `config/knowledge/` | `CONTEXT.md` `README.md` | router + register explainer |
| `dev/` | `CONTEXT.md` `README.md` | router + track index |
| `memory/knowledge/` | `CONTEXT.md` `INDEX.md` | router + disclosure index |
| `memory/skills/` | `CONTEXT.md` `README.md` | router + authordoc |

**The missing rule is which structural file means what.** Case already settles
*structural vs content* (rule 3); it does not settle *which structural file*.
The convention the tree already practises, written down here so a new folder
does not reinvent it:

> A directory's structural files are its **hub files**. Each names one job, and
> a name is used for that job and no other:
>
> - **`CONTEXT.md`** — the ROUTER. What is here, and where to go next. The
>   contract filename an agent harness reads first. Generated for `system/`
>   (O3a); hand-written elsewhere, and `areas/CONTEXT.md` is a declared
>   exception because it indexes Areas A–P, not leaves.
> - **`INDEX.md`** — the one DISCLOSURE index between a router and a leaf.
>   Exactly one per tree; `memory/knowledge/INDEX.md` is the only instance, and
>   a second would be two levels of disclosure, which
>   [[knowledge-index]] forbids.
> - **`README.md`** — the HUMAN entry: why this folder exists and what it is
>   for. For people, not for the routing chain; nothing routes through it.
>
> A folder may carry any subset, but **at most one of each**, and never a
> second `INDEX.md`. `README` with no extension is **not allowed anywhere** —
> every document in this repo is markdown, so the extension is invariant, and
> a bare `README` would be a second naming shape for one kind of file.
> `_README.md` is **not a hub file**: rule 2 makes it a non-member (a draft or
> a template), and no folder has one.

The clause "one per folder" in rule 3 is therefore **wrong as written** and is
proposed for amendment (see the register proposal below): the true statement is
*uppercase is structural*, and the *distribution* of structural files is the
hub-file rule above.

## The `_refs` renames — violation 9 closes

`config/knowledge/violations.yaml` violation 9 measured **13 files under a
`_refs` container in `dev/`** carrying spaces and Title Case. Rule 2 exempts the
`_refs` directory *name* from rule 7, but it says in as many words that the files
inside are still files and still obey rules 1 and 3 — so a Title-Case filename
with spaces inside `_refs` is a genuine breach, not a false positive.

The renames are mechanical: **lowercase-hyphenated, spaces and ` - ` to `-`,
parentheses dropped, apostrophes dropped.**

| was | is |
|---|---|
| `Embrace Complexity (Part 1).md` | `embrace-complexity-part-1.md` |
| `Embrace Complexity (Part 2).md` | `embrace-complexity-part-2.md` |
| `Tony Seale - Data Connectivity.md` | `tony-seale-data-connectivity.md` |
| `Tony Seale - Small World Graphs.md` | `tony-seale-small-world-graphs.md` |
| `Tony Seale - What is Jev.md` | `tony-seale-what-is-jev.md` |
| `Semantic Ontology The Basics.md` | `semantic-ontology-the-basics.md` |
| `Tony Seale - Entropy, Tokenization and Ontology.md` | `tony-seale-entropy-tokenization-and-ontology.md` |
| `Tony Seale - Hierarchical Navigable Small Worlds (HNSW).md` | `tony-seale-hierarchical-navigable-small-worlds-hnsw.md` |
| `Tony Seale - LLMs and Ontology.md` | `tony-seale-llms-and-ontology.md` |
| `Tony Seale - Ontologies and Multi-Agent Systems.md` | `tony-seale-ontologies-and-multi-agent-systems.md` |
| `Tony Seale - Ontologies can save you token.md` | `tony-seale-ontologies-can-save-you-token.md` |
| `Tony Seale - Ontology is the Map, Agent is the Driver.md` | `tony-seale-ontology-is-the-map-agent-is-the-driver.md` |
| `Tony Seale - The Great Compression.md` | `tony-seale-the-great-compression.md` |

**Eight of the thirteen were in the ontology track's reference folder**, and were
deleted with the track on 2026-10-13 (O7). Renaming them first was still right:
it made the remaining five (`dev/jev/_refs/`) conform, and violation 9 now lists
only those five.

**Where the old names still appear.** Nothing links to these files by stem
except `violations.yaml`'s `paths:` and any prose that quotes them; a rename in
git leaves the history intact. `git grep` for the old names before committing.

## What is NOT in scope here

- **P's naming rounds.** Product naming for the public artifact is a Track P
  question on the publication-split branch. File naming and product naming are
  different questions and are not merged.
- **`dev/publication/mythic-lexicon.md` §3 (Title Case).** Re-opened
  2026-10-12. The 2026-10-09 verdict dropped it as a "deprecated lore.md file",
  but the deprecated `lore.md` files were the lore.ai tool's stores; this file
  is the mythic register, renamed from `lore.md` to end that confusion. Whether
  §3 takes Title Case is still Track P's call.
