"""client -- how a session talks to the relay: a blocking ask that survives restarts (R1a).

`ask` does not return until the owner answers or the ask is withdrawn, however
long that takes (decision 3). A relay that is down or restarting is waited for:
the client reconnects with the SAME ask id, and the relay answers a re-ask with
the open ask (no second message) or with the answer it stored while the client
was gone.
"""
from __future__ import annotations

import json
import os
import pathlib
import socket
import time

SOCK_NAME = "familiar-relay.sock"


def sock_path(env=os.environ) -> pathlib.Path:
    if env.get("FAMILIAR_RELAY_SOCK"):
        return pathlib.Path(env["FAMILIAR_RELAY_SOCK"])
    runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return pathlib.Path(runtime) / SOCK_NAME


class RelayDown(ConnectionError):
    """The relay's socket does not answer."""


def _connect(path: pathlib.Path, timeout: float | None) -> socket.socket:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(path))
    except OSError as e:
        s.close()
        raise RelayDown(f"{path}: {e.strerror or e}") from None
    return s


def _lines(s: socket.socket):
    buf = b""
    while True:
        chunk = s.recv(65536)
        if not chunk:
            raise RelayDown("the relay closed the connection")
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                yield json.loads(line)


def request(obj: dict, *, env=os.environ, timeout: float = 10) -> dict:
    """One request, one reply: withdraw, notify, status."""
    with _connect(sock_path(env), timeout) as s:
        s.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        return next(_lines(s))


def annotate(ask_id: str, lines: list, *, env=os.environ, timeout: float = 5) -> bool:
    """Attach the two lines to an ask the owner may already be reading.

    Best effort by design: the lines help a decision, they never condition the
    ask, so a relay that is down costs the lines and nothing else.
    """
    try:
        reply = request({"op": "annotate", "id": ask_id, "lines": list(lines)}, env=env,
                        timeout=timeout)
    except (RelayDown, OSError):
        return False
    return bool(reply.get("annotated"))


def ask(req: dict, *, env=os.environ, retry=5.0, sleep=time.sleep,
        on_retry=lambda err: None) -> dict:
    """Send an ask and block until its answer; reconnect forever with the same id.

    Raises:
        ValueError: The relay refused the request itself (a malformed ask).
    """
    req = {**req, "op": "ask"}
    while True:
        try:
            with _connect(sock_path(env), None) as s:
                s.sendall((json.dumps(req, ensure_ascii=False) + "\n").encode())
                for msg in _lines(s):
                    if msg.get("op") == "answer" and msg.get("id") == req["id"]:
                        return msg
                    if msg.get("ok") is False:
                        raise ValueError(msg.get("error", "refused"))
        except (RelayDown, OSError) as e:
            on_retry(e)
            sleep(retry)
