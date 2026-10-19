#!/usr/bin/env bash
# mirror.sh — publish the BROWSABLE mirror of local PAZRAS to the remote.
#
#   ./mirror.sh            # stage + upload everything
#   ./mirror.sh --stage    # build the staging tree only, upload nothing
#   ./mirror.sh 02_AREAS   # stage + upload one directory
#
# This is the ACCESS layer, not the recovery layer. Recovery is restic's job
# (see STORAGE-MODEL.md §4). Consequences:
#   * .git and node_modules are excluded — pack files cannot be browsed and the
#     code lives on GitHub.
#   * symlinks are resolved or dropped (see below) — a client that rejects them
#     aborts the whole directory over one bad link, not just the link.
#
# WHO UPLOADS. This driver stages and hands each directory to the adapter named
# by `storage.remote` in the profile (`remotes/`, and `remotes/README.md` for
# the contract). An install with no adapter gets `example`, which reaches
# nothing: the staging run still happens and every upload reports itself
# skipped, so a fresh clone can watch what a mirror would do.
#
# Staging uses HARDLINKS, so a large tree costs ~0 bytes of disk. It lives
# outside the PARA tree — a staging dir inside the tree ingests itself.

set -uo pipefail
HERE="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
source "$HERE/../lib/roots.sh"
source "$HERE/remotes/select.sh"

SRC="$PARA_ROOT"
STAGE="${XDG_CACHE_HOME:-$HOME/.cache}/pazras-mirror"
EXCLUDES="$PAZRAS_MIRROR_EXCLUDES"
# Logs live in 05_ARCHIVES/Logs: a visible folder, easy to inspect, and not
# inside the repo. NOTE: this directory is EXEMPT from the archive flush to the
# external disk (only logs older than a year rotate out). A backup log you
# cannot read because the disk is in a drawer is a backup you cannot verify.
LOGDIR="$PARA_ROOT/05_ARCHIVES/Logs"
DIRS=(00_INBOX 01_PROJECTS 02_AREAS 03_ZETTEL 04_RESOURCES 05_ARCHIVES 06_SYSTEM)

[[ "${1:-}" == "--stage" ]] && { STAGE_ONLY=1; shift; } || STAGE_ONLY=0
[[ $# -gt 0 ]] && DIRS=("$@")

mkdir -p "$LOGDIR"
STAMP=$(date +%F_%H%M)
LOG="$LOGDIR/mirror-$STAMP.log"
MANIFEST="$LOGDIR/mirror-symlinks-$STAMP.txt"
# Files the provider refused — known-absent from the browsable layer, present in
# restic. One file, appended across runs: the point is a list you can act on.
REJECTS="$LOGDIR/mirror-rejected.txt"

log(){ echo "$*" | tee -a "$LOG"; }

log "########## $(date) MIRROR ##########"

# The remote half, loaded before anything is staged: a missing adapter, an
# incomplete one, or a client that is not installed is worth knowing before a
# large tree is walked rather than one log line per directory after it.
ADAPTER="$(remote_selected)"
remote_load || { log "✗ no usable adapter ('$ADAPTER') — see remotes/README.md"; exit 1; }
REMOTE_NAME="$(remote_name)"
REMOTE_OK=0
if [[ "$STAGE_ONLY" == "1" ]]; then
    :                                   # the local half alone; no provider needed
elif remote_available; then
    REMOTE_OK=1
elif [[ "$ADAPTER" == "example" ]]; then
    log "remote: 'example' reaches nothing by design (see remotes/example.sh)"
else
    # Selected and broken is not the same as not configured. Fail loudly, here,
    # where the message is one line — the alternative is 'rc=127' per directory
    # reported as "0 uploaded, 0 failed", which reads as success.
    log "✗ adapter '$ADAPTER' is selected but not usable — install its client or change storage.remote"
    exit 1
fi
[[ "$REMOTE_OK" == "1" ]] && log "remote: $REMOTE_NAME -> $(remote_root)" || log "remote: none — staging only"

log "staging: $STAGE"

# ── 1. stage (hardlinked, filtered) ──────────────────────────────────────
# rsync does NOT create nested parent dirs: without this the whole staging
# step fails silently with empty directories, and the upload then "succeeds"
# at uploading nothing. Worked initially only because the dir existed already.
mkdir -p "$STAGE" || { log "✗ cannot create $STAGE"; exit 1; }

for d in "${DIRS[@]}"; do
    rm -rf "${STAGE:?}/$d"
    extra=()
    [[ "$d" == "01_PROJECTS" ]] && extra=(--exclude=_data/)   # bulk; separate upload
    rsync -a --link-dest="$SRC/$d/" --exclude-from="$EXCLUDES" "${extra[@]}" \
          "$SRC/$d/" "$STAGE/$d/" 2>/dev/null
    # an empty stage means uploading nothing while reporting success
    [[ -d "$STAGE/$d" ]] || { log "✗ staging failed for $d — aborting"; exit 1; }
done

# ── 2. symlinks: record, then resolve or drop ────────────────────────────
# A browser cannot follow them and the client cannot upload them. Three
# classes, three treatments.
{
    echo "# symlinks removed from the mirror — $(date)"
    echo "# the mirror is a flat browsable copy; links are recorded here so the"
    echo "# structure they encoded is not lost."
    for d in "${DIRS[@]}"; do
        find "$STAGE/$d" -type l -printf '%p -> %l\n' 2>/dev/null
    done | sed "s|$STAGE/||"
} > "$MANIFEST"
log "symlinks recorded: $(( $(wc -l < "$MANIFEST") - 3 )) → $(basename "$MANIFEST")"

for d in "${DIRS[@]}"; do
    # a) file symlinks → replace with the real file (small, and makes them browsable)
    while IFS= read -r l; do
        t=$(readlink -f "$l") && [[ -f "$t" ]] && cp --remove-destination "$t" "$l"
    done < <(find "$STAGE/$d" -type l -xtype f 2>/dev/null)
    # b) directory symlinks → drop; dereferencing duplicates content already mirrored
    find "$STAGE/$d" -type l -xtype d -delete 2>/dev/null
    # c) broken symlinks → drop; no content, and they abort the upload
    find "$STAGE/$d" -xtype l -delete 2>/dev/null
    # d) FIFOs, sockets, device nodes → drop. Clients reject any non-regular
    #    file; Zotero leaves a named pipe at Papers/Zotero/pipes/. They carry no
    #    content worth mirroring — a FIFO is an IPC endpoint, not data.
    find "$STAGE/$d" \( -type p -o -type s -o -type b -o -type c \) -delete 2>/dev/null
done

remaining=$(for d in "${DIRS[@]}"; do find "$STAGE/$d" -type l 2>/dev/null; done | wc -l)
log "symlinks remaining in staging: $remaining  (must be 0)"
[[ "$remaining" -ne 0 ]] && { log "✗ symlinks survive — aborting"; exit 1; }

for d in "${DIRS[@]}"; do log "  staged $(printf '%-14s' "$d") $(du -sh "$STAGE/$d" 2>/dev/null | cut -f1)"; done
[[ "$STAGE_ONLY" == "1" ]] && { log "--stage only; done"; exit 0; }
[[ "$REMOTE_OK" == "1" ]] || { log "no remote adapter — staged $STAGE, uploaded nothing"; exit 0; }

# ── 3. upload ────────────────────────────────────────────────────────────
# rc is checked per directory: a client returns non-zero for a partial upload,
# and a loop that only reports the last status hides real failures.
rc_total=0
root="$(remote_root)"

for d in "${DIRS[@]}"; do
    log "===== $d ($(du -sh "$STAGE/$d" | cut -f1)) ====="
    out=$(remote_upload "$STAGE/$d" "$root" 2>&1)
    rc=$?
    printf '%s\n' "$out" >> "$LOG"

    # A client returns non-zero if ANY item was rejected, even 3 out of 31,688.
    # Providers refuse some legitimate files: a content sniffer can misidentify
    # plain ASCII (minified .js, some .md) as "application/x-dosexec".
    # Those files are NOT lost — restic has them, and a repo is opaque blobs that
    # no sniffer inspects. Reporting a 99.99% upload as FAILED is the noise that
    # teaches you to ignore alerts, so quantify instead.
    up=$(printf '%s' "$out" | grep -oP 'Uploaded:\s*\K[0-9]+' | head -1); up=${up:-0}
    fail=$(printf '%s' "$out" | grep -oP 'Failed:\s*\K[0-9]+' | head -1); fail=${fail:-0}

    if [[ $rc -eq 0 ]]; then
        log "  ✓ $d ($up uploaded)"
    elif [[ "$fail" -gt 0 && $(( fail * 1000 )) -lt $(( (up + fail) * 10 + 1000 )) ]]; then
        # <1% rejected: record and continue
        log "  ⚠ $d — $up uploaded, $fail rejected by $REMOTE_NAME (recorded, present in restic)"
        { echo "# $(date -Is)  $d"; printf '%s\n' "$out" | grep -E '^\s+- '; } >> "$REJECTS"
    else
        log "  ✗ $d FAILED rc=$rc ($up uploaded, $fail failed)"; rc_total=1
    fi
done

log "########## $(date) DONE rc=$rc_total ##########"
if [[ $rc_total -ne 0 ]]; then
    command -v notify-send >/dev/null && notify-send -u critical "PAZRAS mirror failed" "see $LOG"
fi
exit $rc_total
