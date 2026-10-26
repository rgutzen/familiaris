---
title: Scheduled sessions — jobs, conditions, the dispatcher and chains
summary: unattended jobs: a dispatcher, budget and user conditions, chains
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-25
verified_log: [2026-10-25, 2026-10-22, 2026-10-21, 2026-10-15]
use_count: 9
last_used: 2026-10-22
promoted_from: []
source: 06_SYSTEM/dev/schedule/SPECS.md
supersedes:
related: [scheduled-processes, orchestrators, orchestration-eval, the-loom, consolidation-cycle, phone-relay]
tags: [systemd, scheduling, sessions, jobs, chains, dispatcher, records]
triggers: [scheduled session, scheduled job, chain, dispatcher, checkpoint, carry-over, hold, lost run, schedule a session, tick, budget condition, user_active, session record, familiar schedule sessions, stalled chain]
scope: ["06_SYSTEM/engine/schedule/**", "06_SYSTEM/config/schedule/**"]
area: [B]
stability: evolving
---

# Scheduled sessions — jobs, conditions, the dispatcher and chains

`familiar schedule sessions` runs **unattended pi sessions as jobs**. One
dispatcher decides every five minutes which job may start. A job starts when it
is due, the Claude budget allows it, the user is not working, and no declared
process collides. Each job keeps an append-only record. A **chain** is a job
whose runs continue each other until its SPECS are done. The reasoning and the
user's decisions are `dev/schedule/PLAN.md`; the checklist with its evidence is
`dev/schedule/SPECS.md`.

```
familiar schedule sessions add | list | show | cancel | run | resume
familiar schedule sessions tick [--dry-run]          the dispatcher (the timer calls it)
familiar schedule sessions conditions [<job>]        each condition's value and why
familiar schedule sessions checkpoint [--item ID]    inside a run, before each item
familiar schedule sessions --check
```

## A job

`add` writes a declaration (`schedule.json`) and a wrapper. **It writes no
systemd unit.** The one `familiar-dispatch.timer` (`*:0/5`, `AccuracySec=1s`)
starts every job.

| field | values | meaning |
|---|---|---|
| `trigger` | `at` (`--at`, `--in`), `every` (`--every 5h`), `ready` (`--ready`) | when it is due. `every` is a period from the last START, so no 24-hour/5-hour step mismatch |
| `chain` | `none`, `until-done` | whether each run continues the last |
| `priority` | an integer, lower first | the order among due jobs |
| `profile` | a name in `config/orchestration/profiles.yaml` | **the account the job bills** (`--profile`; the caller's when unnamed, always written). A record without the field reads as the config default, `private` |
| `start_when` / `stop_when` | condition names | what holds the job back; what ends a run at its next item |

## The account a job bills

The profile is the job's, not the shell's (`dev/schedule` 2a). `add` records it,
`run` resolves the model under it, the child `pi` gets it as its environment, and
the budget probe reads it. `pi` alone does not do this: the `.pi-profile` routing
is a bash FUNCTION that a `systemd-run` job never loads, and `claude-bridge` is
the provider id in every profile, so a wrong account looks exactly like a right
one.

`orchestration.profiles.account_env(profile)` derives what the child needs from
the profile's declaration, and it is an overlay, `None` meaning "unset":

| variable | value | why |
|---|---|---|
| `PI_PROFILE` | the job's profile | the engine reads it back through `active` |
| `CLAUDE_CONFIG_DIR` | the directory of the profile's Claude `login` | pi-claude-bridge reads `process.env.CLAUDE_CONFIG_DIR` |
| `CLAUDE_CONFIG_DIR` | **unset** for the profile whose login is `~/.claude` | pointing it at the primary home makes Claude look for a login that is not there (`pi-profile`, measured) |
| `<KEY>` | **unset** for every `<KEY>_<PROFILE>` the profile declares | a personal key never reaches a company call |

That overlay is turned into a FULL environment by `profiles.with_account`:
`pi_call.env_for(base=…)` REPLACES what it is given rather than merging into it,
so an overlay handed straight to `popen(env=…)` starts `pi` with no `PATH`
(measured 2026-10-22).

The work tree's `.pi-profile` is a CHECK, never a source: `add` refuses a tree
whose marker names another profile, `run` refuses with a `refused` event when the
marker changed since, and `sessions --check` reports the mismatch as `DRIFT`.


A record written by 9a (a unit pair of its own) reads as `trigger: at` or
`every`, `chain: none`. Its unit still fires it, and the dispatcher skips it.

## Conditions — named predicates, composed in configuration

`engine/schedule/conditions.py` evaluates each name to `(holds, reason, until)`.
**Holds means "in the way".** The lists and every threshold live in
`config/schedule/sessions.yaml`.

| condition | holds when | reads |
|---|---|---|
| `budget` | the five-hour or weekly fraction reaches `five_hour_max`/`weekly_max` (both `1.0`) | `omarchy-agent-usage-claude --limits-only --force`, under **the job's own account** (below), cached per profile for 15 s. A failed probe falls back to the last window refusal on record. Only listed providers spend the window |
| `user_active` | a listed harness (`claude`, `pi`, `opencode`, `hermes`) on a terminal, outside any scheduled run, with terminal I/O within `idle_after`, and (with `scope: job_cwd`, the default since 2026-10-21) working in the job's `cwd` or below it | `/proc`, and the tty's atime (input) and mtime (output) |
| `conflict` | a declared process whose trees overlap the job is due within its lead, or holds its lock | today `familiar-memory` at 03:30, `~/06_SYSTEM`, lead 30 m, `consolidation.lock` |
| `slot` | `max_parallel` (1) runs are in flight | the per-job locks |

The defaults: `start_when: budget, user_active, conflict, slot`;
`stop_when: user_active, conflict`. The engine never reads
`~/.claude/.credentials.json`.

## The dispatcher — one tick

`tick` runs four steps, then appends one line to `<data>/sessions/dispatch.jsonl`:

1. **Backstops.** A stop condition with `hard_stop` that is due interrupts its
   run: the `backstop` event first, then SIGINT to the run's process group.
   `user_active` is `none`: the run stops at its next item, however long that
   takes. `conflict` is `due`: the run must be gone by the pass's start.
2. **Due.** The trigger, minus a hold that lies ahead, a run in flight, or a run
   dispatched under 10 min ago that has no event since.
3. **May start.** A holding `start_when` condition defers the job. Its record
   gains `deferred` only when the holding names change.
4. **One start.** The lowest priority, then the oldest. It starts through
   `systemd-run --user --collect` as its own transient service. A child of the
   tick's oneshot service would die when the tick exits.

## Refusals hold the same job

A run the window refused, with the tree untouched, is **held** on the same job: a
`held` event until the refusal's reset time + 1 m. A run that another run's
working-directory lock refused is held too, for the fallback 30 m. The retry cap
counts holds in a row (`retry.max`, 6), and a run the window let through resets
it. A run that half-committed is never repeated blindly. Every lock refusal
writes `refused`.

## Inside a run

- The run sets `FAMILIAR_SESSION_JOB` and `FAMILIAR_SESSION_RUN` for its children.
- **`checkpoint`** evaluates the job's `stop_when`: exit 0 continue, exit 10
  stop. It appends a `checkpoint` event either way, and the standing prompt calls
  it before each item.
- **`cancel` from inside the job's own run ENDS the job.** "Inside" is proven by
  process ancestry: the job lock's pid is among the caller's ancestors. An
  environment variable an agent could set proves nothing. From anywhere else,
  `cancel` refuses a run in flight.
- One run per job and one per working directory (`<data>/sessions/locks/`).

## Chains

`chain: until-done` jobs continue at the next tick after a run.

- **SPECS are the state.** Each run's `started` row carries a snapshot (HEAD,
  ticks, the prompt's `status:`, the handoff's mtime). Its `finished` row
  carries the measured `progress` (ticks gained, commits, handoff written,
  status changed) and the transcript's last assistant text (`report`).
- **The carry-over block** opens the next run's prompt. It holds how the last run
  ended (completed, a stop condition, the window, the timeout, the backstop, a
  crash), its commits, what it left uncommitted, its report and its handoff
  (`<record>/handoff.md`). The handoff is then archived as `handoff-<run>.md`,
  so it is read once.
- **Ends** (`ended`, notified) when no SPECS item is open, or on `status: done`.
- **Pauses** (`paused`, notified) on `status: blocked`, when only `model: user`
  items remain (`blocked`), after `chain.stall_after` (2) runs in a row without
  progress (`stalled`), or after ticking an item marked `review: yes` (`review`).
  `resume <job>` clears a pause, and so does editing the ask's source.

## The record

One directory per job, `$PAZRAS_DATA_DIR/sessions/<slug>/`: `schedule.json`,
`runs.jsonl`, `run-<ts>.log`, `run.sh`, `transcript/`, and for a chain
`handoff.md`. The events: `started`, `finished`, `refused`, `held`,
`retry_refused`, `deferred`, `dispatched`, `checkpoint`, `stop_held`,
`backstop`, `chain`, `paused`, `resumed`, `ended`, `cancelled`, `crashed`,
`notified`, `notify_failed`, `pruned`, and the relay's `ask`/`answer`/`relay_down`.

| state | the record says |
|---|---|
| `pending` / `due` | a one-off before / after its time, nothing started |
| `ready` / `repeating` | a `ready` job not yet run / an `every` job between its runs (after a run too) |
| `running` / `waiting` | started, no finished; `waiting` has an ask open on the phone |
| `held` | a hold lies ahead |
| `paused` | a chain waits for the user (`resume`) |
| `continuing` | a chain between runs: its last run finished, the chain has not ended (only a one-off reads `done`) |
| `done` / `ended` / `cancelled` | finished / ended itself / cancelled by the user |
| `LOST` / `crashed` / `missed` | no finished past the timeout / the runner failed / a 9a unit passed its time |

## Pruning — the retention policy

`familiar schedule sessions prune [--older-than 30d] [--dry-run]` **archives,
never deletes**: a prunable record moves under `<data>/sessions/archive/`
whole (declaration, events, transcripts), and gains a `pruned` event saying why.
A record is prunable when it is closed (`ended` or `cancelled`) or never started
a run, and nothing has happened to it for the window. One whose unit files are
still on disk is kept and named instead — `cancel` owns the unit, prune only
archives. Archived records are out of every command that reads the live store
(`list`, `show`, `check`, `tick`); they stay plain directories on disk, and
moving one back is the whole undo.

`list` hides a closed record after **3 days** and says how many it hid;
`--all` shows them all, and `--older-than` changes the window. Retention is the
longer question — **30 days** (`RETENTION`) — so a record closed five days ago
is out of the list and still on disk, which is the point: the screen shows what
is worth reading, the store keeps what is worth keeping. Until an archive
command grows a cadence, pruning is by hand.
Decided 2026-10-25: no cadence — a timer or healthcheck step would only move
the same bytes unattended, and a hand-run command cannot surprise a chain
mid-way.

## The user hears about it

A `notified` event is written first. Then come `notify-send` on the user bus and
the relay's `notify`, each best effort. The states that notify: `done`,
`blocked`, `stalled`, `review`, `crashed`, and `LOST` (the tick sweeps it, once
per start). The nightly brief has a **Scheduled sessions** section read from the
records.

## Supervision from the phone

Built before the dispatcher, because an unattended run stalls the moment it needs
the user (`dec-34447648`). The channel is **Telegram**, with one-tap buttons and
threads; its missing end-to-end encryption is answered by security layers rather
than by a second messenger (`dec-66697741`).

- **The phone may answer anything an interactive session may answer**, and a
  security layer that costs a tap is the wrong layer. A PIN for some approvals is
  a later upgrade (`dec-64682383`).
- **A relayed ask waits indefinitely.** No timeout approves or denies anything
  (`dec-87356820`); the run's state stays `waiting` until the answer or a stop.
- **An ask carries the command and the rule.** Whether more context belongs in the
  default message is settled by measured use of an on-demand *More* button
  (`dec-59987573`).
- **Coverage:** phase 1 (scheduled runs over pi RPC) and phase 2 (interactive pi
  sessions) now; Claude Code and hermes later (`dec-70900481`).

## Traps measured, to carry

1. **`pi -p` cannot be supervised:** every permission ask fails. A run drives
   `pi --mode rpc`, so each dialog reaches the relay and waits
   (`engine/schedule/rpc.py`). With no relay, a run that asks anything waits
   until a relay answers.
2. **A child of a oneshot service dies with it** (`KillMode=control-group`), so
   the dispatcher starts runs with `systemd-run`.
3. **A terminal left open is not the user working:** a `pi` open for 7 h had a
   silent terminal (2026-10-21). Hence `idle_after`, which reads the tty device.
4. **A child session cannot run `bash -ic`.** The wrapper sources
   `~/.config/bash/local.sh` into the job's environment before `pi` starts.
5. **Dirty trees:** a run refuses only when an uncommitted path is inside its
   declared write scope.
6. **The lock file names its holder** and is opened without truncation; a
   refused attempt once erased the holder's pid.
7. **The probe's cache root belongs to the machine, not the account.**
   `omarchy-agent-usage-claude` reads the account from `CLAUDE_CONFIG_DIR` but
   keeps its state in ONE directory (`$XDG_CACHE_HOME/omarchy/agent-usage`):
   measured 2026-10-22, a Work probe seconds after a personal one returned the
   PERSONAL window while its `tierLabel` said `Team`, and `--cache-seconds 0`
   does not bypass it. Worse, that directory is also the fallback when the usage
   endpoint refuses (429): the Work reading became the personal 91%/90% with
   `usageStatusText` EMPTY, so nothing in the output said the numbers were
   another account's. Hence `--force` (0.8–1.2 s) plus `XDG_CACHE_HOME` per
   profile inside the record's data dir, and an engine cache keyed by profile. A
   probe that still cannot read prints "probe failed" and does not hold.

## Limits, stated

- A session's write scope is a promise, not a fence: the permission system and
  the prompt enforce it; nothing masks the filesystem.
- A run's transcript under `--session-dir` may not reach the capture → journal
  pipeline (unmeasured; `dev/schedule` 1i measures it).
- The dispatcher's precision is five minutes (decision 10).

## Verification

```bash
engine/familiar schedule sessions --check        # records, units and sources agree
engine/familiar schedule sessions tick --dry-run # what the dispatcher would do now
engine/familiar schedule sessions conditions     # each condition, live
python3 -m pytest engine/schedule/tests -q
```
