# Recover from backup

A backup nobody has restored is a hypothesis. This brings one file back out of a
restic repository, checks it, and only then puts it where the lost file was —
which is the order that keeps a recovery from becoming a second incident.

The restore below was run against a scratch repository. Your own repositories
hold the only copy of what is in them since the last successful run, so the
target of a restore is the first thing to decide and the last thing to write to.

```console
$ export HOME=/tmp/larder/home
$ git clone <repo> $HOME/06_SYSTEM
$ cd $HOME/06_SYSTEM
$ cp config/profile.example.yaml config/profile.yaml
```

Every `restoring` line below is elided at the restoring user and machine, marked
`…@…`; nothing else in these blocks is elided.

## 1 · Which repository holds the path

`RESTIC_REPOS` in `config/structure/pazras-master-config.example.sh` is the source
of truth, and the split follows authority and mount state rather than size:

| PARA path | Repository |
|---|---|
| `03_ZETTEL`, `06_SYSTEM`, `.claude` | `zettel-system` |
| `00_INBOX`, `01_PROJECTS`, `02_AREAS`, `05_ARCHIVES` | `inbox-projects-areas-archives` |
| `04_RESOURCES` | `resources` |

Movement inside a repository is free, because restic stores content-addressed
packs and a moved file is still the same bytes. That is why the boundary is drawn
where it is, and why looking the repository up is a step rather than a guess.

## 2 · Open the repository read-only

`restic` reads the passphrase from `RESTIC_PASSWORD_FILE`, which the orchestrator
exports from the profile's `storage:`:

```console
$ export RESTIC_PASSWORD_FILE=$HOME/.config/restic/password
$ REPO=$HOME/.local/share/restic/zettel-system
$ restic -r $REPO snapshots --tag 03_ZETTEL --json \
    | jq -r '.[] | "\(.short_id)  \(.time[0:19])  \(.tags|join(","))  \(.paths|join(","))"'
69547ed9  2026-10-15T00:07:08  daily,03_ZETTEL  /tmp/larder/home/03_ZETTEL
f88836f4  2026-10-15T00:07:17  daily,03_ZETTEL  /tmp/larder/home/03_ZETTEL
```

The `--json` route is not decoration: the plain listing has a Host column, and a
snapshot's host is the machine it was taken on. The tag is the PARA path, so a
snapshot is found by what it covers rather than by when it ran.

## 3 · Look inside the snapshot

```console
$ P=/tmp/larder/home/03_ZETTEL/scratch-note.md
$ restic -r $REPO ls f88836f4 $P
snapshot f88836f4 of [/tmp/larder/home/03_ZETTEL] at 2026-10-15 00:07:17.5121597 +0200 CEST by …@… filtered by [/tmp/larder/home/03_ZETTEL/scratch-note.md]:
/tmp/larder/home/03_ZETTEL/scratch-note.md
```

The path on the second line is the answer. **`ls` exits 0 whether or not the path
is in the snapshot**, so a shell test on its exit code asks the wrong question:

```console
$ restic -r $REPO ls 2d7ead3a $P
snapshot 2d7ead3a of [/tmp/larder/home/03_ZETTEL] at 2026-10-15 00:09:48.668302789 +0200 CEST by …@… filtered by [/tmp/larder/home/03_ZETTEL/scratch-note.md]:
```

That header is the whole output, which means the newest snapshot in this
repository does not hold the file — it was taken after the loss. `latest` means
the newest snapshot, not the newest snapshot containing what you want.

## 4 · Bring the file out

To a scratch target, never over the live tree:

```console
$ restic -r $REPO restore f88836f4 --target /tmp/larder/restored \
    --include /tmp/larder/home/03_ZETTEL/scratch-note.md
restoring snapshot f88836f4 of [/tmp/larder/home/03_ZETTEL] at 2026-10-15 00:07:17.5121597 +0200 CEST by …@… to /tmp/larder/restored
Summary: Restored 5 / 1 files/dirs (28 B / 28 B) in 0:00

$ find /tmp/larder/restored -type f
/tmp/larder/restored/tmp/larder/home/03_ZETTEL/scratch-note.md
```

`--target` prefixes the *absolute* path, so the chain under the target repeats the
whole path: one file, four directories around it. When the file is what you want
and the chain is not, `dump` writes it to stdout:

```console
$ restic -r $REPO dump f88836f4 $P
the line that would be lost
```

## 5 · Check it before trusting it

```console
$ restic -r $REPO dump f88836f4 $P | cmp - /tmp/larder/restored/tmp/larder/home/03_ZETTEL/scratch-note.md && echo identical
identical

$ restic -r $REPO check --read-data-subset=5%
read 5.0% of packfiles
[0:00] 100.00%  1 / 1 packs
no errors were found
```

`check` hashes metadata; `--read-data-subset` hashes actual pack data, which is
the difference between "the index is consistent" and "the bytes are there". The
weekly timer runs that subset form, because a full check over a large repository
is a long read.

## 6 · Put it back

Only now, and only the file:

```console
$ printf 'a corrupted line\n' > $P
$ restic -r $REPO restore f88836f4 --target / --include $P
restoring snapshot f88836f4 of [/tmp/larder/home/03_ZETTEL] at 2026-10-15 00:07:17.5121597 +0200 CEST by …@… to /
Summary: Restored 5 / 1 files/dirs (28 B / 28 B) in 0:00

$ cat $P
the line that would be lost
```

`--target /` means the file lands at its original absolute path. Two reasons this
is the last step: a restore over the live tree overwrites whatever is there now,
which may be newer than the snapshot, and it is the only step in this recipe that
can lose data.

## When the repository will not open

Two failures look alike and are not:

- **No passphrase.** `restic` reports it and stops. The passphrase is the user's,
  from their password manager; an agent that invents one produces an encrypted
  repository nobody can open. `familiar backup run` checks for the file first and
  names the one it wanted.
- **A repository that opens but fails `check`.** Then the bytes are suspect, and
  the rule is: **do not `prune` or `forget` a repository whose check failed.**
  Retention repacks data and drops packs nothing references any more; on a
  damaged repository that is the step that turns a recoverable state into an
  unrecoverable one. Report it and leave it alone.

## Honest limits

**The exclude list ships as an example, and the install's copy is the one to
edit.** `config/backup/` holds this machine's exclude lists — they name its
provider and its disk — so the export omits them, and a published tree ships
`backup-excludes.example.txt` and `mirror-excludes.example.txt` in their place.
`engine/lib/roots.sh` resolves to the install's file when it exists and to the
example when it does not, so `familiar backup run` has a working list on the day
you clone. The directory is where YOUR exceptions go:

```console
$ cp config/backup/backup-excludes.example.txt config/backup/backup-excludes.txt
$ $EDITOR config/backup/backup-excludes.txt
```

This was a defect until P5 (found here, at D7, 2026-10-15): the orchestrator was
published and the file its default pointed at was not, so every path failed
`rc=1` on a fresh clone with `failed to read patterns from file …`, and the
workaround was to create an empty list by hand. `restic backup --exclude-file`
fails outright on a file it cannot read — there is no "exclude nothing"
fallback — which is why the shipped default is a real list rather than an empty
stub.

**A green timer is not a green backup.** `systemctl --user list-timers` shows
`pazras-backup.timer` scheduled whether or not the service it activates succeeds.
The service is the unit that reports.

**The off-site half is only as good as the adapter.** `familiar backup sync`
uploads through the adapter named by `storage.remote` in the profile. With none
configured — or with the shipped `example`, which reaches nothing — the archive
disk is still synced and the run logs a warning that the **off-site copy was not
updated**. It exits 0, because the local half succeeded: if you rely on the
off-site copy, read the log line, not the exit code. `engine/backup/remotes/README.md`
has the interface and the failure modes worth knowing when you write one.

**What does not travel.** This machine's repository state, its outage and its
disks are in `memory/knowledge/system/backup/`, which the export omits as
operational state; the design half is `STORAGE-MODEL.md`.

## Read next

- [the Larder](../explanation/lore/backup.md) — the re-acquirability rule, the
  three tiers, and why "degraded" is stated rather than glossed
- `STORAGE-MODEL.md` — the repositories, the disks, and the storage rules
