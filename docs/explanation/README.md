# Explanation — why it is built this way

Explanation is read away from the work. A reader arrives with a question about
the reasoning, not a task, so these pages may take their time; the steps they
would follow live in [`../how-to/`](../how-to/README.md) and the lookup tables in
[`../reference/`](../reference/README.md).

| Page | Answers |
|---|---|
| [`architecture.md`](architecture.md) | where a thing goes, which copy is authoritative, and what leaves a tier — the three relations no register holds, drawn and declaration-checked |
| [`lineage.md`](lineage.md) | where each borrowed idea came from, and where the analogy stops holding |
| [`intention.md`](intention.md) | what the whole thing is for, in the words of the person it is for |
| [`lore/`](lore/) | one page per subject: the mythic name, the mechanism it names, the design choice behind it, and the limit of the analogy |

| Subject | Name | The mechanism it names |
|---|---|---|
| `backup` | [the Larder](lore/backup.md) | stores laid by against a lean season, and the restore path |
| `boundaries` | [the Wards](lore/boundaries.md) | what may not be entered or taken out, and what is only chalk |
| `checks` | [the Threshold](lore/checks.md) | the gates, the tests, and the healthcheck |
| `consolidation` | [the Vigil](lore/consolidation.md) | the nightly pass over the record |
| `context` | [the Clew](lore/context.md) | what a session carries in and out |
| `harness` | [the Guises](lore/harness.md) | the forms a familiar takes: one tree, five names, four of them entry points |
| `host` | [the Hearth](lore/host.md) | this machine and its OS, and not the tools on it |
| `knowledge` | [the Grimoire](lore/knowledge.md) | the written record, one fact per leaf |
| `orchestration` | [the Loom](lore/orchestration.md) | who does the work, under one weaver |
| `practice` | [the Craft](lore/practice.md) | conventions, and the person they are for |
| `publication` | [the Sign](lore/publication.md) | what is shown outward, classified path by path |
| `schedule` | [the Almanac](lore/schedule.md) | what is done when, without anyone deciding it |
| `skills` | [the Apothecary](lore/skills.md) | labelled drawers, fetched on demand |
| `structure` | [the Bones](lore/structure.md) | the folder layout and how a file is named |

The fourteen are the register's subjects, and the ids are the folder names their
leaves live under — so this table is also the map from a name to a directory.

## The two rules these pages obey

**Every analogy names where it stops.** A metaphor is a model, and a model with
an unstated boundary teaches a false one — the limit is the sentence that tells
a reader when to stop reaching for the image. The mythic names claim no
tradition: the register is mnemonic (user, 2026-10-14), so a lore page says what
a name is *for* and never what it descends from.

**A claim carries a citation or a label.** A source that resolves is cited;
anything reaching beyond its source says so, and
[`lineage.md`](lineage.md) is where those labels are defined and applied. A page
that needs one links the row rather than repeating it.

## Status

All three kinds are written: the lineage register, the Intention, and fourteen
lore pages — one per subject id in
[`../../config/knowledge/subjects.yaml`](../../config/knowledge/subjects.yaml),
named for the id, which is also the folder its leaves live under.

**Still open.** Two of the fourteen describe a subject with no leaf in this tree:
[the Loom](lore/orchestration.md) is declared and its mechanism is not built, and
[the Larder](lore/backup.md) is recorded as degraded. Neither page improves on
that — a page that did would be the one thing this folder must not contain.
