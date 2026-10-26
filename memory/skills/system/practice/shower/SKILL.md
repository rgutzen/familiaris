---
title: Cold read
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-20
use_count: 0
last_used:
promoted_from: []
source: https://github.com/lilmgenius/paperthin — skills/depth/shower/SKILL.md
supersedes:
related: [prism]
tags: [paperthin, verification, clarity, handoff]
area: [B]
name: shower
description: "Cold-read an artifact from a fresh, zero-context child to test whether it stands alone — a clean-room comprehension check. Hands over the contents, never the intent; it diagnoses, it does not fix."
invocation: model
triggers: [cold read, fresh eyes, fresh read, does this stand alone, zero-context read, comprehension check, will a stranger follow, read it blind, stand-alone check]
antitriggers: [code review, review the diff, proofread, spell check, data leakage, fact check, handoff]
scope: []
platforms: []
requires_tools: []
mode: link
upstream_path: ~/04_RESOURCES/Software/paperthin/skills/depth/shower
upstream_pin: lilmgenius/paperthin@7d5dc62
license: MIT (© 2026 LilMGenius) — LICENSE in the clone
verified_log: [2026-10-20]
---

# Cold read

**Adoption record — mode `link`.** The body lives upstream and is not copied
here. This file holds only our adaptation: routing surface, trust tier, usage
history and local notes.

- **Body:** `~/04_RESOURCES/Software/paperthin/skills/depth/shower/SKILL.md`
- **Pinned:** `lilmgenius/paperthin@7d5dc62`, tag `v0.17.7`. Refresh with
  `git -C ~/04_RESOURCES/Software/paperthin fetch`, check out the new commit,
  re-read the body, then re-run `familiar skills index`.
- **Licence:** MIT (© 2026 LilMGenius) — LICENSE in the clone.

## Reachability

Model- or human-reachable; routed by the terms in `triggers:` above.

## When NOT to use this

- **Hunting defects in a change** — `code-review` (repo standards and the
  originating spec, on a diff). A cold read asks whether the artifact *reads*,
  not whether it is correct.
- **Proofreading.** A blind reader reports what it had to assume; it does not
  find typos.
- **Checking a claim** — `factchk`.
- **The artifact is the conversation itself.** There is nothing to hand over.

## Local notes

- **The fresh sub-session, on this machine.** A child that inherits this
  session's context is not fresh, so spawn one: `pi -p -nc --model <id>` (no
  project context files, no inherited prompt) or `pi-agent` for a defined role.
  Never self-assess in the session that wrote the artifact — that is the whole
  point, and it is also why this cannot be reasoned around.
- **Hand over contents, never a path.** A path lets the child open the README,
  the neighbours and the history, which spoils the read. Inline the text or
  copy it to a scratch file with nothing else around it and say so.
- **Note the intent privately, first.** One line: what the artifact is for and
  who reads it. The comparison in step 4 has no yardstick without it, and the
  child must never see it.
- **A cheap child is usually enough, and a single draw is a single draw.** For
  an artifact that ships to someone else, two independent reads cost little
  more than one and catch the case where the first reader is confidently wrong.
- **Read, don't sweep.** Never report "clean" from a grep — a cold read is an
  end-to-end read by definition.

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*
