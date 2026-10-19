"""pointers -- was the pointer actually followed?

THE QUESTION THIS ANSWERS, AND WHY IT IS NOT route.py's. `familiar context route`
measures DELIVERY: whether a file's bytes are in the request body. It classifies
each canonical file as `expanded` / `pointer` / `absent`, and its own docstring
says what it cannot see -- "whether the model OBEYED what it was given.
Delivery is mechanical and checkable; compliance is behavioural and would need a
live model, a bill, and a nondeterministic answer."

That is the half this module measures, and it does not need a model, a bill, or
a probe. **The evidence is already on disk.** `~/.local/share/pazras/transcripts/`
holds the staged verbatim tier, and every one of those files contains raw
`tool_use` blocks WITH their inputs. `transcripts.py` drops those inputs in its
REDUCTION -- deliberately, so the model is not handed `cat` output -- but the
reduction is in-memory, so the verbatim tier is untouched and every file an
agent opened is still recorded, with its arguments, in the order it asked.

So the pointer design's central assumption is testable after all. L2 put a flat
index between `CONTEXT.md` and the leaves and injects nothing per turn, on the
reasoning that the model looks when it needs to. That reasoning is only sound if
pointers get followed. Until this module, nothing in the system could say
whether they do.

THE HONEST LIMIT, stated first because it decides how to read the output.
A reference to a path is not proof the model READ it: a `cat` in a loop over a
directory, a `grep -r` whose argument mentions the tree, and a deliberate read
all look identical here. So the count is an UPPER BOUND on following, and the
signal is in the ratios and in which paths, not in the absolute number. What it
can prove is the negative: **a path referenced zero times was not followed**,
and that is the direction the always-on question actually turns on.

THREE CLASSES, and the middle one is why this needs the tree rather than a list:

  always-on   in `posture.ALWAYS_LOADED`. Already in the prompt, so touching it
              is the model re-reading something it was given -- which is worth
              measuring, because a high count here is a file being referenced
              instead of read.
  routed      named by `CONTEXT.md`'s routing table or by `knowledge/INDEX.md`.
              The model had a reason to look, and a pointer in front of it.
  cold        named by neither. Reached only because the model already knew or
              guessed the path -- which is what "cold" means, and is the class
              that proves a pointer worked without being needed.

Anything not in the tree at all is reported separately as a STALE ATTEMPT, with
the date it was tried. That distinction matters more than it looks: the single
most-referenced path in the corpus is one that no longer exists, and without the
date it is impossible to tell a model following a pointer written when the file
was there from a pointer that rotted.
"""
from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import json
import pathlib
import re

from knowledge import ontology
from lib import invocation
from lib import roots

from context import transcripts

# The tools whose INPUT names a file. Both spellings of each: a harness may
# present them bare or through its own MCP namespace, and a counter that
# instruments only one channel measures almost nothing -- measured, read-through
# and shell-through differ by an order of magnitude in this corpus.
READ_TOOLS = ("Read", "read")
BASH_TOOLS = ("Bash", "bash")
INPUT_KEYS = ("file_path", "path", "notebook_path", "command", "pattern")

# Repo-relative keys since R3b: the router sits at the root and the user's
# files under `config/`, so the vault alone no longer holds what an agent is
# pointed at. `agents/` is the vault's name before R3b -- the verbatim tier
# predates the move, and `MOVED` carries those reads to where the file went.
# The old name is spelled once, here: `declared_paths.RETIRED` refuses the
# old paths anywhere else, and this table is the one place that must still
# read them.
PRE_R3B = "agents"
TOPS = (roots.MEMORY_REL, roots.CONFIG_REL, PRE_R3B)
MOVED = tuple((f"{PRE_R3B}/{old}",
               roots.rel(new) + ("" if old.endswith(".md") else "/"))
              for old, new in (("ontology/", roots.ONTOLOGY),
                               ("boundaries/", roots.BOUNDARIES),
                               ("user/", roots.USER),
                               ("conventions/", roots.CONVENTIONS),
                               ("subagents/", roots.SUBAGENTS),
                               ("CONTEXT.md", roots.ROUTER),
                               ("", roots.MEMORY)))

# A path in the tree, however it is spelled: bare, `./`-prefixed, relative to a
# home directory, or absolute. Normalised by `normalise()` afterwards.
_EXT = r"\.(?:md|py|json|yaml|sh|jsonl)"


def _pathlike(tops, ext: str):
    """The literal-path pattern for one set of tops.

    BUILT rather than written twice: two readers of the same transcripts must
    not disagree about what a path looks like, and a second hand-written regex
    is how they would. `tops` differs (see `TOUCH_TOPS`) and `ext` differs with
    it -- the routing report indexes `.md` prose, and a session edits `.ts`.
    """
    return re.compile(r"[\w./~$-]*(?:(?:" + "|".join(tops) + r")/[\w./-]+"
                      + ext + r"|06_SYSTEM/[\w.-]+" + ext + r")")


PATHLIKE = _pathlike(TOPS, _EXT)

# What counts as the tree once a path is anchored. Both words are common:
# `memory/` was the ENGINE's directory before R2 (its Python package lived there), and
# any project has a `config/`. So a `memory/` path must continue into one of the
# vault's own tops, and a `config/` path into one of the subtrees R3b created
# -- read from `MOVED` and the ontology, not listed again.
_SCOPE = tuple(f"{roots.MEMORY_REL}/{t}" for t in ontology.AGENT_TOPS) + tuple(
    new for _, new in MOVED if new.startswith(roots.CONFIG_REL + "/"))


def _anchor(tops):
    return re.compile(r"06_SYSTEM/|(?<![\w.])(?=(?:" + "|".join(tops) + r")/)")


_ANCHOR = _anchor(TOPS)

# ── the SECOND scope: what a session TOUCHED (ontology SPECS O5b, C2) ──
#
# Not a widening of the scope above, and not a mistake that there are two. The
# report answers "was the pointer followed?" about the knowledge tree's own
# homes, and a session's `engine/` reads are noise to that question. `touches:`
# answers "what did this session work on", and there `engine/` is the point.
# So the tops differ, the extension set differs (a session edits `.ts` and
# writes `.timer` files), and the FILTER differs most of all: nothing here is
# kept or dropped by a list of directories -- `ontology.subject_at` decides,
# because a subject's `places:` is the register's answer to which paths exist.
TOUCH_TOPS = (roots.MEMORY_REL, roots.CONFIG_REL, roots.ENGINE_REL)
TOUCH_EXT = r"\.[A-Za-z0-9]{1,8}"
TOUCH_PATHLIKE = _pathlike(TOUCH_TOPS, TOUCH_EXT)
_TOUCH_ANCHOR = _anchor(TOUCH_TOPS)

# The input keys that NAME a file. `pattern` is deliberately not here: a search
# regex that mentions a path is a reference, not a touch. Everything else in an
# input is prose -- an `Edit`'s replacement text says nothing about what the
# session worked on, and scanning it would credit a session with every path a
# document it wrote happens to mention.
TOUCH_KEYS = ("file_path", "filePath", "path", "notebook_path", "command")

# Trailing punctuation a shell command drags in, and which is not part of a path.
TRAILING = ".,;:)\"'`"

# `<<EOF`, `<<-EOF`, `<<'EOF'`, `<<"EOF"` -- a heredoc opening.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


# A heredoc BODY is stdin, not argv. Measured: 18% of the `memory/` path
# references in this corpus sit inside one, because a command WRITING a file that
# happens to mention a path looks identical to a command opening it. Leaving them
# in inflates the count and, worse, inflates it unevenly -- the always-on files
# are the ones most often written about, so the class that decides the always-on
# question is the class most distorted. The opening line is kept, since a heredoc
# target is still an argument.
def strip_heredocs(cmd: str) -> str:
    """`cmd` with every heredoc body removed, terminators kept."""
    lines = cmd.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            tag = m.group(2)
            i += 1
            while i < len(lines) and lines[i].strip() != tag:
                i += 1
        i += 1
    return "\n".join(out)

ALWAYS_ON = "always-on"
ROUTED = "routed"
COLD = "cold"
STALE = "stale"


@dataclasses.dataclass
class Channel:
    read: int = 0
    bash: int = 0

    @property
    def total(self) -> int:
        return self.read + self.bash


@dataclasses.dataclass
class Report:
    corpus: pathlib.Path
    sessions: int = 0
    sessions_touching: int = 0
    calls: int = 0                       # tool_use blocks examined
    mcp_calls: collections.Counter = dataclasses.field(
        default_factory=collections.Counter)
    hits: dict = dataclasses.field(default_factory=dict)   # rel -> Channel
    first_seen: dict = dataclasses.field(default_factory=dict)
    last_seen: dict = dataclasses.field(default_factory=dict)
    cold_sessions: dict = dataclasses.field(default_factory=dict)


def normalise(raw: str, anchor=_ANCHOR, require=_SCOPE) -> str | None:
    """Repo-relative, or None if this is not our tree.

    Every spelling of the same file must collapse to one key, or the report
    counts one file four times: `memory/knowledge/system/consolidation/x.md`,
    `~/06_SYSTEM/memory/knowledge/system/consolidation/x.md`, the absolute path,
    and `./memory/`. That inflation is not cosmetic -- it moves a path out of
    the class it belongs in and hides how often it is really reached. A
    pre-R3b `agents/` spelling is one more of them, mapped through `MOVED`.

    `anchor` and `require` are the two halves of a SCOPE, and both default to
    the routing report's. `touched_paths` passes the wider pair and
    `require=None` -- there, which paths are kept is the register's question
    (`ontology.subject_at`), not this module's.
    """
    p = raw.strip().rstrip(TRAILING)
    m = anchor.search(p)
    if not m:
        return None
    rel = p[m.end():].lstrip("/")
    for old, new in MOVED:
        if rel.startswith(old):
            rel = new + rel[len(old):]
            break
    if ".." in rel.split("/"):
        return None
    if require is None:
        return rel
    return rel if rel == "CONTEXT.md" or rel.startswith(require) else None


def classify(rel: str, routed: set[str], always: set[str]) -> str:
    """Which class this path belongs to. Order matters: always-on first, since
    those files are also named by the routing table."""
    if rel in always:
        return ALWAYS_ON
    if rel in routed:
        return ROUTED
    return COLD


def route_token(tok: str) -> str | None:
    """A routing-table or index token as a path, as written.

    A SECOND RESOLVER, because the two sources are anchored differently and only
    one of them carries its anchor in the text. A token in `CONTEXT.md`'s table
    is already relative to the repository (`config/practice/conventions/
    collaboration.md`) and an index row to `memory/knowledge/`; neither has a
    marker for `normalise()` to find. Routing the table
    through the corpus function is what made a first version of this report every
    routed path as cold.
    """
    tok = tok.strip().strip("`").rstrip(TRAILING).rstrip("/")
    if not tok or tok.startswith(("/", "~", "..")):
        return None            # outside the tree, or the entry point above it
    if any(c in tok for c in "*<>|$ \t"):
        return None            # a glob, a placeholder, or a whole sentence
    if "/" not in tok and not tok.endswith(".md"):
        return None            # a bare word is prose, not a route
    if ".." in tok.split("/"):
        return None
    return tok


def routing_targets(agents: pathlib.Path) -> set[str]:
    """Paths the model has a written reason to open: the entry point's routing
    table, and the flat index L2 put between it and the leaves.

    Read from the live files rather than hard-coded, for the reason route.py
    gives about canaries: a literal list goes stale the first time the table is
    rewritten, and then reports `cold` for a path that is properly routed.

    The two files spell paths against DIFFERENT anchors, and each says so: the
    routing table is relative to the repository (it sits at its root since
    R3b), and `knowledge/INDEX.md` announces "Paths are relative to
    `~/06_SYSTEM/memory/knowledge/`" in its own header. Resolving the index
    against the repository would drop every entry silently and reclassify the
    whole knowledge branch as cold -- which is what a first version of this
    function did, and why the anchor is read from the file rather than assumed.
    """
    out: set[str] = set()
    src = agents.parent / "CONTEXT.md"
    if src.exists():
        for m in re.finditer(r"`([^`\n]+)`", src.read_text()):
            rel = route_token(m.group(1))
            if rel:
                out.add(rel)
    index = agents / "knowledge" / "INDEX.md"
    if index.exists():
        for m in re.finditer(r"`([^`\n]+\.md)`", index.read_text()):
            bare = route_token(m.group(1))
            if bare:
                # An index row: relative to `knowledge/`, as the header says.
                anchor = f"{roots.MEMORY_REL}/knowledge/"
                out.add(bare if bare.startswith(anchor) else anchor + bare)
    return out


def _tool_channel(name: str) -> str | None:
    """`read`, `bash`, or None. Normalises the MCP-namespaced spellings."""
    short = name.rsplit("__", 1)[-1] if name.startswith("mcp__") else name
    if short in READ_TOOLS:
        return "read"
    if short in BASH_TOOLS:
        return "bash"
    return None


def _strings(value, _depth=0):
    """Every string in an input value, however deeply nested.

    `Bash` puts its payload in `command`, but a harness may wrap it, and a
    matcher that only reads top-level strings silently under-counts without
    saying so -- the exact failure `selftest --invariants` exists to prevent one
    layer up.
    """
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v, _depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v, _depth + 1)


def _date_of(path: pathlib.Path) -> str:
    """The session date, from the filename the capture path chose.

    `20260830T212745Z_claude_<uuid>.jsonl` -- the capture path's own naming, so
    it needs no parsing of the transcript body and cannot disagree with the
    record. Falls back to the file mtime, which is later but is at least a time.
    """
    m = re.match(r"(\d{8})T", path.name)
    if m:
        return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
    try:
        return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        return ""


def touched_paths(path: pathlib.Path) -> set[str]:
    """The repository-relative paths one transcript's tool calls named.

    C2's half of this module (`ontology SPECS` O5b): the durable way to
    answer "what did this session work on" is to write it into the entry at
    distill time, and this is the reading that produces the value. There is no
    equivalent here of `scan`'s classification -- no always-on, routed or cold,
    no dates, no counts -- because a facet wants the SET, and the caller turns
    it into subject ids through each subject's `places:`.

    hermes yields nothing and it is not this function's bug: `hermes_extract`
    keeps the tool NAME and drops the arguments, so a caller must count the
    transcripts that produced paths rather than read silence as "touched
    nothing". opencode transcripts staged before 2026-10-09 have the same gap;
    `opencode_extract` keeps the path-naming keys since then (`filePath`).

    Every tool is read, not only `Read` and `Bash`: an `Edit` names a file as
    surely as a `Read` does, and a facet built from reads alone would miss the
    file the session was actually changing.
    """
    out: set[str] = set()
    for _name, data in transcripts.tool_calls(path):
        cmd = data.get("command")
        # The shell is read whole (heredoc bodies stripped) because a path in a
        # command is argv; every other tool is read only at the keys that name
        # a file, because its prose is output, not evidence.
        payload = (strip_heredocs(cmd) if isinstance(cmd, str) else
                   " ".join(str(data[k]) for k in TOUCH_KEYS
                            if isinstance(data.get(k), str)))
        for raw in TOUCH_PATHLIKE.findall(payload):
            rel = normalise(raw, _TOUCH_ANCHOR, require=None)
            if rel:
                out.add(rel)
    return out


def scan(corpus: pathlib.Path, agents: pathlib.Path,
         since: str | None = None, until: str | None = None) -> Report:
    """Walk the verbatim tier and classify every path in the tree touched.

    `since`/`until` are ISO dates and exist because the corpus predates the
    mechanisms under test: `knowledge/INDEX.md` and the MCP server both landed
    2026-09-11, so a whole-corpus number is a baseline for the OLD regime and
    must not be read as a verdict on the new one.
    """
    routed = routing_targets(agents)
    always = set(_always_loaded())
    rep = Report(corpus=corpus)
    files = sorted(corpus.glob("*.jsonl")) if corpus.is_dir() else []
    for path in files:
        date = _date_of(path)
        if since and date and date < since:
            continue
        if until and date and date > until:
            continue
        rep.sessions += 1
        touched = set()
        for name, data in transcripts.tool_calls(path):
            rep.calls += 1
            if name.startswith(("mcp__familiar-mcp", "mcp__pazras-memory")):
                # `mcp__pazras-memory` is the id's spelling in transcripts from
                # before 2026-10-13; the report counts both, or the two calls it
                # exists to count would vanish from the count.
                rep.mcp_calls[name] += 1
            channel = _tool_channel(name)
            if channel is None:
                continue
            for rel in _referenced(channel, data):
                ch = rep.hits.setdefault(rel, Channel())
                setattr(ch, channel, getattr(ch, channel) + 1)
                if date:
                    rep.first_seen.setdefault(rel, date)
                    rep.last_seen[rel] = date
                touched.add(rel)
        if touched:
            rep.sessions_touching += 1
            cold = {r for r in touched
                    if classify(r, routed, always) == COLD}
            if cold:
                rep.cold_sessions[path.name] = cold
    return rep


def _referenced(channel: str, data: dict):
    """The tree paths one `read`/`bash` call references, normalised.

    The single extraction behind `scan` and `reads`: two readers of the same
    call must not disagree about which files it named.
    """
    if channel == "bash":
        # Only the command itself is argv; a heredoc body is stdin.
        cmd = data.get("command")
        payload = strip_heredocs(cmd) if isinstance(cmd, str) else \
            " ".join(_strings(data))
    else:
        payload = " ".join(_strings(data))
    for raw in PATHLIKE.findall(payload):
        rel = normalise(raw)
        if rel is not None:
            yield rel


def session_of(path: pathlib.Path) -> str:
    """The harness's session id, from `<ts>_<harness>_<id>.jsonl`.

    One session is often staged as several files (a capture per `SessionEnd`,
    a resume, a compaction), so a per-session count must key on this, not on
    the file. The id may itself contain `_` (opencode's `ses_…`), hence the
    split limit. A name in no known shape is its own session.
    """
    parts = path.stem.split("_", 2)
    return parts[2] if len(parts) == 3 else path.stem


def reads(corpus: pathlib.Path) -> dict[str, tuple[str, set[str]]]:
    """`session id -> (last date, tree paths it read)`, over the verbatim tier.

    What stage 2 counts as USE (dev/memory/SPECS.md M2a). Only the `read` and
    `bash` channels: an `Edit` or `Write` names a document a session changed,
    which is maintenance, not use. The same upper-bound limit as `scan` holds
    per call -- a reference is not proof of reading -- and one more applies
    per session: a session that reads a document in order to edit it counts.
    hermes staging drops arguments, so hermes sessions contribute nothing.
    """
    out: dict[str, tuple[str, set[str]]] = {}
    files = sorted(corpus.glob("*.jsonl")) if corpus.is_dir() else []
    for path in files:
        seen: set[str] = set()
        for name, data in transcripts.tool_calls(path):
            channel = _tool_channel(name)
            if channel is not None:
                seen.update(_referenced(channel, data))
        if not seen:
            continue
        sid, date = session_of(path), _date_of(path)
        last, paths = out.get(sid, ("", set()))
        out[sid] = (max(last, date), paths | seen)
    return out


def _always_loaded() -> tuple:
    """`context.navigation.ALWAYS_LOADED` -- imported, not restated. It is the
    source `posture.ALWAYS_LOADED` mirrors and `posture.check_injected_surface`
    holds equal; read from here because `context` sits below `consolidation`
    in the dependency order (R1j)."""
    from context.navigation import ALWAYS_LOADED
    return ALWAYS_LOADED


# ── rendering ────────────────────────────────────────────────────────────────

def resolve_classes(rep: Report, agents: pathlib.Path) -> dict[str, str]:
    """Final class per path, which needs the TREE and not just the table: a path
    named by no router and absent from disk is stale, and that is a different
    finding from a cold read."""
    routed = routing_targets(agents)
    always = set(_always_loaded())
    out = {}
    for rel in rep.hits:
        out[rel] = (STALE if not (agents.parent / rel).exists()
                    else classify(rel, routed, always))
    return out


def render(rep: Report, agents: pathlib.Path, top: int = 15) -> str:
    classes = resolve_classes(rep, agents)
    by_class: dict[str, Channel] = collections.defaultdict(Channel)
    for rel, ch in rep.hits.items():
        agg = by_class[classes[rel]]
        agg.read += ch.read
        agg.bash += ch.bash
    cold_sessions = len(rep.cold_sessions)

    lines = []
    lines.append("POINTER FOLLOWING — did the model open what it was pointed at")
    lines.append(f"  corpus             {rep.corpus}")
    lines.append(f"  staged transcripts {rep.sessions}")
    lines.append(f"  tool calls read    {rep.calls}")
    share = (f"{100 * rep.sessions_touching // rep.sessions}%"
             if rep.sessions else "0%")
    lines.append(f"  sessions touching the tree  {rep.sessions_touching} "
                 f"of {rep.sessions} ({share})")
    lines.append(f"  distinct paths     {len(rep.hits)}")
    total = sum(c.total for c in by_class.values())
    lines.append("")
    lines.append("  BY CLASS (references, not distinct paths — see the limit above)")
    for name in (ALWAYS_ON, ROUTED, COLD, STALE):
        c = by_class.get(name)
        if not c:
            continue
        lines.append(f"    {name:10} {c.total:5}  "
                     f"(read {c.read}, bash {c.bash})")
    lines.append("")
    lines.append(f"  COLD reads prove a pointer worked without being needed: "
                 f"{cold_sessions} session(s) reached a path no router names.")
    lines.append(f"  MCP memory tools called, ever: {sum(rep.mcp_calls.values())}"
                 + (f" {dict(rep.mcp_calls)}" if rep.mcp_calls else ""))

    for name in (STALE, COLD, ROUTED, ALWAYS_ON):
        rows = sorted(((r, c) for r, c in rep.hits.items()
                       if classes[r] == name),
                      key=lambda kv: -kv[1].total)[:top]
        if not rows:
            continue
        lines.append("")
        head = {
            STALE: "STALE ATTEMPTS — no such file in the tree now",
            COLD: "COLD — reached by a path no router names",
            ROUTED: "ROUTED — named by CONTEXT.md or knowledge/INDEX.md",
            ALWAYS_ON: "ALWAYS-ON — already in the prompt",
        }[name]
        lines.append(f"  {head}")
        for rel, ch in rows:
            span = ""
            if classes[rel] == STALE:
                f, l = rep.first_seen.get(rel, ""), rep.last_seen.get(rel, "")
                span = f"   {f}..{l}" if f else ""
            lines.append(f"    {ch.total:4}  {rel}{span}")
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────────────────

SPEC = invocation.Spec(
    name="pointers",
    usage="pointers [--since=YYYY-MM-DD] [--until=YYYY-MM-DD] [--top=N] [--json]",
    flags=("--json",),
    options=("--since", "--until", "--top"))


def main(inv) -> int:
    import sys

    corpus = inv.base / "transcripts"
    if not corpus.is_dir():
        print(f"no staged transcripts at {corpus}", file=sys.stderr)
        return 1
    rep = scan(corpus, inv.agents, since=inv.get("--since"),
               until=inv.get("--until"))
    if inv.has("--json"):
        classes = resolve_classes(rep, inv.agents)
        print(json.dumps({
            "corpus": str(corpus),
            "sessions": rep.sessions,
            "sessions_touching": rep.sessions_touching,
            "tool_calls": rep.calls,
            "mcp_calls": dict(rep.mcp_calls),
            "paths": {rel: {"class": classes[rel], "read": ch.read,
                            "bash": ch.bash, "first": rep.first_seen.get(rel),
                            "last": rep.last_seen.get(rel)}
                      for rel, ch in sorted(rep.hits.items())},
        }, indent=2))
        return 0
    print(render(rep, inv.agents, top=inv.integer("--top", 15)))
    # Exit 0 always, and NOT on a threshold. The number this reports is an upper
    # bound on following (see the module docstring), so a gate on it would fire
    # on a `grep -r` and train the reader to ignore the one report that speaks to
    # the always-on question. Baseline recorded, comparison made by a person.
    return 0
