"""recommend -- ask Jev about the queue, store the bands. Stage 8b.

WHERE THIS SITS, AND WHY IT IS LAST. It needs `ctx.proposals`, which stage 4/5/6
produce, and it must run BEFORE the report renders so the report can show the
bands and their order (2h: recommendations are displayed while the ordering
stays put for one cycle). So it runs after the stages and before `report.write`
-- beside `posture.run`, which is there for the same reason.

WHY IT IS GATED, AND WHY THAT GATE IS UNLIKE THE OTHERS. A pass spends money here
that every other stage does not: a real pass must opt in with `--with-jev`, and a
DRY RUN NEVER CALLS at all. The reason is not caution about the model -- it is that
a nightly job which starts billing on an upgrade is a job that gets switched off
the first time someone reads the invoice. One flag makes the spend deliberate.

The dry-run rule differs from stage 1's on purpose. `replay` accepts
`--dry-run --with-model` because a distillation has a PARSE worth exercising and
the entry is reported rather than written. A recommendation has no such half: its
only product is the band written into the queue, and a dry run writes nothing. So
the answer would be paid for and dropped, and the stub tests exercise that path
for free.

WHAT IT WRITES. `queue.json`'s `recommendation` per item, and one line per item to
`decisions.jsonl`? NO -- the decision ledger stays the user's. A recommendation is
not a decision, and writing one there would make `decide`'s record say the user
resolved something they never saw. The recommendation goes in the queue and in the
report, and `decide` is what appends to the ledger when a person acts.

WHAT IT DOES NOT DO (2h). It reorders NOTHING yet. The bands are computed and
displayed; `queue` and the report sort by them only after a report cycle has run
with the numbers visible. This is the same report-only discipline M2 used for the
ranking constants, and for the same reason: a scoring-derived proposal that starts
steering on unvalidated constants fails silently.

BATCHING: ONE CALL PER ARTEFACT, AND THE DOCSTRING THAT SAID OTHERWISE WAS
WRONG. This paragraph used to claim the module sends `one request whose state
carries every item`, and the loop below has always sent one request per item.
The code was right and the prose was wrong; corrected here rather than in the
loop, because 3a is where the difference starts to cost money and fixing it the
other way would have cost correctness.

The reason is the MAPPING. `questions` is a map evaluated against ONE `state`,
so N artefacts in one state need N question objects to keep the answers
distinguishable -- and each would have to name its artefact (`which subject is
entry #7?`), which makes N distinct wordings and therefore N distinct
`schema_hash`es. That shatters the calibration population the hash exists to
define (2e), on top of the accuracy loss of a large state and the 32k state
ceiling 233 journal entries would break. A shared question object over a
per-artefact state keeps one hash, one unambiguous answer, and a state the size
of one entry.

WHAT IT COSTS, since it is not amortised: the question object is re-sent with
every call, so a K-criteria choice over N artefacts pays roughly N x (the
question + one state). For 3a's population that is ~233 calls and ~$0.01 at
$0.042/Mtok -- measured and printed per run (2g), and ESTIMATED under
`--dry-run`, which is the one honest thing a dry run can say about a call it is
not going to make.

A BATCH ITEM IS ASKED PER MEMBER, NOT PER ITEM (3a). One queue item carrying N
members is still ONE proposal and ONE resolution, but it is N questions: the
batch's band is meaningless until each member has an answer. `_ask_batch` is
that loop, and `_split_outliers` is what stops the low-confidence ones hiding
inside the count -- they become their own numbered queue items, which is the
property the batch shape is allowed to exist for.
"""
from __future__ import annotations

import json

from harness import bands, jev, jev_schemas
from consolidation import ledger, queue
from lib import roots

# The most members one night will pay for. A cost guard, not a policy: the
# population is bounded by the corpus (233 today) and this sits above it, so a
# healthy run is never truncated -- but a stage that starts raising an unbounded
# population cannot bill for it unnoticed. A truncated run SAYS SO in the report
# and the rest is asked the next night; it never silently reports a partial
# labelling as a complete one.
MAX_MEMBERS_PER_NIGHT = 400

# How much of an artefact's own text goes into a member's state. Smaller than
# `_target_excerpt`'s 4000 because a labelling question is answered from the
# title, the summary and the headings -- the cookbook shape `jev_schemas` states
# -- and paying for the body of 233 entries would buy noise.
MEMBER_EXCERPT = 1200


def _state_for(ctx, item: dict) -> str:
    """The item, as text for Jev. Assembled by code from the item, never the
    whole tree -- `memory/journal/` alone is ~450k tokens (PLAN.md §Size)."""
    bits = [f"kind: {item['kind']}", f"target: {item['target']}"]
    if item.get("target_kind"):
        bits.append(f"target is a: {item['target_kind']}")
    if item.get("summary"):
        bits.append(f"proposal: {item['summary']}")
    if item.get("why"):
        bits.append(f"reason given by the pass: {item['why']}")
    if item.get("nights", 1) > 1:
        bits.append(f"this has recurred on {item['nights']} nights")
    bits.append("")
    bits.append(_target_excerpt(ctx, item))
    return "\n".join(bits)


def _target_excerpt(ctx, item: dict, limit: int = 4000) -> str:
    """The target's own text, so the question is about the artefact and not only
    about the pass's description of it. Absent for an opaque target, which has no
    file -- stated in the state rather than left as a silent empty section."""
    if item.get("target_kind") == "opaque":
        return "(no file: this target is an id, not a leaf)"
    root = ctx.repo / roots.MEMORY_REL
    for name in (item["target"], item["target"] + ".md"):
        p = root / name.lstrip("/")
        try:
            text = p.read_text()
        except OSError:
            continue
        return f"--- {name} ---\n{text[:limit]}"
    return f"(the file {item['target']} does not exist yet)"


def _member_state(ctx, item: dict, member: dict) -> str:
    """One MEMBER as text for Jev -- the artefact, not the batch.

    The batch's own summary is deliberately absent. It says `233 entries carry
    no subject:`, which is true of every member and therefore tells the model
    nothing about the one in front of it; including it would spend tokens on a
    constant and invite the model to answer about the batch.
    """
    bits = [f"kind: {item['kind']}", f"artefact: {member.get('ref', '?')}"]
    if member.get("summary"):
        bits.append(f"title: {member['summary']}")
    bits.append("")
    bits.append(_member_excerpt(ctx, member))
    return "\n".join(bits)


def _member_excerpt(ctx, member: dict, limit: int = MEMBER_EXCERPT) -> str:
    """The member's frontmatter and opening body, read from `memory/`.

    A member's `ref` is a path relative to `memory/` -- the one spelling the
    stage that raised it writes. A ref that resolves to nothing is stated in the
    state rather than left as a silent empty section: the model would otherwise
    answer confidently about nothing.
    """
    ref = str(member.get("ref", ""))
    p = ctx.repo / roots.MEMORY_REL / ref.lstrip("/")
    try:
        text = p.read_text()
    except OSError:
        return f"(the file {ref} could not be read)"
    return f"--- {ref} ---\n{text[:limit]}"


def _estimate_tokens(payloads) -> int:
    """Roughly what a set of requests will cost to send, without sending them.

    ~4 characters per token, over the JSON actually built. It is an ESTIMATE and
    is labelled one wherever it is printed: the tokeniser is the vendor's and
    this machine does not have it. It exists so `run --with-jev --dry-run` can
    show a cost -- a dry run that printed nothing about the spend would let the
    first real run be the first time anyone saw the number.
    """
    return sum(len(json.dumps(p, ensure_ascii=False)) for p in payloads) // 4


def _batch_estimate(ctx, item: dict) -> tuple:
    """`(n_calls, estimated_input_tokens)` for one batch item, unsent."""
    q = jev_schemas.question(item["kind"])
    members = item.get("members") or []
    return (len(members),
            _estimate_tokens([{"state": _member_state(ctx, item, m),
                               "questions": {m.get("ref", "?"): q}}
                              for m in members]))


def _ask_batch(ctx, item: dict, usage: dict) -> tuple:
    """Ask one question per member. Returns `(answered, stopped_fatally)`.

    The answer is written onto the MEMBER, keyed by nothing: one call carries
    one member's state, so the answer that comes back is that member's and there
    is no mapping to get wrong. That is the whole reason for the per-call shape
    (see the module docstring), and it is what `SPECS.md` §Raise rather than
    decide names as the thing not to accept silently.

    A member already carrying a `band` is NOT re-asked. `queue.merge` carries
    last cycle's answers forward, so a nightly rerun pays only for members that
    are new or were skipped -- and the note says how many of each.
    """
    question = jev_schemas.question(item["kind"])
    pending = [m for m in (item.get("members") or []) if not m.get("band")]
    answered = 0
    for m in pending[:MAX_MEMBERS_PER_NIGHT]:
        try:
            out = jev.ask(_member_state(ctx, item, m),
                          {"answer": question})
        except jev.JevError as exc:
            ctx.note("8b", f"Jev skipped member {m.get('ref')} of "
                           f"{item['kind']}: {exc.kind}: {exc}",
                     "error" if exc.fatal else "warn")
            if exc.fatal:
                return answered, True
            continue
        u = out.get("usage", {})
        usage["input_tokens"] += int(u.get("input_tokens", 0))
        usage["output_tokens"] += int(u.get("output_tokens", 0))
        answer = out["answers"].get("answer", {})
        band = bands.of_answer(item["kind"], answer)
        # The envelope, per member. Every answer records what asked it and what
        # answered (2e) -- a member is an answer like any other, and one that
        # carried a label with no `model` or `schema_hash` beside it would be
        # the unversioned confidence scalar this track rejects.
        m.update({"choice": answer.get("choice"),
                  "probability": band["value"],
                  "confidence": answer.get("confidence"),
                  "probabilities": answer.get("probabilities"),
                  "band": band["band"],
                  "schema_hash": jev_schemas.schema_hash(item["kind"]),
                  "model": out.get("model") or jev.MODEL})
        answered += 1
    left = max(0, len(pending) - MAX_MEMBERS_PER_NIGHT)
    if left:
        ctx.note("8b", f"{item['kind']}: {left} member(s) not asked tonight — "
                       f"the per-night cap is {MAX_MEMBERS_PER_NIGHT}. They are "
                       f"asked on the next run; the batch is INCOMPLETE and its "
                       f"count says so.", "warn")
    return answered, False


def _batch_band(kind: str, members: list) -> dict:
    """The BATCH's own band, from its members' bands.

    A batch is one resolution, so it needs one band, and the rule is the
    conservative one: the batch is `accept` only when every member that was
    asked landed `accept`. Anything weaker would let one keystroke apply a label
    the model itself put in `ask` -- the band would then be carrying authority
    over an artefact nobody looked at, which is what `bands.py` says a band is
    never for.

    `drop`-banded members are excluded from the vote: they are leaving the batch
    as their own items (`_split_outliers`), so counting them here would judge
    the batch by artefacts it no longer covers.
    """
    tr = bands.triple(kind)
    triple_d = {"accept_at": tr.accept_at, "drop_below": tr.drop_below}
    asked = [m for m in members if m.get("band") and m["band"] != bands.DROP]
    if not asked:
        return {"band": bands.ASK, "axis": "batch_min", "value": None,
                "triple": triple_d}
    ps = [m["probability"] for m in asked if m.get("probability") is not None]
    every = all(m["band"] == bands.ACCEPT for m in asked)
    return {"band": bands.ACCEPT if every else bands.ASK,
            "axis": "batch_min",
            "value": min(ps) if ps else None,
            "triple": triple_d}


def _split_outliers(ctx, item: dict, items_: list) -> list:
    """Lift the `drop`-banded members out as their own numbered queue items.

    WHAT COUNTS AS AN OUTLIER, stated once. A member banded `drop` -- the model
    put its best option BELOW the drop cut, so there is no defensible subject
    for that entry at all. That is a different question from the batch's, and it
    cannot be answered by the batch's one keystroke, so it gets its own number.
    A member banded `ask` is NOT lifted: `ask` means the proposal stands and
    wants a look, which is exactly what resolving the batch is, and lifting the
    middle band would turn a 233-member batch back into 200 numbered rows -- the
    report the queue replaced.

    Recorded as a judgement, not a measurement: which band earns its own row is
    a consequence question (`PLAN.md` §The record) and 3d's calibration is what
    would revise it. The distribution is printed either way, so a cut that is
    wrong is visible rather than inferred.

    A LIFTED MEMBER STAYS IN `members`. It is not deleted from the population --
    the batch's count is the population it was raised over, and a count that
    shrank as outliers left would report a smaller corpus than exists. What
    changes is that it now also has a row of its own, and `outliers` holds that
    row's ID.
    """
    today = ctx.today.isoformat()
    was = {i.get("id"): i for i in items_}
    new, ids = [], []
    for m in item.get("members") or []:
        if m.get("band") != bands.DROP:
            continue
        d = queue.as_dict(item["kind"], m.get("ref", "?"),
                          f"no defensible subject — best option "
                          f"`{m.get('choice')}` at p {m.get('probability')}",
                          why=(f"lifted out of the {item['target']} batch: its "
                               f"probability fell below the drop cut, so "
                               f"accepting the batch would assert a label the "
                               f"model itself does not stand behind."),
                          stage=item.get("stage", ""), target_kind="opaque",
                          first_seen=today)
        old = was.get(d["id"])
        if old is not None:
            # The user's answer is never lost to a re-split. An outlier resolved
            # last night is the same id tonight, and re-minting it unresolved
            # would re-ask a settled question -- the failure `queue.merge`
            # guards for ordinary items and that this path would otherwise walk
            # straight into.
            ids.append(d["id"])
            continue
        d["band"] = {"band": bands.DROP, "axis": "choice_probability",
                     "value": m.get("probability"),
                     "triple": _batch_band(item["kind"], [])["triple"],
                     "schema_hash": m.get("schema_hash"),
                     "model": m.get("model")}
        d["recommendation"] = {
            "band": bands.DROP, "action": jev_schemas.action(item["kind"]),
            "probability": m.get("probability"),
            "confidence": m.get("confidence"),
            "probabilities": m.get("probabilities"),
            "axis": "choice_probability",
            "schema_hash": m.get("schema_hash"), "model": m.get("model"),
            "threshold": d["band"]["triple"]}
        new.append(d)
        ids.append(d["id"])
    item["outliers"] = ids
    return new


def _open_items(ctx) -> list:
    """The items this run is about -- and a dry run's are not on disk.

    THE SAME RULE `report._queue_rows` APPLIES, and for the same reason. A real
    pass saves the queue before banding (`run.main` states why that order is
    load-bearing), so the file IS tonight's list. A DRY RUN writes no queue, so
    the file still holds LAST night's -- and estimating the spend over last
    night's items answers a question nobody asked. It would also be silently
    wrong in the direction that matters: tonight's batch item is the expensive
    one and is exactly the one missing from yesterday's file.
    """
    if ctx.dry_run:
        from consolidation.run import _fresh  # local: run imports this at module level
        return _fresh(ctx)
    return [i for i in queue.items(ctx.base) if not i.get("resolution")]


def run(ctx) -> bool:
    """Ask, band, store. Returns True when it ran (or was skipped with a note)."""
    items = _open_items(ctx)
    if not items:
        ctx.note("8b", "no open queue items — nothing to ask Jev about")
        return True

    # The gate. See the module docstring on why the spend is deliberate.
    #
    # A DRY RUN NEVER CALLS, flag or no flag -- and this differs from stage 1 on
    # purpose. `replay` accepts `--dry-run --with-model` because a distillation
    # has a PARSE worth exercising and the entry is reported rather than written.
    # A recommendation has no such half: its only product is the band written
    # into the queue, and a dry run writes nothing, so the answer would be paid
    # for and dropped. There is nothing to learn from it that the stub tests
    # cannot show for free.
    if ctx.dry_run:
        # THE COST IS SHOWN EVEN THOUGH NOTHING IS SENT (3a's exit line). The
        # estimate is built from the payloads this run WOULD have posted, so it
        # also proves the questions assemble -- an undeclared kind or a member
        # whose state cannot be built fails here, for free, rather than on the
        # first paid run.
        calls, est = _would_cost(ctx, items)
        ctx.note("8b", f"{len(items)} item(s) would be banded by `{jev.MODEL}` "
                       f"in {calls} call(s), ~{est} input token(s), "
                       f"~${jev.cost_usd({'input_tokens': est}):.6f} "
                       f"(ESTIMATED at ~4 chars/token — the tokeniser is the "
                       f"vendor's). --dry-run makes no call: it costs money and "
                       f"a dry run writes the answer nowhere.")
        return True
    if "--with-jev" not in ctx.flags:
        ctx.note("8b", f"{len(items)} item(s) carry no recommendation; the pass "
                       f"does not call `{jev.MODEL}` unless asked "
                       f"(`run --with-jev`). No cost was incurred.")
        return True

    # Every kind must be asked. An undeclared kind is an error, not a default.
    kinds = sorted({i["kind"] for i in items})
    cov = jev_schemas.coverage(kinds)
    if cov["missing"]:
        ctx.note("8b", f"no question schema for {cov['missing']} — those items "
                       f"get no recommendation. Add a schema in "
                       f"{roots.ENGINE_REL}/harness/jev_schemas.py.", "error")
    askable = [i for i in items if i["kind"] in cov["covered"]]
    if not askable:
        return True

    usage = {"input_tokens": 0, "output_tokens": 0}
    recorded = 0
    minted: list = []
    for item in askable:
        # A BATCH ITEM IS N QUESTIONS, NOT ONE. Its band is computed from its
        # members' and its `drop`-banded members leave as their own numbered
        # items, so it cannot go through the single-answer path below.
        if item.get("members"):
            n, fatal = _ask_batch(ctx, item, usage)
            if n:
                minted += _store_batch(ctx, item)
                recorded += 1
            if fatal:
                break
            continue
        # One call per item: the question is per KIND, so two items of the same
        # kind share it, but the STATE is per item and the answer must not be
        # ambiguous about which item it belongs to.
        try:
            out = jev.ask(_state_for(ctx, item),
                          {item["id"]: jev_schemas.question(item["kind"])})
        except jev.JevError as exc:
            # Never fatal to the pass. A skipped recommendation is a queue with
            # no recommendation, which `queue` and `decide` already handle.
            ctx.note("8b", f"Jev skipped item {item['id']} ({item['kind']}): "
                           f"{exc.kind}: {exc}",
                     "error" if exc.fatal else "warn")
            if exc.fatal:
                break          # a bad key or schema will fail for every item
            continue
        u = out.get("usage", {})
        usage["input_tokens"] += int(u.get("input_tokens", 0))
        usage["output_tokens"] += int(u.get("output_tokens", 0))
        answer = out["answers"].get(item["id"], {})
        band = bands.of_answer(item["kind"], answer)
        _store(ctx, item, band, answer, out.get("model"))
        recorded += 1

    cost = jev.cost_usd(usage)
    ctx.note("8b", f"banded {recorded}/{len(askable)} item(s) with "
                   f"`{jev.MODEL}` — {usage['input_tokens']} in, "
                   f"{usage['output_tokens']} out, ${cost:.6f}. "
                   f"Recommendations are DISPLAYED; ordering is unchanged this "
                   f"cycle (the shadow rule).")
    if minted:
        ctx.note("8b", f"{len(minted)} low-confidence member(s) were lifted out "
                       f"of their batch as their own numbered item(s) — they "
                       f"are decided separately, never inside the count.")
    return True


def _would_cost(ctx, items: list) -> tuple:
    """`(calls, estimated_input_tokens)` for the whole run, unsent.

    Guarded per item rather than for the loop: a kind with no schema must be
    counted as zero and reported by the coverage check below, not take the whole
    estimate down with it. A dry run that raised here would be a dry run that
    could not tell you what the real one costs.
    """
    calls = est = 0
    for it in items:
        try:
            if it.get("members"):
                n, e = _batch_estimate(ctx, it)
            else:
                n, e = 1, _estimate_tokens(
                    [{"state": _state_for(ctx, it),
                      "questions": {it["id"]: jev_schemas.question(it["kind"])}}])
        except (jev_schemas.UndeclaredKind, OSError):
            continue
        calls += n
        est += e
    return calls, est


def _store_batch(ctx, item: dict) -> list:
    """Write one banded batch back, split its outliers, and return the new items.

    The read-modify-write is over the file rather than the in-memory list for
    the same reason `_store` is: `recommend` runs after the queue was saved, and
    the file is what `decide` will read.
    """
    data = queue.load(ctx.base)
    members = item.get("members") or []
    band = _batch_band(item["kind"], members)
    minted = _split_outliers(ctx, item, data["items"])
    dist = {b: sum(1 for m in members if m.get("band") == b)
            for b in bands.BANDS}
    for it in data["items"]:
        if it["id"] != item["id"]:
            continue
        it["members"] = members
        it["outliers"] = item["outliers"]
        it["band"] = dict(band, schema_hash=jev_schemas.schema_hash(item["kind"]),
                          model=_member_model(members))
        it["recommendation"] = {
            "band": band["band"],
            "action": jev_schemas.action(item["kind"]),
            "probability": band["value"],
            # A batch has no single confidence and no single per-option map: it
            # has one per member, and they are on the members. A number here
            # would be an average nobody asked for -- the same invention the
            # `noul` `confidence: null` rule refuses (PLAN.md §The answer shapes).
            "confidence": None,
            "probabilities": None,
            "axis": band["axis"],
            "members": len(members),
            "distribution": dist,
            "schema_hash": jev_schemas.schema_hash(item["kind"]),
            "model": _member_model(members),
            "threshold": band["triple"]}
    data["items"].extend(minted)
    queue.save(ctx.base, data["items"])
    ctx.note("8b", f"{item['kind']}: {len(members)} member(s) — "
                   f"{dist[bands.ACCEPT]} accept, {dist[bands.ASK]} ask, "
                   f"{dist[bands.DROP]} drop. The batch bands "
                   f"`{band['band']}` on its weakest kept member.")
    return minted


def _member_model(members: list) -> str:
    """The model that answered. One resolved id or the pin -- never a guess: if
    two members were answered by different resolutions, the record says so
    rather than picking one and making the envelope a lie."""
    seen = sorted({m["model"] for m in members if m.get("model")})
    return seen[0] if len(seen) == 1 else (", ".join(seen) or jev.MODEL)


def _store(ctx, item: dict, band: dict, answer: dict, resolved_model) -> None:
    """Write one recommendation into the queue. Order and ordinals untouched."""
    data = queue.load(ctx.base)
    for it in data["items"]:
        if it["id"] != item["id"]:
            continue
        it["band"] = {"band": band["band"], "axis": band["axis"],
                      "value": band["value"], "triple": band["triple"],
                      # The validity envelope: what was asked, and what answered.
                      "schema_hash": jev_schemas.schema_hash(item["kind"]),
                      "model": resolved_model or jev.MODEL}
        it["recommendation"] = {
            "band": band["band"],
            "action": jev_schemas.action(item["kind"]),
            "probability": band["value"],
            "confidence": answer.get("confidence"),   # None for a noul
            "probabilities": answer.get("probabilities"),
            "axis": band["axis"],
            "schema_hash": jev_schemas.schema_hash(item["kind"]),
            "model": resolved_model or jev.MODEL,
            "threshold": band["triple"],
        }
    queue.save(ctx.base, data["items"])
