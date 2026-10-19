# 06_SYSTEM/engine

The generic code of the P.A.Z.R.A.S system: it changes when we change what we
built, and it names nothing about *this* installation. What the user decided
lives next door in `../config/`; what the system remembers lives in
`../memory/` (R3b). The three roots and the reasoning behind them are
`ontology SPECS` R1k.

## The one command line

```bash
familiar <subject> <verb> [args]      # familiar with no argument prints the table
```

`engine/familiar` is the only entry point, and it is on `PATH` through the
dotfiles fragment `shared/bash/.config/bash/rc.d/20-pazras.sh`. Its `ROUTES`
table is the one declaration of the command line; every systemd unit, harness
hook and document is written in its terms.

```
familiar knowledge     index | journal | ontology
familiar consolidation run | status | report | brief | posture | queue | decide |
                     decision | dismiss | conflicts
familiar skills        index
familiar context       capture | harness | tree | route | links | l1 | all |
                     opencode-session | hermes-session | pointers
familiar harness       jev
familiar checks        healthcheck | selftest
familiar structure     init | link | generate | validate | status | config |
                     project | zettel
familiar schedule      timers
familiar backup        run | verify | prune | sync | reconcile
familiar host          goto | capture | daily
```

The three programs this replaced are still here as BACK-ENDS, invoked by path
and not on `PATH`:

| Back-end | Reached as |
|---|---|
| `cli/familiar-memory.py` | `familiar knowledge …`, `familiar consolidation …`, `familiar skills …`, `familiar context capture` |
| `cli/familiar-context.py` | `familiar context tree/route/links/l1/all/harness` |
| `structure/pazras.sh` | `familiar structure …`, `familiar schedule …`, `familiar backup …` |

## Layout

```
engine/
├── familiar               The front door (R1l, R2d) — subject, then verb
├── lib/                 The bottom of the import order: roots, git, invocation
├── knowledge/           The written record: tree, frontmatter, the registers,
│                        the journal and knowledge indexes
├── harness/             Models and harnesses: jev, the question schemas, bands,
│                        pi-agent (the local-model delegate, R2g)
├── context/             What a session carries in and out: capture, transcripts,
│                        links, l1, route, the MCP server, the pi capture shim
├── consolidation/       The act of writing: the nightly pass, ranking, the
│                        ledger, the queue, the report, posture, stages/
├── cli/                 The back-ends and their entry scripts
├── checks/              The threshold: checks.py's registry, declared_paths,
│                        import_order, root_literals, instance_refs, push_guard,
│                        pre-commit and pre-push (the two hooks git runs)
├── boundaries/          The wards: the rules' compile and the harness guards
├── structure/           The bones: the config loader and the generators
├── schedule/            The almanac: the systemd unit generator
├── backup/              Backups, archive flush, the off-site mirror
└── host/                This machine: shell aliases and utilities
```

A package imports only to its LEFT in
`lib ← knowledge ← harness ← context ← consolidation ← cli`
(`checks/import_order.py`, registered in `checks.py`); `checks/` itself is
outside the order because it reads every package from the outside.

`lib/roots.py` declares where each root is (`ENGINE`, `CONFIG`, `MEMORY`,
`DEV`) and the named homes inside them; `lib/roots.sh` is its shell twin. No
other file in the engine spells a root's name — `checks/root_literals.py`
fails a commit that tries.

## Verify a change

```bash
python3 engine/checks/checks.py --list          # the one registry of checks
python3 engine/checks/checks.py --run pre-commit
familiar checks healthcheck                        # the weekly drift report
```

Everything under `config/` is generated from something in `engine/` or is a
decision the user made; fix the generator or edit the decision, never the
output. `engine/generated/` no longer exists for that reason (R2e).

See `../CLAUDE.md` for the rules that constrain edits, `../STRUCTURE.md` for
the PARA layout, and `../STORAGE-MODEL.md` for the backup layer.
