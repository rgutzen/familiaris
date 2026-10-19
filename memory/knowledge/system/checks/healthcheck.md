---
title: Health check — the third scheduled process
summary: Checking the system is sound; what a `--check` drift report means
origin: authored
authority: agent
trust: trial
last_verified: 2026-09-01
verified_log: [2026-09-01]
use_count: 6
last_used: 2026-10-02
promoted_from: []           # built 2026-09-01, ROADMAP.md cross-cutting item
source:
supersedes:
related: [scheduled-processes, consolidation-cycle]
tags: [systemd, healthcheck, stow, drift]
scope: ["06_SYSTEM/engine/checks/healthcheck.sh"]
area: [B]
stability: evolving
---

# Health check — the third scheduled process

`familiar checks healthcheck`, wired as `pazras-healthcheck.timer` (weekly) in
[[scheduled-processes]]'s `PAZRAS_TIMERS` table. The ROADMAP cross-cutting
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
   `pazras-context {links,tree,l1} --check`, `pazras-memory {skills,knowledge}
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

## Which gate runs what — two runners, and `--list` now says so

Corrected 2026-09-11, because a reader (the author of this correction) concluded
from `checks.py --list` that `context-links` **never runs**. It does. There are
two runners and only one of them is the registry:

| Runner | Fires | Runs |
|---|---|---|
| `engine/checks/pre-commit` → `checks.py --run pre-commit` | every commit | `boundaries-compile`, the pytest suites, `wards`, `pi-emitter`, `memory-invariants`, `declared-paths` |
| `pazras-healthcheck.timer` (Wed 07:00) → `healthcheck.sh` | weekly | that script's own drift checks **directly**, plus `checks.py --run healthcheck` for the unit-test section |
| `checks.py --run manual` | when a human runs it | everything |

`checks.py` is the registry of *what exists*, and `--audit` is the mechanism that
makes it complete: it walks `engine/**` for test files no entry runs, and since
2026-09-11 it also verifies every `owner` claim below by grepping the file that
claim names for the command.

The label was the defect, not the coverage, and it is fixed in the registry
rather than only here: `--list` prints a legend and an **owner column**, so a
`manual` entry now says *who* runs it — `engine/checks/healthcheck.sh` for
the nine drift checks, `nothing (documented only)` for the four that genuinely
have no runner (`pi-guard-node` and `opencode-plugin-node` need node;
`memory-selftest --signals` is a gate a person runs deliberately), and
`this registry` for everything gated on pre-commit or healthcheck. The claim is
checked, so a renamed command cannot leave `--list` asserting a runner that no
longer invokes it.

Two consequences worth knowing:

- `--list` now answers both questions — *is it registered* and *when does it
  fire* — so this table is a summary rather than the only place the second one
  is written down.
- Adding the column found a genuine omission: `healthcheck.sh` has
  always run `familiar knowledge index --check` and the registry did not
  name it at all. A check the shell script runs and the registry does not
  mention is exactly the gap `--audit` exists for, one level up. Added.

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
familiar checks healthcheck            # read-only; exit 1 iff a FAIL was found
familiar checks healthcheck --fix      # also applies the mechanical repairs above
systemctl --user status pazras-healthcheck.service
```
