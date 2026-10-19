---
title: Prior art reviewed — agent memory systems
summary: Memory designs already reviewed and rejected — check before proposing one
origin: authored
authority: agent
trust: trial
last_verified: 2026-08-30
use_count: 15
last_used: 2026-10-09
promoted_from: []
source: see §Sources
supersedes:
related: [memory-architecture, memory-ranking, consolidation-cycle, skill-routing, journal-index, knowledge-index, memory-poisoning-posture, agent-prompt-dream-memory-consolidation]
tags: [prior-art, literature, memory, decisions]
scope: ["06_SYSTEM/**"]
area: [A, B]
stability: permanent        # decisions taken, not claims about the world - it says so itself
verified_log: [2026-08-30]
---

# Prior art reviewed

What was read while designing this system, what was taken, and **what was
rejected and why**. Exists so a future agent does not re-read the same papers
and re-propose the same rejected ideas.

## Verdicts

| Source | Taken | Rejected |
|---|---|---|
| **TrustGraph** (agent-memory guide) | provenance tracking; consolidation as a periodic pass | graph DB as store; **LLM-generated confidence scalars** |
| **A-MEM** (Xu et al., NeurIPS'25) | memory-evolution → bidirectional `related:` repair | embedding-based link generation |
| **HippoRAG** (Gutiérrez et al., NeurIPS'24) | — | PPR over an extracted KG: solves multi-hop retrieval we do not have |
| **Zheng et al., M²I** (Engineering 55, 2025) | abstract↔concrete pointers; stability-compartment migration; System II→I promotion | the entire neural-architecture programme |
| **Model-assigned `subject:` from declared criteria** (this system's own `ontology` track, O4b) | the BAND: at `accept` the answer was right 13 of 13, three runs running | the LABELLING: 20/19/19 of 31 against a bar of 27 — the criteria do not cut the corpus by themselves |
| **Claude Code "Dream" consolidation prompt** | merge-then-prune: fold new signal into canonical topic files rather than near-duplicates, prune the index, delete contradicted facts at the source | the agent-judgment classification — stage 9 used to replace it with a deterministic classifier; both were removed 2026-09-11 |

## Why the recurring rejections

**Graph/vector store as truth.** Violates the governing rule in
[[memory-architecture]]: markdown is truth, every index is a disposable cache.
Also needs a running service, which this system deliberately does not have.

**LLM-generated confidence scores.** TrustGraph increments confidence by `+0.1`
and decays by `×0.9`. Those numbers are unfalsifiable and accumulate false
precision. `last_verified` plus a `## Verification` command is strictly better:
it is a claim someone can check and disprove. This is a place where the design
beats the literature rather than trailing it.

**Model-assigned categories from written criteria.** Measured 2026-09-30, not
argued: one `choice` question per leaf over the thirteen declared subjects,
scored against the assignment a human ratified by moving each leaf into its
folder. **20, 19 and 19 of 31 across three runs, against a bar of 27.** The
same eleven leaves were wrong every time, so this is a property of the criteria
and not sampling noise.

The failure has a shape, and the shape is the useful part:

- **At the `accept` band the model was right 13 of 13, in all three runs, over
  an identical set of leaves.** There were **zero confident errors**. A
  vocabulary that was merely prose would produce confident nonsense; this one
  produces correct answers where it discriminates and *says so* where it does
  not.
- The other 18 land in `ask` and are right 39% of the time — above chance
  (1 in 13) and far below usable.
- The confusions are structural, not scattered: `harness` and `pass` leak four
  leaves each, and `tree` and `boundaries` attract five and three. Those pairs
  are not distinguishable from a leaf's title, summary and headings.

**So the honest verdict is narrower than "the criteria are prose".** What is
refuted is *unattended* labelling from criteria alone. What survives is the
band: an `accept`-band answer was trustworthy every single time, which is the
calibration working exactly as designed. Anything built on this must be
proposal-only, with the `ask` band going to a human — which is what the queue
already does.

**Do not repair the criteria to pass this test.** Rewriting them against these
eleven known failures and re-running scores the model on its own answer key;
a repaired vocabulary needs a corpus that did not produce it.

**The scope of retirement, confirmed by the user 2026-10-09.** What retires is
**unattended labelling from criteria alone** — the `ontology` track's O5a as
written, and O5d with it. **What stands is the schema, the registers, the checks
and the moves**: each has its own exit and each met it, and the falsification
never touched them. So this row rejects the *labelling*, not the `subject:`
field or the thirteen-subject vocabulary that `promoted_from:` and the queue's
human-decided proposals still write. Read it that way before citing it against a
facet.

**A reasoner, triple store, or OWL/SKOS serialisation of the registers.**
Ruled out 2026-10-09, and the rejection stands. At ~30 leaves the discipline that
matters is McComb's: *the fewest concepts that promote interoperability* (Semantic
Arts, below). The registers in `config/knowledge/` are that ontology, in YAML a
check reads. A serialisation would add a format and a toolchain, and nothing here
would query it. Seale's case for ontology as a retrieval pre-filter ("the
ontology is the map, the agent is the driver") was the hypothesis behind the
journal's branch facet. O5c measured it at 301–330 entries and did not confirm
it ([[journal-index]]).

**A graph walker over the assertion register (the `ontology` track's O7).**
Proposed as `a `graph <path>` verb --hops=N`: no edge store, no service.
**Retired 2026-10-13, unbuilt, by the user's ruling.** The rule it was gated on
stays in force: **no question, no walker.** A walker is justified only by a
written question that `grep`, `INDEX.md` and a faceted journal search cannot
answer, and none was written. The one argument for it is context size (265 KB
of knowledge against a 64k window, `dev/jev/PLAN.md` §Size constraint): a
decision model's state must be assembled from a slice. That argument does not
hold yet, for two measured reasons. O4b refuted unattended labelling (row
above), so the model a walker would feed may only propose. O5c (2026-10-12/13)
traced its retrieval misses to where entries are filed, not to missing hops. A
future cap on context is therefore not a mandate. Write the question first,
then open a new track for it.

**Embedding retrieval over `knowledge/` and `skills/`.** ~40 curated documents
with a hand-designed hierarchy and declared `triggers:`. Lexical matching is
exact, explainable, and needs no model. Embeddings are reserved for `journal/`
(D4, M4), where the corpus is unbounded and hand-indexing is impossible.

## Zheng et al. — what actually transfers

A perspective paper: it surveys and proposes, and validates nothing
empirically. Its four pillars target **model internals**, not an external
knowledge base, so most of it is out of scope. Three ideas are not.

### 1. Abstract↔concrete association → resolvable `promoted_from:`

§4.1 and Fig. 3 (after Spens & Burgess 2024): memory is not a copy of an episode
but a **reconstruction** from semantic content plus stored residual detail.
Recall needs both the concept and a route back to the instance.

We have the direction (`journal/` distils upward into `knowledge/`) but no route
back: `promoted_from:` was a prose string. **Changed 2026-08-30 to a list of
resolvable paths.** A leaf that fails verification can then be repaired by
re-reading the episodes that produced it, instead of re-derived from nothing.

### 2. A spectrum of decay rates, not one tuned rate

§5.2 and Fig. 4 (after Wang et al., *Nat Mach Intell* 2023): the *Drosophila*
γ mushroom body has five compartments on a **stability↔forgetting gradient**;
the AI mapping keeps five learners of differing plasticity rather than one tuned
compromise, so that neither "excessive stability" nor "excessive forgetting"
dominates. The paper's own framing: regulation should be **adaptive**, selecting
the mode that suits the content.

Our `stability` is author-declared, two-valued, and — by the rule in
`memory-ranking.md` — never written by the consolidator. That rule exists to
stop the formula chasing its own tail, and it stays. But the compartment a leaf
sits in should still be able to change with evidence. See
`memory-ranking.md` §Stability migration for how both hold at once.

### 3. System II → System I promotion

§6, after Kahneman's dual-process theory: migrate work from slow deliberate
System II into fast intuitive System I, so a decision once reasoned about
becomes free the next time.

Maps exactly onto skill routing. Signal 2 (scope binding — no model call, no
tokens) is System I; signal 4 (category browse — a round trip) is System II. A
selection that needed a browse should leave a `triggers:` entry behind, so the
next occurrence resolves for free. See [[skill-routing]] §Trigger promotion.

### 4. Noted, not adopted — fuzzy hash access

§4.1/§4.3.2, after Dasgupta et al. (*Science* 2017): the fly olfactory circuit
implements locality-sensitive hashing over sparse high-dimensional inputs —
approximate nearest neighbours with **no model to run**. Relevant to M4 on a
machine with no discrete GPU, as an alternative to a neural embedding index.

Not adopted: at journal scale, plain lexical search is simpler and probably
better. Revisit only if M4's embedding index proves too slow on CPU.

### Confirms, rather than changes

§4.1's "spatiotemporal dynamic association" — memory decomposed and allocated
across regions, dynamically updated over time, citing the Tolman–Eichenbaum
Machine — is direct support for the `scope:`/`area:`/journal-date axes already
built (`memory-ranking.md` §Spatial prior). The paper notes current ML "lacks
explicit spatiotemporal encoding"; ours has it. Nothing to change.

## Sources

- Zheng Q, Liu H, Zhang X, et al. Machine Memory Intelligence: Inspired by Human
  Memory Mechanisms. *Engineering* 2025;55:24–35. doi:10.1016/j.eng.2025.01.012
- Spens E, Burgess N. A generative model of memory construction and
  consolidation. *Nat Hum Behav* 2024;8(3):526–43. (Zheng ref [37])
- Wang L, Zhang X, Li Q, et al. Incorporating neuro-inspired adaptability for
  continual learning. *Nat Mach Intell* 2023;5(12):1356–68. (ref [56])
- Dasgupta S, Stevens CF, Navlakha S. A neural algorithm for a fundamental
  computing problem. *Science* 2017;358(6364):793–6. (ref [41])
- Whittington JCR, et al. The Tolman–Eichenbaum machine. *Cell* 2020;183(5):1249–63. (ref [38])
- Xu W, et al. A-MEM: Agentic Memory for LLM Agents. NeurIPS 2025. arXiv:2502.12110
- Gutiérrez BJ, et al. HippoRAG. NeurIPS 2024. arXiv:2405.14831
- TrustGraph, Agent Memory. https://trustgraph.ai/guides/key-concepts/agent-memory/
- McComb D. Semantic Ontology: The Basics. Semantic Arts.
  https://www.semanticarts.com/semantic-ontology-the-basics/
- Seale T. LinkedIn posts on ontology and LLM agents, 2023–2026, among them
  "Ontology is the Map, Agent is the Driver" and "Ontologies can save you
  tokens". Held in the user's bookmarks, not in git.

PDF held at `~/Downloads/1-s2.0-S2095809925000293-main.pdf` (not in git).

The Claude Code "Dream" prompt is held in-tree at
`agent-prompt-dream-memory-consolidation.md`
(extracted 2026-09-01 to inform stage 9's design — that stage was removed
2026-09-11 along with the lore DB it triaged; the extraction is kept because the
merge-then-prune reasoning still informs stage 4).

## Verification

Claims here are about *decisions taken*, not about the world, so they do not
rot in the usual way. What can go stale is whether the decision still holds —
check against [[memory-architecture]] §Governing rule and [[skill-routing]].
