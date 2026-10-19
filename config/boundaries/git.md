# Boundaries — git

<!-- GENERATED from git.yaml by engine/boundaries/compile.py. Do not hand-edit. -->

Advisory: nothing here is enforced by the harness *reading* it. Claude Code and
opencode also enforce these at the tool call (`engine/boundaries/guard.py`,
`engine/boundaries/opencode-plugin/`); hermes and anything else rely on you.
`local` means inference on this machine (ollama, local-ollama) — for a remote model the
same read leaves the machine and cannot be recalled. Why these exist, and what
they do not cover: [[boundaries]].

- **no-push** · asks, does not refuse — `~`
  Pushing and rewriting history are the user's call, everywhere, not just in public repos. Committing, branching and worktrees are not.
  → commit and branch freely, then let the user approve the push

A boundary in your way is a conversation with the user, not a puzzle to route
around. Ask.
