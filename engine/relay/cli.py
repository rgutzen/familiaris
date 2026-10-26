"""cli -- `familiar relay serve | status | ask | notify | withdraw` (R1a).

EXIT CODES. 0 ok. 1 usage. 2 refused (no token, a malformed ask, a relay that
is not running for a verb that needs it). 3 `status --check` found the relay
down, unpaired, or not polling.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import time
import uuid

from lib import _miniyaml, roots
from relay import client
from relay.core import PAIR_TTL_S, Relay, new_pair_code
from relay.server import Server
from relay.telegram import Bot, BotError, load_token

CONFIG = roots.RELAY_CONFIG
#: `status --check` calls the poller stale after this long without a successful getUpdates.
STALE_POLL_S = 180


def load_config(path: pathlib.Path = CONFIG) -> dict:
    return (_miniyaml.load(path.read_text(encoding="utf-8")) or {}).get("defaults") or {}


def load_commands(path: pathlib.Path = CONFIG) -> dict:
    """The command registry (R5a); a bad entry stops `serve` with its reason."""
    from relay import commands                               # noqa: PLC0415
    return commands.load((_miniyaml.load(path.read_text(encoding="utf-8")) or {}).get("commands"))


def state_dir(env=os.environ) -> pathlib.Path:
    return roots.data_root(env) / "relay"


def cmd_serve(args, env=os.environ) -> int:
    cfg = load_config()
    token_file = pathlib.Path(env.get("FAMILIAR_RELAY_TOKEN_FILE")
                              or cfg.get("token_file") or "").expanduser()
    try:
        token = load_token(token_file)
    except BotError as e:
        print(f"relay: {e.description}", file=sys.stderr)
        return 2
    loose = token_file.stat().st_mode & 0o077
    if loose:
        print(f"relay: {token_file} is readable beyond its owner (mode "
              f"{token_file.stat().st_mode & 0o777:o}); `chmod 600` it first", file=sys.stderr)
        return 2
    relay = Relay(Bot(token), state_dir(env), cfg, commands=load_commands())
    relay.register_commands()
    server = Server(relay, client.sock_path(env), poll_timeout=int(cfg.get("poll_timeout") or 50))
    print(f"relay: serving {client.sock_path(env)}; owner "
          f"{'paired' if relay.owner else 'NOT paired'}; {len(relay.pending)} open ask(s)",
          flush=True)
    code = asyncio.run(server.run(relay.bot))
    if server.fatal:
        print(f"relay: {server.fatal}", file=sys.stderr)
    return code


def cmd_status(args, env=os.environ) -> int:
    try:
        st = client.request({"op": "status"}, env=env)
    except client.RelayDown as e:
        print(f"relay: not running ({e})", file=sys.stderr)
        return 3 if args.check else 2
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        poll = st.get("poll") or {}
        age = (f"{time.time() - poll['ok_ts']:.0f}s ago" if poll.get("ok_ts") else "never")
        print(f"owner    {'paired' if st['owner'] else 'NOT paired'}"
              f"{'; PAUSED by ' + st['paused'] if st.get('paused') else ''}")
        print(f"poll     last ok {age}{'; error: ' + poll['error'] if poll.get('error') else ''}")
        print(f"asks     {st['pending']} open ({st['unsent']} unsent); outbox {st['outbox']}")
        for a in st.get("asks", []):
            print(f"  {a['id']}  [{a['session']}] {a['kind']}  open {a['age_s']}s"
                  f"{'' if a['sent'] else '  (unsent)'}")
    if args.check:
        poll = st.get("poll") or {}
        fresh = poll.get("ok_ts") and time.time() - poll["ok_ts"] < STALE_POLL_S
        return 0 if st["owner"] and fresh else 3
    return 0


def cmd_ask(args, env=os.environ) -> int:
    req = {"id": args.id or f"cli-{uuid.uuid4().hex[:12]}", "session": args.session,
           "kind": args.kind, "title": args.title, "options": args.option or [],
           "context": args.context or ""}
    try:
        answer = client.ask(req, env=env, on_retry=lambda e: print(
            f"relay: waiting for the relay ({e})", file=sys.stderr))
    except ValueError as e:
        print(f"relay: {e}", file=sys.stderr)
        return 2
    print(json.dumps(answer, ensure_ascii=False))
    return 0


def cmd_pair(args, env=os.environ) -> int:
    """Writes the code's hash beside the relay's state; the running relay reads it on
    `/pair`. The code is printed here and nowhere else."""
    code = new_pair_code(state_dir(env))
    print(f"From the Telegram account that should answer, send the bot:\n\n"
          f"    /pair {code}\n\nValid {PAIR_TTL_S // 60} minutes, once. A new pairing "
          f"replaces the current owner, who is told.")
    return 0


def _toggle(op: str, env) -> int:
    try:
        r = client.request({"op": op}, env=env)
    except client.RelayDown as e:
        print(f"relay: not running ({e})", file=sys.stderr)
        return 2
    print(f"paused: {r.get('paused') or 'no'}")
    return 0 if r.get("ok") else 2


def cmd_pause(args, env=os.environ) -> int:
    return _toggle("pause", env)


def cmd_resume(args, env=os.environ) -> int:
    return _toggle("resume", env)


def cmd_notify(args, env=os.environ) -> int:
    try:
        client.request({"op": "notify", "session": args.session, "text": args.text}, env=env)
    except client.RelayDown as e:
        print(f"relay: not running ({e})", file=sys.stderr)
        return 2
    return 0


def cmd_withdraw(args, env=os.environ) -> int:
    try:
        r = client.request({"op": "withdraw", "id": args.id, "reason": args.reason}, env=env)
    except client.RelayDown as e:
        print(f"relay: not running ({e})", file=sys.stderr)
        return 2
    print("withdrawn" if r.get("withdrawn") else "no open ask with that id")
    return 0 if r.get("withdrawn") else 2


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="familiar relay",
                                 description="The phone channel: one Telegram poller and "
                                             "the socket sessions ask through.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve", help="run the relay (what the user unit runs)")
    st = sub.add_parser("status", help="the poller, the owner and the open asks")
    st.add_argument("--check", action="store_true", help="exit 3 unless paired and polling")
    st.add_argument("--json", action="store_true")
    ak = sub.add_parser("ask", help="ask the owner and wait for the answer (a manual test)")
    ak.add_argument("--session", default="cli")
    ak.add_argument("--kind", choices=("select", "confirm", "input"), default="select")
    ak.add_argument("--title", required=True)
    ak.add_argument("--option", action="append", help="repeat for each option")
    ak.add_argument("--context", help="what `More` shows")
    ak.add_argument("--id", help="re-ask an open ask by its id")
    sub.add_parser("pair", help="print a one-time code; /pair <code> from the phone")
    sub.add_parser("pause", help="hold every ask and refuse every tap (only the machine resumes)")
    sub.add_parser("resume", help="lift a pause")
    nt = sub.add_parser("notify", help="send the owner a note")
    nt.add_argument("--session", default="cli")
    nt.add_argument("text")
    wd = sub.add_parser("withdraw", help="close an open ask without an answer")
    wd.add_argument("id")
    wd.add_argument("--reason", default="withdrawn")
    return ap


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    return {"serve": cmd_serve, "status": cmd_status, "ask": cmd_ask, "pair": cmd_pair,
            "pause": cmd_pause, "resume": cmd_resume, "notify": cmd_notify,
            "withdraw": cmd_withdraw}[args.cmd](args)


# One ENTRY FUNCTION per verb: the front door's routes name functions and hand each
# only the words after the verb (engine/familiar, architecture 3a), so `familiar relay
# status --check` arrives as (["--check"]) and the verb is supplied here.
def serve(argv: list) -> int:
    return main(["serve", *argv])


def status(argv: list) -> int:
    return main(["status", *argv])


def ask(argv: list) -> int:
    return main(["ask", *argv])


def pair(argv: list) -> int:
    return main(["pair", *argv])


def pause(argv: list) -> int:
    return main(["pause", *argv])


def resume(argv: list) -> int:
    return main(["resume", *argv])


def notify(argv: list) -> int:
    return main(["notify", *argv])


def withdraw(argv: list) -> int:
    return main(["withdraw", *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
