#!/usr/bin/env bash
# pazras-status.sh — is the system actually being maintained?
#
# A timer that silently stops firing is indistinguishable from one that
# succeeds quietly. This makes the difference visible: it reports the AGE of
# the last success, not merely whether the last run passed.
#
#   pazras-status.sh          human-readable
#   pazras-status.sh --bar    one line for polybar/waybar
set -uo pipefail
export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.config/restic/password}"
R="${RESTIC_ROOT:-$HOME/.local/share/restic}"
WARN_HOURS=48
worst=0; out=""

for repo in zettel-system inbox-projects-areas-archives resources; do
    if [[ ! -d "$R/$repo" ]]; then
        out+="  ✗ $repo: REPO MISSING ($R/$repo)\n"; worst=2; continue
    fi
    last=$(restic -r "$R/$repo" snapshots --json 2>/dev/null \
           | grep -Po '"time":"\K[^"]+' | sort | tail -1)
    if [[ -z "$last" ]]; then
        out+="  ✗ $repo: NO SNAPSHOTS\n"; worst=2; continue
    fi
    age_h=$(( ( $(date +%s) - $(date -d "$last" +%s) ) / 3600 ))
    if   (( age_h > WARN_HOURS*7 )); then out+="  ✗ $repo: ${age_h}h old\n"; worst=2
    elif (( age_h > WARN_HOURS ));   then out+="  ⚠ $repo: ${age_h}h old\n"; (( worst < 1 )) && worst=1
    else out+="  ✓ $repo: ${age_h}h ago\n"; fi
done

fails=$(tail -5 "$HOME/05_ARCHIVES/Logs/pazras-failures.log" 2>/dev/null | wc -l)

if [[ "${1:-}" == "--bar" ]]; then
    case $worst in 0) echo "backup ok";; 1) echo "backup stale";; *) echo "BACKUP FAILING";; esac
    exit $worst
fi
echo "PAZRAS backup status (warn >${WARN_HOURS}h)"; printf "%b" "$out"
(( fails > 0 )) && echo "  recent failures logged: $fails (05_ARCHIVES/Logs/pazras-failures.log)"
exit $worst
