"""`_miniyaml` rejects what its docstring says it rejects.

Flow collections used to load as raw text -- `modes: {no-read: [read]}` arrived
as the string `'{no-read: [read]}'`. A config that quietly means something other
than it looks like is the failure this parser exists to prevent, and a
vocabulary file (boundaries 2d) is where someone writes a flow list.
"""
import pytest

from lib import _miniyaml


@pytest.mark.parametrize("text", ["a: [1, 2]\n", "a: {x: 1}\n", "a:\n  - [1, 2]\n",
                                  "a: [b, c]  # comment\n"])
def test_a_flow_collection_raises(text):
    with pytest.raises(_miniyaml.YamlError, match="flow collections"):
        _miniyaml.load(text)


@pytest.mark.parametrize("text,key,want", [
    ('a: "[not a list]"\n', "a", "[not a list]"),        # a quoted scalar
    ("a: text with [ brackets\n", "a", "text with [ brackets"),
    ("a: -i\n", "a", "-i"),
    ("a: {x: 1}\n".replace("{x: 1}", "'{x: 1}'"), "a", "{x: 1}"),
])
def test_only_a_leading_flow_collection_is_flow(text, key, want):
    assert _miniyaml.load(text)[key] == want


def test_the_block_form_still_reads():
    got = _miniyaml.load("modes:\n  no-read: [read]\n" if False else
                         "modes:\n  no-read:\n    - read\n")
    assert got == {"modes": {"no-read": ["read"]}}
