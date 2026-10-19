"""pointers -- the instrument that measures whether a pointer was followed.

The measurement matters more than the module, so the tests are about the ways it
can lie. Each one is a way the number would have been wrong in a direction that
looks like a finding:

  normalisation   one file counted under four spellings, which moves it out of
                  the class it belongs in and hides how often it is reached.
  anchoring       the index resolved against the wrong root, which drops every
                  entry and reclassifies a whole branch as cold. This is the bug
                  the first version had.
  nesting         a harness wrapping the payload one level deeper, which
                  under-counts silently.
  channels        counting only the read tool, when the measured ratio between
                  read and bash is roughly 1:10.
  time            the whole-corpus number read as a verdict on the new
                  mechanisms, when the corpus mostly predates them.
"""
import json
import pathlib

import pytest

from context import pointers


@pytest.fixture
def agents(tmp_path):
    a = tmp_path / "memory"
    (a / "knowledge" / "meta").mkdir(parents=True)
    # The router at the repository root and the user's files under `config/`,
    # as since R3b.
    (tmp_path / "CONTEXT.md").write_text(
        "# Router\n\n| q | r |\n|---|---|\n"
        "| a fact | `memory/knowledge/INDEX.md`, then the one leaf it names |\n"
        "| tone | `config/practice/conventions/collaboration.md` |\n")
    practice = tmp_path / "config" / "practice"
    (practice / "conventions").mkdir(parents=True)
    (practice / "conventions" / "collaboration.md").write_text("# Collaboration\n")
    (practice / "user").mkdir()
    (practice / "user" / "user-identity.md").write_text("# Identity\n")
    (a / "knowledge" / "INDEX.md").write_text(
        "Paths are relative to `~/06_SYSTEM/memory/knowledge/`.\n\n"
        "| `meta/consolidation-cycle.md` | the pass | consolidation |\n")
    (a / "knowledge" / "meta" / "consolidation-cycle.md").write_text("# Pass\n")
    (a / "knowledge" / "cold-leaf.md").write_text("# Cold\n")
    return a


def _transcript(corpus, name, calls):
    """One staged transcript. `calls` is [(tool_name, input_dict)]."""
    corpus.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "user", "message": {"content": "hi"}}]
    for tool, inp in calls:
        rows.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": tool, "input": inp}]}})
    (corpus / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")


# ── normalisation: one file, one key ─────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "memory/knowledge/meta/x.md",
    "./memory/knowledge/meta/x.md",
    "~/06_SYSTEM/memory/knowledge/meta/x.md",
    "/home/rg/06_SYSTEM/memory/knowledge/meta/x.md",
    "memory/knowledge/meta/x.md`",
    "'memory/knowledge/meta/x.md',",
])
def test_every_spelling_of_a_path_collapses_to_one_key(raw):
    assert pointers.normalise(raw) == "memory/knowledge/meta/x.md"


@pytest.mark.parametrize("raw,key", [
    ("agents/knowledge/meta/x.md", "memory/knowledge/meta/x.md"),
    ("~/06_SYSTEM/agents/user/user-identity.md",
     "config/practice/user/user-identity.md"),
    ("cat agents/conventions/voice.md", "config/practice/conventions/voice.md"),
    ("~/06_SYSTEM/agents/CONTEXT.md", "CONTEXT.md"),
    ("~/06_SYSTEM/CONTEXT.md", "CONTEXT.md"),
])
def test_a_read_from_before_r3b_lands_where_the_file_went(raw, key):
    """The verbatim tier predates the move. Without the bridge, every read
    of the vault before 2026-10-09 falls out of scope."""
    assert pointers.normalise(raw) == key


@pytest.mark.parametrize("raw", [
    "engine/context/pointers.py",   # not under memory/
    "memory/../secrets.md",                       # escapes the tree
    "memory/",                                    # names nothing
    "~/.config/hypr/x.md",                        # a `config/` not ours
    "~/06_SYSTEM/engine/x.md",                    # in the repo, not the tree
    "memory/pazras_memory/tree.py",               # the engine, before R2
    "src/config/settings.py",                     # some project's config/
])
def test_non_agents_paths_are_dropped(raw):
    assert pointers.normalise(raw) is None


# ── the two anchors ──────────────────────────────────────────────────────────

def test_the_index_is_resolved_against_knowledge_not_agents(agents):
    """`INDEX.md` says in its own header that its paths are relative to
    `knowledge/`. Resolving them against `memory/` drops every row, and the
    whole knowledge branch silently reports as cold -- which is what the first
    version of this did."""
    routed = pointers.routing_targets(agents)
    assert "memory/knowledge/meta/consolidation-cycle.md" in routed
    assert "memory/knowledge/INDEX.md" in routed


def test_the_routing_table_is_resolved_against_the_repository(agents):
    assert "config/practice/conventions/collaboration.md" in \
        pointers.routing_targets(agents)


# ── classification ───────────────────────────────────────────────────────────

def test_always_on_wins_over_routed(agents):
    """`CONTEXT.md` names `conventions/collaboration.md` in its table AND is in
    the always-loaded set. Always-on is the stronger statement, and the order is
    what stops the answer depending on which set is checked first."""
    routed = pointers.routing_targets(agents)
    always = set(pointers._always_loaded())
    assert pointers.classify("config/practice/conventions/collaboration.md",
                             routed, always) \
        == pointers.ALWAYS_ON


def test_a_stale_path_is_its_own_class(agents):
    """Absent from the tree is a different finding from reached-without-a-router.
    `knowledge/operations/consolidation-cycle.md` is the live example: the
    single most-referenced path in the corpus, and it moved."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("Bash", {"command": "cat memory/knowledge/operations/"
                             "consolidation-cycle.md"})])
    rep = pointers.scan(corpus, agents)
    classes = pointers.resolve_classes(rep, agents)
    assert classes["memory/knowledge/operations/consolidation-cycle.md"] == \
        pointers.STALE


# ── channels: both, or the measurement is blind ──────────────────────────────

def test_both_channels_are_counted(agents):
    """Pointer-following happens through `bash` (`cat`/`sed`) far more often than
    through the harness's read tool -- roughly 10:1 in the live corpus. A counter
    that instruments only the read tool measures almost nothing and reports it as
    a finding."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("Read", {"file_path": "memory/knowledge/meta/consolidation-cycle.md"}),
        ("Bash", {"command": "cat memory/knowledge/meta/consolidation-cycle.md"}),
        ("mcp__custom-tools__read",
         {"file_path": "memory/knowledge/meta/consolidation-cycle.md"}),
        ("bash", {"command": "sed -n 1,9p memory/knowledge/cold-leaf.md"}),
    ])
    rep = pointers.scan(corpus, agents)
    ch = rep.hits["memory/knowledge/meta/consolidation-cycle.md"]
    assert (ch.read, ch.bash) == (2, 1), "both read spellings and the shell"
    assert rep.hits["memory/knowledge/cold-leaf.md"].bash == 1


def test_a_payload_nested_deeper_is_still_counted(agents):
    """A harness may wrap its input. Matching only top-level strings under-counts
    without saying so."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("Bash", {"params": {"args": {"cmd": "cat memory/knowledge/cold-leaf.md"}}}),
    ])
    assert pointers.scan(corpus, agents).hits["memory/knowledge/cold-leaf.md"].bash == 1


def test_non_file_tools_are_ignored(agents):
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("TodoWrite", {"todos": [{"content": "read memory/knowledge/cold-leaf.md"}]}),
    ])
    assert pointers.scan(corpus, agents).hits == {}


# ── the MCP counter, and time ────────────────────────────────────────────────

def test_mcp_memory_calls_are_counted_even_though_they_are_not_files(agents):
    """The one tool built for pointer-following. It has been called twice ever,
    and a report that only counted file reads could not say that."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("mcp__familiar-mcp__grep", {"query": "x"}),
        ("mcp__familiar-mcp__journal_search", {"query": "y"}),
    ])
    rep = pointers.scan(corpus, agents)
    assert sum(rep.mcp_calls.values()) == 2


def test_the_window_excludes_sessions_outside_it(agents):
    """The corpus mostly predates `knowledge/INDEX.md` and the MCP server, so the
    whole-corpus number is a baseline for the OLD regime. Comparing it to the new
    mechanisms is the mistake this argument exists to prevent."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl",
                [("Bash", {"command": "cat memory/knowledge/cold-leaf.md"})])
    _transcript(corpus, "20260912T000000Z_claude_s2.jsonl",
                [("Bash", {"command": "cat memory/knowledge/cold-leaf.md"})])
    assert pointers.scan(corpus, agents).sessions == 2
    assert pointers.scan(corpus, agents, since="2026-09-11").sessions == 1
    assert pointers.scan(corpus, agents, until="2026-09-10").sessions == 1


def test_the_session_date_comes_from_the_capture_paths_own_naming(agents):
    """Not from the transcript body, so it cannot disagree with the record."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260830T212745Z_claude_uuid.jsonl", [])
    rep = pointers.scan(corpus, agents)
    assert rep.sessions == 1
    assert pointers._date_of(corpus / "20260830T212745Z_claude_uuid.jsonl") \
        == "2026-08-30"


# ── the live tree ────────────────────────────────────────────────────────────

def test_the_cold_class_is_not_silently_empty_on_the_real_tree():
    """A classifier that returns nothing is the failure mode this whole module is
    about: it would report 'pointers are never followed cold' as a finding."""
    root = pathlib.Path(__file__).resolve().parents[3] / "memory"
    routed = pointers.routing_targets(root)
    assert len(routed) > 10, "the routing table and index produced nothing"
    assert "memory/knowledge/system/consolidation/consolidation-cycle.md" in routed


# ── heredocs are stdin, not argv ─────────────────────────────────────────────

def test_a_heredoc_body_is_not_a_read(agents):
    """A command WRITING a file that happens to mention a path looks identical to
    a command opening it, and the measured share is 18%. It distorts the
    always-on class worst, because those are the files most often written about
    -- which is the class that decides the always-on question."""
    corpus = agents.parent / "data" / "transcripts"
    (agents / "knowledge" / "cold-leaf.md").write_text("# Cold\n")
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("Bash", {"command":
                  "cat > /tmp/doc.md <<'EOF'\n"
                  "# Notes\n"
                  "See memory/knowledge/cold-leaf.md for the detail.\n"
                  "EOF\n"}),
    ])
    assert pointers.scan(corpus, agents).hits == {}, (
        "a heredoc body is stdin, not an argument")


def test_a_real_argument_on_the_same_line_as_a_heredoc_still_counts(agents):
    """The opening line IS argv: `cat memory/... <<EOF` reads the file and takes
    its stdin from a heredoc."""
    corpus = agents.parent / "data" / "transcripts"
    _transcript(corpus, "20260901T000000Z_claude_s1.jsonl", [
        ("Bash", {"command":
                  "cat memory/knowledge/cold-leaf.md <<'EOF'\n"
                  "memory/knowledge/meta/consolidation-cycle.md\n"
                  "EOF\n"}),
    ])
    rep = pointers.scan(corpus, agents)
    assert "memory/knowledge/cold-leaf.md" in rep.hits
    assert "memory/knowledge/meta/consolidation-cycle.md" not in rep.hits


@pytest.mark.parametrize("opener", ["<<EOF", "<<-EOF", "<<'EOF'", '<<"EOF"'])
def test_every_heredoc_spelling_is_stripped(opener):
    cmd = f"cat > x.md {opener}\nmemory/knowledge/cold-leaf.md\nEOF\n"
    assert "cold-leaf" not in pointers.strip_heredocs(cmd)


def test_an_unterminated_heredoc_does_not_swallow_the_rest(agents):
    """A truncated command must not silently drop everything after it."""
    assert pointers.strip_heredocs("cat <<EOF\nbody\nno terminator") == \
        "cat <<EOF"


# ── touched_paths: the SECOND scope (C2) ────────────────────────────────────
#
# `scan` answers "was the pointer followed" about the knowledge tree's own
# homes, and it is scoped to them on purpose. `touches:` answers "what did this
# session work on", where `engine/` is the point -- so these tests pin the two
# scopes apart as much as they pin the extraction.

def test_the_two_scopes_disagree_about_engine_and_that_is_the_design():
    raw = "engine/knowledge/journal_index.py"
    assert pointers.normalise(raw) is None                  # routing scope: not ours
    assert pointers.normalise(raw, pointers._TOUCH_ANCHOR, require=None) == raw


def test_touched_paths_finds_engine_files_the_report_never_sees(tmp_path):
    p = tmp_path / "c.jsonl"
    pointers_calls = [("Read", {"file_path": "/home/rg/06_SYSTEM/engine/knowledge/journal_index.py"}),
                      ("Bash", {"command": "cd ~/06_SYSTEM && git diff engine/context/mcp_server.py"})]
    _transcript(tmp_path / "corpus", "c.jsonl", pointers_calls)
    got = pointers.touched_paths(tmp_path / "corpus" / "c.jsonl")
    assert got == {"engine/knowledge/journal_index.py", "engine/context/mcp_server.py"}


def test_touched_paths_reads_every_tool_not_only_read_and_bash(tmp_path):
    """An `Edit` names a file as surely as a `Read` does, and a facet built
    from reads alone would miss the file the session was changing."""
    d = tmp_path / "corpus"
    _transcript(d, "e.jsonl", [
        ("Edit", {"file_path": "/home/rg/06_SYSTEM/config/knowledge/facets.yaml",
                  "old_string": "a", "new_string": "b"}),
        ("Write", {"file_path": "/home/rg/06_SYSTEM/memory/knowledge/x.md"}),
        ("Bash", {"command": "ls vendor/"}),
    ])
    got = pointers.touched_paths(d / "e.jsonl")
    assert "config/knowledge/facets.yaml" in got and "memory/knowledge/x.md" in got


def test_touched_paths_reads_only_the_keys_that_name_a_file(tmp_path):
    """An `Edit`'s replacement text is prose. Scanning it would credit a session
    with every path a document it wrote happens to mention."""
    d = tmp_path / "corpus"
    _transcript(d, "p.jsonl", [
        ("Edit", {"file_path": "/home/rg/06_SYSTEM/engine/host/x.sh",
                  "edits": [{"oldText": "see memory/knowledge/INDEX.md",
                             "newText": "memory/skills/CONTEXT.md is the router"}]}),
    ])
    got = pointers.touched_paths(d / "p.jsonl")
    assert got == {"engine/host/x.sh"}


def test_touched_paths_strips_a_heredoc_body(tmp_path):
    """A command WRITING a document that mentions paths is not a session
    touching them -- the same 18% inflation `scan` had to learn."""
    d = tmp_path / "corpus"
    _transcript(d, "h.jsonl", [
        ("Bash", {"command": "cat > engine/host/notes.md <<'EOF'\n"
                             "memory/knowledge/deep/leaf.md\nEOF\n"}),
    ])
    assert pointers.touched_paths(d / "h.jsonl") == {"engine/host/notes.md"}


def test_touched_paths_keeps_only_what_is_in_this_repository(tmp_path):
    d = tmp_path / "corpus"
    _transcript(d, "o.jsonl", [
        ("Read", {"file_path": "/tmp/scratch.md"}),
        ("Read", {"file_path": "/home/rg/02_AREAS/B_Tech/dotfiles/README.md"}),
        ("Read", {"file_path": "/home/rg/06_SYSTEM/engine/backup/x.sh"}),
    ])
    assert pointers.touched_paths(d / "o.jsonl") == {"engine/backup/x.sh"}


def test_touched_paths_widens_the_extensions_the_report_does_not_need(tmp_path):
    """The report indexes `.md` prose about the knowledge tree; a session edits
    a timer unit and a TypeScript guard, and a `.md`-only scan would call that
    session empty."""
    d = tmp_path / "corpus"
    _transcript(d, "w.jsonl", [
        ("Read", {"file_path": "/home/rg/06_SYSTEM/config/schedule/familiar-memory.timer"}),
        ("Read", {"file_path": "/home/rg/06_SYSTEM/engine/boundaries/pi-guard/index.ts"}),
    ])
    assert pointers.touched_paths(d / "w.jsonl") == {
        "config/schedule/familiar-memory.timer", "engine/boundaries/pi-guard/index.ts"}


def test_scan_counts_a_pi_transcript(tmp_path):
    """The gap C2 found: `scan` read only `tool_use` blocks, so every PI session
    -- 19 of the 314 staged -- was invisible to the report, and the failure was
    silent (a harness that yields nothing looks like a session that read
    nothing). The walk is shared now (`transcripts._turns`)."""
    corpus = tmp_path / "corpus"
    corpus.mkdir(parents=True)
    rows = [
        {"type": "session", "id": "sess-pi", "cwd": "/home/rg/06_SYSTEM"},
        {"type": "message", "message": {"role": "assistant", "content": [
            {"type": "toolCall", "name": "bash",
             "arguments": {"command": "cat memory/knowledge/cold-leaf.md"}}]}},
    ]
    (corpus / "20260905T191855Z_pi_sess-pi.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    agents = tmp_path / "memory"
    (agents / "knowledge").mkdir(parents=True)
    (agents / "knowledge" / "cold-leaf.md").write_text("# Cold\n")
    rep = pointers.scan(corpus, agents)
    assert rep.calls == 1
    assert rep.hits["memory/knowledge/cold-leaf.md"].bash == 1


def test_session_of_keys_on_the_harness_session_id():
    import pathlib
    from context import pointers
    assert pointers.session_of(pathlib.Path("20261009T192717Z_opencode_ses_ab_c.jsonl")) == "ses_ab_c"
    assert pointers.session_of(pathlib.Path("20260830T212745Z_claude_a3-19.jsonl")) == "a3-19"
    assert pointers.session_of(pathlib.Path("odd.jsonl")) == "odd"
