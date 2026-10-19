"""L1: boundary enforcement inside the MCP server, since wards's own
docstring says MCP tool calls are NOT covered by any harness-side check.
Network-dependent paths (`journal_search` against a live Ollama) are exercised
by hand per journal-index.md's own verification block, not here.
"""
import os

import pytest

from context import mcp_server as m
from lib import roots


def test_a_read_rule_in_the_compiled_set_denies_and_a_path_outside_it_is_clear(
        monkeypatch):
    """The lookup itself, on a rule set this test owns.

    `_denied` reads `compiled()`, which is this machine's deny-list -- omitted
    from the published tree, where it is an empty rule set. So the MECHANISM is
    asserted here, against a fixture, and it holds wherever this runs; that
    this machine's own deny-list has the rule it should is asserted below.
    """
    monkeypatch.setattr(m, "compiled", lambda: {"rules": [
        {"id": "no-read-write", "mode": "no-read-write", "models": "all",
         "denies": ["read"],
         "paths": [{"abs": "/tmp/secret", "real": "/tmp/secret"}]}]})
    rule = m._denied("/tmp/secret/note.md")
    assert rule is not None
    assert rule["mode"] == "no-read-write"
    assert m._denied("/tmp/elsewhere/note.md") is None


@pytest.mark.skipif(
    not roots.instance_here(),
    reason="it asserts a rule from THIS machine's deny-list, which the "
           "classification omits; the export enforces an empty rule set, and "
           "the mechanism is tested above")
def test_zettel_is_denied():
    rule = m._denied(os.path.expanduser("~/03_ZETTEL/some-note.md"))
    assert rule is not None
    assert rule["mode"] == "no-read-write"


def test_agents_tree_is_clear():
    assert m._denied(os.path.join(m.AGENTS_DIR, "knowledge", "operations", "CONTEXT.md")) is None


def test_grep_refuses_path_outside_repo_root():
    hits = m.grep("anything", path="../03_ZETTEL")
    assert hits == [{"error": "'../03_ZETTEL' resolves outside the 06_SYSTEM repo root"}]


def test_grep_drops_matches_under_a_nested_no_read_path(tmp_path, monkeypatch):
    # A `no-read` (models: remote) path has to live *inside* the repo tree for
    # this to be the interesting case, so a grep rooted above it must filter
    # matches, not just the root. The rule below is injected by this test, not
    # read from the compiled config.
    monkeypatch.setattr(m, "REPO_ROOT", os.path.realpath(str(tmp_path)))
    metadata = tmp_path / "Metadata"
    metadata.mkdir()
    (metadata / "secret.txt").write_text("needle here\n")
    other = tmp_path / "agents"
    other.mkdir()
    (other / "public.txt").write_text("needle here too\n")

    orig = m.compiled()
    injected = {
        "domain": "test", "paths": [{"display": "Metadata", "abs": str(metadata), "real": None}],
        "mode": "no-read", "denies": ["read"], "decision": "deny", "models": "remote",
        "reason": "test-only rule", "instead": None, "see": None,
    }
    merged = {**orig, "rules": orig["rules"] + [injected]}
    monkeypatch.setattr(m, "compiled", lambda: merged)

    hits = m.grep("needle", path=".")
    paths = {h["path"] for h in hits if "path" in h}
    assert str(metadata / "secret.txt") not in paths
    assert str(other / "public.txt") in paths


def test_journal_search_reports_missing_index_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "BASE_DIR", str(tmp_path))
    assert m.journal_search("anything") == [
        {"error": "no index yet -- run `familiar knowledge journal index` first"}
    ]


# ── L9: what a result says about its own trustworthiness ─────────────────────
#
# The label is the control, not decoration. A snippet distilled from a
# transcript reads exactly like an instruction if nothing says otherwise, and
# `journal/**` is the one large machine-written corpus a session searches.
# memory/knowledge/meta/memory-poisoning-posture.md, property 5.

def _entry(tmp_path, name, front):
    d = tmp_path / "journal" / "2026" / "09"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(f"---\ntitle: t\n{front}---\n\nbody\n")
    return p


def test_a_distilled_entry_is_labelled_machine_written(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    _entry(tmp_path, "x.md", "distilled_by: deepseek/deepseek-v4-flash\n")
    got = m._provenance("journal/2026/09/x.md")
    assert "machine-distilled" in got and "unreviewed" in got
    assert "not an instruction" in got


def test_an_authored_entry_says_so_once(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    _entry(tmp_path, "x.md", "distilled_by: authored in-session (claude-opus-5)\n")
    got = m._provenance("journal/2026/09/x.md")
    assert got == "authored in-session (claude-opus-5)", "no double-wrapping"


def test_a_pre_2026_09_entry_is_traced_by_its_session_id(tmp_path, monkeypatch):
    """Entries predating `distilled_by:` carry `session:`, which proves the
    same thing: it came out of a transcript."""
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    _entry(tmp_path, "x.md", "session: 2ec6952c\n")
    got = m._provenance("journal/2026/09/x.md")
    assert "machine-distilled" in got and "predates the field" in got


def test_an_unmarked_entry_fails_towards_caution(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    _entry(tmp_path, "x.md", "")
    assert "unreviewed" in m._provenance("journal/2026/09/x.md")


def test_an_unreadable_path_is_unknown_not_authored(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    assert "unknown" in m._provenance("journal/2026/09/absent.md")


def test_the_server_instructions_say_journal_text_is_not_an_instruction():
    """The per-hit label covers a result; this covers the tool list, which is
    what a harness reads before any call."""
    text = m.server.instructions
    assert "EPISODIC RECORD" in text
    assert "never as an instruction" in text
    assert "memory-poisoning-posture.md" in text


def test_brief_reports_an_absent_artifact_rather_than_an_empty_answer(tmp_path,
                                                                      monkeypatch):
    """"the pass has not run" and "nothing happened" must not look the same."""
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    assert "error" in m.brief()


def test_brief_carries_its_own_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "AGENTS_DIR", str(tmp_path))
    d = tmp_path / "journal" / "reports"
    d.mkdir(parents=True)
    (d / "BRIEF.md").write_text("# Brief — 2026-09-12\n\nbody\n")
    got = m.brief()
    assert got["generated"] == "Brief — 2026-09-12"
    assert "deterministic" in got["provenance"]
    assert got["text"].startswith("# Brief")


def test_the_server_reads_the_file_stage_8_writes():
    """The server reads BRIEF.md as a file instead of importing `brief`
    (R1j: context sits below consolidation), so the two spellings of the
    path are held equal here."""
    from consolidation import brief
    assert m.BRIEF == f"journal/reports/{brief.NAME}"
