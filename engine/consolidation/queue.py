"""queue -- the decision queue: what the pass proposed, as a file the CLI reads.

WHY A FILE AND NOT THE REPORT. The report is prose for a human, rendered once
and dated. `familiar consolidation decide 3` has to resolve *the 3rd thing in tonight's
list*, and the ordinal has to mean the same thing in the report, in `queue` and
in `decide` -- three readers, one list. Parsing it back out of Markdown would
make the report the database, and reformatting the report (which this track
does, item 1e) would then be a data migration. So the pass writes the list
once, as data, and every reader reads that.

ITEM IDENTITY. `id` is derived from (kind, target), never from the position in
the list and never from the night. That is what makes `nights` a recurrence
count -- an item proposed on twelve consecutive nights carries `nights: 12` --
and it is what stops a dismissal from being re-proposed under a new number
every night. `what` is EXCLUDED from the id on purpose: the model rewords its
one-line summary each night, so hashing it would mint a new item every night
and the recurrence count would never rise above 1.

ORDINALS ARE PER-REPORT. `ordinal` is the band order the report prints, so it
is a *view* of the queue and not part of an item's identity: an item keeps its
`id` while its ordinal moves as other items are resolved. `decide` therefore
resolves through `queue.by_ordinal`, and the hash guard (1d) exists precisely
because a report printed last night has last night's ordinals.

THE HASH. `digest` covers `kind`, `target`, `ordinal` and `resolution` of every
item -- the fields an ordinal-based `decide` depends on. `first_seen` and
`nights` are excluded: they change every night by construction, and a guard
that refuses every evening is a guard that gets bypassed. The report prints the
digest; `decide` compares it and refuses with exit 3 when it has moved.

WHAT IS NOT HERE. The band rule and the recommendations are step 2; `band` and
`recommendation` are carried as null-able fields so the record does not need a
migration when they arrive (the `probabilities`/`confidence` decision in
`../../dev/jev/SPECS.md` §Thresholds). Writing the *resolution* is the
dispatcher's job (`cli.decide`), because one kind must produce one writer --
`dismiss` already owns the leaf/opaque semantics and must keep owning them.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib

QUEUE = "queue.json"

# Bumped when the fields below change shape in a way a reader must notice.
# A reader that does not know the version must refuse rather than guess at
# fields whose meaning has moved -- an undeclared shape is an error, not a
# default, the same rule `invocation` and the stage list follow.
#
# STILL 1 AFTER THE BATCH WORK (`../../dev/jev/SPECS.md` 3a), and the reason is
# stated rather than assumed: `members` and `outliers` were DECLARED in version
# 1 and were empty in every item ever written, so no reader on disk or in this
# repository can have depended on their element shape. 3a gives those elements a
# shape (below) without moving any field a v1 reader reads. A bump would have
# been the more expensive answer, not the safer one: it makes every existing
# `queue.json` refuse to load, which discards the standing queue and its
# resolutions to protect a reader that does not exist.
VERSION = 1

# How many members a batch row names before it says "and N more". A sample is
# what makes a 233-member row readable at all; the rest is reached with
# `decide N --why`, which prints the population.
SAMPLE = 3


@dataclasses.dataclass
class Item:
    """One proposal as the queue stores it.

    `members` is the batch: the artefacts a single proposal covers when it was
    raised over N of them. `outliers` are the low-confidence members, lifted out
    as their own numbered items rather than left to hide inside the batch --
    that is the property the whole surface rests on (`SPECS.md` §Item shape).

    THE ELEMENT SHAPES, declared here because two modules write them (3a).

      `members[i]` is `{"ref": str, "summary": str}` as a stage raises it --
      `ref` being what the member IS (a path, a leaf name), `summary` a row's
      worth of it. `stages/recommend.py` then adds the answer per member:
      `choice`, `probability`, `confidence`, `band`. Nothing else may be added
      without a reader being told, which is what the version is for.

      `outliers[i]` is the ID of a queue item -- never a member dict. That is
      the whole point: an outlier is a SEPARATE NUMBERED ITEM the user can
      reach with `decide N`, and this list is the batch's pointer to it rather
      than a second place the artefact lives. A list of dicts here would be the
      hidden field `SPECS.md` §Item shape rules out.
    """
    id: str
    kind: str
    target: str
    summary: str            # the one-line `what`, for a row
    first_seen: str         # ISO date this id first appeared
    nights: int = 1         # recurrence count, computed in code
    members: list = dataclasses.field(default_factory=list)
    outliers: list = dataclasses.field(default_factory=list)
    band: dict | None = None            # step 2; null until then
    recommendation: dict | None = None  # step 2; null until then
    resolution: dict | None = None      # set by `decide`
    target_kind: str = "leaf"           # what `target` names (ledger.TARGET_KINDS)
    why: str = ""                       # the reason, for `?` in the walk
    stage: str = ""                     # which stage raised it

    def row(self, ordinal: int) -> str:
        """One report/`queue` line. No command strings -- item 1e.

        The reader copies nothing from here: `decide N` is the whole interface,
        and a printed `dismiss --target=... --kind=...` string is both a second
        writer and a chance to get `target_kind` wrong by hand.
        """
        handle = self.kind.replace(" ", "-")
        line = f"  {ordinal}  {handle}  {self.target} · {self.summary}"
        if self.nights > 1:
            line += f"  (night {self.nights})"
        if self.members:
            # THE COUNT AND THE SAMPLE, on the row itself (3a's exit). A batch
            # that printed only `[233 members]` would be a number the reader
            # cannot judge; three named members are what turn it into something
            # they can agree or disagree with at a glance.
            line += f"  [{len(self.members)} members: {sample_text(self.members)}]"
        if self.outliers:
            line += f"  [{len(self.outliers)} outlier(s), numbered separately]"
        return line


def sample(members: list, n: int = SAMPLE) -> list:
    """Up to `n` members to show on a row, one per answer where there is one.

    DERIVED, NEVER STORED. A `sample` field on `Item` would be a second copy of
    something `members` already determines, and it would have to move with the
    version; deriving it costs nothing and cannot drift from the population it
    claims to represent.

    STRATIFIED BY THE ANSWER once there is one: three members that all landed on
    the same subject say less about a labelling run than three that landed on
    three, and the reader is judging the RUN, not the first three files in it.
    Before banding there is no answer to stratify on and this is the first `n`,
    in the order the stage raised them.
    """
    out, seen = [], set()
    for m in members:
        key = m.get("choice") if isinstance(m, dict) else None
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        out.append(m)
        if len(out) >= n:
            return out
    # Fewer distinct answers than `n`: fill from the head rather than show a
    # shorter sample, because a one-member sample of a 233-member batch reads
    # as a one-member batch.
    for m in members:
        if len(out) >= n:
            break
        if m not in out:
            out.append(m)
    return out


def member_text(m) -> str:
    """One member as a row fragment: what it is, and what was answered about it."""
    if not isinstance(m, dict):
        return str(m)
    ref = m.get("ref", "?")
    if m.get("choice") is None:
        return ref
    p = m.get("probability")
    return f"{ref}→{m['choice']}" + (f" {p:.2f}" if isinstance(p, float) else "")


def sample_text(members: list, n: int = SAMPLE) -> str:
    shown = sample(members, n)
    text = ", ".join(member_text(m) for m in shown)
    rest = len(members) - len(shown)
    return text + (f", +{rest} more" if rest > 0 else "")


def _id(kind: str, target: str) -> str:
    """Stable across nights: (kind, target) only. See the module docstring --
    adding `what` here would mint a new item nightly and break `nights`."""
    return "q-" + hashlib.sha256(f"{kind}\0{target}".encode()).hexdigest()[:12]


def digest(items: list) -> str:
    """The short hash the report prints and `decide` checks (item 1d).

    Covers what an ordinal-based `decide` reads. Deliberately excludes
    `first_seen`/`nights`: those move nightly, so including them would refuse
    every `decide` run the morning after a report.
    """
    h = hashlib.sha256()
    for i, it in enumerate(items, 1):
        h.update(f"{it.get('id')}\0{it.get('kind')}\0{it.get('target')}\0"
                 f"{i}\0{json.dumps(it.get('resolution'), sort_keys=True)}\n".encode())
    return h.hexdigest()[:12]


def path(base) -> pathlib.Path:
    return pathlib.Path(base) / QUEUE


def load(base) -> dict:
    """Read the queue. An absent file is an empty queue, not an error.

    A queue that will not parse or whose version is unknown raises: a reader
    that silently treats a corrupt queue as empty would renumber every item and
    resolve the wrong thing.
    """
    p = path(base)
    try:
        text = p.read_text()
    except OSError:
        return {"version": VERSION, "digest": digest([]), "items": []}
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"{p} is not valid JSON: {exc}") from None
    got = data.get("version")
    if got != VERSION:
        raise ValueError(f"{p} is version {got!r}, this reader knows {VERSION}")
    data.setdefault("items", [])
    return data


def items(base) -> list:
    return load(base)["items"]


def save(base, items_: list) -> pathlib.Path:
    """Write the queue and its digest. The pass's only write to this file."""
    p = path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": VERSION, "digest": digest(items_), "items": items_}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                            sort_keys=False) + "\n")
    return p


def as_dict(kind, target, what, why, stage, target_kind,
            first_seen, nights=1, members=(), outliers=()) -> dict:
    return {
        "id": _id(kind, target), "kind": kind, "target": target,
        "target_kind": target_kind, "summary": what, "why": why, "stage": stage,
        "first_seen": first_seen, "nights": nights,
        "members": list(members), "outliers": list(outliers),
        "band": None, "recommendation": None, "resolution": None,
    }


def merge(previous: list, fresh: list, today: str) -> list:
    """Fold tonight's proposals into the standing queue.

    `nights` is computed here rather than carried by the caller: an item whose
    stable id is already present has been proposed before, so its count rises
    and its `first_seen` is KEPT (the first night it was raised, not tonight).
    Everything else about the item is replaced by tonight's version -- the
    summary is the model's latest wording.

    A RESOLVED ITEM IS NOT RE-RAISED. If tonight's pass proposes again what a
    `decide` already resolved, carrying the resolution forward is what stops the
    queue from forgetting the user's answer. The dismissal ledger is the real
    suppression mechanism (a resolved leaf proposal stops being *generated* once
    dismissed); this is the queue's own memory for the window before the pass
    next runs.

    AN OUTLIER SURVIVES ITS BATCH'S REBUILD, and it has to be said here because
    nothing else could say it. An outlier is minted by `stages/recommend.py`
    from a member's BAND -- so the stage that raises the batch cannot re-raise
    it, and it is never in `fresh`. Dropping it would silently un-number an item
    the user is holding an ordinal for, and take its resolution with it. So a
    previous item named in a surviving batch's `outliers` is carried forward
    whole. It leaves for exactly one reason: the batch that named it is gone.
    """
    was = {p["id"]: p for p in previous}
    out = []
    for f in fresh:
        old = was.get(f["id"])
        if old:
            f["first_seen"] = old.get("first_seen") or today
            f["nights"] = int(old.get("nights", 1)) + 1
            # THE USER'S ANSWER IS CARRIED FORWARD, and so is a recommendation
            # already computed for this id. Losing either would make the queue
            # forget something it had -- and for a resolution that means
            # re-asking a question already settled.
            if old.get("resolution"):
                f["resolution"] = old["resolution"]
            # `band`/`recommendation` are recomputed each cycle when `--with-jev`
            # is passed, so this carries LAST cycle's numbers when it is not.
            # That is the honest behaviour: an old recommendation, labelled with
            # its own `model` and `schema_hash`, is better than a blank that
            # reads as "nothing was judged" when something was.
            if old.get("recommendation"):
                f["recommendation"] = old["recommendation"]
                f["band"] = old.get("band")
            # The BATCH's answers are carried on the same terms and for the same
            # reason. A stage re-raises a batch's population every night but
            # never its per-member answers -- those are `recommend`'s -- so a
            # night without `--with-jev` would otherwise turn a labelled batch
            # back into an unlabelled one and strand its outliers, which
            # `_kept_outliers` reads this list to prevent.
            if not f.get("members") and old.get("members"):
                f["members"] = old["members"]
            elif old.get("members") and old.get("outliers"):
                f["members"] = _relabel(f["members"], old["members"])
            if not f.get("outliers") and old.get("outliers"):
                f["outliers"] = old["outliers"]
        else:
            f["first_seen"] = today
            f["nights"] = 1
        out.append(f)
    out.extend(_kept_outliers(previous, out))
    return out


def _kept_outliers(previous: list, merged: list) -> list:
    """Previous items a surviving batch still names, in their original order.

    Read from `merged` rather than from `fresh`: `merge` has just carried last
    cycle's `outliers` onto tonight's batch item, and that carried list is the
    one that says which items are still claimed.
    """
    have = {i.get("id") for i in merged}
    claimed = {oid for i in merged for oid in (i.get("outliers") or [])}
    return [p for p in previous
            if p.get("id") in claimed and p.get("id") not in have]


def _relabel(fresh_members: list, old_members: list) -> list:
    """Tonight's population, carrying last cycle's answer where the ref matches.

    The population is the stage's to compute and the answers are `recommend`'s;
    this is the one place they meet. A member that is new tonight carries no
    answer, which is correct -- it has not been asked yet.
    """
    was = {m.get("ref"): m for m in old_members if isinstance(m, dict)}
    out = []
    for m in fresh_members:
        old = was.get(m.get("ref")) if isinstance(m, dict) else None
        out.append({**old, **m} if old else m)
    return out


def by_ordinal(items_: list, n: int) -> dict | None:
    """The nth item, 1-based, in the order the report numbered them."""
    if 1 <= n <= len(items_):
        return items_[n - 1]
    return None


def of_kind(items_: list, kind: str) -> list:
    """Unresolved items of one kind, in ordinal order -- `decide --kind=K --all`.

    THE HYPHENATED HANDLE IS ACCEPTED, and that is not a convenience. The report
    renders a kind with spaces as a hyphenated handle (`knowledge→skill link` ->
    `knowledge→skill-link`) because the columns must not shift; a user reading
    that handle and typing it back would otherwise match NOTHING, silently. A
    printed spelling that its own command rejects is worse than no handle.
    Both forms are matched; the stored kind is never rewritten, because a kind is
    an identity and `(kind, target)` is the item's id.
    """
    want = {kind, kind.replace("-", " ")}
    return [it for it in items_
            if it.get("kind") in want and not it.get("resolution")]


def unresolved(items_: list) -> list:
    return [it for it in items_ if not it.get("resolution")]


def resolve(base, item_id: str, resolution: dict) -> int:
    """Stamp one item resolved, in place, preserving order and ordinals.

    One item, one record: the caller has already appended the kind's own line to
    its own ledger. Returns how many items carried that id (0 means the items
    moved under the caller, and `decide` treats that as a staleness refusal).

    A resolution row is never *removed* -- the item stays in the list, resolved,
    so that the ordinal a user saw last night still names the same thing
    tonight. Reordering or dropping resolved items would silently renumber the
    list under a report the user is still reading.
    """
    data = load(base)
    n = 0
    for it in data["items"]:
        if it.get("id") == item_id:
            it["resolution"] = resolution
            n += 1
    if n:
        save(base, data["items"])
    return n


def raise_ordinal_error(n: int, total: int) -> str:
    return f"no item {n} — the queue holds {total} item(s)"
