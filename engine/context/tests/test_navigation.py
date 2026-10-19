"""navigation -- the candidate-5 resolution bug, reproduced and fixed.

The 2026-09-05 architecture review flagged possible duplication between
`links.resolve()` (multi-root: file's own dir, every ancestor up to `memory/`,
then `memory/` itself, `agents.parent`, `$HOME`) and `navigation._resolve()`
(single root: the router's own directory only), but asked for a reproduction
before extracting shared code -- the two modules also have genuinely
different scopes, so the divergence might have been intentional.

It reproduces: a routing-table row written the way `knowledge/operations/
context-budget.md` really writes one -- relative to an ancestor directory,
not the file's own -- resolved under `links.py` but was silently dropped by
`navigation._descend`, and worse than "unresolved is under-reported": the target
never even reached `Route.unresolved`, since `_descend` doesn't populate it.
That is a real under-measurement bug, not a scope difference, so
`navigation._resolve` now shares `links._roots()`'s ancestor walk (see `navigation.py`).
These tests pin the fix.
"""
import pathlib

import pytest

from context import links, navigation


@pytest.fixture
def tree(tmp_path):
    """A miniature memory/ tree with a nested router (`skills/CONTEXT.md`)
    whose own table names a LEAF the way `knowledge/operations/context-budget.md`
    really does: relative to an ancestor (`memory/`), not to the router's own
    directory (`skills/`) and not with an explicit `../`.

    The target must be a leaf, not another `CONTEXT.md` -- `_descend`
    deliberately skips router-named targets regardless of whether they
    resolve, so a `CONTEXT.md` target would pass even with the pre-fix,
    single-root `_resolve` and prove nothing about the ancestor walk.
    """
    vault = tmp_path / "memory"
    (vault / "skills").mkdir(parents=True)
    (vault / "knowledge" / "domains").mkdir(parents=True)
    # The router at the repository root, the vault beside `config/`: measured
    # from the repository since R3b.
    (tmp_path / "CONTEXT.md").write_text(
        "# Router\n\n## Routing table\n"
        "| q | r |\n|---|---|\n"
        "| skills | `memory/skills/CONTEXT.md` |\n")
    (vault / "skills" / "CONTEXT.md").write_text(
        "# Skills\n\n"
        # Written the way a person reads it -- relative to `memory/`, the
        # nearest ancestor that makes the sentence unambiguous -- not to
        # `skills/`, and without a `../` to say so.
        "further: `knowledge/domains/vision.md`\n")
    (vault / "knowledge" / "domains" / "vision.md").write_text(
        "---\ntitle: Vision\n---\n# Vision\n" + "x" * 500)
    return vault


def test_links_resolves_the_ancestor_relative_target(tree):
    """Ground truth: `links.py` finds it via its ancestor walk."""
    source = tree / "skills" / "CONTEXT.md"
    got = links.resolve("knowledge/domains/vision.md", source, tree)
    assert got == (tree / "knowledge" / "domains" / "vision.md").resolve()


def test_navigation_descend_now_finds_the_same_target(tree):
    """Was a bug: `_descend` used to try only `router.parent` (`skills/`), so
    `skills/knowledge/domains/vision.md` -- which does not exist -- was the
    only candidate it checked, and the target was dropped with no trace: not
    a hop, not in `unresolved` (that list is only populated by `routes()` for
    the top-level table; `_descend` never appended to it), so a route through
    `skills/CONTEXT.md` silently under-counted its own cost.

    Fixed by having `navigation._resolve` share `links._roots()`'s ancestor walk.
    This test pins the fix: it fails again if `_resolve` regresses to a
    single root.
    """
    router = tree / "skills" / "CONTEXT.md"
    repo = tree.parent            # `_resolve` is rooted at the repository (R3b)
    seen = {"CONTEXT.md", "memory/skills/CONTEXT.md"}
    hops = navigation._descend(router, repo, seen)
    assert [h.rel for h in hops] == ["memory/knowledge/domains/vision.md"]

    routes = navigation.routes(tree)
    skills_route = next(r for r in routes if r.question == "skills")
    assert any(h.rel == "memory/knowledge/domains/vision.md"
               for h in skills_route.hops)


def test_targets_shares_links_candidate_test():
    """`_targets` must not carry its own idea of what a path-shaped token is.

    It used to: a loose `"." in Path(tick).name` rule that would have called an
    unknown-extension bare word (`nonsense.zx`) or a metacharacter name
    (`report*.md`) a target, where `links._is_candidate` -- the tree's one
    pointer test -- rejects both. The two predicates never disagreed on the
    live tree (a 2026-09-05 check found zero divergence), but they had already
    drifted apart in intent, and a backticked token must mean the same thing in
    the pointer audit and the cost measurement. Pinning this stops `_targets`
    regressing to a local re-derivation.
    """
    accepted = navigation._targets("`skills/CONTEXT.md` and `knowledge/l1.md`")
    assert accepted == ["skills/CONTEXT.md", "knowledge/l1.md"]
    # Unknown-extension and metacharacter tokens: the old local rule accepted any
    # token whose last segment held a `.`, which takes both of these; the shared
    # predicate rejects them for want of a known extension / for the metacharacter.
    assert navigation._targets("`nonsense.zx`") == []
    assert navigation._targets("`report*.md`") == []
    # A prose word with no path shape is not a target, same as links.
    assert navigation._targets("`deny` and `authority: human`") == []
