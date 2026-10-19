"""memory/knowledge/meta/consolidation-cycle.md — a leaf is appended to or marked superseded, never rewritten.

The rule only exists if something would fail when it is broken. Three things
are tested here, in increasing distance from the code:

  1. `_append_only` is a real check, not a comment that agrees with the
     implementation -- fed a diff WITH a deletion it refuses.
  2. `_rewrite_suspect` catches the realistic route, which is a model pasting a
     whole rewritten leaf into `BODY:` where an addition was asked for. Applied
     blindly, that diff is all insertions, the report shows a green add-hunk,
     and the leaf silently ends up holding two whole versions.
  3. `supersede-leaf` is the LEGAL route, and the marking half of its patch
     touches the frontmatter marking keys and nothing else.

Plus the tombstone: `MEMORY.md` was deleted 2026-09-04 and stage 4 kept offering
it as a target for weeks, with a proposal that would have re-created it as a
leaf-shaped mutant. That must not come back.
"""
import datetime as dt

import pytest

from consolidation import pass_ctx
from consolidation.stages import consolidate


LEAF = """---
title: Backup restic
trust: trusted
last_verified: 2026-09-01
supersedes:
superseded_by: []
related: []
---

# Backup restic

What the leaf is for.

## Verification

```sh
restic check
```

## Retention

Seven daily, four weekly, two monthly.

## Failure modes

A timer that never fired is indistinguishable from one that failed.
"""


def _ctx(tmp_path):
    agents = tmp_path / "memory"
    (agents / "knowledge" / "operations").mkdir(parents=True)
    (agents / "journal" / "2026" / "09").mkdir(parents=True)
    (agents / "journal" / "2026" / "09" / "2026-09-03_a.md").write_text(
        "---\ndate: 2026-09-03\n---\n\n# A\n\nsomething durable\n")
    (agents / "knowledge" / "operations" / "backup-restic.md").write_text(LEAF)
    return pass_ctx.Pass(agents, tmp_path / "data", False, dt.date(2026, 9, 3))


def _prop(**kw):
    p = {"summary": "s", "target": "knowledge/operations/backup-restic.md",
         "kind": "extend-leaf", "why": "w", "supersedes": "", "body": "## More\n\ntext\n"}
    p.update(kw)
    return p


# ── 1. the invariant is a check, not a comment ───────────────────────────────

def test_append_only_refuses_a_diff_that_deletes_a_line():
    diff = ("--- a/memory/knowledge/x.md\n+++ b/memory/knowledge/x.md\n"
            "@@ -1,2 +1,2 @@\n kept\n-gone\n+replacement\n")
    with pytest.raises(consolidate._IllegalPatch):
        consolidate._append_only(diff, existed=True)


def test_append_only_accepts_a_pure_insertion():
    diff = ("--- a/memory/knowledge/x.md\n+++ b/memory/knowledge/x.md\n"
            "@@ -1,1 +1,2 @@\n kept\n+added\n")
    consolidate._append_only(diff, existed=True)      # must not raise


def test_append_only_is_vacuous_for_a_file_that_does_not_exist_yet():
    """A new leaf's diff is `--- /dev/null`; there is nothing to delete."""
    consolidate._append_only("--- /dev/null\n+++ b/memory/knowledge/x.md\n+all\n",
                             existed=False)


def test_an_ordinary_extension_emits_no_deletion(tmp_path):
    ctx = _ctx(tmp_path)
    diff = consolidate._as_patch(ctx, _prop())
    assert not [l for l in diff.split("\n")
                if l.startswith("-") and not l.startswith("---")]


# ── 2. the realistic route: a rewrite pasted as an addition ──────────────────

def test_a_pasted_leaf_frontmatter_is_not_an_addition(tmp_path):
    ctx = _ctx(tmp_path)
    whole = "---\ntitle: Backup restic\n---\n\n# Backup restic\n\nrewritten\n"
    why = consolidate._rewrite_suspect(ctx, _prop(kind="extend-leaf", body=whole))
    assert "frontmatter block" in why


def test_a_body_reproducing_every_heading_at_full_length_is_a_rewrite(tmp_path):
    """The signature of a rewrite: the target's COMPLETE heading sequence, in
    order, at comparable length. A genuine extension repeats at most one
    heading and stays short."""
    ctx = _ctx(tmp_path)
    body = ("# Backup restic\n\nDifferent prose.\n\n## Verification\n\nx\n\n"
            "## Retention\n\ny\n\n## Failure modes\n\nz\n")
    why = consolidate._rewrite_suspect(ctx, _prop(body=body))
    assert "headings, in order" in why, why


def test_a_genuine_extension_under_one_existing_heading_is_kept(tmp_path):
    """The false-positive this guard must not produce: adding a bullet to a
    section that already exists repeats that heading and is legitimate."""
    ctx = _ctx(tmp_path)
    body = "## Verification\n\n- also `restic snapshots`\n"
    assert consolidate._rewrite_suspect(ctx, _prop(body=body)) == ""


def test_a_short_restatement_that_repeats_nothing_is_kept(tmp_path):
    ctx = _ctx(tmp_path)
    assert consolidate._rewrite_suspect(
        ctx, _prop(body="## Snapshot pruning\n\n`restic forget --prune`\n")) == ""


def test_a_new_leaf_may_echo_headings_and_carry_frontmatter(tmp_path):
    ctx = _ctx(tmp_path)
    p = _prop(kind="new-leaf", target="knowledge/operations/new.md",
              body="---\ntitle: New\n---\n\n## Verification\n\nx\n")
    assert consolidate._rewrite_suspect(ctx, p) == ""


def test_a_suspected_rewrite_is_reported_and_never_reaches_the_patch(tmp_path,
                                                                   monkeypatch):
    reply = ("PROPOSAL: rewrite the backup leaf\n"
             "TARGET: knowledge/operations/backup-restic.md\n"
             "KIND: extend-leaf\nWHY: it is stale\nBODY:\n"
             "# Backup restic\n\n## Verification\n\nrestic check\n\n"
             "## Retention\n\nseven daily\n\n## Failure modes\n\nsilent\nEND\n")
    ctx = _stage4(tmp_path, reply, monkeypatch)
    assert ctx.proposals == [], "a suspected rewrite must not be appliable"
    warns = [n for n in ctx.notes if "dropped rather than appended" in n.text]
    assert len(warns) == 1
    assert "supersede-leaf" in warns[0].text, "the note must name the legal route"
    assert "unvalidated" in warns[0].text, "the threshold is a guess and says so"


# ── 3. the legal route for replacement ───────────────────────────────────────

def test_supersede_creates_the_replacement_and_marks_the_old_leaf(tmp_path):
    ctx = _ctx(tmp_path)
    p = {"summary": "Backup restic, rewritten", "kind": "supersede-leaf",
         "target": "knowledge/operations/backup-verified.md",
         "supersedes": "knowledge/operations/backup-restic.md",
         "why": "w", "body": "# Backup restic\n\nNew contraction.\n"}
    diff = consolidate._as_patch(ctx, p)
    assert "+++ b/memory/knowledge/operations/backup-verified.md" in diff
    assert "+++ b/memory/knowledge/operations/backup-restic.md" in diff
    assert "+superseded_by: [knowledge/operations/backup-verified.md]" in diff
    assert "+trust: deprecated" in diff
    assert "-trust: trusted" in diff


def test_the_marking_patch_deletes_only_marking_keys_and_leaves_the_body(tmp_path):
    """`trust: trusted` -> `trust: deprecated` is a deletion, and it is the ONE
    kind this module may produce. The body must come through byte-identical:
    that is what "retained for provenance" has to mean to be worth saying."""
    ctx = _ctx(tmp_path)
    rel = "knowledge/operations/backup-restic.md"
    before = (ctx.repo / "memory" / rel).read_text()
    body_lines = {l for l in before.split("\n---\n", 1)[1].split("\n") if l.strip()}

    patch = consolidate._as_patch(ctx, {
        "summary": "s", "kind": "supersede-leaf",
        "target": "knowledge/operations/new.md", "supersedes": rel,
        "why": "w", "body": "body\n"})

    # The marking half is everything after the second file's `+++` header.
    tail = patch.split("+++ b/memory/knowledge/operations/backup-restic.md")[1]
    deletes = [l for l in tail.split("\n")
               if l.startswith("-") and not l.startswith("---")]
    assert deletes, "the marking has to actually happen"
    assert all(l[1:].split(":", 1)[0] in consolidate.MARKING_KEYS
               for l in deletes), deletes
    assert not [l for l in deletes if l[1:] in body_lines], "a body line was deleted"


def test_a_marking_patch_that_deletes_a_body_line_is_refused(tmp_path):
    old = "---\ntrust: trusted\n---\n\nkeep me\n"
    diff = ("--- a/agents/x.md\n+++ b/agents/x.md\n@@ -4,1 +4,0 @@\n-keep me\n")
    with pytest.raises(consolidate._IllegalPatch):
        consolidate._marking_only(diff, old, "x.md")


def test_a_marking_patch_that_deletes_an_unmarked_key_is_refused(tmp_path):
    """`title:` sits in the frontmatter like `trust:` does. Only MARKING_KEYS
    are reachable, or the rule would be \"anything above the first `---`\"."""
    old = "---\ntitle: x\ntrust: trusted\n---\n\nbody\n"
    diff = ("--- a/agents/x.md\n+++ b/agents/x.md\n@@ -2,1 +2,1 @@\n"
            "-title: x\n+title: y\n")
    with pytest.raises(consolidate._IllegalPatch):
        consolidate._marking_only(diff, old, "x.md")


def test_supersede_refuses_a_target_that_names_nothing(tmp_path):
    ctx = _ctx(tmp_path)
    p = {"summary": "s", "kind": "supersede-leaf",
         "target": "knowledge/operations/new.md",
         "supersedes": "knowledge/operations/does-not-exist.md",
         "why": "w", "body": "body\n"}
    with pytest.raises(consolidate._IllegalPatch):
        consolidate._as_patch(ctx, p)


def test_supersede_refuses_an_empty_supersedes_field(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(consolidate._IllegalPatch):
        consolidate._as_patch(ctx, _prop(kind="supersede-leaf",
                                         target="knowledge/operations/new.md"))


def test_supersede_refuses_self_reference(tmp_path):
    ctx = _ctx(tmp_path)
    with pytest.raises(consolidate._IllegalPatch):
        consolidate._as_patch(ctx, _prop(
            kind="supersede-leaf",
            target="knowledge/operations/backup-restic.md",
            supersedes="knowledge/operations/backup-restic.md"))


def test_an_illegal_supersede_is_an_error_note_not_a_dead_stage(tmp_path,
                                                               monkeypatch):
    reply = ("PROPOSAL: replace with nothing\n"
             "TARGET: knowledge/operations/new.md\nKIND: supersede-leaf\n"
             "SUPERSEDES: knowledge/operations/ghost.md\nWHY: w\nBODY:\nbody\nEND\n")
    ctx = _stage4(tmp_path, reply, monkeypatch)
    assert ctx.proposals == []
    errs = [n for n in ctx.notes if n.level == "error" and "patch refused" in n.text]
    assert len(errs) == 1


# ── the tombstone ────────────────────────────────────────────────────────────

def test_MEMORY_md_is_not_offered_to_the_model_as_a_target(tmp_path, monkeypatch):
    seen = {}

    def fake(prompt, timeout=None):
        seen["prompt"] = prompt
        return "NOTHING"

    monkeypatch.setattr(consolidate.model, "available", lambda: True)
    monkeypatch.setattr(consolidate.model, "ask", fake)
    consolidate.run(_ctx(tmp_path))
    assert "MEMORY.md" not in seen["prompt"], (
        "the file was deleted 2026-09-04; offering it as a TARGET is how it came "
        "back as a leaf-shaped orphan")


def test_a_proposal_naming_MEMORY_md_is_dropped_not_merely_reported(tmp_path,
                                                                  monkeypatch):
    reply = ("PROPOSAL: put the invariant in MEMORY.md\nTARGET: MEMORY.md\n"
             "KIND: memory-pointer\nWHY: w\nBODY:\n## Now\n\n- something\nEND\n")
    ctx = _stage4(tmp_path, reply, monkeypatch)
    assert ctx.proposals == []
    warns = [n for n in ctx.notes if "MEMORY.md" in n.text and n.level == "warn"]
    assert len(warns) == 1 and "orphan" in warns[0].text


# ── harness ──────────────────────────────────────────────────────────────────

def _stage4(tmp_path, reply, monkeypatch):
    monkeypatch.setattr(consolidate.model, "available", lambda: True)
    monkeypatch.setattr(consolidate.model, "ask", lambda *a, **k: reply)
    ctx = _ctx(tmp_path)
    consolidate.run(ctx)
    return ctx
