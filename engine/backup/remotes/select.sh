#!/usr/bin/env bash
# remotes/select.sh — pick the provider adapter this install backs up to.
#
# SOURCE THIS FILE, do not run it. It defines one function, `remote_load`,
# which sources the adapter named by the profile and refuses to go on if the
# adapter does not implement the interface.
#
# WHY A SEAM. `familiar backup sync`, `backup reconcile` and the mirror timer
# all move bytes to somewhere that is not this machine, and the commands that
# do it are provider-specific: one CLI's `upload`, another's `cp`, a mounted
# disk's `rsync`. Before this file those calls sat inline in the orchestrator,
# which made the orchestrator the place a provider is named — and made the
# provider this instance happens to use part of the engine. Now the engine
# names a CONTRACT and the profile names an adapter.
#
# WHAT AN INSTALL DOES. Write `config/backup/remotes/<name>.sh` implementing
# the five functions below (`engine/backup/remotes/example.sh` is the template),
# then in `config/profile.yaml`:
#
#     storage:
#       remote: <name>
#
# Two roots, and the split is the point: the name is looked up in
# `config/backup/remotes/` first and in this directory second. The engine ships
# the contract and a template that reaches nothing; the install keeps the file
# that names a provider, in a directory the classification already omits from
# the published tree. A profile with no `remote:` gets `example`: every caller
# skips it and says so, so a fresh clone's `familiar backup sync` exits 0 having
# done nothing and claimed nothing.
#
# THE ARCHIVE IS NOT A REMOTE. `storage.archive_mount` — the external disk —
# is a filesystem path the orchestrator copies to with `rsync`. That half needs
# no adapter: a mount point is local, it is in the profile, and "which disk" is
# the only question it raises. Only the off-site half is a provider.
#
# shellcheck shell=bash

# The interface, in one place so a typo in an adapter fails here rather than at
# 04:30 in a timer nobody reads.
REMOTE_API=(remote_name remote_available remote_upload remote_delete remote_root)


remote_dir() {
    # The SHIPPED adapters: the template, and this selector. `roots.sh` exports
    # the directory; the fallback is for a script that sourced this file alone.
    printf '%s' "${PAZRAS_REMOTE_DIR:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")}"
}


remote_install_dir() {
    # The INSTALL's adapters, searched first. That is where a file naming a
    # provider belongs: inside `config/`, which the classification omits, so a
    # published tree carries the contract and no arrangement.
    printf '%s' "${PAZRAS_REMOTE_CONFIG_DIR:-}"
}


remote_selected() {
    # The profile's `storage.remote`. `roots.sh` exports it as
    # `PAZRAS_STORAGE_REMOTE` from the ROOTS section, which is the only place
    # both callers can see: `structure/pazras.sh` gets it through the config
    # loader, and `backup/mirror.sh` never loads the master config at all. The
    # fallback is here rather than in the assignment so a script that sourced
    # this file alone still selects the template.
    printf '%s' "${PAZRAS_STORAGE_REMOTE:-example}"
}


remote_path() {
    # The adapter file for the selected name, or empty. The name is a stem, so
    # it may not contain a separator or climb out of either directory: the
    # profile is a file the user edits, and `storage.remote: ../../etc/passwd`
    # must not source anything outside these folders. The INSTALL's directory is
    # searched first, so an install may ship its own `example.sh` and have it
    # win -- which is how you replace the template without moving it.
    local name; name="$(remote_selected)"
    case "$name" in
        */*|.|..|"") return 0 ;;
    esac
    local dir p
    for dir in "$(remote_install_dir)" "$(remote_dir)"; do
        [[ -n "$dir" ]] || continue
        p="$dir/$name.sh"
        [[ -f "$p" ]] && { printf '%s' "$p"; return 0; }
    done
}


remote_load() {
    # Source the selected adapter and prove it implements the interface.
    # Returns non-zero with a message on stderr; callers say so in the log and
    # SKIP the provider step rather than aborting the run — the local archive
    # half is still worth doing.
    local name path
    name="$(remote_selected)"
    path="$(remote_path)"
    if [[ -z "$path" ]]; then
        echo "remote: no adapter '$name' in $(remote_install_dir) or $(remote_dir) — write one, or set storage.remote in the profile" >&2
        return 1
    fi
    # shellcheck source=/dev/null
    source "$path"
    local fn missing=()
    for fn in "${REMOTE_API[@]}"; do
        declare -F "$fn" >/dev/null || missing+=("$fn")
    done
    if (( ${#missing[@]} )); then
        echo "remote: $path does not implement ${missing[*]}" >&2
        return 1
    fi
    return 0
}


# The two globals `remote_prepare` fills in. Empty until it succeeds, so a
# caller never has to ask twice and never reads a stale name from a previous
# attempt.
REMOTE_NAME=""
REMOTE_ROOT=""


# The adapters' own guard. `remote_available` is an authenticated round trip
# (2.5 s for the shipped client), and `backup reconcile` calls `remote_delete`
# once per orphan: probing each time cost ~42 minutes per 1,000 deletions. Once
# `remote_prepare` has proved the client in this run, REMOTE_NAME is set and
# the probe is skipped; an adapter called without it still probes.
remote_ready() {
    [[ -n "$REMOTE_NAME" ]] || remote_available
}


remote_prepare() {
    # Load the adapter and prove the client is usable HERE, in one call: the
    # off-site half of every caller is "skip quietly if this is not set up", and
    # repeating those two checks at each call site is how one of them ends up
    # skipping for the wrong reason. On success REMOTE_NAME and REMOTE_ROOT are
    # set; on failure both stay empty and the reason is on stderr.
    REMOTE_NAME=""; REMOTE_ROOT=""
    remote_load || return 1
    remote_available || return 1
    REMOTE_NAME="$(remote_name)"
    REMOTE_ROOT="$(remote_root)"
    return 0
}
