# Familiaris

**A personal knowledge system and the agent stack that maintains it.** A folder
hierarchy for one person's work (PAZRAS), the engine that creates and checks
it, a cross-harness memory for coding agents that consolidates itself nightly,
and boundaries declared once and compiled into each harness's guard. Linux and
systemd only.

Three names, three levels, and they are not interchangeable:

| name | what it names |
|---|---|
| **PAZRAS** | the folder hierarchy this system maintains — a convention, like the XDG base-directory spec |
| **Familiaris** | the software that defines and maintains it: this repository |
| **familiar** | the one command you type: `familiar <subject> <verb>` |

The distinction reaches the paths. `~/.local/share/pazras/` (override:
`PAZRAS_DATA_DIR`) holds one tree's state — its transcripts, ledgers and index —
so it carries the tree's name, not the software's: two PAZRAS trees on one
machine need two roots, and a Familiaris upgrade must not have to move them.
The `PAZRAS_` prefix on every variable says the same thing, so a Familiaris
upgrade renames no variable and moves no root.

The mythic vocabulary (the Vigil, the Clew, the Guises) is documentation, never
a path or a config key; `memory/knowledge/system/publication/glossary.md` maps
each name to its subject.

---

## What runs, and what does not yet

**Runnable** means executed on a fresh clone at `~/06_SYSTEM`, with a scratch
`HOME` and `PARA_ROOT`, and exit 0. **Needs an install** means the command is
real but depends on something a fresh clone does not have; read the code, or
set the dependency up first. Every row below was run in that scratch tree
(2026-10-15, P5).

| Command | | What it does |
|---|---|---|
| `familiar structure validate` | runnable | the profile and the master config parse; no duplicate Area codes |
| `familiar structure init` | runnable | creates the PARA tree under `$PARA_ROOT`, and nothing outside it |
| `familiar structure status` | runnable | sizes and state of each category |
| `familiar structure skeleton [--check]` | runnable | seeds the files every agent session is handed (router, user placeholders). On a published tree they are all present, so it reports nothing to seed and exits 0 |
| `familiar structure generate --check` | runnable | `STRUCTURE.md`'s tables match the profile and master config |
| `familiar structure maps --check` | runnable | the architecture figures are what the registers say; `familiar structure maps` rewrites them |
| `familiar structure link` | runnable | links `familiar` into `~/.local/bin` |
| `familiar structure project create\|list\|complete` | runnable | a project under `01_PROJECTS`, archived to `05_ARCHIVES` |
| `familiar structure zettel daily\|new` | runnable | a daily or permanent note in `03_ZETTEL`, its Area validated |
| `familiar context l1 [--check]` | runnable | compiles the always-loaded files into each installed harness's entry point. A harness whose config directory is absent is reported `absent`, and nothing is written for it |
| `familiar knowledge index --check` · `skills index --check` · `glossary --check` | runnable | the generated routers match the tree |
| `familiar knowledge ontology check` | runnable | the class registers hold, and every folder has an owner |
| `familiar consolidation vault --check` | runnable | the vault contract matches the posture and the registers. Run `vault --write` after `engine/boundaries/compile.py`: the contract LISTS the generated files, so compiling the guard puts it out of date |
| `familiar consolidation status` · `queue` | runnable | capture and consolidation state; the open decisions |
| `familiar consolidation run --dry-run` | runnable | the whole nightly pass, reporting what it would do and calling no model |
| `engine/boundaries/compile.py`, then `--check` | runnable | compiles `config/boundaries/*.yaml` into each harness's guard. Two targets are files under `$HOME`; `--explain PATH --model local\|remote` answers a question without compiling |
| `familiar consolidation run` | needs an install | the nightly pass for real: it reads harness sessions and calls a model. Distilling needs a `pi` model, local by default (`config/profile.example.yaml`, `models:`) |
| `familiar knowledge journal index\|search` | needs an install | the journal's embedding index: nothing to do while there is no journal, and Ollama with an embedding model once there is one |
| `familiar backup run\|verify\|prune\|sync\|reconcile` | needs an install | restic repositories at the profile's `storage:` paths. `run` writes to them, which needs a passphrase file. `sync` and `reconcile` also need an adapter: `engine/backup/remotes/` is the interface, `storage.remote:` picks one, and with none the off-site half is skipped with a warning |
| `familiar schedule timers [--check]` | needs an install | stages systemd units from the timer table into a dotfiles source; `--apply-dotfiles` writes them, and is a sign-off decision |
| `familiar checks healthcheck [--tier daily\|weekly\|monthly]` | needs an install | an installed machine's links, timers, mounts and every registered check at that tier's cadence (see below); on a fresh clone the units it asks `systemctl` about are not this machine's |
| `familiar checks updates [--check]` | needs an install | which tools (`mise`), pi extensions (`npm`) and linked skill upstreams (`git ls-remote`) have a newer version. Read-only: it prints the command that applies each and the checks to run after |
| `python3 engine/checks/checks.py --run pre-commit` | runnable | the commit gate. Green here, with the checks that measure the exporting instance skipped and counted |
| `python3 engine/checks/checks.py --run daily\|weekly\|monthly` | runnable | a healthcheck tier's registry checks, without the machine-state sections `familiar checks healthcheck` adds. `--coverage` lists every `familiar` check mode against the registry |

### How often each check runs

Every check is an entry in `engine/checks/checks.py` and sits at the cheapest cadence
it can afford. A timer tier runs its own checks and every tier below it.

| gate | runs | forbids | measured |
|---|---|---|---|
| `pre-commit` | every commit | network, a model, a harness | about 70 s |
| `daily` | `familiar-healthcheck-daily.timer`, 06:45 | the same, so a flaky link cannot fail it | about 6 s |
| `weekly` | `familiar-healthcheck.timer`, Wednesday 07:00 | a paid call | about 90 s |
| `monthly` | `familiar-healthcheck-monthly.timer`, the 3rd, 07:30 | a paid call | see `memory/knowledge/system/checks/healthcheck.md` |

Each run leaves `$PAZRAS_DATA_DIR/healthcheck/<tier>.status`. The shell greeting
(`engine/host/pazras-aliases.sh`) prints a banner while a tier's last run was red or its
timer stopped, and clears it on the next green run.

## First run

```bash
git clone <repo> ~/06_SYSTEM
cd ~/06_SYSTEM
engine/familiar structure link        # `familiar` on PATH, via ~/.local/bin
familiar structure validate
familiar structure skeleton           # the router and the user placeholders
familiar structure init               # the PARA tree under $PARA_ROOT
familiar structure status
```

A fresh clone runs on `config/profile.example.yaml` and
`config/structure/pazras-master-config.example.sh`. To make it yours, copy each
to the name without `.example` and edit it. A clone anywhere other than
`~/06_SYSTEM` sets `install:` in its profile.

**Try it without touching your home:**

```bash
HOME=/tmp/h PARA_ROOT=/tmp/p engine/familiar structure init     # writes under /tmp/p only
mkdir -p /tmp/h/.claude /tmp/h/.pi/agent
HOME=/tmp/h engine/familiar context l1                          # writes the harness entry points under /tmp/h
```

`context l1` reports a harness whose config directory is absent as `absent`
and writes nothing for it.

`~/.local/bin/familiar` is a **symlink** to `engine/familiar`. Nothing is
copied, so the version-controlled script is always the one that runs.

## Projects and the Zettelkasten

```bash
familiar structure project create "2026-Q4_Paper-Title" "A_Work"
familiar structure project list
familiar structure project complete "2026-Q4_Paper-Title"   # moves to 05_ARCHIVES
familiar structure zettel daily
familiar structure zettel new "A.1.2.3" "note-title"
```

A project belongs to exactly one Area and needs a defined outcome. If it has no
end state, it is an Area, not a project. A Zettel id's leading letter is
validated against the Areas in the profile. `~/03_ZETTEL` is meant to be
**human-only**: an install denies agents reads and writes there with a rule in
`config/boundaries/read-write.yaml`. That file holds one rule per sensitive path
on the machine, so it is the install's own and does not ship;
`config/boundaries/rules.example.yaml` is the template to copy.

## Working with agents

The cross-harness knowledge base is `memory/`; the entry point for every
session is `CONTEXT.md`. Boundaries (what agents may not touch) are declared
once in `config/boundaries/` and compiled to each harness.

```bash
familiar consolidation status     # capture and consolidation state
familiar consolidation report     # the last night's report, once a night has run
engine/boundaries/compile.py --check
```

## Backups

```bash
familiar backup run               # whatever is due today
familiar backup verify            # restic check
familiar backup prune             # retention, and reclaim space
familiar backup sync              # push repo deltas to the configured remotes
```

**A green timer does not mean a successful backup.** `systemctl --user
list-timers` reports that the timer *fired*, not that the service succeeded.
The real state:

```bash
systemctl --user status pazras-backup.service
journalctl --user -u pazras-backup.service -n 20
cat ~/.cache/pazras-status
```

The design — authority, tiers, repos, the rules — is `STORAGE-MODEL.md`.

Two files are yours to copy before the first real run, and both ship as
`.example` beside the name the engine actually reads:

```bash
cp config/backup/backup-excludes.example.txt config/backup/backup-excludes.txt
cp config/backup/mirror-excludes.example.txt config/backup/mirror-excludes.txt
```

**The off-site half is an adapter.** This engine names no provider: it names a
contract, and `storage.remote:` in the profile picks the file that implements
it. `engine/backup/remotes/example.sh` is the template and reaches nothing, so
an install with no provider still runs — the archive disk syncs, and `sync`
logs that the off-site copy was not updated. `engine/backup/remotes/README.md`
is the interface and the three failure modes worth knowing before you write one.

## Changing the system

Everything structural lives in **two files**: the profile holds the install's
facts (install root, PARA root, Areas, storage paths, models), the master
config the system's shape (categories, Zettel layout, backup frequencies,
timers).

```bash
$EDITOR config/profile.yaml                        # Areas, roots, storage, models
$EDITOR config/structure/pazras-master-config.sh   # categories, Zettel, backup, timers
familiar structure validate
familiar structure init           # create anything newly defined, under $PARA_ROOT
familiar structure generate       # regenerate STRUCTURE.md's tables
```

Scripts read both through `pazras-config-loader.sh`; none of them hardcode a
path or an Area. If you find yourself editing a script to add an Area, stop —
it belongs in the profile.

Each PARA directory's README is kept in `config/structure/READMEs/<NAME>.md`,
which is version-controlled; the directories are not. An install links each
one into its directory and edits it here. `init` does not create the links
yet.

## Documents

| Read | For |
|---|---|
| `STRUCTURE.md` | what the tree is made of, and the filing rules |
| `STORAGE-MODEL.md` | where bytes live, and the storage rules |
| `engine/README.md` | the engine's directories |
| `docs/` | the documentation being written |

## Licence

Familiaris is source-available under the **Business Source License 1.1**
(`LICENSE`), and each version becomes open source under the GNU AGPL-3.0 four
years after it is published. Copyright (C) 2025-2026 Robin Gutzen.

| You want to | What applies |
|---|---|
| run it as your own personal system, at home or at work | free, under the licence's Additional Use Grant |
| use it for non-commercial research or teaching | free, under the same grant |
| read, change and share the code outside production | free, under the licence itself |
| build it into a product or service, or offer it to others, with or without publishing the source | a **commercial licence** from the author (`NOTICE`); field-exclusive licences are possible |
| use a version published four or more years ago | the AGPL-3.0 |

The releases published up to 2026-10-20 were released under the AGPL-3.0 and
stay under it. Contributions are welcome under the contributor licence
agreement in `CONTRIBUTING.md`, which keeps these licences possible. The
project's name is not covered by any licence (`NOTICE`).
