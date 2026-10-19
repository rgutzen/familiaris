#!/usr/bin/env bash

# P.A.Z.R.A.S utilities using configuration

# Source configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../structure/pazras-config-loader.sh"
load_pazras_config

# Navigation functions
pazras_goto() {
    local target="$1"
    case "$target" in
        "inbox"|"i") cd "$PARA_ROOT/00_INBOX" ;;
        "projects"|"p") cd "$PARA_ROOT/01_PROJECTS" ;;
        "areas"|"a") cd "$PARA_ROOT/02_AREAS" ;;
        "zettel"|"z") cd "$PARA_ROOT/03_ZETTEL" ;;
        "resources"|"r") cd "$PARA_ROOT/04_RESOURCES" ;;
        "system"|"s") cd "$PAZRAS_INSTALL" ;;
        *)
            if is_valid_area "$target"; then
                cd "$PARA_ROOT/02_AREAS/$target"
            else
                echo "Unknown target: $target"
                echo "Available: inbox(i), projects(p), areas(a), zettel(z), resources(r), system(s)"
                echo "Areas: $(get_areas | tr '\n' ' ')"
                return 1
            fi
            ;;
    esac
    pwd
}

# Quick capture
pazras_capture() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $*" >> "$PARA_ROOT/00_INBOX/quick-capture.md"
    echo "Captured: $*"
}

# Daily note management
pazras_daily() {
    local today=$(date '+%Y-%m-%d')
    local daily_note="$PARA_ROOT/03_ZETTEL/01_Journal/$(date +%Y)/$today.md"
    local template="$PARA_ROOT/03_ZETTEL/04_Templates/daily-note-template.md"

    if [[ ! -f "$daily_note" ]]; then
        mkdir -p "$(dirname "$daily_note")"
        if [[ -f "$template" ]]; then
            sed "s/{{date}}/$today/g" "$template" > "$daily_note"
        else
            echo "# $today" > "$daily_note"
        fi
        echo "Created daily note: $daily_note"
    else
        echo "Daily note exists: $daily_note"
    fi

    echo "$daily_note"
}

# Command interface
case "${1:-}" in
    "goto"|"cd") pazras_goto "$2" ;;
    "capture"|"c") shift; pazras_capture "$@" ;;
    "daily"|"d") pazras_daily ;;
    *)
        echo "P.A.Z.R.A.S Utilities"
        echo "Usage: familiar <command> [args]"
        echo ""
        echo "Commands:"
        echo "  goto <target>  - Navigate to location"
        echo "  capture <text> - Quick capture to inbox"
        echo "  daily          - Create/get daily note"
        ;;
esac
