"""jev -- the System One client: typed questions in, typed answers out.

STDLIB ONLY, BY POLICY. `journal_index.py` states the reason for the pass as a
whole and it binds harder here: this runs unattended at night, and a nightly job
needs *do not crash, try again tomorrow*, not a retry policy. `urllib` is enough
for one POST and one GET, and a dependency that can go missing at 03:00 is worth
less than forty lines of transport.

NO RETRY, DELIBERATELY. A 429 means the rate limit and a 529 means TypeSafe is
overloaded; both are `warn and skip`, because the pass's next run is twelve hours
away and a bounded backoff loop inside a nightly cron buys a slower failure, not
a success. A 401 or 422 is a NAMED ERROR and also a skip: a bad key or a
malformed question will be just as wrong tomorrow, and the report says so rather
than the pass dying. Every failure mode here is `JevError` with a `kind` the
caller records as a note.

THE KEY IS READ HERE AND NOWHERE ELSE. `~/.config/pazras/jev.env`, mode 600,
outside every repository. Steps 0b/0c put it there and `read-write.yaml` names it
so no *tool call* can read it; this module's own `open()` is the one read the
guard cannot see and the one it must permit -- a module cannot authenticate
without reading its credential. `load_key` checks the mode and refuses a
world-readable file rather than using it, because the mode IS the protection.

WHAT IS NOT HERE. No cost accounting beyond `input_tokens` (see `cost_usd`); no
question schemas (step 2c, and they are the ontology's, not this client's); no
band rule (2d). This module knows how to ask and how to report that it could not.

WHY THE MODEL IS PINNED. `MODEL` is the versioned id, never `jev-latest`. A
floated alias makes every logged probability uninterpretable through time
(PLAN.md §The record): a threshold calibrated against 1.13.0 means nothing once
the alias resolves to 1.14. The response's resolved `model` is returned alongside
the answers so the record can prove which one spoke.
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODELS_ENDPOINT = "https://api.typesafe.ai/v1/models"

# The versioned id. `jev-latest`/`jev-preview` resolve to it today; pinning means
# a resolution change cannot silently re-populate a calibration population.
MODEL = "jev-1.13.0"

# $ per million INPUT tokens. Output tokens are returned by the API and are free.
# Multiplying output_tokens by this rate would overstate cost (PLAN.md §The
# answer shapes).
USD_PER_MTOK_INPUT = 0.042

KEY_PATH = pathlib.Path(os.path.expanduser("~/.config/pazras/jev.env"))
KEY_VAR = "TYPESAFE_API_KEY"

TIMEOUT = 120

# Status classes, declared once. See the module docstring for why none retries.
SKIP_STATUSES = {
    401: "key rejected (401) — check the file at ~/.config/pazras/jev.env",
    422: "request rejected as invalid (422) — a question schema is malformed",
    429: "rate limited (429) — skipped, the next pass retries",
    529: "TypeSafe overloaded (529) — skipped, the next pass retries",
}


class JevError(RuntimeError):
    """A call that did not return usable answers. Never raised as a crash.

    `kind` is machine-readable (`no-key`, `bad-mode`, `key-rejected`,
    `invalid-request`, `rate-limited`, `overloaded`, `transport`, `bad-response`)
    so a caller records one note per kind instead of parsing prose. `fatal` is
    True only for the cases where trying again tomorrow cannot help differently:
    a missing or mis-moded key file, and a rejected key.
    """

    def __init__(self, kind: str, message: str, *, fatal: bool = False):
        super().__init__(message)
        self.kind = kind
        self.fatal = fatal


def load_key(path: pathlib.Path | None = None) -> str:
    """Read the bearer token, refusing anything but a mode-600 file.

    The mode check is not decoration. The file's protection is that only its
    owner can read it; a 644 key is readable by every local user and by anything
    that walks the home directory, and using it anyway would report success while
    the credential is already exposed.
    """
    p = pathlib.Path(path) if path else KEY_PATH
    try:
        st = p.stat()
    except OSError:
        raise JevError("no-key", f"no key file at {p} — see dev/jev/SPECS.md "
                                 f"step 0b", fatal=True) from None
    if not stat.S_ISREG(st.st_mode):
        raise JevError("bad-mode", f"{p} is not a regular file", fatal=True)
    mode = stat.S_IMODE(st.st_mode)
    if mode & 0o077:
        raise JevError("bad-mode", f"{p} is mode {mode:o}, expected 600 — "
                                   f"`chmod 600 {p}`", fatal=True)
    text = p.read_text()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, value = line.partition("=")
        if name.strip() == KEY_VAR:
            value = value.strip().strip("'\"")
            if not value:
                raise JevError("no-key", f"{KEY_VAR} is empty in {p}", fatal=True)
            return value
    raise JevError("no-key", f"{KEY_VAR} not found in {p}", fatal=True)


def _request(url: str, key: str, payload: dict | None = None,
             timeout: int = TIMEOUT) -> dict:
    """One request, one answer. Every failure becomes a JevError with a kind."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        detail = ""
        try:
            detail = exc.read().decode()[:300]
        except Exception:
            pass
        known = SKIP_STATUSES.get(status)
        if status in (401, 422):
            raise JevError("key-rejected" if status == 401 else "invalid-request",
                           f"{known} — {detail}".strip(" —"), fatal=True) from None
        if status in (429, 529):
            raise JevError("rate-limited" if status == 429 else "overloaded",
                           known) from None
        raise JevError("transport", f"HTTP {status}: {detail[:200]}") from None
    except urllib.error.URLError as exc:
        raise JevError("transport", f"could not reach {url}: {exc.reason}") from None
    except (TimeoutError, OSError) as exc:
        raise JevError("transport", f"{type(exc).__name__}: {exc}") from None
    try:
        return json.loads(body)
    except ValueError:
        raise JevError("bad-response", f"response was not JSON: {body[:200]}") from None


def ask(state, questions: dict, *, key: str | None = None,
        model: str = MODEL, timeout: int = TIMEOUT) -> dict:
    """One System One call. Returns the raw parsed response.

    `questions` is the caller's map of id -> question object; ids are the
    caller's and come back unchanged. Raises `JevError`; never returns a partial
    answer, because a caller that cannot tell "no answer" from "an empty answer"
    would record a decision nobody made.
    """
    if not questions:
        raise JevError("invalid-request", "questions must not be empty", fatal=True)
    token = key or load_key()
    out = _request(ENDPOINT, token,
                   {"state": state, "model": model, "questions": questions},
                   timeout=timeout)
    if not isinstance(out, dict) or not isinstance(out.get("answers"), dict):
        raise JevError("bad-response", f"no `answers` map in {json.dumps(out)[:200]}")
    return out


def models(*, key: str | None = None, timeout: int = TIMEOUT) -> dict:
    """`GET /v1/models` -- what this key may call. This closes step 0d.

    The one call in this module whose purpose is to prove something about the
    ACCOUNT rather than to answer a question, and therefore the only one that
    cannot be exercised against a mirror.
    """
    return _request(MODELS_ENDPOINT, key or load_key(), timeout=timeout)


def cost_usd(usage: dict) -> float:
    """Input tokens only. Output tokens are free (PLAN.md §The answer shapes)."""
    return round(int(usage.get("input_tokens", 0)) / 1_000_000 * USD_PER_MTOK_INPUT, 6)


def answer_fields(answer: dict) -> dict:
    """The recordable part of one answer, shaped to what the API actually returns.

    A `noul` is a single 0-1 number with NO `confidence` and no `probabilities`;
    `choice` and `score` carry both. Returning `confidence: None` for a Noul is
    correct -- a number there would be invented (PLAN.md §The answer shapes).
    """
    kind = answer.get("type")
    if kind == "noul":
        return {"type": "noul", "probability": answer.get("noul"),
                "probabilities": None, "confidence": None}
    if kind == "choice":
        return {"type": "choice", "choice": answer.get("choice"),
                "probabilities": answer.get("probabilities"),
                "confidence": answer.get("confidence")}
    if kind == "score":
        return {"type": "score", "score": answer.get("score"),
                "probabilities": answer.get("probabilities"),
                "confidence": answer.get("confidence")}
    return {"type": kind, "raw": answer}
