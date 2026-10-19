#!/usr/bin/env bash
# pazras-structure-gen — regenerate the derived blocks of STRUCTURE.md.
#
# WHY THIS EXISTS. The category table, the Area codes and the backup schedule
# all live in `pazras-master-config.sh`. They were also hand-copied into
# STRUCTURE.md and CLAUDE.md, and both copies drifted — the storage reference's status section
# claimed "restic repos ✅" for weeks while no repo existed on this machine.
# Two hand-maintained copies of a machine-readable fact always drift.
#
# So the config is the single source of truth and these blocks are DERIVED
# ARTIFACTS, the same rule the skill routers follow: never hand-edit the output,
# edit the config and rerun. Prose outside the markers is hand-written and kept.
#
# Usage: familiar structure generate [--check]      (--check exits 3 on drift)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/pazras-config-loader.sh"
load_pazras_config >/dev/null 2>&1 || true

# The checkout's own file: STRUCTURE.md is part of the repository, so a clone
# anywhere other than the install root (a worktree, a stranger's checkout, the
# publish stage) must regenerate ITS copy, never the installed instance's.
TARGET="${PAZRAS_STRUCTURE_DOC:-$PAZRAS_REPO/STRUCTURE.md}"
CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

gen_categories() {
    printf '| Directory | Role | Backup | Holds |\n|---|---|---|---|\n'
    for key in $(printf '%s\n' "${!PAZRAS_STRUCTURE[@]}" | sort); do
        IFS=':' read -r role freq desc <<< "${PAZRAS_STRUCTURE[$key]}"
        printf '| `%s` | %s | %s | %s |\n' "$key" "$role" "$freq" "$desc"
    done
}

gen_areas() {
    printf '| Code | Area | Concerns |\n|---|---|---|\n'
    for key in $(printf '%s\n' "${!AREAS[@]}" | sort); do
        IFS=':' read -r _slug desc code <<< "${AREAS[$key]}"
        printf '| `%s` | `%s` | %s |\n' "$code" "$key" "$desc"
    done
}

gen_zettel() {
    printf '| Directory | Role | Holds |\n|---|---|---|\n'
    for key in $(printf '%s\n' "${!ZETTELKASTEN_STRUCTURE[@]}" | sort); do
        IFS=':' read -r role desc <<< "${ZETTELKASTEN_STRUCTURE[$key]}"
        printf '| `%s` | %s | %s |\n' "$key" "$role" "$desc"
    done
}

gen_backup() {
    printf '| Frequency | Paths |\n|---|---|\n'
    for freq in daily weekly monthly manual; do
        local list=""
        for key in $(printf '%s\n' "${!BACKUP_CONFIG[@]}" | sort); do
            [[ "${BACKUP_CONFIG[$key]}" == "$freq" ]] && list+="\`$key\` "
        done
        [[ -n "$list" ]] && printf '| %s | %s |\n' "$freq" "$list"
    done
}

replace_block() {   # <file> <tag> <content-file>
    python3 - "$1" "$2" "$3" <<'PY'
import re, sys
path, tag, src = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path).read()
body = open(src).read().rstrip("\n")
pat = re.compile(rf"(<!-- BEGIN:{tag} \(generated\) -->\n).*?(\n<!-- END:{tag} -->)", re.S)
if not pat.search(text):
    sys.stderr.write(f"marker BEGIN:{tag} not found in {path}\n"); sys.exit(1)
open(path, "w").write(pat.sub(lambda m: m.group(1) + body + m.group(2), text))
PY
}

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
cp "$TARGET" "$tmp/work.md"
# A failed substitution must not look like "in sync" -- that is how a
# generated file silently stops being generated.
gen_categories > "$tmp/cat";   replace_block "$tmp/work.md" CATEGORIES "$tmp/cat" || exit 1
gen_areas      > "$tmp/areas"; replace_block "$tmp/work.md" AREAS      "$tmp/areas" || exit 1
gen_zettel     > "$tmp/zet";   replace_block "$tmp/work.md" ZETTEL     "$tmp/zet" || exit 1
gen_backup     > "$tmp/bk";    replace_block "$tmp/work.md" BACKUP     "$tmp/bk" || exit 1

if cmp -s "$tmp/work.md" "$TARGET"; then
    echo "STRUCTURE.md is in sync with the master config."
    exit 0
fi
if (( CHECK )); then
    echo "DRIFT: STRUCTURE.md differs from the master config. Run: familiar structure generate"
    exit 3
fi
cp "$tmp/work.md" "$TARGET"
echo "STRUCTURE.md regenerated from $(basename "${PAZRAS_CONFIG_FILE:-pazras-master-config.sh}")."
