# Boundaries — Router

<!-- LAYER 3 · DIRECTIVE · Agents propose changes, never make them -->

| Domain | Covers | Source · compiled |
|---|---|---|
| read-write | files agents may not read or write — the user's thinking, personal documents, credentials, backups | `read-write.yaml` · `read-write.md` |
| git | pushing, rewriting history | `git.yaml` · `git.md` |

**Enforced**, unlike `../practice/conventions/`: in Claude Code and opencode a matching
call is stopped at the tool boundary. In hermes and anywhere else these are
advisory and keeping them is your responsibility.

- `*.yaml` is the source; the `.md` beside it is generated — hand-edits are
  overwritten. Adding a rule means editing a `*.yaml` and running
  `../../engine/boundaries/compile.py`; adding a domain means adding a
  file, which the compiler picks up with no code change.
- Why they exist and what they do not cover: [[boundaries]].
