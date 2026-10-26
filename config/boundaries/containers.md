# Boundaries — containers

<!-- GENERATED from containers.yaml by engine/boundaries/compile.py. Do not hand-edit. -->

Advisory: nothing here is enforced by the harness *reading* it. Claude Code and
opencode also enforce these at the tool call (`engine/boundaries/guard.py`,
`engine/boundaries/opencode-plugin/`); hermes and anything else rely on you.
`local` means inference on this machine (ollama, local-ollama) — for a remote model the
same read leaves the machine and cannot be recalled. Why these exist, and what
they do not cover: [[boundaries]].

- **no-host-escape** · asks, does not refuse — `/`
  A container given every device, the host's namespaces, a root-equivalent capability, or a bind of the host's files is not isolated from this laptop. One with --privileged killed the desktop session on 2026-10-22.
  → drop the flag; add only the narrow capability the test needs (e.g. --cap-add NET_ADMIN), bind only a project subdirectory, or test in a VM

A boundary in your way is a conversation with the user, not a puzzle to route
around. Ask.
