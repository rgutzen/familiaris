---
title: Health check — the third scheduled process
summary: Checking the system is sound; what a `--check` drift report means
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-25
verified_log: [2026-09-01, 2026-10-25]
use_count: 7
last_used: 2026-10-14
promoted_from: []           # built 2026-09-01, ROADMAP.md cross-cutting item
source:
supersedes:
related: [scheduled-processes, consolidation-cycle]
tags: [systemd, healthcheck, stow, drift, tiers, cadence, updates]
scope: ["06_SYSTEM/engine/checks/healthcheck.sh", "06_SYSTEM/engine/checks/checks.py", "06_SYSTEM/engine/checks/check_coverage.py", "06_SYSTEM/engine/cli/updates.py"]
area: [B]
stability: evolving
---

# Health check — the third scheduled process

`familiar checks healthcheck [--tier daily|weekly|monthly]`, wired as three timers
(`familiar-healthcheck-daily`, `familiar-healthcheck`, `familiar-healthcheck-monthly`)
in [[scheduled-processes]]'s `PAZRAS_TIMERS` table. See §Tiers; before 2026-10-25 it was one
weekly run, and a leaf here called its unit `pazras-healthcheck.timer`, which no longer exists. The ROADMAP cross-cutting
item asked for this "separate from memory": where `familiar consolidation run`
([[consolidation-cycle]]) asks *is the knowledge tree still true*, this asks
*is the machinery underneath it still correctly wired* — a structurally
different question with a different failure mode, so it gets its own process
rather than a tenth stage bolted onto the nine already carefully ordered and
documented in [[consolidation-cycle]].

## What it checks

1. **Stow package integrity** — `bootstrap.sh --dry-run` for pending link
   changes, plus: does `bootstrap.sh`'s hardcoded `systemctl --user enable`
   list still cover every unit `PAZRAS_TIMERS` declares? (It didn't, for two
   units, found while building this — see [[scheduled-processes]] §What
   existed before.)
2. **Generated-file drift** — `familiar structure generate --check`,
   `familiar schedule timers --check`, `boundaries-compile --check`,
   `familiar context {links,tree,l1} --check`, `familiar {skills,knowledge}
   index --check`. Every generator this system has gets checked, from one of two
   places — see §Which gate runs what, because "one place" was wrong here.
3. **Scheduled-unit results**, not just activation. The trap this section
   exists to close is named in `06_SYSTEM/CLAUDE.md` itself: *"A green timer
   means the timer fired, **not** that the service succeeded — check
   `systemctl --user status <unit>` before believing it. That distinction hid
   a four-day backup outage."* This check reads `systemctl --user show
   <unit>.service -p Result` for every `PAZRAS_TIMERS` unit and fails loudly
   on anything but `success`/never-run.
4. **Mounts and disk space** — is the archive disk mounted when the reconcile/mirror/
   verify timers would need it (informational only — normal for it to be
   unplugged); home filesystem usage.
5. **Dirty working trees** — `06_SYSTEM` and dotfiles. A dirty `06_SYSTEM`
   tree silently blocks the memory pass's stage 0 preflight
   ([[consolidation-cycle]]) for as many nights as it stays dirty, and
   nothing else was surfacing that.
6. **Available system updates** — reported via `checkupdates` (pacman-contrib)
   if present. **Never applied.**

## Tiers — one cadence per check, written once in the registry

A check is in `pre-commit` and/or in **one** timer tier of `engine/checks/checks.py`.
A tier run covers its own checks and every tier below it, so the weekly run is the
daily run plus what is too slow or too distant to repeat daily. The registry is the only
place a cadence is written: `healthcheck.sh` asks `checks.py --due TIER` and wraps each
section it owns in `due ID`, and `checks.py --audit` fails when a section loses its line,
a `due` line has no entry, an owned check is in no tier, or a tier names a timer that
`PAZRAS_TIMERS` does not declare.

| gate | fires | runs | forbids | measured 2026-10-25 |
|---|---|---|---|---|
| `pre-commit` | every commit | the lint, drift and unit gates | network, model, harness, anything heavy | 68 s |
| `daily` | `familiar-healthcheck-daily.timer`, 06:45 | file and live-state checks: drift, generated files, budgets, relay, the catalogue, unit results, mounts, git trees | network, model, Ollama, paid call, harness, heavy | 6 s |
| `weekly` | `familiar-healthcheck.timer`, Wed 07:00 | daily + the 12 test suites, the node suites, `updates`, `jev check`, `eval --validate`, package updates, proposals | paid call | 83 s |
| `monthly` | `familiar-healthcheck-monthly.timer`, day 3, 07:30 | weekly + `context route` | paid call | 394 s, of which `context route` is 287 s |

Why these cuts. **Cost:** daily must stay under a few seconds a check, or it is skipped
by hand. **Network:** a flaky link must never fail the nightly tier, so `updates` and
`jev check` are weekly and `advisory`. **Drift rate:** the nightly pass rewrites the tree at
03:30 and the machine moves between runs, so tree, budget and live-state checks are daily;
a harness changes what it sends only when it is upgraded, so `context route`, which starts
four harness CLIs against a recorder, is monthly. **Side effects:** `orchestration scout`
writes `scout-last.json` and its exit 1 is meant to fail a unit, so it keeps its Monday
timer and the registry names that timer's config line as its `owner`; `backup verify` and
`structure validate` likewise. An `owner` that is a timer line is run by no gate.

Each entry may declare `effects` (`network`, `model`, `ollama`, `paid`, `harness`, `writes`,
`heavy`). `tests/test_tiers.py` fails an entry in `pre-commit` or `daily` that declares one
of the expensive ones, and any scheduled entry that declares `paid`. `advisory="reason"`
turns a red result into a warning: a release landing or a republish due is news for a
person, not a defect.

### How to run each tier

```bash
familiar checks healthcheck --tier daily         # the timer's command; add --fix for the mechanical repairs
familiar checks healthcheck --tier weekly        # the default, as before
familiar checks healthcheck --tier monthly
familiar checks healthcheck --only hc-mounts     # one section the script owns; leaves no result
python3 engine/checks/checks.py --run daily      # only the registry's own checks of that tier
python3 engine/checks/checks.py --run CHECK_ID   # one check
python3 engine/checks/checks.py --list --gate weekly
python3 engine/checks/checks.py --coverage       # every familiar check mode vs the registry
```

### How a failure surfaces

1. **The tier's result file**, `$PAZRAS_DATA_DIR/healthcheck/<tier>.status` (key=value:
   result, time, counts, seconds, `stale_after` = twice the tier's period).
2. **The shell greeting** (`engine/host/pazras-aliases.sh`) prints a banner naming each tier
   whose last run was `FAIL`, or older than its `stale_after` (the timer stopped), and prints
   nothing otherwise. The next green run clears it. This replaces reading
   `~/.cache/pazras-status` alone, which `notify@` overwrites (last writer wins) and nothing
   clears; the `⚠ PAZRAS: FAIL` banner for a crashed unit is unchanged.
3. **The phone**: one `familiar relay notify` when a tier turns from not-red to red. A standing
   red is the banner's job, so it does not repeat.
4. **`notify@`** still fires if the script itself exits non-zero (`OnFailure=`), as before.

### The extension point for performance evaluations

A measurement that passes or fails against a budget is a `Check` whose command exits 0 inside
the budget and prints the metric; give it a tier and `effects`, and `--json-out` already records
its seconds. Nothing else needs to change. `feat/perf-evals` owns the content;
`checks selftest --hook-cost` is excluded from the coverage test for that reason.

### What "covered" means, and the test that keeps it true

`engine/checks/check_coverage.py` reads the route table in `engine/familiar` and lists every
verb with a check mode: a `--check`, `--gate` or `--validate` flag in its `Spec` or its
argparse declarations, and the flagless verbs declared in `VERB_MODES` (`posture`, `ontology
check`, `jev check`). `tests/test_coverage.py` fails when one has neither a registry entry nor a
reason in `NOT_REGISTERED`, when a declaration names something that no longer exists, and when
a registry entry runs a verb that is not a route. The measured table, with every cost and the
checks found red when they were first registered, is `dev/checks/2026-10-25-coverage.md`.

### Updates are a check, not a timer that applies them

`familiar checks updates` reads three sources and applies nothing: `mise outdated` (pi and the
harness CLIs), `npm outdated` in pi's package directory (the extensions), and `git ls-remote`
against the pin of each linked skill upstream. Each finding prints the command that applies it
and the checks to run afterwards. A harness upgrade is re-verified by `context route|loadout` and
`orchestration models`; a skill upstream pull changes the bytes, which `skills scan --check`
reports as digest drift, so the re-audit is triggered by the pull and not done unattended. The
same line the leaf draws for pacman: whether to upgrade a binary that a running session depends
on is a judgement an unattended run does not get to make.

### Why a deleted file's name trips no gate — by design, not by omission

`familiar context links --check` gates only on **fixable** broken pointers and
orphaned leaves. Bare names (`config.yaml`, `bootstrap.sh`, and `MEMORY.md` when
it was deleted) are reported as informational and **exit 0** — reporting all of
them would bury the six that matter. That is the right design and it should not
be "fixed".

The gap it leaves is real, and it is not the linker's to close: **a name that no
longer exists is invisible to every gate**, so the only defence is that nothing
may *depend* on such a name. `pazras.py` §`ALWAYS_LOADED` learned this the hard
way (a budget check stayed green for a day while measuring files that had
moved), and asserts each declared name is present.

That lesson now holds for every declared-path list in the codebase, in one owner
— `engine/checks/declared_paths.py`, gated on pre-commit and healthcheck. It
discovers the lists by AST rather than enumerating them (a hand-written registry
has the same defect as the lists it guards: a new one is added and nobody
notices) and requires of every entry either that it exists or that it is declared
deliberately absent **with a reason**. Three names are excused, each with the
decision that produced it. It also checks the reverse direction, which is the
dangerous one: a tombstone that has come back means something is reachable again
that a deny-list says cannot be, and a stale reason would otherwise keep the gate
green.

The linker side is covered too, but only where it is honest to do it. The files
that *describe this repository's own mechanisms* — this one, `../../../README.md`,
and the always-on leaves `[[context-budget]]`, `[[memory-architecture]]`,
`[[memory-mechanisms]]`, `[[consolidation-cycle]]` — take a stricter rule for
**paths**: a path there is a
claim a reader is meant to follow to the implementing code, so failing to resolve
gates. It is scoped to paths rather than bare names, and that was measured: a
bare-name rule flags thirteen places in those files, of which nine are lines that
*record* a removal and three are prose about a kind of file. Everywhere else a
path fragment is ordinary prose that may name another repository, and gating on
it would make `--check` permanently red — the same failure as having no check.

## The scope decision the ROADMAP wording needed narrowing

The ROADMAP cross-cutting item says the health check "does updates, fixes
broken configs or stale links." Read literally, "does updates" could mean
auto-running `pacman -Syu`/`omarchy update` unattended. This build narrows
that deliberately to *reports that updates are available* — auto-applying a
system update is a judgement call (what breaks, when to reboot, whether to
review the changelog first) this process does not get to make on a laptop
with no supervision at 07:00 on a Wednesday. "Fixes broken configs or stale
links" is honoured literally by `--fix`, but scoped to **mechanical and
reversible** repairs only: re-run `bootstrap.sh` (stow `--restow` is
idempotent) and re-run whichever generator a `--check` reported as drifted.
`--fix` never touches git (no commit, no checkout) and never writes into the
dotfiles stow canonical source beyond what `bootstrap.sh`/stow itself already
manages — the same boundary [[scheduled-processes]] describes for
`--apply-dotfiles`.

## Verification

```bash
familiar checks healthcheck --tier daily      # read-only; exit 1 iff a FAIL was found
familiar checks healthcheck --fix             # also applies the mechanical repairs above
systemctl --user status familiar-healthcheck.service
cat "${PAZRAS_DATA_DIR:-$HOME/.local/share/pazras}"/healthcheck/*.status
```
