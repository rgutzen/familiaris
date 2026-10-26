"""costs -- what one attempt of an option uses, learned from the logs (item 14e).

WHY. Price per token is not the cost of a task: effort multiplies the tokens used
(12c: deepseek-flash at `high` wrote 1.7x the output of `low`), a model's
verbosity differs, and a read is mostly cache hits while an implementation session
is mostly cache reads at a hundred times the volume. 14g ranks options by expected
cost per verified result, so it needs the TOKENS of one attempt per OPTION --
(model, effort, class) -- and this module estimates them from what has run.

THE THREE SOURCES, each row one attempt:
  delegations.jsonl   a child's usage, its role's `class:` (explore -> read), its
                      `bytes_read`, its session log (for the largest request);
  calibration.jsonl   12c's attempts, class `read`, usage read from `child_log`;
  labels.jsonl        first attempts of SPECS items, class from `labels.class_of`
                      (14f: the row's, the probe's, or the eval task's) or
                      `unclassed`.
A row whose model ran nothing (`ran: false`) is not an attempt, and is dropped; so
is a row whose usage is all zeros (five eval labels of 2026-10-15 ran through a
harness that recorded none): unmeasured is not free.

THE ESTIMATE, per pool, is an EXPECTATION, because 14g prices one: an option's
arithmetic mean is shrunk toward its PRIOR by a pseudo-count of `K` rows,
    est = (n * mean_option + K * prior) / (n + K),
and the prior is the CLASS's arithmetic mean times the MODEL's verbosity -- the
`a_k + b_m` of 14e's text, with `b_m` the model's mean log deviation from the
class means of the rows it ran, on TOTAL tokens (so haiku's factor says how much
more or less than its classes' average it uses, wherever it ran). One factor per
model, not per pool: the pools are zero-inflated (deepseek writes no cache, Claude
does), and a per-pool factor gave a haiku read 1.3M cache-write tokens. The class
supplies the pool mix, the model the scale. An option nothing has run is its
prior; one whose class has no row is the class's reference usage (dispatch.yaml,
14c) -- `toward` names which. The two log-scale alternatives were measured and
rejected on 2026-10-22: a geometric mean put a haiku read at $0.0013 against the
$0.0028 its six attempts cost, and the lognormal correction exp(mu + var/2) on
zero-inflated pools put an Opus session at $186 against $21.

SIZE. `c` is the pooled elasticity of output tokens on bytes read, fitted on the
delegation rows (the only ones that record a size) within options: a task twice
the typical size of its option is predicted at 2^c the output. With fewer than
`MIN_SIZE_ROWS` such rows `c` is 0 and says so.

THE LARGEST REQUEST. `prompt` -- the largest single request's context (input +
cache read + cache write of one assistant message) -- is read from the session log
when the row names one, because a long-prompt band (haiku over 100 000) applies
per request and the summed pools cannot say (price.py).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import pathlib
import statistics
import sys

from orchestration import profiles

POOLS = ("input", "cache_write", "cache_read", "output", "prompt")
K = 3.0                        # the prior's weight, in rows
MIN_SIZE_ROWS = 8              # rows with a size before `c` is fitted
UNCLASSED = "unclassed"        # a label from before 14f wrote a class


def _jsonl(path: pathlib.Path) -> list:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def model_id(ran: str) -> str:
    """The catalogue id a log's model names: a provider prefix stripped."""
    return str(ran or "").split("/", 1)[-1]


def largest_request(path) -> int:
    """The largest single request's context in one pi session log, or 0."""
    from orchestration import eval as eval_mod                       # noqa: PLC0415
    best = 0
    p = pathlib.Path(str(path or ""))
    if not path or not p.is_file():
        return 0
    for e in eval_mod._entries(p):
        m = e.get("message") if e.get("type") == "message" else None
        u = m.get("usage") if isinstance(m, dict) else None
        if isinstance(u, dict):
            try:
                best = max(best, sum(int(u.get(k) or 0) for k in
                                     ("input", "cacheRead", "cacheWrite")))
            except (TypeError, ValueError):
                continue
    return best


def role_classes() -> dict:
    """{role: class} from the role files' `class:` frontmatter."""
    from orchestration import bindings                               # noqa: PLC0415
    out = {}
    for p in sorted(bindings.roots.SUBAGENTS.glob("*.md")):
        front, _ = bindings._split(p.read_text(encoding="utf-8"))
        name = bindings._field(front, "name") or p.stem
        klass = bindings._field(front, "class")
        if klass:
            out[name] = klass
    return out


@dataclasses.dataclass
class Obs:
    """One attempt: what ran, how hard, for which class, and what it used."""
    model: str
    effort: str
    klass: str
    usage: dict
    size: int | None = None            # bytes read, where the log records it
    source: str = ""

    @property
    def option(self) -> tuple:
        return (self.model, self.effort or "default", self.klass)


def _usage(raw: dict, prompt: int = 0) -> dict:
    u = {k: int((raw or {}).get(k, 0) or 0) for k in POOLS if k != "prompt"}
    u["prompt"] = int(prompt or 0)
    return u


def observations(data: pathlib.Path | None = None, *, read_logs: bool = True) -> list:
    """Every attempt the three logs hold, as `Obs`."""
    from orchestration import eval as eval_mod                       # noqa: PLC0415
    data = data or profiles.data_dir()
    classes = role_classes()
    out = []
    for r in _jsonl(data / "delegations.jsonl"):
        if not r.get("usage") or r.get("exit") not in (0, None):
            continue
        prompt = largest_request(r.get("session")) if read_logs else 0
        out.append(Obs(model_id(r.get("model")), str(r.get("effort") or ""),
                       classes.get(str(r.get("role")), UNCLASSED),
                       _usage(r["usage"], prompt), r.get("bytes_read"), "delegation"))
    for r in _jsonl(data / eval_mod.CALIBRATION_LOG):
        if r.get("ran") is False or not r.get("child_log"):
            continue
        logs = [pathlib.Path(r["child_log"])]
        if read_logs and not logs[0].is_file():
            continue
        usage = eval_mod.read_usage(logs) if read_logs else {}
        if read_logs and not any(usage.values()):
            continue
        out.append(Obs(model_id(r.get("model")), str(r.get("effort") or ""), "read",
                       _usage(usage, largest_request(logs[0]) if read_logs else 0),
                       None, "calibration"))
    from orchestration import labels                                 # noqa: PLC0415
    tasks = labels.eval_task_classes()
    for r in _jsonl(data / "labels.jsonl"):
        if r.get("attempt") != 1 or not r.get("usage"):
            continue
        out.append(Obs(model_id(r.get("ran_model")), str(r.get("effort") or ""),
                       labels.class_of(r, tasks) or UNCLASSED,
                       _usage(r["usage"], largest_request(r.get("session")) if read_logs else 0),
                       None, "label"))
    return [o for o in out if any(o.usage[p] for p in POOLS if p != "prompt")]


@dataclasses.dataclass
class Fit:
    """The fitted estimates: per option the arithmetic means, per class the
    arithmetic means, per model the verbosity factor."""
    options: dict                      # option -> {"n": int, "mean": {pool: tokens}}
    classes: dict                      # class -> {pool: tokens}
    verbosity: dict                    # model -> factor on total tokens
    c: float                           # output elasticity on bytes read
    c_rows: int
    sizes: dict                        # option -> geometric mean bytes read

    def prior(self, model: str, klass: str) -> tuple[dict | None, str]:
        base = self.classes.get(klass)
        if base is None:
            return None, ""
        factor = self.verbosity.get(model)
        if factor is None:
            return dict(base), f"class {klass}"
        return {p: base[p] * factor for p in POOLS}, f"class {klass} x model {model}"

    def estimate(self, model: str, effort: str, klass: str) -> tuple[dict | None, int, str]:
        """({pool: tokens}, rows behind it, what it shrank toward)."""
        prior, why = self.prior(model, klass)
        row = self.options.get((model, effort or "default", klass))
        if row is None:
            return prior, 0, why
        n = row["n"]
        if prior is None:
            return dict(row["mean"]), n, "nothing"
        return {p: (n * row["mean"][p] + K * prior[p]) / (n + K) for p in POOLS}, n, why


def _means(rows: list) -> dict:
    return {p: statistics.fmean(o.usage.get(p, 0) for o in rows) for p in POOLS}


def _total(o: Obs) -> int:
    return sum(o.usage.get(p, 0) for p in POOLS if p != "prompt")


def fit(obs: list) -> Fit:
    by_opt, by_model, by_class = {}, {}, {}
    for o in obs:
        by_opt.setdefault(o.option, []).append(o)
        by_model.setdefault(o.model, []).append(o)
        by_class.setdefault(o.klass, []).append(o)
    class_log = {k: statistics.fmean(math.log1p(_total(o)) for o in v)
                 for k, v in by_class.items()}
    verbosity = {m: math.exp(statistics.fmean(math.log1p(_total(o)) - class_log[o.klass]
                                              for o in v))
                 for m, v in by_model.items()}
    sizes, xs, ys = {}, [], []
    for k, v in by_opt.items():
        sized = [o for o in v if o.size]
        if not sized:
            continue
        lx = [math.log(o.size) for o in sized]
        ly = [math.log1p(o.usage["output"]) for o in sized]
        sizes[k] = math.exp(statistics.fmean(lx))
        mx, my = statistics.fmean(lx), statistics.fmean(ly)
        xs += [x - mx for x in lx]
        ys += [y - my for y in ly]
    sxx = sum(x * x for x in xs)
    c = sum(x * y for x, y in zip(xs, ys)) / sxx if len(xs) >= MIN_SIZE_ROWS and sxx else 0.0
    return Fit({k: {"n": len(v), "mean": _means(v)} for k, v in by_opt.items()},
               {k: _means(v) for k, v in by_class.items()}, verbosity, c, len(xs), sizes)


def usage_for(f: Fit, model: str, effort: str, klass: str, size: int | None = None,
              rules: dict | None = None) -> tuple[dict, str]:
    """The predicted usage of one attempt, and where it came from. With `size`,
    output scales by (size / the option's typical size) ** c."""
    est, n, why = f.estimate(model, effort, klass)
    if est is None:
        from orchestration import price                              # noqa: PLC0415
        if rules is None:
            from orchestration import selection                      # noqa: PLC0415
            rules = selection._rules()
        return price.reference_usage(rules, klass), "the class's reference usage"
    typical = f.sizes.get((model, effort or "default", klass))
    if size and typical and f.c:
        est = dict(est, output=est["output"] * (size / typical) ** f.c)
    out = {p: int(round(v)) for p, v in est.items()}
    return out, (f"{n} row(s), shrunk toward {why}" if n else f"no row: {why}")


# --- the command -------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="familiar orchestration costs",
        description="What one attempt of each (model, effort, class) uses, from the logs.")
    ap.add_argument("--explain", metavar="MODEL", help="only this model's options")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    from orchestration import price                                  # noqa: PLC0415
    obs = observations()
    f = fit(obs)
    opts = sorted(f.options)
    if args.explain:
        opts = [o for o in opts if o[0] == args.explain]
    rows = []
    for m, e, k in opts:
        usage, why = usage_for(f, m, e, k)
        usd = price.model_cost(m, usage, None, None, usage.get("prompt"))[0]
        rows.append({"model": m, "effort": e, "class": k, "usage": usage, "usd": usd,
                     "why": why})
    if args.json:
        print(json.dumps({"rows": len(obs), "c": f.c, "c_rows": f.c_rows, "k": K,
                          "options": rows}, indent=2))
        return 0
    print(f"costs -- {len(obs)} attempt(s), {len(f.options)} option(s); prior weight "
          f"{K:g} rows; output ~ size^{f.c:.2f}"
          + ("" if f.c_rows >= MIN_SIZE_ROWS else f" (not fitted: {f.c_rows} sized rows)"))
    for r in rows:
        u = r["usage"]
        print(f"  {r['model']:<32} {r['effort']:<8} {r['class']:<10} in {u['input']:>8} "
              f"cw {u['cache_write']:>8} cr {u['cache_read']:>10} out {u['output']:>7}  "
              f"${r['usd']:.4f}  ({r['why']})")
    if not rows:
        print("  no option has run" + (f" for {args.explain}" if args.explain else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
