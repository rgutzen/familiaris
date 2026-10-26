"""Stage 8's second artifact: the precomputed answers
(memory/knowledge/meta/consolidation-cycle.md).

What these guard is the property the brief exists for -- that a session gets
its three answers WITHOUT a model call and WITHOUT a search: the range is
exact, the quoted material is verbatim and attributed, and "the pass has not
run" never renders as "nothing happened".
"""
import datetime as dt
import subprocess

import pytest

from consolidation import brief, pass_ctx
from lib import git

TODAY = dt.date(2026, 9, 12)
IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *IDENT, *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "memory" / "journal" / "2026" / "09").mkdir(parents=True)
    (r / "memory" / "knowledge").mkdir(parents=True)
    (r / "README.md").write_text("seed\n")
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True,
                   capture_output=True, text=True)
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "seed")
    return r


def _entry(repo, name, body):
    p = repo / "memory" / "journal" / "2026" / "09" / name
    p.write_text(body)
    return p


class _Ctx:
    """Just enough of pass_ctx.Pass for brief.render()."""

    def __init__(self, repo, base, today=TODAY):
        self.repo = repo
        self.agents = repo / "memory"
        self.base = base
        self.today = today
        self.dry_run = False
        self.aborted = None
        self.actions = []
        self.proposals = []
        self.notes = []
        self.stages_run = [f"{sid} {label}" for sid, label, _ in
                           __import__("consolidation.run", fromlist=["run"]).STAGES]


def _anchor(base, **fields):
    base.mkdir(parents=True, exist_ok=True)
    import json
    (base / "last-run.json").write_text(json.dumps(fields))


# ── what changed ─────────────────────────────────────────────────────────────

def test_the_range_is_the_last_pass_revision_not_a_date(repo, tmp_path):
    """A date range re-reports commits the previous brief already covered; the
    recorded revision is the only exact answer to "since the last pass"."""
    start = git.head(repo)
    (repo / "one.md").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "after the anchor")
    base = tmp_path / "data"
    _anchor(base, head=start, date="2026-09-11")

    out = brief.render(_Ctx(repo, base))
    assert "after the anchor" in out
    assert f"`{start}..HEAD`" in out
    assert "seed" not in out, "the anchor commit itself is before the range"


def test_an_unresolvable_anchor_degrades_to_a_date_and_says_so(repo, tmp_path):
    base = tmp_path / "data"
    _anchor(base, head="deadbee", date="2026-09-11")
    out = brief.render(_Ctx(repo, base))
    assert "no revision anchor" in out
    assert "deadbee" not in out


def test_no_previous_pass_is_stated_not_rendered_as_nothing_changed(repo, tmp_path):
    out = brief.render(_Ctx(repo, tmp_path / "data"))
    assert "first brief" in out


def test_journal_and_knowledge_changes_are_counted_separately(repo, tmp_path):
    start = git.head(repo)
    _entry(repo, "2026-09-12_a.md", "# a\n")
    (repo / "memory" / "knowledge" / "leaf.md").write_text("# leaf\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "work")
    base = tmp_path / "data"
    _anchor(base, head=start, date="2026-09-11")

    out = brief.render(_Ctx(repo, base))
    assert "1 journal entry" in out
    assert "knowledge leaf/leaves touched" in out
    assert "`leaf.md`" in out


# ── what's open / what failed: the harvest ───────────────────────────────────

ENTRY = """---
title: t
date: 2026-09-12
distilled_by: a-model
---

## What was done

- irrelevant

## Still open

- the thing nobody finished

## What failed or surprised

- the gateway died
"""


def test_open_and_failed_bullets_are_harvested_verbatim_with_a_pointer(repo, tmp_path):
    _entry(repo, "2026-09-12_x.md", ENTRY)
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")

    out = brief.render(_Ctx(repo, base))
    assert "- the thing nobody finished — `memory/journal/2026/09/2026-09-12_x.md:13`" in out
    assert "- the gateway died — `memory/journal/2026/09/2026-09-12_x.md:17`" in out
    assert "- irrelevant" not in out, "only the two declared sections are harvested"


def test_entries_older_than_the_last_pass_are_not_harvested(repo, tmp_path):
    _entry(repo, "2026-09-01_old.md", ENTRY)
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")
    assert "the thing nobody finished" not in brief.render(_Ctx(repo, base))


def test_reports_are_not_harvested_as_journal_entries(repo, tmp_path):
    d = repo / "memory" / "journal" / "reports"
    d.mkdir(parents=True)
    (d / "2026-09-12_consolidation.md").write_text(ENTRY)
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")
    assert "the thing nobody finished" not in brief.render(_Ctx(repo, base))


# ── what failed: the pass's own record ───────────────────────────────────────

def test_warnings_and_a_missing_stage_are_reported(repo, tmp_path):
    ctx = _Ctx(repo, tmp_path / "data")
    ctx.notes.append(pass_ctx.Note("1", "model unreachable", "error"))
    ctx.stages_run = ["1 replay"]
    out = brief.render(ctx)
    assert "model unreachable" in out
    assert "stage(s) that did not run" in out


def test_a_clean_pass_says_nothing_failed_rather_than_leaving_it_blank(repo, tmp_path):
    out = brief.render(_Ctx(repo, tmp_path / "data"))
    assert "Nothing failed in this pass" in out


# ── the artifact ─────────────────────────────────────────────────────────────

def test_the_path_is_stable_so_a_session_never_picks_a_night(repo, tmp_path):
    ctx = _Ctx(repo, tmp_path / "data")
    p = brief.write(ctx)
    assert p.name == "BRIEF.md"
    assert p == repo / "memory" / "journal" / "reports" / "BRIEF.md"
    assert brief.read(ctx.agents) == p.read_text()


def test_a_dry_run_writes_the_brief_outside_the_tree(repo, tmp_path):
    ctx = _Ctx(repo, tmp_path / "data")
    ctx.dry_run = True
    p = brief.write(ctx)
    assert tmp_path / "data" in p.parents
    assert not (repo / "memory" / "journal" / "reports" / "BRIEF.md").exists()


def test_an_absent_brief_reads_as_empty_not_as_an_error(tmp_path):
    assert brief.read(tmp_path) == ""


def test_no_model_is_reachable_from_this_module():
    """The brief is deterministic by construction, not by intention: importing
    `model` would be the first step of the thing this module refuses to do."""
    import inspect
    src = inspect.getsource(brief)
    assert "import model" not in src and "from . import model" not in src


# ── the two defects the first live run surfaced ──────────────────────────────

def test_a_full_proposal_list_does_not_push_the_harvest_off_the_end(repo, tmp_path):
    """The regression: `_section` truncated a second time, after each builder
    had already applied its own budget, so whichever sub-list came last was
    dropped in silence. A brief that says the sessions left nothing open, when
    they left five things open, is worse than no brief."""
    _entry(repo, "2026-09-12_x.md", ENTRY)
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")
    ctx = _Ctx(repo, base)
    for i in range(brief.MAX_LISTED * 2):
        ctx.proposals.append(pass_ctx.Proposal(
            stage="5", kind="dangling-link", target=f"leaf-{i}",
            what="points at nothing", target_kind="leaf"))

    out = brief.render(ctx)
    assert "Left open by recent sessions" in out
    assert "the thing nobody finished" in out
    assert "`familiar consolidation report --full`" in out, "the cut list still says so"


def test_a_hard_wrapped_bullet_is_rejoined_not_cut_mid_sentence(repo, tmp_path):
    """Journal prose is hard-wrapped. Quoting only the first physical line
    ends the quote mid-sentence, which reads as a claim the entry never made."""
    _entry(repo, "2026-09-12_w.md", """---
title: t
---

## Still open

- **A wrapped item** whose sentence continues onto
  a second line and then a third line as well.
- a short one
""")
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")
    out = brief.render(_Ctx(repo, base))
    assert ("**A wrapped item** whose sentence continues onto a second line "
            "and then a third line as well." in out)
    assert "- a short one — `memory/journal" in out


def test_a_blank_line_ends_a_bullet(repo, tmp_path):
    """Otherwise the paragraph after a list is swallowed into the last item."""
    _entry(repo, "2026-09-12_w.md", """---
title: t
---

## Still open

- the item

a paragraph that is not part of it
""")
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")
    out = brief.render(_Ctx(repo, base))
    assert "- the item — `memory/journal" in out
    assert "a paragraph that is not part of it" not in out


def test_a_runaway_bullet_is_capped(repo, tmp_path):
    long_tail = "\n  ".join(["padding words here"] * 60)
    _entry(repo, "2026-09-12_w.md",
           f"---\ntitle: t\n---\n\n## Still open\n\n- start {long_tail}\n")
    base = tmp_path / "data"
    _anchor(base, head=git.head(repo), date="2026-09-11")
    out = brief.render(_Ctx(repo, base))
    quoted = [l for l in out.split("\n") if l.startswith("- start ")]
    assert quoted and len(quoted[0]) < brief.BULLET_CHARS + 120
    assert "…" in quoted[0]


# ── scheduled sessions (dev/schedule 1g) ─────────────────────────────────────

def _job(base, name, events, **decl):
    import json
    d = base / "sessions" / name
    d.mkdir(parents=True)
    (d / "schedule.json").write_text(json.dumps({"name": name, "kind": "chain",
                                                 "trigger": "ready", "chain": "until-done",
                                                 "due": "", "unit": "", **decl}))
    (d / "runs.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def test_the_brief_says_what_ran_unattended_with_its_commits(repo, tmp_path):
    base = tmp_path / "data"
    _anchor(base, date=(TODAY - dt.timedelta(days=1)).isoformat())
    day = TODAY.isoformat()
    _job(base, "track", [
        {"event": "started", "ts": f"{day}T01:00:00+02:00"},
        {"event": "finished", "ts": f"{day}T02:00:00+02:00", "exit": 0,
         "progress": {"ticks": ["1b"], "commits": ["abc1234 schedule: 1b"]}},
        {"event": "paused", "ts": f"{day}T02:00:00+02:00", "state": "review",
         "why": "ticked 1b"}])
    _job(base, "old", [{"event": "started", "ts": "2020-01-01T01:00:00+02:00"},
                       {"event": "finished", "ts": "2020-01-01T02:00:00+02:00", "exit": 0}],
         chain="none", kind="once", trigger="at")
    out = brief.render(_Ctx(repo, base))
    section = out.split("## Scheduled sessions", 1)[1].split("---", 1)[0]
    assert "`track` — **paused** (review: ticked 1b)" in section
    assert "ticked 1b" in section and "abc1234 schedule: 1b" in section
    assert "`old`" not in section, "a job that did nothing since the last pass is not news"


def test_no_scheduled_job_is_stated_not_omitted(repo, tmp_path):
    out = brief.render(_Ctx(repo, tmp_path / "data"))
    assert "## Scheduled sessions" in out and "Nothing ran unattended" in out


# ── the phone's screen (dev/remote R5c) ──────────────────────────────────────

PHONE_BRIEF = """# Brief — 2026-10-21

## What changed

*question*

- a
- b

## What failed

- **error** x

---
"""


def test_the_phone_gets_headings_with_counts_unless_it_asks_for_a_section():
    head = brief.phone(PHONE_BRIEF)
    assert head.splitlines() == ["Brief — 2026-10-21", "What changed: 2 line(s)  (/brief changed)",
                                 "What failed: 1 line(s)  (/brief failed)"]
    assert brief.phone(PHONE_BRIEF, "changed") == "Brief — 2026-10-21 -- What changed\n- a\n- b"
    assert brief.phone(PHONE_BRIEF, "nonsense").startswith("/brief takes one of")
    assert brief.phone(PHONE_BRIEF, "changed", limit=20).endswith("[... cut]")


# ── the morning highlights (dev/remote R6a) ─────────────────────────────────

def test_highlights_group_failures_by_cause_not_by_file(repo, tmp_path):
    ctx = _Ctx(repo, tmp_path / "data")
    for i in range(493):
        ctx.notes.append(pass_ctx.Note(
            "1", f"2026101{i % 10}T0000Z_pi_{i}.jsonl: distillation failed (No API key found for deepseek.",
            "error"))
    out = brief.highlights(ctx)
    assert "493x error: distillation failed (No API key found for deepseek." in out
    assert len(out.splitlines()) <= brief.HIGHLIGHT_LINES + 2


def test_highlights_count_what_waits_and_end_with_review(repo, tmp_path):
    ctx = _Ctx(repo, tmp_path / "data")
    ctx.proposals = [pass_ctx.Proposal("4", "decision", f"dec-{i}", "w") for i in range(3)]
    out = brief.highlights(ctx)
    assert "Waiting on you: 3" in out and "3 decision" in out
    assert out.rstrip().endswith("/review to decide the open items")


def test_highlights_are_written_beside_the_brief(repo, tmp_path):
    ctx = _Ctx(repo, tmp_path / "data")
    brief.write(ctx)
    assert brief.read(ctx.agents, brief.HIGHLIGHTS).startswith(f"Nightly pass {TODAY.isoformat()}")


def test_stale_highlights_say_so_in_their_first_line():
    text = "Nightly pass 2026-10-22\n"
    assert brief.stale_prefix(text, dt.date(2026, 10, 22)) == ""
    assert "from 2026-10-22" in brief.stale_prefix(text, dt.date(2026, 10, 23))
