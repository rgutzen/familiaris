"""costs (14e): what one attempt of an option uses, learned from the logs.

WHAT IS PINNED.
  the sources    a delegation's class is its role's `class:`; a calibration row
                 is `read` and its usage is read from its child log; a label is
                 its own class or `unclassed`. Nothing that ran nothing counts,
                 and all-zero usage is unmeasured, not free.
  the shrinkage  an option's arithmetic mean moves toward its class's mean times
                 its model's verbosity by K pseudo-rows, exactly; an unseen option
                 IS its prior; an option with no class row is the reference usage.
  the size       output scales by (size / typical) ** c, c fitted within options.
  the mean       an estimate is an arithmetic expectation, never a geometric mean.
"""
import json
import math

import pytest

from orchestration import costs


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def deleg(model, out, size=None, role="explore", effort="low", exit=0):
    return {"model": f"deepseek/{model}", "role": role, "effort": effort, "exit": exit,
            "usage": {"input": 100, "cache_read": 1000, "cache_write": 0, "output": out},
            "bytes_read": size, "session": ""}


def test_costs_reads_the_three_logs_and_drops_what_never_ran(tmp_path):
    child = tmp_path / "child.jsonl"
    write(child, [{"type": "message", "message": {"role": "assistant", "usage": {
        "input": 10, "output": 50, "cacheRead": 500, "cacheWrite": 0}}},
                  {"type": "message", "message": {"role": "assistant", "usage": {
        "input": 5, "output": 20, "cacheRead": 900, "cacheWrite": 0}}}])
    write(tmp_path / "delegations.jsonl", [deleg("deepseek-flash", 200, 4000),
                                           deleg("deepseek-flash", 9, exit=1)])
    write(tmp_path / "calibration.jsonl", [
        {"model": "claude-haiku-5-5", "effort": "low", "child_log": str(child)},
        {"model": "mistral-small-2603", "effort": "low", "ran": False, "child_log": str(child)}])
    write(tmp_path / "labels.jsonl", [
        {"ran_model": "claude-bridge/claude-opus-5-5", "effort": "", "attempt": 1,
         "usage": {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4}},
        {"ran_model": "claude-sonnet-5-5", "effort": "medium", "attempt": 1,
         "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}},
        {"ran_model": "claude-opus-5-5", "attempt": 2, "usage": {"input": 9}}])
    obs = costs.observations(tmp_path)
    assert [(o.option, o.source) for o in obs] == [
        (("deepseek-flash", "low", "read"), "delegation"),
        (("claude-haiku-5-5", "low", "read"), "calibration"),
        (("claude-opus-5-5", "default", "unclassed"), "label")]
    cal = obs[1].usage
    assert (cal["output"], cal["cache_read"], cal["prompt"]) == (70, 1400, 905), \
        "summed pools, and the largest single request for the long-prompt band"


def obs(model, effort, klass, out, size=None):
    return costs.Obs(model, effort, klass, {"input": 0, "cache_write": 0, "cache_read": 0,
                                            "output": out, "prompt": 0}, size)


def test_costs_an_option_shrinks_toward_its_class_times_its_models_verbosity():
    rows = [obs("a", "low", "read", 100)] * 2 + [obs("b", "low", "read", 10)] * 2 + \
           [obs("a", "high", "edit", 1000)]
    f = costs.fit(rows)
    cls = (2 * 100 + 2 * 10) / 4                            # read's arithmetic mean
    read_log = (2 * math.log1p(100) + 2 * math.log1p(10)) / 4   # totals: output only here
    # a ran twice in read (above read's log mean) and once in edit (alone: at it)
    v_a = math.exp((2 * (math.log1p(100) - read_log) + 0) / 3)
    est, n, why = f.estimate("a", "low", "read")
    assert n == 2 and why == "class read x model a"
    assert est["output"] == pytest.approx((2 * 100 + costs.K * cls * v_a) / (2 + costs.K))


def test_costs_an_unseen_option_is_its_prior_and_none_is_the_reference():
    f = costs.fit([obs("a", "low", "read", 99), obs("b", "low", "edit", 9)])
    est, n, why = f.estimate("a", "high", "read")
    assert n == 0 and est["output"] == pytest.approx(99) and why == "class read x model a"
    est, n, why = f.estimate("z", "low", "edit")
    assert est["output"] == pytest.approx(9) and why == "class edit", "no verbosity: the class"
    usage, why = costs.usage_for(f, "z", "low", "docs",
                                 rules={"reference_usage": {"default": {"output": 7}}})
    assert usage["output"] == 7 and why == "the class's reference usage"


def test_costs_output_scales_with_size_by_the_fitted_elasticity():
    rows = [obs("a", "low", "read", 2 ** k * 100, size=2 ** k * 1000) for k in range(10)]
    f = costs.fit(rows)
    assert f.c == pytest.approx(1.0, abs=0.01) and f.c_rows == 10, "log1p, not log: 0.999"
    base, _ = costs.usage_for(f, "a", "low", "read")
    double, _ = costs.usage_for(f, "a", "low", "read", size=int(f.sizes[("a", "low", "read")] * 2))
    assert double["output"] == pytest.approx(2 * base["output"], rel=0.02)
    few = costs.fit(rows[:3])
    assert few.c == 0.0, "under MIN_SIZE_ROWS the elasticity is not fitted"


def test_costs_the_estimate_is_the_expectation_not_the_geometric_mean():
    rows = [obs("a", "low", "read", 10), obs("a", "low", "read", 1000)]
    est, _n, _why = costs.fit(rows).estimate("a", "low", "read")
    assert est["output"] == pytest.approx(505), "both rows' class and model are themselves"
