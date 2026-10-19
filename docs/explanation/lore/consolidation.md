# the Vigil — the nightly pass

| | |
|---|---|
| subject | `consolidation` |
| falsified when | the **act of writing** changes: consolidation, ranking, promotion |
| occupies | `engine/consolidation` |

**The name.** A vigil is a watch kept through the night — the hour, in the
register's phrase, when the grimoire writes itself. The word carries the two
properties that matter. It is a *watch*: nobody is doing it, and that is the
point. And it happens at night, which is when subtraction is allowed.

## The mechanism

One pass over the record, on a timer, with no one watching. It reads what
accrued since the last time, ranks it, and decides what to keep, what to merge,
what to let fade. Promotion is the exception rather than the routine: raising a
leaf's trust is a human-gated act, so the pass may improve the *record* but not
the *standing* of a claim.

Ranking is where time enters the system. A compartment carries a half-life — 180
days for recency — so that what has not been reached for in a long time falls in
the order retrieval returns things, without being deleted for it.

## The design choice, and why

**A pass that runs unwatched may write only what its invariants declare.** Each
pass declares the rules it keeps, and those rules are checked the same way a gate
is, which is what makes an unattended writer tolerable at all.

**Weakening is part of the job.** The obvious design is a pass that accumulates —
add, summarize, keep. This one also subtracts, and the reason is the source: the
nightly process in the brain is at least as much downscaling as strengthening,
and a store that only ever grows is one nobody can read.

## Lineage

[Two rows](../lineage.md), and both are models with a boundary. The *weakening*
half has a named source — Tononi & Cirelli's synaptic homeostasis hypothesis. The
*replay* half is uncited: the candidate citation does not resolve, so the row was
dropped rather than written from a plausible memory. The fast/slow pairing is an
**inference from the structure**, not a documented descent.

**Where the analogy stops.** Nothing in this pass is tired. "Sleep" here is the
clock, "replay" is a file read, and the interference avoided is a reader's
attention rather than a weight matrix in a network.

**Leaves.** [`memory/knowledge/system/consolidation/`](../../../memory/knowledge/system/consolidation/)
— the cycle, the mechanisms that enforce it, the ranking, the posture that keeps
an injected claim out, and the prior art this design declined.
