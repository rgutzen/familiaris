---
title: pazras-cli — the folder-tree CLI's own traps
summary: The folder-tree CLI's own traps — bash, config, systemd
origin: authored
authority: agent
trust: trusted
last_verified: 2026-09-01
verified_log: [2026-09-01]
use_count: 1
last_used: 2026-09-11
promoted_from: []
source:
supersedes:
related: [pazras-structure]
tags: [pazras, bash, config, systemd, cli]
scope: ["06_SYSTEM/**"]
area: [B]
stability: stable
---

# pazras-cli — the folder-tree CLI's own traps

Gotchas in the system's own tooling, as opposed to the structure it manages
([[pazras-structure]]) or where it puts bytes (`STORAGE-MODEL.md`).

## A green timer does not mean a successful run

`systemctl --user list-timers` reports that a timer **fired**, not that the
service it activated **succeeded**. `pazras-backup.service` failed every night
from 2026-08-27 to 08-31 while the timer showed green, and nothing surfaced it
for four days.

```bash
systemctl --user status pazras-backup.service   # the real answer
journalctl --user -u pazras-backup.service -n 20
cat ~/.cache/pazras-status                      # last recorded outcome
cat ~/05_ARCHIVES/Logs/pazras-failures.log      # written by OnFailure=
```

Every scheduled unit carries `OnFailure=pazras-notify@%n.service`, so failures
*are* recorded. The gap was never detection — it was that **nothing reads the
record**. Treat any "the timer is green" claim as unverified.

## `load_pazras_config` and `set -u`

**Fixed 2026-08-30; recorded because the pattern recurs.**
`pazras-config-loader.sh` read `$PAZRAS_CONFIG_FILE` and `$PAZRAS_CONFIG_LOADED`
unguarded, so sourcing it from any script with `set -u` aborted on an unset
variable before the config ever loaded. The fix is the `${VAR:-}` form at every
read of an optionally-set variable:

```bash
if [[ -n "${PAZRAS_CONFIG_FILE:-}" ]] && [[ -f "${PAZRAS_CONFIG_FILE:-}" ]]; then
```

The trap is that the loader is *sourced*, so it inherits the caller's shell
options. It cannot assume its own. Any new optional variable in a sourced file
needs the same guard.

```bash
bash -c 'set -u; source ~/06_SYSTEM/engine/structure/pazras-config-loader.sh \
  && load_pazras_config >/dev/null && echo ok'
```

## Structure documentation is generated

`STRUCTURE.md`'s category, Area, Zettel and backup tables are **derived** from
`config/structure/pazras-master-config.sh` by `familiar structure generate`. Never edit
inside the `BEGIN:`/`END:` markers — edit the config and rerun. `--check` exits
3 on drift.

They were hand-maintained until 2026-09-01 and had drifted: the table claimed
`04_RESOURCES` was backed up weekly where the config says monthly. That is the
whole argument for generating them.

## One config, and scripts that never hardcode

Every script resolves structure through `pazras-config-loader.sh`. If a change
tempts you to hardcode an Area code, a path or a frequency into a script, it
belongs in the master config instead. Scripts source the loader from their own
directory, so the version-controlled copy is always the one that runs — there
is no install step that can go stale. `~/.local/bin/familiar` is one symlink
into the engine, for the typed command only.

## Shell alias trap: `pazras-aliases.sh` vs new CLIs

`pazras-aliases.sh:15` defined `alias pi="cd ~/00_INBOX"`, which shadowed the
mise-installed `pi` harness in every interactive shell — aliases beat PATH
lookup, so `pi` ran `cd` and the failure read as "pi doesn't work" rather than
"an alias stole the name" (only `type pi` reveals it). When adopting a new CLI,
grep `pazras-aliases.sh` for a same-name alias first; the harness name wins. The
legacy alias was renamed `pi`→`p0` (user-approved); a running shell keeps the
old alias until it re-sources the rc files.

## Verification

```bash
familiar structure validate            # config parses, no duplicate Area codes
familiar structure generate --check   # 0 = in sync, 3 = drifted
familiar structure status
```
