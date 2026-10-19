# the Wards — what may not be entered or taken out

| | |
|---|---|
| subject | `boundaries` |
| falsified when | a rule, the guard or the compile changes |
| occupies | `engine/boundaries`, `config/boundaries` |

**The name.** A ward is a mark set at a threshold to keep something out or in —
which is also why the register names the *unenforced* rules differently. The
vocabulary here is doing real work: a **ward** is a rule something checks, and
**chalk** is a level-4 rule that a mark anyone can step over describes honestly.

## The mechanism

Rules are written in `config/boundaries`, compiled to a single
`boundaries.json`, and enforced where the work actually passes: the harness
entry points. The compile step is what makes them testable without a harness in
the loop, and the guard is the part a running agent meets.

Which paths may be read, which may be written, and which belong to the user
alone are all rules of this kind. A rule that no mechanism checks is filed as
chalk rather than promoted by wishful reading.

## The design choice, and why

**Enforcement is a property of the rule, and it is stated.** The distinction
between a ward and chalk exists because the failure mode of an advisory rule is
not that it is ignored — it is that a reader treats it as protection. Naming the
level keeps a boundary file from becoming a document of intentions.

**The compile target is one file.** Rules edited in several places, each read by
a different consumer, drift; one compiled artifact means the guard and the tests
read the same bytes.

**Human-owned by construction.** The rules are directive: they are read by
agents and changed by the user. A boundary an agent can edit is not a boundary,
whatever it says.

## Lineage

**No source claimed.** The mechanism is the ordinary one — a policy compiled and
enforced at a choke point — and the register's contribution is the vocabulary
that keeps the enforced and the advisory apart.

**Where the analogy stops.** A ward is set at a threshold and guards one door; so
does this one. A path that does not pass the harness hook is not guarded, and no
rule here makes a claim about it.

**Leaves.** [`memory/knowledge/system/boundaries/`](../../../memory/knowledge/system/boundaries/)
— why the rules exist, how they compile, and what they miss.
