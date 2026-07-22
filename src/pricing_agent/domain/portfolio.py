"""Portfolio aggregation. §14, implementing D2 and D6.

The rule §14.7 states directly: do not add individual P50 forecasts. Outcomes are summed
**across vehicles within each draw**, and percentiles are taken across the resulting
portfolio outcomes.

Measured on the fixture lot, the difference is not academic: the sum of per-vehicle P10
revenue contributions is exactly $0 — no vehicle has a 90% chance of selling inside 30
days — while the portfolio's own P10 revenue is over $50,000, because the lot obviously
sells *something* in a bad month. Marginals cannot reconstruct that.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

import numpy as np

from pricing_agent.config import Config
from pricing_agent.domain.summarize import percentile_set, probability
from pricing_agent.simulation.engine import DrawMatrix

AGE_BUCKETS = ((0, 30), (31, 60), (61, 90), (91, 120), (121, 99999))


# --- capacity (D6) --------------------------------------------------------------------


def capacity_position(capacity: dict, inbound: Sequence[dict]) -> dict:
    """Derive capacity from primitives.

    `reserved_slots ⊇ confirmed_inbound`, so only `confirmed_inbound` enters the flow and
    the excess is deducted separately. Counting both would double-count every inbound
    vehicle — the defect D6 exists to prevent.

    Utilization is always measured against `total_physical_slots`, because a general
    manager saying "70% utilization" means 70% of the lot.
    """
    slots = int(capacity["total_physical_slots"])
    current = int(capacity["current_inventory"])
    reserved = int(capacity["reserved_slots"])
    committed_inbound = sum(1 for v in inbound if v.get("committed_slot"))
    confirmed = int(capacity.get("confirmed_inbound", committed_inbound))
    reserved_not_inbound = max(0, reserved - confirmed)

    return {
        "total_physical_slots": slots,
        "current_inventory": current,
        "reserved_slots": reserved,
        "confirmed_inbound": confirmed,
        "reserved_not_inbound": reserved_not_inbound,
        "expected_exits": int(capacity.get("expected_exits", 0)),
        "physical_open_slots": slots - current,
        "effective_open_slots": slots - current - reserved_not_inbound - confirmed,
        "current_utilization": (current / slots) if slots else 0.0,
        "target_utilization": float(capacity["target_utilization"]),
    }


def arrivals_within(inbound: Sequence[dict], as_of: date, horizon_days: int) -> int:
    """Committed inbound units expected to land inside the horizon."""
    count = 0
    for unit in inbound:
        if not unit.get("committed_slot"):
            continue
        arrival = date.fromisoformat(unit["expected_arrival_date"])
        if 0 <= (arrival - as_of).days <= horizon_days:
            count += 1
    return count


# --- forecast -------------------------------------------------------------------------


def forecast(
    draws: DrawMatrix,
    horizon_days: int,
    capacity: dict,
    scheduled_arrivals: int,
    config: Config,
    revenue_target: float | None = None,
) -> dict:
    """Build an `inventory-sales-forecast.schema.json` block by aggregating within draws."""
    sold = draws.sold_within(horizon_days)

    # Costs accrue only up to the horizon for vehicles that have not sold by then.
    days = np.minimum(draws.days_to_sale.astype(float), float(horizon_days))
    day_fraction = np.divide(
        days,
        draws.days_to_sale.astype(float),
        out=np.ones_like(days),
        where=draws.days_to_sale > 0,
    )

    units_sold = sold.sum(axis=1).astype(float)
    revenue = (draws.transaction_price * sold).sum(axis=1)
    gross = (draws.front_end_gross * sold).sum(axis=1)
    net_value = (draws.net_economic_value * sold).sum(axis=1)
    cash_holding = (draws.cash_holding_cost * day_fraction).sum(axis=1)
    depreciation = (draws.depreciation_loss * day_fraction).sum(axis=1)

    slots = float(capacity["total_physical_slots"])
    current = float(capacity["current_inventory"])

    # Arrivals that cannot physically fit are DEFERRED, not dropped. Modeling an
    # impossible ending utilization would understate the cost of being full, which is
    # the entire premise of the promotion planner.
    room = np.maximum(0.0, slots - (current - units_sold))
    admitted = np.minimum(float(scheduled_arrivals), room)
    ending_inventory = current - units_sold + admitted
    ending_utilization = ending_inventory / slots if slots else np.zeros_like(ending_inventory)
    open_slots = slots - ending_inventory

    target_utilization = float(capacity["target_utilization"])

    return {
        "horizon_days": horizon_days,
        "simulation": draws.reference(),
        "unit_sales": percentile_set(units_sold, "UNITS", draws.simulation_id),
        "sales_revenue": percentile_set(revenue, "USD", draws.simulation_id),
        "front_end_gross": percentile_set(gross, "USD", draws.simulation_id),
        "net_economic_value": percentile_set(net_value, "USD", draws.simulation_id),
        "ending_inventory": percentile_set(ending_inventory, "UNITS", draws.simulation_id),
        "ending_utilization": percentile_set(ending_utilization, "RATIO", draws.simulation_id),
        "open_slots": percentile_set(open_slots, "UNITS", draws.simulation_id),
        "inbound_inventory_count": int(scheduled_arrivals),
        "cash_holding_cost": percentile_set(cash_holding, "USD", draws.simulation_id),
        "depreciation_loss": percentile_set(depreciation, "USD", draws.simulation_id),
        "risk_probabilities": {
            # Direct draw counts. These distributions are skewed and bounded, so a normal
            # approximation would misstate exactly the tail being asked about.
            "revenue_below_target": (
                probability(revenue < revenue_target) if revenue_target else None
            ),
            "utilization_above_target": probability(ending_utilization > target_utilization),
            "utilization_above_100_percent": probability(ending_utilization > 1.0),
        },
        "forecast_basis": {
            # No MCP tool supplies planned acquisitions, so run-off is the default path,
            # not an edge case (docs/open-questions.md C1).
            "mode": "RUN_OFF",
            "includes_confirmed_inbound": True,
            "includes_expected_acquisitions": False,
            "includes_scheduled_events": False,
            "lower_bound_note": (
                "Run-off forecast: assumes no replacement acquisitions, because no tool "
                "supplies planned purchases. Ending inventory, utilization, and revenue "
                "are LOWER BOUNDS — a real dealer replaces sold units."
            ),
        },
    }


# --- valuation ------------------------------------------------------------------------


def valuation(
    draws: DrawMatrix,
    vehicles: Sequence[dict],
    horizon_days: int,
) -> dict:
    """§14.3. Point-in-time sums, except expected transaction value which is a
    distribution and therefore comes from the draws."""
    total_cost = sum(v["capitalized_cost"] for v in vehicles)
    total_list = sum(v["current_list_price"] or 0.0 for v in vehicles)
    total_market = sum(v["market_value"] for v in vehicles)
    internal = [v["internal_estimate"] for v in vehicles if v.get("internal_estimate")]
    financing = sum(v.get("financing_amount", 0.0) for v in vehicles)

    sold = draws.sold_within(horizon_days)
    expected_transaction = (draws.transaction_price * sold).sum(axis=1)

    return {
        "active_inventory_count": len(vehicles),
        "total_cost_basis": total_cost,
        "total_current_list_value": total_list,
        "total_internal_base_value": sum(internal) if internal else None,
        "total_external_market_value": total_market,
        "total_expected_transaction_value": percentile_set(
            expected_transaction, "USD", draws.simulation_id
        ),
        # §14.3 marks liquidation value "if available" and no tool returns it.
        "total_liquidation_value": None,
        "total_pricing_variance": total_list - total_market,
        "total_promotional_headroom": sum(v.get("max_safe_discount", 0.0) for v in vehicles),
        "cash_tied_up": total_cost - financing,
        "segmentation": _segmentation(vehicles),
    }


def _segmentation(vehicles: Sequence[dict]) -> list[dict]:
    out: list[dict] = []
    for dimension, key_fn in (
        ("SEGMENT", lambda v: v["segment"]),
        ("MAKE", lambda v: v["make"]),
        ("AGE_BUCKET", lambda v: _bucket_label(v["days_in_inventory"])),
    ):
        groups: dict[str, list[dict]] = {}
        for vehicle in vehicles:
            groups.setdefault(key_fn(vehicle), []).append(vehicle)
        for key, members in sorted(groups.items()):
            out.append(
                {
                    "dimension": dimension,
                    "key": key,
                    "unit_count": len(members),
                    "cost_basis": sum(m["capitalized_cost"] for m in members),
                    "market_value": sum(m["market_value"] for m in members),
                }
            )
    return out


def _bucket_label(days: int) -> str:
    for low, high in AGE_BUCKETS:
        if low <= days <= high:
            return f"{low}-{high}" if high < 99999 else f"{low}+"
    return "unknown"


# --- aging ----------------------------------------------------------------------------


def aging_profile(
    draws: DrawMatrix, vehicles: Sequence[dict], horizon_days: int
) -> dict:
    """§14.4, with projected counts taken from the draws so 'how much of my inventory
    will be over 90 days in a month' is answered rather than inferred."""
    buckets = []
    aged_units = 0

    for low, high in AGE_BUCKETS:
        members = [v for v in vehicles if low <= v["days_in_inventory"] <= high]
        if low >= 91:
            aged_units += len(members)

        projected = 0
        for vehicle in members:
            i = draws.index_of(vehicle["sim_label"])
            unsold = ~draws.sold_within(horizon_days)[:, i]
            projected += float(unsold.mean())

        buckets.append(
            {
                "label": f"{low}-{high}" if high < 99999 else f"{low}+",
                "min_days": low,
                "max_days": min(high, 9999),
                "unit_count": len(members),
                "cost_basis": sum(m["capitalized_cost"] for m in members),
                "projected_unit_count_at_horizon": int(round(projected)),
            }
        )

    return {
        "buckets": buckets,
        "aged_concentration_pct": (aged_units / len(vehicles)) if vehicles else 0.0,
    }


# --- risk ranking ---------------------------------------------------------------------


def risk_ranking(
    draws: DrawMatrix, vehicles: Sequence[dict], config: Config
) -> list[dict]:
    """Rank by expected economic damage, not by age alone.

    Cost basis is a scoring input so a $45,000 unit at moderate risk outranks a $9,000
    unit at high risk. The list exists to direct attention, and attention should follow
    dollars at stake.
    """
    weights = config.portfolio["risk_weights"]
    rows: list[dict] = []

    max_cost = max((v["capitalized_cost"] for v in vehicles), default=1.0) or 1.0
    max_dep = 1.0
    max_hold = 1.0
    for vehicle in vehicles:
        i = draws.index_of(vehicle["sim_label"])
        max_dep = max(max_dep, float(np.percentile(draws.depreciation_loss[:, i], 90)))
        max_hold = max(max_hold, float(np.percentile(draws.cash_holding_cost[:, i], 90)))

    for vehicle in vehicles:
        i = draws.index_of(vehicle["sim_label"])
        projected_age = draws.days_to_sale[:, i] + vehicle["days_in_inventory"]

        prob_age = probability(projected_age > 90)
        dep_p90 = float(np.percentile(draws.depreciation_loss[:, i], 90))
        hold_p90 = float(np.percentile(draws.cash_holding_cost[:, i], 90))
        prob_negative = probability(draws.net_economic_value[:, i] < 0)
        underwater = 1.0 if vehicle["accounting_break_even"] > vehicle["market_value"] else 0.0

        score = 100.0 * (
            float(weights["prob_age_over_90"]) * prob_age
            + float(weights["p90_depreciation_loss"]) * (dep_p90 / max_dep)
            + float(weights["p90_cash_holding_cost"]) * (hold_p90 / max_hold)
            + float(weights["prob_negative_net_value"]) * prob_negative
            + float(weights["break_even_exceeds_market"]) * underwater
            + float(weights["cost_basis"]) * (vehicle["capitalized_cost"] / max_cost)
        )

        factors = []
        if underwater:
            factors.append("Break-even exceeds market value")
        if prob_age > 0.5:
            factors.append(f"{prob_age:.0%} chance of exceeding 90 days")
        if prob_negative > 0.5:
            factors.append(f"{prob_negative:.0%} chance of negative net value")
        if dep_p90 / max_dep > 0.6:
            factors.append(f"P90 depreciation ${dep_p90:,.0f}")

        rows.append(
            {
                "vehicle_id": vehicle["vehicle_id"],
                "risk_score": round(score, 1),
                "risk_factors": factors or ["No material risk flags"],
                "prob_age_over_90": prob_age,
                "p90_depreciation_loss": dep_p90,
                "prob_negative_net_value": prob_negative,
                "cost_basis": vehicle["capitalized_cost"],
            }
        )

    return sorted(rows, key=lambda r: r["risk_score"], reverse=True)


# --- actions --------------------------------------------------------------------------


def recommended_actions(
    draws: DrawMatrix, vehicles: Sequence[dict], config: Config
) -> list[dict]:
    """One action per vehicle from an ordered decision table — first match wins, so the
    mapping is auditable rather than a judgement call."""
    rules = config.portfolio["actions"]
    out: list[dict] = []

    for vehicle in vehicles:
        i = draws.index_of(vehicle["sim_label"])
        projected_age = draws.days_to_sale[:, i] + vehicle["days_in_inventory"]
        prob_age = probability(projected_age > 90)
        prob_30 = probability(draws.sold_within(30)[:, i])
        days = vehicle["days_in_inventory"]
        underwater = vehicle["accounting_break_even"] > vehicle["market_value"]
        ratio = (
            vehicle["current_list_price"] / vehicle["market_value"]
            if vehicle["current_list_price"] and vehicle["market_value"]
            else 1.0
        )

        if underwater and days > int(rules["loss_minimization_age_threshold_days"]):
            action, rule = "LOSS_MINIMIZATION_REVIEW", "underwater and aged"
        elif days > int(rules["wholesale_age_threshold_days"]):
            action, rule = "WHOLESALE_DISPOSITION", "past wholesale age threshold"
        elif vehicle["has_blocking_warning"]:
            action, rule = "MANAGER_REVIEW", "blocking warning present"
        elif prob_age > float(rules["velocity_reprice_prob_age_over_90"]) and vehicle[
            "max_safe_discount"
        ] > 0:
            action, rule = "VELOCITY_REPRICE", "high aging risk with headroom available"
        elif ratio > float(rules["overpriced_ratio"]):
            action, rule = "BALANCED_REPRICE", "priced above market"
        elif ratio < float(rules["underpriced_ratio"]) and prob_30 > float(
            rules["fast_sale_prob_30_days"]
        ):
            action, rule = "INCREASE_PRICE", "priced below market and selling quickly"
        elif days >= 21 and vehicle["max_safe_discount"] > 0:
            action, rule = "EVENT_PROMOTION", "eligible for event promotion"
        else:
            action, rule = "RETAIN_PRICE", "no action indicated"

        out.append(
            {
                "vehicle_id": vehicle["vehicle_id"],
                "action": action,
                "matched_rule": rule,
                "suggested_price": vehicle.get("recommended_price"),
                "expected_impact_p50": float(
                    np.percentile(draws.net_economic_value[:, i], 50)
                ),
            }
        )
    return out
