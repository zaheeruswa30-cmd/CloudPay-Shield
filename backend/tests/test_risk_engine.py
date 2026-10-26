"""Unit tests for the pure risk engine (no database)."""
from risk_engine import HistoryPoint, RiskContext, assess, level_for, percentage_change
from config import settings

GOOD_REASON = "Annual performance review: promoted to senior role per policy HR-12."


def codes(result):
    return {i["code"] for i in result["indicators"] if i["points"] > 0}


def ctx(**kw):
    base = dict(current_salary=100_000, proposed_salary=105_000, reason=GOOD_REASON, submitter_role="hr",
                base_version=1, current_version=1,
                global_history=[HistoryPoint(p, "approved_request") for p in (5, 6, 7, 8, 8, 9, 10, 6, 7, 8)])
    base.update(kw)
    return RiskContext(**base)


def test_percentage_change_normal():
    assert percentage_change(100_000, 125_000) == 25.0
    assert percentage_change(200_000, 150_000) == -25.0


def test_percentage_change_invalid_values():
    assert percentage_change(0, 100) is None
    assert percentage_change(-5, 100) is None
    assert percentage_change(None, 100) is None
    assert percentage_change("abc", 100) is None
    assert percentage_change(100, -1) is None
    assert percentage_change(float("nan"), 100) is None


def test_small_change_with_good_reason_is_low():
    r = assess(ctx())
    assert r["level"] == "Low"
    assert codes(r) == set()
    assert r["manual_review_required"] is True
    assert "not a probability" in r["score_label"].lower()


def test_threshold_increase_flagged_not_rejected():
    r = assess(ctx(proposed_salary=130_000))
    assert "LARGE_INCREASE" in codes(r)
    assert r["pct_change"] == 30.0
    assert r["manual_review_required"] is True  # flagged for review, not auto-rejected


def test_just_below_threshold_not_flagged():
    r = assess(ctx(proposed_salary=124_000))
    assert "LARGE_INCREASE" not in codes(r)


def test_very_large_increase():
    r = assess(ctx(proposed_salary=170_000))
    assert "VERY_LARGE_INCREASE" in codes(r) and "LARGE_INCREASE" not in codes(r)


def test_decreases():
    assert "UNUSUAL_DECREASE" in codes(assess(ctx(proposed_salary=85_000)))
    assert "SEVERE_DECREASE" in codes(assess(ctx(proposed_salary=60_000)))


def test_missing_and_vague_reason():
    assert "MISSING_REASON" in codes(assess(ctx(reason="")))
    assert "MISSING_REASON" in codes(assess(ctx(reason="raise")))
    assert "VAGUE_REASON" in codes(assess(ctx(reason="salary adjustment.")))
    assert "VAGUE_REASON" not in codes(assess(ctx()))


def test_duplicate_and_repeated():
    r = assess(ctx(other_pending_for_employee=1, same_amount_pending=True, unresolved_recent_for_employee=3))
    assert {"DUPLICATE_PENDING", "REPEATED_UNRESOLVED"} <= codes(r)


def test_stale_version():
    r = assess(ctx(base_version=1, current_version=2))
    assert "STALE_VERSION" in codes(r)
    assert r["recommended_action"].startswith("Reject or ask HR to resubmit")


def test_invalid_baseline_handled_safely():
    r = assess(ctx(current_salary=0))
    assert "INVALID_BASELINE" in codes(r)
    assert r["pct_change"] is None


def test_payroll_limits():
    assert "BELOW_MINIMUM_SALARY" in codes(assess(ctx(current_salary=36_000, proposed_salary=36_500)))
    assert "ABOVE_MAXIMUM_SALARY" in codes(assess(ctx(current_salary=4_900_000, proposed_salary=5_100_000)))


def test_unauthorized_role_indicator():
    assert "UNAUTHORIZED_ROLE" in codes(assess(ctx(submitter_role="employee")))


def test_historical_deviation_with_enough_data():
    r = assess(ctx(proposed_salary=120_000))  # 20%: under threshold but far from ~7.5% median
    assert r["historical"]["reliable"] is True
    assert r["historical"]["sample_size"] == 10
    assert "HISTORICAL_DEVIATION" in codes(r)


def test_typical_change_not_a_historical_deviation():
    r = assess(ctx(proposed_salary=108_000))
    assert "HISTORICAL_DEVIATION" not in codes(r)


def test_insufficient_history_is_not_scored():
    r = assess(ctx(proposed_salary=120_000, global_history=[HistoryPoint(5), HistoryPoint(6)]))
    assert r["historical"]["reliable"] is False
    ind = {i["code"]: i for i in r["indicators"]}
    assert ind["INSUFFICIENT_HISTORY"]["points"] == 0


def test_seeded_history_is_labelled():
    seeded = [HistoryPoint(p, "seed_demo") for p in (5, 6, 7, 8, 9, 10)]
    r = assess(ctx(global_history=seeded))
    assert r["historical"]["seeded_demo_samples"] == 6
    assert "SEEDED DEMO DATA" in r["historical"]["note"]


def test_repeated_large_changes():
    hist = [HistoryPoint(40), HistoryPoint(35)]
    r = assess(ctx(proposed_salary=140_000, employee_history=hist))
    assert "REPEATED_LARGE_CHANGES" in codes(r)


def test_score_capped_and_levels():
    r = assess(ctx(current_salary=100_000, proposed_salary=300_000, reason="", other_pending_for_employee=2,
                   unresolved_recent_for_employee=5, base_version=1, current_version=3))
    assert r["score"] == 100 and r["level"] == "Critical"
    p = settings.risk
    assert level_for(0, p) == "Low" and level_for(25, p) == "Medium"
    assert level_for(50, p) == "High" and level_for(75, p) == "Critical"
