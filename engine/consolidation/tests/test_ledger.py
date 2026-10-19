"""The ledger's contract, held in place.

What is worth a test here is not "does json.loads work" but the three promises
the stages rely on: an unreadable line is COUNTED and not silently dropped, an
absent ledger is an empty one rather than an error, and a dismissal LAPSES when
its leaf changes. Each of those was previously spread across two or three
copies with different answers.
"""
import json

import pytest

from consolidation import ledger


# ── the format ───────────────────────────────────────────────────────────────

def test_absent_ledger_reads_as_empty(tmp_path):
    got = ledger.read(tmp_path, ledger.USAGE)
    assert (len(got), got.malformed) == (0, 0)
    assert got.path == tmp_path / ledger.USAGE


def test_append_then_read_round_trip(tmp_path):
    ledger.append(tmp_path, ledger.USAGE, {"ts": "2026-09-03T00:00:00Z", "skill": "a"})
    ledger.append(tmp_path, ledger.USAGE, {"ts": "2026-09-04T00:00:00Z", "skill": "b"})
    got = ledger.read(tmp_path, ledger.USAGE)
    assert [r["skill"] for r in got] == ["a", "b"]
    assert got.malformed == 0


def test_append_creates_the_data_dir(tmp_path):
    base = tmp_path / "not-yet"
    ledger.append(base, ledger.DECISIONS, {"id": "dec-1"})
    assert (base / ledger.DECISIONS).exists()


def test_non_ascii_survives_the_round_trip(tmp_path):
    ledger.append(tmp_path, ledger.USAGE, {"skill": "café — naïve"})
    assert ledger.read(tmp_path, ledger.USAGE).rows[0]["skill"] == "café — naïve"


def test_unreadable_line_is_counted_never_dropped(tmp_path):
    p = tmp_path / ledger.USAGE
    p.write_text('{"skill": "a"}\n{truncated by a killed ho\n{"skill": "b"}\n')
    got = ledger.read(tmp_path, ledger.USAGE)
    assert [r["skill"] for r in got] == ["a", "b"]
    assert got.malformed == 1, "a skipped line must show up in the count"


def test_a_bare_scalar_is_not_a_row(tmp_path):
    (tmp_path / ledger.USAGE).write_text('"just a string"\n42\n{"skill": "a"}\n')
    got = ledger.read(tmp_path, ledger.USAGE)
    assert len(got) == 1 and got.malformed == 2


def test_blank_lines_are_not_malformed(tmp_path):
    (tmp_path / ledger.USAGE).write_text('\n{"skill": "a"}\n\n\n')
    got = ledger.read(tmp_path, ledger.USAGE)
    assert len(got) == 1 and got.malformed == 0


def test_field_returns_present_values_in_file_order(tmp_path):
    for row in ({"ts": "1"}, {"other": "x"}, {"ts": ""}, {"ts": "2"}):
        ledger.append(tmp_path, ledger.USAGE, row)
    assert ledger.read(tmp_path, ledger.USAGE).field("ts") == ["1", "2"]


def test_legacy_usage_fields_stay_a_subset_of_the_declared_contract():
    # A legacy line carries fewer fields, never different ones. If this fails,
    # `selftest --schema` and every reader disagree about what a line may lack.
    assert set(ledger.USAGE_FIELDS_LEGACY) <= set(ledger.USAGE_FIELDS)


def test_the_ledger_set_is_what_preflight_fingerprints():
    assert ledger.FILES == (ledger.USAGE, ledger.DECISIONS, ledger.DISMISSALS)


# ── decisions ────────────────────────────────────────────────────────────────

def test_record_decision_writes_one_readable_row(tmp_path):
    did = ledger.record_decision(tmp_path, "decision", "use rebase", context="git")
    got = ledger.read(tmp_path, ledger.DECISIONS)
    assert len(got) == 1 and got.malformed == 0
    row = got.rows[0]
    assert row["id"] == did and row["kind"] == "decision"
    assert row["text"] == "use rebase" and row["context"] == "git"
    assert row["ts"].endswith("Z")


def test_decision_id_is_stable_enough_to_search_for(tmp_path):
    did = ledger.record_decision(tmp_path, "disagreement", "overruled")
    # The pass greps for this id across memory/ to see whether it landed.
    assert did.startswith("dis-") and did[4:].isdigit()


def test_an_unknown_kind_is_refused_rather_than_recorded(tmp_path):
    with pytest.raises(ValueError):
        ledger.record_decision(tmp_path, "musing", "text")
    assert not (tmp_path / ledger.DECISIONS).exists()


# ── dismissals ───────────────────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    (tmp_path / "memory" / "knowledge").mkdir(parents=True)
    (tmp_path / "memory" / "knowledge" / "leaf.md").write_text("original\n")
    return tmp_path


def test_dismissal_covers_the_proposal_it_was_recorded_for(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf")
    d = ledger.dismissals(tmp_path)
    assert d.covers(repo, "knowledge/leaf.md", "extend-leaf")


def test_a_dismissal_lapses_when_its_leaf_changes(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf")
    (repo / "memory" / "knowledge" / "leaf.md").write_text("moved on\n")
    assert not ledger.dismissals(tmp_path).covers(repo, "knowledge/leaf.md", "extend-leaf")


def test_a_dismissal_is_scoped_to_one_target_and_one_kind(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf")
    d = ledger.dismissals(tmp_path)
    assert not d.covers(repo, "knowledge/leaf.md", "new-leaf")
    assert not d.covers(repo, "knowledge/other.md", "extend-leaf")


def test_an_absent_leaf_hashes_to_empty_and_does_not_match(tmp_path, repo):
    # A proposal for a leaf that does not exist yet: recorded with an empty
    # hash, and a later real leaf must not inherit that dismissal.
    ledger.record_dismissal(tmp_path, repo, "knowledge/unwritten.md", "new-leaf")
    assert ledger.leaf_hash(repo, "knowledge/unwritten.md") == ""
    d = ledger.dismissals(tmp_path)
    assert d.covers(repo, "knowledge/unwritten.md", "new-leaf")
    (repo / "memory" / "knowledge" / "unwritten.md").write_text("now it exists\n")
    assert not ledger.dismissals(tmp_path).covers(repo, "knowledge/unwritten.md", "new-leaf")


def test_a_leaf_name_resolves_without_its_extension(tmp_path, repo):
    """`decide` and the report raise the bare leaf NAME for a dangling link
    (`related: voice`), while a path-style proposal carries the `.md`. Both are
    real targets and both must hash -- a name that resolves to nothing hashed to
    "" and suppressed the proposal for good (see the time-box test below)."""
    assert ledger.leaf_hash(repo, "knowledge/leaf") == \
        ledger.leaf_hash(repo, "knowledge/leaf.md")
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf", "extend-leaf")
    assert ledger.dismissals(tmp_path).covers(repo, "knowledge/leaf", "extend-leaf")


def test_an_unresolvable_leaf_is_time_boxed_not_permanent(tmp_path, repo):
    """The `"" == ""` permanence bug, for leaves.

    A `dangling-link` proposal's target is a name that by definition resolves to
    no file. `leaf_hash` returns "", and the old covers() matched "" to "" on
    every future night: a permanent "never mention this again" in a module whose
    docstring promises a dismissal lapses. Reachable from the 2026-09-29 report,
    which carries three of exactly this item.
    """
    ledger.record_dismissal(tmp_path, repo, "knowledge-vs-skills", "dangling-link")
    d = ledger.dismissals(tmp_path)
    assert d.covers(repo, "knowledge-vs-skills", "dangling-link")
    assert not d.covers(repo, "knowledge-vs-skills", "dangling-link",
                        now=_now_iso(ledger.OPAQUE_TTL_DAYS + 1)), \
        "an unresolvable leaf must return to the queue, not vanish"


def test_dismissals_reads_once_and_reports_what_it_could_not_read(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf")
    with (tmp_path / ledger.DISMISSALS).open("a") as fh:
        fh.write("{broken\n")
    d = ledger.dismissals(tmp_path)
    assert len(d) == 1 and d.malformed == 1


def test_stage_4_asks_many_times_after_one_read(tmp_path, repo):
    """`covers` must not re-read: stage 4 calls it once per model proposal."""
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf")
    d = ledger.dismissals(tmp_path)
    (tmp_path / ledger.DISMISSALS).unlink()          # the file is gone...
    assert d.covers(repo, "knowledge/leaf.md", "extend-leaf")   # ...the answer stands


def test_recorded_rows_are_plain_json_a_human_can_read(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf", "why")
    line = (tmp_path / ledger.DISMISSALS).read_text().strip()
    assert json.loads(line)["note"] == "why"
    assert "\n" not in line, "one row, one line"


# ── opaque dismissals (the "" == "" permanence bug) ─────────────────────────
# An opaque target is not a file: it hashes to "" unconditionally, so the old
# covers() matched it forever -- a permanent "never mention this again" in a
# module that promises the opposite. Opaque dismissals are time-boxed instead.

def _now_iso(offset_days=0):
    import time as _time
    return _time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          _time.gmtime(_time.time() + offset_days * 86400))


def test_an_opaque_dismissal_is_time_boxed_not_permanent(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "some-skill", "adopt",
                            target_kind="opaque")
    d = ledger.dismissals(tmp_path)
    assert d.covers(repo, "some-skill", "adopt", target_kind="opaque")
    # A month later, with no file to change, the dismissal has lapsed.
    future = _now_iso(ledger.OPAQUE_TTL_DAYS + 1)
    assert not d.covers(repo, "some-skill", "adopt", target_kind="opaque",
                        now=future)


def test_an_opaque_dismissal_does_not_require_a_file(tmp_path):
    # No memory/ tree at all: the target has never been and will never be a
    # file. Recording and covering must not touch the filesystem.
    ledger.record_dismissal(tmp_path, tmp_path, "a ↔ b", "link",
                            target_kind="opaque")
    assert ledger.dismissals(tmp_path).covers(
        tmp_path, "a ↔ b", "link", target_kind="opaque")


def test_an_opaque_dismissal_is_scoped_to_target_and_kind(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "some-skill", "adopt",
                            target_kind="opaque")
    d = ledger.dismissals(tmp_path)
    assert not d.covers(repo, "some-skill", "link", target_kind="opaque")
    assert not d.covers(repo, "other-skill", "adopt", target_kind="opaque")


def test_a_leaf_dismissal_does_not_suppress_an_opaque_proposal(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf")
    assert not ledger.dismissals(tmp_path).covers(
        repo, "knowledge/leaf.md", "extend-leaf", target_kind="opaque")


def test_an_opaque_dismissal_does_not_suppress_a_leaf_proposal(tmp_path, repo):
    ledger.record_dismissal(tmp_path, repo, "knowledge/leaf.md", "extend-leaf",
                            target_kind="opaque")
    assert not ledger.dismissals(tmp_path).covers(
        repo, "knowledge/leaf.md", "extend-leaf")


def test_a_row_without_target_kind_reads_as_leaf(tmp_path, repo):
    # Rows written before target_kind existed carry no field; they are leaves.
    ledger.append(tmp_path, ledger.DISMISSALS,
                  {"ts": _now_iso(), "target": "knowledge/leaf.md",
                   "kind": "extend-leaf",
                   "leaf_sha": ledger.leaf_hash(repo, "knowledge/leaf.md"),
                   "note": ""})
    assert ledger.dismissals(tmp_path).covers(
        repo, "knowledge/leaf.md", "extend-leaf")
    assert not ledger.dismissals(tmp_path).covers(
        repo, "knowledge/leaf.md", "extend-leaf", target_kind="opaque")


def test_an_unknown_target_kind_is_refused(tmp_path, repo):
    with pytest.raises(ValueError):
        ledger.record_dismissal(tmp_path, repo, "x", "adopt", target_kind="nope")
    assert not (tmp_path / ledger.DISMISSALS).exists()
    with pytest.raises(ValueError):
        ledger.dismissals(tmp_path).covers(repo, "x", "adopt", target_kind="nope")


def test_an_unreadable_ts_lapses_the_opaque_dismissal(tmp_path, repo):
    # A row whose ts will not parse must not suppress anything -- fail toward
    # surfacing, never a silent blind.
    ledger.append(tmp_path, ledger.DISMISSALS,
                  {"ts": "not-a-date", "target": "s", "kind": "adopt",
                   "target_kind": "opaque", "note": ""})
    assert not ledger.dismissals(tmp_path).covers(
        repo, "s", "adopt", target_kind="opaque")
