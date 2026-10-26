"""redact -- no secret reaches Telegram's servers (R1b).

Telegram bot chats are not end-to-end encrypted (dev/remote/PLAN.md decision
1), so everything the relay sends -- an ask's title, its `More` context, a note
-- passes through `redact` first, and so does every audit line. The patterns
are the publication scanner's own (`lib.secrets.BUILTIN`: vendor tokens,
private keys, the restic passphrase), so the two gates cannot disagree about
what a secret looks like, plus the shapes a COMMAND LINE carries and a
file does not: an assignment to a secret-named variable, an Authorization
header, a Telegram bot token.

What it does not catch -- a secret with no recognisable shape or name -- is the
residue the `More` button and the edit-after-answer layer narrow, not close.
"""
from __future__ import annotations

import re

from lib.secrets import BUILTIN

MASK = "<redacted>"
_SHAPES = [re.compile(rx) for name, rx, _ in BUILTIN
           if name in ("token", "private-key", "restic-passphrase")]
_SHAPES += [
    # A Telegram bot token. Not `\b`: in a URL it follows `/bot` with no boundary.
    re.compile(r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{30,}"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),    # an Authorization value
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}"),
]
#: `API_KEY=...`, `export GITHUB_TOKEN="..."`, `--password=...`, `"secret": "..."`
_NAMED = re.compile(
    r"(?i)(\b[\w-]*(?:token|secret|passw(?:or)?d|api[_-]?key|access[_-]?key|private[_-]?key)"
    r"[\w-]*[\"']?\s*[:=]\s*)([\"']?)([^\s\"']{4,})\2")


def redact(text: str) -> str:
    if not text:
        return text
    text = _NAMED.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}{m.group(2)}", text)
    for rx in _SHAPES:
        text = rx.sub(MASK, text)
    return text
