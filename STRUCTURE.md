# P.A.Z.R.A.S — Structure

**What the system is made of, and how the parts fit together.** This file is the
map. It does not tell you how to *use* the system (`README.md`), where the bytes
live (`STORAGE-MODEL.md`), or what is still unbuilt (`ROADMAP.md`).

> **The tables below are generated from the profile (`config/profile.yaml`: the
> Areas) and `config/structure/pazras-master-config.sh` (the rest).**
> Never hand-edit inside the `BEGIN:`/`END:` markers — edit the source and run
> `familiar structure generate`. Two hand-maintained copies of a machine-readable
> fact always drift; this repo has the scars to prove it.

---

## Why this shape

Human thinking works by **association**; organization works by **category**. The
system does not try to resolve that tension, it separates it:

- **Categories create distinct environments**, one per kind of work, so that
  entering a directory changes what is at hand.
- **Association is carried by links and tags**, which cross those boundaries
  freely.

Categorization is therefore *post-hoc order over a messy working process*, never
a set of exclusive boxes. A thing that belongs in two places gets one home and a
reference from the other.

The stated purpose of the whole apparatus is to spend **less** time at a
computer, not more.

### Why Zettelkasten is top-level

The `Z` is what separates P.A.Z.R.A.S from P.A.R.A. Resources are *passive*
reference, organized by format and context of use. The Zettelkasten is an
*active* thinking space where understanding is developed, connected and
synthesized. Those are different activities, so they get different environments
rather than one being a subfolder of the other.

### The filing decision

Ask, in order, and stop at the first yes:

| Question | Home |
|---|---|
| Does it have a defined outcome and a deadline? | `01_PROJECTS` |
| Am I responsible for maintaining it, ongoing? | `02_AREAS` |
| Am I *developing understanding*, not storing it? | `03_ZETTEL` |
| Will I consult it across several projects or areas? | `04_RESOURCES` |
| Was any of the above true, but is no longer? | `05_ARCHIVES` |
| Is it configuration or automation? | `06_SYSTEM` |

Anything not yet decided goes to `00_INBOX` and is processed later. Capture must
stay frictionless or it stops happening.

---

## Top-level categories

<!-- BEGIN:CATEGORIES (generated) -->
| Directory | Role | Backup | Holds |
|---|---|---|---|
| `00_INBOX` | capture | daily | Temporary capture area for new items |
| `01_PROJECTS` | action | daily | Active projects with specific outcomes and deadlines |
| `02_AREAS` | action | weekly | Ongoing responsibilities and standards to maintain |
| `03_ZETTEL` | knowledge | daily | Personal knowledge development and thinking space |
| `04_RESOURCES` | reference | weekly | Topics and themes for future reference |
| `05_ARCHIVES` | archive | monthly | Inactive items from other categories |
| `06_SYSTEM` | system | daily | System configuration and automation |
<!-- END:CATEGORIES -->

Every category except `06_SYSTEM` carries a README that is **a symlink back into
`06_SYSTEM/config/structure/READMEs/`** — the source of truth, version-controlled here because the
PARA directories are not themselves git repos. Edit the file in `config/structure/READMEs/`, never
the symlink's other end.

## Areas of responsibility

An Area is a standing commitment, not a topic. The letter code is the addressing
scheme used by Zettel note ids and by `area:` in the agent knowledge tree, so it
is stable: renaming an Area is a migration, not an edit.

<!-- BEGIN:AREAS (generated) -->
| Code | Area | Concerns |
|---|---|---|
| `A` | `A_Work` | Paid work, its projects and its obligations |
| `B` | `B_Tech` | Technology, programming, and digital tools |
| `C` | `C_Writing` | Writing, communication, and publishing |
| `D` | `D_Health` | Health, movement, and wellbeing |
| `E` | `E_Home` | Housing, finances, and the household |
<!-- END:AREAS -->

Each Area folder may carry its own status/obligation README and area-specific
workflow subfolders (`_progress`, `_tracking`) where that helps.

## Zettelkasten

The Obsidian vault, at `~/03_ZETTEL`.

<!-- BEGIN:ZETTEL (generated) -->
| Directory | Role | Holds |
|---|---|---|
| `00_Inbox` | capture | Quick captures and unprocessed notes |
| `01_Journal` | daily | Date-based daily notes and journals |
| `02_Permanent-Notes` | permanent | Main knowledge base organized by areas |
| `03_Maps-Of-Content` | structure | Structure notes and topic overviews |
| `04_Templates` | templates | Note templates and formatting guides |
| `_assets` | media | Images, PDFs, and other media files |
<!-- END:ZETTEL -->

Permanent notes are addressed `{Area}.{Category}.{Sub}.{N}_{slug}.md` — e.g.
`A.1.2.3_cortical-wave-measurement-methods.md`. The leading letter is validated
against the Areas table above, which is what ties the two coordinate systems
together.

> **`~/03_ZETTEL` is human-only.** No agent reads or writes it. This is enforced,
> not requested — see `config/boundaries/read-write.yaml`.

---

## How the parts interact

```
   capture ──► 00_INBOX ──► processed into one of:
                             01_PROJECTS ──(completed)──► 05_ARCHIVES
                             02_AREAS    ──(dormant)────► 05_ARCHIVES
                             03_ZETTEL   ── permanent, never archived
                             04_RESOURCES
                                  │
   06_SYSTEM ── config ──► scripts ──► all of the above
        │
        └── memory/ ── the cross-harness knowledge base (see CONTEXT.md)
```

**Two files drive everything.** The profile (`config/profile.yaml`) holds the
install's facts, the Areas among them; `config/structure/pazras-master-config.sh`
defines the categories, Zettel layout and backup schedule. Every script reads
both through `pazras-config-loader.sh`. Structural change happens in one
place and the rest adapts. `~/.local/bin/familiar` is a symlink to `06_SYSTEM/engine/familiar`,
so the version-controlled copy is always the one that runs.

**The agent knowledge base is a distinct system** living at `memory/`, sharing
this repo but not this file's concerns. It has its own entry point
(`CONTEXT.md`), its own memory tiers, and a nightly consolidation pass.
Start there, not here, when working on agent behaviour.

## Backup schedule

<!-- BEGIN:BACKUP (generated) -->
| Frequency | Paths |
|---|---|
| daily | `00_INBOX` `01_PROJECTS` `03_ZETTEL` `06_SYSTEM`  |
| weekly | `02_AREAS`  |
| monthly | `04_RESOURCES` `05_ARCHIVES`  |
<!-- END:BACKUP -->

Frequencies say *how often a path is eligible*, not that a backup ran. What
actually stores the bytes — the restic repos, their copies, and the rules
between them — is `STORAGE-MODEL.md`.

## Regenerating this file

```bash
familiar structure generate          # rewrite the generated blocks
familiar structure generate --check  # exit 3 if they have drifted
familiar structure validate           # check the config itself for errors
```
