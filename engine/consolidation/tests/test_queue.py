"""The queue store: identity, recurrence, and the digest (SPECS.md item 1a).

The property under test is the one `decide N` rests on: an ordinal printed in
the report names the same item in the queue, and an item's identity does not
change when the model rewords its summary.
"""
import json
import pathlib

import pytest

from consolidation import queue


def _it(kind="dangling-link", target="knowledge-vs-skills", what="`related: voice` resolves to no leaf"):
    return queue.as_dict(kind, target, what, why="why", stage="5a",
                         target_kind="leaf", first_seen="2026-09-29")


# ── identity ─────────────────────────────────────────────────────────────────

def test_an_id_is_stable_across_nights():
    """The whole recurrence count depends on this: same kind+target, same id."""
    a = _it(what="one wording")
    b = _it(what="a completely different wording the model chose tonight")
    assert a["id"] == b["id"]


def test_the_id_is_not_the_position():
    """`decide 3` resolves through the ordinal, so identity must not be it."""
    a, b = _it(target="alpha"), _it(target="beta")
    assert a["id"] != b["id"]
    assert queue.by_ordinal([a, b], 1)["id"] == a["id"]


def test_a_different_kind_on_the_same_target_is_a_different_item():
    a = _it(kind="dangling-link", target="x")
    b = _it(kind="extend-leaf", target="x")
    assert a["id"] != b["id"]


# ── recurrence ───────────────────────────────────────────────────────────────

def test_merge_counts_nights_and_keeps_first_seen():
    prev = [dict(_it(), first_seen="2026-09-27", nights=3)]
    out = queue.merge(prev, [_it()], "2026-09-29")
    assert out[0]["nights"] == 4
    assert out[0]["first_seen"] == "2026-09-27"      # first night, not tonight


def test_merge_starts_a_new_item_at_one_night():
    out = queue.merge([], [_it()], "2026-09-29")
    assert out[0]["nights"] == 1 and out[0]["first_seen"] == "2026-09-29"


def test_merge_takes_tonights_wording_but_keeps_the_identity():
    prev = [dict(_it(what="old wording"), nights=2)]
    out = queue.merge(prev, [_it(what="new wording")], "2026-09-29")
    assert out[0]["summary"] == "new wording"
    assert out[0]["nights"] == 3


def test_a_resolved_item_is_not_re_raised():
    """The user's answer survives the next night's pass."""
    prev = [dict(_it(), resolution={"action": "accept"})]
    out = queue.merge(prev, [_it()], "2026-09-29")
    assert out[0]["resolution"] == {"action": "accept"}


# ── the digest ───────────────────────────────────────────────────────────────

def test_the_digest_ignores_recurrence_but_not_identity():
    """It must NOT move nightly (or `decide` refuses every morning) and it MUST
    move when an ordinal would name something else."""
    a = [_it()]
    same = [dict(_it(), nights=9, first_seen="2020-01-01")]
    assert queue.digest(a) == queue.digest(same)
    moved = [_it(), _it(target="something-else")]
    assert queue.digest(a) != queue.digest(moved)


def test_the_digest_moves_when_a_resolution_lands():
    a = [_it()]
    b = [dict(_it(), resolution={"action": "accept"})]
    assert queue.digest(a) != queue.digest(b)


# ── the file ─────────────────────────────────────────────────────────────────

def test_an_absent_queue_is_empty_not_an_error(tmp_path):
    d = queue.load(tmp_path)
    assert d["items"] == [] and d["version"] == queue.VERSION


def test_save_then_load_round_trips_and_the_digest_matches(tmp_path):
    its = [_it(), _it(target="other")]
    queue.save(tmp_path, its)
    back = queue.load(tmp_path)
    assert [i["target"] for i in back["items"]] == ["knowledge-vs-skills", "other"]
    assert back["digest"] == queue.digest(its)


def test_a_hand_edited_queue_is_detectable(tmp_path):
    """What `decide`'s staleness guard actually checks."""
    queue.save(tmp_path, [_it()])
    p = queue.path(tmp_path)
    raw = json.loads(p.read_text())
    raw["items"].append(_it(target="smuggled-in"))
    p.write_text(json.dumps(raw))          # digest left as it was
    assert queue.load(tmp_path)["digest"] != queue.digest(queue.load(tmp_path)["items"])


def test_an_unknown_version_refuses_rather_than_guessing(tmp_path):
    queue.path(tmp_path).write_text('{"version": 99, "items": []}')
    with pytest.raises(ValueError):
        queue.load(tmp_path)


def test_a_corrupt_queue_refuses(tmp_path):
    queue.path(tmp_path).write_text("{not json")
    with pytest.raises(ValueError):
        queue.load(tmp_path)


def test_resolve_preserves_order_and_ordinals(tmp_path):
    its = [_it(target="a"), _it(target="b"), _it(target="c")]
    queue.save(tmp_path, its)
    queue.resolve(tmp_path, its[0]["id"], {"action": "accept"})
    back = queue.items(tmp_path)
    assert [i["target"] for i in back] == ["a", "b", "c"]   # no reordering
    assert queue.by_ordinal(back, 2)["target"] == "b"       # ordinal still names b
    assert back[0]["resolution"] == {"action": "accept"}


def test_resolve_reports_zero_when_the_id_is_gone(tmp_path):
    queue.save(tmp_path, [_it()])
    assert queue.resolve(tmp_path, "q-nope", {"action": "accept"}) == 0


# ── the view ─────────────────────────────────────────────────────────────────

def test_a_row_carries_no_command_string():
    """Item 1b's exit criterion, at the source: `decide N` is the interface."""
    row = queue.Item(**_it()).row(3)
    assert "dismiss" not in row and "--target" not in row
    assert row.lstrip().startswith("3")


def test_of_kind_returns_only_unresolved_in_ordinal_order():
    its = [dict(_it(target="a")), dict(_it(target="b"), resolution={"action": "accept"}),
           dict(_it(kind="extend-leaf", target="c"))]
    got = queue.of_kind(its, "dangling-link")
    assert [i["target"] for i in got] == ["a"]


def test_a_hyphenated_handle_from_the_report_matches_its_stored_kind():
    """The report renders `knowledge→skill link` as `knowledge→skill-link` so the
    columns do not shift. A user copying that handle into `decide --kind=` matched
    NOTHING -- silently. A printed spelling its own command rejects is worse than
    no handle at all."""
    its = [queue.as_dict("knowledge→skill link", "knowledge/tools/cc.md", "x",
                         "", "5a", "leaf", "2026-09-29")]
    assert len(queue.of_kind(its, "knowledge→skill-link")) == 1
    assert len(queue.of_kind(its, "knowledge→skill link")) == 1


def test_the_handle_fix_does_not_match_a_kind_that_does_not_exist():
    """Normalising hyphens to spaces must not invent a match."""
    its = [queue.as_dict("dangling-link", "a", "x", "", "5a", "leaf",
                         "2026-09-29")]
    assert len(queue.of_kind(its, "dangling-link")) == 1
    assert queue.of_kind(its, "dangling link") == []
