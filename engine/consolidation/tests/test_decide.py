"""`decide`, every form, and the staleness refusal (SPECS.md items 1c, 1d, 1g).

`decide` is run through the real dispatcher (`familiar`'ss `main`) so the
parse, the Spec and the resolution path are exercised together -- an undeclared
flag must fail here exactly as it does for a user.
"""
import json
import pathlib
import subprocess
import sys

import pytest

from cli import cli
from lib import invocation
from consolidation import ledger, queue

ROOT = pathlib.Path(__file__).resolve().parents[2] / "cli"
# The front door (dev/architecture 3b): `decide` is run through the real
# dispatcher, and the dispatcher is `familiar` now.
BIN = ROOT.parent / "familiar"      # ROOT is engine/

ITEMS = [
    queue.as_dict("dangling-link", "knowledge-vs-skills", "`related: voice`",
                  "resolves to no leaf", "5a", "leaf", "2026-09-29"),
    queue.as_dict("dangling-link", "memory-architecture", "`related: voice`",
                  "resolves to no leaf", "5a", "leaf", "2026-09-29"),
    queue.as_dict("extend-leaf", "knowledge/operations/omarchy-host-traps.md",
                  "Stale VPN DNS", "recurrence #3", "5b", "leaf", "2026-09-29"),
    queue.as_dict("decision", "dec-51452279", "has not landed anywhere durable",
                  "awaiting the user", "6", "opaque", "2026-09-29"),
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A private data dir and repo, so nothing touches the real ledger."""
    base = tmp_path / "base"
    agents = tmp_path / "memory"
    agents.mkdir(parents=True)
    (agents.parent / "memory").mkdir(exist_ok=True)
    monkeypatch.setenv("PAZRAS_DATA_DIR", str(base))
    monkeypatch.setenv("PAZRAS_MEMORY_DIR", str(agents))
    return base, agents


def _run(base, argv, stdin=None):
    p = subprocess.run([sys.executable, str(BIN), "consolidation"] + argv, capture_output=True,
                       text=True, input=stdin,
                       env={**__import__("os").environ,
                            "PAZRAS_DATA_DIR": str(base),
                            "PAZRAS_MEMORY_DIR": str(base.parent / "memory")})
    return p.returncode, p.stdout, p.stderr


def _inv(base, argv):
    """Parse argv exactly as the dispatcher does for `decide`."""
    return invocation.parse(argv, cli.DECIDE, base, base.parent / "memory")


# ── the numbered forms ───────────────────────────────────────────────────────

def test_one_ordinal_appends_exactly_one_decision_line(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "1"])
    assert rc == 0, err
    rows = ledger.read(base, ledger.DISMISSALS).rows
    assert len(rows) == 1
    assert rows[0]["target"] == "knowledge-vs-skills"
    assert rows[0]["kind"] == "dangling-link"
    assert "1:" in out


def test_refusing_records_the_refusal_and_not_an_acceptance(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "2", "--no"])
    assert rc == 0, err
    assert "refuse" in json.dumps(queue.items(base)[1]["resolution"])


def test_the_ordinal_resolves_the_item_at_that_position(env):
    """The failure this guards: acting on item 4 while claiming to do item 3."""
    base, _ = env
    queue.save(base, ITEMS)
    assert _run(base, ["decide", "3"])[0] == 0
    assert queue.items(base)[2]["resolution"]["target"] == \
        "knowledge/operations/omarchy-host-traps.md"
    assert queue.items(base)[0]["resolution"] is None


def test_an_ordininal_with_why_shows_the_full_item_and_resolves_nothing(env):
    """The report row carries only the one-line summary, so `why` must be
    reachable somewhere -- and reading it must not be the same as acting on it."""
    base, _ = env
    queue.save(base, ITEMS)
    before = json.dumps(queue.items(base))
    rc, out, err = _run(base, ["decide", "1", "--why"])
    assert rc == 0, err
    assert "resolves to no leaf" in out          # the summary
    assert "Nothing resolved" in out
    assert json.dumps(queue.items(base)) == before
    assert not ledger.read(base, ledger.DISMISSALS).rows


def test_why_does_not_write_a_decision_line(env):
    base, _ = env
    queue.save(base, ITEMS)
    _run(base, ["decide", "2", "--why"])
    assert len(ledger.read(base, ledger.DISMISSALS).rows) == 0


def test_an_ordinal_past_the_end_is_refused_not_clamped(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "99"])
    assert rc == 1 and "no item 99" in err


def test_a_non_numeric_ordinal_is_a_usage_error_not_a_traceback(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "banana"])
    assert rc == 1 and "Traceback" not in err


def test_an_undeclared_flag_is_still_an_error(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "1", "--yes"])
    assert rc == 1 and "--yes" in err


# ── --kind --all ─────────────────────────────────────────────────────────────

def test_kind_all_resolves_the_whole_kind(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--kind=dangling-link", "--all"])
    assert rc == 0, err
    its = queue.items(base)
    assert its[0]["resolution"] and its[1]["resolution"]
    assert its[2]["resolution"] is None            # a different kind is untouched


def test_kind_all_without_all_is_refused(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--kind=dangling-link"])
    assert rc == 1 and "--all" in err


def test_kind_all_refuses_the_whole_kind(env):
    base, _ = env
    queue.save(base, ITEMS)
    queue_before = json.dumps(queue.items(base))
    rc, out, err = _run(base, ["decide", "--kind=dangling-link", "--all", "--no"])
    assert rc == 0, err
    assert "refuse" in json.dumps(queue.items(base)[0]["resolution"])


def test_a_kind_nobody_raised_says_so(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--kind=demote", "--all"])
    assert rc == 1 and "no open items" in err


def test_kind_all_skips_items_already_resolved(env):
    base, _ = env
    queue.save(base, ITEMS)
    queue.resolve(base, ITEMS[0]["id"], {"action": "accept"})
    rc, out, err = _run(base, ["decide", "--kind=dangling-link", "--all"])
    assert rc == 0, err
    assert queue.items(base)[0]["resolution"]["action"] == "accept"  # unchanged


# ── the walk, driven from a pipe ─────────────────────────────────────────────

def test_the_walk_accepts_refuses_and_skips_from_a_pipe(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="y\nn\ns\n")
    assert rc == 0, err
    its = queue.items(base)
    assert its[0]["resolution"]["action"] == "accept"
    assert its[1]["resolution"]["action"] == "refuse"
    assert its[2]["resolution"] is None            # skipped
    assert "1." in out and "2." in out


def test_the_walk_a_key_takes_the_rest_of_the_kind(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="a\n")
    assert rc == 0, err
    its = queue.items(base)
    assert its[0]["resolution"] and its[1]["resolution"]
    assert its[2]["resolution"] is None


def test_the_walk_q_key_stops_without_resolving(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="q\n")
    assert rc == 0, err
    assert all(i["resolution"] is None for i in queue.items(base))


def test_the_walk_question_key_shows_the_item_and_re_asks(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="?\ny\n")
    assert rc == 0, err
    assert "target_kind" in out
    assert queue.items(base)[0]["resolution"]["action"] == "accept"


def test_the_walk_asks_again_on_an_unknown_key(env):
    """Assuming a keystroke is `y` is the failure the walk exists to avoid."""
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="zzz\ny\nq\n")
    assert rc == 0, err
    assert "y / n / a / s / ? / q" in out
    assert queue.items(base)[0]["resolution"]["action"] == "accept"


def test_the_walk_reaches_eof_without_a_traceback(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="")
    assert rc == 0 and "Traceback" not in err


# ── the staleness guard (1d) ─────────────────────────────────────────────────

def test_a_queue_mutated_under_the_cli_refuses_with_exit_3_and_writes_nothing(env):
    """The queue's stored digest is what the guard compares -- an edit that
    leaves the digest stale is the 'queue has moved' case."""
    base, _ = env
    queue.save(base, ITEMS)
    before = len(ledger.read(base, ledger.DISMISSALS).rows)
    p = queue.path(base)
    raw = json.loads(p.read_text())
    raw["items"].append(queue.as_dict("demote", "smuggled", "added by hand",
                                      "", "6", "leaf", "2026-09-29"))
    p.write_text(json.dumps(raw))                 # digest left as it was
    rc, out, err = _run(base, ["decide", "1"])
    assert rc == 3, f"expected exit 3, got {rc}: {err}"
    assert "has moved" in err
    assert len(ledger.read(base, ledger.DISMISSALS).rows) == before   # no write
    assert queue.items(base)[0].get("resolution") is None


def test_a_stale_queue_refuses_the_walk_and_kind_forms_too(env):
    base, _ = env
    queue.save(base, ITEMS)
    p = queue.path(base)
    raw = json.loads(p.read_text())
    raw["digest"] = "000000000000"
    p.write_text(json.dumps(raw))
    assert _run(base, ["decide", "--walk"], stdin="y\n")[0] == 3
    assert _run(base, ["decide", "--kind=dangling-link", "--all"])[0] == 3


def test_an_untouched_queue_does_not_refuse(env):
    """The guard must not fire on the ordinary case -- a nightly-moving digest
    would be a guard that gets bypassed."""
    base, _ = env
    queue.save(base, ITEMS)
    assert _run(base, ["decide", "1"])[0] == 0


# ── 1g: one resolution record, one writer per kind ───────────────────────────

def test_decide_dispatches_opaque_kinds_through_the_dismissal_ledger(env):
    """An opaque item must time-box, not hash to "" and suppress forever."""
    base, _ = env
    items = ITEMS[:3] + [queue.as_dict("adopt", "some-skill", "adopt it", "", "5",
                                       "opaque", "2026-09-29")]
    queue.save(base, items)
    assert _run(base, ["decide", "4"])[0] == 0
    rows = ledger.read(base, ledger.DISMISSALS).rows
    assert len(rows) == 1
    assert rows[0]["target_kind"] == "opaque"
    assert "leaf_sha" not in rows[0] and not rows[0].get("retired")


# ── a decision's own answers (dev/remote R6c) ────────────────────────────────

def test_a_decision_without_a_choice_is_refused_not_guessed(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "4"])
    assert rc == 1 and "land" in err
    assert queue.items(base)[3]["resolution"] is None


def test_drop_retires_a_decision_for_good(env):
    base, _ = env
    queue.save(base, ITEMS)
    assert _run(base, ["decide", "4", "--choice=drop"])[0] == 0
    assert ledger.retired(base) == {"dec-51452279"}
    assert queue.items(base)[3]["resolution"]["action"] == "drop"


def test_superseded_needs_the_replacing_id(env):
    base, _ = env
    queue.save(base, ITEMS)
    assert _run(base, ["decide", "4", "--choice=superseded"])[0] == 1
    assert _run(base, ["decide", "4", "--choice=superseded", "--by=dec-1"])[0] == 0
    assert "superseded by dec-1" in ledger.read(base, ledger.DISMISSALS).rows[0]["note"]


def test_land_queues_the_decision_and_note_leaves_it_open(env):
    from consolidation import resolve
    base, _ = env
    queue.save(base, ITEMS)
    assert _run(base, ["decide", "4", "--choice=note", "--note=check with Work"])[0] == 0
    assert queue.items(base)[3]["resolution"] is None
    assert ledger.read(base, resolve.NOTES).rows[0]["note"] == "check with Work"
    assert _run(base, ["decide", "4", "--choice=land"])[0] == 0
    assert resolve.pending_landings(base)[0]["target"] == "dec-51452279"
    assert not ledger.retired(base)


def test_the_walk_offers_a_decision_its_own_keys(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["decide", "--walk"], stdin="s\ns\ns\np\ndec-9\n")
    assert rc == 0, err
    assert "[l] Land it" in out
    assert queue.items(base)[3]["resolution"]["by"] == "dec-9"


def test_a_retired_decision_is_never_raised_again(tmp_path):
    base = tmp_path
    ledger.record_dismissal(base, tmp_path, "dec-1", "decision", "dropped",
                            target_kind="opaque", retired=True)
    assert ledger.retired(base) == {"dec-1"}


def test_a_leaf_item_records_a_hash_so_it_self_clears(env):
    base, _ = env
    (base.parent / "memory" / "knowledge-vs-skills.md").write_text("body\n")
    queue.save(base, ITEMS)
    assert _run(base, ["decide", "1"])[0] == 0
    rows = ledger.read(base, ledger.DISMISSALS).rows
    assert rows[0]["target_kind"] == "leaf" and rows[0]["leaf_sha"]


def test_the_existing_dismiss_command_still_works_unchanged(env):
    """1g: `decide` reuses `dismiss`, it does not replace it."""
    base, _ = env
    rc, out, err = _run(base, ["dismiss", "--target=x", "--kind=y",
                               "--target-kind=opaque"])
    assert rc == 0, err
    assert len(ledger.read(base, ledger.DISMISSALS).rows) == 1


# ── queue, the read-only view (1b) ───────────────────────────────────────────

def test_queue_lists_numbered_rows_and_no_commands(env):
    base, _ = env
    queue.save(base, ITEMS)
    rc, out, err = _run(base, ["queue"])
    assert rc == 0, err
    numbered = [l for l in out.splitlines() if l.lstrip()[:1].isdigit()]
    assert len(numbered) == len(ITEMS)
    assert "dismiss --target" not in out
    assert "--kind" not in out


def test_queue_hides_resolved_items_unless_all(env):
    base, _ = env
    queue.save(base, ITEMS)
    queue.resolve(base, ITEMS[0]["id"], {"action": "accept"})
    out = _run(base, ["queue"])[1]
    assert "knowledge-vs-skills" not in out
    out_all = _run(base, ["queue", "--all"])[1]
    assert "knowledge-vs-skills" in out_all


def test_an_empty_queue_says_so_rather_than_printing_nothing(env):
    base, _ = env
    rc, out, err = _run(base, ["queue"])
    assert rc == 0 and "empty" in out
