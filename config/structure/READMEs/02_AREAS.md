# P.A.Z.R.A.S Areas Guide

> **Purpose**: Ongoing responsibilities — standards to maintain, not outcomes to finish
> **Location**: `~/02_AREAS/`
> **Review**: Weekly — is each area getting the attention it needs?

## What belongs here

**Ask**: *"What standard am I trying to maintain?"* — not "what am I trying
to finish?" An area has no end date. If it does, it's a project (see
`01_PROJECTS`), and it should live inside the relevant area's project list,
not be confused with the area itself.

Areas are **not exclusive boxes** — they're distinct environments suited to
each domain of interest. The same topic can show up in an area (active
work) and in the Zettelkasten (developed understanding) without conflict;
cross-references and tags are what connect them, not folder placement.

## The 17 areas (source of truth: `config/profile.yaml`)

| Code | Area | Domain |
|---|---|---|
| A | Science | Science and computational modeling |
| B | Tech | Technology, programming, digital tools |
| C | Writing | Writing, communication, publishing |
| D | Art | Visual arts and creative expression |
| E | Connection | Personal relationships |
| F | Community | Community building, social engagement |
| G | Embodiment | Physical movement, dance |
| H | Health | Health management, medical, wellness |
| I | Mindfulness | Meditation, awareness, mental training |
| J | Culture | Spirituality, culture, consciousness |
| K | Cuisine | Cooking, fermenting, foraging |
| L | Career | Job applications, CV, career docs |
| M | Academia | Reviews, funding, interviews, academic service |
| N | Finance | Personal finance management |
| O | Travel | Travel planning and experiences |
| P | Home | Housing and living-space management |
| Q | Ventures | Founding, building and running ventures |

Not every area has a folder yet — one is created on demand via
`familiar structure init` once there's something to put in it. An empty area in
the config isn't a problem; a folder full of one file nobody's touched in a
year is the thing worth noticing.

## Adding or changing an area

Edit the `AREAS` array in `config/structure/pazras-master-config.sh`, then run
`familiar structure init`. Don't create area folders by hand — the config is the
single source of truth, and scripts key off the letter code.

## Areas vs Projects vs Zettelkasten vs Resources

```
Ask: "Am I responsible for maintaining this?"
├─ YES → 02_AREAS (this directory)
└─ NO  → Ask: "Does it have a deadline and a defined outcome?"
    ├─ YES → 01_PROJECTS
    └─ NO  → Ask: "Am I developing understanding, or just referencing it?"
        ├─ Developing → 03_ZETTEL
        └─ Referencing → 04_RESOURCES
```
