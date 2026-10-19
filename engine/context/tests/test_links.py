"""links -- the repair rules, and the three bugs that produced them.

Every test here is a bug that reached the tree on 2026-09-04, not a
hypothetical. The module edits directive files, so its safety properties
(unique-basename repairs, splice-by-span, refuse-generated) are the ones worth
pinning down.
"""
import pathlib

import pytest

from context import links


@pytest.fixture
def tree(tmp_path):
    """A miniature memory/ tree: a router, two leaves, one nested branch."""
    (tmp_path / "knowledge" / "meta").mkdir(parents=True)
    (tmp_path / "conventions").mkdir()
    (tmp_path / "CONTEXT.md").write_text(
        "# Router\n\n| q | r |\n|---|---|\n| style | `conventions/voice.md` |\n")
    (tmp_path / "conventions" / "voice.md").write_text("---\ntitle: Voice\n---\n# Voice\n")
    (tmp_path / "knowledge" / "meta" / "boundaries.md").write_text("# Boundaries\n")
    return tmp_path


# ── what counts as a path ────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    "--check",                      # a flag
    "deny",                         # a value
    "knowledge/**",                 # a glob
    "<name>",                       # a placeholder
    "https://example.com/a.md",     # a URL
    "mattpocock/skills@6654f6b",    # a git ref: path-shaped, not a path
    "authority: human",             # prose with a colon
])
def test_non_paths_are_never_candidates(raw):
    assert not links._is_candidate(raw)


@pytest.mark.parametrize("raw", [
    "conventions/voice.md", "../meta/boundaries.md", "CONTEXT.md",
    "~/06_SYSTEM/CONTEXT.md", "read-write.yaml",
])
def test_paths_are_candidates(raw):
    assert links._is_candidate(raw)


# ── resolution ───────────────────────────────────────────────────────────────

def test_resolve_normalises_dotdot(tree):
    """The bug that hung the orphan walk: `..` is never collapsed by pathlib, so
    two spellings of one file were two Path objects and the visited-set never
    converged."""
    source = tree / "knowledge" / "meta" / "boundaries.md"
    got = links.resolve("../../conventions/voice.md", source, tree)
    assert got == (tree / "conventions" / "voice.md").resolve()
    assert ".." not in str(got)


def test_resolve_anchors_at_every_ancestor(tree):
    """`meta/boundaries.md` written inside knowledge/ means relative to
    knowledge/ -- how a person reads it, so not a defect."""
    source = tree / "knowledge" / "meta" / "boundaries.md"
    assert links.resolve("meta/boundaries.md", source, tree) is not None


def test_out_of_tree_absolute_paths_are_not_our_business(tree):
    assert not links.in_scope("~/.hermes/.anthropic_oauth.json", tree)
    assert links.in_scope("conventions/voice.md", tree)


# ── the repair bound ─────────────────────────────────────────────────────────

def test_unique_basename_is_repaired(tree):
    (tree / "CONTEXT.md").write_text("| x | `voice.md` |\n")
    broken = links.scan(tree)
    assert [b.repair for b in broken] == ["conventions/voice.md"]


def test_ambiguous_basename_is_reported_not_guessed(tree):
    (tree / "knowledge" / "meta" / "voice.md").write_text("# Other voice\n")
    (tree / "CONTEXT.md").write_text("| x | `voice.md` |\n")
    broken = links.scan(tree)
    assert len(broken) == 1
    assert broken[0].repair is None
    assert "2 files share that name" in broken[0].reason


def test_absent_basename_is_reported_not_guessed(tree):
    (tree / "CONTEXT.md").write_text("| x | `knowledge/INDEX.md` |\n")
    broken = links.scan(tree)
    assert broken[0].repair is None


def test_parent_directory_disambiguates(tree):
    """`conventions/CONTEXT.md` has namesakes, but only one lives in a folder
    called conventions."""
    (tree / "conventions" / "CONTEXT.md").write_text("# Conventions\n")
    (tree / "knowledge" / "CONTEXT.md").write_text("# Knowledge\n")
    (tree / "conventions" / "voice.md").write_text(
        "See `knowledge/conventions/CONTEXT.md`\n")
    broken = [b for b in links.scan(tree) if "CONTEXT.md" in b.raw]
    assert broken and broken[0].repair == "CONTEXT.md"


def test_declared_rename_beats_lookup(tree):
    (tree / "CONTEXT.md").write_text("| x | `USER.md` |\n")
    (tree / "conventions" / "user-identity.md").write_text("# Id\n")
    broken = links.scan(tree, {"USER.md": "conventions/user-identity.md"})
    assert broken[0].repair == "conventions/user-identity.md"


# ── the write bound ──────────────────────────────────────────────────────────

def test_apply_only_rewrites_inside_the_delimiter(tree):
    """The user's constraint. A line holding the same token as prose AND as a
    pointer must keep the prose untouched."""
    (tree / "CONTEXT.md").write_text(
        "voice.md was renamed, so read `voice.md` now\n")
    links.apply(links.scan(tree))
    out = (tree / "CONTEXT.md").read_text()
    assert out.startswith("voice.md was renamed")          # prose survived
    assert "`conventions/voice.md`" in out                  # pointer repaired


def test_apply_handles_two_repairs_on_one_line(tree):
    """Right-to-left, because an earlier splice shifts later offsets."""
    (tree / "knowledge" / "meta" / "other.md").write_text("# Other\n")
    (tree / "CONTEXT.md").write_text("`voice.md` and `other.md`\n")
    links.apply(links.scan(tree))
    out = (tree / "CONTEXT.md").read_text()
    assert "`conventions/voice.md`" in out
    assert "`knowledge/meta/other.md`" in out


def test_generated_files_are_never_repaired(tree):
    (tree / "CONTEXT.md").write_text(
        "<!-- GENERATED FILE — do not hand-edit -->\n| x | `voice.md` |\n")
    broken = links.scan(tree)
    assert broken[0].repair is None
    assert "generated" in broken[0].reason
    links.apply(broken)
    assert "`voice.md`" in (tree / "CONTEXT.md").read_text()   # untouched


def test_yaml_see_targets_are_checked(tree):
    (tree / "conventions" / "rules.yaml").write_text(
        "rules:\n  - path: ~\n    see: memory/GONE.md\n")
    assert any(b.raw == "memory/GONE.md" for b in links.scan(tree))


# ── orphans ──────────────────────────────────────────────────────────────────

def test_unreferenced_leaf_is_an_orphan(tree):
    assert (tree / "knowledge" / "meta" / "boundaries.md") in links.orphans(tree)


def test_referenced_leaf_is_not_an_orphan(tree):
    (tree / "CONTEXT.md").write_text("`knowledge/meta/boundaries.md`\n")
    assert (tree / "knowledge" / "meta" / "boundaries.md") not in links.orphans(tree)


def test_bare_branch_name_reaches_its_router(tree):
    """`development` in a generated router means skills/development/ -- and the
    name may carry a hyphen, which `str.isidentifier()` rejects."""
    (tree / "skills" / "app-builder").mkdir(parents=True)
    (tree / "skills" / "CONTEXT.md").write_text("| `app-builder` | does things |\n")
    (tree / "skills" / "app-builder" / "SKILL.md").write_text("# App builder\n")
    (tree / "CONTEXT.md").write_text("`skills/CONTEXT.md`\n")
    assert (tree / "skills" / "app-builder" / "SKILL.md") not in links.orphans(tree)


def test_user_invoked_skill_is_not_an_orphan(tree):
    """Reached by slash command; the model-facing router excludes it on purpose."""
    (tree / "skills" / "handoff").mkdir(parents=True)
    (tree / "skills" / "handoff" / "SKILL.md").write_text(
        "---\ntitle: Handoff\ninvocation: user\n---\n# Handoff\n")
    assert (tree / "skills" / "handoff" / "SKILL.md") not in links.orphans(tree)


# ── adoption ─────────────────────────────────────────────────────────────────

def test_orphan_adopted_into_its_own_router(tree):
    (tree / "knowledge" / "meta" / "CONTEXT.md").write_text(
        "# Meta\n\n| File | Load when |\n|---|---|\n| `x.md` | when |\n")
    (tree / "CONTEXT.md").write_text("`knowledge/meta/CONTEXT.md`\n")
    plans = links.adopt_all(links.orphans(tree), tree, write=True)
    assert any(a.ok for a in plans)
    router = (tree / "knowledge" / "meta" / "CONTEXT.md").read_text()
    assert "`boundaries.md`" in router
    assert "Boundaries" in router          # description came from the leaf's H1


def test_generated_router_is_not_extended(tree):
    (tree / "knowledge" / "meta" / "CONTEXT.md").write_text(
        "<!-- GENERATED FILE -->\n| a | b |\n")
    (tree / "CONTEXT.md").write_text("`knowledge/meta/CONTEXT.md`\n")
    plans = [a for a in links.adopt_all(links.orphans(tree), tree, write=False)
             if a.orphan.name == "boundaries.md"]
    assert plans and not plans[0].ok
    assert "generated" in plans[0].reason


# ── strict sources: a mechanism claim must name a file that resolves ─────────
#
# Added 2026-09-11. Three times in two weeks the prose describing this system
# drifted from the system -- `MEMORY.md` (deleted, still described as live), the
# `loredb` boundary rule (store retired, rule kept), stage 9 (removed, still in
# the stage table). Each was found by hand, late. The bare-name bucket cannot
# catch them: it is informational on purpose, because failing on all 126 bare
# names would bury the six that matter. So these handful of files, which
# DESCRIBE the repository's own mechanisms, get a stricter rule -- for PATHS.

@pytest.fixture
def strict_tree(tmp_path, monkeypatch):
    """A tree with one strict source, aimed at `memory/`."""
    monkeypatch.setattr(links, "STRICT_SOURCES", ("meta.md",))
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "leaf.md").write_text("# leaf\n")
    return tmp_path


def _strict(source, strict_tree):
    (strict_tree / "meta.md").write_text(source)
    return [b for b in links.scan(strict_tree) if b.strict]


def test_a_path_fragment_in_a_strict_source_is_stale(strict_tree):
    """The live case: `stages/consolidate.py` names a file a reader cannot
    find, because the path is anchored at a package rather than the root."""
    found = _strict("Mechanism: `stages/consolidate.py`.\n", strict_tree)
    assert len(found) == 1
    assert found[0].raw == "stages/consolidate.py"
    assert not found[0].fixable, "no namesake, so nothing to repair"


def test_the_same_fragment_outside_a_strict_source_is_not_gated(tree):
    """The rule is scoped. Everywhere else a path fragment is ordinary prose
    that may name another repo, and gating on it would make --check permanent
    red -- the design that must not be traded away."""
    (tree / "knowledge" / "meta" / "boundaries.md").write_text(
        "See `stages/consolidate.py`.\n")
    assert not [b for b in links.scan(tree) if b.strict]


def test_a_bare_module_name_in_a_strict_source_is_not_gated(strict_tree):
    """`conflict.py` is a module name, and by design the reader is given an
    anchor sentence elsewhere rather than a path at every mention. Gating on
    bare names flags 13 places in the real tree, of which 9 are correct records
    of a removal."""
    assert not _strict("Stage 5d lives in `conflict.py`.\n", strict_tree)


def test_a_line_recording_a_removal_is_not_a_stale_claim(strict_tree):
    """`MEMORY.md` is discussed at length in these files BECAUSE it was
    deleted. Reporting that as drift would be the check being wrong."""
    assert not _strict(
        "The third target it used to have, `knowledge/meta/old.md`, was "
        "deleted.\n", strict_tree)


def test_a_generated_output_is_never_a_stale_claim(strict_tree):
    """`BRIEF.md` is written by the pass and is legitimately absent between
    runs. Its absence is not drift."""
    assert not _strict("The brief at `journal/reports/BRIEF.md`.\n", strict_tree)


def test_a_resolvable_path_in_a_strict_source_is_clean(strict_tree):
    assert not _strict("See `knowledge/leaf.md`.\n", strict_tree)


def test_a_repairable_pointer_in_a_strict_source_still_gates(tree, monkeypatch):
    """Strictness must not weaken the existing rule: a moved file is still
    repairable, and still gates.

    `voice.md` exists at one path and is named from another, so the lookup
    succeeds -- the same repair the tool has always offered, now offered from a
    strict source.
    """
    monkeypatch.setattr(links, "STRICT_SOURCES", ("meta.md",))
    (tree / "meta.md").write_text("Style: `knowledge/voice.md`.\n")
    found = [b for b in links.scan(tree) if b.gates]
    assert found, "a unique-namesake pointer must still be repaired"
    assert found[0].fixable
    assert found[0].strict, "and it is still known to be a strict source"


def test_the_real_strict_sources_are_clean():
    """The live tree, not a fixture. If this fails, a mechanism claim in one of
    these files points at a path that is not there."""
    agents = pathlib.Path(__file__).resolve().parents[3] / "agents"
    stale = [b for b in links.scan(agents) if b.strict]
    assert not stale, "\n".join(
        f"{b.source.relative_to(agents)}:{b.line} {b.raw}" for b in stale)


def test_generated_outputs_mirror_the_generator_that_declares_them():
    """`GENERATED_OUTPUTS` names files by hand because the two packages cannot
    import each other -- the same mirror posture.py keeps of pazras.py's
    ALWAYS_LOADED, checked the same way. If brief.py renames its report, this
    check must fail rather than silently exempting a name that no longer
    exists."""
    root = pathlib.Path(__file__).resolve().parents[3]
    src = (root / "engine/consolidation/brief.py").read_text()
    for name in links.GENERATED_OUTPUTS:
        assert f'NAME = "{name}"' in src, (
            f"links.GENERATED_OUTPUTS exempts {name!r}, and brief.py no longer "
            f"declares it — the exemption is stale")


# ── wikilinks ────────────────────────────────────────────────────────────────
#
# O2a converts prose references from relative paths to `[[stem]]` so that O2b's
# `git mv` of 31 leaves does not have to rewrite 600 of them. Before that, this
# module could not SEE a wikilink: it is not path-shaped, so `_is_candidate`
# rejected it and the conversion would have traded a checked pointer for an
# unchecked one.

def test_wikilink_resolves_by_stem_from_anywhere(tree):
    """A wikilink names a file tree-wide, not relative to the file writing it.

    `knowledge/meta/boundaries.md` is nowhere near `conventions/voice.md`, and
    that is the point of converting to this form.
    """
    (tree / "knowledge" / "meta" / "boundaries.md").write_text(
        "# Boundaries\n\nSee [[voice]] for the tone.\n")
    assert links.scan(tree) == []


@pytest.mark.parametrize("body,reason", [
    ("See [[nope]].", "no file of that stem"),
    ("See [[CONTEXT]].", "share that stem"),      # router and branch router
])
def test_wikilink_that_names_nothing_or_two_things_is_broken(tree, body, reason):
    (tree / "knowledge" / "meta" / "CONTEXT.md").write_text("# Branch\n")
    (tree / "knowledge" / "meta" / "boundaries.md").write_text(f"# B\n\n{body}\n")
    found = [b for b in links.scan(tree) if b.source.name == "boundaries.md"]
    assert len(found) == 1 and reason in found[0].reason
    assert found[0].repair is None      # a second namesake is a decision


def test_wikilink_alias_and_anchor_name_the_stem(tree):
    (tree / "knowledge" / "meta" / "boundaries.md").write_text(
        "# B\n\n[[voice|the voice doc]] and [[voice#Tone]].\n")
    assert links.scan(tree) == []


@pytest.mark.parametrize("line", [
    'if [[ -n "${PAZRAS_CONFIG_FILE:-}" ]]; then',   # bash, not a pointer
    "Obsidian understands `[[wikilinks]]`.",         # the syntax, quoted
])
def test_wikilink_lookalikes_are_not_pointers(tree, line):
    (tree / "knowledge" / "meta" / "boundaries.md").write_text(f"# B\n\n{line}\n")
    assert links.scan(tree) == []


def test_wikilink_reaches_its_target_for_orphan_purposes(tree):
    """A leaf reachable only by wikilink is not an orphan."""
    (tree / "knowledge" / "meta" / "lonely.md").write_text("# Lonely\n")
    assert tree / "knowledge" / "meta" / "lonely.md" in links.orphans(tree)
    (tree / "CONTEXT.md").write_text(
        "# Router\n\n`conventions/voice.md` and `knowledge/meta/boundaries.md`\n"
        "and [[lonely]]\n")
    assert tree / "knowledge" / "meta" / "lonely.md" not in links.orphans(tree)


def test_a_namesake_at_the_repository_root_is_reported_not_raised(tmp_path):
    """R3b put `AGENTS.md` both in `memory/` and at the repository root, and the
    index holds the root's own `*.md`. Reporting the two namesakes called
    `relative_to(memory)` on the root one and crashed `links --check`."""
    vault = tmp_path / "memory"
    (vault / "knowledge").mkdir(parents=True)
    (vault / "AGENTS.md").write_text("# vault\n")
    (tmp_path / "AGENTS.md").write_text("# repo\n")
    (vault / "knowledge" / "x.md").write_text("See `gone/AGENTS.md`.\n")
    [found] = links.scan(vault)
    assert found.repair is None
    assert "../AGENTS.md" in found.reason and "AGENTS.md" in found.reason
