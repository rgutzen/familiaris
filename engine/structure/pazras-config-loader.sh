#!/usr/bin/env bash

# P.A.Z.R.A.S Configuration Loader
#
# `PAZRAS_MASTER_CONFIG` comes from the roots module, so this file holds no
# path of its own: the master config left the engine in R2e and lives in
# `config/structure/` now.
# Sources the master configuration for use in other scripts

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../lib/roots.sh"

# =============================================================================
# CONFIGURATION DISCOVERY AND LOADING
# =============================================================================

# Find the master configuration file. The example is the last resort: the
# instance's own file does not travel to the public tree, and the example the
# export writes in its place is what a fresh clone runs on until its owner
# copies it -- the same rule as `config/profile.example.yaml`.
find_config_file() {
    local config_paths=(
        "${PAZRAS_CONFIG_FILE:-}"
        "$PAZRAS_MASTER_CONFIG"
        "${PAZRAS_MASTER_CONFIG%.sh}.example.sh"
    )

    for path in "${config_paths[@]}"; do
        if [[ -f "$path" ]]; then
            echo "$path"
            return 0
        fi
    done

    return 1
}

# Load master configuration
load_pazras_config() {
    local config_file

    # Allow override via environment variable
    if [[ -n "${PAZRAS_CONFIG_FILE:-}" ]] && [[ -f "${PAZRAS_CONFIG_FILE:-}" ]]; then
        config_file="${PAZRAS_CONFIG_FILE:-}"
    else
        config_file=$(find_config_file)
    fi

    if [[ -z "$config_file" ]]; then
        echo "❌ Error: P.A.Z.R.A.S configuration file not found!" >&2
        echo "Please ensure pazras-master-config.sh is available in one of these locations:" >&2
        echo "  - $PAZRAS_MASTER_CONFIG" >&2
        echo "  - ${PAZRAS_MASTER_CONFIG%.sh}.example.sh" >&2
        echo "  - \$PAZRAS_CONFIG_FILE (environment variable)" >&2
        echo "Run: familiar structure link, if the commands are not on PATH" >&2
        return 1
    fi

    # The profile first: the Areas and the storage paths are declared there
    # (P1), and the master config's restic section reads the storage paths. A
    # profile with problems is refused here rather than run on defaults:
    # `--sh` always exits 0 and emits a usable fallback (roots.sh needs that),
    # so its status says nothing, and `eval "$(...)"` would hide a failed
    # reader anyway. `--check` decides; the output is captured, then evaluated.
    local profile_problems profile_sh
    if ! profile_problems="$(python3 "$PAZRAS_ENGINE/lib/profile.py" --check 2>&1 >/dev/null)"; then
        echo "❌ Error: the profile has problems ($PAZRAS_PROFILE_FILE):" >&2
        printf '%s\n' "$profile_problems" >&2
        return 1
    fi
    if ! profile_sh="$(python3 "$PAZRAS_ENGINE/lib/profile.py" --sh structure)"; then
        echo "❌ Error: could not read the profile ($PAZRAS_PROFILE_FILE)" >&2
        return 1
    fi
    eval "$profile_sh"

    # Source the configuration
    if source "$config_file"; then
        PAZRAS_CONFIG_LOADED=true
        PAZRAS_CONFIG_FILE="$config_file"
        echo "✅ Loaded P.A.Z.R.A.S configuration from: $config_file" >&2
        return 0
    else
        echo "❌ Error: Failed to load configuration from: $config_file" >&2
        return 1
    fi
}

# =============================================================================
# ENHANCED UTILITY FUNCTIONS
# =============================================================================

# Build full directory structure dynamically
build_directory_structure() {
    local base_path="${1:-$PARA_ROOT}"
    local structure=()

    # Main P.A.Z.R.A.S directories
    for dir in $(get_pazras_dirs); do
        structure+=("$base_path/$dir")

        # Add subdirectories based on type
        case "$dir" in
            "01_PROJECTS")
                structure+=("$base_path/$dir/_templates")
                ;;
            "02_AREAS")
                for area in $(get_areas); do
                    structure+=("$base_path/$dir/$area")
                    structure+=("$base_path/$dir/$area/_processes")
                    structure+=("$base_path/$dir/$area/_tracking")
                done
                ;;
            "03_ZETTEL")
                # Zettelkasten structure
                for zettel_dir in $(get_zettelkasten_dirs); do
                    structure+=("$base_path/$dir/$zettel_dir")
                done

                # Area-specific subdirectories in permanent notes
                for area in $(get_areas); do
                    structure+=("$base_path/$dir/02_Permanent-Notes/$area")
                done

                # Year subdirectory for daily notes
                structure+=("$base_path/$dir/01_Journal/$(date +%Y)")
                ;;
            "04_RESOURCES")
                structure+=("$base_path/$dir/Papers")
                structure+=("$base_path/$dir/Books")
                structure+=("$base_path/$dir/Courses")
                ;;
            "05_ARCHIVES")
                structure+=("$base_path/$dir/Projects")
                structure+=("$base_path/$dir/Areas")
                structure+=("$base_path/$dir/Resources")
                ;;
            "06_SYSTEM")
                for sys_dir in "${!SYSTEM_DIRS[@]}"; do
                    structure+=("$base_path/$dir/$sys_dir")
                done
                for sys_link in "${!SYSTEM_LINKS[@]}"; do
                    structure+=("link:$base_path/$dir/$sys_link:${SYSTEM_LINKS[$sys_link]}")
                done
                ;;
        esac
    done

    printf '%s\n' "${structure[@]}" | sort -u
}

# Get backup paths with frequencies
get_backup_schedule() {
    local frequency="${1:-all}"

    for path in "${!BACKUP_CONFIG[@]}"; do
        local freq="${BACKUP_CONFIG[$path]}"
        if [[ "$frequency" == "all" ]] || [[ "$freq" == "$frequency" ]]; then
            echo "$path:$freq"
        fi
    done
}

# Generate area README content
generate_area_readme() {
    local area="$1"
    local area_code=$(get_area_code "$area")
    local area_desc=$(get_area_description "$area")

    cat << EOF
# $area

**Area Code**: $area_code
**Focus**: $area_desc

## Purpose & Standards
<!-- Define what you're trying to maintain in this area -->

## Current Focus
<!-- What are you actively working on? -->

## Key Resources
- [[$area_code MOC]] (Map of Content)
- Research papers in: 04_RESOURCES/Papers/$area/

## Processes & Workflows
<!-- How do you manage this area? -->

## Metrics & Tracking
<!-- How do you measure success? -->

## Related Projects
<!-- Current and recent projects in this area -->

## Zettelkasten Notes
- Area notes: [[$area_code.*]]
- Note prefix: $area_code.x.x.x_name

---
Last updated: $(date '+%Y-%m-%d')
Area: $area | Code: $area_code
EOF
}

# =============================================================================
# VALIDATION AND SETUP HELPERS
# =============================================================================

# Validate that configuration is loaded
require_config() {
    if [[ "${PAZRAS_CONFIG_LOADED:-}" != "true" ]]; then
        echo "❌ Error: P.A.Z.R.A.S configuration not loaded!" >&2
        echo "Call load_pazras_config first." >&2
        return 1
    fi
}

# Ensure all required directories exist
ensure_directory_structure() {
    local base_path="${1:-$PARA_ROOT}"
    local created_count=0

    require_config || return 1

    echo "📁 Ensuring P.A.Z.R.A.S directory structure exists..."

    while IFS= read -r dir; do
        # `link:<path>:<target>` -- a subdirectory that is a LINK to a separate
        # repository. Created as a symlink, never as a directory: a plain
        # directory here would shadow the dotfiles repo the link exists to
        # reach (the finding that put this branch in `SYSTEM_LINKS`).
        if [[ "$dir" == link:* ]]; then
            local link_path="${dir#link:}"; link_path="${link_path%%:*}"
            local link_target="${dir##*:}"
            if [[ ! -e "$link_path" && ! -L "$link_path" ]]; then
                ln -sfn "$link_target" "$link_path"
                echo "Linked:  ${link_path#$base_path/} -> $link_target"
                ((created_count++))
            fi
            continue
        fi
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            echo "Created: ${dir#$base_path/}"
            ((created_count++))
        fi
    done < <(build_directory_structure "$base_path")

    if [[ $created_count -gt 0 ]]; then
        echo "✅ Created $created_count directories"
    else
        echo "✅ All directories already exist"
    fi
}

# Create area README files
create_area_readmes() {
    local base_path="${1:-$PARA_ROOT}"

    require_config || return 1

    echo "📝 Creating area README files..."

    for area in $(get_areas); do
        local readme_path="$base_path/02_AREAS/$area/_README.md"

        if [[ ! -f "$readme_path" ]]; then
            generate_area_readme "$area" > "$readme_path"
            echo "Created README for: $area"
        else
            echo "README exists for: $area"
        fi
    done
}

# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Script is being run directly, not sourced

    case "${1:-}" in
        "load")
            load_pazras_config
            ;;
        "validate")
            load_pazras_config && validate_config
            ;;
        "structure")
            load_pazras_config && build_directory_structure "$2"
            ;;
        "schedule")
            load_pazras_config && get_backup_schedule "$2"
            ;;
        "test")
            echo "🧪 Testing configuration loader..."
            if load_pazras_config; then
                echo "✅ Configuration loaded successfully"
                echo "📁 Available areas: $(get_areas | wc -l)"
                echo "📁 Available directories: $(get_pazras_dirs | wc -l)"
                echo "🔄 Backup configurations: $(echo "${!BACKUP_CONFIG[@]}" | wc -w)"
                validate_config
            else
                echo "❌ Configuration loading failed"
                exit 1
            fi
            ;;
        *)
            cat << EOF
P.A.Z.R.A.S Configuration Loader

Usage: $0 <command> [arguments]

Commands:
  load                  - Load configuration (for testing)
  validate              - Load and validate configuration
  structure [base_path] - Show directory structure
  schedule [frequency]  - Show backup schedule
  test                  - Test configuration loading

For use in other scripts:
  source pazras-config-loader.sh
  load_pazras_config
  # Use configuration functions...

Example:
  $0 test
  $0 structure ~/
EOF
            ;;
    esac
fi
