# The Initiation — one evening, end to end

A tutorial is a lesson: it takes a reader who has never run this system and
leaves them having run it once, in one sitting. Every command below was executed
on the published tree, in a scratch `$HOME`, and every output is the one that
came back — colours stripped, nothing elided except where a line says so.

The walk is one loop through the system, because the loop is the thing worth
learning: a thought is captured, filed, left alone, and checked.

## What it costs, and what it touches

Nothing outside a scratch directory. Two environment variables move the roots,
and they beat the profile:

```bash
export HOME=/tmp/tut/home                 # what a harness writes to
git clone <repo> /tmp/tut/home/06_SYSTEM  # the tree, as the PARA tree's 06_SYSTEM
cd /tmp/tut/home/06_SYSTEM
```

`HOME` moves both roots, and it beats the profile: the default profile has
`install: ~/06_SYSTEM` and `para_root: ~`, so a scratch `$HOME` puts the install
and the PARA tree inside it and nothing is written outside. The clone is at
`$HOME/06_SYSTEM` — the arrangement this machine runs, and the one the profile
describes — which matters because `$HOME/06_SYSTEM` is both the checked-out tree
and the PARA folder of the same name.

## 1 · The profile, and what it says

```console
$ engine/familiar structure validate
profile: /tmp/tut/home/06_SYSTEM/config/profile.example.yaml -- 5 Areas, install /tmp/tut/home/06_SYSTEM, PARA root /tmp/tut/tree
🔍 Validating P.A.Z.R.A.S configuration...
⚠️  Backup path not in P.A.Z.R.A.S structure: .claude
✅ Configuration validation passed
```

A fresh clone runs on `config/profile.example.yaml`, and the line above is the
whole of P1's idea: the facts that make a tree *this* person's are in one file,
and a clone that never wrote one behaves like the example. The warning is the
validator doing its job — `.claude` is a backup path outside the PARA
structure, which is true and not an error.

## 2 · The tree

```console
$ engine/familiar structure init
📁 Ensuring P.A.Z.R.A.S directory structure exists...
Created: 00_INBOX
Created: 01_PROJECTS
Created: 01_PROJECTS/_templates
Created: 02_AREAS
Created: 02_AREAS/A_Work
Created: 02_AREAS/A_Work/_processes
Created: 02_AREAS/A_Work/_tracking
…
Linked:  06_SYSTEM/dotfiles -> ../02_AREAS/B_Tech/dotfiles
✅ Created 40 directories
📝 Creating area README files...
Created README for: A_Work
…
[ZETTEL] Created daily note template
[ZETTEL] Created permanent note template
[ZETTEL] Created project template
[INIT] P.A.Z.R.A.S structure initialized successfully
```

Forty directories, one symlink, five Area READMEs, three templates (the listing
is elided; the full output is 20 lines longer). Every directory came from the
master config, so the tree and its description cannot disagree — the same config
renders the tables in [`../../STRUCTURE.md`](../../STRUCTURE.md).

The symlink is the one entry that is not a directory, and it is a **rule** rather
than a personal arrangement: `06_SYSTEM/dotfiles` points at a separate repository
holding the machine's configs. Recommended, not enforced — nothing reads the
path, and the system runs without a dotfiles repository — and created as a link
because a plain directory there would shadow the repository it exists to reach.

```console
$ engine/familiar structure status
📊 P.A.Z.R.A.S System Status
========================
Configuration: …/config/structure/pazras-master-config.example.sh
Profile:       …/config/profile.example.yaml
PARA root:     /tmp/tut/tree

📁 Active Projects: 0
🎯 Areas: 5
   A: A_Work ✅
   B: B_Tech ✅
   C: C_Writing ✅
   D: D_Health ✅
   E: E_Home ✅
🗒️  Zettelkasten: 0 permanent notes, 0 daily notes
🔄 Backup Configuration:
   daily: 5 paths
   weekly: 1 paths
   monthly: 2 paths
💾 Storage Usage:
   00_INBOX: 0
   01_PROJECTS: 0
   02_AREAS: 20K
   03_ZETTEL: 12K
   04_RESOURCES: 0
   05_ARCHIVES: 4.0K
   06_SYSTEM: 3.1M
```

## 3 · A thought, filed

The first half of the loop is capture and filing, and the Zettelkasten is where
a thought goes when it is not yet a project:

```console
$ engine/familiar structure zettel daily
[ZETTEL] Created daily note from template: 2026-10-14
Daily note: /tmp/tut/tree/03_ZETTEL/01_Journal/2026/2026-10-14.md
```

The date is the system's, the template is the one `init` seeded, and the note
lands in the year folder the filing rule asks for. A thought that *is* a project
goes the other way:

```console
$ engine/familiar structure project create 2026-Q4_Paper-Title B_Tech
[PROJECT] Created project: 2026-Q4_Paper-Title in area B_Tech
✅ Project created at: /tmp/tut/tree/01_PROJECTS/2026-Q4_Paper-Title
📁 Area: B_Tech (B) - Technology, programming, and digital tools

$ engine/familiar structure project complete 2026-Q4_Paper-Title
[PROJECT] Archived project: 2026-Q4_Paper-Title
✅ Project archived to: /tmp/tut/tree/05_ARCHIVES/Projects/2026/2026-Q4_Paper-Title
```

Completion moves the folder to the archive with the year in the path, which is
what keeps `01_PROJECTS` readable: a project leaves the working floor when it
ends, and the record does not.

## 4 · The wait

The nightly pass is the middle of the loop and it does not run here: it reads
harness sessions and a model, both of which a fresh clone lacks. What a reader
can see is what it *would* do, and when:

```console
$ engine/familiar consolidation status
familiar consolidation status
  staged transcripts : 0
  session-log lines  : 0
  skill-usage lines  : 0
  data dir           : /tmp/tut/home/.local/share/pazras
  timer              : Thu 2026-10-15 03:42:59 CEST   4h 45min
                       Wed 2026-10-14 03:38:50 CEST   19h ago  familiar-memory.timer
```

That is the whole of the unattended half: a timer, a staging area, and a count of
what has accrued since the last run. [The Vigil](../explanation/lore/consolidation.md)
holds the design; the timer belongs to the machine, which is why the unit names
are functional and the mythos lives in the description.

## 5 · The harness entry points

A session is handed a fixed block of text rather than the tree:

```console
$ engine/familiar context l1
  wrote  claude     /tmp/tut/home/.claude/CLAUDE.md
  absent opencode   /tmp/tut/home/.config/opencode/opencode.json
  absent pi-system  /tmp/tut/home/.pi/agent/SYSTEM.md
  skip   hermes    no harness surface for always-on (sanitizer blocks it)
```

`absent` means the harness's config directory does not exist, and nothing is
written for it — a reader who does not run opencode is not given an opencode
config. `wrote claude` is the block being spliced into `CLAUDE.md` between its
generated markers; run it twice and the second run rewrites the same bytes.

## 6 · The check

The last step is the one that says the tree is still sound. Four generators and
one register check, all of which must agree with the files they derive:

```console
$ engine/familiar structure generate --check
STRUCTURE.md is in sync with the master config.
$ engine/familiar knowledge index --check
0 of 3 generated files would change
$ engine/familiar knowledge glossary --check
0 of 1 generated files would change in /tmp/tut/home/06_SYSTEM/memory
$ engine/familiar knowledge ontology check
ontology check: 0 finding(s) -- 0 declared warning(s), 0 undeclared error(s).
```

`--check` is the verb worth learning: every generator in this system can be
asked what it *would* change, and nothing is written until it is asked without
the flag. The gate is the same idea at a larger scale:

```console
$ python3 engine/checks/checks.py --run export
checks.py: gate 'export' passed (24 check(s), 6 skipped as instance-only
  (boundaries-compile, publish-audit, vault, guard, pi-guard-node,
   opencode-plugin-node))
```

Six checks declare that they measure *the machine* rather than the tree — the
compiled boundary rules, the private deny-list, the disk layout — and the gate
prints them rather than counting them as passes.
[The Threshold](../explanation/lore/checks.md) holds the reasoning.

## Honest limits

**Two steps are not run here.** The nightly pass and the journal search both need
an install — sessions to read, a model to run, an embedding index to search. Any
walkthrough of them would be a description of code rather than a lesson from
having run it.

**Also observed, unexplained.** `structure project list` prints `Area: (?)` for a
project created with an area a moment earlier. The folder is correct; the listing
loses it. Recorded as a defect rather than smoothed over.
