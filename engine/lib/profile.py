#!/usr/bin/env python3
"""profile.py -- the one reading of `config/profile.yaml`, for Python and bash.

WHY. Before P1 the facts that make this tree one person's install were spelled
where they were first needed: the install root in `roots.py`
(`$HOME/06_SYSTEM`), the PARA root as `$HOME` in every line of
`structure/pazras.sh`, the Areas in `pazras-master-config.sh`, the archive disk
and the restic paths beside them, the embedding model in `journal_index.py`.
A second person standing the system up had to find all of them. The profile
names them once, and the example profile is what the public tree ships.

WHICH FILE. `$PAZRAS_PROFILE` if set, else `config/profile.yaml` (the
instance's, never published), else `config/profile.example.yaml` (shipped). So
a fresh clone runs on the example until its owner copies it.

TWO OVERRIDES, by environment, because they are the two a scratch run needs:
`PARA_ROOT` moves the PARA tree and `PAZRAS_INSTALL` moves the install. Both
beat the file -- `PARA_ROOT=/tmp/x familiar structure init` must not touch
`$HOME`, whatever the profile says.

ONE PARSER, TWO CONSUMERS. bash does not parse YAML; it evaluates what
`profile.py --sh` prints (`roots.sh`, `pazras-config-loader.sh`). A second
reader in awk would be the drift this module exists to remove.

NEVER RAISES AT IMPORT. `roots.py` reads the profile and the boundary guard
imports `roots` on every tool call, so a typo in the profile must not become a
hook that fails open. `resolve()` returns the defaults with `problems` filled
in; `--check` and `familiar structure validate` are where a broken profile is
loud.

Stdlib only, and imports nothing outside `lib` (R1j).
"""
from __future__ import annotations

import dataclasses
import os
import pathlib
import shlex
import sys

try:
    from lib import _miniyaml
except ImportError:            # run as a script: `python3 engine/lib/profile.py`
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from lib import _miniyaml

NAME = "profile.yaml"
EXAMPLE = "profile.example.yaml"

# What a profile that says nothing means. The install keeps the name the PARA
# convention gives the system folder, so an install that never wrote a profile
# behaves exactly as it did before P1.
DEFAULT_INSTALL = "~/06_SYSTEM"
DEFAULT_PARA_ROOT = "~"

AREA_KEYS = ("code", "tag", "description")
KNOWN = ("version", "install", "para_root", "identity", "areas", "storage", "models")


@dataclasses.dataclass
class Profile:
    source: pathlib.Path | None
    install: pathlib.Path
    para_root: pathlib.Path
    identity: dict
    areas: dict                    # {"A_Science": {"code", "tag", "description"}}
    storage: dict
    models: dict
    problems: list


def _expand(value: str) -> pathlib.Path:
    return pathlib.Path(os.path.expanduser(os.path.expandvars(value)))


def locate(config: pathlib.Path) -> pathlib.Path | None:
    """The profile file in force, or None when neither file exists."""
    env = os.environ.get("PAZRAS_PROFILE")
    if env:
        return _expand(env)
    for name in (NAME, EXAMPLE):
        if (config / name).is_file():
            return config / name
    return None


def _validate(data: dict) -> list:
    problems = []
    for key in data:
        if key not in KNOWN:
            problems.append(f"unknown key {key!r} (known: {', '.join(KNOWN)})")
    for key in ("identity", "storage", "models"):
        if data.get(key) is not None and not isinstance(data[key], dict):
            problems.append(f"{key}: must be a mapping")
    areas = data.get("areas") or {}
    if not isinstance(areas, dict):
        return problems + ["areas: must be a mapping of Area name to its fields"]
    codes = {}
    for name, fields in areas.items():
        if not isinstance(fields, dict):
            problems.append(f"areas.{name}: must be a mapping with {', '.join(AREA_KEYS)}")
            continue
        missing = [k for k in AREA_KEYS if not fields.get(k)]
        if missing:
            problems.append(f"areas.{name}: missing {', '.join(missing)}")
        code = fields.get("code", "")
        if code in codes:
            problems.append(f"areas.{name}: code {code!r} already used by {codes[code]}")
        codes[code] = name
    return problems


def resolve(config: pathlib.Path) -> Profile:
    """The profile in force, with the environment overrides applied."""
    source = locate(config)
    data, problems = {}, []
    if source is None:
        problems.append(f"no profile: neither {config / NAME} nor {config / EXAMPLE} exists")
    else:
        try:
            data = _miniyaml.load(source.read_text())
        except (OSError, _miniyaml.YamlError) as exc:
            problems.append(f"{source}: {exc}")
        problems += _validate(data)
    if problems:
        data = {}

    def section(key):
        value = data.get(key)
        return value if isinstance(value, dict) else {}

    install = os.environ.get("PAZRAS_INSTALL") or data.get("install") or DEFAULT_INSTALL
    para = os.environ.get("PARA_ROOT") or data.get("para_root") or DEFAULT_PARA_ROOT
    return Profile(source=source, install=_expand(install), para_root=_expand(para),
                   identity=section("identity"), areas=section("areas"),
                   storage={k: str(_expand(v)) if k.endswith(("_root", "_file", "_mount"))
                            else v for k, v in section("storage").items()},
                   models=section("models"), problems=problems)


# ── the identity, and what a placeholder is ──────────────────────────────────
#
# `identity:` was parsed and unread until P2. What reads it now is code that
# SEARCHES for the owner of this install -- the `instance-refs` gate, which
# fails when generic engine code names a person, and the push guard, which
# needs the public forge handle. Both wanted the same two facts and neither
# should spell them, so they are read here.


def placeholders(p: Profile) -> frozenset:
    """The identity values that name NOBODY: the example profile's own.

    `config/profile.example.yaml` ships `Your Name` / `your-handle`, so a fresh
    clone's identity is a caption rather than a person. A reader that searches
    for the identity has to tell the two apart, or a pattern containing `Name`
    matches every `class Name` in the tree and measures the tree's length: the
    gate is then worse than absent, because it is loud and meaningless. So the
    example's own values -- whole and split into words -- are excluded here,
    once, rather than at each reader.

    Read from the file beside the profile in force, not from today's wording
    copied here: an install that copied the example and never edited it is
    exactly the case this must catch, and a second copy of the placeholder
    strings is a definition that drifts from the file it defines.
    """
    if p.source is None:
        return frozenset()
    path = p.source.parent / EXAMPLE
    if not path.is_file():
        return frozenset()
    try:
        data = _miniyaml.load(path.read_text())
    except (OSError, _miniyaml.YamlError):
        return frozenset()
    identity = data.get("identity") if isinstance(data, dict) else None
    if not isinstance(identity, dict):
        return frozenset()
    out = set()
    for value in identity.values():
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
            out.update(value.split())
    return frozenset(out)


def identity_words(p: Profile) -> list:
    """The words that name this install's owner: `name` split, then `handle`.

    The order is the profile's, so a reader that builds one pattern from this
    can print it back in the order it was declared. Case is kept, because a
    search for a name is a search for its spelling -- and the words that only
    fill in the shipped example are dropped, so the example contributes
    nothing and an unedited copy of it measures nothing (see `placeholders`).
    """
    skip = placeholders(p)
    out: list = []
    for key in ("name", "handle"):
        value = p.identity.get(key)
        if not isinstance(value, str):
            continue
        for word in value.split():
            if word not in skip and word not in out:
                out.append(word)
    return out


# ── the shell side ───────────────────────────────────────────────────────────

def shell(p: Profile, what: str) -> str:
    """bash assignments for `what`: `roots` (scalars only, for `roots.sh`) or
    `structure` (the Areas and the storage, for the config loader).

    ONE STORAGE VALUE TRAVELS IN `roots`, and the exception is deliberate:
    `PAZRAS_STORAGE_REMOTE` -- which provider adapter the off-site half loads.
    `roots.sh` runs before the config loader exists in every script, and
    `engine/backup/mirror.sh` never loads the master config at all, so a
    selector that read it from the `structure` section resolved to nothing
    wherever the loader had not run. Measured 2026-10-15: `backup sync` on the
    real install fell back to the `example` adapter and skipped its upload
    while exiting 0. The warning it logged is the only reason it was noticed,
    and it is the reason that warning exists."""
    q = shlex.quote
    if what == "roots":
        lines = [f"PAZRAS_INSTALL={q(str(p.install))}",
                 f"PARA_ROOT={q(str(p.para_root))}",
                 f"PAZRAS_PROFILE_FILE={q(str(p.source or ''))}",
                 f"PAZRAS_PROFILE_PROBLEMS={len(p.problems)}",
                 f"PAZRAS_STORAGE_REMOTE={q(str(p.storage.get('remote') or 'example'))}"]
        return "\n".join(lines) + "\n"
    if what == "structure":
        # The master config's own field order, `tag:description:code`, so
        # `get_area_code` and `get_area_description` read the profile's Areas
        # without a change.
        rows = " ".join(f"[{q(name)}]={q(':'.join((f['tag'], f['description'], f['code'])))}"
                        for name, f in sorted(p.areas.items()))
        lines = [f"declare -gA AREAS=({rows})"]
        for key, value in sorted(p.storage.items()):
            lines.append(f"PAZRAS_STORAGE_{key.upper()}={q(str(value))}")
        return "\n".join(lines) + "\n"
    raise ValueError(f"unknown section {what!r}: roots | structure")


def main(argv: list) -> int:
    # `roots` names the config directory and has already resolved the profile;
    # imported here, not at the top, because `roots` imports this module.
    from lib import roots
    p = roots.PROFILE
    if argv[:1] == ["--sh"]:
        sys.stdout.write(shell(p, argv[1] if len(argv) > 1 else "roots"))
        return 0
    if argv[:1] == ["--check"]:
        for problem in p.problems:
            print(f"profile: {problem}", file=sys.stderr)
        if not p.problems:
            print(f"profile: {p.source} -- {len(p.areas)} Areas, "
                  f"install {p.install}, PARA root {p.para_root}")
        return 1 if p.problems else 0
    print("usage: profile.py --check | --sh [roots|structure]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
