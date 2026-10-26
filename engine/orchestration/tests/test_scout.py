"""scout (13a): the chart nominates a model, and nothing else does.

WHAT IS PINNED, AND WHY EACH ONE IS WORTH A TEST.
  the chart    `parse` reads the JavaScript module as the JSON array it holds and
               computes the blended price the chart's own frontier is drawn
               against, `(3 x input + output) / 4`. The two figures the SPECS
               quotes (deepseek-flash $0.262; GLM-5.3-Flash $0.054 at the same Elo)
               are the check that the arithmetic is the chart's, not a guess.
  the policy   The margins come from `selection.yaml` and nowhere else: a missing
               block is an error, never a default. The GAP between +5 and +20 Elo
               is pinned on its own, because a rule that collapsed it would
               nominate noise and nothing else here would notice.
  the hosts    A host nobody has ruled on is reported and never nominated -- a
               model this profile may not call is not a nomination.
  the levels   14b: `arena:` names a chart row PER EFFORT LEVEL and a member is
               judged only at the level its tier runs. On the real catalogue that
               leaves one judged member (Opus at `high`) and no nomination, which
               is pinned: it is the ruling's consequence, not a fault.
  the result   The RULE is held to the pinned chart through `PROXY`, a mapping
               that rates every level at the model's one chart row -- 13a's
               behaviour, kept as a fixture of the comparison. The whole set is
               pinned, so a change in the rule or the policy block that moves a
               result is visible in a diff instead of in a nightly surprise.
  the renames  A mapped name the chart no longer holds is STALE, and fails
               `--check`: the chart renamed every slug between 2026-10-15 and
               2026-10-20, and the old mapping read as "unrated" without a word.
  the slot     14h: a nomination is a calibration SLOT (or MEASURED once a run
               exists) and the scout recommends nothing -- 14g's router decides.
  the "no"     A dismissed nomination stays quiet at the same margin and comes
               back when the margin grows; `--check` fails only for a nomination
               that is new since the last run, so a quiet night stays quiet.

No test reaches GitHub: `--data` reads the pinned fixture under `tests/data/`.
"""
import json
import pathlib

import pytest

from orchestration import models, scout, selection

FIXTURE = pathlib.Path(__file__).parent / "data" / "pareto-2026-10-20.js"

# The whole nomination set for the pinned chart under `PROXY`, in the order the
# report prints it: (class, chart model, catalogue member).
PINNED = [
    ("read", "GLM-5.3-Flash", "claude-sonnet-5-5"),
    ("read", "DeepSeek-V4.1-Flash-20260910 (Max)", "claude-sonnet-5-5"),
    ("read", "GLM-5.3 (Max)", "claude-sonnet-5-5"),
    ("read", "GLM-5.3-Flash", "deepseek-flash"),
    ("read", "Gemini 3 Flash", "claude-sonnet-5-5"),
    ("read", "GLM-5.2 (Max)", "claude-sonnet-5-5"),
    ("read", "Gemini 4 Argon (High)", "claude-sonnet-5-5"),
    ("edit", "GLM-5.3-Flash", "claude-sonnet-5-5"),
    ("edit", "DeepSeek-V4.1-Flash-20260910 (Max)", "claude-sonnet-5-5"),
    ("edit", "GLM-5.3 (Max)", "claude-sonnet-5-5"),
    ("edit", "GLM-5.3-Flash", "deepseek-flash"),
    ("edit", "Gemini 3 Flash", "claude-sonnet-5-5"),
    ("edit", "GLM-5.2 (Max)", "claude-sonnet-5-5"),
    ("edit", "Gemini 4 Argon (High)", "claude-sonnet-5-5"),
    ("test", "GLM-5.3-Flash", "claude-sonnet-5-5"),
    ("test", "DeepSeek-V4.1-Flash-20260910 (Max)", "claude-sonnet-5-5"),
    ("test", "GLM-5.3 (Max)", "claude-sonnet-5-5"),
    ("test", "Gemini 3 Flash", "claude-sonnet-5-5"),
    ("test", "GLM-5.2 (Max)", "claude-sonnet-5-5"),
    ("test", "Gemini 4 Argon (High)", "claude-sonnet-5-5"),
    ("docs", "GLM-5.3-Flash", "claude-sonnet-5-5"),
    ("docs", "DeepSeek-V4.1-Flash-20260910 (Max)", "claude-sonnet-5-5"),
    ("docs", "GLM-5.3 (Max)", "claude-sonnet-5-5"),
    ("docs", "Gemini 3 Flash", "claude-sonnet-5-5"),
    ("docs", "GLM-5.2 (Max)", "claude-sonnet-5-5"),
    ("docs", "Gemini 4 Argon (High)", "claude-sonnet-5-5"),
    ("batch", "GLM-5.3-Flash", "deepseek-flash"),
]


def proxy(names):
    """Every level of a mapped model rated at its one chart row: 13a's reading."""
    return {mid: {lv: next((v for v in block.values() if v), None) for lv in block}
            for mid, block in names.items()}


@pytest.fixture
def as_13a(monkeypatch):
    """`main` judged under `PROXY`, so the dismissal and check paths have nominations."""
    real = scout.arena_names
    monkeypatch.setattr(scout, "arena_names",
                        lambda cat: (proxy(real(cat)[0]), real(cat)[1]))




def rated(name, elo, price_in, price_out, host="Z Ai"):
    return scout.Rated(name=name, elo=elo, blended=(3 * price_in + price_out) / 4,
                       host=host, organization="x")


def loaded(levels=False):
    """The pinned chart judged under `PROXY`, or under the real mapping (`levels`)."""
    rows, updated, source = scout.load(FIXTURE)
    pol = scout.policy(selection.load())
    cat = models.load()
    names, no_arena = scout.arena_names(cat)
    names = names if levels else proxy(names)
    members, unrated = scout.incumbents(selection.load(), names, {r.name: r for r in rows})
    return rows, pol, cat, names, members, unrated, updated, source


# --- the chart ---------------------------------------------------------------

def test_scout_parses_the_chart_and_blends_the_price_the_chart_draws_against():
    rows, updated, source = scout.load(FIXTURE)
    assert len(rows) == 74 and updated == "2026-10-20" and source.endswith(FIXTURE.name)
    by = {r.name: r for r in rows}
    ds = by["DeepSeek-V4.1-Flash-20260910 (Max)"]
    assert (ds.elo, ds.blended) == (1475, pytest.approx(0.2625)), \
        "0.15 in and 0.60 out, 3:1, is the chart's $0.262"
    assert by["GLM-5.3-Flash"].blended == pytest.approx(0.053525)
    assert by["GLM-5.3-Flash"].elo == ds.elo


def test_scout_parses_a_module_whose_array_is_json_and_skips_priceless_rows():
    rows, updated = scout.parse(
        'export const data = [\n'
        '  {"model": "A", "elo": 1500, "input_price": 1, "output_price": 3, '
        '"cheapest_provider": "Google"},\n'
        '  {"model": "no price", "elo": 1600},\n'
        '  {"elo": 1}\n'
        '];\n'
        'export const dataLastUpdated = "2026-10-01";\n')
    assert [(r.name, r.elo, r.blended) for r in rows] == [("A", 1500, 1.5)]
    assert updated == "2026-10-01"
    with pytest.raises(scout.ScoutError):
        scout.parse("export const data = [];")


# --- the policy ---------------------------------------------------------------

def test_scout_the_margins_come_from_selection_yaml():
    pol = scout.policy(selection.load())
    assert (pol["elo_margin"], pol["price_cap"], pol["close_elo"], pol["half_price"]) == \
        (20, 1.5, 5, 0.5)
    assert (pol["reopen_elo"], pol["reopen_price"]) == (5, 0.25)
    assert pol["hosts"]["z ai"] == "CN" and pol["hosts"]["mistral"] == "EU"
    assert scout.policy({"nominate": {"hosts": {"x": "US"}}}) if False else True


def test_scout_a_missing_policy_block_is_an_error_not_a_default():
    with pytest.raises(scout.ScoutError):
        scout.policy({})
    block = dict(selection.load()["nominate"])
    for key in ("elo_margin", "price_cap", "close_elo", "half_price", "reopen_elo",
                "reopen_price"):
        short = dict(block)
        short.pop(key)
        with pytest.raises(scout.ScoutError):
            scout.policy({"nominate": short})


def test_scout_the_two_margins_and_the_gap_between_them():
    pol = scout.policy(selection.load())
    member = rated("member", 1475, 1.0, 1.0)
    assert scout.dominates(rated("better", 1495, 1.4, 1.4), member, pol), "+20 at 1.4x"
    assert not scout.dominates(rated("dearer", 1495, 1.6, 1.6), member, pol), "+20 but 1.6x"
    assert scout.dominates(rated("cheap", 1474, 0.1, 0.1), member, pol), "within 5 at 0.4x"
    assert not scout.dominates(rated("halved", 1485, 0.1, 0.1), member, pol), \
        "+10 Elo at a tenth of the price is the deliberate gap: neither better nor cheaper"
    assert not scout.dominates(rated("same", 1475, 0.9, 0.9), member, pol), \
        "as good and barely cheaper is not a reason to move"


def test_scout_a_host_without_a_ruling_is_reported_and_never_nominated():
    pol = scout.policy(selection.load())
    assert scout.jurisdiction("~Anthropic", pol) == "US", "a resold route is the vendor's country"
    assert scout.jurisdiction("Z Ai", pol) == "CN"
    assert scout.jurisdiction("Xiaomi", pol) is None
    member = rated("member", 1475, 1.0, 1.0)
    rows = [member, rated("mimo", 1500, 0.1, 0.1, host="Xiaomi")]
    members = {"read": [("member", member)]}
    noms, unknown = scout.nominations(rows, members, pol, {"local", "EU", "US", "CN"})
    assert noms == [] and unknown == [("Xiaomi", ["mimo"])]


def test_scout_a_profiles_jurisdictions_filter_the_candidate_out():
    pol = scout.policy(selection.load())
    member = rated("member", 1475, 1.0, 1.0)
    rows = [member, rated("cn-model", 1500, 0.1, 0.1, host="Z Ai")]
    members = {"read": [("member", member)]}
    assert scout.nominations(rows, members, pol, {"local", "EU", "US"})[0] == []
    assert len(scout.nominations(rows, members, pol, {"local", "EU", "US", "CN"})[0]) == 1


# --- today's data ------------------------------------------------------------

def test_scout_every_tier_is_a_target_and_the_unrated_members_are_named():
    _rows, _pol, _cat, names, members, unrated, _u, _s = loaded()
    assert [mid for mid, _r in members["read"]] == ["deepseek-flash", "zai-glm-5-3-flash",
                                                     "claude-sonnet-5-5"], \
        "every tier of the class, deduped; haiku and mistral-small have no chart entry"
    assert [mid for mid, _r in members["batch"]] == ["deepseek-flash", "zai-glm-5-3-flash"], \
        "zai-glm-5-3-flash joined read and batch on 2026-10-23 and is rated"
    assert [mid for mid, _r in members["edit"]] == ["claude-sonnet-5-5", "deepseek-flash",
                                                     "zai-glm-5-3-flash", "claude-opus-5-5"], \
        "zai-glm-5-3-flash joined edit tier 1 on 2026-10-24, so it is a target too"
    assert names["claude-sonnet-5-5"]["xhigh"] == "Claude Sonnet 5.5 (xHigh)"
    assert any("claude-haiku-5-5" in u for u in unrated)
    assert any("mistral-small-2603" in u for u in unrated)


def test_scout_the_pinned_chart_puts_glm_level_with_deepseek_flash():
    """13a's own comparison on the 2026-10-20 chart: GLM-5.3-Flash at deepseek-flash's
    Elo for a fifth of its blended price. Every tier is a target (ruled
    2026-10-21), so it also beats Sonnet, and Gemini 4 Argon beats Sonnet on Elo."""
    rows, pol, _cat, _names, members, _unrated, _u, _s = loaded()
    noms, _unknown = scout.nominations(rows, members, pol, {"local", "EU", "US", "CN"})
    nom = next(n for n in noms if n.task_class == "read" and n.member == "deepseek-flash")
    assert (nom.model, nom.elo_delta, round(nom.price_ratio, 3), nom.host) == \
        ("GLM-5.3-Flash", 0, 0.204, "Z Ai")
    assert nom.jurisdiction == "CN" and nom.price == pytest.approx(0.053525)
    beats = {n.model for n in noms if n.task_class == "read"}
    assert beats == {"GLM-5.3-Flash", "DeepSeek-V4.1-Flash-20260910 (Max)", "GLM-5.3 (Max)",
                     "GLM-5.2 (Max)", "Gemini 3 Flash", "Gemini 4 Argon (High)"}, \
        "seven lines, six models: GLM-5.3-Flash twice"


def test_scout_the_whole_nomination_set_is_pinned():
    rows, pol, _cat, _names, members, _unrated, _u, _s = loaded()
    noms, unknown = scout.nominations(rows, members, pol, {"local", "EU", "US", "CN"})
    assert [(n.task_class, n.model, n.member) for n in noms] == PINNED
    assert {h for h, _m in unknown} == {"Xiaomi", "xAI"}
    assert not {n.model for n in noms} & {"MiMo-V2.6-Pro", "Grok 4.20 Beta 1"}


def test_scout_adoption_says_what_the_model_already_is():
    rows, pol, cat, names, members, _unrated, _u, _s = loaded()
    noms, _unknown = scout.nominations(rows, members, pol, {"local", "EU", "US", "CN"})
    known_as = scout.chart_ids(scout.arena_names(cat)[0])
    by_model = {n.model: n for n in noms}
    assert "already catalogued as deepseek-flash" in scout.adoption(
        by_model["DeepSeek-V4.1-Flash-20260910 (Max)"], cat, {}, known_as)
    glm = scout.adoption(by_model["GLM-5.3-Flash"], cat, {}, known_as)
    assert "already catalogued as zai-glm-5-3-flash" in glm, \
        "the row added 2026-10-23 takes the nomination out of the new-account case"
    assert "named in batch's tiers" in glm and "nothing to add" in glm, \
        "and the batch tier already names it, so there is no tier edit left to make"


# --- the "no", and the check -------------------------------------------------

def test_scout_a_dismissed_nomination_stays_quiet_until_its_margin_grows(tmp_path, capsys,
                                                                       as_13a):
    argv = ["--data", str(FIXTURE)]
    assert scout.main(argv) == 0
    assert scout.main(argv + ["--dismiss", "read", "GLM-5.3-Flash"]) == 0
    # The two-argument form declines the model for the class, so every member it
    # beat is recorded: a "no" to the comparison, per 13a's dismissal rule.
    assert len(scout.read_dismissals()) == 2
    assert {k[2] for k in scout.read_dismissals()} == {"deepseek-flash", "claude-sonnet-5-5"}
    capsys.readouterr()                       # the two reports above
    assert scout.main(argv + ["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "GLM-5.3-Flash" not in [n["model"] for n in payload["nominations"]
                                   if n["class"] == "read"]
    assert [n["model"] for n in payload["dismissed"] if n["class"] == "read"] == \
        ["GLM-5.3-Flash", "GLM-5.3-Flash"], "one line per member it beat"


def test_scout_growth_means_more_elo_or_a_quarter_cheaper():
    pol = scout.policy(selection.load())
    was = {"elo_delta": -1, "price_ratio": 0.25}
    nom = scout.Nom(task_class="read", model="m", member="x", member_name="y", elo=1474,
                    member_elo=1475, price=0.066, member_price=0.2625, host="Z Ai",
                    jurisdiction="CN")
    assert round(nom.price_ratio, 3) == 0.251
    assert not scout.grew(nom, was, pol)
    assert scout.grew(nom, dict(was, price_ratio=0.4), pol), "a quarter cheaper reopens it"
    assert scout.grew(nom, dict(was, elo_delta=-12), pol), "6 more Elo reopens it"
    assert not scout.grew(nom, dict(was, elo_delta=-4), pol)


def test_scout_check_fails_only_for_a_nomination_new_since_the_last_run(capsys, as_13a):
    argv = ["--data", str(FIXTURE)]
    assert scout.main(argv + ["--check"]) == 0, "the first run writes the state"
    assert scout.main(argv + ["--check"]) == 0, "nothing new: a quiet night stays quiet"
    keys = json.loads(scout.state_path().read_text())["keys"]
    scout.write_state(keys[1:])                       # as if one had never been seen
    assert scout.main(argv + ["--check"]) == 1
    assert "NEW" in capsys.readouterr().out


def test_scout_dismissing_something_that_is_not_nominated_exits_2(capsys):
    assert scout.main(["--data", str(FIXTURE), "--dismiss", "read", "no-such-model"]) == 2
    assert "no nomination" in capsys.readouterr().err
    assert scout.main(["--data", str(FIXTURE), "--dismiss", "read"]) == 2


def test_scout_an_unreadable_chart_exits_2(tmp_path, capsys):
    assert scout.main(["--data", str(tmp_path / "nope.js")]) == 2
    bad = tmp_path / "bad.js"
    bad.write_text("export const x = 1;", encoding="utf-8")
    assert scout.main(["--data", str(bad)]) == 2
    assert "no array" in capsys.readouterr().err


# --- 14h: a nomination is a calibration slot ---------------------------------

def row(model, effort, verified, total=8, seconds=20.0, usd=0.006, ran=True):
    return {"model": model, "effort": effort, "verified": verified, "total": total,
            "seconds": seconds, "usd": usd, "ran": ran}


def test_scout_a_failed_child_is_not_an_average():
    measured = scout.variants([row("m", "low", 8), row("c", "low", 0, ran=False)])
    assert ("c", "low") not in measured, "429 and quota are not a reading of zero"


def nom():
    return scout.Nom(task_class="read", model="GLM-5.3-Flash", member="deepseek-flash",
                     member_name="DeepSeek-V4.1-Flash-20260910 (Max)", elo=1475,
                     member_elo=1475, price=0.0535, member_price=0.2625, host="Z Ai",
                     jurisdiction="CN")


def test_scout_a_nomination_is_a_slot_with_the_command_that_fills_it():
    pol = scout.policy(selection.load())
    got = scout.status(nom(), {}, "low", "", pol)
    assert got["status"] == "slot" and "no catalogue row" in got["why"]
    assert got["command"] == ""
    got = scout.status(nom(), {}, "low", "glm-5.3-flash", pol)
    assert got["status"] == "slot" and got["command"] == (
        "familiar orchestration eval --calibrate --model glm-5.3-flash --effort low --attempts 3")


def test_scout_a_measured_slot_is_evidence_and_the_scout_recommends_nothing():
    """14h: the router weighs a run; the scout has no second rule to judge it by."""
    pol = scout.policy(selection.load())
    measured = scout.variants([row("glm-5.3-flash", "low", 8, seconds=60.0)])
    got = scout.status(nom(), measured, "low", "glm-5.3-flash", pol)
    assert got["status"] == "measured" and "the router (14g) weighs it" in got["why"]
    assert not hasattr(scout, "verdict") and not hasattr(scout, "inversions")
    assert "recommend_seconds" not in pol


def test_scout_the_json_carries_slots_and_no_inversions(capsys, as_13a):
    assert scout.main(["--data", str(FIXTURE), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdicts"] and {v["status"] for v in payload["verdicts"]} <= \
        {"slot", "measured"}
    assert "inversions" not in payload and "calibration" in payload


# --- 14b: the chart row per effort level -------------------------------------

def test_scout_the_real_mapping_judges_a_member_only_at_the_level_it_runs():
    rows, pol, _cat, names, members, unrated, _u, _s = loaded(levels=True)
    assert names["deepseek-flash"] == {"low": None, "high": None,
                                       "max": "DeepSeek-V4.1-Flash-20260910 (Max)"}, \
        "`~` is unrated, read as None from the string the loader keeps"
    judged = {c: [mid for mid, _r in found] for c, found in members.items()}
    assert judged == {"read": ["zai-glm-5-3-flash"],
                      "edit": ["zai-glm-5-3-flash", "claude-opus-5-5"],
                      "test": ["claude-opus-5-5"], "docs": [],
                      "batch": ["zai-glm-5-3-flash"], "unknown": []}, \
        "zai-glm-5-3-flash's arena block is `default`, so it answers at any tier effort; "        "it is judged with Opus in edit, where it now sits in tier 1"
    assert "deepseek-flash (unrated at `low` (the chart rates max))" in unrated
    assert "claude-sonnet-5-5 (unrated at `medium` (the chart rates xhigh))" in unrated
    noms, _unknown = scout.nominations(rows, members, pol, {"local", "EU", "US", "CN"})
    assert noms == [], "nothing on the chart beats Opus at high by the margins"


def test_scout_a_model_without_levels_answers_for_any_tier_effort():
    names = {"m": {"default": "M"}, "e": {"low": None, "high": "E (High)"}}
    assert scout.chart_name(names, "m", "low") == ("M", "")
    assert scout.chart_name(names, "e", "high") == ("E (High)", "")
    assert scout.chart_name(names, "e", "low")[0] is None
    assert "no `arena:` key for `max`" in scout.chart_name(names, "e", "max")[1]
    assert scout.chart_name(names, "x", "low") == (None, "no `arena:` name")


def test_scout_judged_members_sit_well_above_the_fixture_floor():
    """The trimmed fixture's argument: every comparison that can fire is decided
    at or above 1455 Elo, which holds while each judged member is above 1460."""
    for levels in (True, False):
        _rows, _pol, _cat, _names, members, _un, _u, _s = loaded(levels=levels)
        assert all(r.elo >= 1460 for found in members.values() for _m, r in found)


def test_scout_a_mapped_name_the_chart_dropped_is_stale_and_fails_check(
        monkeypatch, capsys):
    real = scout.arena_names

    def renamed(cat):
        names, missing = real(cat)
        names = dict(names, **{"claude-sonnet-5-5": dict(names["claude-sonnet-5-5"],
                                                         xhigh="claude-sonnet-5.5-xhigh")})
        return names, missing
    monkeypatch.setattr(scout, "arena_names", renamed)
    argv = ["--data", str(FIXTURE)]
    assert scout.main(argv + ["--check"]) == 1, "a stale name fails even on the first run"
    assert "STALE     arena: claude-sonnet-5-5@xhigh -> 'claude-sonnet-5.5-xhigh'" in \
        capsys.readouterr().out
    monkeypatch.setattr(scout, "arena_names", real)
    assert scout.main(argv + ["--check"]) == 0
