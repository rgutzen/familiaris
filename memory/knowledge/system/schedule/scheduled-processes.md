---
title: Scheduled processes — the PAZRAS_TIMERS mechanism
summary: Anything unattended — timers, what runs when, what it may write
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-25
verified_log: [2026-10-25, 2026-09-01]
use_count: 8
last_used: 2026-10-20
promoted_from: []           # built 2026-09-01, ROADMAP.md cross-cutting item
source:
supersedes:
related: [consolidation-cycle, healthcheck, journal-index, scheduled-sessions]
tags: [systemd, scheduling, timers, generated-artifacts]
scope: ["06_SYSTEM/engine/structure/**", "dotfiles/shared/systemd/**"]
area: [B]
stability: evolving
---

# Scheduled processes — the PAZRAS_TIMERS mechanism

One table, `PAZRAS_TIMERS` in `config/structure/pazras-master-config.sh`, is now
the single source of truth for every calendar-scheduled background process on
this machine. Cadence, jitter, niceness, IO class and failure-notification
wiring for a process are a **config fact**, not something to hand-write once
per unit — CLAUDE.md rule 4 already says this generally ("if a change tempts
you to hardcode ... a frequency into a script, it belongs in the master
config"); this extends that rule to systemd, which previously sat outside it.

## What existed before this (2026-09-01), and why it drifted

Nine `pazras-*.{service,timer}` pairs lived in the dotfiles stow package
(`shared/systemd/.config/systemd/user/`), each hand-written when its process
was added. Auditing them for this change found real, silent drift:

- `RandomizedDelaySec=` present on 4 of 9 timers, absent on the other 5 —
  not a deliberate choice, just five units nobody revisited after adding it.
- `pazras-validate.service` had **no** `Nice=`/`IOSchedulingClass=` at all —
  the one scheduled process able to compete with interactive work for CPU/IO,
  unnoticed because nothing checked for it.
- `bootstrap.sh`'s hardcoded systemd-enable list (`pazras-backup pazras-sync
  pazras-verify pazras-prune pazras-validate pazras-mirror`) was **missing**
  `pazras-memory` and `pazras-reconcile` — both exist
  and were enabled on this machine, just not through bootstrap.sh; someone
  ran `systemctl --user enable --now` by hand and the script was never
  updated. **Fixed 2026-09-02**: `bootstrap.sh` now sources
  `pazras-master-config.sh` and calls `get_timer_units` itself instead of
  carrying a second copy of the list — verified by a full re-run enabling all
  11 units (including the two new ones below) in one pass with no manual
  step. `pazras-healthcheck` checks that this sourcing is still present
  (`grep -q get_timer_units bootstrap.sh`), not per-unit membership, since
  per-unit *enablement* is already checked directly in the scheduled-units
  section (`systemctl --user is-enabled`).

None of this was a bug in any one file. It was nine copy-paste lineages each
stopping being updated at a different point — exactly the failure mode
`pazras-structure-gen.sh` already fixed for `STRUCTURE.md` and the skill
routers fixed for `skills/CONTEXT.md`. Same governing rule, same fix shape.

## The mechanism

1. **`PAZRAS_TIMERS`** (`pazras-master-config.sh`) — one row per unit,
   `key=value;key=value` dialect (see the table's own header comment for the
   full field list: `on_calendar`, `exec`, `desc`, `persistent`,
   `randomized_delay`, `nice`, `ioclass`, `notify`, `after`, `success_exit`,
   `timeout_start`, `extra_path`, `doc`). This is the **human-readable
   per-process config** the ROADMAP cross-cutting item asked for — one line
   to change a process's cadence, not two files to keep in sync by hand.
2. **`engine/schedule/timers-gen.sh`**, wired as `familiar schedule timers` —
   renders every `.timer`/`.service` pair from that table. Governing rule:
   markdown-is-truth's systemd analogue — never hand-edit a rendered unit,
   edit the table and rerun.
3. **Write targets, deliberately staged:**
   - `familiar schedule timers` renders into `config/schedule/` —
     inside `06_SYSTEM`, always safe to write, fully git-tracked.
   - `familiar schedule timers --check` diffs the staged render against what is
     **actually live** in the dotfiles canonical source
     (`~/02_AREAS/B_Tech/dotfiles/shared/systemd/.config/systemd/user/`),
     read-only, exit 3 on drift — the same contract as
     `familiar structure generate --check`.
   - `familiar schedule timers --apply-dotfiles --yes` copies staged → dotfiles.
     **A renamed key leaves a stale pair behind**, because the table is the
     truth and the old files are not in it: `--check` reports it as `STALE` and
     exits 3, and the apply removes any file in that directory still carrying
     the generator's own banner. Hand-maintained units beside them are never
     touched. A removed file does not unload a running unit — systemd keeps a
     failed stub that `list-timers` still shows — so disable the old timer
     first, or `systemctl --user reset-failed <old>.timer` after.
     **A new pair needs a restow before systemd sees it.** `bootstrap.sh`
     stows with `--no-folding`, so `~/.config/systemd/user` holds one symlink
     per file, and `enable` on an unlinked unit fails with "Unit … does not
     exist" (2026-10-25, `familiar-evals`). `bash ~/02_AREAS/B_Tech/dotfiles/bootstrap.sh`
     restows, reloads the manager and runs `enable --now` for every table row;
     the apply names each `NEW` pair and prints that line.
     **The apply copies every staged pair**, so it also ships any other
     session's staged change that has not been applied yet: run `--check` first.
     **This is the one write in the whole mechanism that touches the
     user's own stow package**, and it requires the second `--yes` flag on
     top of `--apply-dotfiles` for exactly that reason: an agent should never
     pass `--yes` on its own initiative (dotfiles edits are a sign-off
     decision, not a mechanical one — the same boundary that already governs
     any other agent edit to that repo); a human running this by hand is not
     gated by that norm and can use it directly.

## Rationale the generated units no longer carry inline

**Stow mechanics** (cross-cutting): `bootstrap.sh`'s `stow_tier` applies
`STOW_ARGS=(--no-folding --ignore='node_modules' --restow)` to every package.
Folding pulls target-side writes back into the dotfiles tree (GTK wrote
`gtk-3.0/{bookmarks,servers}` into the repo; a fresh machine would gain
systemd `timers.target.wants` symlinks); `--no-folding` prevents it, and
`shared/ai/.opencode/node_modules` exists in-tree only because OpenCode wrote
through a folded link. A package name may appear in multiple tiers
(shared/bash, ubuntu/bash, arch/bash, x11/bash → merged by `~/.bashrc`) — that
only works with `--no-folding`. For a **single-package** change, skip
`bootstrap.sh` (restows ALL packages + theme/timers side effects):
`stow -t "$HOME" -d shared bin`. Two traps: (1) `pazras-archive-flush.path` is
deliberately NOT auto-enabled (manual `systemctl --user start` only — an
auto-trigger would move data off still-single-copy `05_ARCHIVES-EXTERNAL`
unreviewed); (2) GNU `sed -i` on a stow symlink replaces the link with a new
regular file and leaves the canonical stale — Omarchy's monitor scaling
rewrites stowed `monitors.lua` exactly this way, so never let in-place tools
edit symlinked configs.

The nine hand-written units each had explanatory comments next to the
settings they justified. The generator's banner (`timers-gen.sh`
header) explains *where to edit*, not *why a value is what it is* — so that
rationale had to move somewhere before the first `--apply-dotfiles`, or it
would have been silently deleted the moment the generated file overwrote the
hand-written one. It lives here now instead of in the unit file:

- **`Environment=PATH=...` on every `.service`.** A systemd unit does not
  inherit an interactive shell's `PATH`. This bit a real backup once: `zstd`
  resolved only inside a miniforge3 environment's `PATH`, so the unit failed
  silently until the explicit `PATH=` was added. `extra_path` (e.g.
  `pazras-memory`'s `%h/.local/share/mise/shims`) prepends onto this same
  baseline for a process whose executable lives somewhere `timers-gen.sh`'s
  default `%h/bin:%h/.local/bin:/usr/local/bin:/usr/bin:/bin` doesn't reach.
- **`SuccessExitStatus=0 3` on `pazras-backup.service`.** restic returns `3`
  for "completed, some files unreadable" — a warning, not a failure. Without
  this, a routine unreadable-file warning would trip `OnFailure=` every time.
  `success_exit` in `PAZRAS_TIMERS` is this field; leave it empty for a
  process where any nonzero exit should actually page you (everything else).
- **`Persistent=true` (the `persistent` field, default `true`).** The
  decisive flag for a laptop that is asleep at the scheduled time: with it,
  systemd runs the job late on next wake; without it (cron's actual default
  behavior), a missed run is simply skipped and nothing says so. Only turn
  this off deliberately, for a process where a skipped run is truly fine.

## What stays out of this mechanism, deliberately

- **`pazras-notify@.service`** — the shared `OnFailure=` handler every
  generated unit points at (`notify=true`, the default). Referenced, never
  generated; it is not itself scheduled.
- **`pazras-archive-flush.{path,service}`** — a *Path* unit
  (`DirectoryNotEmpty=`), not a Timer. "Scheduled" here means calendar-driven;
  a path unit fires on filesystem state and has no `OnCalendar=` to
  normalise. Left hand-maintained, and deliberately **not** enabled by
  default (`bootstrap.sh`'s own comment: a one-way move onto still-single-copy
  storage should be a decision, not a side effect of a script).

## Verification

```bash
familiar schedule timers --check          # 0 = staged render matches dotfiles; 3 = drift
grep -c '=' <(pazras-master-config.sh timers)   # one line per PAZRAS_TIMERS unit
systemctl --user list-timers | grep familiar
```
