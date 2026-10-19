#!/usr/bin/env bash
# archive-flush.sh — move 05_ARCHIVES staging into 05_ARCHIVES-EXTERNAL.
#
# 05_ARCHIVES is a STAGING area, not a destination: archiving never asks
# "is this big enough to go external?" (no size threshold, no per-item
# judgement). Everything archived lands locally; this flush moves it to the
# authoritative tier on the archive disk when the disk appears.
#
# MANUAL as of 2026-08-20. pazras-archive-flush.path still exists and still
# encodes the right trigger ("the disk is attached", not a schedule that would
# mostly fire and fail), but it is deployed disabled. This flush MOVES data
# (rsync --remove-source-files) into 05_ARCHIVES-EXTERNAL, which is single-copy
# until the archives-external restic repo exists on Disk B — so it runs when
# asked, not when a disk is plugged in.
#
#   systemctl --user start pazras-archive-flush.service   # preferred: idle IO, notifies on failure
#   ~/06_SYSTEM/engine/backup/archive-flush.sh           # direct
#
# Re-automate with: systemctl --user enable --now pazras-archive-flush.path
set -uo pipefail
SRC="$HOME/05_ARCHIVES"
# Stable mountpoint for the archive disk's authoritative archive tier. STORAGE-MODEL.md
# §2/§5: the `05_ARCHIVES-EXTERNAL/` prefix owns the archive disk authority, so archive
# paths always read `/home/<user>/05_ARCHIVES-EXTERNAL/…` no matter where the
# disk appears. This is where the disk is mounted before the flush.
DST="$HOME/05_ARCHIVES-EXTERNAL"
LOG="$HOME/05_ARCHIVES/Logs/archive-flush-$(date +%F).log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "########## $(date) archive flush ##########"

# An unmounted mountpoint is indistinguishable from an empty directory, and
# rsync --delete against one would propagate emptiness. Refuse unless real.
if command -v mountpoint >/dev/null; then
    mountpoint -q "$DST" || { echo "✗ $DST not mounted — disk not attached; refusing"; exit 1; }
else
    [[ -d "$DST" ]] || { echo "✗ $DST absent — disk not attached; refusing"; exit 1; }
fi

# ── sanitise names NTFS cannot store ─────────────────────────────────────
# NTFS forbids  < > : " | ? *  and \  and refuses trailing dots/spaces.
# The flush is a MOVE, so the original name disappears anyway — normalising
# here keeps source and archive consistent rather than silently dropping files.
# rsync exits 23 on such names and leaves them behind, so without this the
# staging area never fully drains.
#
# Renames are recorded in the DESTINATION so the mapping travels with the
# data: an archive whose names were changed without a record is a small lie.
MAP="$DST/_RENAMED-FOR-NTFS.tsv"
sanitise_names() {
    local root="$1" n=0
    [[ -d "$root" ]] || return 0
    # -depth: rename deepest first, or renaming a parent invalidates child paths
    while IFS= read -r -d '' p; do
        local dir base new
        dir=$(dirname "$p"); base=$(basename "$p")
        new=$(printf '%s' "$base" | tr '<>:"|?*\\' '_________')
        new="${new%"${new##*[! .]}"}"          # strip trailing dots/spaces
        [[ -z "$new" ]] && new="_unnamed"
        [[ "$new" == "$base" ]] && continue
        # collision guard: never clobber an existing entry
        local target="$dir/$new" i=1
        while [[ -e "$target" ]]; do target="$dir/${new}~$i"; ((i++)); done
        mv -- "$p" "$target" && {
            mkdir -p "$(dirname "$MAP")" 2>/dev/null
            printf '%s\t%s\n' "${p#$SRC/}" "${target#$SRC/}" >> "$MAP"
            ((n++))
        }
    done < <(find "$root" -depth \( -name '*[<>:"|?*\\]*' -o -name '* ' -o -name '*.' \) -print0 2>/dev/null)
    [[ $n -gt 0 ]] && echo "  sanitised $n name(s) in $(basename "$root") -> $MAP"
    return 0
}

rc=0
for cat in Projects Areas Resources; do
    [[ -d "$SRC/$cat" ]] || continue
    [[ -n "$(ls -A "$SRC/$cat" 2>/dev/null)" ]] || { echo "  $cat: empty"; continue; }
    mkdir -p "$DST/$cat"
    sanitise_names "$SRC/$cat"
    echo "  flushing $cat …"
    # --remove-source-files: this is a MOVE. Staging must drain, or "one
    # archive" quietly becomes two places to search.
    # -L dereferences symlinks into real files: NTFS cannot store them, and a
    # link whose target will not exist after archiving is useless anyway.
    rsync -rtL --remove-source-files --no-perms --no-owner --no-group \
          "$SRC/$cat/" "$DST/$cat/" || rc=1
    find "$SRC/$cat" -type d -empty -delete 2>/dev/null
done

# Logs and Records stay local: Logs are exempt from the flush (a backup log
# you cannot read is a backup you cannot verify); Records/machines are needed
# to rebuild a laptop and are kilobytes.
echo "  Logs/ and Records/ intentionally NOT flushed"

# Refresh the offline index — offline storage costs you search, not access.
# Compressed: 811 GB across ~392k files is 59 MB of plain text — over
# GitHub's 100 MB limit uncompressed, and pure churn in any repo. Gitignored;
# search it with zgrep.
find "$DST" -type f -printf '%12s  %TY-%Tm-%Td  %p\n' 2>/dev/null \
     | gzip -c > "$HOME/06_SYSTEM/archive-index.txt.gz" && echo "  index refreshed (gz)"
echo "########## $(date) done rc=$rc ##########"
exit $rc
