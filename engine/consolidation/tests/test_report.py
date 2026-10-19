"""Stage 8's "Needs a decision" rendering, at the numbered-queue contract.

This file has been rewritten once already and the history is the point. The
2026-09-09 version asserted the report carried a copy-pasteable
`dismiss --target=... --kind=... --target-kind=...` command per row, because
`target_kind` was otherwise invisible and acting on a proposal meant reading
stage source. That fixed a real gap.

Item 1e then removed the commands, for a better reason: the ordinal is now the
interface (`decide N`), so a printed command is a SECOND writer -- one that must
be got right by hand and that duplicates `decide`'s dispatch, including the
target_kind the old test was protecting. The property to test moved: not "the
row carries a command" but "the row carries a number, and `decide N` resolves
the same item the row named".
"""
import datetime as dt
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from consolidation import pass_ctx, queue, report  # noqa: E402


class _FakeCtx:
    """Just enough of pass_ctx.Pass for report.render()."""

    def __init__(self, proposals, base=None, dry_run=False):
        self.today = dt.date(2026, 9, 29)
        self.dry_run = dry_run
        self.branch = "main"
        self.aborted = None
        self.stages_run = ["1"]
        self.proposals = proposals
        self.actions = []
        self.notes = []
        self.base = base or pathlib.Path("/nonexistent")

    def loaded_tree(self):
        return None


def _p(kind="dangling-link", target="knowledge-vs-skills",
       what="`related: voice` resolves to no leaf", target_kind="leaf"):
    return pass_ctx.Proposal(stage="5a", kind=kind, target=target, what=what,
                             why="reported, never deleted",
                             target_kind=target_kind)


def test_a_row_is_numbered_one_line_and_carries_no_command():
    """Item 1e's exit criterion, asserted in the render.

    The shape is the spec's: two leading spaces, the ordinal, the kind, the
    target, then `·` and the one-line summary. `why` is NOT in the row -- it is
    paragraphs long for a `decision` item and would wrap the line; it is behind
    `decide N --why`.
    """
    p = _p()
    out = report.render(_FakeCtx([p]))
    assert "dismiss:" not in out
    assert "familiar consolidation dismiss" not in out
    assert "--target=" not in out
    assert "  1  dangling-link  knowledge-vs-skills · `related: voice`" in out
    assert "reported, never deleted" not in out      # the `why` stays out


def test_the_heading_count_equals_the_number_of_rows():
    """The exit criterion's other half: `report --last | grep -c '^ *[0-9]'` must
    equal the report heading's count, or the numbering is not a numbering.

    Matched on the row shape (leading spaces then a digit then two spaces), not
    on `l[:1].isdigit()`: rows are indented, as the spec's example shows.
    """
    import re
    ps = [_p(target="a"), _p(target="b"), _p(kind="extend-leaf", target="c")]
    out = report.render(_FakeCtx(ps))
    assert "(3)" in out
    numbered = [l for l in out.splitlines() if re.match(r"^\s+\d+  ", l)]
    assert len(numbered) == 3


def test_the_rows_are_in_the_queue_order():
    """`decide N` resolves through this order, so a divergence here makes the
    report's item 3 a different item from `decide`'s item 3."""
    ps = [_p(kind="extend-leaf", target="z"), _p(kind="dangling-link", target="a")]
    out = report.render(_FakeCtx(ps))
    # sorted by kind: dangling-link before extend-leaf
    assert out.index("dangling-link") < out.index("extend-leaf")


def test_the_kind_and_target_columns_are_aligned():
    """A ragged list is not a table. The spec's example aligns both fields."""
    import re
    ps = [_p(kind="dangling-link", target="a"),
          _p(kind="dangling-supersession", target="a-much-longer-target")]
    rows = [l for l in report.render(_FakeCtx(ps)).splitlines()
            if re.match(r"^\s+\d+  ", l)]
    starts = {re.search(r"·", l).start() for l in rows}
    assert len(starts) == 1, f"the · column is ragged: {starts}"


def test_every_ordinal_is_reachable_in_the_default_render():
    """The queue's interface is `decide N`, so a hidden row is an item the user
    cannot reach by the only route they have. MAX_LISTED must not apply here --
    a real pass raised 16 items and the default report showed 8, with the other
    eight behind a `... and 8 more` line that carried no numbers at all."""
    import re
    ps = [_p(target=f"t{i}") for i in range(20)]
    out = report.render(_FakeCtx(ps))          # NOT full
    nums = [int(re.match(r"^\s+(\d+)  ", l).group(1))
            for l in out.splitlines() if re.match(r"^\s+\d+  ", l)]
    assert nums == list(range(1, 21)), f"missing ordinals: {nums}"


def test_the_compressed_tail_still_carries_its_number():
    ps = [_p(target=f"t{i}") for i in range(20)]
    out = report.render(_FakeCtx(ps))
    assert "20" in out.split("## Changed")[0]
    assert "compressed" in out


def test_a_small_queue_is_rendered_in_full_with_no_compression_note():
    ps = [_p(target="a"), _p(target="b")]
    out = report.render(_FakeCtx(ps))
    assert "compressed" not in out


def test_the_report_prints_the_queue_digest():
    """Item 1d: `decide` compares against this, so it must be present."""
    out = report.render(_FakeCtx([_p()]))
    assert "digest" in out
    assert queue.digest([]) in out or "`" in out


def test_the_printed_digest_is_the_stored_one(tmp_path):
    its = [queue.as_dict("dangling-link", "knowledge-vs-skills",
                         "`related: voice` resolves to no leaf", "why", "5a",
                         "leaf", "2026-09-29")]
    queue.save(tmp_path, its)
    out = report.render(_FakeCtx([_p()], base=tmp_path))
    assert queue.digest(its) in out, "the report must print what is on disk"


def test_an_empty_queue_says_nothing_rather_than_printing_zero(tmp_path):
    out = report.render(_FakeCtx([]))
    assert "Nothing." in out
