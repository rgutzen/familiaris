#!/usr/bin/env bash
# healthcheck.sh — the third scheduled process (ROADMAP.md cross-cutting
# item), separate from `familiar consolidation run`. Where the memory pass asks "is the
# knowledge tree still true", this asks "is the machinery underneath it still
# correctly wired": stow symlinks, generated-file drift, whether scheduled
# units actually SUCCEEDED (not just fired), mounts and disk space.
#
# READ-ONLY BY DEFAULT. `--fix` applies only mechanical, reversible repairs:
#   - re-run `bootstrap.sh` (stow --restow) when a package has drifted
#   - regenerate a derived file that a --check reported as stale
# `--fix` never: runs a package update, touches git (commit/push/checkout),
# or writes into the dotfiles stow canonical source beyond what stow itself
# manages. "Does updates" from the roadmap wording is deliberately narrowed to
# "reports that updates are available" — auto-applying a system update is a
# judgement call this script does not get to make unattended.
#
# TIERS. A check is in one tier of engine/checks/checks.py (`daily`, `weekly`,
# `monthly`) and a run covers its tier and every tier below it. This script asks
# the registry which checks are due (`checks.py --due TIER`) and wraps each
# section it owns in `due ID`, so the cadence of a check is written once, in the
# registry, and `checks.py --audit` fails when a section loses its `due` line.
# The checks the registry runs itself (the unit-test suites, the live-state
# probes) are one section here, "registry checks".
#
# EACH RUN LEAVES A RESULT: $PAZRAS_DATA/healthcheck/<tier>.status. The shell
# greeting reads it, so a failure stays visible until a green run replaces it
# (the notify@ file is one slot and nothing ever clears it), and a tier whose
# timer stopped shows as stale. A run that turns green into red sends one note
# to the phone; a red that stays red does not repeat it.
#
# Usage: familiar checks healthcheck [--tier daily|weekly|monthly] [--only ID] [--fix]
#   --tier   the cadence to run (default weekly: what this command always did)
#   --only   one section owned by this script, by registry id; writes no result
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/roots.sh"
source "$SCRIPT_DIR/../structure/pazras-config-loader.sh"
load_pazras_config >/dev/null 2>&1 || true

FIX=0
TIER=weekly
ONLY=""
usage() {
    echo "usage: familiar checks healthcheck [--tier daily|weekly|monthly] [--only ID] [--fix]" >&2
}
while (( $# )); do
    case "$1" in
        --fix)    FIX=1 ;;
        --tier)   TIER="${2:-}"; shift ;;
        --tier=*) TIER="${1#--tier=}" ;;
        --only)   ONLY="${2:-}"; shift ;;
        --only=*) ONLY="${1#--only=}" ;;
        -h|--help) usage; exit 0 ;;
        *) usage; exit 2 ;;
    esac
    shift
done
case "$TIER" in daily|weekly|monthly) ;; *) usage; exit 2 ;; esac

# The checks due at this tier, from the registry. `--only` narrows to one id.
if ! DUE_IDS="$(python3 "$SCRIPT_DIR/checks.py" --due "$TIER")" || [[ -z "$DUE_IDS" ]]; then
    echo "healthcheck: the registry (checks.py --due $TIER) returned nothing" >&2
    exit 2
fi
if [[ -n "$ONLY" ]]; then
    DUE=" $ONLY "
else
    DUE=" $(echo $DUE_IDS) "
fi
SECTIONS_RUN=0
due() { # <registry id> -- is this section due in this run?
    [[ "$DUE" == *" $1 "* ]] && { SECTIONS_RUN=$((SECTIONS_RUN+1)); return 0; }
    return 1
}
RUN_STARTED=$SECONDS

DOTFILES="$HOME/02_AREAS/B_Tech/dotfiles"
WARN=0
FAIL=0

warn() { echo "  ⚠️  $1"; WARN=$((WARN+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
ok()   { echo "  ✅ $1"; }

echo "PAZRAS health check — $TIER${ONLY:+ (only $ONLY)} — $(date -Is)"
echo

# ── 1. stow package integrity ───────────────────────────────────────────
echo "── stow packages ──"
if due hc-stow; then
if [[ -x "$DOTFILES/bootstrap.sh" ]]; then
    out="$("$DOTFILES/bootstrap.sh" --dry-run 2>&1)"
    # stow --simulate is silent (no "LINK:"/"UNLINK:" lines) when a package
    # needs no change; --restow always re-links, so the signal is whether it
    # reports any WOULD-be action beyond the routine restow noise.
    if echo "$out" | grep -qiE '^(LINK|UNLINK|MKDIR|RMDIR): '; then
        warn "bootstrap.sh --dry-run reports pending stow changes"
        if (( FIX )); then
            echo "     → running bootstrap.sh to restow"
            "$DOTFILES/bootstrap.sh" >/dev/null && ok "restowed"
        else
            echo "     (rerun with --fix to restow, or run bootstrap.sh yourself)"
        fi
    else
        ok "all packages correctly linked"
    fi
else
    warn "bootstrap.sh not found or not executable at $DOTFILES"
fi

# bootstrap.sh used to hardcode its own copy of the enable list, which
# silently fell behind PAZRAS_TIMERS (familiar-memory, pazras-lore-sync and
# pazras-reconcile were enabled by hand and never added there — see
# scheduled-processes.md). Fixed 2026-09-02: bootstrap.sh now sources
# PAZRAS_TIMERS and calls get_timer_units itself, so there is no second list
# to drift — this checks that the fix is still in place, not per-unit
# membership (actual enablement is checked per-unit below, § scheduled units).
if [[ -f "$DOTFILES/bootstrap.sh" ]]; then
    if grep -q 'get_timer_units' "$DOTFILES/bootstrap.sh"; then
        ok "bootstrap.sh enables timers dynamically from PAZRAS_TIMERS (no hardcoded list to drift)"
    else
        warn "bootstrap.sh no longer sources PAZRAS_TIMERS dynamically — its timer-enable list can drift again (see scheduled-processes.md)"
    fi
    # Sourcing the config is only half of it: bootstrap.sh names the config by
    # ABSOLUTE PATH, and it lives in the OTHER repository, so O2f's split of
    # the old combined directory could not reach it, and declared_paths.py's
    # retired-path gate cannot see it (that one reads THIS repo's tracked
    # files, which is the right scope for it and the wrong one for this).
    # The failure is silent by construction — bootstrap.sh prints "skipping"
    # and enables no timers at all — which is the worst available combination
    # and the reason this is checked here rather than remembered.
    boot_cfg=$(grep -oE 'PAZRAS_CONFIG="[^"]+"' "$DOTFILES/bootstrap.sh" 2>/dev/null |
               head -1 | sed 's/^PAZRAS_CONFIG="//; s/"$//')
    if [[ -n "$boot_cfg" ]]; then
        if [[ -f "${boot_cfg/\$HOME/$HOME}" ]]; then
            ok "bootstrap.sh's PAZRAS_CONFIG resolves"
        else
            fail "bootstrap.sh's PAZRAS_CONFIG names $boot_cfg, which does not exist — a fresh bootstrap would enable NO timers and report only 'skipping'"
        fi
    fi
fi
fi
echo

# ── 2. derived-file drift ───────────────────────────────────────────────
echo "── generated files ──"
if load_pazras_config >/dev/null 2>&1; then
    if due structure; then
        if "$SCRIPT_DIR/../familiar" structure generate --check >/dev/null 2>&1; then
            ok "STRUCTURE.md in sync"
        else
            warn "STRUCTURE.md drifted from the master config"
            (( FIX )) && "$SCRIPT_DIR/../familiar" structure generate >/dev/null && ok "regenerated"
        fi
    fi
    if due maps; then
        if "$SCRIPT_DIR/../familiar" structure maps --check >/dev/null 2>&1; then
            ok "the architecture figures are in sync with their registers"
        else
            warn "docs/reference/maps.md drifted from a register it is drawn from"
            (( FIX )) && "$SCRIPT_DIR/../familiar" structure maps >/dev/null && ok "regenerated"
        fi
    fi
    if due timers-gen; then
        if "$SCRIPT_DIR/../familiar" schedule timers --check >/dev/null 2>&1; then
            ok "scheduled-unit staging matches the live dotfiles source"
        else
            warn "scheduled-unit staging differs from the live dotfiles source (familiar schedule timers --check for detail)"
            # Deliberately not auto-fixed even with --fix: applying to dotfiles
            # is the one write this mechanism always gates on --apply-dotfiles --yes.
        fi
    fi
    # 12b. 5d's three floors, against the PREVIOUS run. A floor that is still
    # failing is 5d's open question and says nothing here; a floor that passed and
    # now fails exits 1, which is the only thing this warns about.
    if due orchestration-report; then
        if "$SCRIPT_DIR/../familiar" orchestration report --check >/dev/null 2>&1; then
            ok "5d's floors did not regress since the last report"
        else
            warn "a 5d floor regressed (familiar orchestration report --check for the numbers)"
            # Not auto-fixed: a regression is data about the work, not drift to repair.
        fi
    fi
fi
if due boundaries-compile && [[ -x "$PAZRAS_ENGINE/boundaries/compile.py" ]]; then
    if "$PAZRAS_ENGINE/boundaries/compile.py" --check >/dev/null 2>&1; then
        ok "boundaries prose / guard configs in sync"
    else
        warn "$PAZRAS_MEMORY_REL/boundaries/*.yaml has not been compiled since its last edit"
        (( FIX )) && "$PAZRAS_ENGINE/boundaries/compile.py" >/dev/null && ok "compiled"
    fi
fi
# Pointer integrity of the memory/ tree. `--check` gates only on drift this tool
# can repair itself, so a warn here always has a one-command fix; the report's
# other sections (external paths, bare names) are informational and never gate.
if [[ -x "$PAZRAS_ENGINE/familiar" ]]; then
    if due context-links; then
        if "$PAZRAS_ENGINE/familiar" context links --check >/dev/null 2>&1; then
            ok "$PAZRAS_MEMORY_REL/ pointers all resolve; no orphaned leaves"
        else
            warn "$PAZRAS_MEMORY_REL/ has broken pointers or unrouted leaves (familiar context links)"
            (( FIX )) && "$PAZRAS_ENGINE/familiar" context links --fix >/dev/null \
                && ok "pointers repaired"
        fi
    fi
    if due context-tree; then
        if "$PAZRAS_ENGINE/familiar" context tree --check >/dev/null 2>&1; then
            ok "always-loaded budget and caps hold"
        else
            warn "always-loaded layer is over budget, or a declared file is missing"
        fi
    fi
    if due context-l1; then
        if "$PAZRAS_ENGINE/familiar" context l1 --check >/dev/null 2>&1; then
            ok "always-on payload compiled into harness entry points"
        else
            # Deliberately not auto-fixed even with --fix: `l1` writes into the
            # stow canonical source (dotfiles), the one write this mechanism never
            # applies unattended. Report and let the user run it.
            warn "harness entry points out of sync with $PAZRAS_MEMORY_REL/ (familiar context l1)"
        fi
    fi
fi
if [[ -x "$PAZRAS_ENGINE/familiar" ]]; then
    if due skills-index; then
        if "$PAZRAS_ENGINE/familiar" skills index --check >/dev/null 2>&1; then
            ok "skill routers in sync with frontmatter"
        else
            warn "skill routers (skills/CONTEXT.md, TRIGGERS.md) have drifted"
            (( FIX )) && "$PAZRAS_ENGINE/familiar" skills index >/dev/null && ok "regenerated"
        fi
    fi
    # Exit 1 here is over budget, not drift: the index is written either way,
    # but an index that outgrows its budget is the injected block returning by
    # the back door (memory/knowledge/system/knowledge/knowledge-index.md).
    if due knowledge-index; then
        "$PAZRAS_ENGINE/familiar" knowledge index --check >/dev/null 2>&1
        case $? in
            0) ok "knowledge index in sync and within budget" ;;
            3) warn "knowledge/INDEX.md has drifted from the leaves"
               (( FIX )) && "$PAZRAS_ENGINE/familiar" knowledge index >/dev/null && ok "regenerated" ;;
            *) warn "knowledge/INDEX.md is over its token budget or could not be built" ;;
        esac
    fi
    # O3c: the glossary is generated from the subject register, so drift here
    # means the register changed and the leaf did not follow.
    if due knowledge-glossary; then
        "$PAZRAS_ENGINE/familiar" knowledge glossary --check >/dev/null 2>&1
        case $? in
            0) ok "subject glossary in sync with the register" ;;
            3) warn "system/publication/glossary.md has drifted from the subject register"
               (( FIX )) && "$PAZRAS_ENGINE/familiar" knowledge glossary >/dev/null && ok "regenerated" ;;
            *) warn "the subject glossary could not be built" ;;
        esac
    fi
fi
echo

# ── 2b. the ontology ────────────────────────────────────────────────────
# The DEFINITIONS have a decay policy of their own (SPECS.md O1m): a category is
# reviewed on a cadence, because a stale definition quietly classifies new
# material by an old rule. A stale definition WARNS -- it is a signal, not a
# broken build -- so this section never fails the run.
#
# O3d's trigger lives here too: when `knowledge index --check` exits 1 the
# index has outgrown its 2000-token ceiling, and the fix is a PER-BRANCH split
# -- the branch is the facet, and routing down one is the same operation as
# pre-filtering a vector search. The message text is owned by
# knowledge_index.plan(); this block reads the exit code, so the sentence is
# named once, not copied. Section 2 above still reports the exit as a
# knowledge-section warning; that is the drift/maintenance reading, this one is
# the routing-depth reading.
echo "── ontology ──"
if ! due ontology-review; then
    :
elif [[ -x "$PAZRAS_ENGINE/familiar" ]]; then
    onto_out="$("$PAZRAS_ENGINE/familiar" knowledge ontology review 2>&1)"
    if [[ $? -ne 0 ]]; then
        warn "ontology review failed: $(echo "$onto_out" | head -1)"
    else
        while IFS= read -r line; do
            case "$line" in
                warn\ *) warn "${line#warn }" ;;
                ok\ *)   ok "${line#ok }" ;;
                *)       [[ -n "$line" ]] && echo "     $line" ;;
            esac
        done <<< "$onto_out"
    fi
else
    warn "the consolidation back-end not found — the ontology register was NOT reviewed"
fi
# O3d: the routing-depth trigger, read off the same exit code section 2 uses.
if due knowledge-index; then
    "$PAZRAS_ENGINE/familiar" knowledge index --check >/dev/null 2>&1
    if [[ $? -eq 1 ]]; then
        warn "knowledge/INDEX.md is over its token budget: split into PER-BRANCH indexes (O3d)"
    fi
fi
echo

# ── 3. registry checks ───────────────────────────────────────────────────
# engine/checks/checks.py is the single registry (see its docstring): this
# gate was added specifically because five pytest suites — engine/lib/tests,
# engine/context/tests and the boundaries guard/emitter suites — were run by
# NOTHING before 2026-09-05, not pre-commit, not this script, not CLAUDE.md.
# It now runs every check of this tier that the registry itself executes: the
# unit suites and lints at weekly, the live-state probes (relay, hooks, the
# loadout) at daily. The checks this script owns are the sections around it.
# An `advisory` check that fails is a warning: information, not a defect.
echo "── registry checks ($TIER) ──"
if [[ -n "$ONLY" ]]; then
    :   # --only names a section of this script; the registry runs the rest by id
else
    SECTIONS_RUN=$((SECTIONS_RUN+1))
    reg_json="$(mktemp)"
    python3 "$SCRIPT_DIR/checks.py" --run "$TIER" --json-out "$reg_json" >/dev/null 2>&1
    reg_rc=$?
    if [[ -s "$reg_json" ]]; then
        while IFS='|' read -r kind cid secs; do
            case "$kind" in
                ok)       ok "$cid (${secs} s)" ;;
                fail)     fail "$cid failed (${secs} s) — $PAZRAS_ENGINE_REL/checks/checks.py --run $cid for detail" ;;
                advisory) warn "$cid (advisory) is red (${secs} s) — $PAZRAS_ENGINE_REL/checks/checks.py --run $cid" ;;
            esac
        done < <(python3 - "$reg_json" <<'PY'
import json, sys
for r in json.load(open(sys.argv[1]))["checks"]:
    if r.get("skipped"):
        continue
    kind = "ok" if r["rc"] == 0 else ("advisory" if r.get("advisory") else "fail")
    print(f"{kind}|{r['id']}|{r['seconds']}")
PY
)
    else
        fail "the registry run produced no result ($PAZRAS_ENGINE_REL/checks/checks.py --run $TIER)"
    fi
    rm -f "$reg_json"
fi
echo

# ── 4. scheduled-unit results ───────────────────────────────────────────
# The trap this section exists to catch (CLAUDE.md's own caveat): a green
# timer means the TIMER fired, never that the SERVICE it ran succeeded.
echo "── scheduled units ──"
if ! due hc-units; then
    :
elif command -v systemctl >/dev/null; then
    for u in $(get_timer_units 2>/dev/null); do
        if ! systemctl --user is-enabled "${u}.timer" >/dev/null 2>&1; then
            warn "${u}.timer is not enabled"
            continue
        fi
        # Enabled is not armed: a timer with no next elapse will never fire, and
        # its service's Result stays "success" from the last run it had.
        next_real="$(systemctl --user show "${u}.timer" -p NextElapseUSecRealtime --value 2>/dev/null)"
        next_mono="$(systemctl --user show "${u}.timer" -p NextElapseUSecMonotonic --value 2>/dev/null)"
        if [[ -z "$next_real" && ( -z "$next_mono" || "$next_mono" == 0 ) ]]; then
            warn "${u}.timer is enabled but has no next run — it will never fire (systemctl --user status ${u}.timer)"
        fi
        result="$(systemctl --user show "${u}.service" -p Result --value 2>/dev/null)"
        case "$result" in
            success|"") ok "${u}.service: ${result:-never run yet}" ;;
            *) fail "${u}.service last run: $result (see: journalctl --user -u ${u}.service)" ;;
        esac
    done
else
    warn "systemctl not found — skipping scheduled-unit checks"
fi
echo

# ── 5. mounts and disk space ────────────────────────────────────────────
echo "── mounts / disk ──"
if due hc-mounts; then
if [[ -n "${ARCHIVE_MOUNT:-}" ]]; then
    if mountpoint -q "$ARCHIVE_MOUNT" 2>/dev/null; then
        ok "archive disk mounted at $ARCHIVE_MOUNT"
    else
        warn "archive disk not mounted at $ARCHIVE_MOUNT (normal if the disk is unplugged; the reconcile/mirror/verify timers no-op without it)"
    fi
fi
free_pct=$(df --output=pcent "$HOME" 2>/dev/null | tail -1 | tr -dc '0-9')
if [[ -n "$free_pct" && "$free_pct" -ge 90 ]]; then
    warn "home filesystem is ${free_pct}% full"
else
    ok "home filesystem usage: ${free_pct:-?}%"
fi
fi
echo

# ── 6. dirty trees blocking automation ──────────────────────────────────
# Stage 0 of the memory pass refuses to run on a dirty 06_SYSTEM working
# tree; a tree left dirty for days silently starves consolidation, and
# nothing else surfaces that.
echo "── git trees ──"
for repo in "$HOME/06_SYSTEM" "$DOTFILES"; do
    due hc-git-trees || break
    [[ -d "$repo/.git" ]] || continue
    name="$(basename "$repo")"
    if git -C "$repo" diff --quiet 2>/dev/null && git -C "$repo" diff --cached --quiet 2>/dev/null; then
        ok "$name working tree clean"
    else
        warn "$name working tree is dirty — the nightly memory pass (06_SYSTEM only) and any pending timers-gen --apply-dotfiles review need a clean tree first"
    fi
done
echo

# ── 7. pending memory-consolidation proposals ────────────────────────────
# Stage 8's own docstring: "An unread report is the failure mode this design
# is most exposed to." The nightly pass writes proposals into a dated report
# and nowhere else (memory/journal/reports/README.md explains how to act on
# them); this is the one place a weekly, always-run check nudges you to look,
# since a pending proposal is not itself a failure worth an OnFailure alert.
echo "── memory proposals ──"
if due hc-proposals; then
report_dir="$PAZRAS_MEMORY/journal/reports"
latest_report=$(find "$report_dir" -maxdepth 1 -name '*_consolidation.md' -not -name '*.full.md' 2>/dev/null | sort | tail -1)
if [[ -n "$latest_report" ]]; then
    n=$(grep -o '^## Needs a decision (\([0-9]*\))' "$latest_report" | grep -o '[0-9]*' || echo 0)
    n=${n:-0}
    if [[ "$n" -gt 0 ]]; then
        warn "$n proposal(s) awaiting decision in $(basename "$latest_report") — see $PAZRAS_MEMORY_REL/journal/reports/README.md"
    else
        ok "no pending consolidation proposals ($(basename "$latest_report"))"
    fi
else
    warn "no consolidation report found under $report_dir"
fi
fi
echo

# ── 8. available system updates (report only, never applied) ───────────
echo "── system updates ──"
if ! due hc-updates; then
    :
elif command -v checkupdates >/dev/null 2>&1; then
    n=$(checkupdates 2>/dev/null | wc -l)
    if [[ "$n" -gt 0 ]]; then
        warn "$n package update(s) available — review with \`checkupdates\`, apply with \`omarchy update\` or \`sudo pacman -Syu\` yourself"
    else
        ok "no pending package updates"
    fi
else
    warn "checkupdates not found (pacman-contrib) — cannot report available updates"
fi
echo

echo "── summary ──"
echo "  $FAIL failure(s), $WARN warning(s)$([[ $FIX -eq 1 ]] && echo ", --fix applied what it safely could")"

if [[ -n "$ONLY" ]]; then
    if (( SECTIONS_RUN == 0 )); then
        echo "  --only $ONLY names no section of this script; the registry runs a" >&2
        echo "  check it owns itself with: $PAZRAS_ENGINE_REL/checks/checks.py --run $ONLY" >&2
        exit 2
    fi
else
    # The result a run leaves: read by the shell greeting, and by the next run to
    # tell a new failure from a standing one. Plain key=value, because the
    # greeting is bash that starts with every terminal and parses it without a
    # subprocess.
    RESULT=OK
    (( WARN > 0 )) && RESULT=WARN
    (( FAIL > 0 )) && RESULT=FAIL
    status_dir="$PAZRAS_DATA/healthcheck"
    status_file="$status_dir/$TIER.status"
    previous=""
    [[ -r "$status_file" ]] && previous="$(sed -n 's/^result=//p' "$status_file")"
    read -r _ stale_after _ < <(python3 "$SCRIPT_DIR/checks.py" --tier-info "$TIER")
    if mkdir -p "$status_dir" 2>/dev/null; then
        {
            echo "tier=$TIER"
            echo "result=$RESULT"
            echo "time=$(date +%s)"
            echo "iso=$(date -Is)"
            echo "fail=$FAIL"
            echo "warn=$WARN"
            echo "seconds=$((SECONDS - RUN_STARTED))"
            echo "stale_after=${stale_after:-0}"
        } > "$status_file.tmp" && mv "$status_file.tmp" "$status_file"
    else
        echo "  could not write $status_file" >&2
    fi
    # One note to the phone when a tier turns red; a standing red is the
    # greeting's job. HEALTHCHECK_NOTIFY lets a test (or a machine without the
    # relay) put something else in the command's place.
    if [[ "$RESULT" == FAIL && "$previous" != FAIL ]]; then
        notify=("$PAZRAS_ENGINE/familiar" relay notify)
        [[ -n "${HEALTHCHECK_NOTIFY:-}" ]] && read -ra notify <<< "$HEALTHCHECK_NOTIFY"
        "${notify[@]}" "healthcheck $TIER: $FAIL failure(s) — familiar checks healthcheck --tier $TIER" \
            >/dev/null 2>&1 || true
    fi
fi
(( FAIL > 0 )) && exit 1
exit 0
