"""generated_block.splice -- the properties both prior copies needed and only
one of them (partially) had: idempotency, surviving a marker rename, collapsing
duplicates, and one blank line before the block regardless of which branch runs.
"""
import re

from lib.generated_block import splice

BLOCK_ANY = re.compile(r"<!-- BEGIN X.*?<!-- END X -->\n?", re.S)


def block(tag="current"):
    return f"<!-- BEGIN X {tag} -->\npayload\n<!-- END X -->"


# ── idempotency is the acceptance test, same as l1.py's ───────────────────────

def test_compile_then_compile_again_is_stable():
    first = splice("user prose\n", block(), BLOCK_ANY)
    again = splice(first, block(), BLOCK_ANY)
    assert again == first


# ── the two 2026-09-04 bugs, now pinned once for every caller ────────────────

def test_marker_rename_does_not_orphan_old_block():
    old = "<!-- BEGIN X OLD -->\njunk\n<!-- END X -->\n"
    desired = splice(old + "user prose\n", block(), BLOCK_ANY)
    assert "OLD" not in desired
    assert "junk" not in desired
    assert "user prose" in desired


def test_second_block_is_removed_not_duplicated():
    doubled = block() + "\n" + block()
    desired = splice(doubled, block(), BLOCK_ANY)
    assert desired.count("BEGIN X") == 1
    assert desired.count("END X") == 1


# ── placement: exactly one blank line before the block, every branch ────────

def test_fresh_append_to_empty_file_has_no_leading_blank():
    assert splice("", block(), BLOCK_ANY) == block() + "\n"


def test_fresh_append_adds_a_blank_line_before_the_block():
    assert splice("prose\n", block(), BLOCK_ANY) == "prose\n\n" + block() + "\n"


def test_fresh_append_to_text_without_trailing_newline_adds_blank_line():
    assert splice("prose", block(), BLOCK_ANY) == "prose\n\n" + block() + "\n"


def test_fresh_append_does_not_stack_a_second_blank_line():
    assert splice("prose\n\n", block(), BLOCK_ANY) == "prose\n\n" + block() + "\n"


def test_replace_keeps_the_same_one_blank_line_convention():
    """The branch that strips a stale block must leave the file looking exactly
    like the fresh-append branch would have -- this is the drift the two prior
    copies had (one used "\\n", the other "\\n\\n") and neither test suite
    caught, because neither compared its output to the other compiler's."""
    stale = "prose\n" + block("OLD") + "\n"
    replaced = splice(stale, block(), BLOCK_ANY)
    fresh = splice("prose\n", block(), BLOCK_ANY)
    assert replaced == fresh


def test_replacing_the_only_content_leaves_no_orphan_blank_lines():
    assert splice(block("OLD") + "\n", block(), BLOCK_ANY) == block() + "\n"
