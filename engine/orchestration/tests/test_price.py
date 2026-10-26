"""price (14c): the one function that turns tokens into dollars.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  the pools     cache hits at `cache_hit`, cache writes at `cache_write`, each
                falling back to the input rate when the block names none.
  the bands     haiku's long-prompt band applies to ONE request's prompt, passed
                explicitly, never inferred from summed pools; deepseek's off-peak
                half applies outside its UTC windows, and no time means peak.
  the review's  12c's 1 : 1.9 between haiku and deepseek-flash per read is what the
  number        `read` reference shape gives, where the old 1:1 sum said 1 : 2.5.
  the monopoly  no other module multiplies a catalogue rate (the check's rule).
"""
import datetime
import pathlib
import re

import pytest

from orchestration import models, price, selection

UTC = datetime.timezone.utc
FLASH = {"in": "0.30", "cache_hit": "0.006", "out": "1.20",
         "off_peak": {"peak": "mon-fri 01:00-04:00, 06:00-10:00", "factor": "0.5"}}
HAIKU = {"in": "0.10", "cache_hit": "0.01", "out": "0.50", "cache_write": "0.125",
         "long_prompt": {"over": "100000", "in": "0.50", "cache_hit": "0.05", "out": "2.50"}}


def test_price_bills_each_pool_at_its_own_rate():
    usage = {"input": 1_000_000, "cache_write": 1_000_000, "cache_read": 1_000_000,
             "output": 1_000_000}
    assert price.cost(HAIKU, usage) == (round(0.10 + 0.125 + 0.50 + 0.01, 6),
                                        round(0.10 + 0.125 + 0.50, 6))
    assert price.cost({"in": "2", "out": "8"}, usage)[0] == 2 + 2 + 2 + 8, \
        "no cache rates named: both bill at the input rate"
    assert price.cost({}, usage) == (0.0, 0.0)


def test_price_the_long_prompt_band_needs_one_requests_prompt():
    usage = {"input": 1_000_000, "output": 1_000_000}
    assert price.cost(HAIKU, usage)[0] == 0.60, "summed pools never select the band"
    assert price.cost(HAIKU, usage, prompt=100_000)[0] == 0.60, "over, not at"
    assert price.cost(HAIKU, usage, prompt=100_001)[0] == 3.00


def test_price_off_peak_is_half_outside_the_windows_and_no_time_is_peak():
    usage = {"input": 1_000_000, "output": 1_000_000}
    tue_0200 = datetime.datetime(2026, 10, 20, 2, 0, tzinfo=UTC)
    tue_0500 = datetime.datetime(2026, 10, 20, 5, 0, tzinfo=UTC)
    sat_0200 = datetime.datetime(2026, 10, 24, 2, 0, tzinfo=UTC)
    assert price.cost(FLASH, usage)[0] == 1.50
    assert price.cost(FLASH, usage, tue_0200)[0] == 1.50
    assert price.cost(FLASH, usage, tue_0500)[0] == 0.75, "between the two windows"
    assert price.cost(FLASH, usage, sat_0200)[0] == 0.75, "the weekend is off-peak"
    berlin = datetime.timezone(datetime.timedelta(hours=2))
    assert price.cost(FLASH, usage, datetime.datetime(2026, 10, 20, 4, 0, tzinfo=berlin))[0] \
        == 1.50, "04:00 in Berlin is 02:00 UTC, inside the window"


def test_price_the_read_shape_reproduces_the_measured_ratio():
    rules = selection._rules()
    usage = price.reference_usage(rules, "read")
    cat = models.load()
    ratio = price.reference("deepseek-flash", usage, cat) / \
        price.reference("claude-haiku-5-5", usage, cat)
    assert ratio == pytest.approx(1.9, abs=0.15), "12c measured $0.0063 against $0.0033"
    assert price.reference_usage(rules, "docs") == price.reference_usage(rules, "default")


def test_price_a_missing_default_shape_is_an_error():
    with pytest.raises(price.PriceError):
        price.reference_usage({"reference_usage": {"read": {"input": 1}}}, "edit")


def test_price_is_the_only_module_that_multiplies_a_catalogue_rate():
    engine = pathlib.Path(price.__file__).parents[1]
    rate = re.compile(r"""float\((?:cost|price)\.get\(["'](?:in|out|cache_hit)["']""")
    offenders = [str(p.relative_to(engine)) for p in engine.rglob("*.py")
                 if p.name != "price.py" and "tests" not in p.parts
                 and rate.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


# --- 14d: the quota pool's shadow price ---------------------------------------

def test_price_the_quota_weight_steps_and_no_reading_is_decision_24():
    steps = price.quota_steps("0.50: 0.25, 0.80: 1, else: 4")
    assert [price.quota_weight(r, steps) for r in (0.0, 0.49, 0.5, 0.79, 0.8, 1.0)] == \
        [0.25, 0.25, 1.0, 1.0, 4.0, 4.0]
    assert price.quota_weight(None, steps) == 1.0
    with pytest.raises(price.PriceError):
        price.quota_steps("0.50: 0.25")


def test_price_the_weight_applies_to_the_quota_pool_only_and_moves_a_pick():
    """Sonnet (quota) against deepseek-flash (usd) on the default shape: at list
    they are 10.7 : 1, so deepseek runs. A near-empty window does not close that;
    the test pins the weight's arithmetic on the pick_cost the ranking uses."""
    cat = models.load()
    rules = selection._rules()
    usage = price.reference_usage(rules, "edit")
    entry = {e["id"]: e for e in cat["models"]}
    base = price.pick_cost(entry["claude-sonnet-5-5"], usage, rules)
    assert rules["quota_reading"] is None and base == price.reference("claude-sonnet-5-5", usage, cat)
    low = price.pick_cost(entry["claude-sonnet-5-5"], usage, dict(rules, quota_reading=0.2))
    full = price.pick_cost(entry["claude-sonnet-5-5"], usage, dict(rules, quota_reading=0.9))
    assert low == pytest.approx(base / 4) and full == pytest.approx(base * 4)
    flash = price.pick_cost(entry["deepseek-flash"], usage, dict(rules, quota_reading=0.9))
    assert flash == price.reference("deepseek-flash", usage, cat), "the usd pool is unweighted"


def test_price_the_haiku_read_pick_moves_only_near_the_window_limit():
    """`read` tier 1 is haiku (quota), deepseek-flash, mistral-small (usd). haiku is
    the cheapest at list; at 4x (window above 80%) it is not, so the class keeps
    working off the Claude window when it is nearly spent."""
    cat, caps = models.load(), models.load_capabilities()
    sel = selection.with_needs(selection.load(), caps)
    tier = selection.tiers(sel, "read")[0]
    rules = selection._rules()
    assert selection.cheapest(cat, caps, tier, dict(rules, quota_reading=0.3))[0][0] == \
        "claude-haiku-5-5"
    assert selection.cheapest(cat, caps, tier, dict(rules, quota_reading=0.9))[0][0] != \
        "claude-haiku-5-5"
