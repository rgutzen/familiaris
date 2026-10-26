"""waves: the order, the overlap split, and the refusals, over hand-written SPECS.md text."""
import pytest

from orchestration import specs, waves

KEYS = ("touches", "depends")


def item(id_, touches, depends="—", mark=" "):
    return (f"- [{mark}] **{id_} · title {id_}.** prose\n"
            f"  touches: {touches}\n  depends: {depends}\n"
            "  model: claude-sonnet-5-5\n  verify: true\n")


def ids(text):
    return [[it.id for it in w] for w in waves.build(specs.parse(text, KEYS))]


def test_waves_independent_share_one_wave():
    assert ids(item("1a", "a.py") + item("1b", "b.py")) == [["1a", "1b"]]


def test_waves_chain_is_one_item_per_wave():
    text = item("1a", "a.py") + item("1b", "b.py", "1a") + item("1c", "c.py", "1b")
    assert ids(text) == [["1a"], ["1b"], ["1c"]]


def test_waves_diamond_is_three_waves():
    text = (item("1a", "a.py") + item("1b", "b.py", "1a") + item("1c", "c.py", "1a")
            + item("1d", "d.py", "1b, 1c"))
    assert ids(text) == [["1a"], ["1b", "1c"], ["1d"]]


def test_waves_overlap_pushes_later_item_on():
    assert ids(item("1a", "engine/x.py") + item("1b", "engine/x.py")) == [["1a"], ["1b"]]


def test_waves_glob_and_literal_overlap():
    assert ids(item("1a", "engine/x/**") + item("1b", "engine/x/y.py")) == [["1a"], ["1b"]]


def test_waves_disjoint_touches_stay_together():
    text = item("1a", "engine/a/**, docs/a.md") + item("1b", "engine/b/**, docs/b.md")
    assert ids(text) == [["1a", "1b"]]


def test_waves_split_never_breaks_depends():
    # 1b collides with 1a and is pushed; 1c needs 1b, so it must follow it.
    text = item("1a", "x.py") + item("1b", "x.py") + item("1c", "z.py", "1b")
    assert ids(text) == [["1a"], ["1b"], ["1c"]]


def test_waves_pushed_item_keeps_its_place_in_file_order():
    text = item("1a", "x.py") + item("1b", "x.py") + item("1c", "y.py")
    assert ids(text) == [["1a", "1c"], ["1b"]]


def test_waves_cycle_refused_by_name():
    text = item("3b", "a.py", "3d") + item("3d", "b.py", "3b")
    with pytest.raises(waves.CycleError) as e:
        waves.build(specs.parse(text, KEYS))
    assert str(e.value) == "dependency cycle: 3b -> 3d -> 3b"


def test_waves_self_dependency_is_a_cycle():
    with pytest.raises(waves.CycleError, match="1a -> 1a"):
        waves.build(specs.parse(item("1a", "a.py", "1a"), KEYS))


def test_waves_none_spellings():
    assert ids(item("1a", "a.py", "—") + item("1b", "b.py", "-")) == [["1a", "1b"]]


def test_waves_done_dependency_is_satisfied_and_unscheduled():
    text = item("1a", "a.py", mark="x") + item("1b", "b.py", "1a")
    assert ids(text) == [["1b"]]


def test_waves_unknown_dependency_named():
    with pytest.raises(waves.UnknownDependency, match="1b.*1z"):
        waves.build(specs.parse(item("1b", "b.py", "1z"), KEYS))


def test_waves_overlap_rules():
    assert waves.overlaps("engine/x", "engine/x/y.py")
    assert waves.overlaps("engine/x/**", "engine/x")
    assert waves.overlaps("engine/*.py", "engine/a.py")
    assert waves.overlaps("engine/x/**", "engine/x/y/*.py")
    assert not waves.overlaps("engine/x/**", "engine/y/**")
    assert not waves.overlaps("engine/x.py", "engine/xy.py")
    assert not waves.overlaps("engine/x", "engine/xy/z.py")


def test_waves_deterministic():
    text = (item("1a", "a.py") + item("1b", "a.py", "1a") + item("1c", "c.py")
            + item("1d", "d.py", "1c"))
    assert ids(text) == ids(text)
