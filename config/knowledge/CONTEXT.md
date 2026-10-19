# Ontology — Router

<!-- LAYER 3 · DIRECTIVE · Agents READ these files; they never edit them -->

**The classes this system has, stated once so a check can read them.** Six
content files, one per register; the code that binds and applies them is
`../../engine/knowledge/ontology.py`, reached through
`../../engine/lib/_miniyaml.py`.

| The question | Read |
|---|---|
| who may WRITE a document — contracted or declared | `entities.yaml` |
| what makes a claim FALSE — the frontmatter facets and their domains | `facets.yaml` |
| where it is FILED — three branches, the subjects, A–P | `subjects.yaml` |
| what it POINTS AT — the walkable edges, and the coincidences that are not edges | `relations.yaml` |
| what a file may be CALLED — seven rules | `naming.yaml` |
| every known breach, its recommendation and its state | `violations.yaml` |

Every entry carries its criteria text, its layer (`category` · `concept` ·
`association`), its column (`assertion` · `coincidence`) and a `reviewed:` date.
The registers are the same three the rest of the system uses, so a `ls` here is
also the answer to *what change reaches this?*

- **Directive.** A vocabulary change is a proposal into the session report and
  a decision by the user. Nothing here is auto-repaired, and no check writes.
- **No compiled intermediate.** Boundaries compiles YAML → JSON only because its
  reader is a guard hook that cannot import a parser mid-session. Every reader of
  these files is Python, so it loads them directly — and `_miniyaml` is
  deliberately NOT extended for them: the files stay inside its subset, and a
  test asserts both that and its frozen surface.
- **A known gap and a new breach must not look the same.** An entry declared in
  `violations.yaml` warns and the gate stays green; a value nobody declared
  fails. That is the whole reason the register is data rather than prose.
- **For people:** `README.md` draws all six registers and their terms. Not
  agent-loaded; the registers win any disagreement.
- **Not here:** the checks that apply the registers
  (`../../engine/checks/checks.py` — `ontology-valid`, `naming-valid`) and the
  reasoning behind each decision (`README.md` §Why this shape, and the leaves
  under `../../memory/knowledge/system/knowledge/`).
