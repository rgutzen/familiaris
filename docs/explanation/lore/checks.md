# the Threshold — the line crossed on entering

| | |
|---|---|
| subject | `checks` |
| falsified when | a gate, a test or the healthcheck changes |
| occupies | `engine/checks` |

**The name.** The threshold is the line crossed on entering a house, and the
register's note that wards are set at thresholds is the reason a gate is one.
Crossing it is not a formality: the gate runs before the commit, and a failure
stops the entry rather than annotating it.

## The mechanism

Three kinds of check, deliberately kept apart. **Gates** run a named set of
checks before an event — `pre-commit`, and a narrower `export` set for the
published tree. **Tests** belong to the code they test. The **healthcheck** looks
at the machine and the tree rather than at a diff: a drifted generated file, a
timer that never fired, a glossary nobody rebuilt.

## The design choice, and why

**A check declares what it means, and the default is to fail.** A check that
cannot run somewhere — because the input is this machine's — says so in code and
is *counted as skipped* on the summary line it appears on. A check that does not
declare that still fails where its subject is missing, which is what keeps the
gate fail-closed. The alternative, a suite that silently measures an empty set,
was found in this tree and is exactly the failure the rule prevents: green over
nothing.

**A rule that matches nothing is a failure too.** The classification audit fails
on a rule no path uses, so a stale exemption cannot outlive its reason.

**This is the register's weakest subject, and it says so.** Its own criteria
record that a gate is arguably a concept spanning the whole repository rather
than a place, and flag it for review rather than keeping it quietly. A weak
category that names itself is worth more than a tidy one that does not.

## Lineage

**No source claimed**; the ordinary lineage is the test suite. The two rules
above are this tree's own, and both came from a measured failure rather than from
a principle — a check that had silently degraded to zero over an empty set is why
the first one exists.

**Where the analogy stops.** A threshold admits and excludes. A gate here
verifies: it says a tree is *sound*, which is not the same as saying the work is
good, and no gate in this tree has an opinion about whether the change should
have been made at all.

**Leaves.** [`memory/knowledge/system/checks/`](../../../memory/knowledge/system/checks/)
— what a `--check` drift report means, and what to do about it.
