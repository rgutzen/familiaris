"""The fake Bot API and update builders every relay test shares (a uniquely named
module: `from conftest import` collides when several test directories run together)."""
import queue

from relay.telegram import BotError

OWNER = 4242
STRANGER = 666


class FakeBot:
    """Records every call; `fail` names methods that raise; updates come from a queue."""

    def __init__(self):
        self.calls = []
        self.fail = set()
        self.next_id = 100
        self.updates = queue.Queue()

    def call(self, method, payload=None, *, timeout=30):
        if method in self.fail:
            raise BotError(method, 0, "network down")
        self.calls.append((method, payload or {}))
        if method == "sendMessage":
            self.next_id += 1
            return {"message_id": self.next_id}
        return True

    def get_updates(self, offset, timeout):
        try:
            return [self.updates.get(timeout=0.2)]
        except queue.Empty:
            return []

    def sent(self, method="sendMessage"):
        return [p for m, p in self.calls if m == method]


def tap(data, *, user=OWNER, chat=OWNER, uid=1):
    return {"update_id": uid, "callback_query": {
        "id": f"cq{uid}", "from": {"id": user}, "data": data,
        "message": {"chat": {"id": chat, "type": "private"}}}}


def reply(text, to, *, user=OWNER, chat=OWNER, uid=1):
    msg = {"from": {"id": user}, "chat": {"id": chat, "type": "private"}, "text": text}
    if to is not None:
        msg["reply_to_message"] = {"message_id": to}
    return {"update_id": uid, "message": msg}
