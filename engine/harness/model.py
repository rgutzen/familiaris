"""model -- the one place the pass talks to a language model.

THE SEAM IS ONE KEY, in the file an install already edits:
`config/profile.yaml`'s `models.consolidation`, a pi `provider/model` id. Nothing
else in the tree names a model, so swapping one is a one-line edit with no code
change.

**The default is LOCAL, and that is a decision rather than an accident.**
`ollama/qwen3:4b` runs on the machine: nothing read into it leaves, and no
credential is needed, so a fresh clone can run a night end to end the day it is
cloned. The cost is real and stated here rather than discovered at 03:30 -- a
local model is slow (this machine's 4B runs at roughly 10 tokens/s, which will
not finish a night's transcripts before morning), so the pass distils what it can
and notes the rest. Swapping to a provider's model is what makes the night
complete and makes the transcripts disclosure: stage 1 sends session prose to
whatever `models.consolidation` names, and the pi credential decides whether the
call works at all. `memory/knowledge/system/consolidation/` is the leaf that owns
that trade-off; this module owns the id.

Routed through `pi --print --model <id>`, the pi harness one-shot mode. pi is the
default PAZRAS memory harness (2026-09-06), replacing opencode (tools/opencode.md)
as the routing path. The credential lives in pi (`pi auth check --provider <p>`);
this module never reads it, and the boundaries guard refuses that read anyway.

MODEL CHANGED 2026-09-29, `deepseek-v4-flash` -> `deepseek-flash`. Journal
entries written before that date carry the old name in `distilled_by:`, and that
is deliberate: a provenance string records when something happened and is never
rewritten when the thing it names is renamed (memory-architecture.md). The field
is read as a boolean -- "machine-distilled, unreviewed" -- not matched against
this constant.
"""
from __future__ import annotations

import os
import subprocess

from lib import roots

# The profile's `models.consolidation` (P1), so a second install picks its own
# model in the file it already edits. The fallback is LOCAL for the reason the
# docstring gives: a tree with no profile must not post a night's transcripts
# to a third party, and `ollama/qwen3:4b` is a tag anyone can pull. `--model` is
# passed to pi verbatim, so a provider swap is this string and nothing else --
# `harness/tests/test_model.py` holds the fallback to the boundaries' own
# `local_providers` list, which is what keeps it honest when one of the two
# moves.
DEFAULT_MODEL = "ollama/qwen3:4b"
MODEL = roots.PROFILE.models.get("consolidation") or DEFAULT_MODEL
TIMEOUT = 300


class ModelError(RuntimeError):
    pass


def available() -> bool:
    from shutil import which
    return which("pi") is not None


def ask(prompt: str, timeout: int = TIMEOUT) -> str:
    """One turn, no session state. Raises ModelError rather than returning junk."""
    if not available():
        raise ModelError("pi is not on PATH")
    try:
        # cwd matters: pi picks up project config from it. /tmp keeps the
        # call free of whatever repo the pass happens to be standing in.
        # --no-session: one turn, nothing persisted; --no-tools: no tool loop
        # (a pure LLM call, tools would only add latency and failure modes).
        r = subprocess.run(["pi", "--print", "--no-session", "--no-tools",
                            "--model", MODEL, prompt],
                           capture_output=True, text=True, timeout=timeout,
                           cwd="/tmp", env=dict(os.environ, NO_COLOR="1"))
    except subprocess.TimeoutExpired:
        raise ModelError(f"timed out after {timeout}s")
    except OSError as exc:
        raise ModelError(str(exc))
    if r.returncode != 0:
        raise ModelError((r.stderr or r.stdout).strip()[:300] or "non-zero exit")
    out = _strip_chrome(r.stdout)
    if not out.strip():
        raise ModelError("empty response")
    return out.strip()


def _strip_chrome(text: str) -> str:
    """pi --print writes only the answer to stdout; strip stray ANSI if any."""
    return _decolour(text)


def _decolour(s: str) -> str:
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
