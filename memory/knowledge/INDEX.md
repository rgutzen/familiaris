# Knowledge Index

<!-- GENERATED FILE — do not hand-edit. Rebuild: `familiar knowledge index` -->
<!-- READ ON DEMAND, WHOLE. This is the ONLY index between CONTEXT.md and a leaf: -->
<!-- one level of disclosure, never two (knowledge/system/knowledge/knowledge-index.md). -->

Every fact this tree holds, one line each. Paths are relative to `memory/knowledge/`.
**Read the leaf** — a row is a pointer, never the claim. Match the task's vocabulary
against the trigger terms; a match is **explainable**. No match anywhere means the
fact is not here — try `familiar knowledge journal search`, or say it is unknown.

32 leaves in 1 branches.

## `system/` — The Workshop: what we built and maintain. Mirrors the codebase's own directories one scale down.

| Leaf | What it holds | Trigger terms |
|---|---|---|
| `system/boundaries/boundaries.md` | Why the read/write boundary rules exist, how they compile, what they miss | boundaries, enforcement, hooks, privacy, guard |
| `system/checks/healthcheck.md` | Checking the system is sound; what a `--check` drift report means | systemd, healthcheck, stow, drift |
| `system/consolidation/agent-prompt-dream-memory-consolidation.md` | Verbatim prior art for the nightly pass — Claude Code's Dream prompt, pinned at ccVersion 2.1.235 | reference, prior-art, memory-consolidation, agent-prompt, imported |
| `system/consolidation/consolidation-cycle.md` | The nightly pass — what runs when, and what it is allowed to write | consolidation, scheduling, sleep, pruning, cron |
| `system/consolidation/memory-mechanisms.md` | Hooks and timers: what is actually enforced, and what is only asked for | hooks, automation, enforcement, consolidation |
| `system/consolidation/memory-poisoning-posture.md` | Why an injected claim cannot become this system's belief — five structural checks, and their limits | memory poisoning, prompt injection, indirect injection, trust promotion, provenance, unreviewed write access, curator authority, distilled_by |
| `system/consolidation/memory-ranking.md` | Scoring, decay, pruning, and the order retrieval returns things in | ranking, decay, pruning, retrieval, spatial |
| `system/consolidation/prior-art-memory-systems.md` | Memory designs already reviewed and rejected — check before proposing one | prior-art, literature, memory, decisions |
| `system/context/context-budget.md` | What a harness and a route cost in tokens; the `pazras-context` audit | context, tokens, audit, harness, overhead, claude-code, opencode, codex |
| `system/context/pointer-following.md` | Measured follow rates over the staged transcript corpus, and the always-on decision they inform | context, always-on, pointers, measurement, baseline |
| `system/harness/claude-code.md` | Claude Code — hooks, skills, plugins, settings | claude, cli, acp, hooks |
| `system/harness/codex.md` | The fifth harness — audited for cost, wired to nothing | codex, harness, tokens, unaudited |
| `system/harness/hermes.md` | hermes — local models, skills, bundles, prompt size | hermes, signal, gateway, cron |
| `system/harness/mcp-servers.md` | MCP servers — wiring, boundary enforcement, per-harness traps | mcp, retrieval, pi, hermes, opencode, claude-code, harness |
| `system/harness/ollama-local.md` | Local-model work on the 890M iGPU — models, VRAM, what actually runs | ollama, gpu, vram, local-llm |
| `system/harness/opencode.md` | opencode — plugins, providers, config | opencode, plugins, harness |
| `system/harness/orchestrators.md` | Subagents, delegation, multi-agent config — an open design question | orchestrators, subagents, harness, open-question |
| `system/harness/pi.md` | The `pi` harness — surfaces, subagents, the stow-safe subset | pi, harness, subagent, guard, tokens |
| `system/harness/rtk.md` | The `rtk` output filter — what it wraps, and the traps it sets for agents | rtk, tokens, output-filter, git, harness |
| `system/knowledge/journal-index.md` | The journal's shape, the M4 embedding index over it, and its two facets | journal, embeddings, retrieval, m4, ollama |
| `system/knowledge/knowledge-index.md` | The L2 disclosure index over this tree: one level, budgeted, generated | knowledge index, index.md, progressive disclosure, blanket injection, knowledge routing, summary frontmatter |
| `system/knowledge/knowledge-vs-skills.md` | Filing something new: a claim goes in knowledge, a procedure in a skill | knowledge, skills, architecture, icm |
| `system/knowledge/memory-architecture.md` | The tree's architecture — what memory is, which store owns what | memory, architecture, icm |
| `system/knowledge/obsidian-vault.md` | Browsing this tree in Obsidian — graph view, links, what breaks | obsidian, vault, navigation |
| `system/practice/user-vs-conventions.md` | Filing into `config/practice/user/`, `config/practice/conventions/` or `knowledge/` — which store owns it | user, conventions, filing, icm, layers |
| `system/publication/glossary.md` | The subject ids, their mythic names and their criteria, generated from the register | glossary, ontology, subjects |
| `system/schedule/scheduled-processes.md` | Anything unattended — timers, what runs when, what it may write | systemd, scheduling, timers, generated-artifacts |
| `system/skills/skill-adoption.md` | Vetting a skill arriving from anywhere — provenance and supply chain | skills, adoption, provenance, supply-chain |
| `system/skills/skill-routing.md` | How a task reaches a skill: the four resolution signals, zero-install | skills, routing, context, icm |
| `system/structure/file-naming.md` | What a file may be called, which structural file means what, and the renames the rules imply | file naming, naming convention, readme, context, index, hub file, _refs, rename a file |
| `system/structure/pazras-cli.md` | The folder-tree CLI's own traps — bash, config, systemd | pazras, bash, config, systemd, cli |
| `system/structure/pazras-structure.md` | Navigating or changing the PARA structure and its config | familiar, para, structure, config, areas |

Branch routers (`<branch>/CONTEXT.md`) are for human and Obsidian navigation. A model
that has read this file has already routed; descending into one is a second
routing level and buys nothing.
