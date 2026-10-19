# shellcheck shell=bash
# roots.sh -- the shell twin of roots.py: where the repository keeps each kind
# of thing, declared once. Source it; it defines variables and runs nothing but
# the profile reader.
#
# Resolved from this file's real location, so it holds whether the caller came
# in through `familiar` on PATH (`~/.local/bin` links to the engine) or a direct
# path.
# `test_roots.py` asserts these values equal roots.py's.

PAZRAS_REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
PAZRAS_ENGINE="$PAZRAS_REPO/engine"
PAZRAS_CONFIG="$PAZRAS_REPO/config"
PAZRAS_MEMORY="$PAZRAS_REPO/memory"
PAZRAS_DEV="$PAZRAS_REPO/dev"

# The install's facts -- PAZRAS_INSTALL, PARA_ROOT, PAZRAS_PROFILE_FILE -- from
# the profile, through the one parser (`profile.py --sh roots`): bash reads no
# YAML of its own. The environment's PARA_ROOT and PAZRAS_INSTALL win there, so
# they win here too.
eval "$(python3 "$PAZRAS_ENGINE/lib/profile.py" --sh roots)"

# The settings, in their new homes (R2e).
PAZRAS_MASTER_CONFIG="$PAZRAS_CONFIG/structure/pazras-master-config.sh"
PAZRAS_PARA_READMES="$PAZRAS_CONFIG/structure/READMEs"
PAZRAS_UNITS="$PAZRAS_CONFIG/schedule"
PAZRAS_BOUNDARIES_JSON="$PAZRAS_CONFIG/boundaries/boundaries.json"
PAZRAS_BACKUP_EXCLUDES="$PAZRAS_CONFIG/backup/backup-excludes.txt"
PAZRAS_MIRROR_EXCLUDES="$PAZRAS_CONFIG/backup/mirror-excludes.txt"

# The exclude lists: the install's own where it has one, the shipped example
# where it does not. `config/backup/` is `omit` from the published tree — the
# files name this install's provider and its disk — and `restic backup
# --exclude-file` FAILS (rc=1, nothing backed up) on a path it cannot read
# rather than defaulting to anything. A published orchestrator whose default
# pointed at a file the export does not ship was a first command that could not
# succeed (D7, 2026-10-15); the example is a real list, so the fallback is a
# working default rather than a stub.
[[ -r "$PAZRAS_BACKUP_EXCLUDES" ]] || \
    PAZRAS_BACKUP_EXCLUDES="$PAZRAS_CONFIG/backup/backup-excludes.example.txt"
[[ -r "$PAZRAS_MIRROR_EXCLUDES" ]] || \
    PAZRAS_MIRROR_EXCLUDES="$PAZRAS_CONFIG/backup/mirror-excludes.example.txt"

# Which provider this install's adapters upload to, and where they live. The
# name is a filename stem, looked up in `config/backup/remotes/` first and in
# the engine's shipped directory second; the template is `example` and reaches
# nothing. See `engine/backup/remotes/select.sh`.
#
# `PAZRAS_STORAGE_REMOTE` arrives with the roots above, not with the storage
# section the config loader exports later: mirror.sh never loads the master
# config, and `sync`/`reconcile` read it inside the loader -- so a value that
# only existed in the second place was missing in the first. Measured
# 2026-10-15, on the real install: `backup sync` fell back to `example` and
# skipped the upload. The selector keeps its own fallback.
PAZRAS_REMOTE_DIR="$PAZRAS_ENGINE/backup/remotes"
PAZRAS_REMOTE_CONFIG_DIR="$PAZRAS_CONFIG/backup/remotes"

# Repo-relative spellings, for messages a person reads.
PAZRAS_ENGINE_REL="${PAZRAS_ENGINE#"$PAZRAS_REPO"/}"
PAZRAS_MEMORY_REL="${PAZRAS_MEMORY#"$PAZRAS_REPO"/}"
PAZRAS_CONFIG_REL="${PAZRAS_CONFIG#"$PAZRAS_REPO"/}"
