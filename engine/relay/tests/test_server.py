"""The socket and the poller together (R1a): a client that asks gets the tap's answer,
and a client that asked while the relay was down still does."""
import asyncio
import json
import socket
import stat
import threading
import time

from relay_fakes import OWNER, tap

from relay import client
from relay.core import Relay
from relay.server import Server


def start(bot, tmp_path, sock):
    relay = Relay(bot, tmp_path / "relay", nonce=iter(f"n{i}" for i in range(99)).__next__)
    relay.state["owner_id"] = OWNER
    server = Server(relay, sock, poll_timeout=1)
    loop = asyncio.new_event_loop()
    task = {}

    def run():
        asyncio.set_event_loop(loop)
        task["t"] = loop.create_task(server.run(bot))
        try:
            loop.run_until_complete(task["t"])
        except asyncio.CancelledError:
            pass

    th = threading.Thread(target=run, daemon=True)
    th.start()
    # The file exists at bind(), before listen(): wait for a connect that succeeds,
    # not for the file (a loaded gate run found the gap, 2026-10-20).
    for _ in range(500):
        try:
            with socket.socket(socket.AF_UNIX) as probe:
                probe.connect(str(sock))
            break
        except OSError:
            time.sleep(0.01)

    def stop():
        server.fatal = "stopped by the test"
        loop.call_soon_threadsafe(task["t"].cancel)
        th.join(timeout=5)
    return relay, stop


def wait_for(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_a_client_ask_is_answered_by_a_tap(bot, tmp_path):
    sock = tmp_path / "r.sock"
    env = {"FAMILIAR_RELAY_SOCK": str(sock)}
    relay, stop = start(bot, tmp_path, sock)
    try:
        assert stat.S_IMODE(sock.stat().st_mode) == 0o600
        out = {}
        th = threading.Thread(target=lambda: out.update(client.ask(
            {"id": "a1", "session": "s", "kind": "select", "title": "push?",
             "options": ["Yes", "No"]}, env=env)))
        th.start()
        assert wait_for(lambda: bot.sent()), "the ask reached Telegram"
        bot.updates.put(tap("n0:1"))
        th.join(timeout=5)
        assert out["value"] == "No"
        st = client.request({"op": "status"}, env=env)
        assert st["ok"] and st["pending"] == 0 and st["poll"]["ok_ts"]
    finally:
        stop()


def test_an_ask_made_while_the_relay_is_down_is_answered_once_it_runs(bot, tmp_path):
    sock = tmp_path / "r.sock"
    env = {"FAMILIAR_RELAY_SOCK": str(sock)}
    out, retries = {}, []
    th = threading.Thread(target=lambda: out.update(client.ask(
        {"id": "a1", "session": "s", "kind": "confirm", "title": "ok?"}, env=env,
        retry=0.05, on_retry=retries.append)))
    th.start()
    assert wait_for(lambda: len(retries) >= 2), "the client keeps trying"
    relay, stop = start(bot, tmp_path, sock)
    try:
        assert wait_for(lambda: bot.sent())
        bot.updates.put(tap("n0:0"))
        th.join(timeout=5)
        assert out["confirmed"] is True and len(bot.sent()) == 1
    finally:
        stop()


def test_the_socket_refuses_a_malformed_request_and_names_the_ops(bot, tmp_path):
    sock = tmp_path / "r.sock"
    relay, stop = start(bot, tmp_path, sock)
    try:
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(sock))
            s.sendall(b'{"op": "answer", "id": "a1", "value": "Yes"}\nnot json\n')
            f = s.makefile()
            first, second = json.loads(f.readline()), json.loads(f.readline())
        assert first["ok"] is False and "unknown op 'answer'" in first["error"]
        assert second["ok"] is False and "unreadable" in second["error"]
    finally:
        stop()
