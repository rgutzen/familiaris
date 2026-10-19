# P.A.Z.R.A.S Archives Guide

> **Purpose**: Inactive material from every other category — kept, not used
> **Location**: `~/05_ARCHIVES/` (staging) → `~/05_ARCHIVES-EXTERNAL/` (the archive disk, authoritative)
> **Review**: Flushed to the archive disk on disk attach, not on a schedule

## What belongs here

**Ask**: *"Is this from a completed project, or no longer active?"*

Archives are the exception to the "every category is a distinct
environment" rule — everything here is de facto inactive, whatever it was
before. That's why it needs no further internal split by area or type
beyond mirroring where it came from.

## Two tiers, one boundary

`05_ARCHIVES/` on the laptop is **staging only**. Content sits there
temporarily until the archive disk is attached, at which point it's flushed out to
`05_ARCHIVES-EXTERNAL/` (the the archive disk mountpoint) and the laptop copy is
cleared. See `STORAGE-MODEL.md` §2 — authority for anything under the
`05_ARCHIVES-EXTERNAL/` prefix belongs to the archive disk, not the laptop, full
stop. If you're editing something in there, it should not be there; move it
back to an active category first.

## Current structure

- `Areas/` — retired area content, mirroring `02_AREAS/<letter>_Name/`
- `Projects/` — finished projects, mirroring `01_PROJECTS/YYYY-MM-DD_Name/`
- `Records/` — historical documents, exports, machine snapshots (e.g.
  Google Takeout, old conda envs) that aren't tied to a specific project
- `Logs/` — old system/automation logs kept for reference, not active
  troubleshooting

## Moving something here

**Move, don't copy** — an archived item should exist in exactly one place.
If it's from `01_PROJECTS/`, it goes to `05_ARCHIVES/Projects/`; from
`02_AREAS/`, to `05_ARCHIVES/Areas/`, preserving the area's letter/name so a
`grep` across active and archived content still makes sense.

## What does NOT belong here

Content you'd reference again soon, or that spans multiple projects/areas —
that's `04_RESOURCES/`, not Archives. The test: Archives is where things go
to stop being touched; Resources is where things go to keep being consulted.
