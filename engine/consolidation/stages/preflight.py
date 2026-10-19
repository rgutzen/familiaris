"""Stage 0 -- Preflight. Snapshot a dirty tree; take the lock.

A dirty working tree means a human is mid-edit somewhere in the repo -- not
necessarily in `memory/`, and `Persistent=true` plus daily work anywhere on
the machine means the tree is dirty most nights (agent-own paths like
`skills/`, `knowledge/`, `CLAUDE.md` change from ordinary work,
not just deliberate edits). Decided 2026-09-07: rather than abort every such
night, preflight COMMITS the dirty tree first, as its OWN separate commit
(`wip: pre-sleep snapshot`), before the pass does anything else. This keeps
invariant 4 intact rather than breaking it -- "a bad night is one revert"
still holds for the pass's own work, because the human's snapshot is a
separate, independently revertible commit, never merged into the pass's.

QUIESCENCE GUARD. A snapshot must not freeze a half-typed sentence: if any
dirty path was modified within QUIET_SECONDS of "now", the tree is treated as
ACTIVELY being edited and the pass still aborts, exactly as before. This is
the one case pre-sleep commit does not cover -- a machine being typed into at
03:37.

The lock exists because `Persistent=true` makes a suspended laptop fire a
catch-up run on resume, which can land on top of a run already going.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import pathlib
import time

from lib import git
from consolidation import ledger

_handle = None

# Below this age, a dirty file is treated as still being typed into, not a
# stray leftover -- the pass aborts instead of snapshotting. 2 minutes is
# generous for a systemd timer firing once a night; it only has to beat
# "someone is at the keyboard right now", not model a real edit session.
QUIET_SECONDS = 120


def run(ctx) -> bool:
    """False aborts the pass."""
    global _handle
    lock = ctx.base / "consolidation.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    _handle = open(lock, "w")
    try:
        fcntl.flock(_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        ctx.aborted = "another consolidation pass holds the lock"
        ctx.note("0", ctx.aborted, "error")
        return False

    # None, not []: an empty list is a CLEAN tree, None is "git could not
    # answer" -- no repository means no idea what the pass would be changing.
    dirty = git.status_lines(ctx.repo)
    if dirty is None:
        ctx.aborted = "not a git repository, or git failed"
        ctx.note("0", ctx.aborted, "error")
        return False
    if dirty:
        listing = "\n".join("      " + d for d in dirty[:12])
        more = f"\n      ... and {len(dirty) - 12} more" if len(dirty) > 12 else ""
        if ctx.dry_run:
            # In --dry-run the pass writes nothing, so a dirty tree cannot be
            # merged into anything or snapshotted: report and continue, which
            # is what makes the skeleton usable while a human is still working.
            ctx.note("0", f"working tree is dirty ({len(dirty)} paths) -- reporting "
                          f"only, nothing was written:\n{listing}{more}", "warn")
        elif _actively_edited(ctx.repo, dirty):
            ctx.aborted = (f"working tree is dirty ({len(dirty)} paths) and at least "
                           f"one path changed in the last {QUIET_SECONDS}s -- a human "
                           f"looks actively mid-edit. Commit or stash, then rerun.\n"
                           f"{listing}{more}")
            ctx.note("0", ctx.aborted, "error")
            return False
        else:
            r = git.commit(ctx.repo,
                           f"wip: pre-sleep snapshot ({len(dirty)} path(s), "
                           f"uncommitted at consolidation start)\n\n"
                           f"Committed by the preflight stage so the nightly pass "
                           f"is never blocked by ordinary same-day edits. This is NOT\n"
                           f"the pass's own work -- see the following commit for that.\n",
                           paths=(".",))
            if not r.ok:
                ctx.aborted = (f"working tree is dirty ({len(dirty)} paths) and the "
                               f"pre-sleep snapshot commit failed: "
                               f"{r.err.strip()[:200]}\n{listing}{more}")
                ctx.note("0", ctx.aborted, "error")
                return False
            ctx.act("0", "pre-sleep snapshot",
                    f"committed {len(dirty)} dirty path(s) as {git.head(ctx.repo)}")
            ctx.note("0", f"pre-sleep snapshot: committed {len(dirty)} dirty path(s) "
                          f"left over from same-day work:\n{listing}{more}")

    ctx.branch = git.branch(ctx.repo)
    ctx.head = git.head(ctx.repo)
    ctx.quiet = _is_quiet(ctx)
    return True


def _actively_edited(repo, dirty: list[str]) -> bool:
    """True if any dirty path's mtime is within QUIET_SECONDS of now.

    Best-effort: porcelain status lines are `XY path` (rename lines carry an
    arrow and are skipped -- ambiguous which side to stat). A path that no
    longer exists (staged delete) or cannot be stat'd is NOT evidence of
    active editing, so it does not block the snapshot -- only a live, recent
    mtime does.
    """
    now = time.time()
    for line in dirty:
        if "->" in line or len(line) < 4:
            continue
        rel = line[3:].strip().strip('"')
        try:
            mtime = (repo / rel).stat().st_mtime
        except OSError:
            continue
        if now - mtime < QUIET_SECONDS:
            return True
    return False


def _fingerprint(ctx) -> str:
    """What the pass would have to work with. Identical fingerprint = idle day."""
    parts = [ctx.head]
    tdir = ctx.base / "transcripts"
    if tdir.is_dir():
        parts += sorted(f"{p.name}:{p.stat().st_size}" for p in tdir.iterdir())
    # The ledger set comes from `ledger`, so a ledger added there is a ledger
    # the idle check can see. `session.log` is TSV and named explicitly.
    for name in (*ledger.FILES, "session.log"):
        f = ctx.base / name
        parts.append(f"{name}:{f.stat().st_size if f.exists() else 0}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def last_run(base) -> dict:
    """What the previous completed pass left behind, or `{}`.

    Public because the brief (stage 8) needs the same state object this module
    writes: "what changed" means "changed since the revision the last pass
    ended on", and that revision has exactly one recorded home. An absent or
    unreadable file is `{}` -- a first run and a corrupt state file both mean
    "no anchor", and the caller says so rather than inventing one.
    """
    try:
        data = json.loads((pathlib.Path(base) / "last-run.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_quiet(ctx) -> bool:
    """True when nothing has changed since the last completed pass.

    A day the laptop was not used produces no transcripts, no usage lines and
    no commits. Running the full pass anyway would burn two cloud calls to
    conclude nothing, rewrite a report nobody needs, and -- worst -- let stage 6
    propose demotions built on another day of decay that the user had no chance
    to prevent. `Persistent=true` makes this common: a machine off for a week
    fires a catch-up run the moment it boots.

    Utility decay is separately protected by counting active days
    (`activity.py`); this check is about not doing pointless work at all.
    """
    fp = _fingerprint(ctx)
    ctx.fingerprint = fp
    prev = last_run(ctx.base).get("fingerprint")
    if not prev:
        return False
    return prev == fp


def record_run(ctx) -> None:
    """Remember the state the pass LEAVES BEHIND, so the next one can tell an
    idle day.

    Recomputed here, after the pass has committed its own work -- not reused
    from preflight. The pass commits, which moves HEAD, which changes the
    fingerprint; storing the pre-commit value meant every run looked like a
    change had happened and the idle check could never fire once. Found by the
    check failing to fire on the very first idle night.
    """
    if ctx.dry_run:
        return
    ctx.head = git.head(ctx.repo)
    try:
        (ctx.base / "last-run.json").write_text(json.dumps({
            "fingerprint": _fingerprint(ctx),
            "date": ctx.today.isoformat(),
            # The revision this pass ENDED on, so the next brief can ask git
            # for an exact range instead of a date. Written after the commit,
            # like the fingerprint and for the same reason -- `ctx.head` above
            # has just been re-read past the pass's own commit.
            "head": ctx.head,
            "stages": ctx.stages_run}, indent=1) + "\n")
    except OSError:
        pass


def release():
    global _handle
    if _handle:
        try:
            fcntl.flock(_handle, fcntl.LOCK_UN)
            _handle.close()
        except OSError:
            pass
        _handle = None
