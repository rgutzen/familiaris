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
# Usage: familiar checks healthcheck [--fix]
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/roots.sh"
source "$SCRIPT_DIR/../structure/pazras-config-loader.sh"
load_pazras_config >/dev/null 2>&1 || true

FIX=0
[[ "${1:-}" == "--fix" ]] && FIX=1

DOTFILES="$HOME/02_AREAS/B_Tech/dotfiles"
WARN=0
FAIL=0

warn() { echo "  ⚠️  $1"; WARN=$((WARN+1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL+1)); }
ok()   { echo "  ✅ $1"; }

echo "PAZRAS health check — $(date -Is)"
echo

# ── 1. stow package integrity ───────────────────────────────────────────
echo "── stow packages ──"
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
echo

# ── 2. derived-file drift ───────────────────────────────────────────────
echo "── generated files ──"
if load_pazras_config >/dev/null 2>&1; then
    if "$SCRIPT_DIR/../familiar" structure generate --check >/dev/null 2>&1; then
        ok "STRUCTURE.md in sync"
    else
        warn "STRUCTURE.md drifted from the master config"
        (( FIX )) && "$SCRIPT_DIR/../familiar" structure generate >/dev/null && ok "regenerated"
    fi
    if "$SCRIPT_DIR/../familiar" structure maps --check >/dev/null 2>&1; then
        ok "the architecture figures are in sync with their registers"
    else
        warn "docs/reference/maps.md drifted from a register it is drawn from"
        (( FIX )) && "$SCRIPT_DIR/../familiar" structure maps >/dev/null && ok "regenerated"
    fi
    if "$SCRIPT_DIR/../schedule/timers-gen.sh" --check >/dev/null 2>&1; then
        ok "scheduled-unit staging matches the live dotfiles source"
    else
        warn "scheduled-unit staging differs from the live dotfiles source (familiar schedule timers --check for detail)"
        # Deliberately not auto-fixed even with --fix: applying to dotfiles
        # is the one write this mechanism always gates on --apply-dotfiles --yes.
    fi
fi
if [[ -x "$PAZRAS_ENGINE/boundaries/compile.py" ]]; then
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
if [[ -x "$PAZRAS_ENGINE/cli/familiar-context.py" ]]; then
    if "$PAZRAS_ENGINE/familiar" context links --check >/dev/null 2>&1; then
        ok "$PAZRAS_MEMORY_REL/ pointers all resolve; no orphaned leaves"
    else
        warn "$PAZRAS_MEMORY_REL/ has broken pointers or unrouted leaves (familiar context links)"
        (( FIX )) && "$PAZRAS_ENGINE/familiar" context links --fix >/dev/null \
            && ok "pointers repaired"
    fi
    if "$PAZRAS_ENGINE/familiar" context tree --check >/dev/null 2>&1; then
        ok "always-loaded budget and caps hold"
    else
        warn "always-loaded layer is over budget, or a declared file is missing"
    fi
    if "$PAZRAS_ENGINE/familiar" context l1 --check >/dev/null 2>&1; then
        ok "always-on payload compiled into harness entry points"
    else
        # Deliberately not auto-fixed even with --fix: `l1` writes into the
        # stow canonical source (dotfiles), the one write this mechanism never
        # applies unattended. Report and let the user run it.
        warn "harness entry points out of sync with $PAZRAS_MEMORY_REL/ (familiar context l1)"
    fi
fi
if [[ -x "$PAZRAS_ENGINE/cli/familiar-memory.py" ]]; then
    if "$PAZRAS_ENGINE/familiar" skills index --check >/dev/null 2>&1; then
        ok "skill routers in sync with frontmatter"
    else
        warn "skill routers (skills/CONTEXT.md, TRIGGERS.md) have drifted"
        (( FIX )) && "$PAZRAS_ENGINE/familiar" skills index >/dev/null && ok "regenerated"
    fi
    # Exit 1 here is over budget, not drift: the index is written either way,
    # but an index that outgrows its budget is the injected block returning by
    # the back door (memory/knowledge/system/knowledge/knowledge-index.md).
    "$PAZRAS_ENGINE/familiar" knowledge index --check >/dev/null 2>&1
    case $? in
        0) ok "knowledge index in sync and within budget" ;;
        3) warn "knowledge/INDEX.md has drifted from the leaves"
           (( FIX )) && "$PAZRAS_ENGINE/familiar" knowledge index >/dev/null && ok "regenerated" ;;
        *) warn "knowledge/INDEX.md is over its token budget or could not be built" ;;
    esac
    # O3c: the glossary is generated from the subject register, so drift here
    # means the register changed and the leaf did not follow.
    "$PAZRAS_ENGINE/familiar" knowledge glossary --check >/dev/null 2>&1
    case $? in
        0) ok "subject glossary in sync with the register" ;;
        3) warn "system/publication/glossary.md has drifted from the subject register"
           (( FIX )) && "$PAZRAS_ENGINE/familiar" knowledge glossary >/dev/null && ok "regenerated" ;;
        *) warn "the subject glossary could not be built" ;;
    esac
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
if [[ -x "$PAZRAS_ENGINE/cli/familiar-memory.py" ]]; then
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
"$PAZRAS_ENGINE/familiar" knowledge index --check >/dev/null 2>&1
if [[ $? -eq 1 ]]; then
    warn "knowledge/INDEX.md is over its token budget: split into PER-BRANCH indexes (O3d)"
fi
echo

# ── 3. unit tests ────────────────────────────────────────────────────────
# engine/checks/checks.py is the single registry (see its docstring): this
# gate was added specifically because five pytest suites — engine/lib/tests,
# engine/context/tests and the boundaries guard/emitter suites — were run by
# NOTHING before 2026-09-05, not pre-commit, not this script, not CLAUDE.md.
echo "── unit tests ──"
if [[ -x "$SCRIPT_DIR/checks.py" || -f "$SCRIPT_DIR/checks.py" ]]; then
    if python3 "$SCRIPT_DIR/checks.py" --run healthcheck >/dev/null 2>&1; then
        ok "unit test suites pass ($PAZRAS_ENGINE_REL/checks/checks.py --run healthcheck)"
    else
        fail "one or more unit test suites failed ($PAZRAS_ENGINE_REL/checks/checks.py --run healthcheck for detail)"
    fi
else
    warn "$PAZRAS_ENGINE_REL/checks/checks.py not found — unit tests SKIPPED"
fi
echo

# ── 4. scheduled-unit results ───────────────────────────────────────────
# The trap this section exists to catch (CLAUDE.md's own caveat): a green
# timer means the TIMER fired, never that the SERVICE it ran succeeded.
echo "── scheduled units ──"
if command -v systemctl >/dev/null; then
    for u in $(get_timer_units 2>/dev/null); do
        if ! systemctl --user is-enabled "${u}.timer" >/dev/null 2>&1; then
            warn "${u}.timer is not enabled"
            continue
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
echo

# ── 6. dirty trees blocking automation ──────────────────────────────────
# Stage 0 of the memory pass refuses to run on a dirty 06_SYSTEM working
# tree; a tree left dirty for days silently starves consolidation, and
# nothing else surfaces that.
echo "── git trees ──"
for repo in "$HOME/06_SYSTEM" "$DOTFILES"; do
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
echo

# ── 8. available system updates (report only, never applied) ───────────
echo "── system updates ──"
if command -v checkupdates >/dev/null 2>&1; then
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
(( FAIL > 0 )) && exit 1
exit 0
