"""The phone's review walk (dev/remote R6d), driven by a scripted relay."""
from __future__ import annotations

import pytest

from consolidation import ledger, queue, resolve, review
from lib import invocation

ITEMS = [
    queue.as_dict("decision", "dec-1", "has not landed: index per branch", "why 1", "4",
                  "opaque", "2026-10-21"),
    queue.as_dict("decision", "dec-2", "has not landed: index per subject", "why 2", "4",
                  "opaque", "2026-10-21"),
    queue.as_dict("dangling-link", "leaf-a", "`related: x`", "no leaf", "5a", "leaf",
                  "2026-10-21"),
]


class Phone:
    """Answers asks in order from a script; records what was asked and sent."""

    def __init__(self, answers):
        self.answers, self.asked, self.sent = list(answers), [], []

    def ask(self, req):
        self.asked.append(req)
        return {"op": "answer", "id": req["id"], **self.answers.pop(0)}

    def request(self, req):
        self.sent.append(req)
        return {"ok": True}


@pytest.fixture(autouse=True)
def no_real_scheduler(monkeypatch):
    """A walk with a Land it must never reach `familiar schedule sessions add`:
    an unstubbed run once queued a real job from this file."""
    monkeypatch.setattr(review, "schedule_landing", lambda b, r: "scheduled (stub)")
    monkeypatch.setattr("consolidation.land._add",
                        lambda argv: pytest.fail("the real scheduler was called"))


@pytest.fixture
def base(tmp_path):
    b = tmp_path / "base"
    queue.save(b, ITEMS)
    return b


def _main(base, phone, *flags):
    inv = invocation.parse(["--remote", *flags], review.SPEC, base, base.parent / "memory")
    return review.main(inv, ask=phone.ask, request=phone.request)


def test_each_item_gets_its_own_choices_and_the_walk_resolves_them(base):
    phone = Phone([{"value": "Land it"}, {"value": "Drop"}, {"value": "Accept"}])
    assert _main(base, phone) == 0
    assert phone.asked[0]["options"] == ["Land it", "Superseded by…", "Drop", "Note",
                                         "Skip", "Stop"]
    assert phone.asked[2]["options"] == ["Accept", "Refuse", "Skip", "Stop"]
    assert phone.asked[0]["context"] == "why 1"
    acts = [i["resolution"]["action"] for i in queue.items(base)]
    assert acts == ["land", "drop", "accept"]
    assert all(i["resolution"]["via"] == "telegram" for i in queue.items(base))
    assert "3 resolved" in phone.sent[-1]["text"]


def test_a_reply_in_words_is_a_note_and_leaves_the_item_open(base):
    phone = Phone([{"value": None, "text": "ask Work first"}, {"value": "Stop"}])
    _main(base, phone)
    assert queue.items(base)[0]["resolution"] is None
    assert ledger.read(base, resolve.NOTES).rows[0]["note"] == "ask Work first"
    assert "stopped" in phone.sent[-1]["text"] and "/review" in phone.sent[-1]["text"]


def test_superseded_offers_the_other_decisions(base):
    phone = Phone([{"value": "Superseded by…"},
                   {"value": "dec-2: index per subject"}, {"value": "Stop"}])
    _main(base, phone)
    assert queue.items(base)[0]["resolution"]["by"] == "dec-2"
    assert ledger.retired(base) == {"dec-1"}


def test_stop_writes_nothing_more_and_skip_moves_on(base):
    phone = Phone([{"value": "Skip"}, {"value": "Stop"}])
    _main(base, phone)
    assert all(i["resolution"] is None for i in queue.items(base))


def test_an_item_resolved_elsewhere_meanwhile_is_not_written_twice(base):
    class Racing(Phone):
        def ask(self, req):
            if not self.asked:
                queue.resolve(base, ITEMS[0]["id"], {"action": "drop"})
            return super().ask(req)
    phone = Racing([{"value": "Land it"}, {"value": "Stop"}])
    _main(base, phone)
    assert queue.items(base)[0]["resolution"] == {"action": "drop"}
    assert not resolve.pending_landings(base)


def test_a_new_review_withdraws_the_last_runs_open_ask_and_resume_keeps_the_run(base):
    (base / review.STATE).write_text('{"run": "abcd", "current": "review:abcd:x:0"}')
    phone = Phone([{"value": "Stop"}])
    _main(base, phone, "--resume")
    assert phone.asked[0]["id"].startswith("review:abcd:")
    assert not any(r.get("op") == "withdraw" for r in phone.sent)
    (base / review.STATE).write_text('{"run": "abcd", "current": "review:abcd:x:0"}')
    phone = Phone([{"value": "Stop"}])
    _main(base, phone)
    assert phone.sent[0] == {"op": "withdraw", "id": "review:abcd:x:0",
                             "reason": "a new review started"}
    assert not phone.asked[0]["id"].startswith("review:abcd:")


def test_an_empty_queue_says_so(tmp_path):
    b = tmp_path / "b"
    queue.save(b, [])
    phone = Phone([])
    _main(b, phone)
    assert phone.sent[-1]["text"] == "Nothing waits on you."


# ── Land it schedules one job (R6e) ─────────────────────────────────────────

def test_land_schedules_one_job_for_the_pending_decisions_only(tmp_path):
    from consolidation import land
    base, repo = tmp_path / "base", tmp_path / "repo"
    (repo / "memory").mkdir(parents=True)
    (repo / "memory" / "leaf.md").write_text("already landed: dec-2\n")
    ledger.append(base, ledger.DECISIONS, {"id": "dec-1", "kind": "decision",
                                           "text": "the full decision text", "context": "c"})
    queue.save(base, ITEMS)
    for it in ITEMS[:2]:
        resolve.apply(base, repo, it, "land", note="soon" if it["target"] == "dec-1" else "")
    calls = []
    out = land.schedule(base, repo, run=lambda argv: (calls.append(argv), (0, "ok"))[1])
    assert out.startswith("scheduled land-") and "1 decision(s)" in out
    assert len(calls) == 1 and "--ready" in calls[0]
    text = (base / "landing" / (calls[0][calls[0].index("--name") + 1] + ".md")).read_text()
    assert "the full decision text" in text and "soon" in text and "dec-2" not in text
    assert land.schedule(base, repo, run=lambda a: (0, "")) == "nothing to land"
    assert land.pending(base, repo, retry=True)[0]["target"] == "dec-1"


def test_a_walk_with_a_land_schedules_the_landing(base, monkeypatch):
    seen = []
    monkeypatch.setattr(review, "schedule_landing", lambda b, r: seen.append(b) or "scheduled x")
    phone = Phone([{"value": "Land it"}, {"value": "Stop"}])
    _main(base, phone)
    assert seen and "scheduled x" in phone.sent[-1]["text"]
