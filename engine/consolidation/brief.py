"""brief -- the answers artifact. L5, sleep-time compute; the leaf is
memory/knowledge/system/consolidation/consolidation-cycle.md.

WHAT THIS IS. The nightly pass already reads every transcript, scores every
leaf and decides every proposal. Until now the only thing it emitted for an
AGENT was `journal/` -- episodic prose a later session has to search, read and
re-derive an answer from. The brief is the other half: the three questions a
session opens with, answered ahead of time, at a fixed path, in one read.

    What changed?   commits, journal entries and leaves since the last pass
    What's open?    proposals, unlanded decisions, and what sessions left open
    What failed?    this pass's warnings, and what sessions recorded as failing

*Lit:* Sleep-time Compute (arXiv 2504.13171) -- offline pre-computation over a
shared context is ~5x cheaper at test time and the benefit tracks QUERY
PREDICTABILITY. These three are the most predictable queries this system has:
"what did the nightly pass do?" is the question that died on 2026-09-07.

NO MODEL WRITES THIS FILE, and that is a deliberate departure from the ROADMAP
line that put the job in stage 4. All three answers are mechanical -- git, the
ledgers, and the pass's own record of itself -- so a model could only paraphrase
facts that are already exact, at the cost of the two failure modes ACE (arXiv
2510.04618) names, and of adding one more unreviewed LLM artifact to the set a
future prompt reads (memory/knowledge/system/consolidation/memory-poisoning-posture.md).
The sleep-time-compute saving is kept where it is real: stage 1 has ALREADY paid
a model call per transcript, and its `## Still open` / `## What failed or
surprised` sections are answers nobody has indexed. The brief harvests those,
verbatim, as `path:line` pointers -- never re-summarised.

POINTERS, NOT COPIES, for the same reason `journal_search` returns them (L1):
the brief is regenerated nightly and can be stale by a day; the file it cites
cannot. A line here is a claim about where to look, and the reader follows it.

THE STABLE PATH IS THE FEATURE. `BRIEF.md`, overwritten every pass, never
dated: a session asking "what is the state of things" must not first have to
work out which night's file is current. The dated reports remain the human's
per-night record; git history is the brief's.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re

from lib import git
from consolidation.stages import preflight
from lib import roots

NAME = "BRIEF.md"
HIGHLIGHTS = "HIGHLIGHTS.md"

# Screen budget, per section. The brief has exactly one job -- answer three
# questions in one read -- and a 200-line answer is a search result with extra
# steps. Overflow says how much was cut and where the full list lives.
MAX_LISTED = 10

# How far back to harvest journal sections when there is no previous-pass
# anchor at all (first run, or an unreadable state file). Matches
# consolidate.RECENT_DAYS: the same window stage 4 already calls "recent".
FALLBACK_DAYS = 14

# The stage-1 prompt's own section headings (stages/replay.py §PROMPT). Harvest
# targets, not a guess: if that prompt's sections change, these must change with
# it, and `_harvest` reporting zero rows across every entry is the symptom.
OPEN_HEADING = "## Still open"
FAILED_HEADING = "## What failed or surprised"

_BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")
_JOURNAL_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_")

# A harvested bullet is rejoined across the lines it wraps onto, up to this
# many characters. Journal prose is hard-wrapped, so matching only the first
# physical line ends the quote mid-sentence -- which reads as a claim the entry
# did not make, and the pointer beside it then looks wrong rather than terse.
BULLET_CHARS = 240


class Harvested:
    """One bullet lifted from a journal entry, with where it came from."""

    __slots__ = ("text", "rel", "line")
    # Not frozen: `_harvest` appends the lines a hard-wrapped bullet continues
    # onto as it reads them.

    def __init__(self, text: str, rel: str, line: int):
        self.text = text
        self.rel = rel
        self.line = line

    def render(self) -> str:
        return f"- {self.text} — `{self.rel}:{self.line}`"


def _entry_date(path: pathlib.Path) -> dt.date | None:
    m = _JOURNAL_DATE.match(path.name)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _harvest(agents: pathlib.Path, since: dt.date,
             heading: str) -> list[Harvested]:
    """Every bullet under `heading` in journal entries dated on or after `since`.

    Verbatim and line-numbered. The bullet is already a model's output -- it was
    written by stage 1 -- so it is quoted and attributed, never rewritten: a
    second pass over it would be exactly the re-summarisation this module exists
    not to do.

    Entries are selected by FILENAME DATE, which is the journal's layout
    contract (`meta/journal-index.md`) and the same fallback stage 1 uses when
    `date:` is absent -- 4 of the 5 pre-M2 entries had no `date:` field.
    """
    out: list[Harvested] = []
    root = agents / "journal"
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.md"), reverse=True):
        if "reports" in path.relative_to(root).parts:
            continue
        day = _entry_date(path)
        if day is None or day < since:
            continue
        try:
            lines = path.read_text().split("\n")
        except OSError:
            continue
        rel = path.relative_to(agents.parent).as_posix()
        inside = False
        cur: Harvested | None = None
        for n, line in enumerate(lines, 1):
            if line.startswith("## "):
                inside = line.strip() == heading
                cur = None
                continue
            if not inside:
                continue
            m = _BULLET.match(line)
            if m:
                cur = Harvested(m.group(1), rel, n)
                out.append(cur)
            elif cur is not None and line.strip():
                # A continuation of the bullet above: journal prose is
                # hard-wrapped, and half a sentence is a misquote.
                if len(cur.text) < BULLET_CHARS:
                    cur.text = f"{cur.text} {line.strip()}"
            else:
                cur = None          # a blank line ends the bullet
        for h in out:
            if len(h.text) > BULLET_CHARS:
                h.text = h.text[:BULLET_CHARS].rstrip() + "…"
    return out


def _section(title: str, question: str, lines: list[str],
             empty: str) -> list[str]:
    """Frame an ALREADY-BUDGETED list of lines.

    It does not truncate. Each builder below answers one question out of two or
    three sub-lists and applies `MAX_LISTED` to each, so a second cut here would
    silently drop whichever sub-list came last -- which it did: a full proposal
    list pushed every harvested `## Still open` bullet off the end of the brief,
    and the section rendered as though the sessions had left nothing open.
    """
    L = [f"## {title}", "", f"*{question}*", ""]
    if not lines:
        return L + [empty, ""]
    return L + lines + [""]


def _capped(lines: list[str], more_at: str = "") -> list[str]:
    """One sub-list, cut to the screen budget, saying how much was cut."""
    if len(lines) <= MAX_LISTED:
        return lines
    tail = f" — {more_at}" if more_at else ""
    return lines[:MAX_LISTED] + [
        f"- *… and {len(lines) - MAX_LISTED} more{tail}*"]


# ── the three answers ────────────────────────────────────────────────────────

def _changed(ctx, anchor: dict) -> tuple[list[str], str]:
    """Commits, journal entries and leaves since the last completed pass."""
    rev, prev_date = anchor.get("head", ""), anchor.get("date", "")
    # An anchor git cannot resolve is a LOST anchor, not an empty range: after a
    # rebase, a reset or a fresh clone, reporting "nothing changed" for a week of
    # work is the one wrong answer. Demote to the date and say the range is
    # weaker, rather than reporting a confident emptiness.
    if rev and not git.run(ctx.repo, "rev-parse", "--verify",
                           f"{rev}^{{commit}}").ok:
        rev = ""
    commits = git.commits_since(ctx.repo, rev=rev, since_date=prev_date)

    if rev:
        scope = f"since the last pass ({prev_date or '?'}), `{rev}..HEAD`"
    elif prev_date:
        scope = f"since {prev_date} (no revision anchor — date range)"
    else:
        scope = "no previous pass on record — this is the first brief"

    lines = [f"- `{c.sha}` {c.date} — {c.subject}" for c in commits]

    entries, leaves = set(), set()
    for c in commits:
        for p in c.paths:
            if p.startswith(roots.rel(roots.JOURNAL) + "/") and not p.startswith(
                    roots.rel(roots.JOURNAL) + "/reports/"):
                entries.add(p)
            elif p.startswith(roots.rel(roots.KNOWLEDGE) + "/") and p.endswith(".md"):
                leaves.add(p)
    tail = []
    if entries:
        tail.append(f"- **{len(entries)} journal entr{'y' if len(entries) == 1 else 'ies'}**: "
                    + ", ".join(f"`{p}`" for p in sorted(entries)[:6])
                    + (" …" if len(entries) > 6 else ""))
    if leaves:
        tail.append(f"- **{len(leaves)} knowledge leaf/leaves touched**: "
                    + ", ".join(f"`{p.rsplit('/', 1)[-1]}`" for p in sorted(leaves)[:8])
                    + (" …" if len(leaves) > 8 else ""))
    acts = [f"- *(this pass, stage {a.stage})* `{a.target}` — {a.what}"
            for a in ctx.actions]
    return _capped(lines) + tail + _capped(acts), scope


def _open(ctx, anchor: dict) -> list[str]:
    """Proposals awaiting a decision, decisions not yet landed, sessions' own
    open items."""
    L = _capped([f"- **{p.kind}** `{p.target}` — {p.what}"
                 for p in ctx.proposals], "`familiar consolidation report --full`")
    since = _since(anchor, ctx.today)
    harvest = _harvest(ctx.agents, since, OPEN_HEADING)
    if harvest:
        L += ["", "**Left open by recent sessions** (verbatim):"]
        L += _capped([h.render() for h in harvest],
                     f"`{roots.MEMORY_REL}/journal/` since {since.isoformat()}")
    return L


def _failed(ctx, anchor: dict) -> list[str]:
    L = []
    if ctx.aborted:
        L.append(f"- **pass aborted at preflight** — {ctx.aborted.splitlines()[0]}")
    for n in ctx.notes:
        if n.level in ("warn", "error"):
            L.append(f"- **{n.level}** *(stage {n.stage})* — {n.text.splitlines()[0]}")
    expected = {sid for sid, _, _ in _expected_stages()}
    ran = {s.split(" ", 1)[0] for s in ctx.stages_run}
    missing = sorted(expected - ran)
    if missing and not ctx.aborted:
        L.append(f"- **stage(s) that did not run**: {', '.join(missing)} "
                 f"(raised, or excluded by `--stages`)")
    L = _capped(L)
    since = _since(anchor, ctx.today)
    harvest = _harvest(ctx.agents, since, FAILED_HEADING)
    if harvest:
        L += ["", "**Recorded as failing by recent sessions** (verbatim):"]
        L += _capped([h.render() for h in harvest],
                     f"`{roots.MEMORY_REL}/journal/` since {since.isoformat()}")
    return L


def _expected_stages():
    """The stage list, imported lazily so `run` can import this module.

    `run` is the single source of stage names (consolidation-cycle.md invariant
    5) and this module must not grow a second copy of it.
    """
    from consolidation import run as _run
    return _run.STAGES


def _since(anchor: dict, today: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(anchor.get("date", ""))
    except ValueError:
        return today - dt.timedelta(days=FALLBACK_DAYS)


def _scheduled(ctx, anchor: dict) -> list[str]:
    """dev/schedule 1g: each scheduled job that ran since the last pass, or whose
    state needs the user, read from its record under `<data>/sessions/`. Imported
    here and guarded: a defect in the scheduler is one line of this brief, never a
    brief that failed to render."""
    try:
        from schedule import notify                           # noqa: PLC0415
        lines = notify.brief_lines({"PAZRAS_DATA_DIR": str(ctx.base)},
                                   since=_since(anchor, ctx.today))
    except Exception as exc:                                  # noqa: BLE001
        return [f"- *the scheduler's records could not be read: {type(exc).__name__}: {exc}*"]
    return _capped(lines, "`familiar schedule sessions list`")


# ── render and write ─────────────────────────────────────────────────────────

def render(ctx) -> str:
    anchor = preflight.last_run(ctx.base)
    changed, scope = _changed(ctx, anchor)
    L = [f"# Brief — {ctx.today.isoformat()}", "",
         "Precomputed by the nightly pass (`familiar consolidation run`, stage 8). "
         "**Deterministic** — every line is read off git, the append-only "
         "ledgers, or the pass's own record; no model wrote this file. "
         "Quoted bullets are stage 1's verbatim output and are attributed to "
         "the entry they came from.", "",
         "Lines are **pointers**. This file is regenerated nightly and can be a "
         "day stale; the files it cites cannot. Read them.", ""]
    L += _section("What changed", scope, changed,
                  "Nothing — no commit, journal entry or leaf since the last pass.")
    L += _section(
        "What's open",
        "proposals awaiting a decision, and what sessions left unfinished",
        _open(ctx, anchor),
        "Nothing. No open proposal, no unlanded decision, no session left "
        "anything open.")
    L += _section(
        "What failed",
        "this pass's warnings and errors, and what sessions recorded as failing",
        _failed(ctx, anchor),
        "Nothing failed in this pass, and no recent session recorded a failure.")
    L += _section(
        "Scheduled sessions",
        "what ran unattended since the last pass, and where each job stands",
        _scheduled(ctx, anchor),
        "Nothing ran unattended, and no job waits on you.")
    L += ["---", "",
          f"*Tonight's full report: "
          f"`{roots.MEMORY_REL}/journal/reports/{ctx.today.isoformat()}_consolidation.md`. "
          f"Search the journal: `familiar knowledge journal search '<query>'`, or the "
          f"`journal_search` MCP tool.*", ""]
    return "\n".join(L)


def write(ctx) -> pathlib.Path:
    """One file, fixed name. Dry runs write outside git, like the report. The
    phone's highlights are written beside it from the same pass (R6a): the
    failure counts only exist here, before `_capped` cuts them."""
    d = (ctx.base / "reports") if ctx.dry_run else (ctx.agents / "journal" / "reports")
    d.mkdir(parents=True, exist_ok=True)
    p = d / NAME
    p.write_text(render(ctx))
    (d / HIGHLIGHTS).write_text(highlights(ctx))
    return p


def read(agents, name: str = NAME) -> str:
    """The current brief, for `familiar consolidation brief` and the MCP tool."""
    p = pathlib.Path(agents) / "journal" / "reports" / name
    try:
        return p.read_text()
    except OSError:
        return ""


# ── the phone's screen (dev/remote R5c) ─────────────────────────────────────

#: `/brief <word>` -> the section it shows.
PHONE_SECTIONS = {"changed": "What changed", "open": "What's open",
                  "failed": "What failed", "scheduled": "Scheduled sessions"}


def phone(text: str, section: str = "", *, limit: int = 3000) -> str:
    """The brief, phone-sized. No section: each heading with its bullet count -- the
    brief quotes journal bullets, and Telegram is not end-to-end encrypted, so the
    default sends headings only (the user's choice, 2026-10-21). A section: its
    lines, cut at `limit`."""
    title = next((l[2:].strip() for l in text.splitlines() if l.startswith("# ")), "Brief")
    parts: dict = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            parts[current] = []
        elif current and line.strip() and not line.startswith("---"):
            parts[current].append(line)
    if not section:
        rows = [title]
        for name, lines in parts.items():
            n = sum(1 for l in lines if l.lstrip().startswith(("- ", "* ", "|")))
            word = next((k for k, v in PHONE_SECTIONS.items() if v == name), "")
            rows.append(f"{name}: {n} line(s)" + (f"  (/brief {word})" if word else ""))
        return "\n".join(rows)
    name = PHONE_SECTIONS.get(section)
    if name is None:
        return f"/brief takes one of: {', '.join(PHONE_SECTIONS)}"
    body = "\n".join(l for l in parts.get(name, []) if not l.startswith("*")) or "(empty)"
    out = f"{title} -- {name}\n{body}"
    return out if len(out) <= limit else out[:limit] + "\n[... cut]"



# ── the morning highlights (dev/remote R6a) ─────────────────────────────────

#: Lines the highlights may take before they say how much was cut.
HIGHLIGHT_LINES = 20

# A note's per-file prefix: `<transcript>.jsonl: ` or `<leaf>.md: `. Stripped so
# 493 notes with one cause count as one line, not 493.
_NOTE_PREFIX = re.compile(r"^\S+\.(?:jsonl|md|json|yaml):\s*")


def _cause(text: str) -> str:
    return _NOTE_PREFIX.sub("", text.splitlines()[0] if text else "").strip()[:120]


def highlights(ctx) -> str:
    """The pass in ~20 plain lines for Telegram: what waits on the user, what
    broke (grouped by cause), how the unattended jobs ended. Deterministic, like
    the brief: counted, never summarised. The last line names `/review`."""
    from collections import Counter
    L = [f"Nightly pass {ctx.today.isoformat()}"]
    if ctx.aborted:
        L.append(f"ABORTED at preflight: {ctx.aborted.splitlines()[0][:120]}")
    kinds = Counter(p.kind for p in ctx.proposals)
    if kinds:
        L += ["", f"Waiting on you: {sum(kinds.values())}"]
        L += [f"  {n} {k}" for k, n in kinds.most_common()]
    causes = Counter((n.level, _cause(n.text)) for n in ctx.notes
                     if n.level in ("warn", "error"))
    expected = {sid for sid, _, _ in _expected_stages()}
    missing = sorted(expected - {s.split(" ", 1)[0] for s in ctx.stages_run})
    if causes or (missing and not ctx.aborted):
        L += ["", "Failed:"]
        L += [f"  {n}x {lvl}: {c}" for (lvl, c), n in causes.most_common(6)]
        if len(causes) > 6:
            L.append(f"  ... {len(causes) - 6} more cause(s): /brief failed")
        if missing and not ctx.aborted:
            L.append(f"  stage(s) not run: {', '.join(missing)}")
    sched = [l for l in _scheduled(ctx, preflight.last_run(ctx.base))
             if l.startswith("- `")]
    if sched:
        L += ["", "Unattended jobs:"]
        L += ["  " + re.sub(r"[`*]", "", l[2:]).split(";", 1)[0][:90] for l in sched[:5]]
    if len(L) > HIGHLIGHT_LINES:
        L = L[:HIGHLIGHT_LINES - 1] + [f"[... cut, /brief for the rest]"]
    L += ["", "/review to decide the open items" if kinds else "Nothing waits on you."]
    return "\n".join(L) + "\n"


def stale_prefix(text: str, today: dt.date) -> str:
    """'' when the highlights are today's, else a first line saying how old they
    are (R6b): yesterday's pass resent at 06:00 must not read as tonight's."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text.splitlines()[0] if text else "")
    if m and m.group(1) == today.isoformat():
        return ""
    return (f"NO PASS LAST NIGHT -- these are from {m.group(1)}\n" if m
            else "NO PASS LAST NIGHT -- undated highlights\n")
