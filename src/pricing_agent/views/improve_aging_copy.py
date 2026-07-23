"""Dealer-facing copy for the Improve Aging workspace. Phase 5.1, presentation only.

Every reason code, exclusion category, candidate-category description, and "what to do next"
action lives here, in one place, so the view reads a label instead of assembling strings
inline. Nothing in this module computes a price, a percentile, or a forecast — it maps codes
to words and counts items that the workflow already decided.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- reason-code → dealer label -------------------------------------------------------

SELECTION_LABELS: dict[str, str] = {
    "CURRENTLY_OVER_90_DAYS": "Already over 90 days on lot",
    "CURRENTLY_OVER_120_DAYS": "Already over 120 days on lot",
    "P50_PROJECTED_OVER_90_DAYS": "Expected to exceed 90 days before sale",
    "P90_PROJECTED_OVER_90_DAYS": "Meaningful risk of exceeding 90 days before sale",
    "CURRENT_PRICE_POOR_DEAL": "Current price is not competitive",
    "HIGH_DEPRECIATION_RISK": "High risk of further value loss",
    "HIGH_HOLDING_COST": "High cost of remaining in inventory",
    "DUPLICATE_INVENTORY": "Similar vehicles are competing for the same demand",
    "CAPACITY_RELEASE_PRIORITY": "High priority for freeing lot space",
    "HIGH_SAFE_PROMOTIONAL_HEADROOM": "Room for a safer promotional adjustment",
    "INBOUND_REPLACEMENT_PRESSURE": "Incoming inventory is increasing space pressure",
    "LOW_ENGAGEMENT_OR_CONVERSION": "Low shopper engagement or conversion",
}

EXCLUSION_LABELS: dict[str, str] = {
    "RECENTLY_ACQUIRED": "Recently acquired — protect the current strategy",
    "ALREADY_GOOD_DEAL": "Already competitively priced",
    "HIGH_DEMAND_PROTECT_GROSS": "Strong demand — protect profit",
    "EXPECTED_TO_SELL_BEFORE_EVENT": "Expected to sell before the event",
    "INSUFFICIENT_DATA": "Not enough reliable data to recommend an action",
    "NO_SAFE_DISCOUNT_HEADROOM": "No safe room for an additional discount",
    "ALREADY_ASSIGNED_TO_CAMPAIGN": "Already included in another campaign",
    "MANUAL_HOLD": "Manually protected from automated recommendations",
}

# Consolidated action → dealer label.
ACTION_LABELS: dict[str, str] = {
    "REPRICE_NOW": "Reprice now",
    "EVENT_PROMOTION": "Include in sale event",
    "PROTECT_PRICE": "Protect price — no action",
    "MANAGER_REVIEW": "Manager review before repricing",
    "WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW": "Wholesale / loss-minimization review",
    "NO_ACTION": "No action — selling on its own",
}

# Why a vehicle was excluded — is it a safety rule, a business rule, or a data limitation?
SAFETY_RULE = "Safety rule"
BUSINESS_RULE = "Business rule"
DATA_LIMITATION = "Data limitation"

EXCLUSION_CATEGORY: dict[str, str] = {
    "NO_SAFE_DISCOUNT_HEADROOM": SAFETY_RULE,
    "INSUFFICIENT_DATA": DATA_LIMITATION,
    "RECENTLY_ACQUIRED": BUSINESS_RULE,
    "ALREADY_GOOD_DEAL": BUSINESS_RULE,
    "HIGH_DEMAND_PROTECT_GROSS": BUSINESS_RULE,
    "EXPECTED_TO_SELL_BEFORE_EVENT": BUSINESS_RULE,
    "ALREADY_ASSIGNED_TO_CAMPAIGN": BUSINESS_RULE,
    "MANUAL_HOLD": BUSINESS_RULE,
}


def selection_label(code: str) -> str:
    return SELECTION_LABELS.get(code, code.replace("_", " ").title())


def exclusion_label(code: str) -> str:
    return EXCLUSION_LABELS.get(code, code.replace("_", " ").title())


def action_label(code: str) -> str:
    return ACTION_LABELS.get(code, code.replace("_", " ").title())


def exclusion_category(codes: tuple[str, ...]) -> str:
    for code in codes:
        if code in EXCLUSION_CATEGORY:
            return EXCLUSION_CATEGORY[code]
    return BUSINESS_RULE


# --- "why these vehicles?" — business categories present among the candidates ----------

# Each category maps to the selection codes that evidence it and a plain-language line.
CANDIDATE_CATEGORIES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Aging risk",
     ("CURRENTLY_OVER_90_DAYS", "CURRENTLY_OVER_120_DAYS",
      "P50_PROJECTED_OVER_90_DAYS", "P90_PROJECTED_OVER_90_DAYS"),
     "Already past — or projected to pass — 90 days on the lot."),
    ("Poor market position",
     ("CURRENT_PRICE_POOR_DEAL",),
     "Currently advertised above the local market."),
    ("Holding-cost exposure",
     ("CAPACITY_RELEASE_PRIORITY", "HIGH_HOLDING_COST"),
     "Tying up a slot and floorplan cash that a fresher unit could use."),
    ("Depreciation risk",
     ("HIGH_DEPRECIATION_RISK",),
     "Losing value quickly the longer it stays."),
    ("Duplicate inventory pressure",
     ("DUPLICATE_INVENTORY",),
     "A near-identical unit is already on the lot."),
    ("Safe promotional headroom",
     ("HIGH_SAFE_PROMOTIONAL_HEADROOM",),
     "Room to discount without breaking the price floor."),
    ("Inbound replacement pressure",
     ("INBOUND_REPLACEMENT_PRESSURE",),
     "A committed inbound unit of the same type is arriving."),
)


def candidate_categories(candidates) -> list[tuple[str, str, int]]:
    """(category, description, vehicle_count) for each category present among candidates."""
    present: list[tuple[str, str, int]] = []
    for name, codes, description in CANDIDATE_CATEGORIES:
        count = sum(1 for c in candidates if any(code in c.reason_codes for code in codes))
        if count:
            present.append((name, description, count))
    return present


# --- "what should I do next?" ---------------------------------------------------------

_ALTERNATIVE_COPY = {
    "REVISED_UTILIZATION_TARGET": "revise the utilization target",
    "LONGER_CAMPAIGN": "extend the event window",
    "WHOLESALE_DISPOSITION": "wholesale some units",
}


@dataclass(frozen=True)
class NextAction:
    title: str
    detail: str
    grounded_in: str      # the result field / code this action is derived from


def _action_counts(result) -> dict[str, int]:
    counts: dict[str, int] = {}
    for a in result.consolidated_actions:
        counts[a["recommended_action"]] = counts.get(a["recommended_action"], 0) + 1
    return counts


def next_steps(result) -> list[NextAction]:
    """Three-to-five prioritized dealer actions, each grounded in an existing result field,
    action count, approval, warning, or feasibility alternative. No calculation."""
    from pricing_agent.workflows.improve_aging import WorkflowState

    counts = _action_counts(result)
    approvals = len(result.approvals_required)
    steps: list[NextAction] = []

    # 1. If the target cannot be met, the first decision is about the target itself.
    if result.state is WorkflowState.TARGET_NOT_ACHIEVABLE and result.promotion_result:
        alts = result.promotion_result["feasibility"].get("alternatives", [])
        options = [
            _ALTERNATIVE_COPY.get(a["option"], a["option"].replace("_", " ").lower())
            for a in alts
        ]
        detail = ("The requested target is not reachable with safe actions. Options: "
                  + ", ".join(options) + ".") if options else "Reconsider the target."
        steps.append(NextAction(
            "Decide on the target", detail, "feasibility.alternatives"))

    # 2. Vehicles that cannot move without a signature — a safety gate. The dealer-facing count
    # is the number of vehicles requiring review, never the raw approval-record count (that lives
    # in "View approval details"); the manager-review action count is a distinct, smaller figure.
    review = counts.get("MANAGER_REVIEW", 0)
    review_vehicles = len({a.get("vehicle_id") for a in result.approvals_required
                           if a.get("vehicle_id")})
    if review or approvals:
        steps.append(NextAction(
            f"Review {review} vehicle(s) assigned to manager review",
            f"{review_vehicles} vehicle(s) have review conditions to clear before any price "
            "changes.",
            "consolidated_actions[MANAGER_REVIEW] + distinct approvals_required vehicles"))

    # 3. The deeply aged, underwater units.
    wholesale = counts.get("WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW", 0)
    if wholesale:
        steps.append(NextAction(
            f"Wholesale / loss-minimization review for {wholesale} unit(s)",
            "These are aged and below break-even; holding them grows the loss.",
            "consolidated_actions[WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW]"))

    # 4. The safe promotion the plan actually recommends.
    promote = counts.get("EVENT_PROMOTION", 0)
    if promote and result.promotion_result:
        plan = result.promotion_result["recommended_plan"]["plan_type"].replace("_", " ").title()
        steps.append(NextAction(
            f"Approve the {plan} plan — promotes {promote} vehicle(s)",
            "The only vehicles with safe discount room after protection and approval checks.",
            "recommended_plan + consolidated_actions[EVENT_PROMOTION]"))

    # 5. Protected inventory the dealer should consciously leave alone.
    protect = counts.get("PROTECT_PRICE", 0)
    if protect and len(steps) < 5:
        steps.append(NextAction(
            f"Hold price on {protect} protected vehicle(s)",
            "Recently acquired, high demand, or already in a campaign — not for discounting.",
            "consolidated_actions[PROTECT_PRICE]"))

    # 6. Inbound pressure, if the portfolio flagged it and there is room.
    if len(steps) < 5 and result.portfolio_result:
        codes = {w["code"] for w in result.portfolio_result.get("warnings", [])}
        if "INBOUND_CAPACITY_CONFLICT" in codes:
            steps.append(NextAction(
                "Review inbound inventory commitments",
                "Committed inbound units exceed open slots; some aged units must clear first.",
                "portfolio warning INBOUND_CAPACITY_CONFLICT"))

    return steps[:5]


# --- recommendation statement ---------------------------------------------------------


def recommendation_statement(result) -> str:
    """One sentence, derived from the actual state and recommended plan. Never hard-coded
    favourably."""
    from pricing_agent.workflows.improve_aging import WorkflowState

    if result.state is WorkflowState.TARGET_NOT_ACHIEVABLE:
        return ("The requested target is not achievable within the current event window and "
                "price-floor constraints. The most aggressive safe plan and the gap are shown "
                "below.")
    if result.state is WorkflowState.NEEDS_CLARIFICATION:
        return "More information is needed before a plan can be built — see below."
    if result.state is WorkflowState.NO_SAFE_ACTIONS:
        return "No aging vehicle qualifies for a safe repricing or promotion action."
    if result.state is WorkflowState.PARTIAL_RESULT:
        return ("Some analyses did not complete; the recommendation below is based on the "
                "results that finished.")
    if result.promotion_result:
        plan = result.promotion_result["recommended_plan"]["plan_type"].replace("_", " ").title()
        return f"Recommended approach: {plan}."
    return ("Diagnosis complete. Name a calendar event to build a promotion plan and quantify "
            "target achievement.")
