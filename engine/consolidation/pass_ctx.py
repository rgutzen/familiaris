"""pass_ctx -- the object every stage reads from and records into.

The split it enforces is the load-bearing decision of M2 (handoff, decision 2):

  ACTIONS   mechanical repairs the pass applies unattended. A change is
            mechanical only if it does NOT depend on a number nobody has
            validated: counts read off a log, set symmetry, derived artifacts.

  PROPOSALS everything scoring-derived or LLM-derived. These land in the
            report and nowhere else. A wrong number churns frontmatter; a
            wrong paragraph corrupts the knowledge base.

If you are adding a stage and are unsure which list a change belongs in, it is
a proposal.

THE SCORED TREE is reached through `ctx.tree()`, which loads and scores once and
memoises. Stages do not call `tree.documents()` and do not touch `ranking`: the
tree they get has been scored, so no stage can read, or report on, a document
that has not been. `ctx.loaded_tree()` is the report's accessor -- it returns
what was scored and never causes scoring, so an aborted pass still reports zero
rather than quietly doing the work at render time.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib

from consolidation import ledger
from consolidation import ranking as _ranking


@dataclasses.dataclass
class Proposal:
    stage: str
    kind: str                  # re-verify | demote | archive | stability | link | ...
    target: str                # path or leaf name
    what: str                  # the change, one line
    why: str = ""
    patch: str | None = None   # unified diff, when the proposal is appliable
    target_kind: str = "leaf"  # leaf | opaque -- what `target` actually names
    # ONE PROPOSAL OVER N ARTEFACTS (`SPECS.md` §Item shape). A batch proposal
    # names the population it covers here, one entry per artefact, and the queue
    # carries it through to `Item.members`. Empty for the ordinary case of one
    # proposal about one thing -- which is why it is a default and not a
    # required argument: only a stage that genuinely raised one question over N
    # artefacts has anything to put here.
    members: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Action:
    stage: str
    target: str
    what: str


@dataclasses.dataclass
class Note:
    """Something the reader must know: a limit hit, a stage skipped, a failure.

    Stages are required to record these rather than fail silently. An honest
    'stage 1 skipped: no model reachable' is worth more than a clean report.
    """
    stage: str
    text: str
    level: str = "note"        # note | warn | error


class Pass:
    def __init__(self, agents: pathlib.Path, base: pathlib.Path,
                 dry_run: bool, today: dt.date, verbose: bool = False,
                 flags: frozenset = frozenset()):
        self.agents = agents
        self.repo = agents.parent
        self.base = base
        self.dry_run = dry_run
        self.today = today
        self.verbose = verbose
        # The pass's own flags, so a stage reads a declared field instead of
        # guessing with getattr. `replay` guarded on `ctx.flags` for weeks while
        # nothing set it, which made `--dry-run --with-model` unreachable.
        self.flags = flags
        self._tree: _ranking.ScoredTree | None = None
        self.actions: list[Action] = []
        self.proposals: list[Proposal] = []
        self.notes: list[Note] = []
        self.stages_run: list[str] = []
        self.aborted: str | None = None
        self.quiet = False                 # set by preflight: nothing to do
        self.fingerprint = ""
        # Declared here, set by preflight (and re-read after the commit moves
        # HEAD). Empty until then: a pass that aborts before preflight finishes
        # has no branch, and the report says so rather than defending with a
        # getattr that hides whether the stage ever ran.
        self.branch = ""
        self.head = ""

    # -- the scored tree ---------------------------------------------------
    def tree(self) -> _ranking.ScoredTree:
        """The scored universe. Loaded and scored on first ask, then memoised.

        Any stage may ask, in any order -- `run --stages=6` scores what stage 6
        needs rather than reporting an empty tree as fully exempt.
        """
        if self._tree is None:
            self._tree = _ranking.load(self.agents, self.base, self.today)
        return self._tree

    def loaded_tree(self) -> "_ranking.ScoredTree | None":
        """The tree if a stage has already asked for it, else None.

        The report describes what the pass did; it must never be the thing that
        causes a load, a git call or a score.
        """
        return self._tree

    # -- recording ---------------------------------------------------------
    def act(self, stage, target, what):
        self.actions.append(Action(stage, target, what))

    def propose(self, stage, kind, target, what, why="", patch=None, *,
                target_kind, members=()):
        # target_kind is keyword-only and REQUIRED: a proposal must state what
        # its referent is, because `kind` alone does not say whether `target`
        # is a file path or an opaque id. No silent default that lets a new
        # call site misclassify an opaque referent as a leaf.
        if target_kind not in ledger.TARGET_KINDS:
            raise ValueError(f"target_kind must be one of {ledger.TARGET_KINDS}")
        self.proposals.append(
            Proposal(stage, kind, target, what, why, patch, target_kind,
                     list(members)))

    def note(self, stage, text, level="note"):
        self.notes.append(Note(stage, text, level))

    def log(self, msg):
        if self.verbose:
            print(f"    {msg}")
