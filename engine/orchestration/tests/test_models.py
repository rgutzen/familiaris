"""models --check: schema, staleness, the pi comparison and the known-defect file.
Every test feeds `parse_pi_table` text; none runs pi."""
import copy
import datetime

from orchestration import models

TODAY = datetime.date(2026, 10, 13)

PI = """provider       model             context  max-out  thinking  images
claude-bridge  claude-haiku-5-5  200K     128K     yes       yes
mistral        mistral-medium-3.5  262.1K  262.1K   yes       yes
"""


def entry(**over):
    e = {"id": "claude-haiku-5-5", "name": "Haiku", "vendor": "anthropic", "kind": "chat",
         "jurisdiction": "US", "pool": "quota", "context": "1000000", "max_out": "128000",
         "cost": {"in": "1", "out": "5"},
         "capabilities": {"tools": "yes", "vision": "yes", "thinking": "adaptive"},
         "sources": ["https://example.org"], "verified": "2026-10-13"}
    e.update(over)
    return e


def cat(*models_, candidates=()):
    return {"stale_after_days": "60", "models": list(models_), "candidates": list(candidates)}


DEFECT = {"model": "claude-haiku-5-5", "field": "context", "harness_says": "200K",
          "vendor_says": "1000000", "note": "n"}


def run(c, pi=PI, defects=()):
    return models.check(c, pi, list(defects), TODAY)


def test_real_catalogue_schema_is_clean():
    assert models.schema_findings(models.load()) == []


def test_schema_failure_is_named():
    bad = entry(context="a lot", pool="free-ish")
    f = [str(x) for x in models.schema_findings(cat(bad))]
    assert any("claude-haiku-5-5: context: 'a lot' is not an integer" in m for m in f)
    assert any("pool:" in m for m in f)


def test_missing_field_and_duplicate_id():
    e = entry()
    del e["verified"]
    f = [str(x) for x in models.schema_findings(cat(e, candidates=[entry()]))]
    assert "claude-haiku-5-5: verified: missing" in f
    assert "claude-haiku-5-5: duplicate id" in f


def test_stale_entry_fails():
    f = models.stale_findings(cat(entry(verified="2026-07-01")), TODAY)
    assert len(f) == 1 and "104 days old" in str(f[0])
    assert models.stale_findings(cat(entry(verified="2026-08-15")), TODAY) == []


def test_haiku_200k_vs_1m_fails_without_defect():
    rep = run(cat(entry()))
    assert rep.failures == 1
    assert str(rep.findings[0]) == ("claude-haiku-5-5: context: pi says 200K, "
                                    "catalogue (vendor) says 1000000")


def test_known_defect_passes_and_is_counted():
    rep = run(cat(entry()), defects=[DEFECT])
    assert rep.failures == 0 and rep.known == 1
    assert str(rep.findings[0]).startswith("claude-haiku-5-5: known pi defect: context:")


def test_resolved_defect_fails():
    pi = PI.replace("200K     128K", "1M       128K")
    rep = run(cat(entry()), pi=pi, defects=[DEFECT])
    assert rep.failures == 1
    assert "resolved, remove from harness-defects.yaml" in str(rep.findings[0])


def test_defect_for_other_pi_value_does_not_hide_a_new_one():
    rep = run(cat(entry()), defects=[dict(DEFECT, harness_says="100K")])
    assert rep.failures == 2          # the disagreement, and the record that no longer fits


def test_alias_match_and_size_tolerance():
    e = entry(id="mistral-medium-3-5", vendor="mistral", context="256000", max_out="256000",
              aliases="mistral-medium-3, mistral-medium-3.5")
    rep = run(cat(e))                  # pi 262.1K vs 256000: within 5%
    assert rep.failures == 0, [str(f) for f in rep.findings]


def test_size_outside_tolerance_fails():
    e = entry(id="mistral-medium-3.5", vendor="mistral", context="128000", max_out="256000")
    assert run(cat(e)).failures == 1


def test_missing_provider_is_skipped_not_failed():
    e = entry(id="deepseek-flash", vendor="deepseek")
    rep = run(cat(e))
    assert rep.failures == 0 and rep.skipped == 1
    assert "skipped: pi lists no deepseek models (no key in this environment?)" in str(rep.findings[0])


def test_vendor_without_pi_provider_is_named():
    rep = run(cat(entry(id="jev-1", vendor="typesafe")))
    assert rep.failures == 0 and rep.skipped == 1
    assert "jev-1: skipped: no pi provider for vendor 'typesafe'" in str(rep.findings[0])


def test_listed_provider_lacking_model_fails():
    rep = run(cat(entry(id="claude-haiku-9")))
    assert rep.failures == 1 and "pi lists no 'claude-haiku-9'" in str(rep.findings[0])


def test_thinking_and_images_compare():
    e = entry(capabilities={"tools": "yes", "vision": "no", "thinking": "no"})
    msgs = [str(f) for f in run(cat(e), defects=[DEFECT]).findings]
    assert any("thinking: pi says yes, catalogue (vendor) says no" in m for m in msgs)
    assert any("images: pi says yes, catalogue (vendor) says no" in m for m in msgs)


def test_parse_pi_table_skips_header_and_noise():
    rows = models.parse_pi_table(PI + "\nwarning: something\n")
    assert rows["claude-bridge"]["claude-haiku-5-5"]["context"] == "200K"
    assert "provider" not in rows


def test_size():
    assert round(models.size("262.1K")) == 262100 and models.size("1M") == 1e6
    assert models.size("x") is None


def test_empty_defects_file_is_no_records(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("pi:\n")
    assert models.load_defects(p) == []
    assert models.load_defects(tmp_path / "absent.yaml") == []


# --- capabilities (2i) -------------------------------------------------------

CAPS = {
    "benchmarks": {"tb": {"names": ["TB 4", "TB 4.0"]}, "swe": {"names": ["SWE"]},
                   "solo": {"names": ["Solo"]}},
    "capabilities": {"coding": {"benchmarks": ["swe", "solo"]}, "terminal": {"benchmarks": ["tb"]},
                     "writing": {"benchmarks": None}},
    "task_classes": {"edit": {"capabilities": ["coding", "terminal"]},
                     "docs": {"capabilities": ["writing"]}},
}


def _bench(name, score):
    return {"name": name, "score": score, "source": "https://x", "date": "2026-10-01", "grade": "B"}


def _scored():
    return cat(entry(id="a", benchmarks=[_bench("TB 4", "60"), _bench("SWE", "70"), _bench("Solo", "9")]),
               entry(id="b", benchmarks=[_bench("TB 4.0", "40")]),
               entry(id="q", quantised="q4_K_M", benchmarks=[_bench("SWE", "50"), _bench("Odd", "1")]),
               candidates=[entry(id="c", benchmarks=[_bench("TB 4", "60")])])


def test_percentile_counts_ties_half_and_needs_a_second_score():
    assert models.percentile("a", {"a": 60, "b": 40, "c": 60}) == 75.0
    assert models.percentile("a", {"a": 60}) is None
    assert models.percentile("z", {"a": 60, "b": 1}) is None


def test_names_merge_spellings_and_candidates_join_the_population():
    s = models.scores(_scored(), CAPS)
    assert s["tb"] == {"a": 60.0, "b": 40.0, "c": 60.0}
    assert models.unmapped(_scored(), CAPS) == [("q", "Odd")]


def test_a_capability_averages_ranked_benchmarks_and_shows_its_count():
    got = models.capability_scores("a", _scored(), CAPS)
    assert got["coding"] == (100.0, 1, 2)       # Solo ranks nothing: only `a` has it
    assert got["terminal"] == (75.0, 1, 1)
    assert got["writing"] == (None, 0, 0)


def test_explain_says_unknown_never_zero_and_flags_quantisation():
    text = models.explain("q", _scored(), CAPS)
    assert "quantised: q4_K_M" in text and "upper bound" in text
    assert "terminal" in text and "unknown" in text
    assert "docs   writing unknown" in text
    assert "Odd" in text                         # a benchmark no capability claims is named
    assert models.explain("nope", _scored(), CAPS) is None


def test_capability_file_dangling_names_fail():
    bad = {"benchmarks": {"tb": {"names": ["X"]}, "tb2": {"names": ["X"]}},
           "capabilities": {"coding": {"benchmarks": ["missing"]}},
           "task_classes": {"edit": {"capabilities": ["nope"]}}}
    msgs = [f.message for f in models.capability_findings(bad)]
    assert len(msgs) == 3


def test_the_real_capability_file_is_consistent_and_covers_haiku():
    caps = models.load_capabilities()
    assert models.capability_findings(caps) == []
    assert set(caps["task_classes"]) == {"edit", "read", "test", "docs", "batch"}
    text = models.explain("claude-haiku-5-5", models.load(), caps)
    assert "terminal" in text
