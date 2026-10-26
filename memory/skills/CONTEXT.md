# Skills — Tier 0 Router

<!-- PARTLY GENERATED FILE — the BEGIN/END blocks are rebuilt by -->
<!-- `familiar skills index`; the prose is hand-maintained here. -->
<!-- BUDGET: 2400 chars (skill-routing.md). Names BRANCHES, never skills. -->

Skills are **not installed into any harness**. Reach one by reading
`skills/<branch>/<subject>/<name>/SKILL.md`. Never load the library wholesale.
Rationale: [[skill-routing]].

## How to pick a skill

Stop at the first signal that answers.

| # | Signal |
|---|---|
| 1 | **Human named it** — a slash command, a bundle, or "use X". Always wins. |
| 2 | **Scope binding** — the working directory (below). Free; costs no call. |
| 3 | **Trigger match** — task vocabulary vs the trigger index. Verify first. |
| 4 | **Subject browse** — a branch `CONTEXT.md`, then a subject one. |

If none resolve, **ask** or proceed without a skill. Loading one "just in case"
is the failure this router prevents.

## Branches

<!-- BEGIN:BRANCHES (generated) -->
| Branch | Descend when the task involves… | n |
|---|---|---|
| `areas` | The World: subject knowledge, mirroring Areas A-P. This is where knowledge lands and it never retires. | — |
| `projects` | The Workings: a leaf here holds claims that OUTLIVE the plan, because the plan stays in the project's own directory (../../CLAUDE.md rule 5 forbids a plan store). | — |
| `system/` | The Workshop: what we built and maintain. Mirrors the codebase's own directories one scale down. | 16 |
<!-- END:BRANCHES -->

A branch without a trailing slash has no skill yet — declared, not missing.
`system/`'s router lists its subjects.

Bundles (signal 1): see `bundles/`.

## Scope bindings

A **prior, not a filter** — it reorders candidates, never removes them. One
exception: a hard boundary.

<!-- BEGIN:SCOPES (generated) -->
| Working directory | Branches |
|---|---|
| `01_PROJECTS/**` | projects, areas |
| `02_AREAS/B_Tech/**` | areas |
| `06_SYSTEM/**` | system |
| `03_ZETTEL/**` | **none — no read, no write** (`../../config/boundaries/read-write.yaml` enforces) |
<!-- END:SCOPES -->

## Two standing rules

- **Skills cite knowledge, never restate it.** Facts live in `../knowledge/`.
- **Never load a `trust: quarantine` skill** without saying so first. A
  `trust: trial` skill may be used — report afterwards whether it helped.
