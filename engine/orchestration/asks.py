"""asks -- the census of permission asks, before anything judges them (item 8c).

`pi-permission-system` has an opt-in `authorizerChain`: on an `ask` case a
registered link may grant or refuse **without a human being asked**. Before such a
link is written, this module counts what is actually asked, because its whole
value is the size of one category:

  class A  a rule that DELIBERATELY asks -- `git push`, a rebase, a directive edit.
           The rule encodes the user's own decision, so a model must never judge
           it: the answer is already written down, and the ask exists to put the
           choice in front of the person who wrote it.
  class B  an ask raised because NO rule matched -- an unfamiliar path, a tool the
           config does not cover. This is the only category a judging link could
           take off the user's desk.

HOW A LINE IS CLASSIFIED. The permission system's own renderer names the rule that
decided the call: `... (rule '<pattern>')` is present when a rule matched (class
A) and absent when none did (class B). The messages are
`This '<surface>' call ... requires approval, but no interactive UI is available.`
(an ask that had no UI to reach -- every child, and every non-interactive run) and
`Denied by policy: '<surface>' ... (rule '<pattern>').`.

WHAT THIS INSTRUMENT CANNOT SEE, stated because it decides how the numbers read.
  * A prompt the user ANSWERED leaves no trace in the transcript: the tool simply
    runs, and its result is indistinguishable from an allowed call. Only asks that
    could not be surfaced, and denials, are recorded.
  * The phrase also occurs when a transcript QUOTES it -- a source file read, a
    child reporting what blocked it, this module's own tests. So a line counts as
    an EVENT only when it matches the renderer's shape (it starts `This '...'` or
    `Denied by policy: ...` and carries no `<placeholder>`); every other occurrence
    is reported separately as a MENTION, with its session, because that is how the
    one real blocked-child case surfaced at all.
  * Therefore the honest reading is: events are a FLOOR on what was asked, not a
    count of it. `--replay 30` over the vault's own logs (2026-10-14) found 2
    events, both class A, and 0 class-B events -- while a known class-B case (a
    child blocked on `bash -ic`, which had no UI to answer it) appears only as a
    mention in the child's report. A mechanism aimed at class B needs a decision
    LOG before it can be sized: one line per decision, written where the decision
    is made. Until then this census says "not sized", which is a result.

WHY A CHILD IS THE INTERESTING CASE. A prompt that cannot be surfaced does not
pause a child, it KILLS it: the call returns a denial, the child reports being
blocked, and the work stops -- which is the failure 3d's record names. So the
category that a judging link could actually help is the class-B ask inside a
non-interactive session, and that is the number to instrument first.

THE DECISION LOG (8e) IS READ FIRST. `engine/boundaries/pi-emitter/index.ts` writes
one line per permission decision to `<PAZRAS_DATA_DIR>/permission-decisions.jsonl`,
where the decision is made, with the session's id. A session whose id is in that
log is counted from the log -- every ask, answered or not -- and only a session
older than the log falls back to the transcript scan above. `--review` reads a
third source, the package's own review log (`permission_request.waiting` joined to
its terminal event by `requestId`), which has no session id but goes back to the
package's install: it is the history the transcripts could not see.

A RULE IN ANGLE BRACKETS IS NOT THE USER'S. The package's own shape guards --
`<indirection-bash-wrapper>`, `<opaque-bash-wrapper>`, `<unparsed-bash-subtree>`
-- ask on a command's SHAPE (an `env`, a `cd &&`, a wrapper the parser cannot see
through), not because the user wrote a rule. They are class B: no rule of the
user's matched. Measured 2026-10-15 over the review log: 661 of 709 asks.

EXIT CODES. 0 the census printed. 2 a usage error or an unreadable root. A single
unreadable log is named and skipped, never fatal.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import os
import pathlib
import re
import sys

from lib import roots

SESSIONS = pathlib.Path.home() / ".pi/agent/sessions"
REVIEW = (pathlib.Path.home() / ".pi/agent/extensions/pi-permission-system/logs"
          / "pi-permission-system-permission-review.jsonl")
DECISIONS_NAME = "permission-decisions.jsonl"
CLASS_A = "A (a rule asked)"
CLASS_B = "B (no rule matched)"
# A decision log's `reason` (the package's `resolution`) -> the census's kind. A
# resolution not listed here asked nobody (`policy_allow`, `session_approved`,
# `infrastructure_auto_allowed`, `auto_approved`): it is a gate, the denominator.
KINDS = {
    "user_approved": "answered", "user_approved_for_session": "answered",
    "user_denied": "answered",
    "confirmation_unavailable": "unavailable", "prompt_unanswered": "unavailable",
    "authorizer_allowed": "authorized", "authorizer_denied": "authorized",
    "policy_deny": "denied", "gate_error": "error",
}
UUID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$")
ASK = "requires approval, but no interactive UI is available"
DENIED = "Denied by policy"
# The renderer's shape. A quote of the phrase does not start like this, which is
# what separates an event from a mention.
EVENT = re.compile(r"^(?:\[pi-permission-system\]\s*)?(?:This '(?P<surface1>[^'<][^']*)' call|"
                   r"Denied by policy: '(?P<surface2>[^'<][^']*)')")
RULE = re.compile(r"\(rule '(?P<rule>[^']+)'")
AGENT = re.compile(r"agent '(?P<agent>[^']+)'")


def classify(rule: str) -> str:
    """A pattern the user wrote is class A; none, or the package's own shape guard
    (`<indirection-bash-wrapper>`), is class B."""
    return CLASS_A if rule and not rule.startswith("<") else CLASS_B


def decisions_path(env=None) -> pathlib.Path:
    env = os.environ if env is None else env
    return roots.data_root(env) / DECISIONS_NAME


@dataclasses.dataclass
class Ask:
    kind: str                   # unavailable | denied | answered | authorized | error
    klass: str                  # A (a rule asked) | B (no rule matched)
    surface: str
    rule: str = ""
    agent: str = ""
    session: str = ""           # the log's file name
    where: str = ""             # parent | child
    decision: str = ""          # allow | deny, when the source records it

    def line(self) -> str:
        who = f" agent {self.agent}" if self.agent else ""
        rule = f" (rule {self.rule})" if self.rule else " (no rule matched)"
        return f"{self.klass} {self.kind:11} {self.surface}{who}{rule}  [{self.where}]"


@dataclasses.dataclass
class Mention:
    session: str
    where: str
    text: str


def logs(n: int, root: pathlib.Path = SESSIONS) -> list:
    """The `n` most recent session logs, newest first: the parent sessions (one
    directory per cwd) and the children pi-agent keeps in `pi-agent/`. A child's
    log is where a blocked child says so, so both are read."""
    found = []
    # One pass: a child's log lives under `pi-agent/`, which is itself a directory
    # under the root, so matching it twice would count every child ask as a parent
    # ask as well.
    for p in root.glob("*/*.jsonl"):
        where = "child" if p.parent.name == "pi-agent" else "parent"
        try:
            found.append((p.stat().st_mtime, p, where))
        except OSError:
            continue
    found.sort(reverse=True)
    return [(p, where) for _m, p, where in found[:n]]


def _texts(path: pathlib.Path):
    """Every tool result's text in one log, with the tool that produced it."""
    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"asks: cannot read {path}: {e}", file=sys.stderr)
        return
    with fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            m = e.get("message") if isinstance(e, dict) else None
            if not isinstance(m, dict) or m.get("role") != "toolResult":
                continue
            for b in (m.get("content") or []) if isinstance(m.get("content"), list) else []:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    yield m.get("toolName") or "?", b["text"]


def census(pairs: list) -> tuple:
    """(the events, the mentions). An event is a line in the renderer's own shape;
    a mention is the bare phrase anywhere else -- a quote, a child's report -- and
    is kept because it is the only trace some asks leave."""
    events, mentions = [], []
    for path, where in pairs:
        for _tool, text in _texts(path):
            for line in text.splitlines():
                stripped = line.strip()
                if ASK not in stripped and DENIED not in stripped:
                    continue
                m = EVENT.match(stripped)
                if m is None or "<" in stripped.split("(", 1)[0]:
                    mentions.append(Mention(path.name, where, stripped[:200]))
                    continue
                rule = RULE.search(stripped)
                agent = AGENT.search(stripped)
                events.append(Ask(
                    kind="unavailable" if ASK in stripped else "denied",
                    klass=classify(rule.group("rule") if rule else ""),
                    surface=(m.group("surface1") or m.group("surface2") or "?")[:80],
                    rule=rule.group("rule") if rule else "",
                    agent=agent.group("agent") if agent else "",
                    session=path.name, where=where))
    return events, mentions


def _jsonl(path: pathlib.Path):
    """Every JSON object in an append-only log; a torn or foreign line is skipped."""
    try:
        fh = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict):
                yield o


def read_decisions(path: pathlib.Path) -> dict:
    """The decision log (8e), grouped by session id. A line with no session is
    kept under "" so it is counted somewhere rather than nowhere."""
    by_session = collections.defaultdict(list)
    for o in _jsonl(path):
        by_session[o.get("session") or ""].append(o)
    return dict(by_session)


def session_id(path: pathlib.Path) -> str:
    """The uuid pi puts at the end of a session log's file name -- the id the
    decision log records from `ctx.sessionManager.getSessionId()`."""
    m = UUID.search(path.name)
    return m.group(1) if m else ""


def from_decisions(lines: list, session: str, where: str) -> tuple:
    """(the asks, the gates that asked nobody) of one session's decision lines."""
    events, gates = [], 0
    for o in lines:
        kind = KINDS.get(o.get("reason") or "")
        if kind is None:
            gates += 1
            continue
        rule = o.get("rule") or ""
        events.append(Ask(kind=kind, klass=classify(rule),
                          surface=(o.get("surface") or "?")[:80], rule=rule,
                          agent=o.get("agent") or "", session=session,
                          where="child" if o.get("child") else where,
                          decision=o.get("decision") or ""))
    return events, gates


def replay(pairs: list, decisions: dict) -> tuple:
    """(events, mentions, gates, sources): each session from the decision log when
    the log has it, from its transcript otherwise."""
    events, mentions, gates = [], [], 0
    sources = {"decision_log": 0, "transcripts": 0}
    rest = []
    for path, where in pairs:
        sid = session_id(path)
        if sid and sid in decisions:
            ev, g = from_decisions(decisions[sid], path.name, where)
            events += ev
            gates += g
            sources["decision_log"] += 1
        else:
            rest.append((path, where))
    if rest:
        ev, me = census(rest)
        events += ev
        mentions += me
        sources["transcripts"] = len(rest)
    return events, mentions, gates, sources


def review(path: pathlib.Path) -> tuple:
    """(events, span): every ask in the package's own review log -- a
    `permission_request.waiting` -- with its outcome from the terminal event that
    carries the same `requestId`. The log has no session id, so `where` is what
    the outcome says: `unavailable` (no live authority) is a session that could not
    ask, which is a child or a non-interactive run."""
    waiting, final, times = {}, {}, []
    for o in _jsonl(path):
        ev, rid = o.get("event") or "", o.get("requestId")
        if ev == "permission_request.waiting" and rid:
            waiting[rid] = o
            times.append(o.get("timestamp") or "")
        elif ev in ("permission_request.approved", "permission_request.denied") and rid:
            final[rid] = o
    events = []
    for rid, o in waiting.items():
        end = final.get(rid) or {}
        by = (end.get("decidedBy") or {}).get("kind", "")
        kind = {"user": "answered", "unavailable": "unavailable",
                "authorizer": "authorized"}.get(by, "unresolved" if not end else by)
        rule = o.get("matchedPattern") or ""
        events.append(Ask(kind=kind, klass=classify(rule),
                          surface=(o.get("surface") or "?")[:80], rule=rule,
                          agent=o.get("agentName") or "", session="",
                          where="no UI" if kind == "unavailable" else "?",
                          decision=("allow" if end.get("event", "").endswith("approved")
                                    else "deny" if end else "")))
    times = sorted(t for t in times if t)
    return events, (times[0][:10], times[-1][:10]) if times else ("", "")


def summarise(events: list, mentions: list, gates: int = 0, sources: dict | None = None) -> dict:
    by_class = collections.Counter(e.klass for e in events)
    by_kind = collections.Counter(e.kind for e in events)
    by_where = collections.Counter(e.where for e in events)
    rules = collections.Counter(e.rule for e in events if e.rule)
    surfaces = collections.Counter(e.surface for e in events)
    return {
        "events": len(events),
        "class_A": by_class.get(CLASS_A, 0),
        "class_B": by_class.get(CLASS_B, 0),
        "unavailable": by_kind.get("unavailable", 0),
        "denied": by_kind.get("denied", 0),
        "answered": by_kind.get("answered", 0),
        "authorized": by_kind.get("authorized", 0),
        "error": by_kind.get("error", 0),
        "parent": by_where.get("parent", 0),
        "child": by_where.get("child", 0),
        "no_ui": by_where.get("no UI", 0),
        "rules": dict(rules.most_common()),
        "surfaces": dict(surfaces.most_common()),
        "mentions": len(mentions),
        "mentions_in_children": sum(1 for m in mentions if m.where == "child"),
        "gates": gates,
        "sources": sources or {},
        "class_B_rules": dict(collections.Counter(
            e.rule or "(none)" for e in events if e.klass == CLASS_B).most_common()),
        "allowed": sum(1 for e in events if e.decision == "allow"),
    }


def _span(pairs: list) -> str:
    try:
        times = sorted(p.stat().st_mtime for p, _ in pairs)
    except OSError:
        return ""
    if not times:
        return ""
    import datetime
    return (f" ({datetime.date.fromtimestamp(times[0])} to "
            f"{datetime.date.fromtimestamp(times[-1])})")


def report(header: str, events: list, mentions: list, gates: int = 0,
           sources: dict | None = None, out=print) -> None:
    s = summarise(events, mentions, gates, sources)
    out(header)
    if s["sources"]:
        src = s["sources"]
        out(f"  sources    {src.get('decision_log', 0)} session(s) from the decision log, "
            f"{src.get('transcripts', 0)} from the transcript scan (older than the log)")
    out(f"  events     {s['events']} ask(s): {s['answered']} answered by a person, "
        f"{s['unavailable']} without a UI, {s['authorized']} by a chain link, "
        f"{s['denied']} denied by policy, {s['error']} gate error(s)"
        + (f"; {s['gates']} gate(s) asked nobody" if s["gates"] else ""))
    out(f"  classes    A (a rule asked) {s['class_A']}; "
        f"B (no rule matched) {s['class_B']}  <- the ceiling a judging link could take")
    if s["parent"] or s["child"]:
        out(f"  sessions   parent {s['parent']}, child {s['child']} "
            f"(a child that is asked cannot answer: it stops)")
    if s["no_ui"]:
        out(f"  no UI      {s['no_ui']} ask(s) reached no live authority: a child or a "
            f"non-interactive run, which the ask stops")
    if s["rules"]:
        out("  rules      " + ", ".join(f"{r} x{n}" for r, n in list(s["rules"].items())[:6]))
    if s["surfaces"]:
        out("  surfaces   " + ", ".join(f"{r} x{n}" for r, n in list(s["surfaces"].items())[:6]))
    if mentions:
        out(f"  mentions   {s['mentions']} line(s) quote the phrase without being one "
            f"({s['mentions_in_children']} in children): a quote, a source file, or a "
            f"child reporting what blocked it")
    measured = bool(s["sources"].get("decision_log")) or header.startswith("asks --review")
    if s["class_B"] == 0 and not measured:
        verdict = ("no class-B event is recorded, so the mechanism's size is NOT measured. "
                   "The transcripts cannot see an ask the user answered, nor an ask a child "
                   "died on unless the child said so in prose. The decision log "
                   f"({DECISIONS_NAME}, 8e) covers no session in this window yet.")
    elif s["class_B"] == 0:
        verdict = "0 class-B asks in a window the decision log covers: nothing for a judging link to take."
    else:
        verdict = (f"{s['class_B']} class-B ask(s), {s['allowed']} of all asks ended in allow: "
                   "the class-B count is what a judging link or a declared rule could take "
                   "off the user's desk" + ("" if measured else
                                            ", and the prompts answered interactively are not in it") + ".")
    out("  verdict    " + verdict)
    for e in events[:12]:
        out("  " + e.line())
    for m in mentions[:6]:
        out(f"  mention {m.where:6} {m.session[:26]} {m.text[:110]}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration asks",
                                 description="Count the permission asks that are recorded, "
                                             "split into a rule that meant to ask (class A) "
                                             "and no rule matched (class B).")
    ap.add_argument("--replay", type=int, default=30, metavar="N",
                    help="the N most recent session logs (default 30)")
    ap.add_argument("--json", action="store_true", help="the summary as JSON")
    ap.add_argument("--root", type=pathlib.Path, default=SESSIONS,
                    help="where the session logs are (tests use a tmp tree)")
    ap.add_argument("--decisions", type=pathlib.Path, default=None,
                    help=f"the decision log (default <PAZRAS_DATA_DIR>/{DECISIONS_NAME})")
    ap.add_argument("--review", nargs="?", type=pathlib.Path, const=REVIEW, default=None,
                    metavar="PATH", help="count the package's own review log instead of the "
                                         f"sessions (default {REVIEW})")
    args = ap.parse_args(argv)
    if args.review is not None:
        if not args.review.is_file():
            print(f"asks: no review log at {args.review}", file=sys.stderr)
            return 2
        events, (first, last) = review(args.review)
        if args.json:
            print(json.dumps(summarise(events, []), indent=1, sort_keys=True))
            return 0
        report(f"asks --review -- every ask in the package's review log ({first} to {last})",
               events, [])
        return 0
    if args.replay < 1:
        print("asks: --replay needs a positive count", file=sys.stderr)
        return 2
    pairs = logs(args.replay, args.root)
    if not pairs:
        print(f"asks: no session logs under {args.root}", file=sys.stderr)
        return 2
    decisions = read_decisions(args.decisions or decisions_path())
    events, mentions, gates, sources = replay(pairs, decisions)
    if args.json:
        print(json.dumps(summarise(events, mentions, gates, sources), indent=1, sort_keys=True))
        return 0
    report(f"asks -- permission asks in the last {len(pairs)} session log(s){_span(pairs)}",
           events, mentions, gates, sources)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
