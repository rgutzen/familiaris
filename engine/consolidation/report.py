"""Stage 8 -- Report. One dated file; every proposal lands here and nowhere else.

DESIGN CONSTRAINT, from consolidation-cycle.md: "An unread report is the
failure mode this design is most exposed to." With machine health explicitly
out of scope (M2 decision 4) this report has no secondary draw, so it must earn
being opened on its own.

Therefore: decisions first, changes second, limits third, and the score table
LAST and only under --verbose. A report that opens with 40 rows of scores will
not be read twice. Keep the default under one screen.
"""
from __future__ import annotations

import datetime as dt
import pathlib

from consolidation import queue, ranking

MAX_LISTED = 8          # per section, before "... and N more" -- the screen budget

# The decision queue does NOT get the MAX_LISTED cap. Every row there is an
# entry point: the interface is `decide N`, so an item whose number was not
# printed is an item the user cannot reach at all. That is the one section where
# a number is load-bearing rather than decorative.
#
# The screen budget is still real, so the tail keeps its NUMBER and drops its
# detail -- summarised one per LINE is affordable at 8-30 items, and a queue
# that hides its own ordinals would make `decide --kind=K --all` the only way to
# reach whatever fell off the end.
DECIDE_DETAIL = 12      # rows shown in full before the tail compresses


def _fmt(v):
    return "  --" if v is None else f"{v:.2f}"


def _section(title, lines, limit=MAX_LISTED):
    if not lines:
        return []
    out = [f"## {title}", ""]
    out += lines[:limit]
    if len(lines) > limit:
        out.append(f"- *... and {len(lines) - limit} more — `familiar consolidation report --full`*")
    out.append("")
    return out


def _uncappable(note) -> bool:
    """A note about what the pass SPENT or LOST, which must not be truncated.

    Stage 8b is the only spender (`--with-jev`), and a refusal that costs
    coverage is the other thing a reader must not have to hunt for in `--full`.
    Kept narrow on purpose: widening this to "important notes" would make the cap
    meaningless, and the cap is what keeps the report on one screen.
    """
    return note.stage == "8b"


def _recommendations(items_: list) -> list:
    """One line per banded item, in the SAME ordinal order as the rows above.

    A line is `N band target · action (p, model)` where the probability is the
    number the band was taken on. A Noul has no confidence, so none is printed --
    printing a blank field would imply the others have one (`PLAN.md` §The answer
    shapes). A promoted kind prints `ask` and says so: its recommendation is
    shown and cannot be defaulted away.
    """
    out = []
    for n, it in enumerate(items_, 1):
        rec = it.get("recommendation")
        if not rec:
            continue
        band = rec.get("band", "ask")
        lead = {"accept": "do", "ask": "needs you", "drop": "do not"}.get(band, band)
        line = f"  {n}  {band:<7} {it.get('target', '')} · {lead}: {rec.get('action', '')}"
        p = rec.get("probability")
        if p is not None:
            line += f"  (p {p:.2f}"
            if rec.get("axis") and rec["axis"] != "probability":
                line += f" on {rec['axis']}"
            line += ")"
        out.append(line)
    return out


def _queue_rows(ctx) -> list:
    """The digest is over the queue as it stands on disk, not over the in-memory
    proposals: `decide` reads the file, so the report must print the file's
    hash. A dry run wrote no file, so it prints the digest its items WOULD have
    -- and the report says the run was a dry run, so no `decide` is implied.
    """
    try:
        stored = queue.items(ctx.base)
    except ValueError:
        stored = []
    if ctx.dry_run or not stored:
        from consolidation.run import _fresh  # local: run imports report at module level
        return _fresh(ctx)
    return stored


def render(ctx, full: bool = False) -> str:
    L: list[str] = []
    head = f"# Consolidation — {ctx.today.isoformat()}"
    L += [head, ""]

    mode = "dry run — nothing was written" if ctx.dry_run else "applied"
    branch = ctx.branch or "?"        # empty = preflight never got that far
    # `loaded_tree`, never `tree()`: the report says what was scored. Asking for
    # the tree here would make an aborted pass score the world at render time
    # and then report the number as if a stage had done it.
    tree = ctx.loaded_tree()
    n_scored = len(tree) if tree else 0
    L += [f"`{mode}` · branch `{branch}` · {n_scored} documents scored · "
          f"stages: {', '.join(ctx.stages_run) or 'none'}", ""]

    if ctx.aborted:
        L += [f"> **Pass aborted at preflight:** {ctx.aborted}", ""]

    # -- 1. what needs a human decision ------------------------------------
    # One line per item, NUMBERED, and no commands for the reader to copy --
    # item 1e. The ordinal is the interface: every row here is resolvable by
    # `familiar consolidation decide N`, so a printed `dismiss --target=... --kind=...`
    # string would be a second writer, and one that has to be got right by hand
    # (it must carry `target_kind`, which is not visible in the target string).
    #
    # THE ORDER HERE IS THE QUEUE'S ORDER. `run._fresh` sorts proposals by kind
    # over the same list; if these two orders diverge, ordinal N names different
    # items in the report and in `decide`.
    by_kind: dict[str, list] = {}
    for p in ctx.proposals:
        by_kind.setdefault(p.kind, []).append(p)
    ordered = [p for kind in sorted(by_kind) for p in by_kind[kind]]
    dec = []
    # Two fields share the width so the rows read as a table, matching the shape
    # in SPECS.md item 1e (`  1  dangling-link  knowledge-vs-skills · related:
    # voice`). The `why` is deliberately NOT in the row: it is paragraphs long
    # for the `decision` kind, and a row that wraps is not a row. It is what
    # `decide N --why` and the walk's `?` key print.
    w_kind = max((len(p.kind.replace(" ", "-")) for p in ordered), default=0)
    w_tgt = max((len(p.target) for p in ordered), default=0)
    for n, p in enumerate(ordered, 1):
        handle = p.kind.replace(" ", "-")
        dec.append(f"  {n}  {handle:<{w_kind}}  {p.target:<{w_tgt}} · {p.what}")
    if dec:
        L += [f"## Needs a decision ({len(ctx.proposals)})", "",
              f"`decide N` resolves item N. Queue digest `{queue.digest(_queue_rows(ctx))}` "
              f"— `decide` refuses if it has moved.", ""]
        shown = len(dec) if full else DECIDE_DETAIL
        L += dec[:shown]
        # The tail keeps its NUMBER: nothing here may drop a row the user would
        # have to reach by ordinal. Compressed to `N kind` and nothing else.
        for row in dec[shown:]:
            num = row.lstrip().split("  ", 1)[0]
            kind = row.split("  ", 2)[1].strip() if row.count("  ") > 1 else ""
            L.append(f"  {num}  {kind}")
        if shown < len(dec):
            L.append(f"  ({len(dec) - shown} more, compressed — "
                     f"`familiar consolidation report --full` for the detail)")
        # The bands, SHOWN and not applied (2h). The ordering above is unchanged
        # this cycle: a scoring-derived proposal that starts steering on
        # unvalidated constants fails silently, which is the failure the shadow
        # rule exists to prevent.
        recs = _recommendations(_queue_rows(ctx))
        if recs:
            L += ["", "### Recommendations (displayed; ordering unchanged)", ""]
            L += recs
        L.append("")
    else:
        L += ["## Needs a decision", "", "Nothing. ", ""]

    # -- 2. what the pass changed by itself --------------------------------
    acts = [f"- `{a.target}` — {a.what} *(stage {a.stage})*" for a in ctx.actions]
    if acts:
        L += _section(f"Changed ({len(ctx.actions)})", acts,
                      len(acts) if full else MAX_LISTED)
    else:
        L += ["## Changed", "", "Nothing.", ""]

    # -- 3. limits and failures, stated rather than implied ----------------
    warns = [n for n in ctx.notes if n.level in ("warn", "error")]
    notes = [n for n in ctx.notes if n.level == "note"]
    if warns:
        L += _section("Warnings",
                      [f"- **{n.level}** *(stage {n.stage})* — {n.text}" for n in warns],
                      len(warns))
    if notes:
        # The spender's own line must survive the cap. `MAX_LISTED` exists to keep
        # the report under a screen, and with a few dozen stage-1 skip notes it
        # pushes everything after them out -- including the cost line, which is
        # how the first real `--with-jev` pass reported its spend in the FULL
        # report and not in the default one. A reader who never opens `--full`
        # would never see what the night cost.
        #
        # So: notes that are ABOUT THE PASS'S RESOURCES (a spend, a refusal that
        # cost coverage) are printed first and not capped; the rest keep the cap.
        keep = [n for n in notes if _uncappable(n)]
        rest = [n for n in notes if not _uncappable(n)]
        lines = [f"- *(stage {n.stage})* {n.text}" for n in keep]
        lines += [f"- *(stage {n.stage})* {n.text}" for n in rest[:max(0, (len(notes) if full else MAX_LISTED) - len(keep))]]
        if len(keep) + len(rest[:max(0, (len(notes) if full else MAX_LISTED) - len(keep))]) < len(notes):
            hidden = len(notes) - len(lines)
            lines.append(f"- *... and {hidden} more — {'`familiar consolidation report --full`' if not full else 'see the full report'}*")
        L += ["## Limits and skips", ""] + lines + [""]

    # -- 3b. appliable patches --------------------------------------------
    # Stage 4 is proposal-only, so its output must be trivially acceptable or it
    # will never be accepted at all: `familiar consolidation report --patch | git apply`
    # from the repo root, rather than a re-edit by hand.
    patches = [p for p in ctx.proposals if p.patch]
    if patches and full:
        L += ["## Appliable patch", "",
              "Stage 4 writes nothing itself. To accept everything below:", "",
              "```sh",
              "familiar consolidation report --patch | git apply -p1 --directory=. -",
              "```", "",
              "Review first — this is LLM-derived text going into the knowledge "
              "base, where a wrong paragraph reads as authored.", ""]
        for pr in patches:
            L += [f"### `{pr.target}` — {pr.what}", "", "```diff", pr.patch.rstrip(),
                  "```", ""]

    # -- 4. the numbers, last and optional ---------------------------------
    if full and tree is None:
        L += ["## Scores", "",
              "No document was scored — no stage asked for the tree "
              "(aborted preflight, an idle night, or `--stages` without a "
              "stage that scores).", ""]
    elif full:
        L += ["## Scores", "",
              "`R = T × (w_F·F + w_U·U)`. `--` means the component is **undefined**, "
              "not zero — an exempt document is never a pruning candidate.", "",
              "| Document | Kind | F | U | R | Quadrant | Exempt |",
              "|---|---|---|---|---|---|---|"]
        for d in tree.ranked():
            s = d.scores
            L.append(f"| `{d.name}` | {d.kind} | {_fmt(s['F'])} | {_fmt(s['U'])} | "
                     f"{_fmt(s['R'])} | {s['quadrant']} | {', '.join(s['exempt']) or '—'} |")
        L += ["", "### Unvalidated constants", "",
              "Every number below is a first estimate; the usage log had 2 lines when "
              "they were chosen, one of them a test. Do not tune by intuition "
              "(M2 Task 7).", ""]
        L += [f"- `{c}`" for c in ranking.unvalidated()]
        L += [""]
    else:
        L += ["---", "",
              f"*{n_scored} documents scored. `familiar consolidation report --full` for the "
              f"score table and the unvalidated constants behind it.*", ""]

    return "\n".join(L)


def patches(ctx) -> str:
    """Just the diffs, for `familiar consolidation report --patch | git apply`."""
    return "".join(p.patch for p in ctx.proposals if p.patch)


def write(ctx, full_too: bool = True) -> pathlib.Path:
    # A dry run must leave the tracked tree byte-identical -- including by not
    # dropping its own report into it. Dry-run reports go to the data dir,
    # which is outside git on purpose; real runs commit theirs as provenance.
    d = (ctx.base / "reports") if ctx.dry_run else (ctx.agents / "journal" / "reports")
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ctx.today.isoformat()}_consolidation.md"
    p.write_text(render(ctx, full=False))
    if full_too:
        (d / f"{ctx.today.isoformat()}_consolidation.full.md").write_text(
            render(ctx, full=True))
    # The patch is written beside the report so `report --patch` needs no rerun
    # of the model. Empty file rather than absent: "nothing proposed" and "the
    # pass never got that far" must not look the same.
    (d / f"{ctx.today.isoformat()}_consolidation.patch").write_text(patches(ctx))
    return p
