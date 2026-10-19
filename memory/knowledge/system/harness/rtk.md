---
title: rtk
summary: The `rtk` output filter — what it wraps, and the traps it sets for agents
origin: authored
authority: agent
trust: trial
last_verified: 2026-09-30
use_count: 2
last_used: 2026-10-11
promoted_from: []
source: https://github.com/rtk-dev/rtk
supersedes:
related: [pi, claude-code, opencode, memory-mechanisms]
tags: [rtk, tokens, output-filter, git, harness]
scope: []
area: [B]
stability: evolving
verified_log: [2026-09-30]
---

# rtk

`rtk` (Rust Token Killer, v0.48.0) is an **output filter**, not a command
runner: it prefixes a wrapped subcommand, runs the real one, and compresses what
comes back. It is installed as a standalone binary and reached from every
harness here — plain in a shell, and through a rewrite extension or hook in
`pi` and `claude-code` ([[memory-mechanisms]] names `rtk hook claude` in
Claude Code's `PreToolUse` chain).

`rtk -h` is the authority on what is wrapped. The command families are
`ls tree read smart` (files), `git gh glab` (VCS), `grep rg find diff` (search
and diffs), `test err log` (failure-only filtering), `docker kubectl oc aws
psql pnpm dotnet` (infrastructure), and `json deps env summary`.

## What an agent must know

- **A wrapped command's exit code may not be the real one.** `checks.py --run
  <gate>` is the standing example: the gate's own exit status is what matters,
  and the compact render is a summary. Capture the status explicitly —
  `cmd; echo "exit: $?"` — rather than inferring it from what rtk printed.
  Confirmed the hard way on 2026-09-30: a `checks.py` invocation printed its
  full FAILED output, and the status was read from the *next* command in the
  chain instead of from the check.
- **Only the wrapped subcommand is filtered.** `rtk git commit -m …` runs real
  `git commit`; the message, the author and the parent commit are unaffected.
  **`rtk git commit -F -`, multi `-m`, and heredocs all work** — verified
  2026-09-30 in a scratch repo, each form landing its message intact. A commit
  that appears not to have happened is far more likely to be a concurrent
  process, a hook refusal, or an aborted `&&` chain than an rtk defect.
- **Format flags are not filtered.** `grep`/`rg` with `-c -l -L -o -Z` run raw,
  because the compact renderer would destroy the counts. Expect full output
  there, not a summary.
- **Do not parse rtk's output.** It is a presentation layer tuned for
  legibility and is free to change with the tool's version. Take the number from
  the underlying command, or from a machine-readable artifact.

## Two files are shared, and neither belongs to this leaf

- `~/.pi/agent/AGENTS.md` carries the standing "prefer rtk for bulk readout"
  note; the rewrite extension that actually swaps a command for its rtk form is
  a Pi extension beside `familiar-guard`.
- A trap that reaches *skill* authors rather than agents: `rtk` recognises no
  rtk-specific syntax, so a skill's example command must be written the plain
  way and left for the rewrite layer. Shipping `rtk`-prefixed commands inside a
  skill hard-codes a wrapper the reader may not have.

## Verification

```bash
rtk --version                       # expect: rtk 0.48.0 or later
rtk -h                              # the wrapped command list
rtk git status                      # compact status
rtk git log --oneline -1            # message unaffected by the filter
```

Per-command behaviour is `rtk <cmd> -h`. The trap this leaf exists for —
a wrapped command whose real exit code matters — is checked by running the
unwraped command and comparing, which is the only assertion that stays true
across rtk versions.
