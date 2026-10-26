#!/usr/bin/env python3
"""evaluation -- is each component worth it? The Threshold's second question.

WHY. The healthcheck answers *is it working?* Nothing answered *is it worth
it?* in one place. Each instrument that measured a component (`orchestration
report` for the delegation nudge, `labels` for dispatch, `posterior` for the
tiers, `rtk gain` for rtk) kept its own numbers, its own window and its own
idea of a verdict, and most components had no instrument at all. This module is
the layer over them (architecture A, ruled 2026-10-25; the leaf is
`memory/knowledge/system/checks/component-evaluation.md`). It rewrites no instrument: an ADAPTER reads one instrument's output and turns it
into READINGS in one metric vocabulary.

THE REGISTRY is `config/checks/components.yaml`: per component, the question,
the design, the instrument, the metrics and the pre-registered floors. It is
policy, and it carries no verdict.

THE RECORD is `<PAZRAS_DATA_DIR>/evaluation.jsonl`, append-only, read through
`consolidation.ledger`. There are two row kinds:
  reading   component, metric, value, n, n_all, interval, method, design, arm,
            gate (the instrument's own gate), window, instrument, batch, registry
  verdict   component, verdict (keep|change|drop), why, readings, decided_by,
            decision (the consolidation decision id), review_by
A reading is derived and can be recomputed while its source logs exist. A
verdict cannot be, so it also lands in git: in the owning leaf's verdict table,
and as a consolidation decision.

THE COMMANDS (`familiar checks evals <verb>`):
  list [--check] [--metrics]   the registry; --check exits 1 on a malformed entry
  read [--dry-run]             one batch: every adapter's readings, appended
  review [--json]              per component READABLE, HELD, NO RULE, GAP or NEVER READ
  verdict <c> keep|change|drop --why TEXT [--review-by DATE]

DISPLAY WEEKLY, DECIDE AT THE GATE. `read` runs weekly on a timer and decides
nothing. `review` proposes a verdict only when every floor's reading has its
instrument's gate open and at least `min_n` attempts (or the floor's own `n>=`). Before that the component
is HELD. This generalises 5d's "recorded whole" ruling of 2026-10-22, and it is
the defence against peeking: about 20 components re-read every week would cross
some threshold by chance. The user rules; `verdict` records.

COVERAGE BEFORE RATE. A rate whose attempts mostly carry no verdict is flagged
`coverage-limited` (below `COVERAGE` of `n_all`). The flag is printed, not
enforced: whether a heuristic floor such as `used` may still support *keep* is
the user's reading, and the leaf states the rule.

EXIT CODES. 0 done. 1 `list --check` found a malformed entry, or `read` had an
adapter fail (the instrument is broken: an is-it-working question, named on
stderr). 2 a usage error.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from lib import _miniyaml, roots  # noqa: E402

REGISTRY = roots.CONFIG / "checks" / "components.yaml"
LEDGER = "evaluation.jsonl"
COVERAGE = 0.8                 # below this share of attempts with a verdict, a rate is coverage-limited
DEFAULT_MIN_N = 30             # 3f's bar, the one threshold the labels already name
REVIEW_DAYS = {"monthly": 30, "quarterly": 91}
VERDICT_DAYS = 90              # a verdict's default life before it is reviewed again


@dataclasses.dataclass(frozen=True)
class Metric:
    unit: str
    better: str                # higher | lower | rule (the floor's operator says)
    definition: str


# The vocabulary. A new metric is an entry here with its definition, never an
# ad-hoc field in a reading (the leaf's §Metrics).
METRICS = {
    "usd_per_verified": Metric("$", "lower", "sum of $ at the rate of each attempt's hour / attempts that passed"),
    "first_pass": Metric("share", "higher", "attempts whose first verify passed / attempts with a verdict"),
    "verified_share": Metric("share", "higher", "attempts with a verdict / all attempts"),
    "uptake": Metric("share", "higher", "offers used / offers with a verdict"),
    "compression": Metric("x", "higher", "median bytes read / bytes returned"),
    "tokens": Metric("tok", "lower", "median frontier tokens per attempt"),
    "wall_seconds": Metric("s", "lower", "median wall-clock per attempt"),
    "overhead_bytes": Metric("B", "lower", "bytes the component adds to every request"),
    "exposure": Metric("/day", "rule", "situations where the component can act, per active day"),
    "attention": Metric("/day", "lower", "the user's interruptions per active day"),
    "effect": Metric("ratio", "rule", "a randomised contrast: ITT, or LATE where the uptake gap allows"),
}
DESIGNS = ("observational", "withholding", "ab", "bandit", "static", "campaign")
KINDS = ("tool", "mechanism", "skill", "model", "extension", "harness")
VERDICTS = ("keep", "change", "drop")
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
       ">": lambda a, b: a > b, "<": lambda a, b: a < b}
REQUIRED = ("kind", "owner", "question", "since", "design", "instrument", "source",
            "metrics", "lands", "review")


# --- the registry --------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Floor:
    metric: str
    op: str
    value: float
    qualifier: str = ""         # a reading's method or arm, e.g. `late`
    min_n: int | None = None    # this floor's own sample bar, over the entry's `min_n`

    def __str__(self) -> str:
        return (f"{self.metric} {self.op} {self.value:g}" + (f" {self.qualifier}" if self.qualifier else "")
                + (f" n>={self.min_n}" if self.min_n is not None else ""))


def parse_floor(text: str) -> Floor:
    """`<metric> <op> <number> [<qualifier>] [n>=<whole>]`, or ValueError naming what
    is wrong. The `n>=` suffix is for a floor whose estimate needs more attempts
    than its entry's other floors: 5d's LATE divides by an uptake gap, so its
    noise is several times a share's at the same n."""
    parts = str(text).split()
    min_n = None
    if parts and parts[-1].startswith("n>="):
        try:
            min_n = int(parts.pop()[3:])
        except ValueError:
            raise ValueError(f"floor {text!r}: `n>=` wants a whole number") from None
        if min_n < 1:
            raise ValueError(f"floor {text!r}: `n>=` must be at least 1")
    if len(parts) not in (3, 4):
        raise ValueError(f"floor {text!r}: want `<metric> <op> <number> [<qualifier>] [n>=<whole>]`")
    metric, op, number = parts[:3]
    if op not in OPS:
        raise ValueError(f"floor {text!r}: operator {op!r} is not one of {', '.join(OPS)}")
    try:
        value = float(number)
    except ValueError:
        raise ValueError(f"floor {text!r}: {number!r} is not a number") from None
    return Floor(metric, op, value, parts[3] if len(parts) == 4 else "", min_n)


def load(path: pathlib.Path = REGISTRY) -> dict:
    """{name: entry} from the registry; an absent file is an empty registry."""
    if not path.is_file():
        return {}
    return (_miniyaml.load(path.read_text(encoding="utf-8")) or {}).get("components") or {}


def registry_hash(path: pathlib.Path = REGISTRY) -> str:
    """The registry's content hash: which rules a reading was taken under."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path.is_file() else ""


def findings(reg: dict, repo: pathlib.Path = roots.REPO) -> list:
    """Every way an entry breaks the registry's contract, as `name: what`."""
    out = []
    for name, e in sorted(reg.items()):
        if not isinstance(e, dict):
            out.append(f"{name}: not a mapping")
            continue
        out += [f"{name}: missing `{k}`" for k in REQUIRED if not e.get(k)]
        if e.get("kind") and e["kind"] not in KINDS:
            out.append(f"{name}: kind {e['kind']!r} is not one of {', '.join(KINDS)}")
        if e.get("design") and e["design"] not in DESIGNS:
            out.append(f"{name}: design {e['design']!r} is not one of {', '.join(DESIGNS)}")
        inst = e.get("instrument")
        if inst and inst != "none" and inst not in ADAPTERS:
            out.append(f"{name}: instrument {inst!r} has no adapter ({', '.join(sorted(ADAPTERS))}, or none)")
        if e.get("review") and e["review"] not in REVIEW_DAYS:
            out.append(f"{name}: review {e['review']!r} is not one of {', '.join(REVIEW_DAYS)}")
        metrics = e.get("metrics") or []
        if not isinstance(metrics, list):
            out.append(f"{name}: `metrics` must be a block list")
            metrics = []
        out += [f"{name}: metric {m!r} is not in the vocabulary" for m in metrics if m not in METRICS]
        floors = e.get("floors") or []
        if not isinstance(floors, list):
            out.append(f"{name}: `floors` must be a block list")
            floors = []
        for f in floors:
            try:
                fl = parse_floor(f)
            except ValueError as exc:
                out.append(f"{name}: {exc}")
                continue
            if fl.metric not in metrics:
                out.append(f"{name}: floor {f!r} names a metric the entry does not declare")
        try:
            if int(e.get("min_n") or DEFAULT_MIN_N) < 1:
                out.append(f"{name}: min_n must be at least 1")
        except (TypeError, ValueError):
            out.append(f"{name}: min_n {e.get('min_n')!r} is not a whole number")
        try:
            datetime.date.fromisoformat(str(e.get("since") or ""))
        except ValueError:
            out.append(f"{name}: since {e.get('since')!r} is not a YYYY-MM-DD date")
        for key in ("owner", "lands"):
            if e.get(key) and not (repo / str(e[key])).exists():
                out.append(f"{name}: {key} {e[key]!r} does not exist")
    return out


# --- readings ------------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96) -> list | None:
    """The 95% Wilson interval of k/n, or None at n = 0."""
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def reading(metric: str, value, n: int, *, method: str, gate: bool, window: dict,
            n_all: int | None = None, interval=None, arm: str | None = None,
            note: str = "") -> dict:
    """One reading, before `read` stamps it with its component, batch and registry."""
    if metric not in METRICS:
        raise ValueError(f"metric {metric!r} is not in the vocabulary")
    return {"metric": metric, "value": None if value is None else round(float(value), 6),
            "n": int(n), "n_all": n_all, "interval": interval, "method": method,
            "arm": arm, "gate": bool(gate), "window": window, "note": note}


# --- adapter 1: `orchestration report` -> delegation-nudge ----------------------

def _report_window(since: str):
    """5d's window, scanned READ-ONLY. `report_main` would rewrite
    `report-last.json`, and the weekly healthcheck's `report --check` compares
    against that file: a read here would hide a regression from it."""
    from orchestration import log                                   # noqa: PLC0415
    return log.scan(since)


def report_readings(name: str, entry: dict, today: datetime.date) -> list:
    since = str(entry["since"])
    w = _report_window(since)
    window = {"since": since, "until": today.isoformat()}
    gate = bool(w.gate[2])
    known = [r for r in w.rows if r.get("used") is not None]
    used = sum(r["used"] is True for r in known)
    sizes = [r["compression"] for r in w.rows if r.get("compression") is not None]
    rnd = w.randomised()
    arms = f"{rnd['nudged']} nudged / {rnd['withheld']} withheld since {w.arms_since}"
    days = {log_day(p) for p in w.logs} - {""}
    return [
        reading("uptake", used / len(known) if known else None, len(known), n_all=len(w.rows),
                interval=wilson(used, len(known)), method="wilson95", gate=gate, window=window,
                note="`used` is a heuristic floor on uptake (5c)"),
        reading("compression", statistics.median(sizes) if sizes else None, len(sizes),
                n_all=len(w.rows), method="median", gate=gate, window=window),
        reading("effect", rnd["ratio"], min(rnd["nudged"], rnd["withheld"]),
                n_all=rnd["nudged"] + rnd["withheld"], method="late", arm="withheld",
                gate=bool(w.arm_gate[2]), window={"since": w.arms_since, "until": today.isoformat()},
                note=arms + (f"; {rnd['why']}" if rnd["why"] else "")),
        reading("effect", rnd["itt"], min(rnd["nudged"], rnd["withheld"]),
                n_all=rnd["nudged"] + rnd["withheld"], method="itt", arm="withheld",
                gate=bool(w.arm_gate[2]), window={"since": w.arms_since, "until": today.isoformat()},
                note=arms),
        reading("exposure", w.fires / len(days) if days else None, w.fires, n_all=w.turns,
                method="per-active-day", gate=True, window=window,
                note=f"{w.fires} fire(s) over {len(days)} active day(s), {w.turns} turn(s)"),
    ]


def log_day(path) -> str:
    from orchestration import log                                   # noqa: PLC0415
    return log.trigger_date(path)


# --- adapter 2: `labels` -> dispatch ---------------------------------------------

def _labels() -> list:
    from orchestration import labels                                # noqa: PLC0415
    return labels.read(labels.labels_path())


def _price(row: dict):
    """(the row's $, why it is unpriced or ''). Unmeasured is not free: a model the
    catalogue cannot price and an all-zero usage are both excluded and counted."""
    from orchestration import price                                 # noqa: PLC0415
    usage = row.get("usage") or {}
    if not any(int(usage.get(k) or 0) for k in ("input", "output", "cache_write", "cache_read")):
        return None, "no usage recorded"
    block = price.block(str(row.get("ran_model") or ""))
    if not block:
        return None, "model not priced"
    try:
        at = datetime.datetime.fromisoformat(str(row.get("ts") or ""))
    except ValueError:
        at = None
    return price.cost(block, usage, at)[0], ""


def labels_readings(name: str, entry: dict, today: datetime.date) -> list:
    """Live `verify` labels only: an eval seed is a campaign, not the user's usage."""
    since = str(entry["since"])
    min_n = int(entry.get("min_n") or DEFAULT_MIN_N)
    window = {"since": since, "until": today.isoformat()}
    rows = [r for r in _labels() if r.get("source") == "verify"
            and str(r.get("ts") or "")[:10] >= since]
    groups: dict = {None: rows}
    for r in rows:
        groups.setdefault(str(r.get("ran_model") or "?").split("/", 1)[-1], []).append(r)
    out = []
    for arm, rs in sorted(groups.items(), key=lambda kv: (kv[0] is not None, kv[0] or "")):
        own = [r for r in rs if r.get("verdict") == "own"]
        firsts = [r for r in own if r.get("attempt") == 1]
        passed = sum(bool(r.get("passed")) for r in firsts)
        priced, skipped, usd, wins = 0, {}, 0.0, 0
        for r in own:
            cost, why = _price(r)
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            priced += 1
            usd += cost
            wins += bool(r.get("passed"))
        skip = "; ".join(f"{n} {why}" for why, n in sorted(skipped.items()))
        out += [
            reading("first_pass", passed / len(firsts) if firsts else None, len(firsts),
                    n_all=len(rs), interval=wilson(passed, len(firsts)), method="wilson95",
                    arm=arm, gate=len(firsts) >= min_n, window=window),
            reading("verified_share", len(own) / len(rs) if rs else None, len(own), n_all=len(rs),
                    method="share", arm=arm, gate=len(rs) >= min_n, window=window),
            reading("usd_per_verified", usd / wins if wins else None, priced, n_all=len(own),
                    method="sum/passes", arm=arm, gate=priced >= min_n, window=window,
                    note=(f"${usd:.4f} over {priced} priced attempt(s), {wins} passed"
                          + (f"; excluded: {skip}" if skip else ""))),
        ]
    return out


ADAPTERS = {
    "orchestration-report": report_readings,
    "labels": labels_readings,
}


# --- the record ----------------------------------------------------------------

def data_dir() -> pathlib.Path:
    return roots.data_root()


def ledger_rows(base: pathlib.Path | None = None) -> list:
    from consolidation import ledger                                # noqa: PLC0415
    return ledger.read(base or data_dir(), LEDGER).rows


def append(rows: list, base: pathlib.Path | None = None) -> None:
    from consolidation import ledger                                # noqa: PLC0415
    for row in rows:
        ledger.append(base or data_dir(), LEDGER, row)


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def take(reg: dict, today: datetime.date, batch: str, rev: str) -> tuple:
    """(readings, failures) for one batch across every measured component."""
    out, failed = [], []
    for name, e in sorted(reg.items()):
        if not isinstance(e, dict):
            failed.append((name, "not a mapping in the registry"))
            continue
        adapter = ADAPTERS.get(e.get("instrument"))
        if adapter is None:
            continue
        try:
            got = adapter(name, e, today)
        except Exception as exc:                      # noqa: BLE001 -- named, then the rest still read
            failed.append((name, f"{type(exc).__name__}: {exc}"))
            continue
        for r in got:
            out.append({"kind": "reading", "ts": batch, "batch": batch, "component": name,
                        "design": e.get("design"), "instrument": e.get("instrument"),
                        "registry": rev, **r})
    return out, failed


# --- review --------------------------------------------------------------------

def _matches(r: dict, fl: Floor) -> bool:
    if r.get("metric") != fl.metric:
        return False
    if fl.qualifier:
        return fl.qualifier in (r.get("method"), r.get("arm"))
    return r.get("arm") is None


def judge(entry: dict, readings: list) -> dict:
    """One component's state from its newest batch: status, per-floor outcomes,
    and the coverage flag. Pure: `review` prints it, the tests call it."""
    if entry.get("instrument") == "none":
        return {"status": "GAP", "floors": [], "coverage": None}
    if not readings:
        return {"status": "NEVER READ", "floors": [], "coverage": None}
    min_n = int(entry.get("min_n") or DEFAULT_MIN_N)
    floors = []
    texts = entry.get("floors") or []
    for text in texts if isinstance(texts, list) else [texts]:
        try:
            fl = parse_floor(text)
        except ValueError as exc:      # `list --check` names it; the screen still shows the rest
            floors.append((str(text), "HELD", None, str(exc)))
            continue
        r = next((x for x in readings if _matches(x, fl)), None)
        if r is None or r.get("value") is None:
            floors.append((fl, "HELD", r, "no value" + (f": {r['note']}" if r and r.get("note") else "")))
        elif not r.get("gate"):
            floors.append((fl, "HELD", r, "the instrument's gate is closed"))
        elif int(r.get("n") or 0) < (fl.min_n or min_n):
            floors.append((fl, "HELD", r, f"n {r['n']} < min_n {fl.min_n or min_n}"))
        else:
            ok = OPS[fl.op](float(r["value"]), fl.value)
            floors.append((fl, "PASS" if ok else "FAIL", r, ""))
    cov = None
    for r in readings:
        if r.get("arm") is not None:
            continue
        if r.get("metric") == "verified_share" and r.get("value") is not None:
            cov = (r["value"], r["n"], r["n_all"])
        elif r.get("metric") in ("uptake", "first_pass") and r.get("n_all"):
            cov = cov or (r["n"] / r["n_all"], r["n"], r["n_all"])
    if not floors:
        status = "NO RULE"
    elif any(s == "HELD" for _, s, _, _ in floors):
        status = "HELD"
    elif all(s == "PASS" for _, s, _, _ in floors):
        status = "READABLE: proposed keep"
    else:
        status = "READABLE: proposed change or drop"
    return {"status": status, "floors": floors,
            "coverage": cov if cov and cov[0] < COVERAGE else None}


def newest(rows: list, name: str, kind: str) -> list:
    """The newest batch of `kind` rows for one component (one row for a verdict)."""
    mine = [r for r in rows if r.get("kind") == kind and r.get("component") == name]
    if not mine:
        return []
    if kind == "verdict":
        return [max(mine, key=lambda r: str(r.get("ts")))]
    last = max(str(r.get("batch")) for r in mine)
    return [r for r in mine if str(r.get("batch")) == last]


def _shown(r: dict | None) -> str:
    if not r or r.get("value") is None:
        return "--"
    v, unit = r["value"], METRICS[r["metric"]].unit
    body = f"{v:.0%}" if unit == "share" else f"${v:.4f}" if unit == "$" else f"{v:.2f}"
    iv = r.get("interval")
    return body + (f" [{iv[0]:.2f}, {iv[1]:.2f}]" if iv else "") + f" n={r.get('n')}"


def review(reg: dict, rows: list, today: datetime.date, out=print) -> list:
    """The monthly screen: per component its state, floors, coverage and verdict."""
    report = []
    reg = {n: e for n, e in reg.items() if isinstance(e, dict)}   # `list --check` names the rest
    out(f"evals review -- {len(reg)} component(s), {today.isoformat()}")
    for name, e in sorted(reg.items(), key=lambda kv: (kv[1].get("instrument") == "none", kv[0])):
        batch = newest(rows, name, "reading")
        j = judge(e, batch)
        v = newest(rows, name, "verdict")
        verdict = v[0] if v else None
        due = ""
        if verdict and str(verdict.get("review_by") or "9999") < today.isoformat():
            due = f"verdict {verdict['verdict']} of {verdict['ts'][:10]} is past review_by"
        elif not verdict and j["status"].startswith("READABLE"):
            due = "a verdict is due"
        report.append({"component": name, "status": j["status"], "due": due,
                       "verdict": verdict and verdict.get("verdict"),
                       "floors": [(str(f), s) for f, s, _, _ in j["floors"]]})
        if j["status"] == "GAP":
            out(f"  GAP        {name:<22} {e.get('design')}: {e.get('source')}")
            continue
        out(f"  {j['status']:<10} {name}" + (f"  [{batch[0]['batch'][:10]}]" if batch else "")
            + (f"  verdict {verdict['verdict']} {verdict['ts'][:10]}" if verdict else ""))
        for fl, s, r, why in j["floors"]:
            out(f"      {s:<4} {str(fl):<28} {_shown(r)}" + (f"  ({why})" if why else ""))
        if not j["floors"]:
            for r in batch:
                if r.get("arm") is None:
                    out(f"      {r['metric']:<18} {_shown(r)}" + (f"  {r['note']}" if r.get("note") else ""))
        if j["coverage"]:
            share, n, n_all = j["coverage"]
            out(f"      coverage-limited: {n}/{n_all} attempt(s) carry a verdict ({share:.0%} < {COVERAGE:.0%})")
        if due:
            out(f"      DUE  {due}: familiar checks evals verdict {name} keep|change|drop --why ...")
    return report


# --- verdict -------------------------------------------------------------------

def record_verdict(name: str, entry: dict, verdict: str, why: str, rows: list,
                   today: datetime.date, review_by: str | None, base: pathlib.Path) -> dict:
    from consolidation import ledger                                # noqa: PLC0415
    batch = newest(rows, name, "reading")
    refs = [f"{r['batch']}/{r['metric']}/{r.get('arm') or r.get('method')}" for r in batch]
    did = ledger.record_decision(base, "decision",
                                 f"Evaluation verdict, {name}: {verdict}. {why}",
                                 context="familiar checks evals verdict")
    row = {"kind": "verdict", "ts": now().isoformat(), "component": name, "verdict": verdict,
           "why": why, "readings": refs, "decided_by": "user", "decision": did,
           "review_by": review_by or (today + datetime.timedelta(days=VERDICT_DAYS)).isoformat()}
    append([row], base)
    return row


# --- the command ---------------------------------------------------------------

def _list(reg: dict, args) -> int:
    if args.metrics:
        for m, d in METRICS.items():
            print(f"  {m:<18} {d.unit:<6} {d.better:<6} {d.definition}")
        return 0
    if args.check:
        found = findings(reg)
        for f in found:
            print(f"  {f}")
        print(f"evals list --check: {len(reg)} component(s), {len(found)} finding(s)")
        return 1 if found else 0
    rows = ledger_rows()
    print(f"evals -- {len(reg)} component(s) in {roots.rel(REGISTRY)}")
    for name, e in sorted(reg.items()):
        v = newest(rows, name, "verdict")
        print(f"  {name:<22} {e.get('kind', ''):<10} {e.get('design', ''):<13} "
              f"{e.get('instrument', ''):<21} " + (f"{v[0]['verdict']} {v[0]['ts'][:10]}" if v else "-"))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="familiar checks evals",
        description="Is each component worth it? The registry, the reading record, the "
                    "review and the verdict (leaf system/checks/component-evaluation.md).")
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("list", help="the registry")
    p.add_argument("--check", action="store_true", help="exit 1 on a malformed entry")
    p.add_argument("--metrics", action="store_true", help="the metric vocabulary")
    p = sub.add_parser("read", help="append one batch of readings from every adapter")
    p.add_argument("--dry-run", action="store_true", help="print the readings, write nothing")
    p = sub.add_parser("review", help="the monthly screen: state, floors, coverage, verdicts")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("verdict", help="record the user's verdict on one component")
    p.add_argument("component")
    p.add_argument("verdict", choices=VERDICTS)
    p.add_argument("--why", required=True, help="the reason, quoted into the decision")
    p.add_argument("--review-by", metavar="DATE",
                   help=f"when to look again (default today + {VERDICT_DAYS} days)")
    args = ap.parse_args(argv)
    try:
        reg = load()
    except ValueError as exc:                         # _miniyaml.YamlError: the file does not parse
        print(f"evals: {roots.rel(REGISTRY)}: {exc}", file=sys.stderr)
        return 1
    today = now().date()

    if args.verb == "list":
        return _list(reg, args)
    if args.verb == "read":
        batch = now().isoformat()
        got, failed = take(reg, today, batch, registry_hash())
        if not args.dry_run:
            append(got)
        for r in got:
            how = r["method"] if r.get("arm") is None else f"{r['arm']} {r['method']}"
            print(f"  {r['component']:<18} {r['metric']:<18} {how:<28} "
                  f"{_shown(r)}{'' if r['gate'] else '  (gate closed)'}")
        for name, why in failed:
            print(f"evals read: {name}: the adapter failed: {why}", file=sys.stderr)
        print(f"evals read: {len(got)} reading(s)"
              + (" (dry run, nothing written)" if args.dry_run else f" -> {data_dir() / LEDGER}"))
        return 1 if failed else 0
    if args.verb == "review":
        rows = ledger_rows()
        if args.json:
            print(json.dumps(review(reg, rows, today, out=lambda *_: None), indent=2))
        else:
            review(reg, rows, today)
        return 0
    if args.verb == "verdict":
        if args.component not in reg:
            print(f"evals verdict: no component {args.component!r} in the registry", file=sys.stderr)
            return 2
        if args.review_by:
            try:
                datetime.date.fromisoformat(args.review_by)
            except ValueError:
                print("evals verdict: --review-by wants a YYYY-MM-DD date", file=sys.stderr)
                return 2
        e = reg[args.component]
        row = record_verdict(args.component, e, args.verdict, args.why, ledger_rows(), today,
                             args.review_by, data_dir())
        print(f"evals verdict: {args.component} {args.verdict}, decision {row['decision']}, "
              f"review by {row['review_by']}")
        print(f"  add this row to the verdict table in {e.get('lands')}:")
        print(f"  | {args.component} | **{args.verdict}** {today.isoformat()} | {args.why} |")
        if args.verdict != "keep":
            print(f"  and schedule the work: an item in {e.get('owner')} or a line in "
                  "ROADMAP.md §Known gaps")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
