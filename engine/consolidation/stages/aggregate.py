"""Stage 2 -- Aggregate. Reads -> `use_count`, `last_used`.

MECHANICAL, and the only stage that writes frontmatter it did not compute from
the tree. It qualifies as mechanical under M2 decision 2 because the numbers are
COUNTED OFF RECORDS, not scored: nothing here depends on an unvalidated constant.

ONE USE = ONE SESSION THAT READ THE DOCUMENT (dev/memory/SPECS.md M2a, decided
2026-10-09). Two sources, keyed by session so neither double-counts the other:

  * the staged transcripts (`pointers.reads`): every session whose `read` or
    `bash` calls named a skill's `SKILL.md` or a knowledge leaf. This is how
    skills are actually used here -- read through the router -- and the only
    signal knowledge leaves have at all.
  * `skill-usage.jsonl`: Claude Code's `Skill` invocations. It held 2 lines in
    six weeks, because the library is not installed as harness skills; kept
    because an invocation is still a use, and costs nothing to fold in.

`use_count` is RECOMPUTED from both sources every pass, never incremented.
Incrementing turns it into a stored counter that drifts when a pass runs twice
or dies halfway; recomputing makes the stage idempotent by construction, which
is the same argument memory-ranking.md makes for deriving F from `last_verified`
rather than storing it.

HONEST LIMITS, carried into the report. `use_count` is biased both ways, so it
may PROPOSE demotion and may never delete:
  * LOW: a read the human makes is invisible, hermes staging drops tool
    arguments, and a transcript is only on disk once its session was staged.
  * HIGH: a session that reads a document in order to maintain it counts as a
    use -- the 2026-10 restructure read most of the tree.
A path from before a move resolves by name (a leaf's stem, a skill's folder),
so reads survive renames of the folders above a document, not of the document.
"""
from __future__ import annotations

import pathlib

from context import pointers
from knowledge import frontmatter
from consolidation import ledger
from lib import roots

# Verification history, added in M2 (memory-ranking.md Sec.Stability migration:
# "This needs verification history, which is not currently kept ... do it when
# M2 is built"). Most recent first; entry 0 mirrors `last_verified` after each
# pass, which is what lets the NEXT pass detect that it changed. Three entries
# because the migration table asks for "unchanged across >=3 verifications".
VERIFIED_LOG_KEY = "verified_log"
VERIFIED_LOG_DEPTH = 3


def _resolver(docs):
    """A function from a repo-relative path to the Doc it names, or None.

    Exact path first; then by name, because the verbatim tier predates every
    move of the tree (`agents/` -> `memory/`, R3a's renamed subject folders) and
    a read of a document's old path is still a read of that document. A name
    shared by two documents of one kind resolves to neither -- an unattributable
    read is dropped rather than guessed.
    """
    by_rel = {d.rel: d for d in docs}
    by_name: dict[tuple, list] = {}
    for d in docs:
        names = {d.name} | ({d.path.parent.name} if d.kind == "skill" else set())
        for n in names:
            by_name.setdefault((d.kind, n), []).append(d)
    prefix = roots.MEMORY_REL + "/"

    def resolve(rel: str):
        if not rel.startswith(prefix):
            return None
        r = rel[len(prefix):]
        if r in by_rel:
            return by_rel[r]
        p = pathlib.PurePosixPath(r)
        if p.name == "SKILL.md" and r.startswith("skills/"):
            key = ("skill", p.parent.name)
        elif r.startswith("knowledge/") and p.suffix == ".md":
            key = ("knowledge", p.stem)
        else:
            return None
        hits = by_name.get(key, [])
        return hits[0] if len(hits) == 1 else None
    return resolve


def uses(ctx, rows, docs) -> tuple[dict, int]:
    """`doc.rel -> {session id: date}`, and how many sessions contributed.

    Keyed by session so a session that both invoked a skill and read its
    `SKILL.md` counts once. A log line with no `session` is its own session:
    it predates nothing that could merge it, and dropping it would lose a use.
    """
    resolve = _resolver(docs)
    by_skill = {}
    for d in docs:
        if d.kind == "skill":
            by_skill.setdefault(d.name, d)
    out: dict[str, dict[str, str]] = {}

    def add(doc, sid, date):
        seen = out.setdefault(doc.rel, {})
        seen[sid] = max(seen.get(sid, ""), date)

    for i, r in enumerate(rows):
        d = by_skill.get(r.get("skill") or "")
        if d is not None:
            add(d, str(r.get("session") or f"log-line-{i}"), (r.get("ts") or "")[:10])
    sessions = pointers.reads(ctx.base / "transcripts")
    contributing = 0
    for sid, (date, paths) in sessions.items():
        hit = {resolve(p) for p in paths} - {None}
        for d in hit:
            add(d, sid, date)
        contributing += bool(hit)
    return out, contributing


def run(ctx) -> bool:
    # Lines written before 2026-08-30 lack signal/caller/terms and are read as
    # they are. Do NOT backfill them with guesses -- an invented signal is
    # indistinguishable from a measured one later, which is the same trap as a
    # faked last_verified.
    usage = ledger.read(ctx.base, ledger.USAGE)
    rows = usage.rows
    if usage.malformed:
        ctx.note("2", f"{usage.malformed} unparseable line(s) in {ledger.USAGE}, "
                      f"skipped", "warn")

    # Invocation counts per skill NAME, for Loop D's adoption proposals below;
    # `use_count` itself comes from `uses()`.
    counts: dict[str, int] = {}
    signals: dict[str, dict[str, int]] = {}
    for r in rows:
        s = r.get("skill")
        if not s:
            continue
        counts[s] = counts.get(s, 0) + 1
        sig = r.get("signal")                      # absent on pre-2026-08-30 lines
        if sig:
            signals.setdefault(s, {})
            signals[s][sig] = signals[s].get(sig, 0) + 1

    tree = ctx.tree()
    known = {d.name for d in tree.skills()}
    used, contributing = uses(ctx, rows, list(tree.all()))
    written = 0
    for d in tree.all():
        updates = {}
        sessions = used.get(d.rel)
        if sessions:
            cur = str(d.get("use_count", "0") or "0").strip()
            if cur != str(len(sessions)):
                updates["use_count"] = len(sessions)
            lu = max(sessions.values())
            if lu and str(d.get("last_used") or "").strip() != lu:
                updates["last_used"] = lu

        # -- verification history ------------------------------------------
        lv = str(d.get("last_verified") or "").strip()
        log = d.get(VERIFIED_LOG_KEY) or []
        if lv and (not log or log[0] != lv):
            updates[VERIFIED_LOG_KEY] = [lv] + [x for x in log if x != lv][:VERIFIED_LOG_DEPTH - 1]

        if not updates:
            continue
        try:
            changed = frontmatter.update(d.path, updates, dry_run=ctx.dry_run)
        except ValueError as exc:
            ctx.note("2", f"{d.rel}: {exc}", "error")
            continue
        if changed:
            written += 1
            ctx.act("2", d.rel, ", ".join(f"{k}={v}" for k, v in updates.items()))
            d.fm.update(updates)

    # Loop D -- a skill invoked but absent from the library has earned a record.
    #
    # EXCEPT a harness built-in. `signal: external` means our routers did not
    # select it; it is the harness's own skill, works without adoption, and
    # will never be vendored. Proposing it every night is a false positive that
    # trains the reader to skim the section that matters most.
    #
    # Pre-2026-08-30 log lines have no `signal`, so the classification is
    # unavailable rather than negative -- those are listed separately as
    # unclassifiable, not silently dropped.
    if written:
        # This stage wrote the frontmatter R is derived from. Re-score, or every
        # later stage reads the tree as it was BEFORE tonight's usage landed.
        tree.rescore()

    # Read once, then ask per candidate: a rejected "no, don't adopt X" must
    # not be re-proposed every night while X is still invoked but unadopted.
    dismissed = ledger.dismissals(ctx.base)
    unknown = sorted(s for s in counts if s not in known)
    skipped_d = 0
    for s in unknown:
        sigs = signals.get(s, {})
        if sigs.get("external"):
            continue                       # harness built-in, not ours to adopt
        if not sigs:
            ctx.note("2", f"`{s}` was invoked {counts[s]}x and is not in the "
                          f"library, but its log line(s) predate the `signal` "
                          f"field, so whether it is a harness built-in cannot be "
                          f"told. Not proposed for adoption on that basis.")
            continue
        if dismissed.covers(ctx.repo, s, "adopt", target_kind="opaque"):
            skipped_d += 1
            continue
        ctx.propose("2", "adopt", s,
                    f"invoked {counts[s]}x but has no record in skills/",
                    "adopt-on-first-use (memory-mechanisms.md Loop D)",
                    target_kind="opaque")
    if skipped_d:
        ctx.note("2", f"{skipped_d} adoption proposal(s) suppressed -- already "
                      f"decided, within the {ledger.OPAQUE_TTL_DAYS}-day window "
                      f"(`familiar consolidation dismiss`)")

    ctx.note("2", f"`use_count` = sessions that read the document: "
                  f"{contributing} staged session(s) read {len(used)} "
                  f"document(s); {len(rows)} skill-invocation line(s) folded in. "
                  f"Biased both ways -- maintenance reads count, human reads "
                  f"and hermes sessions do not -- so it may propose, never "
                  f"delete")
    nosig = sum(1 for r in rows if not r.get("signal"))
    if nosig:
        ctx.note("2", f"{nosig} line(s) predate the signal/caller/terms fields "
                      f"(2026-08-30) and were counted but not classified")
    ctx.log(f"{written} document(s) updated, {len(unknown)} adoption candidate(s)")
    return True
