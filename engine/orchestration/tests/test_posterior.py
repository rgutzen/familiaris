"""posterior (14f): P(verified) per (model, effort, class), from the class's own evidence.

WHAT IS PINNED.
  the beta      the incomplete beta against closed forms, and the quantile as its
                inverse, so the lower bound 14g filters on is the number it says.
  the prior     mean0 = base_k + SPREAD (pct/100 - 0.5), clamped, at N0 attempts;
                no benchmark keeps the base rate.
  no crossing   an option's evidence is its own class's attempts only: a model's
                edit record moves nothing in read.
  the sources   own first attempts, calibration (all quotes verified), `used`
                delegations; a shared verdict, a rerun, a child that never ran and
                a delegation without `used` are not evidence.
"""
import json
import random

import pytest

from orchestration import labels, posterior as P


def test_posterior_the_beta_matches_its_closed_forms():
    for x in (0.1, 0.5, 0.9):
        assert P.beta_cdf(x, 1, 1) == pytest.approx(x)
        assert P.beta_cdf(x, 2, 1) == pytest.approx(x ** 2)
        assert P.beta_cdf(x, 1, 3) == pytest.approx(1 - (1 - x) ** 3)
    assert P.beta_ppf(0.25, 2, 1) == pytest.approx(0.5, abs=1e-6)
    # An independent check: the density integrated (Simpson, 2000 panels) up to the
    # quantile returns the quantile's probability.
    import math
    a_, b_ = 30.0, 10.0
    x = P.beta_ppf(0.1, a_, b_)
    lnB = math.lgamma(a_) + math.lgamma(b_) - math.lgamma(a_ + b_)
    pdf = lambda t: math.exp((a_ - 1) * math.log(t) + (b_ - 1) * math.log(1 - t) - lnB) if 0 < t < 1 else 0.0
    n = 2000
    h = x / n
    area = h / 3 * (pdf(0) + pdf(x) + sum((4 if i % 2 else 2) * pdf(i * h) for i in range(1, n)))
    assert area == pytest.approx(0.1, abs=1e-6)


def o(model, klass, ok, effort="low", source="label"):
    return P.Outcome(model, effort, klass, ok, source)


def test_posterior_the_prior_is_the_class_base_moved_by_the_capability(monkeypatch):
    monkeypatch.setattr(P, "capability_pct", lambda m, k, cat, caps: {"a": 90.0}.get(m))
    obs = [o("a", "read", True), o("b", "read", False), o("b", "read", True)]
    base = (2 + 1) / (3 + 2)
    b = P.belief("a", "low", "read", obs, {}, {})
    assert b.prior_mean == pytest.approx(base + P.SPREAD * 0.4)
    assert (b.alpha, b.beta) == pytest.approx((P.N0 * b.prior_mean + 1, P.N0 * (1 - b.prior_mean)))
    nob = P.belief("b", "low", "read", obs, {}, {})
    assert nob.prior_mean == pytest.approx(base) and "no benchmark" in nob.why
    assert P.belief("c", "low", "docs", obs, {}, {}).prior_mean == 0.5, "an empty class is 0.5"


def test_posterior_no_evidence_crosses_classes(monkeypatch):
    monkeypatch.setattr(P, "capability_pct", lambda *a: None)
    obs = [o("a", "edit", True)] * 14 + [o("a", "read", False)]
    b = P.belief("a", "low", "read", obs, {}, {})
    assert (b.successes, b.failures) == (0, 1), "fourteen edits say nothing about a read"


def test_posterior_draws_are_betas_and_the_lower_bound_is_below_the_mean():
    b = P.Belief(("a", "low", "read"), 9.0, 3.0, 7, 1, 0.5, "")
    assert b.mean == pytest.approx(0.75) and b.lower < b.mean
    rng = random.Random(1)
    draws = [b.draw(rng) for _ in range(4000)]
    assert sum(draws) / len(draws) == pytest.approx(0.75, abs=0.01)
    assert sum(d < b.lower for d in draws) / len(draws) == pytest.approx(P.LOWER, abs=0.015)


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_posterior_reads_only_the_attempts_that_judge_the_option(tmp_path, monkeypatch):
    monkeypatch.setattr(labels, "eval_task_classes", lambda: {"t": "edit"})
    write(tmp_path / "labels.jsonl", [
        {"ran_model": "x/m", "effort": "high", "attempt": 1, "verdict": "own", "passed": True,
         "class": "edit", "specs": "s", "item": "1"},
        {"ran_model": "m", "attempt": 2, "verdict": "own", "passed": False, "class": "edit"},
        {"ran_model": "m", "attempt": 1, "verdict": "shared", "passed": False, "class": "edit"},
        {"ran_model": "m", "attempt": 1, "verdict": "own", "passed": False, "specs": "eval:t:a"},
        {"ran_model": "m", "attempt": 1, "verdict": "own", "passed": False, "specs": "dev/x"}])
    write(tmp_path / "calibration.jsonl", [
        {"model": "r", "effort": "low", "verified": 8, "total": 8},
        {"model": "r", "effort": "low", "verified": 7, "total": 8},
        {"model": "r", "effort": "low", "ran": False, "verified": 0, "total": 8}])
    write(tmp_path / "delegations.jsonl", [
        {"model": "d/r", "effort": "low", "role": "explore", "used": True},
        {"model": "d/r", "effort": "low", "role": "explore", "used": None}])
    got = [(x.option, x.ok, x.source) for x in P.outcomes(tmp_path)]
    assert got == [(("m", "high", "edit"), True, "label"),
                   (("m", "default", "edit"), False, "label"),
                   (("r", "low", "read"), True, "calibration"),
                   (("r", "low", "read"), False, "calibration"),
                   (("r", "low", "read"), True, "delegation")]
