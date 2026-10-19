"""Stage 1 -- Replay. Staged transcripts -> one journal entry each.

APPEND-ONLY. An existing entry is never rewritten (journal rule 1). Idempotent:
a transcript already cited by an entry is skipped, so an interrupted night
resumes instead of duplicating.

WHY IT EXISTS: M1 found 9 leaves whose `promoted_from:` points at sessions that
were never journalled. Every entry this stage writes must therefore resolve as a
`promoted_from:` target -- that dangling-provenance gap is the thing it is here
to stop reopening.

PRIVACY. Transcripts are staged from EVERY working directory, personal Areas
included, and distillation is a CLOUD call. EXCLUDE_CWD below is the one line to
edit; it defaults to excluding the personal Areas rather than including them,
because the failure of guessing wrong is irreversible disclosure. Excluded
transcripts are kept staged and reported, never silently dropped.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

from harness import model
from context import pointers
from context import transcripts
from knowledge import ontology
from lib import roots

# Personal Areas that no cloud model should see the inside of. Areas are not
# expressible as BOUNDARIES.yaml rules today (they are a P.A.Z.R.A.S concept,
# not a path the guard needs to deny), so they are listed here. Everything the
# guard already knows about is derived instead -- see `_excluded_paths`.
EXCLUDE_CWD = (
    "/02_AREAS/E_Connection", "/02_AREAS/G_Embodiment", "/02_AREAS/H_Health",
    "/02_AREAS/I_Mindfulness", "/02_AREAS/N_Finance", "/02_AREAS/P_Home",
    "/02_AREAS/_Deep_Life",
)

BOUNDARIES_JSON = roots.BOUNDARIES_JSON


def _excluded_paths(ctx) -> list[str]:
    """Every path a REMOTE model may not read, derived from BOUNDARIES.yaml.

    Stage 1 is a second disclosure channel the guard cannot see: it does not
    read a protected path, it reads a STAGED TRANSCRIPT of a session that was
    working there, and sends that to a cloud model. Hardcoding a second list
    here would drift from BOUNDARIES.yaml silently -- which is exactly the D1
    failure the compiled-boundaries work exists to prevent. So the rules are
    read from the compiled artifact, and adding one row to BOUNDARIES.yaml
    protects distillation automatically.

    Fails CLOSED: if the compiled file cannot be read, the hardcoded Area list
    still applies and the pass says so rather than assuming everything is fine.
    """
    out = list(EXCLUDE_CWD)
    try:
        data = json.loads(BOUNDARIES_JSON.read_text())
    except (OSError, ValueError) as exc:
        ctx.note("1", f"could not read compiled boundaries ({exc}); cloud "
                      f"exclusion falls back to the personal-Area list alone. "
                      f"Run `{roots.ENGINE_REL}/boundaries/compile.py`.", "warn")
        return out
    for rule in data.get("rules", []):
        if "read" not in rule.get("mode", ""):
            continue
        if rule.get("models") not in ("remote", "all"):
            continue
        for p in rule.get("paths", []):
            for key in ("abs", "real"):
                if p.get(key):
                    out.append(p[key])
    return out


PROMPT = """You are distilling one coding-session transcript into a single \
journal entry for a private engineering knowledge base.

Write the entry as GitHub-flavoured markdown. Output ONLY the entry. Begin with \
exactly two header lines, then the body:

SLUG: <three-to-five-word-kebab-case-slug>
TITLE: <one short declarative sentence>

Then the body, using these sections, omitting any that would be empty:

## What was done
## Decisions taken
## What failed or surprised
## Still open

Rules:
- Record what a future session would otherwise have to re-derive. Facts, \
decisions, exact paths, commands and error strings.
- Be specific and terse. No praise, no summary of the summary, no filler.
- If something failed, say so plainly. Failures are the most valuable content.
- Do not invent anything that is not in the transcript.

Session metadata: cwd={cwd} branch={branch} date={date}

TRANSCRIPT (tool output removed; prose turns only):
---
{body}
---"""


def _cited(agents) -> set[str]:
    """Transcript ids AND session ids already covered by a journal entry.

    Session id matters as well as transcript id: a human may have written the
    entry for a session by hand, before the transcript was ever staged. Matching
    only on transcript id would then append a second, machine-written entry for
    the same session -- duplication in an append-only journal, which nothing
    downstream can clean up.
    """
    out = set()
    for p in (agents / "journal").rglob("*.md"):
        try:
            head = p.read_text()[:4000]
        except OSError:
            continue
        for key in ("transcript", "session"):
            for m in re.finditer(rf"^{key}:\s*(.+)$", head, re.M):
                out.add(m.group(1).strip())
    return out


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return "-".join(s.split("-")[:6]) or "session"


def _touches(path: pathlib.Path) -> tuple[str, ...]:
    """The subjects one transcript's tool calls named, in register order.

    C2 (`ontology SPECS` O5b, `config/knowledge/facets.yaml` `touches`).
    `pointers` decides what a path is spelled like and `ontology.subject_at`
    decides which subject occupies it, so neither rule is restated here -- this
    is the one line where the two meet, and it is deliberately a line.

    EMPTY IS A REAL ANSWER and the common one: a session in an Area, or one that
    only read prose, named no file this system owns. It is also what a
    transcript with no tool inputs looks like, so the caller reports the count
    rather than reading silence as "worked on nothing".
    """
    seen = {s for rel in pointers.touched_paths(path)
            if (s := ontology.subject_at(rel))}
    return tuple(s for s in ontology.SUBJECTS if s in seen)


def run(ctx) -> bool:
    staged = transcripts.staged(ctx.base)
    if not staged:
        ctx.note("1", "no staged transcripts")
        return True

    done = _cited(ctx.agents)
    excluded_paths = _excluded_paths(ctx)
    excluded = excluded_paths
    todo, skipped, excluded_list = [], 0, []
    for p in staged:
        tid = transcripts.transcript_id(p)
        m = transcripts.meta(p)
        if tid in done or (m["session"] and m["session"] in done):
            skipped += 1
            continue
        if any(x in (m["cwd"] or "") for x in excluded):
            excluded_list.append((tid, m["cwd"]))
            continue
        todo.append((p, tid, m))

    if excluded_list:
        ctx.note("1", f"{len(excluded_list)} transcript(s) NOT sent to the cloud model "
                      f"(cwd matches the personal-Area exclude list); kept staged: "
                      + ", ".join(c for _, c in excluded_list), "warn")
    ctx.log(f"{len(staged)} staged · {skipped} already journalled · {len(todo)} to distil")

    if not todo:
        return True

    # `--dry-run --with-model` exercises the model call and the parse; it does
    # NOT relax the dry-run invariant. The distilled entry is reported and
    # dropped -- a dry run leaves the tracked tree byte-identical, proved with
    # `git status` (consolidation-cycle.md). Without the flag, no call is made
    # at all, because a call costs money and a dry run writes nothing.
    if ctx.dry_run and "--with-model" not in ctx.flags:
        ctx.note("1", f"{len(todo)} transcript(s) would be distilled by "
                      f"`{model.MODEL}`; --dry-run makes no model call "
                      f"(it costs money and writes nothing). "
                      + ", ".join(t for _, t, _ in todo))
        return True

    if not model.available():
        ctx.note("1", "pi is not on PATH — cannot distil. Transcripts are "
                      "kept staged; nothing was lost.", "error")
        return True

    no_paths = 0

    for p, tid, m in todo:
        body = transcripts.reduce(p)
        if len(body) < 200:
            ctx.note("1", f"{tid}: too little prose to distil ({len(body)} chars); "
                          f"kept staged")
            continue
        try:
            out = model.ask(PROMPT.format(cwd=m["cwd"], branch=m["branch"],
                                          date=m["date"], body=body))
        except model.ModelError as exc:
            ctx.note("1", f"{tid}: distillation failed ({exc}); transcript kept "
                          f"staged — never prune the source of a consolidation "
                          f"that did not happen", "error")
            continue

        slug, title, text = _parse(out)
        # What the session worked on, written into the record rather than
        # derived into the search index later. The transcript is the only place
        # this is still visible -- `transcripts.reduce` dropped the tool inputs
        # on purpose -- and from here the ENTRY carries it, so pruning the
        # verbatim tier cannot lose it (facets.yaml, `touches`).
        touches = _touches(p)
        date = m["date"] or ctx.today.isoformat()
        try:
            d = dt.date.fromisoformat(date)
        except ValueError:
            d = ctx.today
        dest = ctx.agents / "journal" / f"{d.year:04d}" / f"{d.month:02d}" / \
            f"{d.isoformat()}_{slug}.md"
        if dest.exists():
            dest = dest.with_name(f"{d.isoformat()}_{slug}-{tid[:15]}.md")
        entry = (
            "---\n"
            f"title: {title}\n"
            f"date: {d.isoformat()}\n"
            f"session: {m['session'] or 'unknown'}\n"
            f"cwd: {m['cwd']}\n"
            f"transcript: {tid}\n"
            f"distilled_by: {model.MODEL}\n"
            "tags: []\n"
            + (f"touches: [{', '.join(touches)}]\n" if touches else "")
            + "---\n\n"
            f"{text.strip()}\n\n"
            f"---\n\n*Distilled from the verbatim transcript `{tid}` "
            f"(`~/.local/share/pazras/transcripts/`) by `{model.MODEL}`. "
            f"Machine-written: treat as a pointer to the transcript, not as an "
            f"authored record.*\n")
        # Make a possible duplicate VISIBLE. Idempotency matches on transcript
        # id and session id; an entry written before either was recorded has
        # neither, so the pass cannot see it and writes a twin. That happened on
        # the first real run (2026-08-31): three hand-written entries predating
        # M2 acquired machine twins. The journal is append-only, so a twin
        # cannot be cleaned up afterwards -- the only defence is to say so.
        siblings = [q.name for q in dest.parent.glob(f"{d.isoformat()}_*.md")
                    if q != dest]
        if siblings:
            ctx.note("1", f"{dest.name} may duplicate an existing entry for the "
                          f"same date ({', '.join(siblings)}). Idempotency needs a "
                          f"`session:` or `transcript:` field, which entries "
                          f"written by hand may lack.", "warn")
        rel = dest.relative_to(ctx.agents).as_posix()
        if ctx.dry_run:
            ctx.note("1", f"{tid}: distilled to `{rel}` ({len(entry)} bytes) and "
                          f"DISCARDED — --with-model exercises the model call, it "
                          f"does not license a write. Rerun without --dry-run to "
                          f"keep it.")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(entry)
        ctx.act("1", rel, f"journal entry distilled from {tid}")
        if not touches:
            no_paths += 1

    if no_paths:
        ctx.note("1", f"{no_paths} of {len(todo)} entr(ies) carry no `touches:` — "
                      f"their transcripts named no file this system owns. "
                      f"Expected for a session in an Area; for an opencode or "
                      f"hermes session it is also what a DROPPED tool input "
                      f"looks like (`opencode_extract` and `hermes_extract` keep "
                      f"the tool name and drop the arguments), so the two are "
                      f"not distinguishable from the entry alone.")

    return True


def _parse(out: str):
    slug = title = ""
    lines = out.split("\n")
    body_start = 0
    for i, line in enumerate(lines[:8]):
        # A model that has been asked for `SLUG:` reliably returns it, but
        # sometimes dressed as `## SLUG:` or `**SLUG:**`. Undress the line
        # before matching: an unmatched header is not a small problem, it
        # names the file and titles the entry ("Session"), and leaves the
        # header line sitting in the prose.
        s = line.strip().lstrip("#").strip().replace("**", "").replace("__", "").strip()
        if s.upper().startswith("SLUG:"):
            slug = _slugify(s[5:])
            body_start = i + 1
        elif s.upper().startswith("TITLE:"):
            title = s[6:].strip()
            body_start = i + 1
    text = "\n".join(lines[body_start:]).strip()
    if not title:
        title = "Session"
    if not slug:
        slug = _slugify(title)
    return slug, title, text
