# `system/checks/` — the Threshold — Tier 2 Router

<!-- GENERATED FILE — do not hand-edit. Rebuild: `familiar skills index` -->

<!-- checks: Falsified when a gate, a test, the healthcheck, or an evaluation's rule changes: whether a component is working, and whether it is worth it. The WEAKEST subject by the category test -- a gate is arguably a concept spanning the whole repo -- and it is flagged for the first review rather than quietly kept. The evaluation half was ruled 2026-10-25 (dev/evaluation/PLAN.md decision 2). -->

The gates a change passes before it lands — tests and the review of a diff. The thinnest subject here, and the one closest to the engineering habits the library adopted wholesale: a procedure about a gate, not about the machinery the gate guards.

| Skill | What it does | Origin | Trust |
|---|---|---|---|
| `factchk` | "Verify a claim asserted as real against sources in both directions before it ships: could the absurd be real, could the obvious be false? Fixes the mechanically clear errors and flags the judgment calls." | imported (link) | trial |
| `mandela` | "Audit an eval, metric or experiment for leakage: does independent ground-truth enter, or are model, scorer and designer only confirming each other? Returns only the patterns that fire, each with an independence fix. Read-only." | imported (link) | trial |

Always-on companions, loaded regardless of which skill fires:
`../../../../config/practice/conventions/code-style.md`.
