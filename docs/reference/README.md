# Reference — where to look a thing up

Links, not copies. Every table named below already exists in the file it came
from, and a copy is a second thing to keep true: the lookup a reader wants is
one click away, while a restatement drifts the day either side changes.

| Read | For |
|---|---|
| [`../../README.md`](../../README.md) | what runs on a fresh clone, and what is read-only without an install |
| [`../../STRUCTURE.md`](../../STRUCTURE.md) | the PARA tree, its Areas and its filing rules — generated from the example profile |
| [`../../STORAGE-MODEL.md`](../../STORAGE-MODEL.md) | authority, tiers, backup repositories, flows, and the storage rules that follow from them |
| [`../../engine/README.md`](../../engine/README.md) | the engine's directories, one line each |
| [`../../memory/knowledge/INDEX.md`](../../memory/knowledge/INDEX.md) | every knowledge leaf that ships, one line each, with its trigger terms |
| [`../../memory/knowledge/system/publication/glossary.md`](../../memory/knowledge/system/publication/glossary.md) | the subject ids, their mythic names, their criteria, and the places each occupies — generated from the register |
| [`../assets/route-cost-chart.png`](../assets/route-cost-chart.png) | worst-case tokens to answer one routing question; [`../assets/route-cost-chart.py`](../assets/route-cost-chart.py) draws it |
| [`maps.md`](maps.md) | five figures the registers generate — the package order, the subjects and their places, the boundaries and their targets, the schedule, the pass's stages — beside the three that have no register and are hand-written in [`../explanation/architecture.md`](../explanation/architecture.md) |

The last row is the one exception to the list's rule, and it is a measurement
rather than a document: the PNG is an output of the script beside it, the
numbers live in the script, and the image carries no table to duplicate.

## Missing here, and why

`DATA-ARCHITECTURE.md` and `memory/README.md` are this
machine's own writing: the publication classification omits them, so a reader of
this tree cannot open them and a link to one would dangle. `STORAGE-MODEL.md` is
the published half of `DATA-ARCHITECTURE.md`.

`VISUAL-ARCHITECTURE.md` is gone rather than missing: it was hand-drawn Mermaid
that restated its sources and named this machine's disks, and P4b replaced it
with the figures above — generated where a register holds the relation,
declaration-checked where it does not.

**Honest limits.** These files are of two kinds, and the difference matters when
one is quoted. The generated ones (`STRUCTURE.md`'s tables, the glossary, the
index) are written by the engine and go stale the moment a register changes
without a rebuild; the rest are hand-written and versioned. A number quoted in a
conversation should be read from the file, never from a memory of this page.

**Still open.** `context links --check` resolves the pointers inside the vault,
not these: the paths above are outside it, so a rename that breaks one is caught
by review rather than by a gate.
