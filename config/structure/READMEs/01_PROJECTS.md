# P.A.Z.R.A.S Projects Guide

> **Purpose**: Active work with a defined outcome and a deadline
> **Location**: `~/01_PROJECTS/`
> **Review**: Weekly — check progress, archive what's finished

## What belongs here

**Ask**: *"What specific outcome am I trying to achieve, by when?"*

A project is finite — it ends. If the answer to "when is this done?" is
"never, it's ongoing," it belongs in `02_AREAS/` instead, not here.

- Papers with a submission deadline
- Grant applications
- Conference talks/posters
- Specific experiments or analyses with a defined endpoint
- Time-bound collaborations

## Naming

`YYYY-MM-DD_Project-Title/` — the date is when the project started, not a
deadline. Sort by name and you get a rough timeline for free.

## `_data/`

Bulk datasets shared across multiple projects live in `01_PROJECTS/_data/`,
referenced by path from whichever project needs them — not duplicated per
project. Large, low-churn, backed up but excluded from most sync operations
(see `config/backup/backup-excludes.txt`).

## Projects vs Areas vs Zettelkasten

```
New work → Ask: "Does it have a deadline and a defined outcome?"
├─ YES → 01_PROJECTS (this directory)
└─ NO  → Ask: "Am I responsible for maintaining this over time?"
    ├─ YES → 02_AREAS (ongoing responsibility)
    └─ NO  → Ask: "Am I developing understanding, not producing an outcome?"
        └─ YES → 03_ZETTEL (thinking space)
```

## When a project finishes

Move it to `05_ARCHIVES/Projects/` (see the Archives guide). Don't leave
finished projects here — an active-projects folder that's half dead work is
hard to scan at a glance, which defeats the point of the split.

## Version control

Projects with real iteration (code, drafts with meaningful history) should
be their own git repo. `01_PROJECTS` itself is not one repo — each project
under it may be. Projects with no repo and no history yet are a known
cleanup item.
