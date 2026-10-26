"""cli -- the non-capture, non-pass subcommands.

Each states what it accepts as an `invocation.Spec`; the dispatcher parses
against it, so an unknown flag is refused here exactly as it is in `capture`.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import stat
import subprocess
import sys

from lib import invocation
from lib import roots

STATUS = invocation.Spec(name="status", usage="status")
REPORT = invocation.Spec(name="report", usage="report [--full] [--patch]",
                         flags=("--full", "--patch"))
BRIEF = invocation.Spec(name="brief", usage="brief [--phone|--highlights [--send]] [section]",
                        flags=("--phone", "--highlights", "--send"),
                        positional="section")
DECISION = invocation.Spec(
    name="decision",
    usage="decision --kind=decision|disagreement --text='...' "
          "[--context='...'] [--session=...]",
    options=("--kind", "--text", "--context", "--session"))
DISMISS = invocation.Spec(
    name="dismiss",
    usage="dismiss --target=TARGET --kind=... [--target-kind=leaf|opaque] "
          "[--note='why']",
    options=("--target", "--kind", "--target-kind", "--note"))
QUEUE = invocation.Spec(name="queue", usage="queue [--all] [--json]",
                        flags=("--all", "--json"))
JEV = invocation.Spec(name="jev", usage="jev check|probe", positional="check|probe")
DECIDE = invocation.Spec(
    name="decide",
    usage="decide [N] [--no] [--choice=land|superseded|drop|note [--by=ID]] [--partial] "
          "[--kind=K --all] [--walk] [--why] [--note='why']",
    flags=("--no", "--partial", "--all", "--walk", "--why"),
    options=("--kind", "--note", "--choice", "--by"),
    positional="N")
OPENCODE_SESSION = invocation.Spec(
    name="opencode-session",
    usage="opencode-session --session=ID [--db=PATH]",
    options=("--session", "--db"))

HERMES_SESSION = invocation.Spec(name="hermes-session", usage="hermes-session")
HERMES_SESSION_WORKER = invocation.Spec(
    name="hermes-session-worker", usage="hermes-session-worker --session=ID",
    options=("--session",))


def status(inv) -> int:
    base = inv.base
    tdir = base / "transcripts"
    n_t = len(list(tdir.iterdir())) if tdir.is_dir() else 0

    def lines(p):
        return sum(1 for _ in p.open()) if p.exists() else 0

    print("familiar consolidation status")
    print(f"  staged transcripts : {n_t}")
    print(f"  session-log lines  : {lines(base / 'session.log')}")
    print(f"  skill-usage lines  : {lines(base / 'skill-usage.jsonl')}")
    print(f"  data dir           : {base}")
    reports = roots.INSTALL / roots.rel(roots.JOURNAL) / "reports"
    if reports.is_dir():
        r = sorted(p for p in reports.glob("*_consolidation.md"))
        print(f"  last report        : {r[-1].name if r else '(none)'}")
    out = subprocess.run(["systemctl", "--user", "list-timers", "--no-pager"],
                         capture_output=True, text=True, check=False).stdout
    for line in out.split("\n"):
        if "familiar-memory" in line:
            print(f"  timer              : {line.strip()}")
    return 0


def show_report(inv) -> int:
    d = inv.agents / "journal" / "reports"
    if inv.has("--patch"):
        pats = sorted(d.glob("*_consolidation.patch")) if d.is_dir() else []
        if not pats:
            print("no patch yet — run `familiar consolidation run`", file=sys.stderr)
            return 1
        txt = pats[-1].read_text()
        if not txt.strip():
            print("# the last pass proposed no appliable change",
                  file=sys.stderr)
            return 1
        print(txt, end="")
        return 0
    full = inv.has("--full")
    pat = "*_consolidation.full.md" if full else "*_consolidation.md"
    files = sorted(p for p in d.glob(pat)
                   if full or not p.name.endswith(".full.md")) if d.is_dir() else []
    if not files:
        print("no report yet — run `familiar consolidation run --dry-run`")
        return 1
    print(files[-1].read_text())
    return 0


def show_brief(inv) -> int:
    """Print the precomputed answers (memory/knowledge/system/consolidation/consolidation-cycle.md).

    Distinct from `report`, which is the human's per-night decision list. This
    is what a session asks when it opens: what changed, what's open, what
    failed. Exit 1 with the reason when there is none, rather than printing an
    empty answer -- "the pass has not run" and "nothing happened" are different
    states and a session must be able to tell them apart.
    """
    from consolidation import brief as _brief
    if inv.has("--highlights"):
        text = _brief.read(inv.agents, _brief.HIGHLIGHTS)
        if not text.strip():
            print("no highlights yet — they are written with the brief by stage 8",
                  file=sys.stderr)
            return 1
        text = _brief.stale_prefix(text, dt.date.today()) + text.rstrip()
        if inv.has("--send"):
            # The 06:00 timer (dev/remote R6b). A relay that is down fails the
            # unit, so `notify@` puts it on the desktop instead of losing it.
            from relay import client
            try:
                reply = client.request({"op": "notify", "session": "nightly",
                                        "text": text}, timeout=5)
            except Exception as exc:                          # noqa: BLE001
                print(f"[familiar] highlights not sent: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                return 1
            if not (reply or {}).get("ok", True):
                print(f"[familiar] highlights not sent: {reply}", file=sys.stderr)
                return 1
            print("highlights sent")
            return 0
        print(text)
        return 0
    text = _brief.read(inv.agents)
    if not text.strip():
        print("no brief yet — it is written by stage 8 of `familiar consolidation run`",
              file=sys.stderr)
        return 1
    if inv.has("--phone"):
        print(_brief.phone(text, inv.rest[0] if inv.rest else ""))
        return 0
    print(text)
    return 0


def decision(inv) -> int:
    """Record a decision or an overruled disagreement.

    ROADMAP M2 criteria 10 and 11. LEVEL 4 -- an agent must choose to call this;
    no hook can detect that the user just settled a recurring question. What is
    enforced is what happens next: the nightly pass surfaces the line every
    night until it lands in a leaf or a journal entry.
    """
    from consolidation import ledger
    if inv.help:
        print(f"usage: familiar consolidation {DECISION.usage}\n\n"
              "  decision      settles a recurring question; a later session "
              "should not re-ask it\n"
              "  disagreement  a push-back overruled after two rounds, recorded "
              "so both sides can refer back")
        return 0
    kind, text = inv.get("--kind"), inv.get("--text")
    if kind not in ledger.KINDS or not text:
        print(f"usage: familiar consolidation {DECISION.usage}", file=sys.stderr)
        return 1
    did = ledger.record_decision(inv.base, kind, text,
                                 inv.get("--context"), inv.get("--session"))
    print(f"recorded {kind} {did}")
    print("It will appear in every nightly report until it lands in a leaf, "
          "or a journal entry.")
    return 0


def dismiss(inv) -> int:
    """Mark a proposal decided so it stops recurring in the nightly report."""
    from consolidation import ledger
    if inv.help:
        print(f"usage: familiar consolidation {DISMISS.usage}\n\n"
              "A leaf dismissal lapses if the target file changes, so a leaf "
              "that moves on can be proposed for again. An opaque target "
              f"(skill name, link pair, decision id) has no file "
              f"to change, so it lapses after {ledger.OPAQUE_TTL_DAYS} days.")
        return 0
    target, kind = inv.get("--target"), inv.get("--kind")
    if not target or not kind:
        print(f"usage: familiar consolidation {DISMISS.usage}", file=sys.stderr)
        return 1
    tkind = inv.get("--target-kind") or "leaf"
    if tkind not in ledger.TARGET_KINDS:
        print(f"--target-kind must be one of {ledger.TARGET_KINDS}",
              file=sys.stderr)
        return 1
    sha = ledger.record_dismissal(inv.base, inv.agents.parent, target, kind,
                                  inv.get("--note"), target_kind=tkind)
    if tkind == "opaque":
        print(f"dismissed {kind} {target} "
              f"(opaque — returns after {ledger.OPAQUE_TTL_DAYS} days)")
        print(f"It will return after {ledger.OPAQUE_TTL_DAYS} days.")
        return 0
    print(f"dismissed {kind} {target} (leaf {sha or 'absent'})")
    print("It will return if that leaf changes.")
    return 0


def jev_cli(inv) -> int:
    """`jev check` -- what this account may call. This closes step 0d.

    The one command in this track that proves something about the ACCOUNT rather
    than about the code, and therefore the one that cannot be tested against a
    stub and called verified. It never reads the key: the client does, and a
    missing or loose-mode key comes back as a typed `JevError`. The command makes
    one `GET /v1/models` and prints what came back together with the key file's
    mode (metadata only) -- so a green
    run here is also evidence that the credentials rule of 0c is not in the way.

    Exit 0 only on a real answer. Every failure names its kind, so a nightly
    caller can tell `no-key` (fix the file) from `rate-limited` (wait).
    """
    from harness import jev
    if inv.help or inv.rest not in (("check",), ("probe",)):
        print(f"usage: familiar consolidation {JEV.usage}\n\n"
              "  check   GET /v1/models with the key at "
              f"{jev.KEY_PATH}\n"
              "          prints what this account may call; exit 0 on a valid "
              "key\n"
              "  probe   one real noul call, to prove the pinned id resolves "
              "and\n          show the resolved model, the answer and the usage"
              " line", file=sys.stderr)
        return 1 if inv.rest not in (("check",), ("probe",)) and not inv.help else 0
    if inv.rest == ("probe",):
        return _jev_probe()
    try:
        out = jev.models()
    except jev.JevError as exc:
        print(f"[familiar] jev check: {exc.kind}: {exc}", file=sys.stderr)
        return 2 if exc.fatal else 3
    print(f"key ok ({jev.KEY_PATH}, mode "
          f"{oct(stat.S_IMODE(jev.KEY_PATH.stat().st_mode))[2:]})")
    print(f"pinned  : {jev.MODEL}")
    ids = _model_ids(out)
    print(f"callable: {', '.join(ids) if ids else '(none listed)'}")
    # DO NOT fail on `MODEL not in ids`. Measured 2026-09-29: `/v1/models` on a
    # valid key lists `jev-latest, jev-preview` ONLY, while a POST naming
    # `jev-1.13.0` succeeds and resolves to `jev-1.13.0`. The listing enumerates
    # the ALIASES the account may call, not every accepted id -- so treating a
    # missing versioned id as retired would fail this check every night on a
    # healthy account, which is how a real signal gets ignored.
    if ids and not any(jev.MODEL in i or i in jev.MODEL for i in ids):
        print(f"  note: the versioned pin is not in the listing; the listing "
              f"carries aliases only. `familiar harness jev probe` proves the pin.")
    return 0


def _model_ids(payload) -> list:
    """The ids out of whatever shape `/v1/models` returns. Tolerant by design:
    the field names come from mirrors (PLAN.md §The answer shapes), so this reads
    the common shapes and reports `(none listed)` rather than guessing."""
    if isinstance(payload, dict):
        items = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            got = it.get("id") or it.get("name") or it.get("model")
            if got:
                out.append(str(got))
    return out


def _jev_probe() -> int:
    """One real call, to prove the PIN resolves.

    `check` cannot prove this: `/v1/models` lists aliases only (measured
    2026-09-29). One cheap noul is the only honest way to show that the model id
    this pass pins actually answers -- and the resolved `model` in the response
    is the field the record keeps, so printing it is the point.

    Cost: one noul over a one-sentence state is a few hundred input tokens,
    about $0.00001 at $0.042/Mtok. Cheap enough to be a routine check, stated
    because spending money is not this command's to do silently.
    """
    from harness import jev
    try:
        out = jev.ask(
            "This is a connectivity probe from the consolidation pass.",
            {"reachable": {"type": "noul",
                           "instructions": "Is this a connectivity probe?",
                           "criteria": {"true": "a probe",
                                        "false": "not a probe"}}})
    except jev.JevError as exc:
        print(f"[familiar] jev probe: {exc.kind}: {exc}", file=sys.stderr)
        return 2 if exc.fatal else 3
    got = jev.answer_fields(out["answers"]["reachable"])
    usage = out.get("usage", {})
    print(f"resolved: {out.get('model')!r}")
    print(f"pinned  : {jev.MODEL}")
    if out.get("model") != jev.MODEL:
        print(f"[familiar] jev probe: the alias resolved to "
              f"{out.get('model')!r}, not the pin {jev.MODEL!r} — record which "
              f"one spoke before trusting a probability", file=sys.stderr)
        return 4
    print(f"answer  : {got}")
    print(f"usage   : {usage.get('input_tokens', 0)} in, "
          f"{usage.get('output_tokens', 0)} out → "
          f"${jev.cost_usd(usage):.6f}")
    return 0


def show_queue(inv) -> int:
    """The read-only view (item 1b): numbered rows in band order, no commands.

    `--all` includes resolved items, which is what makes the queue auditable
    after a `decide`: the default view is "what still needs me", and a list that
    silently dropped resolved rows could not be compared against last night's.
    """
    from consolidation import queue
    try:
        its = queue.items(inv.base)
    except ValueError as exc:
        print(f"[familiar] {exc}", file=sys.stderr)
        return 2
    if inv.has("--json"):
        print(json.dumps(queue.load(inv.base), ensure_ascii=False, indent=2))
        return 0
    shown = its if inv.has("--all") else queue.unresolved(its)
    if not shown:
        print("the queue is empty — nothing has been proposed, or everything "
              "is resolved (`--all` to see resolved items)")
        return 0
    print(f"queue — {len(queue.unresolved(its))} open of {len(its)}, "
          f"digest {queue.digest(its)}")
    for n, it in enumerate(its, 1):
        if it in shown:
            row = queue.Item(**{k: it[k] for k in
                               ("id", "kind", "target", "summary", "first_seen",
                                "nights", "members", "outliers", "band",
                                "recommendation", "resolution", "target_kind",
                                "why", "stage") if k in it}).row(n)
            if it.get("resolution"):
                row += "  [resolved]"
            elif it.get("recommendation"):
                rec = it["recommendation"]
                row += f"  → {rec.get('action', '?')}" if isinstance(rec, dict) else ""
            print(row)
    print("\n`familiar consolidation decide N` resolves item N.")
    return 0


# Kinds whose resolution `dismiss` already owns. `decide` DISPATCHES to it
# rather than writing its own row, so there is one resolution record and one
# writer per kind (item 1g). Frontmatter edits (dangling-link, extend-leaf) are
# NOT here -- the pass cannot repair those itself (associate.py: a dangling
# `related:` is "a REPORT LINE, not a deletion"), so `decide` writes them.
def _one_resolution(inv, it: dict, accepted: bool, partial: bool,
                    note: str = "", choice: str = "") -> str:
    """Record one resolution through `consolidation.resolve`, the one writer.

    `choice` names the answer for the kinds that have their own (a decision:
    land / superseded / drop / note); without it, `accepted` picks accept or
    refuse. A decision without a choice is refused by `resolve.apply` rather
    than guessed: accepting one used to record a dismissal and land nothing.
    """
    from consolidation import resolve
    return resolve.apply(inv.base, inv.agents.parent, it,
                         choice or ("accept" if accepted else "refuse"),
                         note=note, by=inv.get("--by") or "")


def decide(inv) -> int:
    """Resolve what the pass proposed (item 1c), through the queue's numbering.

    `decide N` does the recommended thing; `--no` refuses; `--partial` accepts
    the item's sample but not its low-confidence outliers; `--kind=K --all`
    resolves the rest of a kind; `--walk` is the interactive pass.

    STALENESS IS CHECKED FIRST (1d). The queue carries a digest; `decide`
    compares it against the hash the report printed and refuses with exit 3 when
    the file has moved. Without this, `decide 3` after another `decide` resolved
    item 3 would silently act on item 4 -- the failure mode is not a crash, it
    is doing the wrong thing quietly.
    """
    from consolidation import queue
    try:
        data = queue.load(inv.base)
    except ValueError as exc:
        print(f"[familiar] {exc}", file=sys.stderr)
        return 2
    its = data["items"]
    if not its:
        print("the queue is empty — nothing to decide", file=sys.stderr)
        return 1
    # STALENESS, and why it needs no flag (item 1d). `save` writes the digest
    # of what it wrote; `load` hands that digest back. Recomputing it here over
    # the items just read detects a file edited or truncated under the CLI by
    # anything other than `save` -- which is the "the queue has moved" case,
    # and the reason the report prints the digest: a reader comparing the two
    # is looking at the same guarantee this check enforces.
    #
    # It is deliberately NOT a user-passed hash. `PLAN.md` §The queue: "Five
    # forms, no quoting, no paths, no hashes" -- a hash the user must paste is a
    # hash they will paste wrong, and the guard would then refuse valid work.
    recomputed = queue.digest(its)
    if data.get("digest") != recomputed:
        print(f"[familiar] the queue file has moved under the CLI "
              f"(stored digest {data.get('digest')}, recomputed {recomputed}).\n"
              f"  Nothing was written. Run `familiar consolidation run` or re-read "
              f"`familiar consolidation queue`.", file=sys.stderr)
        return 3
    if inv.has("--walk"):
        return _walk(inv, its, note=inv.get("--note"))
    if inv.get("--kind"):
        k = inv.get("--kind")
        if not inv.has("--all"):
            print(f"[familiar] --kind={k} needs --all "
                  f"(or name an ordinal: familiar consolidation decide N)", file=sys.stderr)
            return 1
        targets = queue.of_kind(its, k)
        if not targets:
            print(f"no open items of kind {k}", file=sys.stderr)
            return 1
        n = 0
        try:
            for it in targets:
                _one_resolution(inv, it, accepted=not inv.has("--no"), partial=False,
                                note=inv.get("--note"), choice=inv.get("--choice"))
                n += 1
        except ValueError as exc:
            print(f"[familiar] {exc}", file=sys.stderr)
            return 1
        verb = inv.get("--choice") or ("refused" if inv.has("--no") else "accepted")
        print(f"{verb} {n} item(s) of kind {k}")
        return 0
    if not inv.rest:
        print(f"usage: familiar consolidation {DECIDE.usage}", file=sys.stderr)
        return 1
    try:
        n = int(inv.rest[0])
    except ValueError:
        raise UsageError_for_decide(inv.rest[0])
    it = queue.by_ordinal(its, n)
    if it is None:
        print(f"[familiar] {queue.raise_ordinal_error(n, len(its))}",
              file=sys.stderr)
        return 1
    # `--why` shows the item in full and resolves nothing: the report row now
    # carries only the one-line summary (a `decision` item's reason is
    # paragraphs long and would wrap the row), so this is where it is read. The
    # walk's `?` key is the same answer, per item.
    if inv.has("--why"):
        print(f"{n}: {it['kind']}  {it['target']}  ({it.get('target_kind')}, "
              f"stage {it.get('stage')}, night {it.get('nights', 1)})")
        print(f"\n{it.get('summary', '')}")
        if it.get("why"):
            print(f"\n{it['why']}")
        print(f"\nNothing resolved. `decide {n}` acts; `decide {n} --no` refuses.")
        return 0
    accepted = not inv.has("--no")
    note = inv.get("--note")
    try:
        what = _one_resolution(inv, it, accepted, inv.has("--partial"), note,
                               choice=inv.get("--choice"))
    except ValueError as exc:
        print(f"[familiar] {exc}", file=sys.stderr)
        return 1
    print(f"{n}: {it['kind']} {it['target']} — {what}")
    if inv.has("--partial") and it.get("outliers"):
        print(f".  {len(it['outliers'])} outlier(s) left open — they are "
              f"separate numbered items")
    return 0


def UsageError_for_decide(raw):
    """A non-numeric ordinal is a usage error, not a traceback."""
    from lib import invocation
    return invocation.UsageError(f"decide wants an item number, got {raw!r}")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


#: The walk's key per answer. `s` is skip, so superseded is `p` (rePlaced).
_KEYS = {"accept": "y", "refuse": "n", "land": "l", "superseded": "p", "drop": "d",
         "note": "t"}


def _walk(inv, its: list, note: str = "") -> int:
    """The interactive pass: the item's own answers (`resolve.choices`), then
    a / s / ? / q.

    Driven from a pipe as well as a terminal, because a test drives it that way
    and because the same keys are what a script would send. An unrecognised key
    re-asks rather than guessing: assuming `y` is the failure this walk exists to
    avoid. `a` (the rest of this kind) exists only for accept/refuse kinds: a
    batch of decisions has no one answer.
    """
    from consolidation import queue, resolve
    open_ = [it for it in its if not it.get("resolution")]
    if not open_:
        print("nothing open to walk")
        return 0
    i = 0
    while i < len(open_):
        it = open_[i]
        n = its.index(it) + 1
        opts = resolve.choices(it)
        keys = {_KEYS[c]: c for c in opts}
        batch = opts == resolve.DEFAULT_CHOICES
        menu = " / ".join(f"[{_KEYS[c]}] {resolve.LABELS[c]}" for c in opts)
        menu += (" / [a]ll of this kind" if batch else "") + " / [s]kip / [?]full / [q]uit"
        short = " / ".join(list(keys) + (["a"] if batch else []) + ["s", "?", "q"])
        print(f"\n{n}. {it['kind']}  {it['target']}"
              + (f"  [nights: {it['nights']}]" if it.get("nights", 1) > 1 else ""))
        print(f"   {it.get('summary', '')}")
        try:
            key = input(f"   {menu} > ").strip().lower()
            if key in keys:
                choice, by, text = keys[key], "", note
                if choice == "superseded":
                    by = input("   superseded by (id) > ").strip()
                elif choice == "note":
                    text = input("   note > ").strip()
        except EOFError:
            print("\n(end of input — stopping the walk)")
            return 0
        if key in keys:
            try:
                what = resolve.apply(inv.base, inv.agents.parent, it, choice,
                                     note=text, by=by)
            except ValueError as exc:
                print(f"   {exc}")
                continue
            print(f"   → {what}")
            i += 1
        elif key == "a" and batch:
            rest = [x for x in its if x.get("kind") == it["kind"] and not x.get("resolution")]
            for x in rest:
                resolve.apply(inv.base, inv.agents.parent, x, "accept", note=note)
            print(f"   → accepted {len(rest)} of kind {it['kind']}")
            return 0
        elif key == "s":
            i += 1
        elif key == "?":
            print(f"   target_kind: {it.get('target_kind')}  stage: {it.get('stage')}")
            print(f"   {it.get('why') or '(no further detail)'}")
        elif key == "q":
            print("   (quit — nothing more resolved)")
            return 0
        else:
            print(f"   {short}")
    print("\nwalk finished")
    return 0


ONTOLOGY = invocation.Spec(
    name="ontology",
    usage="ontology facets|subjects|relations|branches|violations|corpus|check|"
          "naming|review|selfcheck",
    positional="facets|subjects|relations|branches|violations|corpus|check|"
               "naming|review|selfcheck")


def ontology_cmd(inv) -> int:
    """`ontology` -- read the class list, and run the structural checks.

    A DECLARED SUBCOMMAND IS THE ONLY FORM. An undeclared one exits 1 with the
    list, the same rule `invocation` sets for flags: a surface that guesses at
    what it was asked is a surface that answers the wrong question quietly.

    Exit codes follow the register's own governance rule, which is the whole
    point of the module: an open violation a register entry DECLARES warns and
    exits 0, because a known gap must not read as a broken build; a value nobody
    declared exits 1. `review` always exits 0 -- a stale definition is a signal.
    """
    from knowledge import ontology, ontology_render
    table = ONTOLOGY.positional.split("|")
    cmd = inv.rest[0] if inv.rest else ""
    if inv.help or not cmd:
        print(f"usage: familiar consolidation {ONTOLOGY.usage}",
              file=sys.stdout if inv.help else sys.stderr)
        if inv.help:
            print("\n  facets      the register, with domains and columns\n"
                  "  subjects    the registered subjects, with name, criteria, reviewed\n"
                  "  relations   the walkable register and the coincidences\n"
                  "  branches    the three top branches and their lifecycles\n"
                  "  violations  every known breach, its recommendation, state\n"
                  "  corpus      the 31 leaves as (subject, path) -- O4's ground\n"
                  "              truth, ratified by where O2b put each one\n"
                  "  check       the structural half: branches, subjects, facet\n"
                  "              values, identifiers, relation endpoints, names\n"
                  "  naming      the file-naming rules alone (1-9; 4, 8, 9 unchecked)\n"
                  "  review      register entries past the 180 d cadence\n"
                  "  selfcheck   the registers against each other; raises on drift")
            return 0
        return 1
    if cmd not in table:
        print(f"[familiar] unknown ontology subcommand: {cmd}\n"
              f"usage: familiar consolidation {ONTOLOGY.usage}", file=sys.stderr)
        return 1

    if cmd == "selfcheck":
        try:
            ontology.selfcheck()
        except ontology.Inconsistent as exc:
            print(f"[familiar] {exc}", file=sys.stderr)
            return 1
        print("ontology selfcheck: registers agree")
        return 0

    if cmd in ontology_render.VIEWS:
        # The register's columns are the renderer's knowledge, not this
        # module's (dev/architecture 4a). Exit 0: these five are views.
        for line in ontology_render.VIEWS[cmd]():
            print(line)
        return 0

    if cmd == "corpus":
        # O4a. Printed as `subject<TAB>path` so the dump is both readable and
        # cut-able; the count is on stderr so it cannot contaminate a pipe.
        rows = ontology.corpus()
        for rel, subject in rows:
            print(f"{subject or '-':<12}\t{rel}")
        missing = [r for r, s in rows if not s]
        print(f"\ncorpus: {len(rows)} leaf/leaves, "
              f"{len({s for _, s in rows if s})} subject(s) represented"
              + (f", {len(missing)} WITHOUT a subject" if missing else ""),
              file=sys.stderr)
        return 1 if missing else 0

    if cmd == "review":
        for line in ontology.review_lines():
            print(line)
        return 0

    if cmd in ("check", "naming"):
        findings = (ontology.naming_findings() if cmd == "naming"
                    else ontology.structural_findings())
        warns = [f for f in findings if f.level == "warn"]
        errs = [f for f in findings if f.level == "error"]
        for f in findings:
            print(f.line())
        declared = sorted({f.violation for f in warns if f.violation})
        if declared:
            print(f"\ndeclared (violations "
                  f"{', '.join(str(n) for n in declared)}) -- a known gap "
                  f"warns; it does not fail:")
            for v in ontology.violations():
                if v.n in declared:
                    print(f"  {v.n}  {v.what}")
                    print(f"     → {v.recommendation}  [{v.state}]")
        print(f"\nontology {cmd}: {len(findings)} finding(s) -- {len(warns)} "
              f"declared warning(s), {len(errs)} undeclared error(s).")
        if cmd == "naming":
            files = sorted({f.where for f in findings})
            print(f"naming rules 1-9 (4, 8, 9 unchecked): {len(files)} file(s) named, in "
                  f"violation(s) {', '.join(str(n) for n in declared) or 'none'} "
                  f"of SPECS.md O1k. Rules are declared once in "
                  f"ontology.NAMING; nothing here is renamed.")
        return 1 if errs else 0

    return 1




def opencode_session(inv) -> int:
    """opencode's half of journal/ coverage. opencode has no per-session
    transcript file (opencode-plugin/index.js's `captureSessionIdle` docstring)
    -- sessions live in one SQLite DB. Called from the plugin's `session.idle`
    hook as a second, independent, best-effort spawn alongside the existing
    `capture --harness=opencode --event=session-end` call: this one stages a
    transcript if it can, that one always logs the session as ACTIVE either
    way. A failure here writes nothing and says so on stderr -- it must never
    surface in, or block, the user's session (same fail-open rule as capture.py).
    """
    from context import opencode_extract

    sid = inv.get("--session")
    if not sid:
        print(f"usage: familiar consolidation {OPENCODE_SESSION.usage}", file=sys.stderr)
        return 1
    db = pathlib.Path(inv.get("--db") or opencode_extract.DEFAULT_DB)
    result = opencode_extract.extract_session(db, sid)
    if result is None:
        sys.stderr.write(f"[familiar] opencode-session: {sid} not found in {db}\n")
        return 0
    meta, rows = result
    if not rows:
        sys.stderr.write(f"[familiar] opencode-session: {sid} has no user/assistant "
                         f"prose; nothing to stage\n")
        return 0
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = inv.base / "transcripts" / f"{now}_opencode_{sid}.jsonl"
    opencode_extract.write_jsonl(rows, dest)
    log = inv.base / "session.log"
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with log.open("a") as fh:
        fh.write(f"{now_iso}\topencode\t{sid}\t{meta['cwd']}\t{dest}\n")
    sys.stderr.write(f"[familiar] captured transcript: {dest}\n")
    return 0


def hermes_session(inv) -> int:
    """Hook-facing half of Hermes journal/ coverage. Unlike Pi/opencode,
    Hermes's shell hooks are SYNCHRONOUS: `~/.hermes/config.yaml`'s
    `on_session_end` blocks session shutdown for up to the hook's configured
    `timeout` (agent/shell_hooks.py `_spawn`, waits on `proc.communicate`).
    The actual extraction shells out to `hermes sessions export`, which opens
    another Python venv and queries state.db -- too slow to trust inside that
    window. So this command does almost nothing: read the payload Hermes
    already piped on stdin, pull `session_id`, and hand off to a DETACHED
    worker (`hermes-session-worker`, this module) that outlives it -- same
    shape as Pi's and opencode's `spawn(...).unref()`, just done from Python
    since Hermes gives this one synchronous slot to work with. shell_hooks.py
    itself documents the pattern this relies on: "an intentionally detached
    helper (`some-daemon &`) survives a successful run" (process_group=0).
    """
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    sid = payload.get("session_id")
    if not sid:
        sys.stderr.write("[familiar] hermes-session: no session_id in payload\n")
        return 0
    # `familiar` is the only entry point (3b): the worker is one of its routes,
    # and calling the front door keeps the route table the one declaration.
    bin_path = pathlib.Path(__file__).resolve().parents[1] / "familiar"
    try:
        subprocess.Popen(
            [str(bin_path), "context", "hermes-session-worker", f"--session={sid}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass   # best-effort; never let this block or fail session shutdown
    return 0


def hermes_session_worker(inv) -> int:
    """The actual extraction. Runs detached (spawned by `hermes_session`
    above), so it may take as long as `hermes sessions export` needs to.
    """
    from context import hermes_extract

    sid = inv.get("--session")
    if not sid:
        print(f"usage: familiar consolidation {HERMES_SESSION_WORKER.usage}", file=sys.stderr)
        return 1
    result = hermes_extract.extract_session(sid)
    if result is None:
        sys.stderr.write(f"[familiar] hermes-session-worker: {sid} did not "
                         f"export (unknown session, or `hermes` failed)\n")
        return 0
    meta, rows = result
    if not rows:
        sys.stderr.write(f"[familiar] hermes-session-worker: {sid} has no "
                         f"user/assistant prose; nothing to stage\n")
        return 0
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = inv.base / "transcripts" / f"{now}_hermes_{sid}.jsonl"
    hermes_extract.write_jsonl(rows, dest)
    log = inv.base / "session.log"
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with log.open("a") as fh:
        fh.write(f"{now_iso}\thermes\t{sid}\t{meta['cwd']}\t{dest}\n")
    sys.stderr.write(f"[familiar] captured transcript: {dest}\n")
    return 0
