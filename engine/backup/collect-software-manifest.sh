#!/usr/bin/env bash
# collect-software-manifest.sh — record what is installed, so the new machine
# can be rebuilt from a list instead of restored from binaries.
#
#   ./collect-software-manifest.sh
#
# Output: 05_ARCHIVES/Records/machines/<host>/<date>/
#
# WHY A MANIFEST AND NOT A BACKUP
# ~95 GB of this laptop is package managers, caches and compiled binaries.
# Restoring those onto Omarchy would fail anyway: they are built against
# Ubuntu 22.04's glibc, and the target is Arch. A few hundred KB of lists is
# both smaller and more likely to work. (The `glibc238` directory in $HOME is
# evidence of having hit this before.)
set -uo pipefail

HOST="$(hostname -s)"
OUT="$HOME/05_ARCHIVES/Records/machines/$HOST/$(date +%F)"
mkdir -p "$OUT/conda"
echo "▸ writing manifest to $OUT"

cap() { # cap <file> <description> <command...>
    local f="$1" desc="$2"; shift 2
    if command -v "$1" >/dev/null 2>&1 || [[ "$1" == ls ]]; then
        { echo "# $desc"; echo "# captured $(date -Is) on $HOST"; "$@" ; } > "$OUT/$f" 2>/dev/null \
            && echo "  ✓ $f ($(grep -vc '^#' "$OUT/$f" 2>/dev/null) entries)" \
            || echo "  ! $f (command failed)"
    else
        echo "  – $f (not installed)"
    fi
}

# ── system packages ──────────────────────────────────────────────────────
# apt output is a REFERENCE, not an install list: Omarchy is Arch. 1685
# manual packages is a decade of accumulation, most of them transitive deps
# that pacman resolves differently. Curate pkg-core.txt by hand from this.
cap apt-manual.txt   "Ubuntu: explicitly installed packages (reference only)" apt-mark showmanual
cap snap.txt         "snap packages (foreign to Arch; find AUR/flatpak equivalents)" snap list
cap flatpak.txt      "flatpak applications (portable to Arch)" flatpak list --app --columns=application

# ── language / tool ecosystems: these DO port cleanly ────────────────────
cap pipx.txt         "pipx applications" pipx list --short
cap cargo.txt        "cargo installed binaries" cargo install --list
cap npm-global.txt   "npm global packages" npm ls -g --depth=0
cap rustup.txt       "rust toolchains" rustup toolchain list
cap go.txt           "go version" go version
cap elan.txt         "Lean toolchains" ls "$HOME/.elan/toolchains"
cap nvm.txt          "node versions" ls "$HOME/.nvm/versions/node"

# ── conda: --from-history is the load-bearing flag ───────────────────────
# A default `conda env export` pins every transitive dependency to an exact
# build compiled for THIS glibc; those will not resolve on Arch. --from-history
# records only what was explicitly requested, letting the solver rebuild
# natively. The pre-2021 exports in Records/envs are full-pin and unusable.
if [[ -d "$HOME/miniforge3/envs" ]]; then
    echo "  conda environments (--from-history):"
    for e in "$HOME/miniforge3/envs"/*; do
        [[ -d "$e" ]] || continue
        n=$(basename "$e")
        conda env export -n "$n" --from-history > "$OUT/conda/$n.yml" 2>/dev/null \
            && echo "      ✓ $n" || echo "      ! $n (export failed)"
    done
fi

# ── AI assistant tooling (reinstallable bulk, ~9.8 GB) ───────────────────
# opencode writes this file itself; read the live copy, not a snapshot.
[[ -f "$HOME/.config/opencode/package.json" ]] && \
    cp "$HOME/.config/opencode/package.json" "$OUT/opencode-package.json" 2>/dev/null
ls "$HOME/.claude/plugins" > "$OUT/claude-plugins.txt" 2>/dev/null && echo "  ✓ claude-plugins.txt"

# ── scheduled jobs & misc state ──────────────────────────────────────────
crontab -l > "$OUT/crontab.txt" 2>/dev/null && echo "  ✓ crontab.txt"
systemctl --user list-unit-files --state=enabled --no-legend > "$OUT/systemd-user-enabled.txt" 2>/dev/null \
    && echo "  ✓ systemd-user-enabled.txt"
fc-list : family 2>/dev/null | sort -u > "$OUT/fonts.txt" && echo "  ✓ fonts.txt ($(wc -l < "$OUT/fonts.txt") families)"
lpstat -p 2>/dev/null > "$OUT/printers.txt" && [[ -s "$OUT/printers.txt" ]] && echo "  ✓ printers.txt"
# Firefox bookmarks: copy places.sqlite (locked while running, so copy not read)
for prof in "$HOME"/.mozilla/firefox/*.default*/; do
    [[ -f "$prof/places.sqlite" ]] || continue
    cp "$prof/places.sqlite" "$OUT/firefox-places.sqlite" 2>/dev/null && echo "  ✓ firefox-places.sqlite (bookmarks+history)"
    break
done

# ── desktop/system context worth having when rebuilding ──────────────────
{
    echo "# system context — captured $(date -Is)"
    echo "host:      $HOST"
    echo "distro:    $(lsb_release -ds 2>/dev/null || cat /etc/os-release 2>/dev/null | head -1)"
    echo "kernel:    $(uname -r)"
    echo "session:   ${XDG_SESSION_TYPE:-?} / ${XDG_CURRENT_DESKTOP:-?}"
    echo "shell:     $SHELL"
    echo "locale:    ${LANG:-?}"
    echo "cpu:       $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs)"
    echo "memory:    $(free -h | awk '/^Mem:/{print $2}')"
    echo "disks:"; lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT 2>/dev/null | grep -v loop | sed 's/^/  /'
} > "$OUT/system-context.txt" && echo "  ✓ system-context.txt"

# ── a curated core list is the actual deliverable ────────────────────────
if [[ ! -f "$HOME/05_ARCHIVES/Records/machines/pkg-core.txt" ]]; then
cat > "$HOME/05_ARCHIVES/Records/machines/pkg-core.txt" <<'EOF'
# pkg-core.txt — the 50-80 tools you would actually miss, with ARCH names.
# THIS is what you install on Omarchy; apt-manual.txt is only a memory aid.
# Hand-curated on purpose: 1685 apt packages is accumulation, not intent.
#
# pacman -S --needed - < pkg-core.txt
#
# --- shell / core ---
git stow rsync restic age zsh tmux
# --- editors ---
neovim
# --- dev ---
python python-pip rustup go nodejs npm
# --- media / documents ---
zathura imagemagick ffmpeg pandoc texlive-core
# --- desktop (Omarchy ships most of this) ---
# hyprland waybar wofi
# --- science ---
# (fill in)
EOF
echo "  ✓ pkg-core.txt template created — CURATE THIS BY HAND"
fi

echo
echo "✅ manifest written: $OUT"
echo "   next: curate 05_ARCHIVES/Records/machines/pkg-core.txt with Arch package names"
