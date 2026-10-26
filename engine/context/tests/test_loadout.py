"""loadout -- replaying a pi session into the prompt every request carries.

The reader has four rules that are easy to get subtly wrong, and each one is a
silent over- or under-count rather than an error: sections overwrite by name,
`null` deletes one, `toolsRemoved` runs before `toolsAdded`, and a truncated
line (a session being written as this runs) is skipped rather than fatal. They
are pinned here against fixtures, so the gate needs no live session.

The caps are policy, so they are tested as policy: a fixture over a cap must
name the owner, a cap that holds must stay silent, and a harness with no
declared budget must not inherit another's.
"""
import json
import os

import pytest

from context import loadout
from lib import roots


def tool(name, description="", parameters=None):
    return {"name": name, "description": description,
            "parameters": parameters or {"type": "object", "properties": {}}}


def system(**message):
    return {"type": "message", "message": {"role": "system", "content": "", **message}}


def write(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def test_sections_and_tools_replay(tmp_path):
    path = write(tmp_path / "s.jsonl", [
        {"type": "session", "cwd": "/home/u/proj"},
        {"type": "message", "message": {"role": "user", "content": "hi"}},
        system(sections={"preamble": "A" * 100, "cwd": "<cwd>x</cwd>"},
               toolsAdded=[tool("read", "r" * 10), tool("mcp", "m" * 10)]),
        # a repeat must not duplicate a section or a tool
        system(sections={"preamble": "A" * 100}),
        # a patch: one section removed, one tool swapped for two
        system(sections={"cwd": None, "project_context": "P" * 50},
               toolsRemoved=[tool("mcp")],
               toolsAdded=[tool("web_search", "w" * 10), tool("ask_user", "q" * 10)]),
    ])
    lo = loadout.read(path)
    assert lo.cwd == "/home/u/proj"
    assert lo.sections == {"preamble": "A" * 100, "project_context": "P" * 50}
    assert [t.name for t in lo.tools] == ["read", "web_search", "ask_user"]
    assert lo.section_chars == 150
    assert lo.tool_chars == sum(
        len(json.dumps(tool(n, d), ensure_ascii=False))
        for n, d in (("read", "r" * 10), ("web_search", "w" * 10), ("ask_user", "q" * 10)))
    assert lo.total_chars == lo.section_chars + lo.tool_chars


def test_tool_reserialized_not_remeasured(tmp_path):
    """The stored declaration is counted as stored: a tool that appears twice
    across messages is counted once, at its latest declaration."""
    path = write(tmp_path / "s.jsonl", [
        system(toolsAdded=[tool("read", "short")]),
        system(toolsAdded=[tool("read", "a much longer description")]),
    ])
    lo = loadout.read(path)
    assert len(lo.tools) == 1
    assert lo.tools[0].chars == len(json.dumps(tool("read", "a much longer description")))


def test_truncated_line_is_skipped(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(json.dumps(system(toolsAdded=[tool("read")])) + "\n{\"type\": \"mess")
    lo = loadout.read(path)
    assert [t.name for t in lo.tools] == ["read"]


def test_system_content_counts_toward_sections(tmp_path):
    """A system message may carry prose in `content` as well as `sections`; pi
    sends both in one string, so both are section bytes here."""
    path = write(tmp_path / "s.jsonl", [
        {"type": "message", "message": {"role": "system", "content": "framing " * 10,
                                        "sections": {"preamble": "A" * 10}}},
    ])
    lo = loadout.read(path)
    assert lo.section_chars == 80 + 10


def test_budgets_name_the_owner(tmp_path):
    path = write(tmp_path / "s.jsonl", [
        system(sections={"preamble": "x" * 40000},
               toolsAdded=[tool("read", "y" * 40000)]),
    ])
    lo = loadout.read(path)
    problems = loadout.check(lo, {"pi": {"sections": 100, "tools": 100}})
    assert len(problems) == 2
    assert any(p.startswith("sections:") for p in problems)
    assert any(p.startswith("tools:") for p in problems)
    assert loadout.check(lo, {"pi": {"sections": 10**9, "tools": 10**9}}) == []
    assert loadout.check(lo, {"other": {"tools": 1}}) == []


def test_session_lookup(tmp_path):
    assert loadout.newest_session("/nope/x", tmp_path) is None
    directory = tmp_path / loadout.slug("/home/u/proj")
    directory.mkdir(parents=True)
    assert directory.name == "--home-u-proj--"
    older, newest = directory / "a.jsonl", directory / "b.jsonl"
    older.write_text("")
    newest.write_text("")
    os.utime(older, (1_000_000, 1_000_000))
    assert loadout.newest_session("/home/u/proj", tmp_path) == newest


def test_the_live_repo_session_parses():
    """The number the caps were written against. Skipped on a machine with no
    pi sessions for this cwd -- a fresh clone has none, and that is not a
    failure of the reader."""
    path = loadout.newest_session(str(roots.INSTALL))
    if path is None:
        pytest.skip("no pi session for this repo on this machine")
    lo = loadout.read(path)
    assert lo.total_chars > 0
    assert [t.name for t in lo.tools], "a session with no tool declarations"
