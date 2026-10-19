"""Stage 6b -- the labelling proposal: one `subject:` question per unlabelled
journal entry, raised as ONE batch item (`../../../dev/jev/SPECS.md` 3a).

WHAT THIS STAGE OWNS, AND WHAT IT DOES NOT. It owns the MECHANISM: finding the
population, raising it as one proposal with members, and nothing else. It does
not run the labelling, does not write `subject:` into any entry, and does not
touch the M4 index. Those are `ontology SPECS` O5a/O5b and they are
sequenced after O2 -- a leaf or an entry that moves early breaks O4's ground
truth. So this stage's entire product is a row in the queue.

WHY `tags:` IS THE TRIGGER AND `subject:` IS THE ANSWER. `config/knowledge/
facets.yaml` states it as a rule: `tags` is the CONCEPT layer and is
"deliberately UNCONTROLLED ... An empty `tags:` is not a gap to fill by
machine." So an empty `tags:` is read here only as a SIGNAL that an entry was
never labelled by hand; what gets proposed is `subject:`, the one exclusive
rule-based cut. Proposing tags instead would collapse the concept layer into the
category layer, which is the error the whole schema exists to avoid.

WHY ONE ITEM AND NOT 233. `SPECS.md` §Item shape: one queue item is one
PROPOSAL, possibly over N artefacts. 233 numbered rows for one decision is not a
queue, it is the report the queue replaced. The batch stays honest because the
low-confidence members do not hide in it -- `recommend` lifts them out as their
own numbered items, and that split is the only reason the batch shape is allowed
at all.

WHY IT RE-RAISES A POPULATION EVERY NIGHT. An entry drops out of the population
the moment it carries a `subject:`, so the count falls as the labelling lands
and the item disappears when it reaches zero. Nothing here suppresses: the
resolution the user gives is carried by `queue.merge`, and the ledger is what
stops a refused proposal returning.
"""
from __future__ import annotations

import re

from knowledge import frontmatter
from knowledge.tree import SKIP_NAMES
from lib import roots

# The stage's own label, in the STAGES table's `6` slot. Same device stage 5d
# uses: two generators, one run-table entry, and notes that name which of them
# spoke (`run.py` §STAGES).
STAGE = "6b"

# The kind, and the question `jev_schemas` holds for it. Named once so the stage
# cannot drift from the schema it is asking under -- an undeclared kind is an
# error, and this is the name that must be declared.
KIND = "entry-subject"

# `ledger.TARGET_KINDS` is ("leaf", "opaque") and a journal corpus is neither a
# knowledge leaf nor a file. `opaque` is the honest one: it means "this target is
# an id, not a leaf", which is what `memory/journal` is here, and it keeps the
# dismissal semantics that read the leaf tree away from a target that is not in
# it. An `episode` target kind would be a change to the ledger's own vocabulary,
# which is wider than 3a and is not taken here.
TARGET = roots.rel(roots.JOURNAL)
TARGET_KIND = "opaque"

# `tree.SKIP_NAMES` IMPORTED, NEVER RE-DERIVED -- the same rule `conflict.py`
# and `knowledge_index.py` follow, and the reason `declared_paths.py` gives for
# the one policy entry that covers all of them: a second tuple here would be a
# second answer to "what is not content", and the two would drift. A router
# describes the layer; it is not content in it.

# The reports the pass writes about itself are not episodes, and labelling them
# would put the pass's own output into the corpus that describes the user's work.
SKIP_DIRS = ("reports",)


def population(agents) -> list:
    """Journal entries that carry frontmatter, no `subject:`, and no `tags:`.

    ALL THREE CONDITIONS, and each one excludes a different thing:

      frontmatter  -- an entry with none was never distilled by the pass, so
                      there is no place to put an answer and no title to ask
                      about.
      no `subject:` -- already labelled. The population is what is LEFT, which
                      is what makes the count fall as the labelling lands rather
                      than re-asking a settled question every night.
      no `tags:`    -- the hand-labelled entries are held out. They are 3b's
                      corpus, and a run that had already seen them could not be
                      scored against them.
    """
    root = agents / "journal"
    out = []
    for p in sorted(root.rglob("*.md")):
        if p.name in SKIP_NAMES or set(SKIP_DIRS) & set(p.parts):
            continue
        meta = frontmatter.read(p)
        if not meta or set(meta) == {"_body"}:
            continue
        if _value(meta, "subject") or _value(meta, "tags"):
            continue
        out.append({"ref": p.relative_to(agents).as_posix(),
                    "summary": meta.get("title", "") or p.stem})
    return out


def held_out(agents) -> list:
    """The entries that already carry human tags -- 3b's corpus, never asked.

    Returned by the same walk that builds the population so the two cannot
    disagree about what "already labelled" means. 3b scores against this list;
    `O4c` records that the scoring is an inspection-scored consistency check
    rather than a mechanical one, because a controlled 14-option choice and a
    free folksonomy are not the same measurement.
    """
    root = agents / "journal"
    out = []
    for p in sorted(root.rglob("*.md")):
        if p.name in SKIP_NAMES or set(SKIP_DIRS) & set(p.parts):
            continue
        meta = frontmatter.read(p)
        tags = _value(meta, "tags")
        if meta and tags:
            out.append({"ref": p.relative_to(agents).as_posix(), "tags": tags})
    return out


# How much of the body a labelling state carries. Enough for the opening
# paragraphs that say what a document is ABOUT -- a journal entry's median is
# ~4.2 KB including frontmatter -- and short enough that the state stays a
# description of the item rather than the item.
BODY_CHARS = 1500
HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$", re.M)


def state(path) -> str:
    """One document as a labelling question's `state`: title, summary, section
    headings, and the opening of the body.

    ONE BUILDER, EVERY READER. O5a's labelling and the ontology track's agreement
    runs that test it must ask about the SAME text, or the test measures a
    question the labeller never asks -- which is what O4b did by withholding
    the body (`ontology SPECS` O4d).

    THE PATH IS NEVER IN THE STATE. For a knowledge leaf the folder is the
    answer; for a journal entry it is a date. Neither describes the content.
    """
    meta = frontmatter.read(path)
    body = meta.get("_body") if meta else path.read_text()
    headings = [m.group(2) for m in HEADING.finditer(body)]
    opening = " ".join(body.split())[:BODY_CHARS]
    bits = [f"title: {meta.get('title') or path.stem}"]
    if meta.get("summary"):
        bits.append(f"summary: {meta['summary']}")
    bits += ["", "section headings:"]
    bits += [f"  - {h}" for h in headings] or ["  (none)"]
    bits += ["", "body (opening):", opening]
    return "\n".join(bits)


def _value(meta: dict, key: str):
    """The key's value, with an empty list and an empty string both meaning
    absent. `tags: []` parses to `[]` and `subject:` to `""`; treating either as
    present would empty the population and report it as fully labelled."""
    v = meta.get(key)
    if isinstance(v, list):
        v = [x for x in v if str(x).strip()]
    return v or None


def run(ctx) -> bool:
    entries = population(ctx.agents)
    reserved = held_out(ctx.agents)
    if not entries:
        ctx.note(STAGE, f"every journal entry with frontmatter carries a "
                        f"`subject:` or hand-written `tags:` — nothing to "
                        f"label ({len(reserved)} entry/entries are held out as "
                        f"the hand-tagged corpus).")
        return True

    ctx.log(f"{len(entries)} unlabelled entries, {len(reserved)} held out")
    ctx.propose(
        STAGE, KIND, TARGET,
        f"{len(entries)} journal entr(ies) carry no `subject:` — one "
        f"`{KIND}` question each",
        why=(f"`subject:` is the one exclusive, rule-based cut over the "
             f"subjects in {roots.MEMORY_REL}/ontology/facets.yaml. `tags:` is the "
             f"concept layer and is NOT written by this proposal — an empty "
             f"`tags:` is read only as the signal that an entry was never "
             f"labelled by hand.\n"
             f"{len(reserved)} hand-tagged entr(ies) are held out of the "
             f"population so they stay scoreable as the precision corpus "
             f"(dev/jev/SPECS.md 3b, as amended by ontology SPECS O4c).\n"
             f"Nothing is written by this stage: the labelling RUN and the "
             f"`subject:` writes are ontology SPECS O5a."),
        target_kind=TARGET_KIND, members=entries)
    return True
