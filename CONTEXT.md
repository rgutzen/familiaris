# Agent Context — Entry Point

<!-- LAYER 0 · ROUTING ONLY · BUDGET 800 tokens · NEVER put knowledge here -->
<!-- Seeded by `familiar structure skeleton` from engine/structure/skeleton/.
     Yours from here on: edit the rows, keep it a routing table. -->

## Routing table

**Stop at the first row that answers.** Reading a second file "to be safe" is
the cost this table exists to avoid.

| Looking for | Read |
|---|---|
| tone, disagreement, ask vs decide, how much to verify, response shape | `config/practice/conventions/collaboration.md` |
| prose style — leaves, docs, commit messages | `config/practice/conventions/voice.md` |
| code style, docstrings, solution hierarchy, correctness, performance | `config/practice/conventions/code-style.md` |
| who the user is — background, environment, values | `config/practice/user/user-identity.md` |
| paths agents must not read, write or push, and why | `config/boundaries/CONTEXT.md` |
| which skill fits this task | `memory/skills/CONTEXT.md` |
| the class list — entities, facets, subjects, relations | `config/knowledge/CONTEXT.md` |
| any fact this system has written down | `memory/knowledge/INDEX.md`, then the one leaf it names |
| what exactly happened on some past date | `memory/journal/` (exact recall; never bulk-load) |

Paths here are relative to the repository root: `memory/` changes with use,
`config/` when the user decides. The vault contract
(`config/vault.example.yaml`) says which paths are whose.

- **Always loaded:** `config/practice/user/user-identity.md` and
  `config/practice/conventions/collaboration.md`, compiled into each harness's
  entry point by `familiar context l1`. Everything else is reached by pointer.
- **Skills are not installed in any harness.** Route via
  `memory/skills/CONTEXT.md`; never load the library wholesale.
- **Directive:** the `human_owned` paths of the vault contract — an agent does not
  edit them; a change comes back as a proposal. `ROADMAP.md` is the one
  exception: edit it, and flag each edit in the turn.
