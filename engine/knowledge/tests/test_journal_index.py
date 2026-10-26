"""The journal index's two invariants and its one trap.

WHY THIS FILE EXISTS AT ALL. `journal_index` is the module that talks to
Ollama and writes a cache outside the repo, and it had no test -- so every
change to it was verified by running it against the live corpus, which is how
a 1,514-chunk rebuild becomes part of a unit test's feedback loop. The seam is
one function wide (`embed`), and every test here stubs it: a test that needs a
model server is a test that passes on one machine and fails everywhere else.

THE TRAP. A facet is a key on a chunk, and Python does not error on a missing
key -- it returns False. So an index built before `branch` existed answers a
filtered search with ZERO hits and no error, and a search that used to work
looks like a search with nothing to find. `test_the_schema_stamp_forces_a_
rebuild` writes that index by hand and asserts the rebuild, because the
failure mode has no other symptom.

What is NOT tested here: the numbers. `branch_of_cwd` is asserted against
R1h's four CLASSES; the split over the live corpus (170/20/55/26 on
2026-10-09) is a measurement, and `journal search`'s exit records it.
"""
import io
import json
import os
import pathlib
import urllib.error

import pytest

from knowledge import journal_index as ji
from knowledge import ontology

# The real `_post_json`, kept before the autouse fixture replaces it: the error
# classification tests drive it through a stubbed `urlopen`, never a socket.
_REAL_POST_JSON = ji._post_json
_REAL_EMBED = ji.embed

ENTRY = "# Title\n\n## What was done\n\nrestic backup ran here\n"

# R1h's four classes, as cwd values. Built from the real home because `build()`
# derives the facet from the machine it runs on -- the same reason the
# production path cannot be made hermetic, stated rather than hidden.
HOME = pathlib.Path.home()
SYSTEM_CWD = str(HOME / ji.SYSTEM_DIR)
PROJECT_CWD = str(HOME / ji.PROJECTS_DIR / "demo")
AREA_CWD = str(HOME / ji.AREAS_DIR / "B_Tech")


# ── the seam ─────────────────────────────────────────────────────────────────

VOCAB = ("restic", "backup", "journal", "facet")


def _stub_embed(texts, model=""):
    """A deterministic stand-in: a bag of four words, so ranking is real
    (a query about restic outranks a chunk that never says it) without a
    model, a port, or a machine that has the weights pulled."""
    return [[float(t.lower().count(w)) for w in VOCAB] for t in texts]


@pytest.fixture(autouse=True)
def _no_ollama(monkeypatch):
    monkeypatch.setattr(ji, "_post_json", _raise_ollama)
    monkeypatch.setattr(ji, "embed", _stub_embed)


def _raise_ollama(*_a, **_kw):
    raise AssertionError("a test reached for Ollama; stub `embed` instead")


# ── fixtures ─────────────────────────────────────────────────────────────────

def _entry(memory: pathlib.Path, rel: str, cwd=None, touches=None) -> pathlib.Path:
    p = memory / "journal" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = []
    if cwd is not None:
        fm.append(f"cwd: {cwd}")
    if touches:
        fm.append("touches: [" + ", ".join(touches) + "]")
    head = ("---\ntitle: t\ndate: 2026-10-09\n" + "\n".join(fm)
            + "\n---\n\n") if fm else ""
    p.write_text(head + ENTRY)
    return p


@pytest.fixture
def memory(tmp_path):
    """Four entries, one per class of `cwd:`, plus a router that must not be
    indexed at all. Two of them carry `touches:` — a facet only stage 1 writes,
    so a fixture is the only way to see one before the next session is distilled.
    """
    m = tmp_path / "memory"
    _entry(m, "2026/10/2026-10-01_system.md", SYSTEM_CWD,
           touches=["knowledge", "consolidation"])
    _entry(m, "2026/10/2026-10-02_project.md", PROJECT_CWD)
    _entry(m, "2026/10/2026-10-03_area.md", AREA_CWD, touches=["backup"])
    _entry(m, "2026/10/2026-10-04_none.md")
    _entry(m, "2026/10/2026-10-05_ambiguous.md", str(HOME))
    (m / "journal" / "CONTEXT.md").write_text("# Router\n\nnot a session\n")
    return m


@pytest.fixture
def base(tmp_path):
    return tmp_path / "data"


def _index(base) -> dict:
    return json.loads((base / "journal-index" / "index.json").read_text())


# ── the derivation (R1h) ─────────────────────────────────────────────────────

def test_the_four_classes_of_cwd():
    home = pathlib.Path("/home/someone")
    assert ji.branch_of_cwd("/home/someone/06_SYSTEM/x", home=home) == (ji.SYSTEM, "")
    assert ji.branch_of_cwd("/home/someone/01_PROJECTS/demo/sub", home=home) == \
        (ji.PROJECTS, "demo")
    assert ji.branch_of_cwd("/home/someone/02_AREAS/B_Tech", home=home) == (ji.AREAS, "B")
    assert ji.branch_of_cwd(None, home=home) == (ji.UNKNOWN, "")


@pytest.mark.parametrize("cwd", [
    "/home/someone",                    # the home directory itself
    "/home/someone/03_ZETTEL/notes",     # a PARA directory with no branch
    "/home/someone/06_SYSTEMX",          # a prefix, not a path
    "/tmp", "relative/path", "", None, "~",
])
def test_everything_else_is_unknown_never_guessed(cwd):
    assert ji.branch_of_cwd(cwd, home=pathlib.Path("/home/someone")) == (ji.UNKNOWN, "")


def test_the_branch_values_are_the_registers_branches():
    """The three ids are `subjects.yaml`'s, and this is what keeps them so: a
    rename in the register fails here rather than silently producing a fourth
    value that nothing filters on and no one sees."""
    assert set(ji.BRANCH_VALUES) - {ji.UNKNOWN} == set(ontology.BRANCHES)


def test_a_missing_or_bad_branch_is_an_error_not_an_empty_page():
    assert ji.validate_branch("system") == "system"
    assert ji.validate_branch("unknown") == "unknown"
    with pytest.raises(ValueError):
        ji.validate_branch("backup")           # a SUBJECT, not a branch
    with pytest.raises(ValueError):
        ji.validate_branch("")


# ── the build ────────────────────────────────────────────────────────────────

def test_each_chunk_carries_the_facet_of_its_file(memory, base):
    stats = ji.build(str(memory), str(base))
    idx = _index(base)
    assert "CONTEXT.md" not in " ".join(idx["files"])       # a router is not content
    by_path = {c["path"]: c["branch"] for c in idx["chunks"]}
    assert by_path["journal/2026/10/2026-10-01_system.md"] == ji.SYSTEM
    assert by_path["journal/2026/10/2026-10-02_project.md"] == ji.PROJECTS
    assert by_path["journal/2026/10/2026-10-03_area.md"] == ji.AREAS
    assert by_path["journal/2026/10/2026-10-04_none.md"] == ji.UNKNOWN
    assert stats["files_unmapped"] == 2                     # no `cwd:`, and `~`
    assert idx["schema"] == ji.SCHEMA
    # The per-file record too, so the build log's ambiguous count is checkable
    # without walking the chunks.
    assert idx["files"]["journal/2026/10/2026-10-03_area.md"]["locator"] == "B"


def test_a_second_build_changes_nothing(memory, base):
    first = ji.build(str(memory), str(base))
    second = ji.build(str(memory), str(base))
    assert first["files_changed"] == 5
    assert second["files_changed"] == 0
    assert second["chunks_embedded"] == 0
    assert second["files_removed"] == 0
    assert second["total_chunks"] == first["total_chunks"]


def test_one_changed_entry_rebuilds_one_file(memory, base):
    ji.build(str(memory), str(base))
    p = memory / "journal" / "2026" / "10" / "2026-10-02_project.md"
    p.write_text(p.read_text() + "\n## Later\n\nmore\n")
    os.utime(p, (1_700_000_000, 1_700_000_000))             # coarser than one build
    stats = ji.build(str(memory), str(base))
    assert stats["files_changed"] == 1
    assert stats["chunks_embedded"] == 3                    # frontmatter + two H2s
    left = [c for c in _index(base)["chunks"]
            if c["path"].endswith("2026-10-02_project.md")]
    assert all(c["branch"] == ji.PROJECTS for c in left)


def test_a_removed_entry_drops_its_chunks(memory, base):
    ji.build(str(memory), str(base))
    (memory / "journal" / "2026" / "10" / "2026-10-03_area.md").unlink()
    stats = ji.build(str(memory), str(base))
    assert stats["files_removed"] == 1
    assert not [c for c in _index(base)["chunks"] if c["branch"] == ji.AREAS]


# ── the trap ─────────────────────────────────────────────────────────────────

def test_the_schema_stamp_forces_a_rebuild(memory, base):
    """An index built before the facet is not silently filtered to nothing.

    Hand-written, not simulated: this is exactly what is on disk on the
    machine that upgrades, and the assertion that the old shape returns ZERO
    hits is the bug the stamp exists to catch."""
    ji.build(str(memory), str(base))
    idx = _index(base)
    idx["schema"] = 1
    for c in idx["chunks"]:
        c.pop("branch")
        c.pop("locator")
    (base / "journal-index" / "index.json").write_text(json.dumps(idx))

    assert ji.search(str(memory), str(base), "restic", branch=ji.SYSTEM) == []
    assert ji.summary(str(base))["branches"] == {"(none)": len(idx["chunks"])}

    stats = ji.build(str(memory), str(base))
    assert stats["files_changed"] == 5                      # everything, not the delta
    assert ji.summary(str(base))["schema"] == ji.SCHEMA
    assert ji.search(str(memory), str(base), "restic", branch=ji.SYSTEM)


def test_a_changed_model_still_rebuilds_everything(memory, base):
    ji.build(str(memory), str(base))
    stats = ji.build(str(memory), str(base), model="other-model")
    assert stats["files_changed"] == 5


# ── the pre-filter ───────────────────────────────────────────────────────────

def test_the_filter_selects_a_subset_and_top_counts_within_it(memory, base):
    ji.build(str(memory), str(base))
    everything = ji.search(str(memory), str(base), "restic", top=99)
    assert len(everything) == 9            # five entries: frontmatter block + H2
    one = ji.search(str(memory), str(base), "restic", top=99, branch=ji.PROJECTS)
    assert [h["branch"] for h in one] == [ji.PROJECTS] * 2
    # `top` is the cut INSIDE the subset: asked for one, got one -- not one
    # surviving a post-hoc prune of an unfiltered ranking.
    assert len(ji.search(str(memory), str(base), "restic", top=1, branch=ji.SYSTEM)) == 1
    assert len(one) < len(everything)


def test_ranking_inside_the_subset_is_by_similarity(memory, base):
    _entry(memory, "2026/10/2026-10-06_system.md", SYSTEM_CWD)
    p = memory / "journal" / "2026" / "10" / "2026-10-06_system.md"
    p.write_text(p.read_text().replace("restic backup ran here",
                                       "backup backup backup backup"))
    ji.build(str(memory), str(base))
    hits = ji.search(str(memory), str(base), "backup", top=9, branch=ji.SYSTEM)
    assert hits[0]["score"] > hits[-1]["score"]
    assert hits[0]["text"].lower().count("backup") > 1


def test_an_empty_facet_returns_nothing_without_embedding_the_query(
        memory, base, monkeypatch):
    """A facet that selects no chunk costs no embedding call, and the caller
    gets the shape of the index back so it can say WHY the page is empty."""
    ji.build(str(memory), str(base))
    calls = []
    monkeypatch.setattr(ji, "embed",
                        lambda texts, model="": calls.append(texts) or _stub_embed(texts))
    assert ji.search(str(memory), str(base), "restic", branch="nothing-here") == []
    assert calls == []
    assert ji.summary(str(base))["chunks"] == 9
    assert "no chunk matches" in ji._no_hits(str(base), ji.AREAS, None)
    assert "no index yet" in ji._no_hits(str(base / "elsewhere"), None, None)


# ── the second facet: `touches:` (C2) ────────────────────────────────────────

def test_a_chunk_carries_the_touches_its_entry_declares(memory, base):
    ji.build(str(memory), str(base))
    idx = _index(base)
    by_path = {c["path"]: c["touches"] for c in idx["chunks"]}
    assert by_path["journal/2026/10/2026-10-01_system.md"] == ["knowledge",
                                                              "consolidation"]
    assert by_path["journal/2026/10/2026-10-03_area.md"] == ["backup"]
    assert by_path["journal/2026/10/2026-10-02_project.md"] == []
    assert idx["files"]["journal/2026/10/2026-10-03_area.md"]["touches"] == ["backup"]
    assert ji.summary(str(base))["touches_chunks"] == 4      # two entries, two chunks each


def test_touches_is_read_verbatim_and_never_validated_here():
    """The index mirrors the record. An out-of-domain subject is
    `ontology.facet_findings`' finding, in the entry -- not a second vocabulary
    rule in this module, which is how the two would come to disagree."""
    assert ji.touches_of(["backup", "backup", "knowledge"]) == ["backup", "knowledge"]
    assert ji.touches_of("backup") == ["backup"]           # a bare value is a list of one
    assert ji.touches_of("  ") == [] and ji.touches_of(None) == []
    assert ji.touches_of("knolwedge") == ["knolwedge"]     # the register reports it


def test_the_touches_filter_selects_a_subset_and_top_counts_within_it(memory, base):
    ji.build(str(memory), str(base))
    one = ji.search(str(memory), str(base), "restic", top=99, touches="backup")
    assert [h["touches"] for h in one] == [["backup"]] * 2
    assert len(one) == 2
    assert len(ji.search(str(memory), str(base), "restic", top=1, touches="backup")) == 1
    # Both facets intersect rather than override: `areas` has chunks and
    # `backup` has chunks, and their intersection is those two.
    both = ji.search(str(memory), str(base), "restic", top=99,
                     branch=ji.AREAS, touches="backup")
    assert len(both) == 2 and all(h["branch"] == ji.AREAS for h in both)
    assert ji.search(str(memory), str(base), "restic", branch=ji.PROJECTS,
                     touches="backup") == []


def test_the_touches_filter_says_when_no_entry_carries_the_facet(memory, base):
    """The C2 trap: an index whose entries predate the facet answers a
    `--touches=` search with zero hits and no error, which reads as "nothing
    matches" rather than "nothing is labelled yet". Say which."""
    ji.build(str(memory), str(base))
    msg = ji._no_hits(str(base), None, "knowledge")
    assert "no chunk matches" in msg
    # ... and when NOTHING carries it, the message names that instead:
    idx = _index(base)
    for c in idx["chunks"]:
        c.pop("touches")
    (base / "journal-index" / "index.json").write_text(json.dumps(idx))
    msg = ji._no_hits(str(base), None, "knowledge")
    assert "no chunk carries `touches:` at all yet" in msg


def test_a_v2_index_is_rebuilt_for_touches_too(memory, base):
    """Bumping SCHEMA is what makes the facet present rather than absent, and
    the absence is invisible -- the same trap as v1's `branch`."""
    ji.build(str(memory), str(base))
    idx = _index(base)
    idx["schema"] = 2
    for c in idx["chunks"]:
        c.pop("touches")
    (base / "journal-index" / "index.json").write_text(json.dumps(idx))
    assert ji.search(str(memory), str(base), "restic", touches="backup") == []
    stats = ji.build(str(memory), str(base))
    assert stats["schema"] == ji.SCHEMA == 3
    assert stats["files_changed"] == 5
    assert ji.search(str(memory), str(base), "restic", touches="backup")


def test_a_touches_value_that_is_not_a_subject_is_an_error(memory, base, capsys):
    assert ji.validate_touches("backup") == "backup"
    with pytest.raises(ValueError):
        ji.validate_touches("backup/")            # a path, not an id
    code = ji.main(["search", "restic", "--touches=nope"], str(base), str(memory))
    assert code == 1
    assert "is not a subject" in capsys.readouterr().err


def test_a_hit_is_a_pointer_to_the_entry_never_a_copy(memory, base):
    """The governing rule: the index ranks, markdown is the truth. Every hit
    carries the location and no chunk claims to be the section itself."""
    ji.build(str(memory), str(base))
    for h in ji.search(str(memory), str(base), "restic", top=99):
        assert {"path", "header", "start_line", "end_line", "score", "branch"} <= set(h)
        assert "embedding" not in h
        assert h["start_line"] >= 1 and h["end_line"] >= h["start_line"]


# -- the command line --------------------------------------------------------
def test_help_prints_the_usage_and_does_not_start_a_build(memory, base, capsys):
    """`invocation.parse` accepts `--help` for every spec, so a verb that
    ignores it answers a question with minutes of Ollama. The trap is named in
    the module's own handoff; this pins the fix."""
    assert ji.main(["index", "--help"], str(base), str(memory)) == 0
    assert "usage" in capsys.readouterr().out
    assert not (base / "journal-index" / "index.json").exists()
    assert ji.main(["search"], str(base), str(memory)) == 1      # a query is required


def test_a_bad_branch_exits_nonzero_with_the_allowed_values(memory, base, capsys):
    code = ji.main(["search", "restic", "--branch=backup"], str(base), str(memory))
    assert code == 1
    assert "system, areas, projects, unknown" in capsys.readouterr().err


# ── the error class: an answered request is not an unreachable server ────────
#
# 2026-10-24 and 10-25: Ollama answered HTTP 400 and the message read "cannot
# reach Ollama ... Is `ollama serve` running?", because `HTTPError` is a
# subclass of `URLError` and the handler for the parent came first.

def _http_error(code, reason, body):
    return urllib.error.HTTPError("http://x/api/embed", code, reason, {},
                                  io.BytesIO(body.encode()))


def _real_post(monkeypatch, exc):
    def urlopen(*_a, **_kw):
        raise exc
    monkeypatch.setattr(ji, "_post_json", _REAL_POST_JSON)
    monkeypatch.setattr(ji.urllib.request, "urlopen", urlopen)


def test_an_http_error_reports_the_status_and_the_body_not_unreachable(monkeypatch):
    body = '{"error":"Post \\"http://127.0.0.1:42773/tokenize\\": connection reset by peer"}'
    _real_post(monkeypatch, _http_error(400, "Bad Request", body))
    with pytest.raises(ji.OllamaHTTPError) as e:
        ji._post_json("/api/embed", {})
    assert e.value.status == 400
    assert "HTTP 400 Bad Request" in str(e.value)
    assert "connection reset by peer" in str(e.value)       # Ollama's own words
    assert "cannot reach" not in str(e.value)
    assert "ollama serve" not in str(e.value)


def test_a_connection_error_is_still_unreachable(monkeypatch):
    _real_post(monkeypatch, urllib.error.URLError(ConnectionRefusedError(111, "refused")))
    with pytest.raises(ji.OllamaUnreachable) as e:
        ji._post_json("/api/embed", {})
    assert e.value.status is None
    assert "cannot reach Ollama" in str(e.value)
    assert "ollama serve" in str(e.value)


def test_a_connection_dropped_without_an_answer_is_unreachable(monkeypatch):
    """A peer that accepts and closes without answering -- Ollama's runner
    dying mid-request -- raises `ConnectionResetError`: an OSError and NOT a
    URLError, so the URLError clause never sees it. Measured against a socket
    that closes on accept, 2026-10-25; before this the exception escaped
    `_post_json` unclassified, so `build` saved nothing and the CLI printed a
    traceback instead of "cannot reach"."""
    _real_post(monkeypatch, ConnectionResetError(104, "Connection reset by peer"))
    with pytest.raises(ji.OllamaUnreachable) as e:
        ji._post_json("/api/embed", {})
    assert "cannot reach Ollama" in str(e.value)
    assert "ConnectionResetError" in str(e.value)          # what the socket did
    assert "reset by peer" in str(e.value).lower()


def test_a_dropped_connection_stops_the_cli_at_2_and_saves_the_progress(
        memory, base, capsys, monkeypatch):
    """The same class of failure, through the whole stack: `build` must stop
    cleanly (progress saved, no traceback) rather than die on an OSError."""
    _real_post(monkeypatch, ConnectionResetError(104, "Connection reset by peer"))
    monkeypatch.setattr(ji, "embed", _REAL_EMBED)
    assert ji.main(["index"], str(base), str(memory)) == 2
    err = capsys.readouterr().err
    assert "cannot reach Ollama" in err and "Traceback" not in err
    assert (base / "journal-index" / "index.json").exists()


def test_a_timeout_is_unreachable_and_an_empty_body_is_said(monkeypatch):
    _real_post(monkeypatch, TimeoutError())
    with pytest.raises(ji.OllamaUnreachable, match="timed out"):
        ji._post_json("/api/embed", {})
    _real_post(monkeypatch, _http_error(500, "Internal Server Error", ""))
    with pytest.raises(ji.OllamaHTTPError, match=r"HTTP 500.*\(empty body\)"):
        ji._post_json("/api/embed", {})


def test_the_cli_prints_the_http_failure_and_exits_2(memory, base, capsys, monkeypatch):
    def refuse(texts, model=""):
        raise ji.OllamaHTTPError("Ollama answered /api/embed with HTTP 404 Not Found: "
                                 "model \"x\" not found", status=404)
    monkeypatch.setattr(ji, "embed", refuse)
    assert ji.main(["index"], str(base), str(memory)) == 2
    err = capsys.readouterr().err
    assert "HTTP 404" in err and "not found" in err and "cannot reach" not in err


def test_embed_caps_each_text_and_does_not_hide_a_400_behind_the_legacy_route(monkeypatch):
    sent = []

    def post(path, body, timeout=0):
        sent.append((path, body))
        raise ji.OllamaHTTPError("HTTP 400", status=400)
    monkeypatch.setattr(ji, "_post_json", post)
    monkeypatch.setattr(ji, "embed", _REAL_EMBED)
    with pytest.raises(ji.OllamaHTTPError):
        ji.embed(["x" * 1_000_000, "y"])
    assert [p for p, _ in sent] == ["/api/embed"]           # no per-text retry
    assert max(len(t) for t in sent[0][1]["input"]) == ji.MAX_CHUNK_CHARS


def test_embed_falls_back_to_the_legacy_route_only_on_a_404(monkeypatch):
    def post(path, body, timeout=0):
        if path == "/api/embed":
            raise ji.OllamaHTTPError("HTTP 404", status=404)
        return {"embedding": [1.0, 2.0]}
    monkeypatch.setattr(ji, "_post_json", post)
    monkeypatch.setattr(ji, "embed", _REAL_EMBED)
    assert ji.embed(["a", "b"]) == [[1.0, 2.0], [1.0, 2.0]]


# ── one bad chunk, one bad batch, one interrupted run ────────────────────────

POISON = "POISONED-CHUNK"


def _refusing(poison=POISON, calls=None):
    """An embed that, like Ollama on 2026-10-24, answers 400 for a whole batch
    that contains one input it cannot take."""
    def embed(texts, model=""):
        if calls is not None:
            calls.append(len(texts))
        if any(poison in t for t in texts):
            raise ji.OllamaHTTPError("HTTP 400 Bad Request: tokenize reset",
                                     status=400)
        return _stub_embed(texts)
    return embed


def _poisoned(memory):
    p = memory / "journal" / "2026" / "10" / "2026-10-03_area.md"
    p.write_text(p.read_text() + f"\n## Bad\n\n{POISON}\n")
    os.utime(p, (1_700_000_000, 1_700_000_000))
    return "journal/2026/10/2026-10-03_area.md"


def test_one_bad_chunk_is_skipped_and_logged_not_fatal(memory, base, monkeypatch):
    bad = _poisoned(memory)
    monkeypatch.setattr(ji, "embed", _refusing())
    lines = []
    stats = ji.build(str(memory), str(base), log=lines.append)
    assert stats["chunks_skipped"] == 1
    assert any(l.startswith("!! skipped") and "Bad" in l and "tokenize reset" in l
               for l in lines)                              # named, with Ollama's words
    idx = _index(base)
    paths = {c["path"] for c in idx["chunks"]}
    assert len(paths) == 5                                  # the other four files, and this one's good chunks
    assert not any(POISON in c["text"] for c in idx["chunks"])
    assert bad not in idx["files"]                          # unrecorded -> retried


def test_the_partly_indexed_file_is_retried_and_completed_once_it_can_be(memory, base, monkeypatch):
    bad = _poisoned(memory)
    monkeypatch.setattr(ji, "embed", _refusing())
    ji.build(str(memory), str(base))
    monkeypatch.setattr(ji, "embed", _stub_embed)           # Ollama recovers
    lines = []
    stats = ji.build(str(memory), str(base), log=lines.append)
    assert stats["files_changed"] == 1 and stats["chunks_skipped"] == 0
    # A retry is not a new file: its good chunks are already in the index, so
    # the build log must not call it one.
    assert stats["files_new"] == 0
    assert "(0 new, 1 modified)" in " ".join(lines)
    idx = _index(base)
    assert bad in idx["files"]
    mine = [c for c in idx["chunks"] if c["path"] == bad]
    assert len(mine) == idx["files"][bad]["chunks"]         # no duplicates from the retry


def test_a_failing_batch_is_split_so_the_good_chunks_are_not_lost(memory, base, monkeypatch):
    _poisoned(memory)
    calls = []
    monkeypatch.setattr(ji, "embed", _refusing(calls=calls))
    ji.build(str(memory), str(base))
    assert calls[0] > 1 and 1 in calls                      # whole batch first, then down to one


def test_five_refusals_in_a_row_abort_the_run_with_progress_saved(memory, base, monkeypatch):
    def refuse_all(texts, model=""):
        raise ji.OllamaHTTPError("HTTP 400 Bad Request: nope", status=400)
    monkeypatch.setattr(ji, "BATCH_CHUNKS", 1)
    monkeypatch.setattr(ji, "MAX_CONSECUTIVE_SKIPS", 3)
    monkeypatch.setattr(ji, "embed", refuse_all)
    with pytest.raises(ji.EmbedError, match="3 chunks in a row"):
        ji.build(str(memory), str(base))
    assert (base / "journal-index" / "index.json").exists()


def test_a_status_that_is_not_about_the_request_is_not_split(memory, base, monkeypatch):
    calls = []

    def not_found(texts, model=""):
        calls.append(len(texts))
        raise ji.OllamaHTTPError("HTTP 404: model not found", status=404)
    monkeypatch.setattr(ji, "embed", not_found)
    with pytest.raises(ji.OllamaHTTPError, match="model not found"):
        ji.build(str(memory), str(base))
    assert len(calls) == 1                                  # not 2 * chunks of retries


def test_an_interrupted_run_keeps_its_finished_files_and_resumes_the_rest(memory, base, monkeypatch):
    n = {"batches": 0}

    def dies_on_the_third(texts, model=""):
        n["batches"] += 1
        if n["batches"] == 3:
            raise ji.OllamaUnreachable("cannot reach Ollama")
        return _stub_embed(texts)
    monkeypatch.setattr(ji, "BATCH_CHUNKS", 1)
    monkeypatch.setattr(ji, "embed", dies_on_the_third)
    with pytest.raises(ji.OllamaUnreachable):
        ji.build(str(memory), str(base))
    saved = _index(base)
    assert len(saved["files"]) == 1                         # one finished (2 chunks); the file in flight is unrecorded
    assert len(saved["chunks"]) == 2                        # the finished file's, nothing half-written
    monkeypatch.setattr(ji, "embed", _stub_embed)
    stats = ji.build(str(memory), str(base))
    assert stats["files_changed"] == 4                      # only the rest
    done = _index(base)
    assert len(done["files"]) == 5
    assert len(done["chunks"]) == sum(f["chunks"] for f in done["files"].values())


def test_a_chunk_is_stored_capped_and_embedded_capped(memory, base, monkeypatch):
    p = memory / "journal" / "2026" / "10" / "2026-10-01_system.md"
    p.write_text(p.read_text() + "\n## Huge\n\n" + "w" * 1_200_000 + "\n")
    seen = []
    monkeypatch.setattr(ji, "embed",
                        lambda texts, model="": seen.extend(texts) or _stub_embed(texts))
    ji.build(str(memory), str(base))
    assert max(len(t) for t in seen) == ji.MAX_CHUNK_CHARS
    assert max(len(c["text"]) for c in _index(base)["chunks"]) == ji.MAX_CHUNK_CHARS
    big = [c for c in _index(base)["chunks"] if c["header"] == "Huge"][0]
    assert big["end_line"] - big["start_line"] >= 3         # the pointer is still the whole section


def test_batches_respect_the_chunk_and_the_byte_ceiling():
    chunk = lambda n: {"text": "a" * n}
    out = list(ji._batches([chunk(10)] * (ji.BATCH_CHUNKS + 1)))
    assert [len(b) for b in out] == [ji.BATCH_CHUNKS, 1]
    big = ji.BATCH_CHARS // 2 + 1
    assert [len(b) for b in ji._batches([chunk(big)] * 3)] == [1, 1, 1]
    assert list(ji._batches([])) == []


# ── what made 2026-10-24 look like an invalidated index ──────────────────────
#
# 474 "changed" files read as a hash or path change. They were 471 new entries
# (one consolidation commit) and 3 edits, against an index that was intact.

def test_a_burst_of_new_entries_is_reported_as_new_not_as_an_invalidation(memory, base):
    ji.build(str(memory), str(base))
    before = _index(base)
    for i in range(40):
        _entry(memory, f"2026/10/2026-10-20_burst-{i:02d}.md", SYSTEM_CWD)
    p = memory / "journal" / "2026" / "10" / "2026-10-04_none.md"
    p.write_text(p.read_text() + "\n## Edit\n\nx\n")
    os.utime(p, (1_700_000_000, 1_700_000_000))
    lines = []
    stats = ji.build(str(memory), str(base), log=lines.append)
    assert "(40 new, 1 modified)" in " ".join(lines)
    assert stats["files_new"] == 40 and stats["files_changed"] == 41
    assert not any("forcing full rebuild" in l for l in lines)    # model and schema held
    after = _index(base)
    key = lambda c: (c["path"], c["start_line"])
    kept = {key(c): c["embedding"] for c in before["chunks"]
            if not c["path"].endswith("none.md")}
    assert kept and all(c["embedding"] == kept[key(c)] for c in after["chunks"]
                        if key(c) in kept)                       # untouched entries kept their vectors
    assert {key(c) for c in after["chunks"]} >= set(kept)


def test_a_move_of_the_whole_journal_does_not_change_what_is_stored_as_changed(memory, base, tmp_path):
    """The index keys files by their path RELATIVE to the memory root and
    compares mtimes, so the same journal read from another checkout (a
    worktree) has the same keys and a different mtime for every file. That is
    why a worktree run against the live index would re-embed everything, and
    why the live service must run from the install."""
    ji.build(str(memory), str(base))
    other = tmp_path / "checkout" / "memory"
    for src in (memory / "journal").rglob("*.md"):
        dst = other / src.relative_to(memory)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text())
    stats = ji.build(str(other), str(base))
    assert stats["files_removed"] == 0
    assert stats["files_changed"] == 5
