#!/usr/bin/env python3
"""push_guard.py -- the private tree never pushes to the public repository.

WHY THIS EXISTS, and why at `pre-push`. The public repository is GENERATED:
`publish.py` writes a cleaned tree into a clone of it, a human reads the diff,
and the human pushes from THERE. This repository keeps everything the export
omits -- the journal, `config/practice/user/**`, `dev/**` -- so one push of one
branch from here to the public repository puts the whole private history into a
public object store, and nothing takes that back. There is no gate on the way
in, which is why the gate is on the way out.

THE NAME IS THE WHOLE DIFFICULTY. Until 2026-10-14 the PRIVATE repository
carried the bare name; the rename gives the private one a suffix naming the
machine it lives on and leaves the bare name to the public one. So one remote
spelling means two different repositories on the two sides of that date, and no
fact inside this tree distinguishes them. What IS decidable is the pair: a push
whose URL names `<handle>/<the name below>` FROM a checkout that has `dev/` is
the push that must not happen. A publish clone has no `dev/` -- the
classification omits it -- which is exactly why the push that SHOULD happen is
not blocked.

THE HANDLE COMES FROM THE PROFILE (P1). `identity.handle` is the public forge
account, so no account is spelled here; where the profile in force is the
shipped example, the handle is a placeholder and the guard is inert, because the
example names nobody. The repository half of the name is the constant below: it
is a decision, not a fact about a person.

THE TRANSPORT IS NOT PARSED FOR MEANING. ssh, https and a local path are all
the same pair to this guard, deliberately: what is refused is the destination,
and a test's fake remote is a local path. Only the last two path segments are
read.

ARMED IS A STATE, NOT A FILE. `.git/hooks/pre-push` is a symlink shared through
`$GIT_COMMON_DIR`, so git runs the MAIN checkout's copy of the hook body whichever
worktree the push comes from -- and that body resolves the tree being pushed and
runs THAT tree's guard, which is why the two copies may differ. `--check` asks
three questions rather than one: is a hook installed, is it this hook, is it
executable. A symlink whose target the resolving checkout does not have is
INSTALLED AND INERT -- reported rather than failed, because no reader can fix it
by acting.

Usage:
    python3 engine/checks/push_guard.py --url <remote-url> [--tree <dir>]
        what the hook calls; exit 1 refuses the push
    python3 engine/checks/push_guard.py --check
        is the guard armed in this checkout? exit 1 when it must be and is not
Exit codes: 0 allow, 1 refuse, 2 usage.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lib import profile  # noqa: E402
from lib import roots  # noqa: E402

# The public repository's name, and half of the pair that identifies it; the
# other half is the handle the profile declares.
PUBLIC_REPO = "familiaris"

# This guard, and the hook file that wires it.
HOOK_NAME = "pre-push"
HOOK_FILE = HERE / HOOK_NAME

# The install command, spelled from the root's own name so the guard has no
# second copy of it; the `../../` is relative to the hooks directory git prints.
ARM = f"ln -sfn ../../{roots.ENGINE_REL}/checks/{HOOK_NAME}"

# The directory whose presence says "this checkout holds the private tree".
PRIVATE_MARKER = "dev"

# The tail of a remote URL: `owner/repo`, with or without `.git`, whatever
# precedes it. Read from the END, so a host, a scheme, a `user@` and a port are
# all irrelevant to the question.
REMOTE = re.compile(r"(?:^|[/:])(?P<owner>[^/:]+)/(?P<repo>[^/]+?)(?:\.git)?$")

# git's own variables, cleared before running git: in a hook `GIT_DIR` points at
# the repository's git directory rather than the working tree being pushed, and
# `rev-parse` would then answer about the wrong checkout. `checks.py` clears
# the same five for its children, for the same reason.
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX",
                "GIT_COMMON_DIR")


def git(tree: pathlib.Path, *args: str) -> str:
    """`git <args>` in `tree`, or "" when git cannot answer."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    done = subprocess.run(("git",) + args, cwd=str(tree), env=env,
                          capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def pair(url: str):
    """`(owner, repo)` from a remote URL, lowercased; None when there is none."""
    if not url:
        return None
    found = REMOTE.search(url.strip().rstrip("/"))
    if found is None:
        return None
    return found.group("owner").lower(), found.group("repo").lower()


def public_owner(p=None) -> str:
    """The forge handle the public repository sits under, from the profile."""
    p = roots.PROFILE if p is None else p
    handle = p.identity.get("handle")
    if not isinstance(handle, str):
        return ""
    handle = handle.strip()
    return "" if handle in profile.placeholders(p) else handle


def is_public(url: str, p=None) -> bool:
    """Whether `url` names the public repository."""
    owner = public_owner(p)
    return bool(owner) and pair(url) == (owner.lower(), PUBLIC_REPO)


def refuses(url: str, tree, p=None) -> str | None:
    """The reason to refuse this push, or None to allow it.

    Two conditions, and both are needed: the destination is the public
    repository, and the checkout being pushed holds the private tree. A publish
    clone pushing to the public repository is the normal case, and a private
    checkout pushing to the private repository is the other one.
    """
    tree = pathlib.Path(tree)
    if not is_public(url, p):
        return None
    if not (tree / PRIVATE_MARKER).is_dir():
        return None
    owner = public_owner(p)
    return (f"{url} is the PUBLIC repository and this checkout has `{tree / PRIVATE_MARKER}`, "
            f"so a push from here publishes the journal, the user's own practice "
            f"files and the private working notes in one step, for good. The public tree "
            f"is generated: push from the publish clone instead, which has no "
            f"`{PRIVATE_MARKER}/`. If this checkout's own remote still names the "
            f"public repository, the rename has not reached it -- `git remote "
            f"set-url origin` it to `{owner}/{PUBLIC_REPO}-<this machine>`.")


def hook_path(tree) -> pathlib.Path | None:
    """Where git looks for this checkout's hooks, or None if git cannot say."""
    hooks = git(pathlib.Path(tree), "rev-parse", "--git-path", "hooks")
    if not hooks:
        return None
    path = pathlib.Path(hooks) / HOOK_NAME
    return path if path.is_absolute() else pathlib.Path(tree) / path


def arm_command(path: pathlib.Path) -> str:
    """The install command for `path`: the symlink where it would resolve.

    The symlink is relative to the hooks directory, so it lands in the checkout
    that owns `$GIT_COMMON_DIR` -- which may be on a branch without this hook.
    There the symlink is installed and inert, and a reader who followed the
    advice would be told green by `--check` and guarded by nothing. Where the
    target is absent, the advice is the copy, which works today.
    """
    target = path.parent / ".." / ".." / roots.ENGINE_REL / "checks" / HOOK_NAME
    if target.exists():
        return f"{ARM} {path}"
    return (f"cp {HOOK_FILE} {path} (a symlink would be inert: "
            f"{target.resolve()} does not exist yet)")


def installed(path: pathlib.Path) -> bool:
    """Whether `path` is an install of this hook -- by location, or by content.

    LOCATION, not identity, because the hook is a SHARED symlink: git resolves
    `$GIT_COMMON_DIR/hooks/pre-push`, so a linked worktree runs the MAIN
    checkout's copy of the script -- a different branch, and possibly a
    different revision of this file. That is deliberate and the script is
    written for it: whichever copy runs, it resolves the tree being pushed and
    runs THAT tree's guard.

    CONTENT as well, because a COPY is the one arming that works before the
    revision carrying this script reaches the checkout git resolves hooks from
    -- and a copy that has drifted from the committed body is a guard nobody
    can predict, so it is a finding rather than a pass.
    """
    real = path.resolve()
    if (real.name == HOOK_NAME and real.parent.name == "checks"
            and real.parent.parent.name == roots.ENGINE_REL):
        return True
    try:
        return path.read_bytes() == HOOK_FILE.read_bytes()
    except OSError:
        return False


def check(tree=None, p=None):
    """(ok, message): is the guard armed in the checkout being committed?

    Three answers, and the third is the one worth having: ARMED, NOT INSTALLED
    -- a failure where the private tree is -- and INSTALLED BUT INERT, which is
    what a symlink into a checkout that does not carry this branch resolves to.
    A guard that is inert is not a guard, and it is also not something the
    reader can fix, so it is reported as the state it is rather than as red.
    """
    tree = roots.REPO if tree is None else pathlib.Path(tree)
    private = (tree / PRIVATE_MARKER).is_dir()
    path = hook_path(tree)
    if path is None:
        return True, ("push-guard: git cannot name this checkout's hooks "
                      "directory, so there is no push to guard")
    if path.is_symlink() and not path.exists():
        return True, (f"push-guard: {path} points at {path.resolve()}, which does "
                      f"not exist -- the guard is INSTALLED AND INERT, and that "
                      f"is the state until the revision carrying "
                      f"{roots.ENGINE_REL}/checks/{HOOK_NAME} reaches the checkout "
                      f"git resolves this hook from")
    if path.exists():
        if not installed(path):
            return False, (f"push-guard: {path} exists and is not this guard, so "
                           f"nothing refuses a push to {public_owner(p)}/"
                           f"{PUBLIC_REPO}. Replace it: {arm_command(path)}")
        if not os.access(path, os.X_OK):
            return False, (f"push-guard: {path} is not executable, so git runs "
                           f"nothing: chmod +x {path.resolve()}")
        owner = public_owner(p)
        if not owner:
            return True, (f"push-guard: armed at {path}, and inert -- the profile "
                          f"in force declares no public handle (the shipped "
                          f"example names nobody), so there is no public "
                          f"repository for a push to be refused over")
        return True, (f"push-guard: armed at {path} -- a push to {owner}/"
                      f"{PUBLIC_REPO} from a checkout with `{PRIVATE_MARKER}/` "
                      f"is refused")
    if not private:
        return True, (f"push-guard: not installed, and not needed here -- "
                      f"{tree} has no `{PRIVATE_MARKER}/`, so nothing in it is "
                      f"private and a push from it publishes nothing extra")
    # Not installed, and this checkout is the private tree. Whether that is a
    # failure turns on one fact: which repository the remote names. Until the
    # rename and the `set-url`, the public name IS this repository, and arming
    # the guard then would refuse the push that is right -- so the state is
    # correct until the remote moves, and a gate that called it a failure would
    # teach its reader to ignore it.
    origin = git(tree, "remote", "get-url", "origin")
    if is_public(origin, p):
        return True, (f"push-guard: not installed, and correctly so -- `origin` "
                      f"is {origin}, which until the rename and the `remote "
                      f"set-url` is THIS repository. Arm it once origin names the "
                      f"private one: {arm_command(path)}")
    return False, (f"push-guard: NOT armed -- {tree} has a `{PRIVATE_MARKER}/` and "
                   f"its origin is {origin or 'unset'}, so a push to "
                   f"{public_owner(p)}/{PUBLIC_REPO} would publish the private tree "
                   f"and nothing would refuse it. Arm it: {arm_command(path)}")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="the remote URL being pushed to (the hook's "
                                  "second argument)")
    ap.add_argument("--tree", help="the checkout being pushed (default: this one)")
    ap.add_argument("--check", action="store_true",
                    help="report whether the guard is armed in this checkout")
    args = ap.parse_args(argv)
    tree = pathlib.Path(args.tree).resolve() if args.tree else roots.REPO

    if args.check:
        armed, message = check(tree)
        print(message)
        return 0 if armed else 1
    if args.url is None:
        print("push_guard: --url, or --check", file=sys.stderr)
        return 2
    reason = refuses(args.url, tree)
    if reason:
        print(f"push-guard: REFUSED -- {reason}", file=sys.stderr)
        return 1
    return 0                      # a hook is quiet when it has nothing to say


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
