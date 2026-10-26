"""posterior -- P(verified) per (model, effort, class), from this class's evidence only (14f).

WHY NOT ONE ELO. A chart ranks chat preference across everything; this system
delegates a READ to one model and an EDIT to another, and what it needs to know is
how often each option's output passes its own check in that class. 6d proposed a
code-review model on 14/17 first-pass IMPLEMENTATION items -- evidence from another
class. Here no outcome crosses classes.

THE MODEL. A Beta-binomial per option. The PRIOR's mean is the class's own base
rate, moved by the model's percentile on the class's capabilities
(`capabilities.yaml`, the catalogue's benchmarks):
    mean0 = clamp(base_k + SPREAD * (pct / 100 - 0.5), FLOOR, CEIL)
at a strength of `N0` pseudo-attempts (alpha0 = N0 * mean0). A model with no
benchmark for the class keeps the base rate. The class base rate is itself
Laplace-smoothed, (s + 1) / (n + 2), so an empty class reads 0.5.

THE EVIDENCE, each one attempt with a verdict about this option's own output:
  labels.jsonl        attempt 1, `verdict: own` (a shared verifier says nothing
                      per item, 3f), class from `labels.class_of`;
  calibration.jsonl   one 12c attempt, a success when every answer is CORRECT
                      (verified and carrying the asked fact), class `read`; a
                      child that never ran (`ran: false`) is no attempt;
  cascade.jsonl       one `ref+quote` check of a routed step (pi-agent), its class;
  delegations.jsonl   `used: true|false` (12a) for the role's class; `None` waits.

OUTPUTS. `mean`, a LOWER BOUND (the `LOWER` quantile, by bisection on the
regularised incomplete beta), and `draw()` for 14g's Thompson sampling
(`random.betavariate`). Stdlib only.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import pathlib
import random
import sys

from orchestration import profiles

N0 = 4.0                 # the prior's strength, in attempts (ruled with step 14)
SPREAD = 0.4             # how far a 0th-to-100th percentile moves the prior mean
FLOOR, CEIL = 0.05, 0.95
LOWER = 0.10             # the lower bound's quantile
CASCADE_LOG = "cascade.jsonl"   # pi-agent's per-check verdicts (written by `cascade_row`)


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


@dataclasses.dataclass(frozen=True)
class Outcome:
    model: str
    effort: str
    klass: str
    ok: bool
    source: str

    @property
    def option(self) -> tuple:
        return (self.model, self.effort or "default", self.klass)


def outcomes(data: pathlib.Path | None = None) -> list:
    """Every attempt with a verdict, as `Outcome`; unclassed labels are left out."""
    from orchestration import costs, eval as eval_mod, labels        # noqa: PLC0415
    data = data or profiles.data_dir()
    out = []
    tasks = labels.eval_task_classes()
    for r in _jsonl(data / "labels.jsonl"):
        if r.get("attempt") != 1 or r.get("verdict") != "own":
            continue
        klass = labels.class_of(r, tasks)
        if klass:
            out.append(Outcome(costs.model_id(r.get("ran_model")), str(r.get("effort") or ""),
                               klass, bool(r.get("passed")), "label"))
    for r in _jsonl(data / eval_mod.CALIBRATION_LOG):
        if r.get("ran") is False or not r.get("total"):
            continue
        out.append(Outcome(costs.model_id(r.get("model")), str(r.get("effort") or ""),
                           "read", calibration_ok(r), "calibration"))
    for r in _jsonl(data / CASCADE_LOG):
        if r.get("class"):
            out.append(Outcome(costs.model_id(r.get("model")), str(r.get("effort") or ""),
                               str(r["class"]), bool(r.get("ok")), "cascade"))
    classes = costs.role_classes()
    for r in _jsonl(data / "delegations.jsonl"):
        if r.get("used") is None or str(r.get("role")) not in classes:
            continue
        out.append(Outcome(costs.model_id(r.get("model")), str(r.get("effort") or ""),
                           classes[str(r["role"])], bool(r["used"]), "delegation"))
    return out


def calibration_ok(r: dict) -> bool:
    """One 12c attempt's verdict: every answer CORRECT -- the quote verified AND the
    line carries the asked fact. `verified` alone would pass a well-quoted
    non-answer, which is the failure 14i's superseded tier is built to expose; a
    row from before the `correct` column falls back to it."""
    total = int(r.get("total") or 0)
    got = r.get("correct", r.get("verified"))
    return total > 0 and int(got or 0) == total


# --- the beta distribution ----------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta (Numerical Recipes, betacf)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e300
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """The regularised incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
          + a * math.log(x) + b * math.log(1 - x))
    front = math.exp(ln)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1 - x) / b


def beta_ppf(q: float, a: float, b: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclasses.dataclass
class Belief:
    """One option's posterior, and what it rests on."""
    option: tuple
    alpha: float
    beta: float
    successes: int
    failures: int
    prior_mean: float
    why: str

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def lower(self) -> float:
        return beta_ppf(LOWER, self.alpha, self.beta)

    def draw(self, rng: random.Random | None = None) -> float:
        return (rng or random).betavariate(self.alpha, self.beta)


def base_rates(obs: list) -> dict:
    """{class: (s + 1) / (n + 2)} over every model's attempts in the class."""
    by = {}
    for o in obs:
        s, n = by.get(o.klass, (0, 0))
        by[o.klass] = (s + o.ok, n + 1)
    return {k: (s + 1) / (n + 2) for k, (s, n) in by.items()}


def capability_pct(model: str, klass: str, cat: dict, caps: dict) -> float | None:
    """The model's mean percentile over the class's capabilities, or None."""
    from orchestration import models                                 # noqa: PLC0415
    needs = ((caps.get("task_classes") or {}).get(klass) or {}).get("capabilities") or []
    if not needs:
        return None
    try:
        sc = models.capability_scores(model, cat, caps)
    except Exception:                       # noqa: BLE001 -- an uncatalogued model has none
        return None
    got = [sc[c][0] for c in needs if sc.get(c, (None,))[0] is not None]
    return sum(got) / len(got) if got else None


def belief(model: str, effort: str, klass: str, obs: list, cat: dict, caps: dict,
           bases: dict | None = None) -> Belief:
    bases = bases if bases is not None else base_rates(obs)
    base = bases.get(klass, 0.5)
    pct = capability_pct(model, klass, cat, caps)
    mean0 = base if pct is None else min(CEIL, max(FLOOR, base + SPREAD * (pct / 100 - 0.5)))
    opt = (model, effort or "default", klass)
    mine = [o for o in obs if o.option == opt]
    s = sum(o.ok for o in mine)
    f = len(mine) - s
    why = (f"class {klass} base {base:.2f}"
           + (f", capability {pct:.0f}th percentile" if pct is not None else ", no benchmark")
           + f"; {s}/{len(mine)} own")
    return Belief(opt, N0 * mean0 + s, N0 * (1 - mean0) + f, s, f, mean0, why)


def beliefs(obs: list, cat: dict, caps: dict) -> list:
    bases = base_rates(obs)
    return [belief(m, e, k, obs, cat, caps, bases)
            for m, e, k in sorted({o.option for o in obs})]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="familiar orchestration posterior",
                                 description="P(verified) per (model, effort, class), "
                                             "from each class's own evidence.")
    ap.add_argument("--class", dest="klass", help="only this class")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    from orchestration import models                                 # noqa: PLC0415
    cat, caps = models.load(), models.load_capabilities()
    obs = outcomes()
    got = [b for b in beliefs(obs, cat, caps) if not args.klass or b.option[2] == args.klass]
    if args.json:
        print(json.dumps([{"model": b.option[0], "effort": b.option[1], "class": b.option[2],
                           "successes": b.successes, "failures": b.failures,
                           "prior": round(b.prior_mean, 3), "mean": round(b.mean, 3),
                           "lower": round(b.lower, 3), "why": b.why} for b in got], indent=2))
        return 0
    print(f"posterior -- {len(obs)} attempt(s) with a verdict; prior strength {N0:g}; "
          f"lower bound at the {LOWER:.0%} quantile")
    for b in got:
        m, e, k = b.option
        print(f"  {k:<6} {m:<32} {e:<8} {b.successes:>3}/{b.successes + b.failures:<3} "
              f"prior {b.prior_mean:.2f}  mean {b.mean:.2f}  lower {b.lower:.2f}  ({b.why})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
