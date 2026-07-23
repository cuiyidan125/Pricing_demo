"""Explainable aging-candidate selection. Phase 5, no calculation.

This layer decides **which** vehicles the Improve Aging workflow should look at more
closely. It ranks and filters values that the portfolio-forecast skill already produced,
and reads static inventory facts (days on lot, price, campaign flags, acquisition date). It
does **not** compute a price, a percentile, a holding cost, a depreciation figure, a
break-even, or promotional headroom — every such number is read from the portfolio result.

The output is a reason-coded selection: each vehicle is either a candidate (with the reasons
it was chosen) or excluded (with the reason it was held back). Protected vehicles — recently
acquired, high-demand, already a good deal — are excluded here, before any deeper analysis,
so they never enter an aggressive promotion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --- selection policy (thresholds, not calculations) ----------------------------------
# These are policy dials for *which* vehicles to examine, not financial math. The financial
# figures they compare against were all produced by the portfolio skill.

OVER_90_DAYS = 90
OVER_120_DAYS = 120
OVER_60_DAYS = 60
RECENTLY_ACQUIRED_DAYS = 30
P50_PROJECTED_PROB = 0.50   # prob(age > 90) above this ⇒ P50 projection already over 90
P90_PROJECTED_PROB = 0.10   # between this and P50 threshold ⇒ only the P90 tail is over 90
HIGH_DEPRECIATION_QUANTILE = 0.60  # fraction of the cohort's worst p90 depreciation

# A candidate needs at least one *primary* reason to age it into the plan. The remaining
# reasons are supporting context — a vehicle flagged only by them (a mild P90 tail, some
# headroom, an inbound of the same segment) is still expected to sell and is not selected.
PRIMARY_REASONS = frozenset({
    "CURRENTLY_OVER_90_DAYS",
    "CURRENTLY_OVER_120_DAYS",
    "P50_PROJECTED_OVER_90_DAYS",
    "CURRENT_PRICE_POOR_DEAL",
    "HIGH_DEPRECIATION_RISK",
    "DUPLICATE_INVENTORY",
    "CAPACITY_RELEASE_PRIORITY",
})

# Portfolio `recommended_actions.action` values, grouped by what they tell selection.
HEADROOM_ACTIONS = {"EVENT_PROMOTION", "VELOCITY_REPRICE"}
POOR_DEAL_ACTIONS = {"BALANCED_REPRICE"}
PROTECT_ACTIONS = {"INCREASE_PRICE", "RETAIN_PRICE"}
AGGRESSIVE_DISPOSITION = {"WHOLESALE_DISPOSITION", "LOSS_MINIMIZATION_REVIEW"}


@dataclass(frozen=True)
class Candidate:
    vehicle_id: str
    description: str
    days_in_inventory: int
    current_list_price: float | None
    risk_score: float
    reason_codes: tuple[str, ...]
    portfolio_action: str


@dataclass(frozen=True)
class Exclusion:
    vehicle_id: str
    description: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class Selection:
    candidates: tuple[Candidate, ...]
    exclusions: tuple[Exclusion, ...]

    # Reason codes that mean "do not promote aggressively"; used by callers and tests.
    PROTECTED_REASONS = (
        "RECENTLY_ACQUIRED",
        "ALREADY_GOOD_DEAL",
        "HIGH_DEMAND_PROTECT_GROSS",
        "ALREADY_ASSIGNED_TO_CAMPAIGN",
        "MANUAL_HOLD",
    )

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(c.vehicle_id for c in self.candidates)


def _describe(vehicle: dict) -> str:
    return (
        f"{vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')} "
        f"{vehicle.get('trim') or ''}".strip()
    )


def _duplicate_ids(inventory: list[dict]) -> set[str]:
    """Vehicle ids that share make+model+trim with another active unit."""
    seen: dict[tuple, list[str]] = {}
    for v in inventory:
        key = (
            str(v.get("make")).casefold(),
            str(v.get("model")).casefold().replace("-", "").replace(" ", ""),
            str(v.get("trim")).casefold(),
        )
        seen.setdefault(key, []).append(v["vehicle_id"])
    return {vid for ids in seen.values() if len(ids) > 1 for vid in ids}


def select_candidates(
    portfolio_result: dict,
    inventory: list[dict],
    inbound: list[dict],
    *,
    as_of: date,
) -> Selection:
    """Rank and filter the portfolio result into reason-coded candidates and exclusions."""
    risk_by_id = {r["vehicle_id"]: r for r in portfolio_result.get("top_risk_vehicles", [])}
    action_by_id = {a["vehicle_id"]: a for a in portfolio_result.get("recommended_actions", [])}
    analyzed_ids = set(portfolio_result.get("audit", {}).get("vehicle_identifiers", []))

    duplicates = _duplicate_ids(inventory)
    inbound_segments = {str(i.get("segment")).casefold() for i in inbound if i.get("committed_slot")}

    # Cohort reference for "high depreciation": the worst p90 depreciation across the ranked
    # set. This is a comparison against an already-computed figure, not a new calculation.
    worst_dep = max(
        (r.get("p90_depreciation_loss", 0.0) for r in risk_by_id.values()), default=0.0
    ) or 1.0

    candidates: list[Candidate] = []
    exclusions: list[Exclusion] = []

    for vehicle in inventory:
        vid = vehicle["vehicle_id"]
        description = _describe(vehicle)
        days = int(vehicle.get("days_in_inventory") or 0)
        action = (action_by_id.get(vid) or {}).get("action", "RETAIN_PRICE")
        risk = risk_by_id.get(vid, {})
        risk_score = float(risk.get("risk_score", 0.0))
        prob_age = float(risk.get("prob_age_over_90", 0.0))

        # --- exclusions first (protection takes priority over selection) --------------
        exclude: list[str] = []

        if vid not in analyzed_ids:
            exclude.append("INSUFFICIENT_DATA")
        if vehicle.get("campaign_participation"):
            exclude.append("ALREADY_ASSIGNED_TO_CAMPAIGN")
        if str(vehicle.get("status", "")).upper() in {"HOLD", "MANUAL_HOLD"}:
            exclude.append("MANUAL_HOLD")

        acquired = vehicle.get("acquisition_date")
        if acquired:
            try:
                if (as_of - date.fromisoformat(acquired)).days <= RECENTLY_ACQUIRED_DAYS:
                    exclude.append("RECENTLY_ACQUIRED")
            except ValueError:
                pass
        if days <= RECENTLY_ACQUIRED_DAYS and "RECENTLY_ACQUIRED" not in exclude:
            exclude.append("RECENTLY_ACQUIRED")

        # A vehicle the portfolio wants to hold or price up is demand-protected, not aged
        # inventory to discount.
        if action in PROTECT_ACTIONS:
            if action == "INCREASE_PRICE":
                exclude.append("HIGH_DEMAND_PROTECT_GROSS")
            elif days < OVER_60_DAYS:
                exclude.append("ALREADY_GOOD_DEAL")

        if exclude:
            exclusions.append(Exclusion(vid, description, tuple(dict.fromkeys(exclude))))
            continue

        # --- selection reasons --------------------------------------------------------
        reasons: list[str] = []
        if days > OVER_120_DAYS:
            reasons.append("CURRENTLY_OVER_120_DAYS")
        elif days > OVER_90_DAYS:
            reasons.append("CURRENTLY_OVER_90_DAYS")

        if prob_age >= P50_PROJECTED_PROB:
            reasons.append("P50_PROJECTED_OVER_90_DAYS")
        elif prob_age >= P90_PROJECTED_PROB:
            reasons.append("P90_PROJECTED_OVER_90_DAYS")

        if action in POOR_DEAL_ACTIONS:
            reasons.append("CURRENT_PRICE_POOR_DEAL")
        if action in HEADROOM_ACTIONS:
            reasons.append("HIGH_SAFE_PROMOTIONAL_HEADROOM")
        if action in AGGRESSIVE_DISPOSITION:
            reasons.append("CAPACITY_RELEASE_PRIORITY")

        if float(risk.get("p90_depreciation_loss", 0.0)) / worst_dep >= HIGH_DEPRECIATION_QUANTILE:
            reasons.append("HIGH_DEPRECIATION_RISK")

        if vid in duplicates:
            reasons.append("DUPLICATE_INVENTORY")
        if str(vehicle.get("segment", "")).casefold() in inbound_segments:
            reasons.append("INBOUND_REPLACEMENT_PRESSURE")

        if not any(r in PRIMARY_REASONS for r in reasons):
            # Only supporting signals (mild tail risk, some headroom, an inbound of the same
            # segment). Not aged enough to act on — expected to sell before the event.
            exclusions.append(Exclusion(vid, description, ("EXPECTED_TO_SELL_BEFORE_EVENT",)))
            continue

        candidates.append(
            Candidate(
                vehicle_id=vid,
                description=description,
                days_in_inventory=days,
                current_list_price=vehicle.get("current_list_price"),
                risk_score=risk_score,
                reason_codes=tuple(dict.fromkeys(reasons)),
                portfolio_action=action,
            )
        )

    # Rank candidates by the portfolio's own risk score — attention follows dollars at stake.
    candidates.sort(key=lambda c: c.risk_score, reverse=True)
    return Selection(tuple(candidates), tuple(exclusions))
