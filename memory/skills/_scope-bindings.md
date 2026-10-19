---
title: Scope bindings — source for the generated Tier 0 router
authority: human
bindings: [
  "01_PROJECTS/** :: projects, areas",
  "02_AREAS/B_Tech/** :: areas",
  "06_SYSTEM/** :: system",
  "03_ZETTEL/** :: **none — no read, no write** (`../../config/boundaries/read-write.yaml` enforces)"
]
---

# Scope bindings

**Source, not a derived artifact.** `familiar skills index` reads the
`bindings:` list above and renders it into the `BEGIN:SCOPES` block of
`CONTEXT.md`. Edit here; never edit the generated block.

Resolution signal 2 ([[skill-routing]]). A binding is a
retrieval **prior, not a filter** — it reorders candidates and never removes
them, per the `s_min` floor in [[memory-ranking]].

The `03_ZETTEL/**` row is the one exception: a hard boundary, enforced at
level 2 by the guards compiled from `../../config/boundaries/read-write.yaml`, not by this table.

Not derivable from skill frontmatter today — every canonical skill declares
`scope: []`, and the `03_ZETTEL` row corresponds to no skill at all. If skills
ever carry real `scope:` globs, revisit whether this file can be generated.

**A prior over branches is coarse by construction after O6b.** Every canonical
skill sits under `system/`, so `06_SYSTEM/** :: system` merely reorders the whole
library; it no longer discriminates. Filing a skill under the `areas` or
`projects` branch is what would give this table resolution again — that is the
backlog the O6b entry names (multi-context skills, one skill reachable from more
than one place). The alternative, a RHS of subject names, was considered and
rejected for now: it would have to be rewritten at every re-filing, which is the
judgement call a branch binding is meant to spare.
