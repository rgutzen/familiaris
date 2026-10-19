#!/usr/bin/env bash
# remotes/example.sh — the adapter template. Copy it, replace the placeholder,
# select it with `storage.remote:` in `config/profile.yaml`.
#
# THE CONTRACT, in five functions. `remotes/select.sh` loads the adapter a
# profile names and refuses to run if any of these is missing, so an incomplete
# adapter fails on the first `familiar backup sync` rather than at 04:30.
#
#   remote_name                 one word — what the log calls this provider
#   remote_root                 the base path everything else hangs off
#   remote_available            rc 0 if the provider's client is usable HERE
#   remote_upload LOCAL DIR     upload LOCAL into the remote folder DIR
#   remote_delete PATH          remove one remote path
#
# WHAT `remote_upload` MEANS, exactly, because a mirror is only useful if
# re-running it is safe: upload LOCAL (a file or a directory) into the remote
# folder DIR, keeping its name; merge into an existing folder; skip a file that
# is already there; NEVER delete. Uploads are monotonic, and that is what makes
# `backup sync` a command you can run twice. Reconciliation is the separate,
# gated operation that removes what a local `prune` dropped.
#
# WRITING YOURS. Three things are worth more than the rest:
#   1. `remote_available` must be honest. A missing client discovered here is
#      one log line; discovered per directory it is "0 uploaded, 0 failed",
#      which reads as success.
#   2. A client that cannot upload symlinks, FIFOs or sockets will abort a whole
#      directory over one of them. `engine/backup/mirror.sh` strips them before
#      it gets here; a path you add yourself has to do the same.
#   3. Report a partial upload as partial. If the client returns non-zero for a
#      rejected file, count it instead of calling the run a failure — see the
#      tolerance in `mirror.sh` — but never report a failure as success.
#
# `remotes/README.md` is the longer version, and the instance this template
# came from has a second adapter beside it — the same five functions against a
# real provider's client, `omit` from the published tree because which provider
# an install backs up to is that install's arrangement.
#
# shellcheck shell=bash

# 1. What the log calls you. One word: it goes into log lines and unit
#    descriptions, so a sentence here reads as a sentence inside a sentence.
remote_name() { printf '%s' example; }

# 2. The base remote path. Everything the orchestrator uploads is joined to
#    this, so it is where an install points at its own account's root.
remote_root() { printf '%s' "${EXAMPLE_REMOTE_ROOT:-/remote-root}"; }

# 3. Is the client usable here? "Usable", not "installed": a client that is
#    present but not logged in fails every upload, and a check that only looks
#    for the binary turns that into one error line per directory plus a FAILED
#    line per repository. Do the cheapest authenticated read your client has
#    (this one is a single-path `info`, 2.5 s) and say what the fix is.
remote_available() {
    command -v example-cli >/dev/null 2>&1 || {
        echo "example: example-cli not on PATH — install it, or set storage.remote to an adapter that exists" >&2
        return 1
    }
    local out
    out="$(example-cli info "$(remote_root)" 2>&1)" || {
        echo "example: not logged in ($(printf '%s' "$out" | head -1)) — run: example-cli login" >&2
        return 1
    }
    return 0
}

# 4. Upload LOCAL into the remote folder DIR. `-f skip -d merge` is this
#    client's spelling of the contract: skip a conflicting file, merge a
#    folder. Your client says it differently; the contract does not change.
remote_upload() {
    local local_path="$1" remote_dir="$2"
    remote_available || return 1
    example-cli upload --on-conflict skip --merge --no-thumbnails \
                       "$local_path" "$remote_dir"
}

# 5. Remove one remote path. This is the ONLY destructive call in the
#    interface, and the only caller is `backup reconcile`, which reaches it
#    having verified the local repo and aged the orphan first. A client whose
#    delete moves to a trash folder rather than unlinking is a better client.
remote_delete() {
    local remote_path="$1"
    remote_available || return 1
    example-cli delete "$remote_path"
}
