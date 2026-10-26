"""pi_call -- the one place a `pi` process is started (`memory/knowledge/system/harness/pi.md` §Starting a pi process).

WHY ONE PLACE. `pi -p` reads a non-TTY stdin to EOF, so a child that inherits an
open pipe hangs until its timeout. That was fixed by hand at six spawn sites in
three commits (7d19ade, de8df4e, 342c4ef), and `pi --list-models` never got the
fix. Every hazard of that kind is now fixed here, once, for every caller.

WHAT THIS MODULE ALWAYS DOES, and no caller can switch off:
  * stdin is /dev/null;
  * `NO_COLOR=1` is in the child's environment, and `answer` strips stray ANSI;
  * `pi` not starting (absent from PATH, not executable) raises `PiError`.

WHAT THE CALLER MUST STATE, with no default, because callers genuinely differ:
  * `approve` -- pi's `--approve` (TRUST project-local files) or `--no-approve`
    (ignore them). An unattended child cannot answer a trust prompt, so most
    callers say False; a scheduled session in its own checkout says True. Not
    to be confused with permission asks, which this flag does not touch.
  * `session` -- `None` (pi's `--no-session`: nothing persisted) or a
    `Session(dir, id)` whose log the caller reads afterwards.

WHAT THE CALLER MAY STATE: the model, a system prompt (which REPLACES pi's),
`bare` (`-nc -ns`: no AGENTS.md/CLAUDE.md, no skills index), the tool allowlist,
the thinking level, the cwd (default /tmp, so pi picks up no project config),
extra environment, output destinations, and `wrap` -- a transform applied to the
argv just before the spawn, which is how `eval` puts a cell under bubblewrap
while the spawn itself stays here.

TWO LEVELS, because the callers want two things:
  * `run` reports. A non-zero exit is a returncode and a timeout is 124 -- the
    convention `pi-agent`, `sessions` and `eval` already record -- because those
    callers keep a record of a failed run rather than abandoning it.
  * `popen` starts the bidirectional side: `pi --mode rpc`, whose stdin carries
    the prompt and the answers to the dialogs it raises (`argv_rpc` builds its
    command line). Its clock belongs to the caller; see `spawn` on timeouts.
  * `answer` and `list_models` judge. A timeout, a non-zero exit or an empty
    answer each raise `PiError`, because their callers want text or nothing.

THE SEAM FOR TESTS is the executable itself: `PI` is looked up on PATH at call
time, so a test puts a fake `pi` first on PATH and observes what a real child
would see (`tests/test_pi_call.py`). No caller needs a mock parameter.
"""
from __future__ import annotations

import dataclasses
import os
import pathlib
import subprocess
from typing import Callable, Mapping, Sequence

PI = "pi"
TIMEOUT = 300
TIMED_OUT = 124          # the exit code a timeout reports, as `timeout(1)` does
LIST_TIMEOUT = 30

Wrap = Callable[[list, pathlib.Path], list]


class PiError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Session:
    """Where pi keeps this call's log: `--session-dir dir --session-id id`."""
    dir: pathlib.Path
    id: str


@dataclasses.dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def timed_out(self) -> bool:
        return self.returncode == TIMED_OUT


def argv(task: str, *, approve: bool, session: Session | None, model: str | None = None,
         system_prompt: str | os.PathLike | None = None, bare: bool = False,
         tools: Sequence[str] | None = None, thinking: str | None = None) -> list:
    """The `pi -p` command line. `tools=None` leaves pi's default set, `()` is
    `--no-tools`, a sequence is the allowlist."""
    out = [PI, "-p", task]
    if system_prompt is not None:
        out += ["--system-prompt", str(system_prompt)]
    if bare:
        out += ["-nc", "-ns"]
    if tools is not None:
        out += ["--tools", ",".join(tools)] if tools else ["--no-tools"]
    if model:
        out += ["--model", model]
    if thinking:
        out += ["--thinking", thinking]
    if session is None:
        out.append("--no-session")
    else:
        out += ["--session-dir", str(session.dir), "--session-id", session.id]
    out.append("--approve" if approve else "--no-approve")
    return out


def argv_rpc(*, approve: bool, session: Session | None, model: str | None = None,
             thinking: str | None = None, extensions: Sequence[str | os.PathLike] = ()) -> list:
    """The `pi --mode rpc` command line (the converse a scheduler drives, dev/remote R2a).

    RPC differs from `-p` in what stdin is FOR: the prompt and the dialog answers
    travel on it, so this mode is started by `popen`, not `spawn`. `extensions`
    are `-e PATH` tools a scheduled run needs and an interactive session does
    not (`ask_user`)."""
    out = [PI, "--mode", "rpc"]
    if model:
        out += ["--model", model]
    if thinking:
        out += ["--thinking", thinking]
    if session is None:
        out.append("--no-session")
    else:
        out += ["--session-dir", str(session.dir), "--session-id", session.id]
    out.append("--approve" if approve else "--no-approve")
    for ext in extensions:
        out += ["-e", str(ext)]
    return out


def env_for(extra: Mapping[str, str] | None = None, base: Mapping[str, str] | None = None) -> dict:
    """The child's environment: `base` (this process's by default), then `extra`,
    then what the module always sets."""
    env = dict(os.environ if base is None else base)
    env.update(extra or {})
    env["NO_COLOR"] = "1"
    return env


def spawn(cmd: Sequence[str], *, cwd: str | os.PathLike = "/tmp",
          env: Mapping[str, str] | None = None, timeout: float | None = TIMEOUT,
          wrap: Wrap | None = None, stdout=subprocess.PIPE, stderr=subprocess.PIPE) -> Result:
    """Start `cmd` (an argv beginning with `pi`) and report how it ended.

    `stdout`/`stderr` take what `subprocess.run` takes: PIPE (captured into the
    Result), a file object, `subprocess.STDOUT`, or None to inherit."""
    cmd = list(cmd)
    if wrap is not None:
        cmd = list(wrap(cmd, pathlib.Path(cwd)))
    try:
        p = subprocess.run(cmd, cwd=str(cwd), env=env_for(base=env),
                           timeout=timeout, stdin=subprocess.DEVNULL,
                           stdout=stdout, stderr=stderr, text=True, check=False)
    except subprocess.TimeoutExpired as exc:
        return Result(TIMED_OUT, _text(exc.stdout), _text(exc.stderr))
    except OSError as exc:
        raise PiError(f"{cmd[0]}: {exc}") from exc
    return Result(p.returncode, p.stdout or "", p.stderr or "")


def popen(cmd: Sequence[str], *, cwd: str | os.PathLike = "/tmp",
          env: Mapping[str, str] | None = None, wrap: Wrap | None = None):
    """Start a BIDIRECTIONAL `pi` (RPC mode) and hand back the process.

    `stdin`, `stdout` and `stderr` are pipes because the protocol needs all
    three; `NO_COLOR` and the `PiError` on a pi that does not start are the same
    as in `spawn`. There is no timeout here: an RPC run's clock belongs to its
    driver, which alone knows how long the owner spent answering (rpc.py)."""
    cmd = list(cmd)
    if wrap is not None:
        cmd = list(wrap(cmd, pathlib.Path(cwd)))
    try:
        return subprocess.Popen(cmd, cwd=str(cwd), env=env_for(base=env),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
    except OSError as exc:
        raise PiError(f"{cmd[0]}: {exc}") from exc


def run(task: str, *, approve: bool, session: Session | None, env_extra=None,
        cwd: str | os.PathLike = "/tmp", timeout: float | None = TIMEOUT,
        wrap: Wrap | None = None, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **flags) -> Result:
    """`argv(...)` then `spawn(...)`: one prompt, reported. `flags` are `argv`'s
    optional keywords (model, system_prompt, bare, tools, thinking)."""
    return spawn(argv(task, approve=approve, session=session, **flags),
                 cwd=cwd, env=env_for(env_extra), timeout=timeout, wrap=wrap,
                 stdout=stdout, stderr=stderr)


def answer(task: str, *, approve: bool, session: Session | None, timeout: float = TIMEOUT,
           **kw) -> str:
    """One prompt, judged: the answer's text, or `PiError`."""
    r = run(task, approve=approve, session=session, timeout=timeout, **kw)
    if r.timed_out:
        raise PiError(f"timed out after {timeout}s")
    if r.returncode != 0:
        raise PiError((r.stderr or r.stdout).strip()[:300] or f"exit {r.returncode}")
    out = decolour(r.stdout).strip()
    if not out:
        raise PiError("empty response")
    return out


def list_models(timeout: float = LIST_TIMEOUT) -> str:
    """`pi --list-models`, judged: its table as text, or `PiError`."""
    r = spawn([PI, "--list-models"], timeout=timeout)
    if r.timed_out:
        raise PiError(f"pi --list-models timed out after {timeout}s")
    if r.returncode != 0:
        raise PiError(f"pi --list-models exited {r.returncode}: {r.stderr.strip()}")
    return decolour(r.stdout)


def decolour(s: str) -> str:
    """Strip ANSI escape sequences (CSI ... m / K)."""
    out, i = [], 0
    while i < len(s):
        if s[i] == "\x1b":
            j = i + 1
            while j < len(s) and s[j] not in "mK":
                j += 1
            i = j + 1
            continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _text(b) -> str:
    if b is None:
        return ""
    return b.decode(errors="replace") if isinstance(b, bytes) else b
