---
title: Glossary of subjects
summary: The subject ids, their mythic names and their criteria, generated from the register
origin: derived
authority: agent
trust: trial
last_verified: 2026-10-09
use_count: 6
last_used: 2026-10-12
promoted_from:
source: config/knowledge/subjects.yaml
supersedes:
related: [knowledge-index, memory-architecture, knowledge-vs-skills]
tags: [glossary, ontology, subjects]
scope: ["06_SYSTEM/**"]
area: [A, B]
stability: permanent
verified_log: [2026-10-09]
---

# Glossary of subjects

<!-- GENERATED FILE — do not hand-edit. Rebuild: `familiar knowledge glossary` -->

Every subject this system declares, with the question that falsifies it. The register is
`config/knowledge/subjects.yaml`; this leaf is one of its readers, so the two cannot drift.
A subject is a PLACE, not a topic: the id is the folder name where its leaves live (R1e).

14 subjects under `system/`. `areas/` uses A–P unchanged; the `projects` branch is open.

| Subject | Name | Falsified when | Occupies |
|---|---|---|---|
| `backup` | the Larder | Falsified when backups, disks or recovery change. | `engine/backup`, `config/backup` |
| `boundaries` | the Wards | Falsified when a rule, the guard or the compile changes. | `engine/boundaries`, `config/boundaries` |
| `checks` | the Threshold | Falsified when a gate, a test or the healthcheck changes. The WEAKEST subject by the category test -- a gate is arguably a concept spanning the whole repo -- and it is flagged for the first review rather than quietly kept. | `engine/checks` |
| `consolidation` | the Vigil | Falsified when the ACT OF WRITING changes: consolidation, ranking, promotion. | `engine/consolidation` |
| `context` | the Clew | Falsified when what a session carries IN AND OUT changes. | `engine/context` |
| `harness` | the Guises | Falsified when a harness or a model changes. | `engine/harness` |
| `host` | the Hearth | Falsified when THIS MACHINE or its OS changes -- and not when a tool we install on it changes, which is `harness`. Added during planning because `omarchy-host-traps` had no home at all until it existed. | `engine/host` |
| `knowledge` | the Grimoire | Falsified when the WRITTEN RECORD changes: filing, indexing, browsing. | `memory/knowledge`, `engine/knowledge`, `config/knowledge` |
| `orchestration` | the Loom | Falsified when WHO DOES THE WORK changes: which familiar, model, tools and permissions a task is given, and how work is split, dispatched and rejoined. Not when a harness or a model itself changes, which is `harness`; not when what a procedure says changes, which is `skills`. Ratified 2026-10-12 (dev/orchestration/PLAN.md decision 12). | `config/orchestration` |
| `practice` | the Craft | Falsified when `config/practice/conventions/` or `config/practice/user/` changes. | `config/practice` |
| `publication` | the Sign | Falsified when what we show OUTWARD changes. Its first leaf is the generated subject glossary (O3c), which is derived from this register and therefore cannot drift from it. | `docs`, `engine/publication` |
| `schedule` | the Almanac | Falsified when a timer or a unit changes. | `engine/schedule` |
| `skills` | the Apothecary | Falsified when a skill or its routing changes. | `memory/skills` |
| `structure` | the Bones | Falsified when the PARA layout, its config or its CLI changes. | `engine/structure`, `config/structure` |

An empty subject is DECLARED, never missing — its folder appears on its first leaf.
The branch router marks it with a bare name (no trailing slash) for the same reason.
