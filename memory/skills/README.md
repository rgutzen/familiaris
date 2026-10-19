# Canonical Skills

**This is the single source of truth for user-authored skills across every
harness.**

Skills live here, filed under `system/<subject>/<name>/` — the same three
branches and subjects the knowledge tree uses (`../../config/knowledge/subjects.yaml`,
SPECS.md O6b). They are **not** installed into any harness (zero-install,
2026-08-30). Historical note: they used to be symlinked outward, flattened at
the harness boundary, because harnesses expect `skills/<name>/SKILL.md`:

```
~/.claude/skills/<name>      -> ~/06_SYSTEM/memory/skills/system/<subject>/<name>
~/.codex/skills/<name>       -> ~/06_SYSTEM/memory/skills/system/<subject>/<name>
~/.memory/skills/<name>      -> ~/06_SYSTEM/memory/skills/system/<subject>/<name>
~/.pi/agent/skills/<name>    -> ~/06_SYSTEM/memory/skills/system/<subject>/<name>
```

Flattening is lossless only while skill names are unique across subjects. A
name collision would break silently — the router's `skills index` must guard
against it.

**Hermes is not in the outward-link set.** Its layout is category-nested
(`~/.hermes/skills/<category>/<skill>/SKILL.md`), so flat links do not fit; its
skills are upstream-managed and stay in `~/.hermes/skills/`, referenced not
copied, so they do not go stale.

Never add a skill directly to a harness home — it becomes invisible to the
other three and is lost on machine migration.

## Why this exists

Before Phase 0, skills were scattered across seven agent homes holding
2/2/2/2/14/0/15 entries, and all 14 links in `02_AREAS/B_Tech/skills/` (now
trashed) pointed at `/home/rgutzen/…` — an account that does not exist on this
machine. Every one was dead.

## Adding a skill

1. Create `system/<subject>/<name>/SKILL.md` here. The subject must be one of
   the register's subjects in `../../config/knowledge/subjects.yaml`, chosen by its
   `criteria`; there is no `category:` field — the path is the subject.
2. Run `familiar skills index` to regenerate the routers, `TRIGGERS.md`,
   `USER-INVOKED.md` and every harness command.
3. Commit — this directory is version-controlled and portable.

---

## Routing

With 1161 `SKILL.md` files on this machine (2026-08-29), listing them costs
~38,000 tokens. They are therefore **never injected wholesale**. Selection runs
through a four-tier router:

- `CONTEXT.md` — Tier 0, ~400 tokens, always loaded. Names branches, not
  skills. **Partly generated — edit the prose, never the blocks.**
- `<branch>/CONTEXT.md` — Tier 1, loaded on branch match. Generated.
- `<branch>/<subject>/CONTEXT.md` — Tier 2, loaded on subject match. Generated;
  its prose comes from the `_subject.md` beside the skills.
- `<branch>/<subject>/<skill>/SKILL.md` — Tier 3, loaded on selection.

Full mechanism, resolution order and lifecycle:
[[skill-routing]].
New skills start from `_skill-template.md` — a skill without frontmatter is
invisible to the router and will never be selected.
