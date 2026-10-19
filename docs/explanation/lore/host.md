# the Hearth — this machine and its OS

| | |
|---|---|
| subject | `host` |
| falsified when | **this machine** or its OS changes — and not when a tool installed on it changes, which is [the Guises](harness.md) |
| occupies | `engine/host` |

**The name.** A hearth is the fire a household is kept around — the place
itself, not the tools in it. The register gives no gloss for this name; the
reading here is the page's own, and the boundary it draws is the load-bearing
part: this subject is *the machine*, not the software placed on it.

## The mechanism

A leaf of host-level traps: a VPN client that fails in a specific way, a
Kerberos-flavoured SSH to a compute cluster, theming that does not apply,
packages built rather than fetched. Each is a fact about *this* Arch install,
recorded because the failure is not diagnosable from its symptom and the next
person to meet it is usually the same person a year later.

## The design choice, and why

**The subject exists because its leaf had nowhere to go.** The register records
this plainly: `omarchy-host-traps` had no home until the subject was added, and
the falsification test is what placed it. A trap in the OS is not a harness fact
— updating a harness does not make the trap true or false — and it is not a
structure fact either, since the layout is the same on any machine.

**Traps, not a manual.** A page of things that went wrong on one machine is worth
more than a description of the machine, and it is the form that stays true: the
description would be stale in a release, and a trap's shape — the symptom and its
cause — survives one.

## Lineage

**No source claimed.** The content is first-hand: these are failures met on this
machine, and their authority is that they happened, which is a weaker form of
evidence than a measurement and a stronger one than a recall. Where a leaf
generalises, it says so.

**Where the analogy stops.** A hearth implies a household gathered around one
fire; this is a list of one machine's idiosyncrasies, worthless on a machine that
is not this one. That limit is the reason the subject is `host` and not a section
of a harness page: it keeps the general claims from being contaminated by the
particular ones.

**Leaves — not here.** The traps are recorded in
`memory/knowledge/system/host/`, which is one machine's own notes, and the export
omits them for exactly that reason: they name places and accounts that are
specific to that machine. What travels is the shape above — the symptom, and the
cause that does not follow from it.
