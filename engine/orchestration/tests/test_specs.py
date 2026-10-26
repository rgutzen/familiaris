"""The SPECS.md item contract: the file loads, and an item missing or misusing
a field is named with the item and the field."""
import textwrap

import pytest

from lib import roots
from orchestration import specs

# A test whose subject is this instance's own content skips in a published tree.
INSTANCE = pytest.mark.skipif(
    not roots.instance_here(),
    reason="the track's own SPECS file is under `dev/`, which the "
           "classification omits")

CONTRACT = specs.load_contract()
KEYS = set(CONTRACT["fields"])
MODELS = {"claude-opus-5-5", "deepseek-flash"}

GOOD = textwrap.dedent("""\
    ## Step 1

    - [x] **1a · done already.** No fields needed.
    - [ ] **1b · open.** Prose that mentions touches: in passing.
      touches: engine/x.py, engine/tests/**
      depends: 1a
      model: claude-opus-5-5
      verify: python3 -m pytest engine/tests -q
    - [ ] **1c · the user's.**
      touches: ~/elsewhere/file
      depends: —
      model: user
      verify: manual: the user reads it
    """)


def _findings(text, models=MODELS):
    return specs.validate(specs.parse(text, KEYS), CONTRACT, models)


def test_the_contract_names_four_required_fields_of_known_types():
    required = {n for n, spec in CONTRACT["fields"].items() if spec["required"] == "yes"}
    assert required == {"touches", "depends", "model", "verify"}
    for spec in CONTRACT["fields"].values():
        assert spec["type"] in specs.TYPES


def test_review_is_an_optional_flag_and_only_yes_or_no_passes():
    """dev/schedule 1f: an item may ask a scheduled chain to pause for the user's review."""
    review = CONTRACT["fields"]["review"]
    assert review["type"] == "flag" and review["required"] == "no"
    assert _findings(GOOD) == [], "absent is fine"
    anchor = "  verify: manual: the user reads it\n"
    assert _findings(GOOD.replace(anchor, anchor + "  review: yes\n")) == []
    bad = _findings(GOOD.replace(anchor, anchor + "  review: maybe\n"))
    assert any(f.field == "review" and "yes or no" in f.message for f in bad), bad


def test_a_complete_file_passes():
    assert _findings(GOOD) == []


def test_parse_reads_ids_titles_and_fields():
    items = specs.parse(GOOD, KEYS)
    assert [(i.id, i.done) for i in items] == [("1a", True), ("1b", False), ("1c", False)]
    assert items[1].title == "open"
    assert items[1].fields["depends"] == "1a"


@pytest.mark.parametrize("field", ["touches", "depends", "model", "verify"])
def test_a_stripped_field_is_named_with_its_item(field):
    # Remove the field from item 1b only (its first occurrence).
    lines, removed = [], False
    for line in GOOD.splitlines():
        if not removed and line.startswith(f"  {field}:"):
            removed = True
            continue
        lines.append(line)
    found = _findings("\n".join(lines))
    assert [(f.item, f.field, f.message) for f in found] == [("1b", field, "missing")]


@pytest.mark.parametrize("line,field,fragment", [
    ("  depends: 9z", "depends", "not an item in this file"),
    ("  depends: step one", "depends", "not an item id"),
    ("  depends:", "depends", "empty"),
    ("  model: gpt-9", "model", "not a callable catalogue id"),
    ("  verify: manual:", "verify", "names nothing"),
    ("  touches: ,", "touches", "names no path"),
])
def test_a_bad_value_is_named(line, field, fragment):
    text = GOOD.replace(f"  {field}: " + {"depends": "1a", "model": "claude-opus-5-5",
                                          "verify": "python3 -m pytest engine/tests -q",
                                          "touches": "engine/x.py, engine/tests/**"}[field],
                        line, 1)
    found = _findings(text)
    assert len(found) == 1 and found[0].item == "1b" and found[0].field == field
    assert fragment in found[0].message


def test_without_a_catalogue_any_model_passes():
    assert _findings(GOOD.replace("claude-opus-5-5", "gpt-9"), models=None) == []


def test_a_duplicate_id_and_a_twice_given_field_are_refused():
    dup = GOOD + "- [ ] **1b · again.**\n"
    assert any(f.field == "id" for f in _findings(dup))
    twice = GOOD.replace("  model: user", "  model: user\n  model: user")
    assert [(f.item, f.field) for f in _findings(twice)] == [("1c", "model")]


def test_a_heading_ends_an_item():
    text = GOOD + "\n## Step 2\n\n  model: not-a-field-of-1c\n"
    assert _findings(text) == []


@INSTANCE
def test_the_track_s_own_file_parses():
    path = roots.DEV / "orchestration" / "SPECS.md"
    items = specs.parse(path.read_text(), KEYS)
    assert {"2a", "2b", "2g"} <= {i.id for i in items}
    assert specs.validate(items, CONTRACT, models=None) == []


def test_explain_prints_every_field():
    out = specs.explain(CONTRACT)
    for name in KEYS:
        assert f"{name}:" in out


def test_other_tracks_id_styles_parse():
    text = "- [ ] **M2b · fit**\n- [x] **P0 · classify.**\n"
    assert [(i.id, i.has_id) for i in specs.parse(text, KEYS)] == [("M2b", True), ("P0", True)]


def test_an_open_checkbox_without_an_id_is_refused_not_skipped():
    text = GOOD + "- [ ] **Disk B off-site** — acquire a disk\n- [x] plain done line\n"
    found = _findings(text)
    assert [(f.field, f.message.split(";")[0]) for f in found] == [("id", "no item id")]
    assert found[0].item.startswith("line ")
