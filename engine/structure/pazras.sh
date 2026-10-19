#!/usr/bin/env bash

# Configurable P.A.Z.R.A.S Management System
# Uses master configuration instead of hardcoded values

# Ensure we're running in bash
if [[ -z "$BASH_VERSION" ]]; then
    echo "Error: This script requires bash, but is running in $0"
    echo "Please run with: bash $0 $@"
    exit 1
fi

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/roots.sh"
# The provider adapters. Sourcing this defines functions and nothing else; the
# selection is `storage.remote` in the profile, resolved inside the backup
# verbs that actually move bytes.
source "$SCRIPT_DIR/../backup/remotes/select.sh"
# Where the typed commands are installed. `familiar` reaches every subject, so
# one symlink into a directory already on PATH for every shell is the whole
# install; `~/.pazras-system` (a symlink to the engine) was the older route and
# is gone as of 2026-10-13.
LOCAL_BIN="$HOME/.local/bin"
# Logs: visible and inspectable, outside the repo. Exempt from the archive
# flush — a backup log you cannot read is a backup you cannot verify. Under
# the PARA root, so a scratch `PARA_ROOT` keeps its logs to itself.
LOG_DIR="$PARA_ROOT/05_ARCHIVES/Logs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# The log directory, and nothing else: every command logs. `~/.local/bin` is
# made by `link` alone, so a scratch run (`PARA_ROOT=/tmp/x … init`) writes
# nothing outside the root it was given.
mkdir -p "$LOG_DIR"

# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

# Load configuration system
load_configuration() {
    local loader_paths=(
        "$SCRIPT_DIR/pazras-config-loader.sh"
    )

    local loader_found=false
    for loader in "${loader_paths[@]}"; do
        if [[ -f "$loader" ]]; then
            if source "$loader" && load_pazras_config; then
                loader_found=true
                log_message "SUCCESS" "CONFIG" "Loaded configuration from: $PAZRAS_CONFIG_FILE"
                break
            fi
        fi
    done

    if [[ "$loader_found" != "true" ]]; then
        echo -e "${RED}❌ Error: Could not load P.A.Z.R.A.S configuration!${NC}" >&2
        echo "Please ensure the configuration files are available:" >&2
        echo "  1. structure/pazras-master-config.sh" >&2
        echo "  2. core/pazras-config-loader.sh" >&2
        echo "" >&2
        echo "Run: familiar structure link, if the commands are not on PATH" >&2
        return 1
    fi
}

# =============================================================================
# LOGGING AND UTILITIES
# =============================================================================

# Logging function
log_message() {
    local level="$1"
    local component="$2"
    local message="$3"
    local logfile="${4:-$LOG_DIR/system.log}"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] [$component] $message" >> "$logfile"
    echo -e "${BLUE}[$component]${NC} $message"
}

# =============================================================================
# SYSTEM LINK MANAGEMENT
# =============================================================================

# Install the typed command. `familiar` handles every subject, so ONE symlink
# into a directory already on PATH for login and non-interactive shells is the
# whole install — no PATH line in the dotfiles, and no second entry point to
# keep in step. The dotfiles carry the same link for a fresh machine
# (`shared/bin/.local/bin/familiar`); this recreates it locally.
link_system() {
    local target="$LOCAL_BIN/familiar"
    local source="$PAZRAS_ENGINE/familiar"

    mkdir -p "$LOCAL_BIN"
    if [[ -L "$target" && "$(readlink -f "$target")" == "$(readlink -f "$source")" ]]; then
        echo -e "${GREEN}✅ $target already links to $source${NC}"
        return 0
    fi

    if [[ -e "$target" && ! -L "$target" ]]; then
        echo -e "${RED}❌ $target exists and is not a symlink — refusing to overwrite${NC}" >&2
        echo "Move it aside first if it holds anything worth keeping." >&2
        return 1
    fi

    ln -sfn "$source" "$target"
    echo -e "${GREEN}✅ Linked $target -> $source${NC}"
}

# =============================================================================
# INITIALIZATION FUNCTIONS
# =============================================================================

# Initialize P.A.Z.R.A.S structure using configuration
init_pazras_structure() {
    log_message "INFO" "INIT" "Initializing P.A.Z.R.A.S structure from configuration"

    # Ensure directory structure exists
    ensure_directory_structure "$PARA_ROOT"

    # Create area README files
    create_area_readmes "$PARA_ROOT"

    # Initialize Zettelkasten templates
    init_zettelkasten_templates

    log_message "SUCCESS" "INIT" "P.A.Z.R.A.S structure initialized successfully"

    # Report, never write: the vault lives in the repository, outside the root.
    if ! seed_skeleton --check >/dev/null; then
        echo "The vault is missing files every session is handed:"
        seed_skeleton --check | sed 's/^/  /'
        echo "Seed them into $PAZRAS_REPO with: familiar structure skeleton"
    fi
}

# Seed the install's vault from engine/structure/skeleton/: the files every
# session is handed (the router and the user's identity, both always loaded)
# that a fresh clone does not have, because the instance's own never travel.
# The skeleton mirrors the repository's layout, so the list is the directory.
#
# Into the REPOSITORY, never the PARA root -- which is why it is not part of
# `init`: `PARA_ROOT=/tmp/x familiar structure init` writes under /tmp/x and
# nowhere else. A file that exists is never overwritten (the vault contract's
# `on_drift: refuse`); `--check` lists what is missing and exits 1 if anything is.
seed_skeleton() {
    local check=0; [[ "${1:-}" == "--check" ]] && check=1
    local skel="$SCRIPT_DIR/skeleton" missing=0 rel
    [[ -d "$skel" ]] || { echo -e "${RED}❌ no skeleton at $skel${NC}" >&2; return 1; }
    while IFS= read -r rel; do
        local dest="$PAZRAS_REPO/$rel"
        [[ -e "$dest" ]] && continue
        missing=$((missing + 1))
        if [[ $check -eq 1 ]]; then
            echo "missing: $rel"
        else
            mkdir -p "$(dirname "$dest")"
            cp "$skel/$rel" "$dest"
            echo -e "${GREEN}seeded: $rel${NC} — yours to edit"
        fi
    done < <(cd "$skel" && find . -type f -printf '%P\n' | sort)
    if [[ $check -eq 1 ]]; then
        [[ $missing -eq 0 ]] && echo "skeleton: every seeded file is present"
        [[ $missing -eq 0 ]]
        return
    fi
    [[ $missing -eq 0 ]] && echo "skeleton: nothing to seed — every file exists"
    return 0
}

# Initialize Zettelkasten templates
init_zettelkasten_templates() {
    local zettel_base="$PARA_ROOT/03_ZETTEL"
    local templates_dir="$zettel_base/04_Templates"

    # Daily note template
    local daily_template="$templates_dir/daily-note-template.md"
    if [[ ! -f "$daily_template" ]]; then
        cat > "$daily_template" << 'EOF'
# {{date}}

## Daily Focus
- [ ]

## Areas Review
{% for area in areas %}
### {{area}}
-

{% endfor %}

## Current Projects
-

## Captures & Ideas
-

## Reflections
-

---
Links: [[{{yesterday}}]] | [[{{tomorrow}}]]
Tags: #daily-note
EOF
        log_message "INFO" "ZETTEL" "Created daily note template"
    fi

    # Permanent note template
    local permanent_template="$templates_dir/permanent-note-template.md"
    if [[ ! -f "$permanent_template" ]]; then
        cat > "$permanent_template" << 'EOF'
# {{title}}

**Area**: {{area}}
**ID**: {{id}}

## Context
<!-- How does this relate to other notes? -->

## Key Ideas
<!-- Main concepts -->

## Sources
<!-- References and links -->

## Connections
<!-- Links to other notes -->

---
Created: {{date}}
Tags: #{{area_tag}} #permanent-note
ID: {{id}}
EOF
        log_message "INFO" "ZETTEL" "Created permanent note template"
    fi

    # Project template
    local project_template="$templates_dir/project-note-template.md"
    if [[ ! -f "$project_template" ]]; then
        cat > "$project_template" << 'EOF'
# {{project_name}}

**Area**: {{area}}
**Status**: Active
**Created**: {{created_date}}
**Deadline**: {{deadline}}

## Objective
<!-- What is the successful outcome? -->

## Key Tasks
- [ ]
- [ ]
- [ ]

## Resources
<!-- Links to relevant resources -->

## Notes
<!-- Project-specific notes -->

## Related Areas
- [[{{area}}]]

---
Tags: #project #{{area_tag}} #active
EOF
        log_message "INFO" "ZETTEL" "Created project template"
    fi
}

# =============================================================================
# BACKUP SYSTEM
# =============================================================================

# Run backup using configuration — restic-based.
#
# Replaces the previous rclone implementation. rclone's off-site backend was
# unofficial and broke; more importantly it offered
# no versioning, so the old code hand-rolled _versions/ directories with
# timestamped copies and manual expiry. restic makes all of that native:
# snapshots ARE the version history, and `forget --prune` is the expiry.
run_pazras_backup() {
    require_config || return 1
    command -v restic >/dev/null || { log_message "ERROR" "BACKUP" "restic not installed"; return 1; }
    [[ -r "$RESTIC_PASSWORD_FILE" ]] || { log_message "ERROR" "BACKUP" "no password file: $RESTIC_PASSWORD_FILE"; return 1; }
    export RESTIC_PASSWORD_FILE

    local today=$(date +%u) day_of_month=$(date +%d)
    local schedule="daily"
    [[ "$today" -eq 7 ]] && schedule="daily weekly"
    [[ "$day_of_month" -eq 1 ]] && schedule="$schedule monthly"
    [[ -n "${1:-}" ]] && schedule="$1"   # allow: familiar backup run weekly

    log_message "INFO" "BACKUP" "restic backup — schedule: $schedule"

    local rc_total=0 done_count=0

    for frequency in $schedule; do
        # ONE SNAPSHOT PER PATH — never grouped.
        #
        # restic selects a parent snapshot by matching path-set + host. Group
        # several paths into one invocation and the set changes whenever
        # BACKUP_CONFIG changes, so the parent is not found and restic re-reads
        # every file. That regression is invisible: storage stays correct
        # (dedup is repo-wide) and only the runtime degrades — until a backup
        # is killed mid-write and leaves orphaned packs behind.
        #
        # A path's own set never changes, so the parent is always found.
        # Snapshots are tiny pointers; having more of them costs nothing.
        for path in "${!BACKUP_CONFIG[@]}"; do
            [[ "${BACKUP_CONFIG[$path]}" == "$frequency" ]] || continue
            # A dot-path (`.claude`) is a harness's home-relative default, not a
            # PARA folder; everything else is under the PARA root.
            local base="$PARA_ROOT"; [[ "$path" == .* ]] && base="$HOME"
            [[ -d "$base/$path" ]] || continue
            local repo="${RESTIC_REPOS[$path]:-}"
            [[ -n "$repo" ]] || { log_message "WARN" "BACKUP" "no repo mapped for $path — skipped"; continue; }

            log_message "INFO" "BACKUP" "[$frequency] $path -> $repo"
            restic -r "$RESTIC_ROOT/$repo" backup "$base/$path" \
                   --exclude-file "$RESTIC_EXCLUDES" \
                   --tag "$frequency" --tag "$path" --compression max \
                   >>"$LOG_DIR/backup.log" 2>&1
            local rc=$?

            # restic exit codes: 0 ok, 3 = completed but some files unreadable.
            # Checking only the final command hides real failures — that is
            # exactly how a broken backup stays invisible.
            case $rc in
                0) log_message "SUCCESS" "BACKUP" "$path"; ((done_count++)) ;;
                3) log_message "WARN" "BACKUP" "$path PARTIAL — unreadable files (rc=3)"
                   [[ $rc_total -eq 0 ]] && rc_total=3 ;;
                *) log_message "ERROR" "BACKUP" "$path FAILED rc=$rc"; rc_total=1 ;;
            esac
        done
    done

    # Retention runs monthly: forget drops snapshot pointers (instant, frees
    # nothing); prune repacks and reclaims space (slow). Separating them is
    # why prune is not run on every backup.
    if [[ "$day_of_month" -eq 1 || "${1:-}" == "prune" ]]; then
        apply_retention
    fi

    log_message "INFO" "BACKUP" "restic backup finished: $done_count ok, rc=$rc_total"
    if [[ $rc_total -ne 0 ]]; then
        command -v notify-send >/dev/null && \
            notify-send -u critical "PAZRAS backup problem (rc=$rc_total)" "see $LOG_DIR/backup.log"
    fi
    return $rc_total
}

# Snapshot retention + space reclamation.
apply_retention() {
    require_config || return 1
    export RESTIC_PASSWORD_FILE
    log_message "INFO" "BACKUP" "applying retention policy"
    local repos=$(printf '%s\n' "${RESTIC_REPOS[@]}" | sort -u)
    for repo in $repos; do
        for tag in "${!RESTIC_RETENTION[@]}"; do
            restic -r "$RESTIC_ROOT/$repo" forget --tag "$tag" --group-by tag,host \
                   ${RESTIC_RETENTION[$tag]} >>"$LOG_DIR/backup.log" 2>&1
        done
        restic -r "$RESTIC_ROOT/$repo" prune >>"$LOG_DIR/backup.log" 2>&1 \
            && log_message "SUCCESS" "BACKUP" "pruned $repo" \
            || log_message "ERROR" "BACKUP" "prune failed: $repo"
    done
}

# Integrity verification. A backup you have not restored is a rumour;
# --read-data-subset re-hashes actual pack data rather than only metadata.
verify_backups() {
    require_config || return 1
    export RESTIC_PASSWORD_FILE
    local subset="${1:-5%}" rc_total=0
    local repos=$(printf '%s\n' "${RESTIC_REPOS[@]}" | sort -u)
    for repo in $repos; do
        log_message "INFO" "VERIFY" "checking $repo (read-data-subset=$subset)"
        if restic -r "$RESTIC_ROOT/$repo" check --read-data-subset="$subset" \
                  >>"$LOG_DIR/backup.log" 2>&1; then
            log_message "SUCCESS" "VERIFY" "$repo intact"
        else
            log_message "ERROR" "VERIFY" "$repo FAILED integrity check"; rc_total=1
        fi
    done
    return $rc_total
}

# Reconcile remote repo copies with the local repo.
#
# THE DANGEROUS ONE. Uploads never delete, so after `prune` the remotes keep
# packs the local repo dropped. Removing them is correct — a mirror should
# match its source — but if the LOCAL repo were damaged, "delete what local
# no longer has" would destroy the good copy.
#
# Four independent safety gates, in order of importance:
#   1. the local repo must pass `restic check` FIRST. Never delete remote data
#      on the authority of a repo you have not verified.
#   2. ORPHAN age, not file age: a pack must have been unreferenced for
#      RECONCILE_MIN_AGE_DAYS across separate runs. A pack wrongly pruned
#      today is not eligible today, whatever its creation date — that window
#      is your chance to notice and restore from the remote.
#   3. a percentage bound: refuse if >RECONCILE_MAX_DELETE_PCT of the remote
#      would go. Wanting to delete most of the mirror means something is wrong.
#   4. dry-run by default; deletion requires --execute.
#
# The REMOTE half of gate 4 is `remote_delete` — the interface's one
# destructive call. The local half is `rm`, and it is not gated on an adapter:
# the archive disk is this machine's copy, and a reconcile that did not touch
# it because no provider was configured would report a clean run over a subset
# of what it was asked to reconcile.
reconcile_remote_repos() {
    require_config || return 1
    export RESTIC_PASSWORD_FILE
    local execute=0; [[ "${1:-}" == "--execute" ]] && execute=1
    local today=$(date +%s) rc_total=0
    mkdir -p "$RECONCILE_STATE"

    # One load for the whole run, and none of it fatal: an install with no
    # provider reconciles the archive disk alone, which is the half it can
    # always reach.
    local rname="" rbase=""
    if remote_prepare 2>>"$LOG_DIR/backup.log"; then
        rname="$REMOTE_NAME"; rbase="$REMOTE_ROOT"
    else
        # WARN, not INFO. The archive disk half still runs, so the exit code is
        # 0 either way — and a green run that quietly stopped updating the
        # off-site copy is the failure this whole file is written against.
        log_message "WARN" "RECONCILE" "no usable remote adapter ('$(remote_selected)') — the OFF-SITE copy was not reconciled; see $PAZRAS_ENGINE_REL/backup/remotes/README.md"
    fi

    local repos=$(printf '%s\n' "${RESTIC_REPOS[@]}" | sort -u)
    for repo in $repos; do
        local local_repo="$RESTIC_ROOT/$repo"
        [[ -d "$local_repo" ]] || continue

        # ── gate 1: verify the local repo before trusting it ──────────────
        if ! restic -r "$local_repo" check >>"$LOG_DIR/backup.log" 2>&1; then
            log_message "ERROR" "RECONCILE" "$repo: local repo FAILED check — refusing to touch remotes"
            rc_total=1; continue
        fi

        local lst="$RECONCILE_STATE/$repo.orphans"
        touch "$lst"

        # The archive disk is a filesystem, so the set difference is cheap, and
        # it is the copy whose orphans this loop measures. The off-site copy is
        # reconciled from the same orphan list, but only once the disk agrees.
        local bf="$ARCHIVE_MOUNT/_Backups/restic/$repo"
        [[ -d "$bf" ]] || { log_message "INFO" "RECONCILE" "$repo: archive copy absent — skipped"; continue; }

        local cur_orphans=$(comm -13 \
            <(cd "$local_repo" && find . -type f | sort) \
            <(cd "$bf"        && find . -type f | sort))
        local remote_total=$(cd "$bf" && find . -type f | wc -l)
        local n_orphan=$(printf '%s' "$cur_orphans" | grep -c . || true)

        if [[ "$n_orphan" -eq 0 ]]; then
            : > "$lst"; log_message "SUCCESS" "RECONCILE" "$repo: remote matches local"; continue
        fi

        # ── gate 2: orphan age, tracked across runs ───────────────────────
        local -A seen=()
        while IFS='|' read -r f ts; do [[ -n "$f" ]] && seen["$f"]="$ts"; done < "$lst"
        local eligible=() newstate=""
        while IFS= read -r f; do
            [[ -n "$f" ]] || continue
            local first="${seen[$f]:-$today}"
            newstate+="$f|$first"$'\n'
            local age_d=$(( (today - first) / 86400 ))
            (( age_d >= RECONCILE_MIN_AGE_DAYS )) && eligible+=("$f")
        done <<< "$cur_orphans"
        printf '%s' "$newstate" > "$lst"

        local n_elig=${#eligible[@]}
        log_message "INFO" "RECONCILE" "$repo: $n_orphan orphaned, $n_elig past ${RECONCILE_MIN_AGE_DAYS}d"
        [[ "$n_elig" -eq 0 ]] && continue

        # ── gate 3: percentage bound ──────────────────────────────────────
        local pct=$(( n_elig * 100 / (remote_total > 0 ? remote_total : 1) ))
        if (( pct > RECONCILE_MAX_DELETE_PCT )); then
            log_message "ERROR" "RECONCILE" "$repo: would delete $pct% (>${RECONCILE_MAX_DELETE_PCT}%) — REFUSING, investigate"
            rc_total=1; continue
        fi

        # ── gate 4: dry-run unless --execute ──────────────────────────────
        if [[ "$execute" -eq 0 ]]; then
            log_message "INFO" "RECONCILE" "$repo: DRY RUN — $n_elig files ($pct%) would be removed; --execute to apply"
            printf '  %s\n' "${eligible[@]:0:5}" | sed 's|^|      |'
            continue
        fi

        # The destructive half. The local copy always goes — the archive disk is
        # this machine's — and the remote copy goes through the adapter, which
        # is the only place in the engine that knows a provider exists.
        for f in "${eligible[@]}"; do
            rm -f "$bf/${f#./}"
            if [[ -n "$rbase" ]]; then
                remote_delete "$rbase/_Backups/restic/$repo/${f#./}" >>"$LOG_DIR/backup.log" 2>&1
            fi
        done
        log_message "SUCCESS" "RECONCILE" "$repo: removed $n_elig stale files ($pct%) from $rname"
        : > "$lst"
    done
    return $rc_total
}

# Copy repo deltas off-machine. restic pack files are immutable, so "upload
# what is missing" is sufficient — no sync semantics needed, and the adapter's
# `-f skip` makes a re-run cost a listing.
#
# TWO DESTINATIONS, and they are not the same kind of thing. The archive disk is
# a mount point from the profile: a local copy, no adapter, and skipped when the
# disk is not attached. The off-site half goes through `storage.remote`'s
# adapter and reports itself skipped when that adapter is unusable — the two
# halves fail independently, because a detached disk must not stop the upload
# and a missing provider must not stop the local copy.
RESTIC_SUBDIRS=(config keys data index snapshots)

sync_repos_offsite() {
    require_config || return 1
    local rc_total=0
    local rname="" rbase=""
    if remote_prepare 2>>"$LOG_DIR/backup.log"; then
        rname="$REMOTE_NAME"; rbase="$REMOTE_ROOT"
    else
        log_message "WARN" "BACKUP" "no usable remote adapter ('$(remote_selected)') — the OFF-SITE copy was NOT updated; see $PAZRAS_ENGINE_REL/backup/remotes/README.md"
    fi
    local repos=$(printf '%s\n' "${RESTIC_REPOS[@]}" | sort -u)
    for repo in $repos; do
        if [[ -n "$rbase" ]]; then
            local ok=0
            for sub in "${RESTIC_SUBDIRS[@]}"; do
                [[ -d "$RESTIC_ROOT/$repo/$sub" ]] || continue
                remote_upload "$RESTIC_ROOT/$repo/$sub" \
                              "$rbase/_Backups/restic/$repo" >>"$LOG_DIR/backup.log" 2>&1 || ok=1
            done
            if [[ $ok -eq 0 ]]; then
                log_message "SUCCESS" "BACKUP" "$repo -> $rname"
            else
                log_message "ERROR" "BACKUP" "$repo -> $rname FAILED (client rc; see backup.log)"
                rc_total=1
            fi
        fi
        local bf="$ARCHIVE_MOUNT/_Backups/restic/$repo"
        if mountpoint -q "$ARCHIVE_MOUNT" 2>/dev/null || [[ -d "$ARCHIVE_MOUNT/_Backups" ]]; then
            rsync -rt --no-perms --no-owner --no-group "$RESTIC_ROOT/$repo/" "$bf/" \
              >>"$LOG_DIR/backup.log" 2>&1 \
              && log_message "SUCCESS" "BACKUP" "$repo -> the archive disk" \
              || { log_message "ERROR" "BACKUP" "$repo -> the archive disk FAILED"; rc_total=1; }
        fi
    done
    return $rc_total
}

# =============================================================================
# PROJECT MANAGEMENT
# =============================================================================

# Project lifecycle management using configuration
manage_project() {
    require_config || return 1

    local action="$1"
    local project_name="$2"
    local area="${3:-}"

    case "$action" in
        "create")
            if [[ -z "$project_name" ]] || [[ -z "$area" ]]; then
                echo "Usage: $0 project create <project_name> <area>"
                echo "Available areas: $(get_areas | tr '\n' ' ')"
                return 1
            fi

            if ! is_valid_area "$area"; then
                echo "❌ Invalid area: $area"
                echo "Available areas: $(get_areas | tr '\n' ' ')"
                return 1
            fi

            local project_dir="$PARA_ROOT/01_PROJECTS/$project_name"
            if [[ -d "$project_dir" ]]; then
                log_message "ERROR" "PROJECT" "Project already exists: $project_name"
                return 1
            fi

            mkdir -p "$project_dir"

            # Use configuration to create project README
            local area_code=$(get_area_code "$area")
            local area_desc=$(get_area_description "$area")

            cat > "$project_dir/README.md" << EOF
# $project_name

**Area**: [$area](../02_AREAS/$area/) ($area_code)
**Focus**: $area_desc
**Status**: Active
**Created**: $(date '+%Y-%m-%d')
**Deadline**: <!-- Add deadline -->

## Objective
<!-- What is the successful outcome? -->

## Key Tasks
- [ ]
- [ ]
- [ ]

## Resources
- [[$area_code MOC]] (Area Map of Content)
- Project files: [[$project_name/]]

## Notes
<!-- Project-specific notes -->

## Related Areas
- [[$area]]

---
Tags: #project #$area #active
Area Code: $area_code
EOF

            log_message "SUCCESS" "PROJECT" "Created project: $project_name in area $area"
            echo "✅ Project created at: $project_dir"
            echo "📁 Area: $area ($area_code) - $area_desc"
            ;;

        "complete")
            if [[ -z "$project_name" ]]; then
                echo "Usage: $0 project complete <project_name>"
                return 1
            fi

            local project_dir="$PARA_ROOT/01_PROJECTS/$project_name"
            if [[ ! -d "$project_dir" ]]; then
                log_message "ERROR" "PROJECT" "Project not found: $project_name"
                return 1
            fi

            # Archive the project
            local archive_dir="$PARA_ROOT/05_ARCHIVES/Projects/$(date +%Y)"
            mkdir -p "$archive_dir"

            if mv "$project_dir" "$archive_dir/"; then
                log_message "SUCCESS" "PROJECT" "Archived project: $project_name"

                # Update README to mark as completed
                local readme="$archive_dir/$project_name/README.md"
                if [[ -f "$readme" ]]; then
                    sed -i "s/Status**: Active/Status**: Completed/" "$readme"
                    echo "**Completed**: $(date '+%Y-%m-%d')" >> "$readme"
                fi

                echo "✅ Project archived to: $archive_dir/$project_name"
            else
                log_message "ERROR" "PROJECT" "Failed to archive project: $project_name"
                return 1
            fi
            ;;

        "list")
            echo -e "${BLUE}📁 Active Projects${NC}"
            echo "=================="
            if [[ -d "$PARA_ROOT/01_PROJECTS" ]]; then
                find "$PARA_ROOT/01_PROJECTS" -mindepth 1 -maxdepth 1 -type d ! -name '_*' | while read -r project; do
                    local name=$(basename "$project")
                    local readme="$project/README.md"
                    if [[ -f "$readme" ]]; then
                        local area=$(grep "^**Area**:" "$readme" | sed 's/.*\[\(.*\)\].*/\1/')
                        local area_code=$(get_area_code "$area" 2>/dev/null || echo "?")
                        local deadline=$(grep "^**Deadline**:" "$readme" | cut -d' ' -f2-)
                        echo -e "${GREEN}📋 $name${NC}"
                        echo "   Area: $area ($area_code)"
                        [[ "$deadline" != "<!--*" ]] && echo "   Deadline: $deadline"
                        echo ""
                    fi
                done
            fi
            ;;
    esac
}

# =============================================================================
# ZETTELKASTEN UTILITIES
# =============================================================================

# Zettelkasten utilities using configuration
zettel_utils() {
    require_config || return 1

    local action="$1"
    shift

    case "$action" in
        "daily")
            local today=$(date '+%Y-%m-%d')
            local daily_note="$PARA_ROOT/03_ZETTEL/01_Journal/$(date +%Y)/$today.md"
            local template="$PARA_ROOT/03_ZETTEL/04_Templates/daily-note-template.md"

            if [[ ! -f "$daily_note" ]]; then
                mkdir -p "$(dirname "$daily_note")"
                if [[ -f "$template" ]]; then
                    # Simple template substitution
                    sed "s/{{date}}/$today/g" "$template" > "$daily_note"
                    log_message "INFO" "ZETTEL" "Created daily note from template: $today"
                else
                    echo "# $today" > "$daily_note"
                    log_message "INFO" "ZETTEL" "Created basic daily note: $today"
                fi
            fi

            echo "Daily note: $daily_note"
            ;;

        "new")
            local note_id="$1"
            local title="$2"

            if [[ -z "$note_id" ]] || [[ -z "$title" ]]; then
                echo "Usage: $0 zettel new <note_id> <title>"
                echo "Example: $0 zettel new A.1.2.3 'cortical-wave-dynamics'"
                echo ""
                echo "Available area codes:"
                for area in $(get_areas); do
                    local code=$(get_area_code "$area")
                    echo "  $code: $area"
                done
                return 1
            fi

            # Determine area from ID
            local area_letter=$(echo "$note_id" | cut -d'.' -f1)
            local area_name=""

            for area in $(get_areas); do
                local code=$(get_area_code "$area")
                if [[ "$code" == "$area_letter" ]]; then
                    area_name="$area"
                    break
                fi
            done

            if [[ -z "$area_name" ]]; then
                log_message "ERROR" "ZETTEL" "Unknown area code: $area_letter"
                echo "Available area codes:"
                for area in $(get_areas); do
                    local code=$(get_area_code "$area")
                    echo "  $code: $area"
                done
                return 1
            fi

            local note_file="$PARA_ROOT/03_ZETTEL/02_Permanent-Notes/$area_name/${note_id}_${title}.md"
            mkdir -p "$(dirname "$note_file")"

            # Use configuration data in note
            local area_desc=$(get_area_description "$area_name")

            cat > "$note_file" << EOF
# $title

**Area**: $area_name ($area_letter)
**Focus**: $area_desc
**ID**: $note_id

## Context
<!-- How does this relate to other notes? -->

## Key Ideas
<!-- Main concepts -->

## Sources
<!-- References and links -->

## Connections
<!-- Links to other notes -->

---
Created: $(date '+%Y-%m-%d %H:%M')
Tags: #$area_name #permanent-note
ID: $note_id
EOF

            log_message "SUCCESS" "ZETTEL" "Created note: $note_id - $title"
            echo "✅ Note created: $note_file"
            echo "📁 Area: $area_name ($area_letter) - $area_desc"
            ;;
    esac
}

# =============================================================================
# STATUS AND REPORTING
# =============================================================================

# System status using configuration
show_pazras_status() {
    require_config || return 1

    echo -e "${BLUE}📊 P.A.Z.R.A.S System Status${NC}"
    echo "========================"
    echo "Configuration: $PAZRAS_CONFIG_FILE"
    echo "Profile:       $PAZRAS_PROFILE_FILE"
    echo "PARA root:     $PARA_ROOT"
    echo ""

    # Projects count
    local active_projects=0
    if [[ -d "$PARA_ROOT/01_PROJECTS" ]]; then
        active_projects=$(find "$PARA_ROOT/01_PROJECTS" -mindepth 1 -maxdepth 1 -type d ! -name '_*' | wc -l)
    fi
    echo -e "${GREEN}📁 Active Projects: $active_projects${NC}"

    # Areas overview
    echo -e "${PURPLE}🎯 Areas: $(get_areas | wc -l)${NC}"
    for area in $(get_areas); do
        local code=$(get_area_code "$area")
        local readme="$PARA_ROOT/02_AREAS/$area/_README.md"
        local status="$([ -f "$readme" ] && echo "✅" || echo "⚠️")"
        echo "   $code: $area $status"
    done

    # Zettelkasten stats
    if [[ -d "$PARA_ROOT/03_ZETTEL" ]]; then
        local note_count=$(find "$PARA_ROOT/03_ZETTEL/02_Permanent-Notes" -name "*.md" -type f 2>/dev/null | wc -l)
        local daily_count=$(find "$PARA_ROOT/03_ZETTEL/01_Journal" -name "*.md" -type f 2>/dev/null | wc -l)
        echo -e "${YELLOW}🗒️  Zettelkasten: $note_count permanent notes, $daily_count daily notes${NC}"
    fi

    # Backup configuration
    echo -e "${BLUE}🔄 Backup Configuration:${NC}"
    for freq in daily weekly monthly; do
        local count=$(get_backup_schedule "$freq" | wc -l)
        echo "   $freq: $count paths"
    done

    # Storage usage
    echo -e "${BLUE}💾 Storage Usage:${NC}"
    for dir in $(get_pazras_dirs); do
        if [[ -d "$PARA_ROOT/$dir" ]]; then
            local size=$(du -sh "$PARA_ROOT/$dir" 2>/dev/null | cut -f1)
            echo "   $dir: $size"
        fi
    done

    # Last backup
    if [[ -f "$LOG_DIR/backup.log" ]]; then
        echo -e "${GREEN}📅 Last Backup:${NC}"
        tail -1 "$LOG_DIR/backup.log" | grep "SUCCESS" | tail -1 || echo "   No recent successful backup"
    fi
}

# =============================================================================
# MAIN COMMAND HANDLER
# =============================================================================

case "$1" in
    "link")
        link_system
        ;;
    "init")
        load_configuration && init_pazras_structure
        ;;
    "skeleton")
        seed_skeleton "${2:-}"
        ;;
    "structure")
        # Regenerate STRUCTURE.md's derived blocks from the master config.
        # The tables there used to be hand-copied and drifted; they are now
        # generated artifacts. --check exits 3 on drift, for a pre-commit hook.
        shift
        exec "$SCRIPT_DIR/pazras-structure-gen.sh" "$@"
        ;;
    "maps")
        # The architecture figures in docs/reference/maps.md, regenerated from
        # the registers they depict (import order, subjects.yaml, the boundary
        # compiler, PAZRAS_TIMERS, the pass's stages), and the hand-written
        # figures' `%% path:`/`%% para:` declarations checked. --check exits 3
        # on drift, for a pre-commit hook.
        shift
        exec python3 "$PAZRAS_ENGINE/structure/maps.py" "$@"
        ;;
    "timers")
        # Render every calendar-scheduled systemd unit pair (PAZRAS_TIMERS in
        # the master config) into config/schedule/. --check diffs
        # against the live dotfiles source without writing; --apply-dotfiles
        # --yes writes them there (human sign-off — see the script header).
        shift
        exec "$PAZRAS_ENGINE/schedule/timers-gen.sh" "$@"
        ;;
    "healthcheck")
        # System health check: stow-link integrity, derived-file drift across
        # every generator (structure/boundaries/skills/timers), scheduled-unit
        # results (a green timer means it FIRED, not that the service
        # succeeded), mount and disk-space checks. Read-only by default;
        # --fix applies only mechanical, reversible repairs (restow, rerun a
        # generator) — never a package update or a git operation.
        shift
        exec "$PAZRAS_ENGINE/checks/healthcheck.sh" "$@"
        ;;
    "backup")
        # familiar backup run            → today's scheduled frequencies
        # familiar backup run daily      → force one frequency
        # familiar backup verify     → integrity check (restic check)
        # familiar backup prune      → retention + space reclamation
        # familiar backup sync       → push repo deltas to the remote and the archive disk
        case "${2:-}" in
            verify) load_configuration && verify_backups "${3:-5%}" ;;
            prune)  load_configuration && apply_retention ;;
            sync)   load_configuration && sync_repos_offsite ;;
            # reconcile: remove remote packs the local repo dropped at prune.
            # Dry-run by default — deletion of backup data is never implicit.
            reconcile) load_configuration && reconcile_remote_repos "${3:-}" ;;
            *)      load_configuration && run_pazras_backup "${2:-}" ;;
        esac
        ;;
    "project")
        load_configuration && manage_project "$2" "$3" "$4"
        ;;
    "zettel")
        load_configuration && zettel_utils "$2" "$3" "$4"
        ;;
    "status")
        load_configuration && show_pazras_status
        ;;
    "config")
        load_configuration
        echo "Configuration file: $PAZRAS_CONFIG_FILE"
        echo "Edit with: \$EDITOR $PAZRAS_CONFIG_FILE"
        ;;
    "validate")
        # The profile first: with a profile that did not parse, AREAS is empty
        # and the master config's duplicate-code check passes on nothing.
        load_configuration && python3 "$PAZRAS_ENGINE/lib/profile.py" --check \
            && validate_config
        ;;
    *)
        echo -e "${BLUE}🚀 Configurable P.A.Z.R.A.S System Manager${NC}"
        echo "======================================"
        echo ""
        echo "Usage: $0 <command> [arguments]"
        echo ""
        echo "Setup Commands:"
        echo "  link                      - install \`familiar\` into ~/.local/bin"
        echo "  init                      - Initialize P.A.Z.R.A.S structure under \$PARA_ROOT"
        echo "  skeleton [--check]        - Seed the vault's missing always-loaded files"
        echo "  validate                  - Validate configuration"
        echo "  structure [--check]       - Regenerate STRUCTURE.md from the config"
        echo "  timers [--check]          - Regenerate scheduled-process systemd units"
        echo "  healthcheck [--fix]       - Stow links, derived-file drift, timer results, mounts"
        echo ""
        echo "Daily Commands:"
        echo "  backup                    - Run configuration-driven backup"
        echo "  project <action> [args]   - Manage projects"
        echo "    create <name> <area>    - Create new project"
        echo "    complete <name>         - Archive completed project"
        echo "    list                    - List active projects"
        echo "  zettel <action> [args]    - Zettelkasten utilities"
        echo "    daily                   - Create/open daily note"
        echo "    new <id> <title>        - Create new permanent note"
        echo "  status                    - Show system status"
        echo "  config                    - Show configuration info"
        echo ""
        echo "Examples:"
        echo "  $0 link                               # First-time / repair setup"
        echo "  $0 init                               # Initialize structure"
        echo "  $0 project create 2024-Q4_Paper A_Science  # New project"
        echo "  $0 zettel new A.1.2.3 brain-dynamics  # New note"
        echo "  $0 backup                             # Run backup"
        echo ""
        echo "The system uses configuration files to define structure."
        echo "All areas, directories, and backup schedules are configurable."
        echo ""
        echo "'para-system' remains a working alias for this command."
        ;;
esac
