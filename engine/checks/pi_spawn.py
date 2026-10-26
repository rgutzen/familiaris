#!/usr/bin/env python3
"""No engine code builds a `pi` command line; it asks `harness/pi_call` (`memory/knowledge/system/harness/pi.md` §Starting a pi process).

WHY. `pi -p` reads a non-TTY stdin to EOF, so a child that inherits an open pipe
hangs. That was fixed by hand at six spawn sites in three commits, and a seventh
(`pi --list-models`) never got the fix. `harness/pi_call.py` is now the one place
a pi process starts. This gate keeps it the only one: a new caller that writes
its own `["pi", ...]` would rediscover every hazard the module already handles.

WHAT COUNTS. In Python under `engine/` (and the extensionless `pi-agent` script),
an argv literal whose first element is the string "pi": `["pi", ...]` or
`("pi", ...)`, in code or in a string's own source line.

WHAT IS EXEMPT, and why each:
  * `harness/pi_call.py` -- the module itself (it spells `PI`, but may spell more).
  * this file -- its prose spells the pattern it looks for.
  * tests -- a fake argv is data about what pi receives, not a spawn.
  * a line carrying `# pi-spawn: <reason>` -- a deliberate exception. The reason
    is mandatory, so the exemption is a decision on the record.

Usage:  pi_spawn.py [--list]     exit 1 on any finding
"""
from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from lib import roots  # noqa: E402

MODULE = roots.ENGINE / "harness" / "pi_call.py"
SCRIPTS = (roots.ENGINE / "orchestration" / "pi-agent",)   # Python with no `.py`
# `[` or `(` NOT preceded by a name or `)`/`]`: a literal, not a call such as
# `Result("pi", ...)` whose first argument merely names the harness.
ARGV = re.compile(r"""(?<![\w)\]])[\[(]\s*(["'])pi\1\s*,""")
MARK = re.compile(r"#\s*pi-spawn:\s*\S")


def _sources(engine: pathlib.Path):
    for path in sorted(engine.rglob("*.py")):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        if path.name.startswith("test_"):
            continue
        yield path
    for path in SCRIPTS:
        if path.is_file() and str(path).startswith(str(engine)):
            yield path


def findings(engine: pathlib.Path = roots.ENGINE, module: pathlib.Path = MODULE) -> list:
    out = []
    for path in _sources(engine):
        if path.resolve() in (module.resolve(), pathlib.Path(__file__).resolve()):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0] if not MARK.search(line) else ""
            if ARGV.search(code):
                out.append((path, n, line.strip()[:100]))
    return out


def main(argv=None) -> int:
    found = findings()
    for path, n, line in found:
        print(f"{roots.rel(path)}:{n}: {line}")
    print(f"pi spawn: {len(found)} finding(s) outside harness/pi_call.py"
          + ("" if not found else " -- build the argv with `pi_call.argv` and start it "
             "with `pi_call.run`/`spawn`, or mark the line `# pi-spawn: <reason>`"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
