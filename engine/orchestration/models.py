"""models -- load the catalogue, check its schema and compare it with a harness.

`config/orchestration/models.yaml` is the curated, harness-agnostic catalogue
(decisions 20, 22, 25). The vendor is the source of truth for a model's context,
output limit and capabilities; a harness (pi) carries its own table of the same
facts, and it can be wrong. `--check` fails on three things:

- the schema: a required field missing or mistyped, a duplicate id, or an entry
  whose `verified` is older than `stale_after_days`;
- a callable model that pi does not list under its provider;
- an overlapping field (context, max out, thinking, images) where pi and the
  vendor disagree, the message naming both sides.

KNOWN DEFECTS. A disagreement that is the harness's error is recorded in
`config/orchestration/harness-defects.yaml` and then reported, not failed. A
record whose disagreement has gone fails instead, so the file cannot rot.
The catalogue is never edited to match the harness.

A VENDOR WITHOUT A KEY is unavailable (decision 26): `pi --list-models` lists
only providers whose key is in the environment, so an unlisted provider is a
skipped note, not a failure. Vendors with no pi provider (Jev) are skipped by
name. The parser of pi's table is pure so tests feed it text and never run pi.

The vendor-to-provider map is the ACTIVE profile's (`profiles.py`): under `pi-work`
the deepseek models are compared under `deepseek-work`.

`--explain <id>` (item 2i) hooks in at `main`; `--resolve <id>` [`--approve=REASON`]
is the profile resolver (item 2j).
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import pathlib
import re
import sys

from harness import pi_call
from lib import _miniyaml
from lib import roots
from orchestration import profiles

CATALOGUE = roots.SUBAGENTS / "models.yaml"
DEFECTS = roots.SUBAGENTS / "harness-defects.yaml"
CAPABILITIES = roots.SUBAGENTS / "capabilities.yaml"

KINDS = ("chat", "typed", "embed")
JURISDICTIONS = ("local", "EU", "US", "CN")
POOLS = ("quota", "usd", "free")
YESNO = ("yes", "no")
THINKING = ("no", "yes", "adaptive", "always")
GRADES = ("A", "B", "C", "D")
TOLERANCE = 0.05                    # vendors write 256k for 262144
PI_TIMEOUT = 30


@dataclasses.dataclass
class Finding:
    where: str                      # model id, or "catalogue"
    message: str
    fail: bool = True

    def __str__(self) -> str:
        return f"{self.where}: {self.message}"


def load(path: pathlib.Path = CATALOGUE) -> dict:
    return _miniyaml.load(path.read_text(encoding="utf-8"))


def entries(cat: dict) -> list:
    """(section, entry) for every callable model and candidate."""
    return [(s, e) for s in ("models", "candidates") for e in cat.get(s) or []]


# --- schema ---------------------------------------------------------------

def _int(v) -> bool:
    return isinstance(v, str) and v.isdigit()


def _num(v) -> bool:
    try:
        float(v)
    except (TypeError, ValueError):
        return False
    return True


def _date(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(v)
    except (TypeError, ValueError):
        return None


def _entry_findings(e: dict) -> list:
    """Messages for one entry, without its id prefix."""
    out = []
    got = lambda *path: _dig(e, path)

    def need(path, ok, expect):
        v = got(*path)
        if v is None:
            out.append(f"{'.'.join(path)}: missing")
        elif not ok(v):
            out.append(f"{'.'.join(path)}: {v!r} is not {expect}")

    one_of = lambda *vals: (lambda v: v in vals)
    for f in ("id", "name", "vendor"):
        need((f,), lambda v: isinstance(v, str) and v, "a non-empty string")
    need(("kind",), one_of(*KINDS), "one of " + "|".join(KINDS))
    need(("jurisdiction",), one_of(*JURISDICTIONS), "one of " + "|".join(JURISDICTIONS))
    need(("pool",), one_of(*POOLS), "one of " + "|".join(POOLS))
    need(("context",), _int, "an integer")
    need(("cost", "in"), _num, "a number")
    need(("cost", "out"), _num, "a number")
    need(("capabilities", "tools"), one_of(*YESNO), "yes|no")
    need(("capabilities", "vision"), one_of(*YESNO), "yes|no")
    need(("capabilities", "thinking"), one_of(*THINKING), "one of " + "|".join(THINKING))
    need(("sources",), lambda v: isinstance(v, list) and v, "a non-empty list")
    need(("verified",), lambda v: _date(v) is not None, "an ISO date")
    if got("max_out") is not None and not _int(got("max_out")):
        out.append(f"max_out: {got('max_out')!r} is not an integer")
    for i, b in enumerate(got("benchmarks") or []):
        if not isinstance(b, dict):
            out.append(f"benchmarks[{i}]: not a mapping")
            continue
        for f in ("name", "source"):
            if not b.get(f):
                out.append(f"benchmarks[{i}].{f}: missing")
        if not _num(b.get("score")):
            out.append(f"benchmarks[{i}].score: {b.get('score')!r} is not a number")
        if _date(b.get("date")) is None:
            out.append(f"benchmarks[{i}].date: {b.get('date')!r} is not an ISO date")
        if b.get("grade") not in GRADES:
            out.append(f"benchmarks[{i}].grade: {b.get('grade')!r} is not one of A|B|C|D")
    return out


def _dig(d, path):
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
    return d


def schema_findings(cat: dict) -> list:
    out, seen = [], set()
    for section, e in entries(cat):
        eid = e.get("id") or f"<unnamed {section} entry>"
        out += [Finding(eid, m) for m in _entry_findings(e)]
        if e.get("id") in seen:
            out.append(Finding(eid, "duplicate id"))
        seen.add(e.get("id"))
    return out


def stale_findings(cat: dict, today: datetime.date) -> list:
    days = cat.get("stale_after_days")
    if not _int(days):
        return [Finding("catalogue", f"stale_after_days: {days!r} is not an integer")]
    out = []
    for _, e in entries(cat):
        d = _date(e.get("verified"))
        if d and (today - d).days > int(days):
            out.append(Finding(e.get("id", "?"),
                               f"verified {d} is {(today - d).days} days old (limit {days})"))
    return out


# --- pi's table -----------------------------------------------------------

_SIZE = re.compile(r"^(\d+(?:\.\d+)?)([KM]?)$")


def size(text: str) -> float | None:
    """'262.1K' -> 262100.0; None when it is not a size."""
    m = _SIZE.match(text.strip())
    return float(m.group(1)) * {"": 1, "K": 1e3, "M": 1e6}[m.group(2)] if m else None


def parse_pi_table(text: str) -> dict:
    """{provider: {model: {context, max_out, thinking, images}}}, values as pi
    prints them. The header row and anything that is not six columns is skipped."""
    rows: dict = {}
    for line in text.splitlines():
        c = line.split()
        if len(c) != 6 or c[0] == "provider":
            continue
        rows.setdefault(c[0], {})[c[1]] = dict(
            context=c[2], max_out=c[3], thinking=c[4], images=c[5])
    return rows


def run_pi() -> str:
    """`pi --list-models`, through the one place a pi process starts. A failure is
    `pi_call.PiError`, a `RuntimeError` as before."""
    return pi_call.list_models(timeout=PI_TIMEOUT)


# --- comparison -----------------------------------------------------------

def _aliases(e: dict) -> list:
    return [a.strip() for a in (e.get("aliases") or "").split(",") if a.strip()]


def _pi_row(e: dict, listed: dict):
    """The pi row for an entry: by id first, then by the first alias pi lists."""
    for name in [e["id"], *_aliases(e)]:
        if name in listed:
            return name, listed[name]
    return None, None


def _same_size(pi_text: str, vendor: str) -> bool:
    a, b = size(pi_text), float(vendor)
    return a is not None and abs(a - b) <= TOLERANCE * b


def disagreements(e: dict, row: dict) -> list:
    """(field, pi text, catalogue text) for each overlapping field that differs."""
    out = []
    for f in ("context", "max_out"):
        if e.get(f) is not None and not _same_size(row[f], e[f]):
            out.append((f, row[f], e[f]))
    thinking = "no" if e["capabilities"]["thinking"] == "no" else "yes"
    if row["thinking"] != thinking:
        out.append(("thinking", row["thinking"], thinking))
    if row["images"] != e["capabilities"]["vision"]:
        out.append(("images", row["images"], e["capabilities"]["vision"]))
    return out


def load_defects(path: pathlib.Path = DEFECTS) -> list:
    """Records under `pi:`; an empty file or a bare `pi:` is no records."""
    data = _miniyaml.load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return (data or {}).get("pi") or []


@dataclasses.dataclass
class Report:
    findings: list
    n_models: int = 0
    known: int = 0
    skipped: int = 0

    @property
    def failures(self) -> int:
        return sum(f.fail for f in self.findings)


def compare(cat: dict, pi: dict, defects: list, provider_map: dict | None = None) -> Report:
    """Callable models against pi's table, defects applied. Notes carry fail=False.
    `provider_map` is vendor -> pi provider; the default is the private profile's."""
    provider_map = provider_map or profiles.providers("private")
    rep = Report([])
    used, unchecked = set(), set()
    note_providers = set()
    for e in cat.get("models") or []:
        rep.n_models += 1
        eid, vendor = e.get("id", "?"), e.get("vendor")
        provider = provider_map.get(vendor)
        if provider in (None, "none"):
            rep.skipped += 1
            rep.findings.append(Finding(eid, f"skipped: no pi provider for vendor {vendor!r}", False))
            unchecked.add(eid)
            continue
        if provider not in pi:
            rep.skipped += 1
            unchecked.add(eid)
            if provider not in note_providers:
                note_providers.add(provider)
                rep.findings.append(Finding(
                    provider, f"skipped: pi lists no {provider} models (no key in this environment?)",
                    False))
            continue
        name, row = _pi_row(e, pi[provider])
        if row is None:
            rep.findings.append(Finding(eid, f"pi lists no {eid!r} under {provider}"
                                        + (f" (aliases tried: {', '.join(_aliases(e))})" if _aliases(e) else "")))
            continue
        for field, said, truth in disagreements(e, row):
            msg = f"{field}: pi says {said}, catalogue (vendor) says {truth}"
            hit = next((d for d in defects if d.get("model") == eid and d.get("field") == field
                        and d.get("harness_says") == said), None)
            if hit:
                used.add(id(hit))
                rep.known += 1
                rep.findings.append(Finding(eid, f"known pi defect: {msg} -- {hit.get('note', '')}", False))
            else:
                rep.findings.append(Finding(eid, msg))
    for d in defects:
        if id(d) in used:
            continue
        where = d.get("model", "?")
        if where in unchecked:
            rep.findings.append(Finding(where, f"known pi defect on {d.get('field')} not checkable here", False))
        else:
            rep.findings.append(Finding(
                where, f"{d.get('field')}: resolved, remove from harness-defects.yaml"))
    return rep


def check(cat: dict, pi_text: str, defects: list, today: datetime.date,
          provider_map: dict | None = None) -> Report:
    rep = compare(cat, parse_pi_table(pi_text), defects, provider_map)
    rep.findings = schema_findings(cat) + stale_findings(cat, today) + rep.findings
    return rep


# --- capabilities (2i) ------------------------------------------------------

def load_capabilities(path: pathlib.Path = CAPABILITIES) -> dict:
    return _miniyaml.load(path.read_text(encoding="utf-8"))


def _names(caps: dict) -> dict:
    """Benchmark name as written in models.yaml -> its canonical key."""
    return {n: key for key, b in (caps.get("benchmarks") or {}).items()
            for n in b.get("names") or []}


def capability_findings(caps: dict) -> list:
    """A capability naming an undefined benchmark, a task class naming an
    undefined capability, or one name claimed by two benchmarks."""
    out = []
    benches = caps.get("benchmarks") or {}
    capdefs = caps.get("capabilities") or {}
    seen: dict = {}
    for key, b in benches.items():
        for n in b.get("names") or []:
            if n in seen:
                out.append(Finding("capabilities", f"benchmark name {n!r} is claimed by {seen[n]} and {key}"))
            seen[n] = key
    for name, c in capdefs.items():
        for b in (c or {}).get("benchmarks") or []:
            if b not in benches:
                out.append(Finding("capabilities", f"capability {name} names undefined benchmark {b}"))
    for tc, t in (caps.get("task_classes") or {}).items():
        for c in (t or {}).get("capabilities") or []:
            if c not in capdefs:
                out.append(Finding("capabilities", f"task class {tc} names undefined capability {c}"))
    return out


def scores(cat: dict, caps: dict) -> dict:
    """{benchmark key: {model id: score}} over every catalogue entry, callable
    and candidate. A name no benchmark claims is not scored (see `unmapped`)."""
    names = _names(caps)
    out: dict = {}
    for _, e in entries(cat):
        for b in e.get("benchmarks") or []:
            key = names.get(b.get("name"))
            if key and _num(b.get("score")):
                out.setdefault(key, {})[e["id"]] = float(b["score"])
    return out


def unmapped(cat: dict, caps: dict) -> list:
    """(model id, benchmark name) pairs that no `names:` list claims."""
    names = _names(caps)
    return [(e["id"], b.get("name")) for _, e in entries(cat)
            for b in e.get("benchmarks") or [] if b.get("name") not in names]


def percentile(model_id: str, by_model: dict) -> float | None:
    """Share of the OTHER scored models this one beats, ties counting half.
    None when it has no score, or when nobody else does (nothing to rank)."""
    if model_id not in by_model or len(by_model) < 2:
        return None
    mine = by_model[model_id]
    others = [v for k, v in by_model.items() if k != model_id]
    beaten = sum(1.0 if v < mine else 0.5 if v == mine else 0.0 for v in others)
    return 100.0 * beaten / len(others)


def efforts(cat: dict, model_id: str) -> tuple[list, str]:
    """(the levels the catalogue lists for this model, what it says about
    thinking). `capabilities.effort` is a vendor-published list ("low, medium,
    high, xhigh, max" for the Claude models); `capabilities.thinking` is
    `always`, `adaptive` or `yes`. An empty list means the catalogue does not say,
    which is NOT the same as "unsupported": the caller decides whether to accept
    an unverifiable level, and must never silently clamp one."""
    e = next((x for x in cat.get("models") or [] if x.get("id") == model_id), None)
    if e is None:
        return [], ""
    cap = e.get("capabilities") or {}
    return [x.strip() for x in str(cap.get("effort") or "").split(",") if x.strip()], \
        str(cap.get("thinking") or "")


def effort_reason(cat: dict, model_id: str, level: str) -> str:
    """'' when the level is admissible, else why not. A model with no published
    list accepts any level (the harness may ignore it); a model WITH a list
    refuses one outside it, because that is a request the vendor cannot serve."""
    if not level or level == "off":
        return ""                      # asking for no thinking is always admissible
    listed, thinking = efforts(cat, model_id)
    if thinking == "no":
        return (f"{model_id}: the catalogue says this model does not think "
                f"(thinking: no), so {level} is not a level it has")
    if level in ("minimal", "low") or not listed:
        return ""                      # below the published floor, or nothing published
    if level in listed:
        return ""
    return (f"{model_id} lists {', '.join(listed)}; the request is {level}. "
            f"A level above the list is refused here rather than clamped, because "
            f"the two are not the same request")


def capability_scores(model_id: str, cat: dict, caps: dict) -> dict:
    """{capability: (mean percentile or None, benchmarks used, benchmarks named)}."""
    table = scores(cat, caps)
    out = {}
    for name, c in (caps.get("capabilities") or {}).items():
        benches = (c or {}).get("benchmarks") or []
        pcts = [p for b in benches
                if (p := percentile(model_id, table.get(b, {}))) is not None]
        out[name] = (sum(pcts) / len(pcts) if pcts else None, len(pcts), len(benches))
    return out


def explain(model_id: str, cat: dict, caps: dict) -> str | None:
    e = next((e for _, e in entries(cat) if e["id"] == model_id or model_id in
              [a.strip() for a in (e.get("aliases") or "").split(",")]), None)
    if e is None:
        return None
    section = "callable" if e in (cat.get("models") or []) else "candidate"
    cost = e.get("cost") or {}
    lines = [f"{e['id']}  {e.get('name', '')}  ({e.get('vendor')}, {e.get('kind')}, {section})",
             f"  pool {e.get('pool')}  in {cost.get('in')} / out {cost.get('out')} $/M  "
             f"context {e.get('context')}  jurisdiction {e.get('jurisdiction')}"]
    if e.get("quantised"):
        lines.append(f"  quantised: {e['quantised']} -- public scores are full precision, "
                     f"so any score here is an upper bound")
    caps_ = capability_scores(e["id"], cat, caps)
    lines += ["", "capabilities (percentile among the catalogue entries scored on each "
                  "benchmark, averaged;", "  n = benchmarks behind it, of those the capability names):"]
    for name, (pct, used, named) in caps_.items():
        val = f"{pct:5.0f}" if pct is not None else "  unknown"
        why = "" if pct is not None else (
            "  no benchmark named" if not named else "  no ranked score")
        lines.append(f"  {name:<15}{val:>9}   n = {used} of {named}{why}")
    lines += ["", "task classes (their capabilities, side by side; no combined score):"]
    for tc, t in (caps.get("task_classes") or {}).items():
        parts = []
        for c in (t or {}).get("capabilities") or []:
            pct = caps_.get(c, (None,))[0]
            parts.append(f"{c} {pct:.0f}" if pct is not None else f"{c} unknown")
        lines.append(f"  {tc:<7}{' · '.join(parts)}")
    loose = [n for mid, n in unmapped(cat, caps) if mid == e["id"]]
    if loose:
        lines += ["", "benchmarks in the entry that no capability claims: " + "; ".join(loose)]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration models",
                                 description="Check the model catalogue.")
    ap.add_argument("--check", action="store_true",
                    help="schema, staleness, and agreement with `pi --list-models`")
    ap.add_argument("--resolve", metavar="ID",
                    help="the provider this catalogue id resolves to under the active profile")
    ap.add_argument("--explain", metavar="ID",
                    help="each capability as a percentile within the catalogue, with its benchmark count")
    ap.add_argument("--approve", metavar="REASON",
                    help="with --resolve: borrow another profile's account, logged")
    args = ap.parse_args(argv)
    if args.resolve:
        try:
            res = profiles.resolve(args.resolve, profiles.active(), approve=args.approve)
        except profiles.ProfileError as e:
            print(f"models --resolve: {e}", file=sys.stderr)
            return 2
        print(res.line())
        return 0 if res.available else 1
    if args.explain:
        text = explain(args.explain, load(), load_capabilities())
        if text is None:
            print(f"models --explain: {args.explain!r} is not in the catalogue", file=sys.stderr)
            return 2
        print(text)
        return 0
    if not args.check:
        ap.print_usage(sys.stderr)
        return 2
    try:
        provider_map = profiles.providers(profiles.active())
    except profiles.ProfileError as e:
        print(f"models --check: {e}", file=sys.stderr)
        return 2
    try:
        pi_text = run_pi()
    except pi_call.PiError as e:
        if isinstance(e.__cause__, FileNotFoundError):
            e = "`pi` is not on PATH; cannot compare with its table"
        print(f"models --check: {e}", file=sys.stderr)
        return 1
    rep = check(load(), pi_text, load_defects(), datetime.date.today(), provider_map)
    for f in capability_findings(load_capabilities()):
        rep.findings.append(f)
    for f in rep.findings:
        print(f)
    print(f"models --check: {rep.n_models} model(s), {rep.failures} failure(s), "
          f"{rep.known} known defect(s), {rep.skipped} skipped")
    return 1 if rep.failures else 0
