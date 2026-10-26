---
title: P.A.Z.R.A.S structure
summary: Navigating or changing the PARA structure and its config
origin: authored
authority: agent
trust: trusted
last_verified: 2026-08-31
use_count: 10
last_used: 2026-10-20
promoted_from: []
source:
supersedes:
related: [obsidian-vault, memory-architecture, pazras-cli, file-naming]
tags: [familiar, para, structure, config, areas]
scope: []                   # the tree is everywhere; this applies anywhere
area: []                    # spans all Areas A-Q by definition
stability: stable
verified_log: [2026-08-31]
---

# P.A.Z.R.A.S structure

Where things live and why, plus the places the tree on disk has drifted from
the configuration that claims to define it.

**The philosophy is not here** — it is `06_SYSTEM/CLAUDE.md` §System Philosophy
and the per-directory guides in `06_SYSTEM/config/structure/READMEs/`. This leaf is the
structural facts an agent needs to navigate and not break things.

## The one thing to know

**The configuration is the source of truth, and it is two files.**

```
06_SYSTEM/config/profile.yaml                       ← this install: roots, Areas, storage, models
06_SYSTEM/config/structure/pazras-master-config.sh  ← the system: PARA folders, Zettel, backup, timers
~/.local/bin/familiar → 06_SYSTEM/engine/familiar   ← the one command on PATH
```

The profile (since P1, 2026-10-14) holds what makes the tree one person's
install: the install root, the PARA root, the Areas, the restic and archive
paths, the models. `engine/lib/profile.py` is its one parser; bash reads it
through `profile.py --sh`. `PARA_ROOT` and `PAZRAS_INSTALL` in the environment
beat the file, so `PARA_ROOT=/tmp/x familiar structure init` writes under
`/tmp/x` and nowhere else. Structural changes go in one of the two files, then
`familiar structure init`. Scripts read the config; they do not hardcode.
Editing a script to add a directory is the failure this design exists to
prevent.

Verified 2026-10-13: `~/.local/bin/familiar` is a symlink to
`06_SYSTEM/engine/familiar`, so the typed command is version-controlled
source. Scripts source their siblings by path (`$SCRIPT_DIR/../…`), so no
install point sits between them and the source.

## The seven top-level directories

`00_INBOX` `01_PROJECTS` `02_AREAS` `03_ZETTEL` `04_RESOURCES` `05_ARCHIVES`
`06_SYSTEM` — all seven exist at `~/`. Definitions: `PAZRAS_STRUCTURE` in the
master config; the decision framework for which one a thing belongs in is
`CLAUDE.md` §Resources vs Areas.

`03_ZETTEL` is elevated from a Resources subfolder to a top level of its own
because it is an *active* thinking space, not passive reference. It is also
memory domain **D1** and is off limits to agents — no read, no write, declared
in `../../../../config/boundaries/read-write.yaml` and enforced by the guards compiled from it. See
[[memory-architecture]] and [[boundaries]].

## The 17 Areas — and the entries that do not conform

`areas:` in `config/profile.yaml` declares 17, coded `A`–`Q` (the master
config's `AREAS` table until P1; the loader still builds `AREAS` from the
profile, in the old field order):
`A_Science` `B_Tech` `C_Writing` `D_Art` `E_Connection` `F_Community`
`G_Embodiment` `H_Health` `I_Mindfulness` `J_Culture` `K_Cuisine` `L_Career`
`M_Academia` `N_Finance` `O_Travel` `P_Home` `Q_Ventures`. All 17 exist on disk.

These Area codes are what `area:` in leaf frontmatter refers to, and one axis
of the spatial retrieval prior in [[memory-ranking]].

### The `_` prefix means "not an Area"

Resolved 2026-08-31. Three non-Area entries were found in `02_AREAS/` on
2026-08-30; two were drift and are gone:

- `App-Builder/` — a duplicate of a skill already vendored into
  `memory/skills/system/practice/app-builder/`, byte-identical. **Removed.**
- `drift-to-determinism` — a symlink to
  `/home/rgutzen/.hermes/skills/...`, the **previous machine's** home. Dead
  since the migration to user `rg`, and the skill exists nowhere on this
  machine. **Removed; unrecoverable.**
- `_Deep_Life/` — **legitimate, and deliberately not an Area.** Life planning
  after Cal Newport's Deep Life stack (`I_0`–`I_3` discipline/organisation/
  craft/simplification, `II_0`–`II_2` values/service/transformation, plus a
  mission manifesto). It is *more general than any Area*, so making it an Area
  would misfile it.

> An entry directly under a PARA directory is well-formed if it matches that
> directory's naming rule (`[A-Q]_*` for `02_AREAS/`) **or** begins with `_`.
> The `_` prefix marks cross-cutting or structural content that the directory
> holds but does not categorise, and sorts it to the top.

The tree already used this without naming it: `_README` in three PARA
directories, `_assets` in the Zettel structure, `_leaf-template.md` and
`_category.md` under `memory/`. `_Deep_Life` sitting above `A_Science` is the
convention expressing what it is — it governs why the Areas exist.

**Proposed, not enforced:** `familiar structure validate` currently accepts anything
under `02_AREAS/`. Teaching it this rule would turn a convention into a check.

### `Q_Ventures` — added 2026-10-20

The 17th Area: one folder per venture. A venture folder holds the
**company's** property only. The user's personal stake in a venture
(contracts, equity, compensation) stays in `L_Career/<Venture>/`. The split
follows ownership: a confidentiality clause binds the company part, and the
personal part outlasts the role. A finished venture moves to
`05_ARCHIVES/Areas/`; the Area stays. Each venture's `AGENTS.md` carries its
own rules; never name a venture in a leaf that travels to the public tree.

What may cross into `memory/` is the **method, not the property**: knowledge of
how the user works on a venture may be written there; customer data and
intellectual property never are (user, 2026-10-21). The venture folder is also
that venture's own institutional knowledge base — the one colleagues eventually
share — so a claim about its work lands there first.

### Stale symlinks from the migration

`drift-to-determinism` was not unique. Broken symlinks pointing into
`/home/rgutzen/` survive elsewhere — `04_RESOURCES/Software/Snakemake-cookbook/
snake-blaustein-mpi` is another. Sweep with:

```bash
find ~/0[1-5]_* -xtype l 2>/dev/null
```

## PARA READMEs — the convention, and where it is not applied

`CLAUDE.md` states the authoritative README for each PARA directory lives in
`06_SYSTEM/config/structure/READMEs/` with a single symlink pointing back in, and that **all
six** directories follow it. All six source files exist. The symlinks do not:

Repaired 2026-08-31 — all five checkable directories now symlink to the source:

| Directory | Link | State |
|---|---|---|
| `00_INBOX/00_README` | `../06_SYSTEM/config/structure/READMEs/00_INBOX.md` | ✅ |
| `01_PROJECTS/README.md` | `../06_SYSTEM/config/structure/READMEs/01_PROJECTS.md` | ✅ |
| `02_AREAS/_README` | `../06_SYSTEM/config/structure/READMEs/02_AREAS.md` | ✅ created |
| `04_RESOURCES/_README` | `../06_SYSTEM/config/structure/READMEs/04_RESOURCES.md` | ✅ was a regular file; content was identical, so converting lost nothing |
| `05_ARCHIVES/_README` | `../06_SYSTEM/config/structure/READMEs/05_ARCHIVES.md` | ✅ created |
| `03_ZETTEL/` | — | not checked — agents may not read it |

**Three link names are in use** (`00_README`, `README.md`, `_README`), so there
is no single filename to test for. New links use `_README`, per the `_` rule
above. Standardising the other two is a one-line change nobody has made;
`01_PROJECTS/README.md` in particular can be mistaken for a project's own.

## Naming

- Zettel notes: `{Area}.{Cat}.{Sub}.{N}_{descriptive-name}.md`, e.g.
  `A.1.2.3_cortical-wave-measurement-methods.md`. The dotted id is the third
  axis of the spatial prior. Area letter validated against `AREAS`.
- Projects: `YYYY-MM-DD_Name` or `YYYY-QN_Name`; the date prefix is the time
  axis of the spatial prior.

## Verification

```bash
familiar structure validate
ls -l ~/.local/bin/familiar                             # must be a symlink into 06_SYSTEM/engine
ls ~/02_AREAS/ | grep -vE '^[A-Q]_|^_'                  # expect: nothing
find ~/0[1-5]_* -xtype l                                # broken symlinks from the migration
for d in 00_INBOX 01_PROJECTS 02_AREAS 04_RESOURCES 05_ARCHIVES; do
  ls -la ~/"$d" | grep -i readme; done                  # symlink, file, or absent?
```
