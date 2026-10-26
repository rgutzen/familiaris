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

from harness import pi_call
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


# `pi_call`'s error, under the name the pass's stages already catch.
ModelError = pi_call.PiError


def available() -> bool:
    from shutil import which
    return which(pi_call.PI) is not None


def ask(prompt: str, timeout: int = TIMEOUT) -> str:
    """One turn, no session state. Raises ModelError rather than returning junk.

    Spawned through `pi_call` (pi.md §Starting a pi process), which owns stdin, NO_COLOR,
    the cwd default (/tmp, so the call picks up no project config) and the error
    mapping. What is chosen HERE: no tools (a pure LLM call; tools would only add
    latency and failure modes), no session, and no project trust."""
    if not available():
        raise ModelError("pi is not on PATH")
    return pi_call.answer(prompt, approve=False, session=None, model=MODEL,
                          tools=(), timeout=timeout)
