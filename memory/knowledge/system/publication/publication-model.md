---
title: Publication model — one private tree, one generated public repository
summary: What is public, what stays private and by which mechanism; the republish loop; the push guard and leak gate
origin: authored
authority: agent
trust: trial
last_verified: 2026-10-26
use_count: 1
last_used: 2026-10-20
promoted_from:
source: the publication track (Track P, retired at P6; in git history)
supersedes:
related: [glossary, memory-poisoning-posture, boundaries]
tags: [publication, publish, republish, export, leak-scan, push-guard, familiaris]
scope: ["06_SYSTEM/**"]
area: [B]
stability: stable
verified_log: [2026-10-21, 2026-10-20]
---

# Publication model

**The private tree is the ground truth; the public repository is its generated
output.** Every file is edited and committed in the private tree. The public
repository `<handle>/familiaris` receives one generated commit per publish, and
nothing is edited only in public. First published 2026-10-19.

## The split: three categories, three mechanisms

| Category | Example | Mechanism | Failure if the wrong mechanism is used |
|---|---|---|---|
| secret | a backup passphrase, a token | deny-list: `.gitignore` and the boundary rules | irreversible disclosure |
| personal | the journal, `config/practice/user/**`, `dev/**` | omitted from the export; no redacted form exists | disclosure the user did not choose |
| instance | Areas, disks, provider accounts | the profile plus `*.example.*` files written in their place | harmless, but the artifact reads as a diary |

Redaction is not a fourth mechanism. A redacted journal is still a journal, and
omission is cheaper and honest.

## The pipeline, and the order of its gates

1. **Classification** (`publish.yaml`): every tracked path is `public`, `omit`
   or `example`. It is an allow-list, and `publish-audit` fails on an
   unclassified path, because a deny-list fails open on the file nobody thought of.
2. **Export** (`engine/publication/publish.py --to <clone>`): rebuilds the tree
   in a scratch stage, runs the stage's own `export` gate, and only then writes
   into the clone. A red export gate means nothing is written.
3. **Scan** (`publish_scan.py`): an independent second gate for residue. Every
   hit is either fixed or declared with its observed count in
   `leak-exceptions.txt`. Raising a count to silence a new hit defeats the register.
4. **Review and push**: a human reads the diff in the clone, commits once and
   pushes. No step publishes automatically.
5. **Record** (`publish_drift.py --record familiaris --commit <sha>`): stamps the
   hash of the private sources. From then on `publish_drift` reports drift at
   `healthcheck`, never at `pre-commit`, because between two publishes drift is
   the expected state.

## At the push: guard and gate

- **Push guard** (`engine/checks/push_guard.py`, wired by `engine/checks/pre-push`)
  refuses a push to `<handle>/familiaris` from any checkout that has `dev/`.
  The publish clone has no `dev/`, so its push is allowed. The rule is a pair
  (destination, tree), because the repository name alone changed meaning at the
  2026-10-14 rename: the private repository took the suffix, and the bare name
  became the public one.
- **Leak gate** (`leak_gate.py`) scans the refs being pushed to any public
  destination. It is advisory unless the checkout sets
  `git config pazras.leak-gate strict`.
- **The hook is shared** through `$GIT_COMMON_DIR`, so every worktree runs the
  main checkout's copy. The body resolves the tree being pushed and runs that
  tree's rules. Where a tree predates the rules, the hook applies the guard's
  coarse form (any owner, the name `familiaris`, a tree with `dev/`) and lets the
  advisory gate's absence pass with a note (fixed 2026-10-19; before that, the
  missing script under `set -e` refused every push from such a branch).
- **Arming**: a symlink `../../engine/checks/pre-push` where the main checkout
  carries the file, a copy otherwise. `push_guard.py --check` names the right one
  and fails a copy that has drifted from the committed body.

## Republishing

**The procedure is `docs/how-to/publish-the-tree.md`**: the one-time setup,
each publish, and what to do when a gate fails. `publish_drift.py` prints the
commands with this instance's clone path when it reports DRIFT. The path is
`clone` in `config/publication/export-state.json`.

A branch that adds code reading `dev/**` or instance config must make its tests
and checks pass in the export. Otherwise the export gate stays red and
`publish.py` refuses to write. The pattern is `instance_only` on a check, or
`roots.instance_here()` on one assertion. Measured 2026-10-19: merging the
orchestration track made the export gate red on six checks for this reason.
Measured again 2026-10-26: the 163 commits after the first publish made it red
on eight, about 70 tests, among them a real portability bug (the tier checks read
the master config without the `.example.sh` fallback the bash loader has) and
two hand-written files under the omitted `config/schedule/`.

Two floors under the classification (2026-10-26). Nothing under `dev/`
travels, whatever `publish.yaml` says: `publish.py` refuses it
(`NEVER_PUBLIC`), because one longer `overrides:` entry would otherwise beat
the `dev/` rule. A venture is never named in the export: the pattern register
refuses it, and a `rename:` rule ships the billing profile named after it as
`work` in every exported file, so the engine and its tests still agree.

`publish.py` copies working-tree bytes, not a commit. Run it from a clean
worktree at the commit being published whenever the main checkout holds
uncommitted work, or that work travels.

## Decisions that bind

- **BSL 1.1 with a personal-use grant, each version converting to AGPL-3.0
  four years after its publication**, with commercial and field-exclusive
  licences beside it (`dec-74619058`, 2026-10-26). It replaced AGPL-3.0 plus a commercial
  licence (`dec-78916300`, 2026-10-19), which could not make a field-exclusive
  licence enforceable: under the AGPL anyone may build on familiaris by
  publishing their fork. The releases up to 2026-10-20 stay AGPL-3.0, because
  a licence already granted cannot be withdrawn. `LICENSE` holds the BSL with
  its parameters, `NOTICE` the terms in plain words, and the contributor
  agreement in `CONTRIBUTING.md` (v1.1) the rights that make all three
  licences possible.
- One public repository, the whole system, umbrella first (`dec-73517266`).
- Private canonical, publish into a clone (`dec-66370526`).
- One generated commit per publish; no personal history travels.
- Knowledge leaves keep the first person where they are a case study and
  template only the addresses (Q9).
- The mythic names are mnemonics and claim no tradition (`dec-53679064`).
- Per-subject repositories only when a subsystem has an outside user, then by
  `git subtree split`.

## Honest limits

The scanner finds the shapes and names it was given. A personal fact phrased in
words it has no pattern for travels, and only the human review catches it. The
model is verified for one machine and one forge account; a second machine
sharing the private repository is an open storage question.
