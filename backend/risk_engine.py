"""Hybrid, explainable salary-change risk engine.

Three layers:
  A. Policy rules  - thresholds, reasons, duplicates, versions, payroll limits, roles
  B. History       - robust statistics (median / MAD) over applied salary changes
  C. Scoring       - documented weights summed and capped at 100, mapped to levels

IMPORTANT: the result is a RISK SCORE that ranks requests for human review.
It is NOT a probability of fraud and must never be used as proof of wrongdoing.
Every request still needs a manager decision, whatever its score.

All functions here are pure (no database access) so they are easy to unit-test.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from config import RiskPolicy, settings

POLICY_VERSION = "2026.10-v1"
SCORE_LABEL = "Rule-based risk score (0-100). Not a probability of fraud."


def percentage_change(current, proposed) -> float | None:
    """((proposed - current) / current) * 100, or None when it cannot be computed safely."""
    try:
        current_f = float(current)
        proposed_f = float(proposed)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(current_f) and math.isfinite(proposed_f)):
        return None
    if current_f <= 0 or proposed_f < 0:
        return None
    return round(((proposed_f - current_f) / current_f) * 100, 2)


@dataclass
class HistoryPoint:
    pct_change: float
    source: str = "approved_request"  # or "seed_demo"


@dataclass
class RiskContext:
    current_salary: object
    proposed_salary: object
    reason: str | None
    submitter_role: str = "hr"
    base_version: int | None = None
    current_version: int | None = None
    other_pending_for_employee: int = 0
    same_amount_pending: bool = False
    unresolved_recent_for_employee: int = 0
    employee_history: list[HistoryPoint] = field(default_factory=list)
    department_history: list[HistoryPoint] = field(default_factory=list)
    global_history: list[HistoryPoint] = field(default_factory=list)
    department: str | None = None


TITLES = {
    "LARGE_INCREASE": "Large salary increase",
    "VERY_LARGE_INCREASE": "Very large salary increase",
    "UNUSUAL_DECREASE": "Unusual salary decrease",
    "SEVERE_DECREASE": "Severe salary decrease",
    "NO_CHANGE": "Proposed salary equals current salary",
    "MISSING_REASON": "Missing or too-short reason",
    "VAGUE_REASON": "Vague reason",
    "DUPLICATE_PENDING": "Duplicate pending request",
    "REPEATED_UNRESOLVED": "Repeated unresolved requests",
    "REPEATED_LARGE_CHANGES": "Repeated large changes for this employee",
    "STALE_VERSION": "Based on an outdated salary version",
    "HISTORICAL_DEVIATION": "Unusual compared with salary history",
    "BELOW_MINIMUM_SALARY": "Below payroll minimum",
    "ABOVE_MAXIMUM_SALARY": "Above payroll maximum",
    "INVALID_BASELINE": "Invalid current salary",
    "UNAUTHORIZED_ROLE": "Submitted by an unauthorized role",
    "INSUFFICIENT_HISTORY": "Not enough history for statistical comparison",
}

CATEGORY = {
    "HISTORICAL_DEVIATION": "history",
    "REPEATED_LARGE_CHANGES": "history",
    "INSUFFICIENT_HISTORY": "history",
    "UNAUTHORIZED_ROLE": "permission",
}


def _severity(points: int) -> str:
    if points >= 30:
        return "high"
    if points >= 15:
        return "medium"
    if points > 0:
        return "low"
    return "info"


def level_for(score: int, policy: RiskPolicy) -> str:
    for name, lower in policy.levels:
        if score >= lower:
            return name
    return "Low"


def _is_vague(reason: str, policy: RiskPolicy) -> bool:
    cleaned = " ".join(reason.lower().replace(".", " ").replace(",", " ").split())
    if cleaned in policy.vague_reasons:
        return True
    words = cleaned.split()
    # Very few distinct words, all of them generic.
    generic = {w for phrase in policy.vague_reasons for w in phrase.split()}
    return len(words) <= 3 and all(w in generic for w in words)


def robust_stats(values: list[float]) -> tuple[float, float]:
    median = statistics.median(values)
    mad = statistics.median([abs(v - median) for v in values])
    return median, mad


def historical_analysis(ctx: RiskContext, pct: float | None, policy: RiskPolicy) -> dict:
    """Compare the request with the most specific reliable reference group."""
    groups = [
        (f"department:{ctx.department}" if ctx.department else "department", ctx.department_history),
        ("organisation", ctx.global_history),
    ]
    chosen_name, chosen = None, []
    for name, points in groups:
        if len(points) >= policy.min_history_samples:
            chosen_name, chosen = name, points
            break

    info = {
        "reference_group": chosen_name,
        "sample_size": len(chosen),
        "real_samples": sum(1 for p in chosen if p.source != "seed_demo"),
        "seeded_demo_samples": sum(1 for p in chosen if p.source == "seed_demo"),
        "median_pct": None,
        "mad_pct": None,
        "robust_z": None,
        "reliable": False,
        "employee_prior_changes": len(ctx.employee_history),
        "note": "",
    }
    if pct is None:
        info["note"] = "Percentage change could not be computed, so no historical comparison was made."
        return info
    if not chosen:
        info["note"] = (
            f"Fewer than {policy.min_history_samples} applied salary changes are available; "
            "historical comparison is not reliable and was not scored."
        )
        return info

    values = [p.pct_change for p in chosen]
    median, mad = robust_stats(values)
    # Floor the spread at 1 percentage point so identical history does not explode the score.
    scale = max(mad, 1.0)
    z = 0.6745 * (pct - median) / scale
    info.update(median_pct=round(median, 2), mad_pct=round(mad, 2), robust_z=round(z, 2), reliable=True)
    if info["seeded_demo_samples"] > info["real_samples"]:
        info["note"] = "Most reference data is SEEDED DEMO DATA, not real payroll history."
    else:
        info["note"] = "Reference data comes from applied (approved) salary changes."
    return info


def assess(ctx: RiskContext, policy: RiskPolicy | None = None) -> dict:
    policy = policy or settings.risk
    w = policy.weights
    indicators: list[dict] = []

    def add(code: str, explanation: str, points: int | None = None):
        pts = w.get(code, 0) if points is None else points
        indicators.append({
            "code": code,
            "title": TITLES.get(code, code),
            "category": CATEGORY.get(code, "policy"),
            "points": pts,
            "severity": _severity(pts),
            "explanation": explanation,
        })

    pct = percentage_change(ctx.current_salary, ctx.proposed_salary)

    # ---- A. Policy rules
    try:
        current = float(ctx.current_salary)
    except (TypeError, ValueError):
        current = None
    try:
        proposed = float(ctx.proposed_salary)
    except (TypeError, ValueError):
        proposed = None

    if current is None or not math.isfinite(current) or current <= 0:
        add("INVALID_BASELINE", "The current salary is missing, zero, negative or not a number, "
            "so the percentage change cannot be calculated. Verify the payroll record first.")

    if pct is not None:
        if pct > policy.very_large_increase_pct:
            add("VERY_LARGE_INCREASE", f"Increase of {pct:.2f}% exceeds the {policy.very_large_increase_pct:g}% "
                "very-large threshold. Confirm supporting documents (promotion letter, market review).")
        elif pct > policy.increase_threshold_pct:
            add("LARGE_INCREASE", f"Increase of {pct:.2f}% exceeds the {policy.increase_threshold_pct:g}% review threshold.")
        elif pct < -policy.severe_decrease_pct:
            add("SEVERE_DECREASE", f"Decrease of {abs(pct):.2f}% exceeds the {policy.severe_decrease_pct:g}% severe-decrease "
                "threshold. Large cuts can indicate errors or misuse and may have legal implications.")
        elif pct < -policy.decrease_threshold_pct:
            add("UNUSUAL_DECREASE", f"Decrease of {abs(pct):.2f}% exceeds the {policy.decrease_threshold_pct:g}% decrease threshold.")
        elif pct == 0:
            add("NO_CHANGE", "The proposed salary is the same as the current salary; the request may be unnecessary.")

    if proposed is not None and math.isfinite(proposed):
        if proposed < policy.minimum_salary:
            add("BELOW_MINIMUM_SALARY", f"Proposed salary PKR {proposed:,.0f} is below the configured payroll "
                f"minimum of PKR {policy.minimum_salary:,}.")
        if proposed > policy.maximum_salary:
            add("ABOVE_MAXIMUM_SALARY", f"Proposed salary PKR {proposed:,.0f} is above the configured payroll "
                f"maximum of PKR {policy.maximum_salary:,}.")

    reason = (ctx.reason or "").strip()
    if len(reason) < policy.min_reason_length:
        add("MISSING_REASON", f"Reason is {len(reason)} characters; at least {policy.min_reason_length} are expected "
            "to explain the business justification.")
    elif _is_vague(reason, policy):
        add("VAGUE_REASON", f"Reason \"{reason[:60]}\" is generic and does not explain why the change is needed.")

    if ctx.other_pending_for_employee > 0:
        extra = " with the same proposed amount" if ctx.same_amount_pending else ""
        add("DUPLICATE_PENDING", f"{ctx.other_pending_for_employee} other pending request(s) already exist for this "
            f"employee{extra}. Resolve them first to avoid double changes.")

    if ctx.unresolved_recent_for_employee >= policy.repeated_unresolved_count:
        add("REPEATED_UNRESOLVED", f"{ctx.unresolved_recent_for_employee} requests for this employee in the last "
            f"{policy.repeated_window_days} days are unresolved.")

    if ctx.base_version is not None and ctx.current_version is not None and ctx.base_version != ctx.current_version:
        add("STALE_VERSION", f"The request was prepared against salary version {ctx.base_version}, but the current "
            f"version is {ctx.current_version}. It cannot be approved until it is resubmitted.")

    if ctx.submitter_role not in ("hr",):
        add("UNAUTHORIZED_ROLE", f"Role '{ctx.submitter_role}' is not allowed to submit salary changes.")

    # ---- B. Historical analysis
    hist = historical_analysis(ctx, pct, policy)
    if hist["reliable"] and hist["robust_z"] is not None and abs(hist["robust_z"]) > policy.robust_z_threshold:
        add("HISTORICAL_DEVIATION", f"A {pct:.2f}% change is far from the typical {hist['median_pct']:.2f}% "
            f"in {hist['reference_group']} (robust z = {hist['robust_z']}, threshold {policy.robust_z_threshold:g}, "
            f"n = {hist['sample_size']}).")
    elif not hist["reliable"] and pct is not None:
        add("INSUFFICIENT_HISTORY", hist["note"])

    large_prior = [p for p in ctx.employee_history if abs(p.pct_change) > policy.increase_threshold_pct]
    if len(large_prior) >= 2 and pct is not None and abs(pct) > policy.increase_threshold_pct:
        add("REPEATED_LARGE_CHANGES", f"This employee already had {len(large_prior)} changes above "
            f"{policy.increase_threshold_pct:g}%; another large change is unusual.")

    # ---- C. Score
    score = min(100, sum(i["points"] for i in indicators))
    level = level_for(score, policy)
    recommended = {
        "Low": "Standard review: confirm the reason and approve or reject.",
        "Medium": "Careful review: check the flagged items and supporting documents before deciding.",
        "High": "Enhanced review: verify documents with HR and the department head; record a detailed decision reason.",
        "Critical": "Escalated review: do not approve until every flag is resolved and independently verified.",
    }[level]
    if any(i["code"] == "STALE_VERSION" for i in indicators):
        recommended = "Reject or ask HR to resubmit against the current salary version. " + recommended

    return {
        "score": score,
        "level": level,
        "score_label": SCORE_LABEL,
        "pct_change": pct,
        "indicators": indicators,
        "explanations": [i["explanation"] for i in indicators if i["points"] > 0],
        "policy_violations": [i["code"] for i in indicators if i["category"] in ("policy", "permission") and i["points"] > 0],
        "historical": hist,
        "recommended_action": recommended,
        "manual_review_required": True,
        "enhanced_review_required": level in ("High", "Critical"),
        "policy_version": POLICY_VERSION,
    }


def policy_description(policy: RiskPolicy | None = None) -> dict:
    policy = policy or settings.risk
    return {
        "policy_version": POLICY_VERSION,
        "score_label": SCORE_LABEL,
        "thresholds": {
            "increase_threshold_pct": policy.increase_threshold_pct,
            "very_large_increase_pct": policy.very_large_increase_pct,
            "decrease_threshold_pct": policy.decrease_threshold_pct,
            "severe_decrease_pct": policy.severe_decrease_pct,
            "min_reason_length": policy.min_reason_length,
            "min_history_samples": policy.min_history_samples,
            "robust_z_threshold": policy.robust_z_threshold,
            "repeated_window_days": policy.repeated_window_days,
            "repeated_unresolved_count": policy.repeated_unresolved_count,
            "minimum_salary": policy.minimum_salary,
            "maximum_salary": policy.maximum_salary,
        },
        "weights": [
            {"code": code, "title": TITLES.get(code, code), "points": pts, "category": CATEGORY.get(code, "policy")}
            for code, pts in policy.weights.items()
        ],
        "levels": [{"level": name, "min_score": lower} for name, lower in policy.levels],
        "method": (
            "Points for each triggered indicator are added and capped at 100. Historical deviation uses a robust "
            "z-score: 0.6745 x (change - median) / max(MAD, 1), computed only when at least "
            f"{policy.min_history_samples} applied changes exist in the reference group."
        ),
    }
