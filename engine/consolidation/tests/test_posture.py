"""The memory-poisoning checks
(memory/knowledge/meta/memory-poisoning-posture.md).

A security check that has never been seen to FAIL is a comment. Every check
below is exercised on a tree where the property is broken, as well as on one
where it holds -- otherwise the whole module could be `return []` and the
suite would be green.
"""
import subprocess

import pytest

from knowledge import frontmatter, ontology
from consolidation import posture

IDENT = ["-c", "user.email=test@example.invalid", "-c", "user.name=Test"]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *IDENT, *args], check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "memory" / "knowledge" / "meta").mkdir(parents=True)
    (r / "memory" / "journal" / "2026" / "09").mkdir(parents=True)
    (r / "memory" / "knowledge" / "meta" / "leaf.md").write_text(
        "---\ntitle: leaf\ntrust: trial\nlast_verified: 2026-09-01\n---\n\n"
        "# leaf\n\nsettled prose\n")
    # The directive directories the LIVE register declares. Derived rather than
    # listed: property 4 reads its paths from `entities.yaml` (R3d), so a
    # fixture that spelled them would fail the day a kind is added.
    for d in ontology.directive_dirs():
        (r / d).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(r)], check=True,
                   capture_output=True, text=True)
    _git(r, "add", "-A")
    _git(r, "commit", "-m", "seed")
    return r


def _pass_commit(repo, msg="memory: nightly consolidation 2026-09-12"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", msg)


def _kinds(findings):
    return {f.check for f in findings}


# ── 2. promotion is human-gated ──────────────────────────────────────────────

def test_the_promotion_gate_is_checked_behaviourally_not_by_grep(monkeypatch):
    """The realistic failure is the guard being moved or short-circuited, which
    a grep for the constant would not notice."""
    assert posture.check_promotion_gate() == []
    monkeypatch.setattr(frontmatter, "set_fields",
                        lambda text, updates: text)
    findings = posture.check_promotion_gate()
    assert findings and "promote its own text" in findings[0].detail


def test_a_wrong_exception_is_a_finding_not_a_pass(monkeypatch):
    def _raises(text, updates):
        raise ValueError("unrelated")
    monkeypatch.setattr(frontmatter, "set_fields", _raises)
    findings = posture.check_promotion_gate()
    assert findings and "instead of PromotionRefused" in findings[0].detail


# ── 3. the curator never edits prose unattended ──────────────────────────────

def test_a_frontmatter_only_pass_commit_is_clean(repo):
    leaf = repo / "memory" / "knowledge" / "meta" / "leaf.md"
    leaf.write_text(leaf.read_text().replace("trust: trial", "trust: deprecated"))
    _pass_commit(repo)
    assert posture.check_curator_writes(repo) == []


def test_a_pass_commit_that_edits_leaf_PROSE_is_a_finding(repo):
    leaf = repo / "memory" / "knowledge" / "meta" / "leaf.md"
    leaf.write_text(leaf.read_text() + "\nan unattended paragraph\n")
    _pass_commit(repo)
    findings = posture.check_curator_writes(repo)
    assert findings and "changed PROSE" in findings[0].detail


def test_a_HUMAN_commit_editing_prose_is_not_this_checks_business(repo):
    leaf = repo / "memory" / "knowledge" / "meta" / "leaf.md"
    leaf.write_text(leaf.read_text() + "\na paragraph a person wrote\n")
    _pass_commit(repo, "docs: write the thing by hand")
    assert posture.check_curator_writes(repo) == []


def test_the_generated_index_body_may_change(repo):
    (repo / "memory" / "knowledge" / "INDEX.md").write_text(
        "# Knowledge Index\n\n| a | b |\n")
    _pass_commit(repo)
    assert posture.check_curator_writes(repo) == []


# ── 4. directive paths ───────────────────────────────────────────────────────

def test_the_property_is_read_from_the_register_not_a_tuple(repo, monkeypatch):
    """R3d. The check must ask the register, so that a kind added, moved or
    unmarked changes what it protects without an edit here."""
    seen = []
    monkeypatch.setattr(posture.ontology, "directive_dirs",
                        lambda: seen.append(1) or ("config/boundaries/",))
    posture.check_directives(repo)
    assert seen, "the directive paths were not read from the register"


def test_a_directive_path_inside_the_scored_tree_is_a_live_finding(repo,
                                                                  monkeypatch):
    """The path is injected through the register, because after R3b no
    directive KIND lives under the scored tree -- which is the structural half
    of the property. A tuple could still name one, and this is what would
    happen if it did."""
    (repo / "memory" / "knowledge" / "conventions").mkdir()
    (repo / "memory" / "knowledge" / "conventions" / "voice.md").write_text("x\n")
    monkeypatch.setattr(posture.ontology, "directive_dirs",
                        lambda: ("memory/knowledge/conventions/",))
    findings = posture.check_directives(repo)
    assert any("a writing stage can reach it" in f.detail and f.level == "error"
               for f in findings)


def test_a_directive_directory_the_register_names_but_the_tree_lacks(repo):
    """The assertion `declared_paths` used to make of the constant: the register
    is a claim about the tree, and a kind whose directory went must say so."""
    (repo / "config" / "boundaries").rmdir()
    findings = posture.check_directives(repo)
    assert [f.level for f in findings] == ["error"]
    assert "does not exist" in findings[0].detail
    assert "config/boundaries/" in findings[0].detail


def test_a_past_breach_in_the_spelling_of_its_date_is_a_warning(repo):
    """The BRIDGE. History spells what was true then: the 2026-08-31 pass wrote
    `verified_log:` into the conventions where they lived at the time, and a
    repath of the constant must not make that finding vanish -- a check that
    reports a clean history it did not verify is worse than one that reports
    nothing."""
    d = repo / "agents" / "knowledge" / "conventions"
    d.mkdir(parents=True)
    (d / "voice.md").write_text("x\n")
    _pass_commit(repo)
    (d / "voice.md").unlink()
    d.rmdir()
    _pass_commit(repo, "docs: move conventions out of the scored tree")
    findings = posture.check_directives(repo)
    assert [f.level for f in findings] == ["warn"]
    assert "None is still inside the scored tree" in findings[0].detail
    assert "agents/knowledge/conventions/voice.md" in findings[0].detail


def test_a_clean_history_has_nothing_to_say(repo):
    assert posture.check_directives(repo) == []


# ── 1. nothing machine-written is injected ───────────────────────────────────

def test_the_always_loaded_set_is_checked_against_the_compiler(repo, monkeypatch):
    """The mirror is the risk: a file added to `familiar-context.py`'s ALWAYS_LOADED
    and not here would silently widen the injected surface."""
    monkeypatch.setattr(posture, "ALWAYS_LOADED", ("CONTEXT.md",))
    findings = posture.check_injected_surface(repo)
    assert any("drifted" in f.detail for f in findings)


def test_an_injected_file_written_by_the_pass_is_a_finding(repo, monkeypatch):
    (repo / "CONTEXT.md").write_text("# routing\n")
    _pass_commit(repo)
    monkeypatch.setattr(posture, "CONTEXT_SOURCE", repo / "missing.py")
    findings = posture.check_injected_surface(repo)
    assert any("reaching prompts unasked" in f.detail for f in findings)


# ── 5. provenance labelling ──────────────────────────────────────────────────

def test_an_unmarked_journal_entry_is_a_warning(repo):
    (repo / "memory" / "journal" / "2026" / "09" / "x.md").write_text(
        "---\ntitle: t\n---\n\nbody\n")
    findings = posture.check_journal_provenance(repo / "memory")
    assert findings and findings[0].level == "warn"


def test_a_marked_entry_passes(repo):
    (repo / "memory" / "journal" / "2026" / "09" / "x.md").write_text(
        "---\ntitle: t\ndistilled_by: a-model\n---\n\nbody\n")
    assert posture.check_journal_provenance(repo / "memory") == []


def test_routers_are_not_journal_entries(repo):
    (repo / "memory" / "journal" / "CONTEXT.md").write_text("# routing\n")
    assert posture.check_journal_provenance(repo / "memory") == []


# ── the gate ─────────────────────────────────────────────────────────────────

def test_check_never_raises_even_on_a_non_repository(tmp_path):
    assert isinstance(posture.check(tmp_path, tmp_path / "memory"), list)


def test_every_declared_check_is_reachable():
    """CHECKS is what the CLI prints as `ok`; a name there with no producer
    would report a check that does not exist as passing."""
    src = __import__("inspect").getsource(posture)
    for name in posture.CHECKS:
        assert f'"{name}"' in src


# ── the vault contract (P1) ─────────────────────────────────────────────────

def test_the_vault_contract_parses_as_it_renders():
    from lib import _miniyaml
    contract = posture.vault_contract()
    assert _miniyaml.load(posture.render_vault(contract)) == contract


def test_the_vault_contract_is_derived_not_restated():
    contract = posture.vault_contract()
    assert contract["always_loaded"] == list(posture.ALWAYS_LOADED)
    assert contract["human_owned"] == list(posture.directive_prefixes())
    assert contract["machine_writable"] == list(posture.WRITABLE_ROOTS)
    assert contract["on_drift"] == "refuse"
    for path in posture.GENERATED:
        assert path in contract["generated"]
    # nothing the person owns is also something a generator rewrites, except
    # the compiled boundary targets, which live beside their human-owned source
    for gen in contract["generated"]:
        owners = [h for h in contract["human_owned"] if gen.startswith(h)]
        assert not owners or gen.startswith(posture.roots.rel(posture.roots.BOUNDARIES)), gen


def test_the_committed_vault_contract_is_in_sync():
    assert posture.VAULT_FILE.read_text() == posture.render_vault(posture.vault_contract())
