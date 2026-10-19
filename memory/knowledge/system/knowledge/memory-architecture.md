---
title: Memory architecture
summary: The tree's architecture — what memory is, which store owns what
origin: authored
authority: human
trust: trusted
last_verified: 2026-08-30
use_count: 12
last_used: 2026-09-29
promoted_from: []  # originated 2026-08-28; no journal entry for that session
source:
supersedes:
related: [memory-mechanisms, memory-ranking, consolidation-cycle, knowledge-vs-skills, boundaries, hermes, obsidian-vault, ollama-local, pazras-structure, prior-art-memory-systems, user-vs-conventions, journal-index, voice, context-budget, knowledge-index, memory-poisoning-posture, pointer-following, agent-prompt-dream-memory-consolidation, file-naming, glossary]
tags: [memory, architecture, icm]
scope: ["06_SYSTEM/**"]
area: [B]
stability: stable
verified_log: [2026-08-30]
---

# Memory architecture

Four memory domains, distinguished by **who may write** and **whether
forgetting is permitted**. They are deliberately not one system.

## The four domains

| | D1 Zettelkasten | D2 Project | D3 System | D4 Index |
|---|---|---|---|---|
| Content | the user's thinking | how to work in one repo | how to work with the user | retrieval |
| Writer | **human only** | agent, freely | agent, human-gated | machine |
| Decay | **forbidden** | aggressive | slow | disposable |
| Compression | **forbidden** | the entire point | summarise | — |
| Privacy | **local models only** | cloud ok | cloud ok | local embedding |
| Lives in | `~/03_ZETTEL/` | *(retired 2026-09-11)* | `~/06_SYSTEM/memory/` | rebuildable cache |

**D2 — the per-repo store — was retired on 2026-09-11** together with lore,
which owned it (it was a git-tracked `.lore.md` per repo, mirrored from a
SQLite DB). The measurement that ended it is
`journal/2026/09/2026-09-10_lore-reevaluation.md`: the store was a lossy mirror
of each repo's own git history, its recall cost 2.2 s median and 102 s worst
case, and the price of having it was a 72-entry block injected into every
session. Per-project memory is now the repo's own `CLAUDE.md`/`AGENTS.md` plus
`journal/`. The tier is kept in this table as a retired row because leaves
promoted out of it carry `D2→D3` in their provenance comments.

D1's local-only rule is concrete: `03_ZETTEL/Working-Memory.md` contains health,
finance and housing material. It does not leave the machine.

**Decided 2026-08-30: D1 is human-maintained, full stop — agents neither read
nor write it.** This is enforced structurally, not by instruction: it is one
rule in `../../../../config/boundaries/read-write.yaml`, compiled to a `PreToolUse` hook in Claude Code
and a `tool.execute.before` plugin in opencode ([[boundaries]];
[[memory-mechanisms]] §Boundaries are structural). It supersedes the "local
models only" relaxation below, which is retained for the record but is not the
operative rule.

**Decided 2026-08-28.** Content operations on D1 are **local models only** —
no exceptions. *Structural* help (link suggestion, MOC skeletons, clustering by
title alone) may use a cloud model, since it need not read note bodies. That
relaxation is **backlogged, not adopted**: at 337 notes the corpus is still
manageable by hand, so nothing is gained by taking the risk yet. Revisit only
when hand-curation stops keeping up.

## Governing rule

**Markdown is truth. Every vector or graph index is a derived, disposable
cache.** No index is ever authoritative; all must be rebuildable from markdown.

This is what settles the RAG question, and it settles it differently per domain:

- **D3 (`knowledge/`, `skills/`) — no retrieval index.** Curated, hierarchical,
  with declared `triggers:` and a `scope:`/`area:` spatial prior. Exact lexical
  matching over frontmatter beats embeddings here and needs no model, no
  rebuild, no service. See [[skill-routing]] §The trigger index.
- **D4 over `journal/` — a local embedding index, eventually.** Unbounded,
  unindexable by hand, and exact recall is the point. Local model only; this
  machine has no discrete GPU, so embeddings are feasible and a generative
  reranker is not ([[ollama-local]]).

## Displacement, not truncation

`../../../../config/practice/user/user-identity.md` is capped at 1375 chars by hermes
(`~/.hermes/config.yaml` → `memory:`), matching `pazras.py` §CAPS. The cap is a
filing signal, not a limit on knowledge. On overflow: move the least-referenced
section into a `knowledge/` or `../../../../config/practice/conventions/` leaf and leave one pointer line
behind. Never truncate.

`MEMORY.md` was the other capped file under this rule and was **deleted
2026-09-04** — `memory/` serves every agent on this machine, and the always-on
layer is compiled from `CONTEXT.md` + `../../../../config/practice/user/user-identity.md` +
`../../../../config/practice/conventions/collaboration.md` by `familiar context l1`. The principle is unchanged
and still governs `knowledge/INDEX.md` (2,000 tok) and hermes' own store;
`README.md` §Displacement carries the current table.

Also: knowledge leaves are **claims with a decay score**; the conventions under
`knowledge/conventions/**` are **always-on policy**. They share housing but
not semantics. A document with `authority: human` is scored like any other and
appears in the report's quadrant table, but stage 6 never touches it — it is
reported, never demoted or archived (`engine/consolidation/stages/downscale.py`). Before 2026-09-11
this sentence pointed at a `conventions-are-policy` note in
[[consolidation-cycle]] that **never existed**; the fact above is the one
that did, and it is enforced in code rather than written down twice.

## `tags:` stays uncontrolled

`tags:` is the concept layer: free terms that let a leaf associate across
branches. It has no vocabulary, no check and no field contract, by decision
(user, 2026-10-09). A controlled `tags:` would become a second category layer
beside the folder. Do not tidy it into a vocabulary; revisit only if it needs
cleanup.

## Phase status

**Lives in `06_SYSTEM/ROADMAP.md` §Tracks and `06_SYSTEM/dev/memory/SPECS.md`,
not here.** Status is an intention that decays by completion; this leaf holds
claims that decay by becoming false. Keeping a copy here guaranteed one of them
would be stale — as it was: this section still read "Phase 0 pending" three
commits after Phase 0 was completed.

Memory phases are labelled **M0-M4** since 2026-08-30, to distinguish them from
`MIGRATION-PLAN.md`'s unrelated Phases 0-9.

## Verification

`ls ~/06_SYSTEM/memory/` shows the tree.
`wc -c ~/06_SYSTEM/config/practice/user/user-identity.md` must stay under 1375.
`engine/familiar context tree --check` asserts every always-loaded name
exists and is inside its budget — prefer it over the `wc -c` above, which cannot
tell a moved file from an empty one.

## Two rules about where things live

Both outlive any particular plan, which is why they are here and the phase
numbering that prompted them is not: **M0–M4 and `MIGRATION-PLAN.md`'s Phase
0–9 are scaffolding, and scaffolding stops being true the moment the plan
completes.** Numbering lives in `ROADMAP.md`; only the durable rules land here.

- **Provenance strings are never rewritten.** A frozen `promoted_from:` path
  records *when something happened*, so it is not renamed when the thing it
  names is later renumbered or retitled. A provenance link that is edited to
  stay tidy has stopped being provenance.
- **Plans never live in `knowledge/`.** The two decay in opposite ways: a
  knowledge leaf decays by becoming **false**, and is repaired by
  re-verification and scored by F/U; a plan decays by being **done**, and is
  repaired by deletion, which no score can detect. Putting a plan in the
  knowledge tree gives it a decay signal that will never fire. Status therefore
  has exactly one canonical home outside the tree — the docs-about-knowledge
  form of `knowledge/CONTEXT.md` rule 1, one canonical home per fact.
