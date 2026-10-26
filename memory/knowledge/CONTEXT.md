# Knowledge Tree — Router

<!-- LAYER 2 · ROUTING ONLY · Content lives in leaves, never here -->

**Looking for a fact, not a folder? Read `INDEX.md`.** It lists every subject
with its leaves' trigger terms; the subject's own `INDEX.md` lists its leaves, one
line each. Two levels since 2026-10-21, when one flat file outgrew its budget
([[knowledge-index]], O3d). The branches below are for navigating by hand.

<!-- BEGIN:BRANCHES (generated) -->
| Branch | Holds | n |
|---|---|---|
| `system/` | The Workshop: what we built and maintain. Mirrors the codebase's own directories one scale down. | 42 |
<!-- END:BRANCHES -->

Each branch's `Holds` line is its **criteria in `config/knowledge/subjects.yaml`**
and `n` is counted from disk; O3a made the register the source, because a
description hand-edited into a router is a fact this table then copies. The
routers themselves are generated from the same register — except `areas/`,
which indexes Areas A–P rather than leaves ([[knowledge-index]] §Known
duplication). Rebuild with `familiar knowledge index`.

**Everything here is agent-writable and scored.** `../../engine/knowledge/tree.py`
decays, ranks and prunes every leaf, so a directive file placed in this tree
would be treated as disposable. Directive standing rules live in
`../../config/practice/conventions/`, `../../config/practice/user/` and `../../config/boundaries/` instead.

## Rules for this tree

1. **One canonical home per fact.** If a fact appears in two leaves, one
   becomes a pointer to the other.
2. **One-way references.** A leaf points outward to what it needs; nothing
   points down into a deeper leaf except through a `CONTEXT.md`.
3. **Every folder carries a `CONTEXT.md`** once it holds more than ~4 files.
   It routes; it never holds content.
4. **Every leaf carries frontmatter** (`_leaf-template.md`). A leaf without it
   is invisible to maintenance and will rot.
5. **Leaves stay under ~200 lines.** Longer means it is two topics.
6. **Depth is capped at 5 levels below `memory/`**; breadth is unlimited. Need
   a 6th? The parent topic is too broad — split it sideways into a sibling.

**Splitting is the maintaining agent's job.** When a *router* outgrows what it
can triage — roughly 12 rows, or when its rows stop sharing a single question —
split it and say so in the session report. The row is the unit, not the branch
above it: `system/CONTEXT.md` lists thirteen subjects, and the subject routers
below it list the leaves. `meta/` was carved out of `operations/` under exactly
that rule.
