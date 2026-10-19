"""Stage 4 -- Consolidate. Journal -> knowledge/.

PROPOSAL-ONLY IN M2, by the ruling in the handoff: decision 2 named
SCORING-derived changes proposal-only, but this stage's writes are LLM-derived,
which is a different and larger risk. A wrong number churns frontmatter; a wrong
paragraph corrupts the knowledge base, and the corruption reads as authored.

So the output is emitted as an APPLIABLE PATCH rather than prose, so that
accepting a night's consolidation is one command and not a re-edit:

    familiar consolidation report --patch | git apply

Promote to unattended only after the report has been read for a few weeks.

-- memory/knowledge/system/consolidation/consolidation-cycle.md: APPEND OR MARK SUPERSEDED, NEVER REWRITE A LEAF WHOLESALE --

The rule, in the falsifiable form `_as_patch` enforces: a patch this stage emits
may only (a) INSERT lines into a leaf's body, or (b) REVISE A FRONTMATTER VALUE
for a marking key (`supersedes:`, `superseded_by:`, `trust:`) -- and (b) is
itself a form of (a)'s exception, because marking a leaf superseded is exactly
the sanctioned replacement. Nothing else. `_append_only` proves (a) and refuses
the rest.

WHY THIS IS A GUARD AND NOT A COMMENT. The patch builder already appended
unconditionally, so the rule held by construction -- and a rule that holds by
construction is one refactor away from not holding, with the failure invisible:
a rewritten leaf pasted into BODY: arrives as a diff of INSERTIONS, so the
report shows a green add-hunk and a human reading `report --patch` accepts it.
The leaf then contains two whole versions, and the newer one reads as authored.
That is the brevity-bias/context-collapse failure ACE (arXiv 2510.04618) names,
reached through the door marked "append-only".

So the rule is stated, checked, and given a LEGAL ALTERNATIVE: `KIND:
supersede-leaf` with a `SUPERSEDES:` field is how the model says "this leaf is
replaced". Without a legal route the only route is the illegal one.

MEMORY.md IS NOT A TARGET AND MUST NOT BE RE-CREATED. It was deleted
2026-09-04 (commit 66135b7): `memory/` serves every agent on this machine, the
always-on layer is compiled by `familiar context l1` from CONTEXT.md +
user/user-identity.md + conventions/collaboration.md, and a file nothing loads
is 569 tokens of session floor for no reader. This stage kept reading it,
cap-checking it and offering it as a TARGET for weeks after the deletion, and
its last proposal would have resurrected it as a leaf-shaped mutant with
frontmatter it was never meant to carry. A model proposal naming it is now
dropped like any other path that is not a target.

Directive paths (USER.md, knowledge/conventions/**) are proposal-only at
every stage and are never in a patch.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import difflib

from knowledge import frontmatter
from consolidation import ledger
from harness import model
from lib import roots

RECENT_DAYS = 14
# Stage 4's prompt is the largest in the pass -- every recent journal entry and
# the whole leaf list -- and it grows as stage 1 adds entries. It timed out at
# model.TIMEOUT (300 s) on the first night stage 1 had run, when the entry count
# doubled. Budget it separately from stage 1's per-transcript call.
CONSOLIDATE_TIMEOUT = 900
MAX_ENTRIES = 12          # newest first; a prompt that never finishes proposes nothing

# A path this stage may never write, whatever a model proposes. Not a
# prefix-match list: MEMORY.md is a tombstone (see the module docstring), the
# other two are directive. Kept together because the handling is identical --
# drop the proposal, say so, do not report it as appliable.
OFF_LIMITS = ("USER.md", "knowledge/conventions/", "MEMORY.md")

# -- the marking keys, i.e. the only frontmatter values a stage-4 patch may
# REVISE rather than append. `supersedes`/`superseded_by` are the declared
# precedence pair; `trust` is the marking that makes the loser stop being read
# as current. Anything else in frontmatter is out of reach here -- a proposal
# that wants to change `stability` or `scope` is a stage-6/downscale matter and
# arrives as prose in WHY:, not as a patch.
MARKING_KEYS = ("supersedes", "superseded_by", "trust")

# -- the rewrite guard's constants. Unvalidated, like every threshold this pass
# holds, and reported as such in the note that fires (ranking.unvalidated is
# where R's constants are declared; these are not R's, so they are declared here
# and named in the report line they produce).
#
# Two tests, because brevity bias and a pasted rewrite leave different marks.
#  * The STRUCTURAL test needs the target to have >= 2 body headings, and fires
#    when the BODY reproduces every one of them in order. That is the pasted
#    rewrite, and it fires regardless of length -- which matters, because
#    ACE (arXiv 2510.04618) names BREVITY BIAS as the characteristic failure of
#    an LLM rewrite: the rewritten leaf is typically SHORTER than the original,
#    so a length threshold alone would miss the case the rule exists for.
#  * The LENGTH test covers the leaf with one heading, where "it repeats the
#    heading" cannot distinguish an addition from a replacement. It needs a
#    repeated heading AND REWRITE_SHARE of the target's non-blank line count.
REWRITE_SHARE = 0.5
REWRITE_MIN_HEADINGS = 2
# A BODY opening with frontmatter is a whole leaf, not an addition. No threshold:
# a leaf's frontmatter block is never a legitimate append to another leaf's body.
FM_OPEN = "---\n"

PROMPT = """You maintain a private engineering knowledge base. Below are recent \
journal entries (episodic records of work sessions) and the leaves that already \
exist.

Propose consolidation. Output ONLY a list of proposals, each in this exact form, \
separated by blank lines. Output nothing else.

PROPOSAL: <one-line summary>
TARGET: <knowledge/<area>/<leaf>.md>
KIND: <new-leaf | extend-leaf | supersede-leaf>
SUPERSEDES: <path of the leaf this replaces — ONLY for supersede-leaf, else omit>
WHY: <one sentence: the durable fact that emerged, and from which entry>
BODY:
<the markdown to add, verbatim>
END

Rules:
- NEVER REWRITE A LEAF. Do not output text that already exists in the target \
leaf. `extend-leaf` means ADD: your BODY is appended after everything already \
there, so repeating existing prose or headings duplicates it. If a leaf must be \
REPLACED rather than extended, use `KIND: supersede-leaf` with `SUPERSEDES: \
<that leaf's path>` and put ONLY the new leaf's content in BODY — the old leaf \
is marked superseded for you, and its text is retained for provenance.
- Propose only DURABLE facts: something a future session would otherwise \
re-derive. Not narrative, not what happened, not a summary of the session.
- CRYSTALLIZED, NOT SCAFFOLDING. A fact earns a leaf only if it stays true \
after the current work finishes. Reject anything that dies when a plan \
completes: phase and milestone numbering, migration state, "currently at step \
N", which items are open, what is built vs unbuilt. Those live in the roadmap \
and go stale in the knowledge tree within weeks, where nothing will notice. \
The durable version of such a fact is the RULE it illustrates, not the state: \
"plans never live in knowledge/, because a leaf decays by becoming false and a \
plan decays by being done" is crystallized; "the phases are M0-M4" is not.
- Prefer the general rule to the incident that taught it. If the transcript \
shows a specific bug, propose the invariant that prevents its whole class.
- A fact that appeared in three or more separate sessions has earned a leaf.
- Never propose changes to USER.md or knowledge/conventions/** — directive.
- If nothing durable emerged, output exactly: NOTHING
- Do not invent facts that are not in the entries.

EXISTING KNOWLEDGE LEAVES, with their section headings. If a fact is already \
covered by one of these sections, DO NOT propose it again — say nothing about \
it. Only propose what is genuinely absent:
{leaves}

RECENT JOURNAL ENTRIES:
---
{entries}
---"""


def _recent(ctx):
    out = []
    cutoff = ctx.today - dt.timedelta(days=RECENT_DAYS)
    for p in sorted((ctx.agents / "journal").rglob("*.md")):
        if p.name == "CONTEXT.md":
            continue
        try:
            txt = p.read_text()
        except OSError:
            continue
        # `date:` frontmatter is the intent, but 4 of the 5 entries written
        # before M2 carry the date ONLY in the filename -- which is the layout
        # the journal router actually specifies. Filename is the fallback, not
        # the other way round, so a corrected `date:` still wins.
        m = None
        for line in txt[:600].split("\n"):
            if line.startswith("date:"):
                try:
                    m = dt.date.fromisoformat(line[5:].strip())
                    break
                except ValueError:
                    pass
        if m is None:
            try:
                m = dt.date.fromisoformat(p.name[:10])
            except ValueError:
                pass
        if m and m >= cutoff:
            out.append((p, txt))
    return out


def run(ctx) -> bool:
    # -- exit criteria 10 & 11: decisions and overruled disagreements ------
    # Runs BEFORE the model call and regardless of whether one is available:
    # losing a decision the user already made is worse than any consolidation
    # this stage could propose, and it must not depend on a network round trip.
    # Read once, up front: both this call and the later leaf-proposal loop
    # share the one Dismissals object.
    dismissed = ledger.dismissals(ctx.base)
    _surface_decisions(ctx, dismissed)

    entries = _recent(ctx)

    if not entries:
        ctx.note("4", f"no journal entries in the last {RECENT_DAYS} days — "
                      f"nothing to consolidate")
        return True

    if ctx.dry_run:
        ctx.note("4", f"{len(entries)} recent journal entr(ies) would be offered to "
                      f"`{model.MODEL}` for consolidation; --dry-run makes no model "
                      f"call. Stage 4 is PROPOSAL-ONLY regardless — it emits a patch, "
                      f"it never writes knowledge/ itself.")
        return True

    if not model.available():
        ctx.note("4", "pi is not on PATH — no consolidation proposed", "error")
        return True

    # Titles ALONE are not enough. With only titles the model cannot tell
    # whether a fact is already recorded, so it re-proposes the same extension
    # every night until the journal entries age out of the window -- and a
    # report that repeats yesterday's resolved proposals stops being read.
    # Section headings are a few hundred bytes against a ~60 kB prompt and are
    # exactly the missing signal.
    rows = []
    for d in ctx.tree().leaves():
        heads = [l.strip() for l in (d.get("_body") or "").split("\n")
                 if l.startswith(("## ", "### "))]
        rows.append(f"- {d.rel}: {d.get('title', '')}"
                    + (f"\n    sections: {' | '.join(heads)}" if heads else ""))
    leaves = "\n".join(rows)
    used_entries = sorted(entries, key=lambda e: e[0].name, reverse=True)[:MAX_ENTRIES]
    if len(used_entries) < len(entries):
        ctx.note("4", f"{len(entries)} recent entries, newest {len(used_entries)} "
                      f"offered to the model — the rest were already consolidated "
                      f"on an earlier night")
    body = "\n\n".join(f"### {p.relative_to(ctx.agents).as_posix()}\n{t[:6000]}"
                       for p, t in used_entries)
    try:
        ctx.log(f"prompt {len(body) // 1000} kB over {len(used_entries)} entries")
        out = model.ask(PROMPT.format(leaves=leaves, entries=body),
                        timeout=CONSOLIDATE_TIMEOUT)
    except model.ModelError as exc:
        ctx.note("4", f"consolidation failed ({exc}); nothing proposed", "error")
        return True

    if out.strip().upper().startswith("NOTHING"):
        ctx.note("4", f"{len(entries)} recent entr(ies) reviewed; no durable fact "
                      f"had emerged that is not already a leaf")
        return True

    # `dismissed` was read once, up front, and is arithmetic over what was
    # read plus one hash of the target leaf.
    reply = _parse(out)
    if reply.dropped:
        # Work the model did that nobody can use: named, not silently binned.
        lost = ", ".join(f"`{p['target']}` ({p['summary'] or 'no summary'})"
                         for p in reply.dropped)
        ctx.note("4", f"{len(reply.dropped)} proposal(s) arrived with no BODY and "
                      f"were dropped — the model wrote a header and no content, so "
                      f"there is nothing to propose: {lost}", "warn")
    skipped_d = 0
    for p in reply:
        if p["target"].startswith(OFF_LIMITS):
            # One branch, two reasons, stated per case so the report does not
            # make the reader look up which. `MEMORY.md` is a tombstone and the
            # other two are directive; what they share is that a patch naming
            # them must never reach `report --patch`.
            why = ("deleted 2026-09-04 and nothing loads it — a proposal would "
                   "re-create it as an orphan" if p["target"].startswith("MEMORY.md")
                   else "a directive file — propose into the report, never a patch")
            ctx.note("4", f"model proposed `{p['target']}` — dropped: {why}",
                     "warn")
            continue
        # L3. The guard runs BEFORE the dismissal check, because a suppressed
        # rewrite must be reported even when the target is already dismissed --
        # "the model is still trying to rewrite this leaf" is information the
        # dismissal ledger does not hold.
        suspect = _rewrite_suspect(ctx, p)
        if suspect:
            ctx.note("4", f"`{p['target']}`: BODY {suspect} — dropped rather than "
                          f"appended. Stage 4 may only ADD to a leaf; to replace "
                          f"one, the proposal has to say `KIND: supersede-leaf` "
                          f"and `SUPERSEDES: <path>`. (share threshold "
                          f"{REWRITE_SHARE:.0%}, unvalidated)", "warn")
            continue
        if dismissed.covers(ctx.repo, p["target"], p["kind"],
                           target_kind="leaf"):
            skipped_d += 1
            continue
        try:
            patch = _as_patch(ctx, p)
        except _IllegalPatch as exc:
            # A rule violation here is a bug in this module, not a bad model
            # reply, so it is loud. The stage still returns: one refused patch
            # must not cost the night's other proposals.
            ctx.note("4", f"`{p['target']}`: patch refused — {exc}", "error")
            continue
        ctx.propose("4", p["kind"], p["target"], p["summary"], p["why"],
                    patch=patch, target_kind="leaf")
    if skipped_d:
        ctx.note("4", f"{skipped_d} proposal(s) suppressed — already decided and "
                      f"the target leaf is unchanged since "
                      f"(`familiar consolidation dismiss`)")
    return True


@dataclasses.dataclass
class Reply:
    """What the model returned: the usable records, and the ones that were not.

    `dropped` exists because a record without a BODY used to vanish -- it
    appeared in no report and no count, so a model that formatted one proposal
    wrongly cost work nobody could see was missing. Same rule as `ledger.read`:
    the parser counts what it could not use and the CALLER decides how loudly
    to say so. Unlike a malformed JSON line, a bodyless record still carries its
    summary and target, so the report can name what was lost rather than
    counting it.
    """
    proposals: list
    dropped: list

    def __iter__(self):
        return iter(self.proposals)

    def __len__(self) -> int:
        return len(self.proposals)


def _parse(out: str) -> Reply:
    props, cur, body, in_body = [], None, [], False
    for line in out.split("\n"):
        s = line.strip()
        if s.startswith("PROPOSAL:"):
            if cur:
                cur["body"] = "\n".join(body).strip()
                props.append(cur)
            cur, body, in_body = {"summary": s[9:].strip(), "target": "?",
                                  "kind": "?", "why": "", "supersedes": ""}, [], False
        elif cur is None:
            continue
        elif s.startswith("TARGET:"):
            cur["target"] = s[7:].strip()
        elif s.startswith("KIND:"):
            cur["kind"] = s[5:].strip()
        elif s.startswith("SUPERSEDES:"):
            cur["supersedes"] = s[11:].strip()
        elif s.startswith("WHY:"):
            cur["why"] = s[4:].strip()
        elif s == "BODY:":
            in_body = True
        elif s == "END":
            cur["body"] = "\n".join(body).strip()
            props.append(cur)
            cur, body, in_body = None, [], False
        elif in_body:
            body.append(line)
    if cur:
        cur["body"] = "\n".join(body).strip()
        props.append(cur)
    return Reply(proposals=[p for p in props if p.get("body")],
                 dropped=[p for p in props if not p.get("body")])


class _IllegalPatch(RuntimeError):
    """A patch this stage built that violates L3. A bug here, not a bad reply."""


def _body_headings(text: str) -> list[str]:
    """The H2+ headings of a body, in order. `##` and `###` both count.

    Deliberately not the H1: `_leaf-template.md` gives every leaf an H1 equal
    to its title, so an H1 in a BODY is either a mistake or the pasted leaf,
    and both are already caught by the frontmatter test.
    """
    return [l.strip() for l in text.split("\n")
            if l.startswith(("## ", "### "))]


def _is_subsequence(small: list[str], big: list[str]) -> bool:
    it = iter(big)
    return all(any(x == y for y in it) for x in small)


def _rewrite_suspect(ctx, p) -> str:
    """Why a BODY reads as a whole rewritten leaf, or "" when it does not.

    Returns an explanation string rather than a bool so the report can say
    which of the two tests fired. Two tests, both cheap and both stated:

      1. A BODY opening with `---` is a leaf, not an addition. Unambiguous.
      2. The BODY reproduces the target's COMPLETE heading sequence, in order,
         when the target has at least `REWRITE_MIN_HEADINGS` of them.
      3. The BODY repeats an existing heading AND reaches `REWRITE_SHARE` of the
         target's length -- the leaf with one heading, where (2) cannot decide.

    Not proof, any of them -- signals, with their thresholds named in the note,
    which is why the failure mode is "dropped and reported", never "applied and
    hoped".

    `new-leaf` and `supersede-leaf` are exempt: a new leaf legitimately carries
    frontmatter and may legitimately echo headings, and supersede is the
    sanctioned route for exactly the case this guards against.
    """
    kind = (p.get("kind") or "").strip()
    if kind in ("new-leaf", "supersede-leaf"):
        return ""
    block = (p.get("body") or "")
    if block.startswith(FM_OPEN):
        return "opens with a `---` frontmatter block, i.e. a whole leaf was pasted"
    path = ctx.repo / f"{roots.MEMORY_REL}/{p['target'].lstrip('/')}"
    if not path.exists():
        return ""
    try:
        old = path.read_text()
    except OSError:
        return ""
    heads = _body_headings(old)
    if not heads:
        return ""
    block_heads = _body_headings(block)
    if len(heads) >= REWRITE_MIN_HEADINGS and _is_subsequence(heads, block_heads):
        return (f"reproduces all {len(heads)} of the leaf's headings, in order — "
                f"that is the leaf, not an addition to it")
    old_n = len([l for l in old.split("\n") if l.strip()])
    block_n = len([l for l in block.split("\n") if l.strip()])
    repeated = [h for h in block_heads if h in set(heads)]
    if repeated and old_n and block_n >= REWRITE_SHARE * old_n:
        return (f"repeats the leaf's `{repeated[0]}` heading and is "
                f"{block_n / old_n:.0%} of the leaf's length — that is a "
                f"replacement, not an addition")
    return ""


def _append_only(diff: str, existed: bool) -> None:
    """L3, checked. `existed` False means the diff creates the file.

    For an EXISTING target the diff may carry no `-` line: see `_as_patch`, which
    never routes a body hunk through here for a marking edit.
    """
    if not existed:
        return
    for line in diff.split("\n"):
        if line.startswith("-") and not line.startswith("---"):
            raise _IllegalPatch(
                "a patch to an existing leaf deleted a line from its body: "
                f"{line[:80]!r}")


def _as_patch(ctx, p) -> str:
    """A unified diff against the repo root, appliable with `git apply -p1`.

    Built with difflib from the real before/after text, NOT by hand. A
    hand-written `@@` header with a fabricated context line looks like a diff
    and is rejected by the only consumer that matters; `git apply --check` is
    the difference between "looks right" and "is right".

    memory/knowledge/system/consolidation/consolidation-cycle.md, and the whole shape of this function follows from it: a leaf is
    APPENDED TO or it is MARKED SUPERSEDED, and nothing else happens to it.

      * `new-leaf` / `extend-leaf` -> one hunk per file, insertions only, and
        `_append_only` proves it. A bad proposal can therefore add a paragraph
        a human then deletes; it cannot destroy one.
      * `supersede-leaf` -> two files. The new leaf is created whole (its
        `supersedes:` comes from the model's SUPERSEDES:, mechanical elsewhere),
        and the OLD leaf gets exactly one kind of edit: the marking keys in
        MARKING_KEYS. Its body is never touched, which is what "retained for
        provenance" has to mean to be worth saying.
    """
    kind = (p.get("kind") or "").strip()
    if kind == "supersede-leaf":
        return _supersede_patch(ctx, p)

    rel = f"{roots.MEMORY_REL}/{p['target'].lstrip('/')}"
    path = ctx.repo / rel
    old = path.read_text() if path.exists() else ""
    block = p["body"].rstrip("\n") + "\n"
    if not old and not block.startswith(FM_OPEN):
        # A new leaf without frontmatter breaks the shared contract: stage 3
        # would score it never-verified and the routers would not know its
        # category. Synthesised here rather than demanded from the model --
        # these are mechanical facts the pass knows and the model does not.
        block = _new_leaf_frontmatter(ctx, p) + "\n" + block
    if old and not old.endswith("\n"):
        old += "\n"
    new = old + ("\n" if old else "") + block
    diff = _diff(rel, old, new)
    _append_only(diff, existed=bool(old))
    return diff


def _diff(rel: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{rel}" if old else "/dev/null", tofile=f"b/{rel}", n=3))


def _supersede_patch(ctx, p) -> str:
    """Create the replacing leaf, mark the replaced one. Two files, one patch.

    The marking half goes through `frontmatter.set_fields`, the same
    line-surgical writer stage 2 and 5a use, so key order and trailing `#`
    comments survive -- a parse-then-reserialise round trip would destroy M1's
    provenance comments. It is therefore the ONE place this module emits a `-`
    line, and `_marking_only` proves the deletion stays inside the frontmatter
    and touches only MARKING_KEYS.

    A `SUPERSEDES:` that names nothing on disk is refused rather than applied:
    marking a leaf superseded by a leaf that does not exist leaves the tree
    claiming a precedence with no winner, which is worse than the conflict it
    was meant to settle.
    """
    target = p["target"].strip()
    old_rel = (p.get("supersedes") or "").strip()
    if not old_rel:
        raise _IllegalPatch("`supersede-leaf` arrived with no `SUPERSEDES:` line")
    new_rel = f"{roots.MEMORY_REL}/{target.lstrip('/')}"
    old_path = ctx.repo / f"{roots.MEMORY_REL}/{old_rel.lstrip('/')}"
    if ctx.repo / new_rel == old_path:
        raise _IllegalPatch(f"`{target}` supersedes itself")
    if not old_path.exists():
        raise _IllegalPatch(f"`SUPERSEDES: {old_rel}` names no file on disk")
    old_text = old_path.read_text()
    if (ctx.repo / new_rel).exists():
        raise _IllegalPatch(f"`{target}` already exists — supersede creates the "
                            f"replacement, it does not extend it")

    block = p["body"].rstrip("\n") + "\n"
    if not block.startswith(FM_OPEN):
        block = _new_leaf_frontmatter(ctx, p, supersedes=old_rel) + "\n" + block
    created = _diff(new_rel, "", block)

    try:
        marked = frontmatter.set_fields(old_text, {
            "superseded_by": [target],
            "trust": "deprecated",
        })
    except ValueError as exc:
        # No frontmatter at all. A leaf without one is already broken and stage
        # 3 says so; guessing here would invent a contract.
        raise _IllegalPatch(f"`{old_rel}` has no frontmatter to mark ({exc})")
    edit = _diff(f"{roots.MEMORY_REL}/{old_rel.lstrip('/')}", old_text, marked)
    _marking_only(edit, old_text, old_rel)
    return created + edit


def _marking_only(diff: str, old_text: str, rel: str) -> None:
    """L3 for the marking half: a deletion may only be a MARKING KEY in the
    frontmatter.

    `set_fields` rewrites a frontmatter value in place, so honouring a
    supersession necessarily emits `-` lines -- `trust: trusted` becomes
    `trust: deprecated`. That is the "mark superseded" half of the rule, and it
    is the only deletion this module may produce. The check is: take every `-`
    line in the diff, and require that it be a frontmatter line of the ORIGINAL
    text whose key is in MARKING_KEYS. Anything else -- a body line, an
    unmarked key -- is refused.

    Counted against the original text rather than parsed out of the diff's `@@`
    hunks: a diff's line numbers refer to two different files at once, and
    reading them wrong is how this check would become decorative.
    """
    m = frontmatter.FM_RE.match(old_text)
    fm_lines = set()
    if m:
        fm_lines = {"---", *(m.group(1).split("\n")), "---"}
    for line in diff.split("\n"):
        if not line.startswith("-") or line.startswith("---"):
            continue
        content = line[1:]
        km = frontmatter.KEY_RE.match(content)
        if km is None or km.group(1) not in MARKING_KEYS:
            raise _IllegalPatch(
                f"a marking patch to `{rel}` deleted a line that is not a marking "
                f"key ({MARKING_KEYS}): {content[:80]!r}")
        if content not in fm_lines:
            raise _IllegalPatch(
                f"a marking patch to `{rel}` deleted {content[:80]!r}, which is not "
                f"in that leaf's frontmatter — the body is out of reach here")


def _surface_decisions(ctx, dismissed) -> None:
    """Report every recorded decision that has not yet landed anywhere durable.

    "Landed" means the decision's id appears somewhere under memory/ -- a leaf,
    or a journal entry. Until then the pass raises it every night.
    That nagging is the enforced half of the mechanism: capture is level 4 and
    skippable, but once a line exists it is not quietly forgotten.

    A dismissal only pauses the nagging for `OPAQUE_TTL_DAYS`: if the decision
    still has not landed durably by the time the window lapses, it resurfaces
    -- the same nagging this function exists to guarantee, just deferred, never
    silenced permanently.
    """
    log = ledger.read(ctx.base, ledger.DECISIONS)
    rows = log.rows
    if log.malformed:
        # A decision that cannot be read is a decision lost -- the one thing this
        # mechanism exists to prevent. Loud, not a note.
        ctx.note("4", f"{log.malformed} unparseable line(s) in {ledger.DECISIONS}: "
                      f"a recorded decision may be unreadable and will never be "
                      f"surfaced. Inspect {log.path}.", "error")
    if not rows:
        ctx.note("4", "no decisions or disagreements recorded "
                      "(`familiar consolidation decision --help`) — level 4, so an empty "
                      "log means either none arose or none were captured")
        return
    landed = set()
    for f in ctx.agents.rglob("*.md"):
        if "/journal/reports/" in f.as_posix():
            continue                       # a report citing it is not it landing
        try:
            txt = f.read_text()
        except OSError:
            continue
        for r in rows:
            if r["id"] in txt:
                landed.add(r["id"])
    skipped_d = 0
    for r in rows:
        if r["id"] in landed:
            continue
        if dismissed.covers(ctx.repo, r["id"], r["kind"], target_kind="opaque"):
            skipped_d += 1
            continue
        kind = "decision" if r["kind"] == "decision" else "overruled disagreement"
        ctx.propose("4", r["kind"], r["id"],
                    f"{kind} of {r['ts'][:10]} has not landed anywhere durable: "
                    f"{r['text'][:180]}",
                    r.get("context") or
                    "record it in a leaf so a later session finds it",
                    target_kind="opaque")
    if skipped_d:
        ctx.note("4", f"{skipped_d} decision/disagreement proposal(s) suppressed "
                      f"-- already decided, within the {ledger.OPAQUE_TTL_DAYS}-day "
                      f"window (`familiar consolidation dismiss`)")


def _new_leaf_frontmatter(ctx, p, supersedes: str = "") -> str:
    """The shared leaf contract for a leaf the pass is proposing into existence.

    `trust: trial` and `origin: derived` are not defaults chosen for
    convenience: this text was written by a model from journal entries, and
    knowledge-vs-skills.md reserves `trusted` for a human's promotion.
    `last_verified` is deliberately EMPTY -- nothing has checked this against
    the world yet, and memory-ranking.md is explicit that a fake date here would
    be indistinguishable from a real one six months later. Empty means the leaf
    is flagged never-verified and exempt from pruning, which is the truth.

    `supersedes:` is filled only for a `supersede-leaf` proposal, where the
    model named the leaf it replaces. It is the one frontmatter value here that
    is a CLAIM rather than a mechanical fact, which is why the module never
    writes it speculatively: an empty `supersedes:` says "nothing", and a wrong
    one silently deprecates a live leaf (see the L4 conflict module, which reads
    this field and is the reason it has to be right).
    """
    title = p["summary"].strip().rstrip(".")
    srcs = ", ".join(sorted(
        f"journal/{q.relative_to(ctx.agents / 'journal').as_posix()}"
        for q, _ in _recent(ctx))[:3])
    return (
        "---\n"
        f"title: {title}\n"
        "origin: derived           # distilled by the consolidation pass\n"
        "authority: agent\n"
        "trust: trial              # a model wrote this; `trusted` is a human's call\n"
        "last_verified:            # EMPTY on purpose — nothing has checked it yet\n"
        "verified_log: []\n"
        "use_count: 0\n"
        "last_used:\n"
        f"promoted_from: [{srcs}]\n"
        "source:\n"
        f"supersedes: {frontmatter.fmt_list([supersedes]) if supersedes else ''}\n"
        "superseded_by:\n"
        "contradicts: []\n"
        "related: []\n"
        "tags: []\n"
        'scope: ["06_SYSTEM/**"]\n'
        "area: [B]\n"
        "stability: evolving\n"
        "---\n")
