# The Spellbook — task recipes

A how-to is a recipe. The reader arrives with a task already in mind and wants
the steps, in order, with the failure that the step prevents named beside it. So
the body stays plain: a mythic name appears in a heading at most, because
someone following steps under time pressure pays for every figure of speech.

| Recipe | The task | Run |
|---|---|---|
| [add a boundary](add-a-boundary.md) | write a rule, compile it, and watch the guard refuse the thing it forbids | executed: all four steps, in a scratch `$HOME` |
| [adopt a skill](adopt-a-skill.md) | vet a skill arriving from outside, then route a task to it | executed: the records written, the routers regenerated, the warning for an undeclared subject read |
| [recover from backup](recover-from-backup.md) | bring one file back out of a restic repository | executed end to end against a scratch repository; the instance's own repos are not touched |
| [publish the tree](publish-the-tree.md) | publish a private instance as a generated public repository, and republish it when it drifts | executed: the first publish of this tree, end to end, and the `--check` path on a scratch clone |
| [add a harness](add-a-harness.md) | put a fifth agent behind the always-on compiler and keep the boundary guard | **half executed**: the compiler half, on a patched scratch copy; the audit, hook and transcript steps need the program itself |

**Each recipe was run once as written, or says what stopped it.** Every command
block is the output that came back, with elisions marked in the text beside it.
Three of the first four were run on a scratch clone, because the point of the exercise
is what the commands write — and one of them writes outside the tree.

**Still open.** Five recipes are the start, not the set. A recipe is added when
someone actually needed it — the list of things a task might need is not
evidence that anyone will.

**Found by running them.** Two defects are recorded on the pages themselves
rather than left for a reader to rediscover: `familiar backup run` fails on a
published tree because its default exclude list does not travel
([recover from backup](recover-from-backup.md)), and a quoted `description:`
reaches the skill router with its quotes in it
([adopt a skill](adopt-a-skill.md)).
