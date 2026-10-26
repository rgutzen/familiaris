---
title: Delegation and permission asks — the trigger, the logs, the chain link
summary: When pi suggests delegating, what delegations and permission decisions log, which asks a link answers
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-15
verified_log: [2026-10-15]
use_count: 2
last_used: 2026-10-19
promoted_from: []
source: 06_SYSTEM/dev/orchestration/SPECS.md
supersedes:
related: [the-loom, orchestrators, boundaries, pi, agent-profiles, phone-relay]
tags: [delegation, pi-agent, trigger, permissions, authorizer, rtk, logs]
triggers: [delegation hint, explore trigger, delegations.jsonl, permission-decisions.jsonl, asks --review, authorizerChain, familiar-delegations, requires approval, rtk git push]
scope: ["06_SYSTEM/engine/orchestration/**", "06_SYSTEM/engine/boundaries/**", "~/.pi/agent/extensions/**"]
area: [B]
stability: evolving
---

# Delegation and permission asks — the trigger, the logs, the chain link

**Three pi extensions and two logs, so that delegation is suggested by a
count, measured by a log, and never stopped by an ask it did not deserve.**
Each extension's source is in `06_SYSTEM`. The dotfiles hold a loader shim per
extension, symlinked from `~/.pi/agent/extensions/`.

| extension | source | does | on |
|---|---|---|---|
| `familiar-trigger` | `engine/orchestration/trigger/pi-trigger/` | ≥ 6 files read **and** ≥ 80 KB of tool output in one user turn → one hint naming `explore` | parent sessions |
| `familiar-decisions` | `engine/boundaries/pi-emitter/` | one line per permission decision → `permission-decisions.jsonl` | everywhere, children included |
| `familiar-asks` | `engine/orchestration/pi-asks/` | registers the chain link `familiar-delegations` | everywhere; it acts only because `authorizerChain` names it |

## The trigger (5b)

The count includes `cat`/`sed`/`head`/`tail` inside `bash`, as the 2026-10-12
replay did. The four read tools alone would fire on 1.9% of turns: this machine
reads through bash.

- **Replay rate:** 28.7% of 108 turns, against a recorded 27% (84% precision).
  `familiar orchestration trigger --replay 30` re-measures it and prints the
  four-tools-only rate beside it. `--since YYYY-MM-DD` counts only the logs dated
  in a window: that is how 5d's floor reads the fires since the trigger went
  live, since the plain newest-N scan would also count the calibration session.
- **Changing a threshold starts a new population.** It is a re-calibration, so
  it is replayed and recorded, never tuned.

## The delegation log (5c)

`pi-agent` writes one line per child to `<PAZRAS_DATA_DIR>/delegations.jsonl`:

- role, the model that ran, profile, effort, exit;
- the pools, `bytes_read`, `bytes_returned`, `compression`;
- `used`, null when written.

It keeps every child's session log, and prints `pi-agent: delegation role=<r>
session=<path>` to stderr. The parent's transcript keeps that line, which is
the join key: `familiar orchestration delegations --replay N` recomputes each
line from the child logs and judges `used`. At session end the pi-trigger hook
runs `delegations --write --parent <session>`; a session pi never wrote a log
for (nothing was sent — pi creates the file lazily) is skipped quietly, while
an explicit `--parent` that names no file stays an error, because there it is
a typo and not an empty session.

**`used` is a heuristic with a stated floor.** A returned path, URL, or 24+
character quote must reappear later in the parent's tool calls or messages. A
result relied on silently counts as unused. 5d's floors read this log: uptake ≥
50%, median compression ≥ 5×.

## The decision log, and what actually asks (8e)

`familiar orchestration asks --replay N` counts from the decision log first,
and falls back to a transcript scan for older sessions. `asks --review` reads
the permission package's own review log instead, which goes back to its install:

- **715 asks** from 2026-09-05 to 2026-10-15, 690 of them answered by the user;
- **667 class B**: the package's own shape floors (`<indirection-bash-wrapper>`
  488, `<unparsed-bash-subtree>` 100, `<opaque-bash-wrapper>` 79);
- **48 class A**: rules the user wrote, such as `git push *`.

A rule in angle brackets is the package's, not the user's.

## The chain link `familiar-delegations` (8d)

**A delegation asks only because of its wrapper.** `"*": "allow"` covers
`pi-agent` and `bindings run`, and `bound_*` / `/bound-*` never meet the bash
gate. A wrapper such as `env X=1 pi-agent …` or `cd … && …; echo` is floored to
`ask` over any `allow`, so a declared allow rule cannot help. The link reads
the unit the package unwrapped, and **allows only** when:

1. the surface is `bash`, and
2. the ask came from `<indirection-bash-wrapper>` or `<unparsed-bash-subtree>`
   (never an opaque `bash -c`, never a user rule), and
3. every statement is a delegation or an inert companion (`cd`, `echo`, `wait`,
   `true`, or a pipe into `tail`/`head`/`wc`/`grep`), and
4. there is no `$(…)`, backtick or process substitution.

Everything else defers to the user. Each grant is written to the review log as
`familiar_delegations.allow` with its reason. The link has authority only
because `config/boundaries/read-write.yaml` lists it under
`authorizer_chain:`. The package also downgrades any link's `allow` on a path
surface to `defer`.

- **Verified live (headless):** `env PI_PROFILE=private pi-agent explore …` →
  `authorizer_allowed`; `git push …` → deferred, then denied with no UI.
- **Deferred, with the rules already written (the user, 2026-10-16):** a Jev
  link judging the *residue* — the class-B asks that are not delegations
  (`env FOO=1 pytest` and the like). It waits for evidence that a model beats a
  plain rule there. Any such link is bounded by four rules: it may narrow and
  never widen; it judges class B only; it may grant only what is reversible and
  outside the sensitive paths; and every judgement is logged.

## rtk rewrites before the gate

The `rtk` extension turns `git push x` into `rtk git push x` **before** the
permission gate runs. It does the same to `git commit --amend`, but not to
rebase or filter-branch/-repo. A prefix rule `git push *` therefore missed the
rewritten form and fell through to `allow`.

Since 2026-10-15 the boundaries compiler emits an `rtk ` twin of every
push/rewrite pattern for pi. Claude Code's guard matches anywhere in the
command and was never affected. **Any new pi bash rule must match the
rewritten form too**: `rtk rewrite "<cmd>"` shows it.
