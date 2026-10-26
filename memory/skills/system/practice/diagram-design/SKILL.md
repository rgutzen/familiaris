---
title: Diagram design
origin: imported
authority: agent
trust: trial
last_verified: 2026-10-23
use_count: 22
last_used: 2026-10-24
promoted_from: []           # adopted 2026-10-23; see journal entry for that date
source: https://github.com/cathrynlavery/diagram-design — skills/diagram-design
supersedes:
related: []
tags: [diagrams, visualization, svg, architecture, editorial]
area: [B]
name: diagram-design
description: Draw an editorial, brand-skinned diagram as one HTML+SVG file for a doc, brief or slide; export SVG or PNG.
invocation: model
triggers: [architecture diagram, draw a diagram, redraw this diagram, flowchart for a doc, sequence diagram, swimlane, state machine diagram, diagram for a brief, investor diagram, customer-facing diagram, import mermaid, export diagram to png, diagram-design]
antitriggers: [terminal diagram, chat diagram, termaid, ascii chart, asciichartpy, plot data, matplotlib, notebook figure, quick sketch]
scope: []
platforms: []
requires_tools: [python3]
mode: link
upstream_path: ~/04_RESOURCES/Software/diagram-design/skills/diagram-design
upstream_pin: cathrynlavery/diagram-design@7a12007 (v2.6.119)
license: MIT (Cathryn Lavery / LittleMight) — LICENSE in the clone
verified_log: [2026-10-23]
---

# Diagram design

**Adoption record — mode `link`.** The body lives upstream and is not copied here.
This file holds only our adaptation: routing surface, trust tier, usage history
and local notes.

- **Body:** `~/04_RESOURCES/Software/diagram-design/skills/diagram-design/SKILL.md`
- **Pinned:** `cathrynlavery/diagram-design@7a12007` · refresh with
  `git -C ~/04_RESOURCES/Software/diagram-design pull`, re-run the stage-02 read on the
  diff of `skills/` and `scripts/`, then `familiar skills index`
- **Licence:** MIT (Cathryn Lavery, LittleMight)

## When to use this

A diagram that a person outside this session will read: a doc, a brief, a pitch, a
review, a slide. The skill picks one of 45 types, lays it out by hand on a 4px grid,
and verifies the geometry.

## When NOT to use this

- **A reply in the terminal.** The output is an HTML file; chat stays `termaid`.
- **A chart computed from data.** The skill hand-places every mark, so a value can be
  drawn wrong without any check noticing. Plot data with `matplotlib`; borrow only the
  skin.
- **A diagram that changes with every commit.** Re-laying out by hand on each change
  costs more than Mermaid's diff does; keep those in Mermaid.

## Knowledge this cites

- `[[omarchy-host-traps]]` — why PNG export on this machine needs a clean fontconfig

## Reachability

Model- or human-reachable. Routed by the terms in `triggers:` above.

## Local notes

- **Stage-02 review, 2026-10-23.** Read `SKILL.md` and every reference the routing
  touches; grepped all six packaged scripts. Findings: no instruction acts outside
  diagram work, no exfiltration, no safeguard bypass. Network use is limited to
  (1) Google Fonts in generated files when the skin's font source is `web`,
  (2) a website the user names for brand onboarding, (3) Playwright's Chromium for
  PNG export. The scripts are standard library only, except `export_png.py`, which
  needs Playwright.
- **No remote fonts, anywhere on this machine (user, 2026-10-23).** Upstream defaults to
  `Font source: web`, which puts a Google Fonts `<link>` in every diagram and an `@import`
  in every SVG export; its templates carry the link too. Always generate as
  `Font source: system`: strip the link from any copied template, export SVG with
  `--system-fonts`, and pass `self_check.py --offline` before handing a file over. Never
  embed a font as `data:` either. Reason: a remote font leaks the reader's IP address to a
  third party, and font files are parsed by FreeType and the browser, whose font parsers
  have had exploited memory-corruption bugs.
- **One local patch in the clone (user, 2026-10-23):** `references/style-guide.md` line
  `Font source: \`system\`` instead of upstream's `web`. It makes the skill omit font links
  everywhere, also where no project marker exists. The skill now treats the working copy as
  customised, so outside a marked project it skips the first-run skin question and offers to
  save a profile; decline. On `git pull`: `git stash`, pull, `git stash pop`, and re-check
  `grep '^Font source' references/style-guide.md`.
- **Otherwise never edit the clone's `references/style-guide.md`.** Onboarding writes there by
  default, which forks the linked body. Skins live as named profiles in
  `~/.diagram-design/profiles/<slug>.md`, selected per project by a one-line
  `.diagram-design` marker (`profile: <slug>`).
- **Checks outside the installed skill.** `scripts/verify-geometry.py` and
  `scripts/verify-contrast.py` sit at the repository root of the clone, not under
  `skills/`. Run them as `python3 -I ~/04_RESOURCES/Software/diagram-design/scripts/<name>.py`.
- **PNG export:** `uv run --no-project --with playwright python -I <skill>/scripts/export_png.py <in.html> <out.png> 2`.
  It needs `chromium-headless-shell` for the current Playwright, installed with
  `uv run --no-project --with playwright playwright install chromium-headless-shell`.
- **Mono fonts on this machine:** a user fontconfig rule makes Chromium draw Geist Mono
  as Nimbus Mono PS; see `[[omarchy-host-traps]]` §Fonts in headless Chromium.
- **A project may ship its own export wrapper** that runs the checks, then the SVG and
  PNG export, with the font workaround built in. Prefer it where it exists.
- **Data charts stay out.** The skill hand-places every mark. Route a chart computed
  from numbers to matplotlib with the project's style; keep this skill for concepts.
- **Mermaid theming, when a project keeps Mermaid beside this skill:** `mermaid-cli` 11
  ignored a `fontFamily` theme variable of `'Geist, sans-serif'` and honoured
  `'Geist, Helvetica Neue, Arial'` (tested 2026-10-23).

*(usage outcomes go here as `use_count` accrues — this is `trust: trial`)*

## Use history

- **2026-10-24, the figures pass (22 figures).** The whole docs tree redrawn in
  one day: 20 authored figures + the maps theme + 2 matplotlib charts re-skinned.
  The gate (`self_check --offline`, geometry, contrast, system-fonts SVG) caught
  the one figure that named instance facts (`backup-installed`) — omitted with
  its doc, which is the check working as intended. Delegation notes: hand-placed
  SVG draws well on deepseek-flash (6 figures, 2 after retry) and zai-glm-5-3-flash
  / mistral-small-2603 (10, 2 mid-run deaths retried); qwen3-30b local failed at
  the reading step. `dev/figures/run.sh` (headless Sonnet) and `runpi.sh`
  (pi fallback) are the reusable runners; `dev/figures/check.sh` the gate.
