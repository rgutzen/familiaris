"""F, U, R and the quadrant -- the arithmetic of memory-ranking.md.

The constants are first estimates and are expected to move (M2 Task 7). What
these tests hold still is not the numbers but the RULES the numbers must obey:
undefined is not zero, exempt is exempt from both columns, and utility decays
over active days while freshness decays over calendar days.
"""
import datetime as dt

from consolidation import ranking

TODAY = dt.date(2026, 9, 3)


class FakeDoc:
    """The whole interface ranking needs: `get`, `kind`, `created`, `scores`."""

    def __init__(self, kind="knowledge", created=None, **fields):
        self.kind = kind
        self.created = created if created is not None else dt.date(2020, 1, 1)
        self.fm = fields
        self.scores = {}

    def get(self, key, default=None):
        return self.fm.get(key, default)


# ── freshness ────────────────────────────────────────────────────────────────

def test_missing_last_verified_is_undefined_never_zero():
    f, why = ranking.freshness(FakeDoc(), TODAY)
    assert f is None and why == "never-verified"


def test_freshness_halves_after_one_half_life():
    d = FakeDoc(stability="evolving",
                last_verified=(TODAY - dt.timedelta(days=90)).isoformat())
    f, _ = ranking.freshness(d, TODAY)
    assert f == 0.5


def test_permanent_never_decays():
    d = FakeDoc(stability="permanent", last_verified="2019-01-01")
    assert ranking.freshness(d, TODAY) == (1.0, None)


def test_a_skill_without_a_stability_uses_the_skill_half_life():
    d = FakeDoc(kind="skill",
                last_verified=(TODAY - dt.timedelta(days=ranking.SKILL_DEFAULT_H)).isoformat())
    f, _ = ranking.freshness(d, TODAY)
    assert f == 0.5


def test_a_future_verification_is_flagged_rather_than_scored_above_one():
    d = FakeDoc(stability="evolving", last_verified="2027-01-01")
    assert ranking.freshness(d, TODAY) == (1.0, "verified-in-future")


def test_freshness_ignores_active_days_because_the_world_drifts_anyway():
    d = FakeDoc(stability="evolving",
                last_verified=(TODAY - dt.timedelta(days=90)).isoformat())
    quiet = frozenset({TODAY})
    assert ranking.score(d, TODAY, quiet)["F"] == 0.5


# ── utility ──────────────────────────────────────────────────────────────────

def test_a_young_document_is_cold_start_exempt():
    d = FakeDoc(created=TODAY - dt.timedelta(days=10), use_count=0)
    u, why = ranking.utility(d, TODAY)
    assert u is None and why == "cold-start"


def test_never_used_and_never_dated_is_zero_not_undefined():
    assert ranking.utility(FakeDoc(use_count=0), TODAY) == (0.0, None)


def test_used_but_never_dated_is_floored_rather_than_guessed():
    u, why = ranking.utility(FakeDoc(use_count=10), TODAY)
    assert why == "used-never-dated" and u == 0.5


def _worked(*spans) -> frozenset:
    days = set()
    for start, n in spans:
        days |= {start + dt.timedelta(days=i) for i in range(n)}
    return frozenset(days)


def test_utility_decays_over_active_days_not_calendar_days():
    """A leaf is never demoted for days the laptop was closed."""
    used = TODAY - dt.timedelta(days=ranking.U_RECENCY_H)      # 180 calendar days
    d = FakeDoc(created=dt.date(2020, 1, 1), use_count=10, last_used=used.isoformat())
    by_calendar, _ = ranking.utility(d, TODAY)
    # Enough working days before `used` to clear the cold-start window, then two
    # working days since: the machine was closed for the rest of those 180.
    worked = _worked((dt.date(2021, 1, 1), 70), (used + dt.timedelta(days=1), 2))
    by_activity, why = ranking.utility(d, TODAY, worked)
    assert by_calendar == 0.5
    assert why is None and by_activity > 0.99, "two active days is not 180 of disuse"


def test_cold_start_is_measured_in_active_days_too():
    """A leaf written before a long break has not had 60 days of CHANCES to be
    used, so the exemption counts working days as well."""
    d = FakeDoc(created=TODAY - dt.timedelta(days=365), use_count=0)
    assert ranking.utility(d, TODAY)[1] is None, "365 calendar days clears it"
    barely_worked = _worked((TODAY - dt.timedelta(days=30), 30))
    assert ranking.utility(d, TODAY, barely_worked)[1] == "cold-start"


def test_an_empty_activity_record_falls_back_to_calendar_days():
    # No evidence means "we do not know", and inventing zero decay would make
    # every leaf look permanently fresh.
    used = TODAY - dt.timedelta(days=ranking.U_RECENCY_H)
    d = FakeDoc(use_count=10, last_used=used.isoformat())
    assert ranking.utility(d, TODAY, frozenset())[0] == 0.5


# ── quadrant and R ───────────────────────────────────────────────────────────

def test_the_four_quadrants():
    assert ranking.quadrant(0.1, 0.9) == "re-verify"
    assert ranking.quadrant(0.9, 0.1) == "demote"
    assert ranking.quadrant(0.1, 0.1) == "archive"
    assert ranking.quadrant(0.9, 0.9) == "healthy"


def test_either_component_undefined_means_exempt_from_both_columns():
    assert ranking.quadrant(None, 0.9) == "exempt"
    assert ranking.quadrant(0.9, None) == "exempt"


def test_r_is_undefined_when_a_component_is_so_nothing_exempt_can_be_pruned():
    s = ranking.score(FakeDoc(use_count=3, last_used=TODAY.isoformat()), TODAY)
    assert s["F"] is None and s["R"] is None and s["quadrant"] == "exempt"


def test_r_applies_the_trust_gate_to_the_weighted_sum():
    d = FakeDoc(stability="permanent", last_verified=TODAY.isoformat(),
                use_count=10, last_used=TODAY.isoformat(), trust="trial")
    s = ranking.score(d, TODAY)
    w_f, w_u = ranking.WEIGHTS["knowledge"]
    assert s["F"] == 1.0 and s["U"] == 1.0
    assert s["R"] == ranking.TRUST_GATE["trial"] * (w_f + w_u)


def test_a_deprecated_document_scores_zero_but_is_still_scored():
    d = FakeDoc(stability="permanent", last_verified=TODAY.isoformat(),
                use_count=10, last_used=TODAY.isoformat(), trust="deprecated")
    assert ranking.score(d, TODAY)["R"] == 0.0


def test_human_authority_is_carried_into_the_scores_for_stage_6():
    assert ranking.score(FakeDoc(authority="human"), TODAY)["human"] is True


def test_the_unvalidated_constants_are_reported_by_name():
    named = " ".join(ranking.unvalidated())
    assert "quadrant midpoint" in named and "cold start" in named
    # The opaque-dismissal TTL is a first estimate too; it must not hide
    # behind "tuned by intuition" any more than the ranking constants do.
    assert "opaque dismissal TTL" in named
