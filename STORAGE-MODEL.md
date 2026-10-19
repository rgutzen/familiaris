# Storage Model

**The design of where bytes live.** Which copy is authoritative, how data flows
between tiers, and the rules that keep the copies consistent. It names roles —
the working machine, the archive disk, the rotation disk, the off-site store —
never a particular device or provider. An install records its own devices
beside this document, not in it.

> A migration is a *project* that finishes. This document is the *system* that
> remains. When they disagree, this one wins.

---

## 1. Roles

| Role | Filesystem | Holds |
|---|---|---|
| **Working machine** `~/` | any | the working set; active work happens here |
| **Archive disk** | any; NTFS is lossy (below) | the authoritative archive tier, plus restic repo copies |
| **Rotation disk** | ext4 + LUKS | a plain mirror, swapped off-site — the tool-independent layer |
| **Off-site store** | provider | restic repo copies (recovery) and a browsable mirror (access) |
| **Secret store** | password manager | tokens, recovery codes, the restic passphrase |
| **Git host** | — | source code and the configuration repositories |

The profile names the paths an install uses (`config/profile.example.yaml`,
`storage:`): the restic root, the passphrase file, the archive mountpoint.

**Filesystem constraint.** An archive disk formatted NTFS has no POSIX
permissions, symlinks or xattrs, so a plain mirror there is *lossy*. restic repos
are unaffected — the metadata is stored inside the repo. Such a disk therefore
carries repos and the archive tree; the plain mirror goes to the rotation disk.

---

## 2. Authority

**One authority per path. Never two.** The authoritative copy is where you edit;
every other copy is derived and may be overwritten from it.

**Authority is structural, not remembered.** One boundary in the filesystem
decides it — the `05_ARCHIVES-EXTERNAL/` prefix — not a per-directory lookup
table. A rule you can see in the path cannot be forgotten.

```
~/00_INBOX  01_PROJECTS  02_AREAS  03_ZETTEL  04_RESOURCES  06_SYSTEM   ← working-machine authority
~/05_ARCHIVES/                              ← staging only (§5), flushed on attach
~/05_ARCHIVES-EXTERNAL/                     ← mountpoint · archive-disk authority
      ├── Projects/   Areas/   Resources/
```

**Everything under `05_ARCHIVES-EXTERNAL/` is de facto archived.** Content on a
disk you do not carry is inactive whatever it is called — access friction *is*
archival. The tier therefore needs no internal active/archived distinction. Its
subfolders record *provenance* (the PARA category the content came from), not
status, under the same names as the local `05_ARCHIVES/{Projects,Areas,Resources}`:
one archive category, two tiers, identical internal shape.

**Naming.** The `05_` prefix is deliberate. The external tier is **not a new
category; it is the fifth PAZRAS element on other media**. Local `05_ARCHIVES`
(staging) and `05_ARCHIVES-EXTERNAL` (authoritative) are two tiers of one
category, and the shared number says so. It also sorts them adjacently, so the
pair reads together in any listing.

---

## 3. What goes off-site — the re-acquirability test

Off-site storage is the smallest tier, so the deciding question is **not** size:

> **Can I re-acquire this from the internet?**

| Answer | Examples | Copies |
|---|---|---|
| **Yes** | courses, books, papers, software, ISOs, videos | archive disk + rotation disk (2 copies) |
| **No** | personal photos, scans, own outputs, correspondence, notes | + off-site store (3 copies) |

**Apply 3-2-1 per tier, not globally.** Three copies of re-downloadable media
would spend the off-site budget protecting the least valuable thing you own.

---

## 4. Backup layer

### Repositories

restic repos live **outside** the PAZRAS tree (the profile's
`storage.restic_root`), so no repo ever backs itself up. The master config
(`RESTIC_REPOS`) maps each PAZRAS path to a repo.

| Repo | Contents | Authority | Copies live on | Verify |
|---|---|---|---|---|
| `zettel-system` | `03_ZETTEL` `06_SYSTEM` | working machine | off-site · archive disk · rotation disk | **full** `--read-data`, weekly |
| `inbox-projects-areas-archives` | `00_INBOX` `01_PROJECTS`* `02_AREAS` `05_ARCHIVES` | working machine | off-site · archive disk · rotation disk | 5 % sample, monthly |
| `resources` | `04_RESOURCES` | working machine | off-site · archive disk · rotation disk | 5 % sample, quarterly |
| `archives-external` | `05_ARCHIVES-EXTERNAL` | **archive disk** | **off-site · rotation disk only** | 5 % sample, quarterly |

\* excluding `_data/` — bulk, immutable, versioning pointless. Plain copy instead.

The verify column is the design. **Built:** one timer, `familiar backup verify
5%`, monthly over every repo; the per-repo cadence is not.

The example master config defines the first three. The fourth needs a home that
is neither the archive disk nor too small for its source, so an install adds it
when a rotation disk exists — and until then says plainly that its archive tier
is single-copy, rather than creating an empty repo that implies coverage.

> **The `archives-external` repo must never live on the archive disk.** Its
> source is authoritative there; a repo on the same disk puts data and backup in
> one failure domain, and one disk death destroys both. That is the hardware
> form of Rule 2. The other three repos may sit on the archive disk freely:
> their sources are on the working machine, so no failure domain is shared.

**Why four repos.** A repo boundary is the only way to vary `prune` and `check`
cadence; tags cannot, because both operate per repo. Three boundaries sit where
files do not travel. The fourth sits where **authority and mount state** change,
so one `mountpoint -q` check guards all three concepts at once.

**Accepted cost.** Archiving crosses a repo boundary, so moving a project from
`01_PROJECTS` to `05_ARCHIVES-EXTERNAL` **re-stores** its data in the new repo.
The cost is bounded and infrequent — batched at flush time (§5) — and the
authority/mount alignment pays for it. It is a trade, not an oversight.

**One passphrase for all repos,** kept in the secret store **and on paper**.
Losing it makes every snapshot permanently unreadable; there is no recovery
path.

### Off-site layout

```
<off-site root>/
├── 00_INBOX/ 01_PROJECTS/ … 06_SYSTEM/   ← browsable mirror (ACCESS)
├── _Backups/restic/<repo>/               ← restic repos (RECOVERY)
└── _Logs/     backup logs, manifests, verification reports
```

**Recovery and access are different jobs.** restic encrypts filenames and
structure, so nothing in a repo is browsable from a web client or a phone. The
plain mirror exists for "grab that PDF on the train". Neither replaces the
other.

---

## 5. Flows

### Usage

```
capture ─► 00_INBOX ─┬─► 01_PROJECTS ─┐
                     ├─► 02_AREAS     │  complete / go inactive
                     ├─► 03_ZETTEL    │
                     └─► 04_RESOURCES ┘
                                      ▼
                            ~/05_ARCHIVES         ← LOCAL STAGING (small, transient)
                                      │  flush on disk attach
                                      ▼
                05_ARCHIVES-EXTERNAL/{Projects,Areas,Resources}  ← ARCHIVE DISK (authoritative)
```

Movement *within* a repo is **free**: content is addressed by hash, so a move
rewrites tree metadata only. The one boundary that costs data is the flush to
`05_ARCHIVES-EXTERNAL`, which crosses into a different repo (§4).

### Archiving is a two-step operation — and that is the point

`05_ARCHIVES` is a **staging area, not a destination.** Archiving never asks
*"is this big enough to go external?"*; there is no size threshold and no
per-item judgement:

1. **Archive** → `~/05_ARCHIVES/` — always, regardless of size, disk not required
2. **Flush** → `05_ARCHIVES-EXTERNAL/{Projects,Areas,Resources}/` — on each attach, batched

This converts a per-item decision into a periodic one — the same move as
`_UNSORTED_` (Rule 13). It also means archiving works with the disk in a
drawer, which is when you usually want to do it.

**There is exactly one archive.** `~/05_ARCHIVES` should be near-empty between
flushes; if it is not, the flush is overdue. Never search two places for
archived content — search the index (below).

### Backup

```
daily      restic → zettel-system, inbox-projects-areas-archives (by frequency tag)
weekly     restic → 02_AREAS ; rsync mirror → rotation disk
monthly    restic → 04_RESOURCES ; prune ; swap the rotation disk off-site
on attach  flush 05_ARCHIVES → 05_ARCHIVES-EXTERNAL ; restic → archives-external ;
           regenerate the archive index
quarterly  full restore test from the off-site store into a scratch dir
yearly     re-run the software manifest; review the archive index
```

This is the design cadence. What actually runs is the master config's timer
table (`PAZRAS_TIMERS`), staged by `familiar schedule timers`; the rotation-disk
mirror and the restore test have no timer.

### Offline archive mechanics

The archive tier is unmounted most of the time, which has three consequences:

1. **Mount at a stable path.** `05_ARCHIVES-EXTERNAL` is a mountpoint (the
   profile's `storage.archive_mount`), so restic records the same prefix
   wherever the desktop happens to auto-mount the disk. **One** mountpoint to
   guard, not one per leaf.
2. **Guard every operation.** An unmounted mountpoint is indistinguishable from
   an empty directory, and `rsync --delete` or a restic run against it would
   propagate emptiness. `engine/backup/archive-flush.sh` refuses to run on one:
   ```bash
   mountpoint -q "$ARCHIVE_MOUNT" || { echo "not mounted — refusing"; exit 1; }
   ```
3. **A local index.** restic cannot snapshot an unmounted disk, and you cannot
   search one. The flush refreshes a gzipped file listing of the tier, so
   offline storage costs you *access*, not *search*. **Not built:** a staleness
   alarm for the last `archives-external` snapshot.

---

## 6. Rules

### Storage

1. **One authority per path.** Two writable copies with no rule between them is
   how version mixups happen. No merge tool fixes ambiguous authority.
1b. **Make authority structural, not remembered.** It is a visible path prefix
   (`05_ARCHIVES-EXTERNAL/`), never a lookup table. A rule you must recall
   before acting is a rule you will eventually forget — the same reason
   `.gitignore` is a deny-list and repos sit outside backup sets.
2. **Backup destinations live outside backup sources** — in *directories* and
   in *hardware*. A repo on the same disk as its authoritative source is a copy,
   not a backup; the distinction matters only when the disk dies, which is the
   only moment it matters.
3. **Derived copies follow the authority**, never the reverse. Reorganise the
   authoritative side and re-run the sync; never impose a layout back onto the
   source.
4. **`--checksum` across a filesystem boundary.** NTFS and ext4 disagree on
   timestamp resolution and timezones, so rsync's size+mtime heuristic is
   invalid between them — confidently wrong, not merely slow.
5. **`--delete` points away from the authority.** Written the wrong way round
   it destroys the collection. Dry-run first, always.

### Backup

6. **A backup you haven't restored is a rumour.** Verification means restoring
   and diffing, not checking that files arrived.
7. **3-2-1 per tier, not globally.**
8. **Make failure loud.** restic returns **exit code 3** when a backup completes
   but files were unreadable — check every invocation, never just the last.
   `set -e` does *not* catch it. A backup system with no feedback channel decays
   into no backup at all.
9. **Never back up what a manifest can rebuild.** conda envs, `node_modules`,
   caches. Export `environment.yml --from-history`, not the environment.
10. **Uploads never delete.** Files removed locally by `prune` persist on the
    remotes; remotes grow monotonically while the local repo shrinks. Reconcile
    with `familiar backup reconcile` — **dry-run by default**, quarterly timer,
    four gates: the local `restic check` must pass first; a pack must be
    *orphaned* (not merely old) for 30 days; a run refuses if more than 25 % of
    the remote would go; `--execute` is required to delete. Deleting backup
    data on the authority of an unverified local repo is the one mistake that
    destroys the good copy. The same mechanism means a revoked restic key file
    survives remotely until explicitly deleted.

### Organisation

11. **The paradigm is frozen.** PARA + `YYYY-MM_descriptive-name`. While the
    scheme is open to revision, every file becomes a referendum on the whole
    system.
12. **Triage before curating.** Whole directories, ~10 s, four verdicts:
    keep · rename · archive · defer. Curation is per-file and only for what
    earns it.
13. **Deferring is a decision.** `_UNSORTED_YYYY-MM/` is a first-class
    destination, timestamped so it is honest.
14. **Photos sort by date, not topic.** Chronology is the only scheme with zero
    decisions per file. Hand-name only the events worth it.
15. **Deduplicate with hashes, never with eyes.**
16. **Version what you'd hand-write again; skip what the application
    generates.**

### Security

17. **Secrets never enter git.** Deny-list `.gitignore`, untracked
    `~/.config/*/local*` files, scan before every push. Leaking must require
    defeating three mechanisms, not merely forgetting one.
18. **Private keys are generated where they're used**, never copied between
    machines.
19. **Encrypt what leaves the house.** Secrets on an unencrypted portable disk
    are a wallet you can drop. Use `age`, or store them inside a restic repo.
20. **Rotation is not redaction.** Removing a credential from a file does not
    revoke it.

---

## 7. Current state

**Not recorded here.** A status snapshot in a reference document rots silently.
For what is true *right now*, ask the machine rather than a document:

```bash
systemctl --user status pazras-backup.service   # did the last run succeed?
cat ~/.cache/pazras-status                      # last recorded outcome
restic -r "$RESTIC_ROOT/<repo>" snapshots       # what is actually stored
```

**The runbook must be reachable without the backup system.** Keep the install's
own copy of its storage inventory and recovery procedure in a git repository you
can clone before any disk, provider or restic is available; a recovery document
that lives only inside the backup is a circular dependency.
