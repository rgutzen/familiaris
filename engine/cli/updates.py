"""`familiar checks updates` -- what has a newer version than the one installed.

THE HOLE. `healthcheck.sh` reports pending pacman updates and nothing else.
Everything this system actually runs on was outside it: pi and the harness CLIs
(installed by mise), pi's extensions (npm, under `~/.pi/agent/npm`), and the
skills whose bodies live in a git clone of someone else's repository. None of
them has a `--check`, a timer, or a notice, so each is as old as the last time
a person remembered.

THREE SURFACES, and what updating each one costs afterwards:

  tools    `mise outdated` -- pi, claude, codex, opencode, gh. A harness upgrade
           can change what it sends to the model, so the harness checks are the
           re-verification: `context route`, `context loadout`,
           `orchestration models` (agrees with `pi --list-models`).
  pi       `npm outdated` in pi's package directory -- the extensions. pi's own
           guard and relay suites are the re-verification.
  skills   a skill whose body is `mode: link` is pinned to a commit of its
           upstream clone (`upstream_pin: owner/repo@sha`). The remote moving
           past the pin is the news; pulling it changes the bytes, which
           `familiar skills scan --check` reports as drift, and the skill is
           re-scanned and re-dispositioned before it is trusted again. The pull
           is the trigger of that re-audit, so this reports it and does not do it.

READ-ONLY, ALWAYS. This never installs, upgrades, pulls or fetches into a clone.
Applying an update is a judgement (what breaks, when to restart a session that
is running on the old binary) that an unattended run does not get to make --
the same line `healthcheck.sh` draws for pacman. Each finding prints the command
that applies it.

EXIT CODES. 0 nothing is behind. 3 something is behind (`--check`; without it,
0). 2 a surface could not be read -- offline, a tool missing. The registry marks
the entry advisory, so a red here is a warning to read, never a failed tier.

    familiar checks updates [--check] [--json] [--only tools|pi|skills]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

from lib import roots

TIMEOUT = 60
# The packages whose upgrade can change what a session sends or is allowed to
# do; the rest of `mise` is ordinary tooling and is reported as such.
HARNESSES = frozenset({"pi", "claude", "codex", "opencode", "gemini", "hermes"})
PI_DIR = pathlib.Path("~/.pi/agent/npm").expanduser()
SKILLS = roots.MEMORY / "skills"

AFTER = {
    "harness": "familiar context route --check; familiar context loadout --check; "
               "familiar orchestration models --check",
    "tool": "",
    "pi-package": f"python3 {roots.ENGINE_REL}/checks/checks.py --run pi-guard-node; "
                  f"python3 {roots.ENGINE_REL}/checks/checks.py --run pytest-relay",
    "skill": "familiar skills scan --check, then scan the changed skills and "
             "disposition any new HIGH before trusting them",
}


class Unreadable(RuntimeError):
    """A surface that could not be read: offline, or its tool is missing."""


def _run(cmd: list[str], cwd: pathlib.Path | None = None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=cwd, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Unreadable(f"{cmd[0]}: {exc}") from exc
    return r.stdout if r.returncode in (0, 1) else _fail(cmd, r)


def _fail(cmd: list[str], r: subprocess.CompletedProcess) -> str:
    raise Unreadable(f"{' '.join(cmd[:3])}: exit {r.returncode}: {r.stderr.strip()[:120]}")


def tools() -> list[dict]:
    """Installed tools that `mise` knows a newer version of."""
    out = _run(["mise", "outdated", "--json"]).strip()
    rows = []
    for name, v in sorted((json.loads(out) if out else {}).items()):
        kind = "harness" if name in HARNESSES else "tool"
        rows.append({"surface": "tools", "kind": kind, "name": name,
                     "have": v["current"], "latest": v["latest"],
                     "apply": f"mise upgrade {name}",
                     "after": AFTER[kind]})
    return rows


def pi_packages() -> list[dict]:
    """pi's installed extensions that npm knows a newer version of."""
    if not PI_DIR.is_dir():
        return []
    out = _run(["npm", "outdated", "--json"], cwd=PI_DIR).strip()
    return [{"surface": "pi", "kind": "pi-package", "name": name,
             "have": v["current"], "latest": v["latest"],
             "apply": f"pi update --extension npm:{name}", "after": AFTER["pi-package"]}
            for name, v in sorted((json.loads(out) if out else {}).items())]


def _frontmatter(path: pathlib.Path) -> dict:
    out = {}
    for line in path.read_text().splitlines()[1:]:
        if line == "---":
            break
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.split(" #")[0].strip()
    return out


def skill_upstreams() -> dict[pathlib.Path, dict]:
    """Each upstream clone the library links to: its pin, and the skills on it.

    A pin looks like `owner/repo@sha`. One that is not a git clone on this
    machine (`pacman package ...`, a path under /usr/share) is not this
    surface's: pacman reports it.
    """
    clones: dict[pathlib.Path, dict] = {}
    for md in sorted(SKILLS.glob("*/*/*/SKILL.md")):
        fm = _frontmatter(md)
        if fm.get("mode") != "link" or "@" not in fm.get("upstream_pin", ""):
            continue
        body = pathlib.Path(fm.get("upstream_path", "").replace("~", str(pathlib.Path.home())))
        try:
            top = _run(["git", "-C", str(body), "rev-parse", "--show-toplevel"]) \
                if body.exists() else ""
        except Unreadable:
            top = ""            # not a git checkout (a package's files): not this surface's
        if not top.strip():
            continue
        entry = clones.setdefault(pathlib.Path(top.strip()),
                                  {"pins": set(), "skills": []})
        entry["pins"].add(fm["upstream_pin"].split()[0].rpartition("@")[2])
        entry["skills"].append(md.parent.name)
    return clones


def skills() -> list[dict]:
    """Upstream clones whose remote head is not the commit the library pinned."""
    rows = []
    for clone, entry in sorted(skill_upstreams().items()):
        remote = _run(["git", "-C", str(clone), "ls-remote", "origin", "HEAD"]).split()
        if not remote:
            raise Unreadable(f"{clone.name}: the remote named no HEAD")
        head = remote[0]
        if any(head.startswith(pin) for pin in entry["pins"]):
            continue
        rows.append({"surface": "skills", "kind": "skill", "name": clone.name,
                     "have": "/".join(sorted(entry["pins"])), "latest": head[:7],
                     "skills": len(entry["skills"]),
                     "apply": f"git -C {clone} pull --ff-only   # then re-pin and re-scan",
                     "after": AFTER["skill"]})
    return rows


SURFACES = {"tools": tools, "pi": pi_packages, "skills": skills}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar checks updates", description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 3 when anything is behind")
    ap.add_argument("--json", action="store_true", help="one JSON object instead of the report")
    ap.add_argument("--only", choices=sorted(SURFACES), help="read one surface")
    args = ap.parse_args(argv)

    rows, unreadable = [], []
    for name, read in SURFACES.items():
        if args.only and name != args.only:
            continue
        try:
            rows += read()
        except Unreadable as exc:
            unreadable.append(f"{name}: {exc}")

    if args.json:
        print(json.dumps({"behind": rows, "unreadable": unreadable}, indent=1))
    else:
        for r in rows:
            extra = f" ({r['skills']} skills)" if "skills" in r else ""
            print(f"  behind  {r['surface']:<7}{r['name']:<28}{r['have']} -> {r['latest']}{extra}")
            print(f"            apply: {r['apply']}")
            if r["after"]:
                print(f"            then:  {r['after']}")
        for u in unreadable:
            print(f"  unread  {u}", file=sys.stderr)
        print(f"updates: {len(rows)} behind, {len(unreadable)} surface(s) unreadable. "
              "Nothing was applied.")
    if unreadable:
        return 2
    return 3 if args.check and rows else 0
