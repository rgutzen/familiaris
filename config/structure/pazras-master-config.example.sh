#!/usr/bin/env bash

# P.A.Z.R.A.S Master Configuration
# Single source of truth for the entire system structure
#
# P.A.Z.R.A.S = Projects, Areas, Zettelkasten, Resources, Archives, System

# =============================================================================
# CORE SYSTEM STRUCTURE
# =============================================================================

# Top-level P.A.Z.R.A.S directories
declare -gA PAZRAS_STRUCTURE=(
    ["00_INBOX"]="capture:daily:Temporary capture area for new items"
    ["01_PROJECTS"]="action:daily:Active projects with specific outcomes and deadlines"
    ["02_AREAS"]="action:weekly:Ongoing responsibilities and standards to maintain"
    ["03_ZETTEL"]="knowledge:daily:Personal knowledge development and thinking space"
    ["04_RESOURCES"]="reference:weekly:Topics and themes for future reference"
    ["05_ARCHIVES"]="archive:monthly:Inactive items from other categories"
    ["06_SYSTEM"]="system:daily:System configuration and automation"
)

# Areas of responsibility/interest: declared in `config/profile.yaml` (P1),
# which the loader evaluates before this file -- `AREAS` is already set here,
# in this file's old `tag:description:code` field order.

# System directories
declare -gA SYSTEM_DIRS=(
    ["engine"]="engine:Generic code, one folder per subject"
    ["config"]="configuration:The user's decisions (directives) -- one folder per subject"
)

# Subdirectories of `06_SYSTEM` that are LINKS to a separate repository rather
# than folders of their own. RECOMMENDED, NOT ENFORCED: the system runs without
# a dotfiles repository, and nothing reads this path. The link exists so that
# the dotfiles are versioned in their own repo while still reachable from the
# install, and the target is the user's to change -- `02_AREAS/B_Tech` is where
# the example profile's technology Area is.
#
# The system's own backups are NOT a directory here: they are restic
# repositories at the profile's `storage:` paths (`~/.local/share/restic`).
# `06_SYSTEM/backups` was vestigial and is removed (user, 2026-10-14).
declare -gA SYSTEM_LINKS=(
    ["dotfiles"]="../02_AREAS/B_Tech/dotfiles"
)

# =============================================================================
# ZETTELKASTEN STRUCTURE
# =============================================================================

declare -gA ZETTELKASTEN_STRUCTURE=(
    ["00_Inbox"]="capture:Quick captures and unprocessed notes"
    ["01_Journal"]="daily:Date-based daily notes and journals"
    ["02_Permanent-Notes"]="permanent:Main knowledge base organized by areas"
    ["03_Maps-Of-Content"]="structure:Structure notes and topic overviews"
    ["04_Templates"]="templates:Note templates and formatting guides"
    ["_assets"]="media:Images, PDFs, and other media files"
)

# =============================================================================
# BACKUP AND SYNC CONFIGURATION
# =============================================================================

# Backup frequencies: daily, weekly, monthly, manual
declare -gA BACKUP_CONFIG=(
    ["00_INBOX"]="daily"
    ["01_PROJECTS"]="daily"
    ["03_ZETTEL"]="daily"
    ["06_SYSTEM"]="daily"
    ["02_AREAS"]="weekly"
    ["04_RESOURCES"]="monthly"
    ["05_ARCHIVES"]="monthly"
)

# =============================================================================
# RESTIC BACKUP CONFIGURATION
# =============================================================================
# Which restic repository covers which PAZRAS path. Repo boundaries follow
# AUTHORITY and MOUNT state, not size — see STORAGE-MODEL.md §4.
# Movement inside a repo is free (content-addressed); across one it re-stores.
declare -gA RESTIC_REPOS=(
    ["03_ZETTEL"]="zettel-system"
    ["06_SYSTEM"]="zettel-system"
    ["00_INBOX"]="inbox-projects-areas-archives"
    ["01_PROJECTS"]="inbox-projects-areas-archives"
    ["02_AREAS"]="inbox-projects-areas-archives"
    ["05_ARCHIVES"]="inbox-projects-areas-archives"
    ["04_RESOURCES"]="resources"
)

# Repos live OUTSIDE the PAZRAS tree: a repo inside its own backup set
# ingests itself and compounds every run.
# The paths come from the profile's `storage:` (P1); the environment still wins.
RESTIC_ROOT="${RESTIC_ROOT:-$PAZRAS_STORAGE_RESTIC_ROOT}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$PAZRAS_STORAGE_RESTIC_PASSWORD_FILE}"
# The exclude list: the install's own when it has one, the shipped example when
# it does not. `roots.sh` resolves WHICH (see the note there) and the nested
# default keeps this file usable on its own, without the loader.
RESTIC_EXCLUDES="${RESTIC_EXCLUDES:-${PAZRAS_BACKUP_EXCLUDES:-$PAZRAS_INSTALL/config/backup/backup-excludes.txt}}"

# Stable mountpoint for the archive disk. STORAGE-MODEL.md §2/§5:
# mount at ONE path regardless of where the disk appears (udisks auto-mounts at
# /run/media/<user>/<label>, which changes with the username) so every script
# and restic snapshot records the same `/home/<user>/05_ARCHIVES-EXTERNAL/…`
# prefix. The disk root holds the archive tier AND `_Backups/restic/`.
# The path is the profile's `storage.archive_mount` (P1).
ARCHIVE_MOUNT="${ARCHIVE_MOUNT:-$PAZRAS_STORAGE_ARCHIVE_MOUNT}"

# --- remote reconciliation ------------------------------------------------
# Uploads never delete: rsync without --delete and the remote adapter's
# skip-on-conflict upload (see `engine/backup/remotes/`) only ever add, so
# remote copies grow monotonically while the local repo shrinks after prune.
# Reconciliation removes remote packs the local repo no
# longer references — the single most dangerous operation here, since a
# damaged local repo would otherwise instruct us to delete the good copy.
#
# ORPHAN age, not file age. A pack written 6 months ago and wrongly pruned
# today must NOT be immediately eligible; what matters is how long it has
# been *unreferenced*, which gives you time to notice and recover.
RECONCILE_MIN_AGE_DAYS="${RECONCILE_MIN_AGE_DAYS:-30}"
# Refuse if a run would remove more than this share of the remote: a
# reconcile wanting to delete most of the mirror means something is wrong.
RECONCILE_MAX_DELETE_PCT="${RECONCILE_MAX_DELETE_PCT:-25}"
RECONCILE_STATE="${RECONCILE_STATE:-$HOME/.cache/pazras/reconcile}"

# Retention per frequency tag. restic replaces the old hand-rolled
# _versions/ directories: snapshots ARE the version history.
declare -gA RESTIC_RETENTION=(
    ["daily"]="--keep-daily 14 --keep-weekly 8 --keep-monthly 12"
    ["weekly"]="--keep-weekly 12 --keep-monthly 24"
    ["monthly"]="--keep-monthly 36"
)

# =============================================================================
# SCHEDULED PROCESSES
# =============================================================================
# Single source of truth for every calendar-scheduled systemd unit (rule 4:
# "if a change tempts you to hardcode ... a frequency into a script, it
# belongs in the master config"). Before this table, each process's cadence,
# jitter, niceness and failure-notification wiring lived by itself in a
# hand-written pair of dotfiles unit files (`shared/systemd/.config/systemd/
# user/pazras-*.{service,timer}`) — nine near-identical files that drifted:
# some had RandomizedDelaySec, some didn't; `validate.service` had no Nice/
# IOSchedulingClass at all. `familiar schedule timers` (structure/timers-gen.sh)
# renders every unit pair from the one row below — see that script's header
# for what stays hand-maintained (notify@.service, the archive-flush
# .path unit — event-triggered, not calendar-scheduled). Not to be confused
# with BACKUP_CONFIG/RESTIC_RETENTION above ("schedule" there means retention
# tagging per path; this table means systemd calendar cadence per process) —
# `pazras-config-loader.sh schedule` already used that word for the former.
#
# Field dialect: `key=value;key=value`, order-independent. Fields:
#   on_calendar       systemd OnCalendar= expression (required)
#   exec              command, relative to $HOME (required)
#   desc              one-line Description=, used in both .timer and .service
#   persistent        Persistent= (default true — catch up after a laptop
#                      sleeps through the scheduled time, rather than skip)
#   randomized_delay  RandomizedDelaySec= (default 15m; empty string = omit)
#   nice              Nice= (default 15)
#   ioclass           IOSchedulingClass= (default idle)
#   notify            OnFailure=notify@%n.service (default true)
#   after             optional After=<unit>
#   success_exit      optional SuccessExitStatus= (e.g. restic's benign "3")
#   timeout_start     optional TimeoutStartSec=
#   extra_path        optional extra PATH segment prepended before the
#                      standard %h/bin:%h/.local/bin:/usr/local/bin:/usr/bin:/bin
#   doc               optional Documentation=file:%h/<path>
declare -gA PAZRAS_TIMERS=(
    ["pazras-backup"]="on_calendar=*-*-* 00:00:00;exec=06_SYSTEM/engine/familiar backup run;desc=PAZRAS restic backup — all configured paths;nice=10;success_exit=0 3;doc=06_SYSTEM/STORAGE-MODEL.md"
    ["pazras-sync"]="on_calendar=*-*-* 04:30:00;exec=06_SYSTEM/engine/familiar backup sync;desc=Push restic repo deltas to the configured remotes;nice=15;randomized_delay=30m;after=pazras-backup.service"
    ["familiar-memory"]="on_calendar=*-*-* 03:30:00;exec=06_SYSTEM/engine/familiar consolidation run;desc=Agent-memory consolidation — the nightly pass (9 stages);nice=10;extra_path=%h/.local/share/mise/shims;doc=06_SYSTEM/memory/knowledge/system/consolidation/consolidation-cycle.md"
    ["pazras-prune"]="on_calendar=*-*-02 05:00:00;exec=06_SYSTEM/engine/familiar backup prune;desc=PAZRAS restic retention and prune;nice=19;randomized_delay=20m"
    ["pazras-mirror"]="on_calendar=Sat *-*-* 02:00:00;exec=06_SYSTEM/engine/backup/mirror.sh;desc=Publish a browsable PAZRAS mirror to the off-site provider;nice=19;randomized_delay=20m;timeout_start=12h"
    ["pazras-validate"]="on_calendar=Sun *-*-* 09:00:00;exec=06_SYSTEM/engine/familiar structure validate;desc=PAZRAS configuration validation;nice=19;randomized_delay=20m"
    ["pazras-verify"]="on_calendar=*-*-01 05:00:00;exec=06_SYSTEM/engine/familiar backup verify 5%%;desc=PAZRAS restic integrity check;nice=19;randomized_delay=20m"
    ["pazras-reconcile"]="on_calendar=*-01,04,07,10-05 06:00:00;exec=06_SYSTEM/engine/familiar backup reconcile;desc=Reconcile remote restic copies with the local repo (dry-run — apply with backup reconcile --execute);nice=19;randomized_delay=20m"
    ["familiar-journal-index"]="on_calendar=*-*-* 06:15:00;exec=06_SYSTEM/engine/familiar knowledge journal index;desc=Rebuild the local embedding index over journal/ (D4, incremental);nice=15;doc=06_SYSTEM/memory/knowledge/system/knowledge/journal-index.md"
    ["familiar-healthcheck"]="on_calendar=Wed *-*-* 07:00:00;exec=06_SYSTEM/engine/familiar checks healthcheck;desc=System health check — stow links, derived-file drift, timer results, mounts;nice=15;randomized_delay=20m;extra_path=%h/.miniforge3/bin;doc=06_SYSTEM/memory/knowledge/system/checks/healthcheck.md"
)

# =============================================================================
# UTILITY FUNCTIONS FOR CONFIG ACCESS
# =============================================================================

# Get all P.A.Z.R.A.S directories
get_pazras_dirs() {
    if [[ ${#PAZRAS_STRUCTURE[@]} -eq 0 ]]; then
        echo "Error: PAZRAS_STRUCTURE not loaded" >&2
        return 1
    fi
    printf '%s\n' "${!PAZRAS_STRUCTURE[@]}" | sort
}

# Get all areas
get_areas() {
    if [[ ${#AREAS[@]} -eq 0 ]]; then
        echo "Error: AREAS not loaded" >&2
        return 1
    fi
    printf '%s\n' "${!AREAS[@]}" | sort
}

# Get all Zettelkasten directories
get_zettelkasten_dirs() {
    if [[ ${#ZETTELKASTEN_STRUCTURE[@]} -eq 0 ]]; then
        echo "Error: ZETTELKASTEN_STRUCTURE not loaded" >&2
        return 1
    fi
    printf '%s\n' "${!ZETTELKASTEN_STRUCTURE[@]}" | sort
}

# Get area description
get_area_description() {
    local area="$1"
    [[ -z "$area" ]] && return 1

    if [[ -n "${AREAS[$area]:-}" ]]; then
        local desc=$(echo "${AREAS[$area]}" | cut -d':' -f2)
        [[ -n "$desc" ]] && echo "$desc" || echo "No description"
    else
        echo "Area not found"
        return 1
    fi
}

# Get area code (letter)
get_area_code() {
    local area="$1"
    [[ -z "$area" ]] && return 1

    if [[ -n "${AREAS[$area]:-}" ]]; then
        local code=$(echo "${AREAS[$area]}" | cut -d':' -f3)
        [[ -n "$code" ]] && echo "$code" || echo "?"
    else
        echo "?"
        return 1
    fi
}

# Get backup frequency for a path
get_backup_frequency() {
    local path="$1"
    [[ -z "$path" ]] && echo "manual" && return 0

    local freq="${BACKUP_CONFIG[$path]:-manual}"
    [[ -n "$freq" ]] && echo "$freq" || echo "manual"
}

# Get directory type (action, reference, archive, etc.)
get_dir_type() {
    local dir="$1"
    [[ -z "$dir" ]] && return 1

    if [[ -n "${PAZRAS_STRUCTURE[$dir]:-}" ]]; then
        local type=$(echo "${PAZRAS_STRUCTURE[$dir]}" | cut -d':' -f1)
        [[ -n "$type" ]] && echo "$type" || echo "unknown"
    else
        echo "unknown"
        return 1
    fi
}

# Get directory description
get_dir_description() {
    local dir="$1"
    [[ -z "$dir" ]] && return 1

    if [[ -n "${PAZRAS_STRUCTURE[$dir]:-}" ]]; then
        local desc=$(echo "${PAZRAS_STRUCTURE[$dir]}" | cut -d':' -f3)
        [[ -n "$desc" ]] && echo "$desc" || echo "No description"
    else
        echo "Directory not found"
        return 1
    fi
}

# Get all scheduled-process unit basenames
get_timer_units() {
    if [[ ${#PAZRAS_TIMERS[@]} -eq 0 ]]; then
        echo "Error: PAZRAS_TIMERS not loaded" >&2
        return 1
    fi
    printf '%s\n' "${!PAZRAS_TIMERS[@]}" | sort
}

# Get one field of a timer entry: get_timer_field <unit> <field> [default]
get_timer_field() {
    local unit="$1" field="$2" default="${3:-}"
    local row="${PAZRAS_TIMERS[$unit]:-}"
    [[ -z "$row" ]] && { echo "$default"; return 1; }
    local IFS=';' part
    for part in $row; do
        if [[ "$part" == "$field="* ]]; then
            echo "${part#*=}"
            return 0
        fi
    done
    echo "$default"
}

# Validate area code
is_valid_area() {
    local area="$1"
    [[ -n "$area" ]] && [[ -n "${AREAS[$area]:-}" ]]
}

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

# Validate the entire configuration
validate_config() {
    local errors=0

    echo "🔍 Validating P.A.Z.R.A.S configuration..."

    # Check for duplicate area codes
    local codes=()
    for area in "${!AREAS[@]}"; do
        local code=$(get_area_code "$area")
        if [[ " ${codes[*]} " =~ " ${code} " ]]; then
            echo "❌ Duplicate area code: $code"
            ((errors++))
        fi
        codes+=("$code")
    done

    # Check area naming convention
    for area in "${!AREAS[@]}"; do
        if [[ ! "$area" =~ ^[A-Z]_[A-Za-z]+$ ]]; then
            echo "❌ Invalid area name format: $area (should be Letter_Name)"
            ((errors++))
        fi
    done

    # Check backup config references valid paths
    for path in "${!BACKUP_CONFIG[@]}"; do
        local valid=false
        for pazras_dir in "${!PAZRAS_STRUCTURE[@]}"; do
            if [[ "$path" == "$pazras_dir"* ]]; then
                valid=true
                break
            fi
        done
        if [[ "$valid" != "true" ]]; then
            echo "⚠️  Backup path not in P.A.Z.R.A.S structure: $path"
        fi
    done

    if [[ $errors -eq 0 ]]; then
        echo "✅ Configuration validation passed"
        return 0
    else
        echo "❌ Configuration validation failed with $errors errors"
        return 1
    fi
}

# =============================================================================
# EXPORT FUNCTIONS FOR EXTERNAL USE
# =============================================================================

# Export configuration for other scripts
export_config() {
    local export_file="${1:-/tmp/pazras_config_export.sh}"

    cat > "$export_file" << 'EOF'
# Exported P.A.Z.R.A.S Configuration
# Auto-generated - do not edit manually

EOF

    # Export arrays
    declare -p PAZRAS_STRUCTURE >> "$export_file"
    declare -p AREAS >> "$export_file"
    declare -p SYSTEM_DIRS >> "$export_file"
    declare -p ZETTELKASTEN_STRUCTURE >> "$export_file"
    declare -p BACKUP_CONFIG >> "$export_file"

    echo "Configuration exported to: $export_file"
}

# Generate documentation
generate_docs() {
    cat << 'EOF'
# P.A.Z.R.A.S System Configuration Documentation

## Directory Structure

### Main P.A.Z.R.A.S Categories
EOF

    for dir in $(get_pazras_dirs 2>/dev/null); do
        # Skip empty directories
        [[ -z "$dir" ]] && continue

        local type=$(get_dir_type "$dir" 2>/dev/null || echo "unknown")
        local desc=$(get_dir_description "$dir" 2>/dev/null || echo "No description")
        local freq=$(get_backup_frequency "$dir" 2>/dev/null || echo "manual")

        # Ensure no variable is just a dash
        [[ "$type" == "-" ]] && type="unknown"
        [[ "$desc" == "-" ]] && desc="No description"
        [[ "$freq" == "-" ]] && freq="manual"

        echo "- **${dir}** (${type}, backup: ${freq}): ${desc}"
    done

    cat << 'EOF'

### Areas of Responsibility
EOF

    for area in $(get_areas 2>/dev/null); do
        # Skip empty areas
        [[ -z "$area" ]] && continue

        local code=$(get_area_code "$area" 2>/dev/null || echo "?")
        local desc=$(get_area_description "$area" 2>/dev/null || echo "No description")

        # Ensure no variable is just a dash
        [[ "$code" == "-" ]] && code="?"
        [[ "$desc" == "-" ]] && desc="No description"

        echo "- **${area}** (Code: ${code}): ${desc}"
    done

    cat << 'EOF'

### Scheduled Processes
EOF

    for unit in $(get_timer_units 2>/dev/null); do
        [[ -z "$unit" ]] && continue
        local cal=$(get_timer_field "$unit" on_calendar "?")
        local desc=$(get_timer_field "$unit" desc "No description")
        echo "- **${unit}** (\`${cal}\`): ${desc}"
    done

    cat << 'EOF'

### Zettelkasten Structure
EOF

    for dir in $(get_zettelkasten_dirs 2>/dev/null); do
        # Skip empty directories
        [[ -z "$dir" ]] && continue

        local desc="${ZETTELKASTEN_STRUCTURE[$dir]}"
        if [[ -n "$desc" ]]; then
            # Extract description after the colon
            desc="${desc#*:}"
            [[ "$desc" == "-" ]] && desc="No description"
            echo "- **${dir}**: ${desc}"
        else
            echo "- **${dir}**: No description"
        fi
    done
}

# =============================================================================
# COMMAND LINE INTERFACE (only runs when executed directly, not when sourced)
# =============================================================================

# Only run CLI if this script is executed directly, not sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        "validate")
            validate_config
            ;;
        "export")
            export_config "$2"
            ;;
        "docs")
            generate_docs
            ;;
        "areas")
            get_areas
            ;;
        "dirs")
            get_pazras_dirs
            ;;
        "area-info")
            if [[ -z "$2" ]]; then
                echo "Usage: $0 area-info <area_name>"
                exit 1
            fi
            if is_valid_area "$2"; then
                echo "Area: $2"
                echo "Code: $(get_area_code "$2")"
                echo "Description: $(get_area_description "$2")"
            else
                echo "Invalid area: $2"
                exit 1
            fi
            ;;
        "backup-freq")
            if [[ -z "$2" ]]; then
                echo "Usage: $0 backup-freq <path>"
                exit 1
            fi
            echo "$(get_backup_frequency "$2")"
            ;;
        "timers")
            for unit in $(get_timer_units); do
                printf '%-24s %-22s %s\n' "$unit" "$(get_timer_field "$unit" on_calendar)" \
                    "$(get_timer_field "$unit" desc)"
            done
            ;;
        *)
            cat << EOF
P.A.Z.R.A.S Master Configuration

Usage: $0 <command> [arguments]

Commands:
  validate              - Validate configuration
  export [file]         - Export config for other scripts
  docs                  - Generate documentation
  areas                 - List all areas
  dirs                  - List all P.A.Z.R.A.S directories
  area-info <area>      - Show area information
  backup-freq <path>    - Show backup frequency for path
  timers                 - List scheduled-process units (see also: familiar schedule timers)

Examples:
  $0 validate
  $0 area-info A_Science
  $0 export /tmp/config.sh
  $0 docs > STRUCTURE.md

Note: This file can also be sourced to load configuration arrays and functions.
EOF
            ;;
    esac
fi
