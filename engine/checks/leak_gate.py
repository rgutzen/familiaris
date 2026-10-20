#!/usr/bin/env python3
"""leak_gate.py -- personal data meets a PUBLIC destination exactly once, and is refused.

WHAT IT GUARDS. `publish_scan.py` scans a tree `publish.py` wrote, in a workflow
that has a human reading a diff. This gate guards the other road out: any
commit or push, from any checkout, whose DESTINATION turns out to be publicly
visible. The pattern set is the same one -- one scanner, two ways in -- and so is
the declared-versus-undeclared rule.

WHY THE DESTINATION DECIDES (the question that chose `pre-push`). "Must not be
public" is not a property of a file, it is a property of a file AT A
DESTINATION. The same commit to a private repository is the private tree working
as designed -- it holds the journal, the user's practice files and this
machine's own paths on purpose. So a gate that fired on the private tree would
be noise, and a gate that fired on the commit would fire before anyone knows
where it is going. `git push` is the first moment both halves are in one place:
git hands the hook the URL AND the refs. Hence: pre-push is the gate, and the
visibility question is asked about the URL, never about the tree.

ONLY A PUBLIC DESTINATION IS SCANNED AT ALL. `private` and `unknown` return
before a single blob is read. This checkout is one of those: the private
instance has nothing to refuse, and the gate belongs to the publication track
-- it exists for the clone a publish writes and for any other checkout whose
destination turns out to be public. `--check` reports the state rather than
arming it here, and `publish.py` arms the clone.

ADVISORY UNLESS THE CHECKOUT SAYS OTHERWISE. A finding is printed, with the
blobs and the lines, and the push proceeds. A gate that stops an unhurried push
is a gate the reader learns to bypass, and this is a personal system: the walk
past has to be deliberate, not impossible. Deliberate is what `git config
pazras.leak-gate strict` buys -- that checkout refuses (exit 1) and names
`-c pazras.leak-gate=warn push` as the way through. `--strict` and `--advisory`
set the stance for one run.

WHY A `--staged` MODE STILL EXISTS. In a checkout whose own origin is public --
the publish clone, if its owner wants it -- every commit is public-bound, and
catching it before the object exists is strictly better than catching it on the
way out (a commit can be pushed by another tool, another day, another harness).
Same scanner, one ref instead of a URL. It is available, not armed for you.

WHEN THE ANSWER CANNOT BE RESOLVED, NOTHING IS REPORTED. `gh` (or the anonymous
API) is asked whether the destination is private; `git config pazras.visibility
public|private` pins the answer when the probe cannot be reached. Offline,
unauthenticated against a host that is not GitHub, and rate-limited all resolve
to `unknown`, and an unknown destination is not a public one -- so it is not
scanned, not warned about, and not refused. A hook that nags about a question it
could not ask is the noise this rule exists to keep out. `--verbose` says what
was skipped.

WHAT THE REFUSAL IS NOT. It is not a secret scanner in the credential sense.
`.gitignore` deny-lists and `read-write.yaml` own that; the built-in patterns
here (a key, a token, a passphrase assignment) are the shapes that
would be wrong in any tree, and they are refused here for the same reason as
the rest. It is also not a judgement about a name: the dotfiles repository
publishes the user's own name and machine paths deliberately, and a personal
name that no declaration covers is a QUESTION ("should this travel?"), which is
exactly what the declaration file is for.

DECLARED VERSUS UNDECLARED. A hit is cleared by a declaration in the register
`publish_scan` reads (`config/publication/leak-exceptions.txt`) when the scanned
paths are that export's. A repository that is not the export carries both halves
of its own answer in `.pazras/`: `leak-patterns.txt` (the names that must not
travel FROM THERE, in the register's `name<TAB>regex` format) and
`leak-allow.txt` (the rows a declaration file has:
`path<TAB>pattern<TAB>count<TAB>reason`). One parser each, so the decision is
visible in the repository it is about.

Usage:
    python3 engine/checks/leak_gate.py --url <remote-url> [--tree DIR]   # reads git's pre-push refs on stdin
    python3 engine/checks/leak_gate.py --staged [--tree DIR]             # a pre-commit in a public checkout
    python3 engine/checks/leak_gate.py --check [--tree DIR]              # is the gate armed here, and where is the destination
    python3 engine/checks/leak_gate.py --arm  [--tree DIR]               # write the pre-push hook into this checkout
Flags that change the stance: --strict, --advisory, --verbose, --quiet.
Exit codes: 0 allow (advisory mode always), 1 refuse (strict mode), 2 usage.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import publish_scan as ps  # noqa: E402
from lib import roots  # noqa: E402

PUBLIC, PRIVATE, UNKNOWN = "public", "private", "unknown"

# The forge this gate can ask. A remote on another host is not scanned as if it
# were GitHub's -- reading a `host:owner/repo` as a pair would report an answer
# about some other site's repository.
GITHUB_HOSTS = ("github.com",)
PROBE_TIMEOUT = 8          # a push can wait for an answer
CHECK_TIMEOUT = 4          # a commit must not
HOOK_NAME = "pre-push"
ZERO = "0" * 40
MAX_BLOB = 2 * 1024 * 1024      # a scan is a regex pass; a bigger file is a finding in itself

# git's own variables, cleared before running git: in a hook `GIT_DIR` points at
# the repository's git directory rather than the working tree being pushed, and
# `rev-parse` would then answer about the wrong checkout. `checks.py` clears the
# same five for its children, for the same reason.
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX",
                "GIT_COMMON_DIR")

SCP = re.compile(r"^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")
URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]+@)?(?P<host>[^:/]+)(?::\d+)?/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")


@dataclasses.dataclass
class Blob:
    path: str
    text: str


# ── the destination ──────────────────────────────────────────────────────────

def forge_pair(url: str):
    """`(host, owner, repo)` for a forge remote, or None.

    Three spellings reach one repository -- ssh, https, and the `scp` form git
    writes -- and all three are read here. A local path is not a forge, which is
    why the test suite's fake remote never has to touch the network.
    """
    if not url:
        return None
    url = url.strip().rstrip("/")
    m = SCP.match(url) or URL.match(url)
    if m is None:
        return None
    return (m.group("host").lower(), m.group("owner").lower(),
            m.group("repo").lower())


def _github_probe(owner: str, repo: str, timeout: int = PROBE_TIMEOUT) -> tuple[str, str]:
    """(`public`|`private`|`unknown`, evidence). Never raises, never hangs long.

    `gh` first, because it answers for private repositories too and the answer is
    the user's own authenticated view. The anonymous API second, which answers
    for a public repository (200) and not for a private one (404).
    """
    if shutil.which("gh"):
        try:
            done = subprocess.run(("gh", "api", f"repos/{owner}/{repo}",
                                   "--jq", ".private"),
                                  capture_output=True, text=True, timeout=timeout)
            if done.returncode == 0:
                answer = done.stdout.strip().lower()
                if answer in ("true", "false"):
                    return ((PRIVATE if answer == "true" else PUBLIC),
                            f"gh says private={answer}")
        except (OSError, subprocess.SubprocessError):
            pass
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "familiar-leak-gate"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
        if data.get("private") is True:
            return PRIVATE, "the anonymous API says private"
        if data.get("private") is False:
            return PUBLIC, "the anonymous API says public"
        return UNKNOWN, "the API answered without a visibility field"
    except urllib.error.HTTPError as err:
        # 404 is what a private repository looks like to a caller with no
        # credentials. It is also what a typo looks like; both mean this gate
        # cannot see the repository, and neither is a reason to refuse a push.
        if err.code == 404:
            return PRIVATE, "the anonymous API returns 404 (private, or no such repository)"
        return UNKNOWN, f"the API answered {err.code}"
    except (OSError, ValueError, urllib.error.URLError) as err:
        return UNKNOWN, f"no answer from the API ({err.__class__.__name__})"


def visibility(url: str, tree=None, pin: str | None = None,
               probe=_github_probe, timeout: int = PROBE_TIMEOUT) -> tuple[str, str]:
    """(`public`|`private`|`unknown`, evidence) for a destination URL."""
    if pin:
        return pin, "pinned"
    pair = forge_pair(url)
    if pair is None:
        return UNKNOWN, ("the destination is not a remote this gate reads "
                         "(a local path, or a host that is not GitHub)")
    host, owner, repo = pair
    if host not in GITHUB_HOSTS:
        return UNKNOWN, f"{host} is not a host this gate can ask about"
    return probe(owner, repo, timeout)


ADVISORY, STRICT = "warn", "strict"


def mode(tree) -> str:
    """The checkout's stance: `warn` (the default) or `strict` (refuse).

    A git config value rather than a flag, because the hook has no command line
    of its own -- `git config pazras.leak-gate strict` is how a checkout that
    wants the hard gate says so, and it travels with the clone.
    """
    value = git(tree, "config", "--get", "pazras.leak-gate").strip().lower()
    return STRICT if value == STRICT else ADVISORY


def pinned(tree) -> str | None:
    """`pazras.visibility`, when the checkout sets one."""
    value = git(tree, "config", "--get", "pazras.visibility").strip().lower()
    return value if value in (PUBLIC, PRIVATE) else None


# ── what is leaving ──────────────────────────────────────────────────────────

def git(tree, *args: str) -> str:
    """`git <args>` in `tree`, or "" when git cannot answer."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    try:
        done = subprocess.run(("git",) + args, cwd=str(tree), env=env,
                              capture_output=True, text=True)
    except OSError:
        return ""
    return done.stdout if done.returncode == 0 else ""


def pushed_refs(text: str) -> list[tuple[str, str]]:
    """`(local sha, remote sha)` per ref git offers on the hook's stdin.

    git's format is `<local ref> <local sha> <remote ref> <remote sha>`; a
    deletion carries an all-zero local sha and has nothing to scan.
    """
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] != ZERO:
            out.append((parts[1], parts[3]))
    return out


def _batch(tree, format: str, shas: list[str]) -> str:
    """One `git cat-file` for many objects, text in and text out."""
    if not shas:
        return ""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    try:
        done = subprocess.run(("git", "cat-file", format), cwd=str(tree), env=env,
                              input="\n".join(shas) + "\n",
                              capture_output=True, text=True)
    except OSError:
        return ""
    return done.stdout if done.returncode == 0 else ""


def range_objects(tree, local: str, remote: str) -> list[tuple[str, str]]:
    """`(path, blob sha)` for every blob a ref update PUBLISHES.

    TWO QUESTIONS, TWO GIT QUERIES, and both are needed:

    * the OBJECT WALK (`rev-list --objects remote..local`) is what the remote's
      object store gains. It includes a blob that a later commit replaced -- so
      a first push of a branch that once carried a leak catches it even though
      the tip tree is clean, because the pack still carries those bytes.
    * the TIP TREE (`ls-tree -r local`) says which path each object sits at. A
      path is what a declaration is keyed on, and rev-list names each object
      once: two identical files would arrive as one path, and a declaration
      covering that path would speak for the other one.

    So the walk decides WHAT is published, and the tree decides WHERE. An object
    the tip no longer carries keeps the path history recorded it under -- the
    message should name the file the reader would edit.

    An all-zero remote (a new branch, the first push of a clone) has no common
    history, so the range is everything the local ref carries.
    """
    rng = f"{local}^{{commit}}" if remote == ZERO else f"{remote}^{{commit}}..{local}^{{commit}}"
    listing = git(tree, "rev-list", "--objects", rng)
    if not listing:
        return []
    shas = [line.split(maxsplit=1)[0] for line in listing.splitlines() if line.strip()]
    sizes = _batch(tree, "--batch-check=%(objecttype) %(objectname) %(objectsize)", shas)
    keep = []
    for line in sizes.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "blob" and fields[2].isdigit() \
                and int(fields[2]) <= MAX_BLOB:
            keep.append(fields[1])
    if not keep:
        return []
    # Where the tip carries the object, its paths are the truth; where it does
    # not (replaced or deleted later in the range), the walk's name is all there
    # is, and it is better than nothing.
    tip: dict[str, list[str]] = {}
    for entry in git(tree, "ls-tree", "-r", "-z", f"{local}^{{commit}}").split("\0"):
        if entry and "\t" in entry:
            meta, path = entry.split("\t", 1)
            fields = meta.split()
            if len(fields) >= 3:
                tip.setdefault(fields[2], []).append(path)
    walked: dict[str, list[str]] = {}
    for line in listing.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            walked.setdefault(parts[0], []).append(parts[1])
    out = []
    for sha in keep:
        for path in tip.get(sha, walked.get(sha, [])):
            out.append((path, sha))
    return out


def staged_objects(tree) -> list[tuple[str, str]]:
    """`(path, blob sha)` for the index -- the tree a commit would write.

    The whole index, deliberately: after `git add -p` or `git commit <paths>`,
    the index IS what is being committed, and the working tree is not.
    """
    listing = git(tree, "ls-files", "--stage", "-z")
    if not listing:
        return []
    out = []
    for entry in listing.split("\0"):
        if not entry or "\t" not in entry:
            continue
        meta, path = entry.split("\t", 1)
        fields = meta.split()
        if len(fields) >= 3 and fields[2] == "0":      # stage 0: no conflict
            out.append((path, fields[1]))
    return out


def blobs(tree, objects: list[tuple[str, str]]) -> list[Blob]:
    """Read the objects' contents, skipping what is not text.

    One blob may be several paths -- git stores content, not filenames, and two
    identical files are one object. Every path is reported, deliberately: a
    declaration covers a PATH, so collapsing the paths would let a declared copy
    speak for an undeclared one.
    """
    if not objects:
        return []
    # One streamed `--batch` for every object: it is the only way to read many
    # blobs without a process per file, and it carries the size in its header.
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
    wanted: dict[str, list[str]] = {}
    for path, sha in objects:
        wanted.setdefault(sha, []).append(path)
    try:
        done = subprocess.run(("git", "cat-file", "--batch"), cwd=str(tree), env=env,
                              input=("\n".join(wanted) + "\n").encode(),
                              capture_output=True)
    except OSError:
        return []
    if done.returncode != 0:
        return []
    out: list[Blob] = []
    data, pos = done.stdout, 0
    while pos < len(data):
        header, _, rest = data[pos:].partition(b"\n")
        pos = pos + len(header) + 1
        fields = header.split()
        if len(fields) < 3 or fields[1] != b"blob":
            break
        size = int(fields[2])
        raw, pos = rest[:size], pos + size + 1        # +1: the object's own newline
        paths = wanted.get(fields[0].decode("ascii", "replace"))
        if not paths or len(raw) > MAX_BLOB or b"\0" in raw[:8192]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        out.extend(Blob(path, text) for path in paths)
    return out


# ── the register ─────────────────────────────────────────────────────────────

def register_for(tree) -> list:
    """The declarations that apply to `tree`.

    The export's register always applies: `publish_scan` reads it from this
    install, and a publish clone's paths are the export's paths. A repository
    that is not the export carries its own decisions, in the same row format, so
    the answer travels with the repository it is about.
    """
    out = ps.declarations()
    local = pathlib.Path(tree) / ".pazras" / "leak-allow.txt"
    if local.exists():
        out = out + ps.declarations(local)
    return out


def as_declared(hits: list, decls: list) -> list:
    """The register as a DELTA scan can honestly read it.

    A declaration's count is a measurement of a whole tree (`publish_scan
    --tree`), and this gate scans a push or an index -- a fraction of one. Set
    against a delta, the count is wrong in both directions: a declaration whose
    file is not in THIS push would read as stale, and the count check would
    refuse a hit that the register does cover. So a delta asks the one question
    it can answer -- is this (path, pattern) declared at all -- and the counts
    stay the tree scan's business.
    """
    counted: dict = {}
    for h in hits:
        counted[(h.path, h.name)] = counted.get((h.path, h.name), 0) + 1
    out = []
    for d in decls:
        n = counted.get((d.path, d.name), 0)
        if n:
            out.append(dataclasses.replace(d, count=n))
    return out


# ── the gate ─────────────────────────────────────────────────────────────────

def scan_objects(tree, objects: list[tuple[str, str]]) -> tuple[list, list[str]]:
    """(hits, notes) for a set of `(path, blob sha)` -- the one scan path."""
    read = blobs(tree, objects)
    hits = ps.scan_texts([(b.path, b.text) for b in read], patterns(tree))
    notes = []
    if len(read) < len({sha for _, sha in objects}):
        notes.append(f"{len({sha for _, sha in objects}) - len(read)} object(s) "
                     f"skipped: not text, or larger than this gate reads")
    return hits, notes


def verdict(destination: str, answer: str, evidence: str, hits: list,
            tree, advice: str, strict: bool = False) -> tuple[bool, str]:
    """(block, message). `block` is what the mode decides to do about it.

    The hits are listed ONCE, and the findings behind them are summarised by
    their advice rather than repeated per occurrence: forty copies of "no
    declaration covers this" bury the one sentence that says what to do.

    ADVISORY UNLESS THE CHECKOUT SAYS OTHERWISE. `block` is only ever True in
    `strict` mode; the caller exits 1 on it. In the default mode the same
    findings are printed as a WARNING and the push proceeds -- a personal
    system's gate is a thing the reader must be able to walk past deliberately,
    and a gate that stops an unhurried push at 02:00 is a gate that gets
    --no-verify in its own defence. What the mode changes is the LAST sentence:
    advisory names how to make it strict, strict names how to proceed anyway.
    """
    if answer in (PRIVATE, UNKNOWN):
        # Only a PUBLIC destination is scanned at all: the private tree is
        # SUPPOSED to hold this, and an unresolved destination is not known to
        # be public. `--verbose` reports what was skipped.
        return False, ""
    if not hits:
        return False, ""
    problems, _ = ps.findings(tree, hits, as_declared(hits, register_for(tree)),
                              advice=advice)
    if not problems:
        # Declared, and the declaration covers exactly what was found -- a
        # declaration is a measurement, and this one still measures.
        return False, ""
    shown = "\n".join(f"  {h.path}:{h.line}: {h.name}: {h.text!r}" for h in hits[:40])
    more = f"\n  ... and {len(hits) - 40} more" if len(hits) > 40 else ""
    reasons: dict[str, int] = {}
    for p in problems:
        reason = p.split(" -- ", 1)[1] if " -- " in p else p
        reasons[reason] = reasons.get(reason, 0) + 1
    body = "\n".join(f"  {n} occurrence(s): {reason}"
                     for reason, n in reasons.items())
    head = "REFUSED" if strict else "WARN"
    tail = (f"  This checkout is STRICT (pazras.leak-gate = strict), so the push "
            f"is stopped. To proceed: git -c pazras.leak-gate=warn push, or "
            f"--no-verify." if strict else
            f"  The push is NOT stopped -- this is advisory. Make it strict with "
            f"`git config pazras.leak-gate strict`, which refuses instead.")
    return strict, (f"leak-gate: {head} -- {destination} is PUBLIC ({evidence}) "
                    f"and this would put {len(problems)} undeclared hit(s) in "
                    f"it:\n{shown}{more}\n{body}\n{tail}")


def hook_path(tree) -> pathlib.Path | None:
    hooks = git(tree, "rev-parse", "--git-path", "hooks").strip()
    if not hooks:
        return None
    path = pathlib.Path(hooks) / HOOK_NAME
    return path if path.is_absolute() else pathlib.Path(tree) / path


def hook_body() -> str:
    """The body `--arm` writes: the tree is resolved at push time.

    The engine path is baked in because a foreign checkout has no `engine/` to
    find it in; the tree is not, because the same clone may be renamed or moved
    and the hook must follow it. `GIT_DIR` is cleared for the reason the
    registry clears it: with the hook's own environment, `rev-parse` answers
    about the checkout git resolves hooks from, not the one being pushed.
    """
    return f"""#!/usr/bin/env bash
# written by {roots.ENGINE_REL}/checks/leak_gate.py --arm -- regenerate, do not edit.
set -euo pipefail
refs="$(cat)"
REPO_TREE="$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE -u GIT_PREFIX \\
    -u GIT_COMMON_DIR git rev-parse --show-toplevel)"
exec python3 {HERE / 'leak_gate.py'} --tree "$REPO_TREE" --url "${{2:-}}" --quiet <<<"$refs"
"""


def armed(path: pathlib.Path) -> bool:
    """Whether `path` is an install of this gate (by content, not identity)."""
    try:
        return (path.read_text().find("leak_gate.py") >= 0
                and os.access(path, os.X_OK))
    except OSError:
        return False


def register_path(tree=None) -> pathlib.Path:
    """The pattern register that applies to `tree`.

    A repository that is not this instance carries its own names in
    `.pazras/leak-patterns.txt`, in the same row format (`name<TAB>regex`), and
    when it does, THAT is its register: the decision about what may travel
    belongs in the repository it is about. A tree without one -- this checkout,
    the export clone -- reads the install's register, which is the set the
    publication survey measured.

    A function rather than a constant because the test suite must be able to
    point it at a file that exists: in the EXPORT, `dev/` is omitted by design.
    """
    if tree is not None:
        local = pathlib.Path(tree) / ".pazras" / "leak-patterns.txt"
        if local.exists():
            return local
    return ps.PATTERN_FILE


def patterns(tree=None) -> list[tuple]:
    """The built-in shapes plus the register's -- `publish_scan`'s one set."""
    return ps.patterns(register_path(tree))


def arm(tree, register: pathlib.Path | None = None) -> pathlib.Path:
    """Write the pre-push hook into `tree`'s hooks directory, and return it.

    The register must be readable by the engine that writes the hook: a hook
    baked from an EXPORT's copy of this file would run `patterns()` in the
    export, where the private pattern file is omitted by design, and fail closed
    on every push. So the arming refuses to be done by a copy that cannot see
    the register -- `publish.py` calls this from the private install, and the
    path it bakes is the install's.
    """
    register = register_path(tree) if register is None else pathlib.Path(register)
    if not register.exists():
        raise SystemExit(
            f"leak-gate: {ps.spell(register)} does not exist, so the engine "
            f"that would be baked into the hook cannot read the patterns. Arm "
            f"from the install that holds the register, not from an export.")
    path = hook_path(tree)
    if path is None:
        raise SystemExit(f"leak-gate: git cannot name {tree}'s hooks directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(hook_body())
    path.chmod(0o755)
    return path


def check(tree=None, probe=_github_probe, timeout: int = CHECK_TIMEOUT):
    """(ok, message): is the gate armed where it is needed, and is the origin public?

    The rule is the visibility of the ORIGIN: where the origin is public, an
    unarmed checkout is a failure, because every commit there is public-bound
    and nothing else would refuse it. Where the origin is private -- this
    repository, until the rename -- not being armed is the correct state, and
    the message says so rather than leaving the reader to infer it.
    """
    tree = roots.REPO if tree is None else pathlib.Path(tree)
    path = hook_path(tree)
    origin = git(tree, "remote", "get-url", "origin").strip()
    answer, evidence = visibility(origin, tree, pinned(tree), probe, timeout)
    arm = f"python3 {roots.ENGINE_REL}/checks/leak_gate.py --arm"
    if path is None:
        return True, "leak-gate: git cannot name this checkout's hooks directory"
    if armed(path):
        stance = mode(tree)
        return True, (f"leak-gate: armed at {path} ({stance}) -- a push from "
                      f"{tree} to a public destination is scanned and "
                      f"{'refused' if stance == STRICT else 'reported'}")
    if answer == PUBLIC:
        return False, (f"leak-gate: NOT armed -- {path} is missing (or is not "
                       f"this gate), and `origin` is {origin}, which is PUBLIC "
                       f"({evidence}). Every push from here is public-bound. "
                       f"Arm it: {arm}")
    return True, (f"leak-gate: not armed, and correctly so here -- `origin` is "
                  f"{origin or 'unset'} ({answer}: {evidence}), so this "
                  f"checkout is not the public instance the gate is for. The "
                  f"clone a publish writes is armed by publish.py; to arm a "
                  f"checkout by hand: {arm}")


# ── cli ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="the destination being pushed to (the hook's "
                                  "second argument); the refs come on stdin")
    ap.add_argument("--tree", help="the checkout being pushed (default: this one)")
    ap.add_argument("--staged", action="store_true",
                    help="scan the index instead of a push (a pre-commit in a "
                         "public checkout)")
    ap.add_argument("--check", action="store_true",
                    help="report whether the gate is armed here and whether the "
                         "origin is public")
    ap.add_argument("--arm", action="store_true",
                    help="write the pre-push hook into this checkout")
    ap.add_argument("--visibility", choices=(PUBLIC, PRIVATE),
                    help="pin the answer for this run (the offline escape hatch)")
    ap.add_argument("--strict", action="store_true",
                    help="refuse instead of warning (exit 1)")
    ap.add_argument("--advisory", action="store_true",
                    help="warn and allow, whatever the checkout's mode says")
    ap.add_argument("--quiet", action="store_true",
                    help="print nothing at all for a destination that is not "
                         "public; a warning is still printed")
    ap.add_argument("--verbose", action="store_true",
                    help="say what was skipped, and what was scanned")
    args = ap.parse_args(argv)

    tree = pathlib.Path(args.tree).expanduser().resolve() if args.tree else roots.REPO

    if args.check:
        ok, message = check(tree)
        print(message)
        return 0 if ok else 1

    if args.arm:
        path = arm(tree)
        local = pathlib.Path(tree) / ".pazras" / "leak-patterns.txt"
        register = (local if local.exists()
                    else f"{ps.spell(ps.PATTERN_FILE)} (this tree carries no "
                         f".pazras/leak-patterns.txt of its own)")
        print(f"leak-gate: armed at {path} -- every push from {tree} is scanned "
              f"against {register} when the destination is public")
        return 0

    strict = args.strict or (not args.advisory and mode(tree) == STRICT)
    pin = args.visibility or pinned(tree)

    if args.staged:
        # A commit has no destination, so the origin is the destination being
        # asked about: a checkout whose origin is public is public-bound.
        origin = git(tree, "remote", "get-url", "origin").strip()
        answer, evidence = visibility(origin, tree, pin, _github_probe, CHECK_TIMEOUT)
        destination = f"the origin of {tree} ({origin or 'unset'})"
        objects = staged_objects(tree)
        advice = (f"fix the file, or declare the residue in "
                  f"{pathlib.Path(tree) / '.pazras' / 'leak-allow.txt'} with its "
                  f"count and the reason (a push is a delta, so the count is not "
                  f"read against it)")
    else:
        if args.url is None:
            print("leak-gate: --url, or --staged, or --check, or --arm",
                  file=sys.stderr)
            return 2
        answer, evidence = visibility(args.url, tree, pin, _github_probe, PROBE_TIMEOUT)
        destination = args.url
        refs = pushed_refs(sys.stdin.read())
        objects = []
        for local, remote in refs:
            objects.extend(range_objects(tree, local, remote))
        advice = (f"fix the file, or declare the residue in "
                  f"{pathlib.Path(tree) / '.pazras' / 'leak-allow.txt'}, or in "
                  f"{ps.EXCEPTION_FILE} if this tree is the export")

    hits, notes = scan_objects(tree, objects)
    block, message = verdict(destination, answer, evidence, hits, tree, advice, strict)
    # STDERR, always: a git hook's stdout may be swallowed by the caller, and a
    # warning nobody sees is not a warning.
    if message:
        print(message, file=sys.stderr)
    if args.verbose:
        print(f"leak-gate: {destination}: {answer} ({evidence}); "
              f"{len(objects)} object(s), {len(hits)} hit(s), "
              f"{'strict' if strict else 'advisory'}", file=sys.stderr)
        for note in notes:
            print(f"  note {note}", file=sys.stderr)
    return 1 if block else 0


if __name__ == "__main__":
    sys.exit(main())
