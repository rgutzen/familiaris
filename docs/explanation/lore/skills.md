# the Apothecary — labelled drawers, fetched on demand

| | |
|---|---|
| subject | `skills` |
| falsified when | a skill or its routing changes |
| occupies | `memory/skills` |

**The name.** An apothecary keeps labelled drawers and is asked for one of them.
The register's gloss makes the design claim explicit — *never carried all at
once* — which is why a skill is a thin index entry first and a body of
instructions only when a task asks for it.

## The mechanism

A skill is a directory holding instructions and whatever files they need. Nothing
loads by default. A task reaches one of them through the resolution signals the
routing leaf describes, and the skill then enters the context for that task
alone. Adoption — a skill arriving from outside — is a separate path with its own
test, because the interesting failure is not a skill that does not work but one
that works and came from somewhere.

## The design choice, and why

**Zero-install, and the contrast is with its predecessor.** The alternative
design — install skills into the harness, let the harness advertise their
descriptions in every session — spends the always-on budget on drawers nobody
opened. Routing instead resolves against the task at hand, which is the same
budget discipline as [the Clew](context.md): pay when a pointer is followed.

**Knowledge or a skill is a filing decision, not a taste.** A claim goes in the
knowledge tree; a procedure goes in a skill. The test exists as a leaf because
the two stores answer different questions and a fact filed as a procedure is
unfindable.

**Provenance is part of adoption.** A skill is instructions a model will follow,
so vetting it is the same problem as any other unreviewed input — a supply chain
with a context window at the end of it.

## Lineage

**No source claimed** for the name, and none claimed for zero-install routing.
The prior-art leaf in the consolidation subject reviews memory designs that were
considered and rejected; skill routing was arrived at by measurement of the
always-on budget rather than by descent from a design.

**Where the analogy stops.** An apothecary compounds; this store only holds. A
drawer here is text, the routing is a handful of deterministic signals, and a
skill that is never fetched is dead weight rather than evidence of breadth.

**Leaves.** [`memory/knowledge/system/skills/`](../../../memory/knowledge/system/skills/)
— the routing signals and the adoption test, which is where a new skill is
vetted before it is one.
