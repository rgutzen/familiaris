# The provider seam

Everything this system sends off the machine goes through one of these files.
The engine ships the **contract**; an install ships the **adapter**.

```
remotes/
  README.md      this
  select.sh      loads the selected adapter, refuses an incomplete one
  example.sh     the template — a working adapter that reaches nothing
  <name>.sh      yours: copy the template, replace the client
```

Select one in `config/profile.yaml`:

```yaml
storage:
  restic_root: ~/.local/share/restic
  restic_password_file: ~/.config/restic/password
  archive_mount: ~/05_ARCHIVES-EXTERNAL
  remote: example
```

## Why the seam exists

`familiar backup sync`, `familiar backup reconcile`, and the weekly mirror all
move bytes somewhere that is not this machine, and every provider's client
disagrees about how. Before this split those calls sat inline in
`engine/structure/pazras.sh` and `engine/backup/mirror.sh`, which made the
engine the place a provider is named — the one disclosure in the tree that is
an *arrangement* rather than a fact about the system. Now the engine names a
contract, the profile names an adapter, and the adapter is the only file that
knows which company is on the other end.

**The archive disk is not a remote.** `storage.archive_mount` is a mount point:
a local copy, made with `rsync`, no client, no credentials, and skipped when the
disk is not attached. Only the off-site half is a provider. The two halves fail
independently, on purpose — a detached disk must not stop the upload, and a
misconfigured provider must not stop the local copy.

## The contract

Five shell functions. `select.sh` sources the selected adapter and checks all
five are defined before any bytes move, so an incomplete adapter fails on the
first `backup sync` rather than at 04:30 in a timer nobody reads.

| function | what it must do |
|---|---|
| `remote_name` | print one word. It goes into log lines and unit descriptions. |
| `remote_root` | print the base remote path everything else is joined to. |
| `remote_available` | exit 0 if the client is usable **here**. Print why not. |
| `remote_upload LOCAL DIR` | upload `LOCAL` into the remote folder `DIR`, keeping its name |
| `remote_delete PATH` | remove one remote path |

`remote_upload`'s meaning, exactly, because a mirror is only useful if re-running
it is safe:

- `LOCAL` is a file or a directory; it keeps its name inside `DIR`.
- merge into an existing folder, **skip** a file that is already there.
- **never delete.** Uploads are monotonic, which is what makes `backup sync` a
  command you can run twice with no thought. Reconciliation is the separate,
  gated operation that removes what a local `prune` dropped.

`remote_delete` is the only destructive call in the interface, and it has one
caller: `backup reconcile`. That command reaches it having verified the local
repo with `restic check` and after the orphan has aged `RECONCILE_MIN_AGE_DAYS`
across separate runs, refused if the deletion would exceed
`RECONCILE_MAX_DELETE_PCT`. An adapter whose delete moves to a trash folder
rather than unlinking is a better adapter.

## Writing one

```console
$ cp engine/backup/remotes/example.sh engine/backup/remotes/mine.sh
$ $EDITOR engine/backup/remotes/mine.sh
$ $EDITOR config/profile.yaml          # storage.remote: mine
$ familiar backup sync                 # the log names the adapter it used
```

`select.sh` will not accept a name containing `/`, so the stem is a filename and
nothing else.

Three properties are worth more than the rest, and each has a failure mode that
is invisible from the outside:

1. **`remote_available` must be honest.** A missing client found here is one log
   line. Found per directory it is `0 uploaded, 0 failed`, which reads as
   success — the failure that hides a broken mirror behind a green check.
2. **Rejecting clients need the count.** A client that returns non-zero when 3
   of 31,688 files were refused will report a 99.99% upload as FAILED. Count the
   rejections instead of trusting the exit code — but never report a failure as
   success. `mirror.sh` shows the tolerance it uses.
3. **Non-regular files abort a directory.** Symlinks, FIFOs, sockets and device
   nodes are rejected by most clients, and one of them aborts the whole upload.
   `mirror.sh` strips them and records the symlinks it drops; an adapter that
   adds a path of its own has to do the same.

## When nothing is configured

With no `remote:` — or with the shipped `example` — every caller **skips the
off-site half and says so**: `backup sync` and `backup reconcile` log a warning
that the off-site copy was not updated, and the mirror stages the tree locally
and exits without uploading. The archive disk keeps working. Nothing fails, and
nothing pretends to have happened.

An adapter that is *selected but broken* is a different case and does fail:
`mirror.sh` exits before staging, because a named adapter that cannot run is a
misconfiguration, not an absence.
