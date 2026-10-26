"""commands -- the bot's /commands beyond the built-ins, declared in relay.yaml (R5a).

WHY A REGISTRY. The relay is standard library and is used BY the scheduler; the
commands the phone wants (the jobs, the brief, the tracks' todos) belong to other
subjects. Importing them here would couple one always-on service to every
subject, so each subject prints its own phone-sized text from a `familiar` verb
and the relay runs a DECLARED argv (`dev/remote/2026-10-21-commands.md`).

THE RULES, each one a test:

* The argv is fixed in config (a directive). The message supplies the words after
  the command; they must match the command's `arg` pattern WHOLE, and replace the
  `{args}` element as separate argv elements -- never a shell, never a string the
  shell would split.
* A command without `arg` takes nothing; trailing words are refused, not dropped.
* Output is redacted and cut like an ask's text, and every run is audited.
* `confirm: true` (for a command that destroys, `/cancel`) asks Yes/No first.
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
import subprocess
import time

from lib import roots

NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
TIERS = ("read", "control")
ARGS = "{args}"


class CommandError(ValueError):
    """A registry entry that cannot be used, or a message that does not fit it."""


@dataclasses.dataclass(frozen=True)
class Command:
    name: str
    help: str
    run: tuple
    arg: str = ""
    usage: str = ""
    tier: str = "read"
    confirm: bool = False


def load(raw: dict | None) -> dict:
    """The registry from `relay.yaml`'s `commands:` mapping. Raises on a bad entry:
    a relay that silently dropped a declared command would lie in `/help`."""
    out = {}
    for name, entry in (raw or {}).items():
        if not NAME.match(str(name)):
            raise CommandError(f"commands.{name}: a name is lower-case letters, digits, _")
        if not isinstance(entry, dict) or not isinstance(entry.get("run"), list) \
                or not entry["run"]:
            raise CommandError(f"commands.{name}: needs a `run:` block list (the argv)")
        tier = str(entry.get("tier") or "read")
        if tier not in TIERS:
            raise CommandError(f"commands.{name}: tier {tier!r}, one of {', '.join(TIERS)}")
        arg = str(entry.get("arg") or "")
        if arg:
            re.compile(arg)
        if ARGS in entry["run"] and not arg:
            raise CommandError(f"commands.{name}: `{ARGS}` in run needs an `arg` pattern")
        out[str(name)] = Command(name=str(name), help=" ".join(str(entry.get("help") or "").split()),
                                 run=tuple(str(a) for a in entry["run"]), arg=arg,
                                 usage=str(entry.get("usage") or ""), tier=tier,
                                 confirm=str(entry.get("confirm") or "false") == "true")
    return out


def argv(cmd: Command, rest: str, *, base: pathlib.Path | None = None) -> list:
    """The argv for `/name rest`. Raises CommandError with the usage when it does not fit."""
    rest = " ".join((rest or "").split())
    if cmd.arg:
        if not re.fullmatch(cmd.arg, rest):
            raise CommandError(f"usage: /{cmd.name} {cmd.usage}".rstrip())
    elif rest:
        raise CommandError(f"/{cmd.name} takes no argument")
    out = []
    for a in cmd.run:
        if a == ARGS:
            out += rest.split()
        else:
            out.append(a)
    head = pathlib.Path(out[0]).expanduser()
    if not head.is_absolute():
        head = (base or roots.REPO) / head
    return [str(head)] + out[1:]


def execute(cmd_argv: list, *, timeout: float, cwd: pathlib.Path | None = None) -> tuple:
    """(exit, text, seconds). A timeout or a missing program is an exit, not a raise."""
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd_argv, capture_output=True, text=True, timeout=timeout,
                           cwd=str(cwd or roots.REPO))
        code, text = p.returncode, (p.stdout or "").strip()
        if code and p.stderr.strip():
            text = (text + "\n" + p.stderr.strip()).strip()
    except subprocess.TimeoutExpired:
        code, text = 124, f"(no answer within {timeout:g} s)"
    except OSError as e:
        code, text = 127, f"(could not run: {e})"
    return code, text, round(time.monotonic() - t0, 2)


def telegram_list(builtin: dict, registry: dict) -> list:
    """`setMyCommands`' payload: the built-ins, then the registry, each with its help."""
    rows = [{"command": n, "description": h[:256]} for n, h in builtin.items()]
    rows += [{"command": c.name, "description": (c.help or c.name)[:256]}
             for c in registry.values() if c.name not in builtin]
    return rows
