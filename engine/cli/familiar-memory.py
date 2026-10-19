#!/usr/bin/env python3
"""The capture and consolidation BACK-END, reached through `familiar` (R2d).

Not an entry point: `familiar context capture`, `familiar consolidation run` and
the rest of the subject-verb table route here. The verbs below are what
that table may name.

  capture --harness=<n> --event=<e>   hook payload on stdin, append to a log
  status                              staging / log counts
  run [--dry-run] [--stages=LIST]     the nightly consolidation pass
  skills index [--check]              stage 7 alone
  knowledge index [--check]           stage 7 alone: rebuild knowledge/INDEX.md,
                                      the one-level disclosure index (L2)
  knowledge glossary [--check]        O3c: rebuild the generated subject
                                      glossary leaf in system/publication/
  conflicts [--check] [--apply]       stage 5d alone: resolve declared
                                      supersession/contradiction by ISO-8601
                                      precedence (L4). Reports by default;
                                      --apply writes the marking.
  journal index [--force]             M4: (re)build the D4 embedding index
  journal search '<query>' [--top=N]  M4: search it, optionally within one
         [--branch=BRANCH]            branch (`system`|`areas`|`projects`|
         [--touches=SUBJECT]          `unknown`, from each entry's `cwd:`)
                                      and/or one subject it worked on
                                      (from each entry's `touches:`)
  report [--full] [--patch]           print the most recent report
  brief                               print the precomputed answers the last
                                      pass left: what changed, what's open,
                                      what failed (L5, sleep-time compute)
  posture                             the memory-poisoning checks (L9): what
                                      is injected, who may promote, what the
                                      curator wrote. Exit 3 on a failure.
  vault [--check] [--write]           the vault contract, derived from the
                                      posture and the registers (P1). Exit 3
                                      on drift; writes only with --write.
  decision --kind=K --text=T          record a user decision / overruled
                                      disagreement so a later session finds it
  dismiss --target=P --kind=K         stop a decided proposal recurring, until
                                      that leaf changes (or its time-box ends)
  queue [--all] [--json]              the open decisions, numbered; read-only
  decide [N] [--no] [--partial]       resolve item N (or walk the queue):
         [--kind=K --all] [--walk]     y accept, n refuse, a all of kind,
                                      s skip, ? full, q quit
  ontology <cmd>                      the class list, read and checked:
         facets|subjects|relations|    the registers, the subjects, the walkable
         branches|violations|check|    edges vs the coincidences, the three
         naming|review|selfcheck      branches, every known breach with its
                                      state, the structural checks, the seven
                                      naming rules, the review cadence
  jev check                           GET /v1/models with the deposited key;
                                      prints what the account may call
  opencode-session --session=ID       stage one opencode session's transcript
           [--db=PATH]                out of opencode.db (Loop A, opencode half)
  hermes-session                      hook-facing: reads session_id from stdin,
                                      hands off to a detached worker (Loop A,
                                      hermes half)
  hermes-session-worker --session=ID  the detached worker itself; not meant to
                                      be called directly
  selftest [--signals] [--schema]     capture gates: signal fixtures, the
           [--hook-cost]              skill-usage schema, hook latency

GOVERNING RULES (memory-mechanisms.md):
  * Hooks capture, cron consolidates. A hook never calls an LLM.
  * Hooks only append to logs; only the scheduled pass mutates tracked files.
    Sessions run in parallel -- a hook editing frontmatter races.

AN UNDECLARED FLAG IS AN ERROR, not a shrug. Every subcommand below states what
it accepts as an `invocation.Spec`, and anything else exits 1. `run --dry-dun`
used to drop the typo and run a REAL pass, which on 2026-09-03 wrote a partial
report over the night's and committed it (reverted in 057d04b).

DISPATCH IS LAZY ON PURPOSE. `capture` runs on the user's latency budget for
every SessionEnd and PostToolUse, so it must not import the ranking, reporting
or stage code. Do not hoist these imports to the top of the file; `selftest
--hook-cost` measures the consequence if you do.

Exit codes: 0 ok - 1 usage/parse error - 2 refused - 3 drift (--check/--dry-run)
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ENGINE = os.path.dirname(HERE)
if ENGINE not in sys.path:
    sys.path.insert(0, ENGINE)

from lib import roots  # noqa: E402

BASE_DIR = os.environ.get("PAZRAS_DATA_DIR", os.path.expanduser("~/.local/share/pazras"))
AGENTS_DIR = os.environ.get("PAZRAS_MEMORY_DIR", str(roots.INSTALL / roots.MEMORY_REL))


def usage(code=1):
    sys.stderr.write(__doc__.split("GOVERNING")[0].rstrip() + "\n")
    return code


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else ""
    rest = argv[1:]

    # -- the latency-critical path, before any heavy import --------------
    if cmd == "capture":
        from context import capture
        return capture.main(rest, BASE_DIR, AGENTS_DIR)

    if cmd in ("-h", "--help", "help", ""):
        return usage(0 if cmd else 1)

    from lib import invocation

    def leaf(fn, spec):
        try:
            return fn(invocation.parse(rest, spec, BASE_DIR, AGENTS_DIR))
        except invocation.UsageError as exc:
            sys.stderr.write("[familiar] %s\n" % exc)
            return 1

    if cmd == "status":
        from cli import cli
        return leaf(cli.status, cli.STATUS)
    if cmd == "run":
        from consolidation import run
        return leaf(run.main, run.SPEC)
    if cmd == "skills":
        if rest[:1] != ["index"]:
            sys.stderr.write("[familiar] usage: familiar skills index [--check]\n")
            return 1
        from consolidation.stages import reindex
        return reindex.main(rest[1:])
    if cmd == "knowledge":
        if rest[:1] not in (["index"], ["glossary"]):
            sys.stderr.write(
                "[familiar] usage: familiar knowledge index|glossary [--check]\n")
            return 1
        if rest[:1] == ["glossary"]:
            from knowledge import glossary
            return glossary.main(rest[1:])
        from knowledge import knowledge_index
        return knowledge_index.main(rest[1:])
    if cmd == "conflicts":
        from consolidation.stages import conflict
        return conflict.main(rest)
    if cmd == "journal":
        from knowledge import journal_index
        try:
            return journal_index.main(rest, BASE_DIR, AGENTS_DIR)
        except invocation.UsageError as exc:
            sys.stderr.write("[familiar] %s\n" % exc)
            return 1
    if cmd == "report":
        from cli import cli
        return leaf(cli.show_report, cli.REPORT)
    if cmd == "brief":
        from cli import cli
        return leaf(cli.show_brief, cli.BRIEF)
    if cmd == "posture":
        from consolidation import posture
        return leaf(posture.main, posture.SPEC)
    if cmd == "vault":
        from consolidation import posture
        return leaf(posture.vault_main, posture.VAULT_SPEC)
    if cmd == "decision":
        from cli import cli
        return leaf(cli.decision, cli.DECISION)
    if cmd == "dismiss":
        from cli import cli
        return leaf(cli.dismiss, cli.DISMISS)
    if cmd == "queue":
        from cli import cli
        return leaf(cli.show_queue, cli.QUEUE)
    if cmd == "decide":
        from cli import cli
        return leaf(cli.decide, cli.DECIDE)
    if cmd == "ontology":
        from cli import cli
        return leaf(cli.ontology_cmd, cli.ONTOLOGY)
    if cmd == "jev":
        from cli import cli
        return leaf(cli.jev_cli, cli.JEV)
    if cmd == "opencode-session":
        from cli import cli
        return leaf(cli.opencode_session, cli.OPENCODE_SESSION)
    if cmd == "hermes-session":
        from cli import cli
        return leaf(cli.hermes_session, cli.HERMES_SESSION)
    if cmd == "hermes-session-worker":
        from cli import cli
        return leaf(cli.hermes_session_worker, cli.HERMES_SESSION_WORKER)
    if cmd == "selftest":
        from cli import selftest
        return leaf(selftest.main, selftest.SPEC)
    if cmd == "pointers":
        from context import pointers
        return leaf(pointers.main, pointers.SPEC)

    # M1 subcommands folded into `run`; kept so old wiring says where to look.
    if cmd in ("distil", "promote", "prune"):
        sys.stderr.write(
            "[familiar] '%s' is now a stage of `familiar consolidation run` "
            "(consolidation-cycle.md). Try: familiar consolidation run --dry-run\n" % cmd)
        return 2

    sys.stderr.write("[familiar] unknown command: %s\n" % cmd)
    return usage()


if __name__ == "__main__":
    sys.exit(main())
