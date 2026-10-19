# Boundaries — directives

<!-- GENERATED from config/knowledge/entities.yaml (the entity register — one rule per kind marked `directive: true`) by engine/boundaries/compile.py. Do not hand-edit. -->

Advisory: nothing here is enforced by the harness *reading* it. Claude Code and
opencode also enforce these at the tool call (`engine/boundaries/guard.py`,
`engine/boundaries/opencode-plugin/`); hermes and anything else rely on you.
`local` means inference on this machine (ollama, local-ollama) — for a remote model the
same read leaves the machine and cannot be recalled. Why these exist, and what
they do not cover: [[boundaries]].

- **no-write** · asks, does not refuse — `~/06_SYSTEM/config/practice/conventions`
  `convention` is a DIRECTIVE kind (config/knowledge/entities.yaml): these are the user's own files, and an agent proposes a change to them, never makes one. Derived from the register, so it is the user's to move or to stop marking directive.
  → say what you would change and let the user make the edit, or file it as a proposal
- **no-write** · asks, does not refuse — `~/06_SYSTEM/config/practice/user`
  `identity` is a DIRECTIVE kind (config/knowledge/entities.yaml): these are the user's own files, and an agent proposes a change to them, never makes one. Derived from the register, so it is the user's to move or to stop marking directive.
  → say what you would change and let the user make the edit, or file it as a proposal
- **no-write** · asks, does not refuse — `~/06_SYSTEM/config/boundaries`
  `ward` is a DIRECTIVE kind (config/knowledge/entities.yaml): these are the user's own files, and an agent proposes a change to them, never makes one. Derived from the register, so it is the user's to move or to stop marking directive.
  → say what you would change and let the user make the edit, or file it as a proposal

A boundary in your way is a conversation with the user, not a puzzle to route
around. Ask.
