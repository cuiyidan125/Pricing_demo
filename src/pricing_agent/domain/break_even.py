"""Break-even and price floors. Implements D3 and D4.

**Only cash holding cost enters anything in this module.** Slot opportunity cost is
imputed; including it would raise the floor above the dealer's real recovery point, and
since §19.1 makes that floor a publication bar it would silently refuse profitable sales
(docs/fail-safe-policy.md §1).
"""

from __future__ import annotations

import numpy as np

from pricing_agent.config import Config
from pricing_agent.domain.summarize import percentile_set, probability
from pricing_agent.domain.vehicle import CostBasis
from pricing_agent.simulation.engine import DrawMatrix

_CONSTRAINTS = {
    "accounting": "ACCOUNTING_BREAK_EVEN",
    "policy": "POLICY_FLOOR",
    "financing": "FINANCING",
    "risk": "RISK_FLOOR",
}


def current_accounting_break_even(cost_basis: CostBasis) -> float:
    """§11.7 — costs already incurred or contractually committed as of today.

    No future costs, no imputed costs. This is the figure a controller would recognise.
    """
    return (
        cost_basis.capitalized_cost
        + cost_basis.accrued_cash_holding_cost
        + cost_basis.direct_selling_costs
    )


def analyze(
    cost_basis: CostBasis,
    market_value: float,
    draws: DrawMatrix,
    vehicle_id: str,
    daily_cash_holding_cost: float,
    expected_discount_rate: float,
    policy: dict | None,
    config: Config,
) -> dict:
    """Build a `break-even-analysis.schema.json` block."""
    i = draws.index_of(vehicle_id)
    accounting = current_accounting_break_even(cost_basis)

    # §11.8 — current costs plus expected future cash cost until sale, per draw.
    days = draws.days_to_sale[:, i].astype(float)
    projected = accounting + daily_cash_holding_cost * days

    pricing_cfg = config.pricing
    policy = policy or {}

    floor_rule = policy.get("policy_price_floor_rule", {})
    multiple = float(
        floor_rule.get("cost_basis_multiple", pricing_cfg["policy_floor"]["cost_basis_multiple"])
    )
    minimum_gross = float(
        policy.get("minimum_gross_policy", pricing_cfg["policy_floor"]["minimum_gross_policy"])
    )
    risk_pct = float(
        policy.get("risk_floor_pct", pricing_cfg["policy_floor"]["risk_floor_pct_of_market"])
    )

    policy_floor = cost_basis.capitalized_cost * multiple + minimum_gross
    risk_floor = market_value * risk_pct
    financing = cost_basis.financing_amount or 0.0

    candidates = {
        "accounting": accounting,
        "policy": policy_floor,
        "financing": financing,
        "risk": risk_floor,
    }
    binding_key = max(candidates, key=lambda k: candidates[k])
    minimum_safe_transaction_price = candidates[binding_key]

    # §11.11 — a vehicle listed exactly at its minimum safe transaction price will
    # transact BELOW it after normal negotiation.
    minimum_safe_list_price = minimum_safe_transaction_price / (1.0 - expected_discount_rate)

    value_at_sale = draws.value_at_sale[:, i]
    crossover_prob = probability(projected > value_at_sale)

    return {
        "simulation": draws.reference(),
        "cost_components": {
            "acquisition_cost": cost_basis.acquisition_cost,
            "auction_fee": cost_basis.auction_fee,
            "transportation_cost": cost_basis.transportation_cost,
            "reconditioning_cost": cost_basis.reconditioning_cost,
            "accrued_cash_holding_cost": cost_basis.accrued_cash_holding_cost,
            "direct_selling_costs": cost_basis.direct_selling_costs,
        },
        "current_accounting_break_even": accounting,
        "projected_break_even": percentile_set(projected, "USD", draws.simulation_id),
        "floors": {
            "hard_price_floor": max(policy_floor, financing, risk_floor),
            "policy_price_floor": policy_floor,
            "financing_constraint": financing or None,
            "risk_floor": risk_floor,
            "binding_constraint": _CONSTRAINTS[binding_key],
        },
        "minimum_safe_transaction_price": minimum_safe_transaction_price,
        "minimum_safe_list_price": minimum_safe_list_price,
        "expected_discount_rate_used": expected_discount_rate,
        "probability_of_loss": probability(draws.transaction_price[:, i] < accounting),
        "market_value_crossover_risk": {
            "break_even_exceeds_market_value_now": bool(accounting > market_value),
            "probability_crossover_within_horizon": crossover_prob,
            "estimated_crossover_days": _crossover_days(
                accounting, daily_cash_holding_cost, market_value, draws, i
            ),
        },
    }


def _crossover_days(
    accounting: float,
    daily_cash: float,
    market_value: float,
    draws: DrawMatrix,
    index: int,
) -> int | None:
    """Days until the rising break-even meets the falling market value, on median paths.

    None when they never meet inside the horizon — or when they have already crossed,
    which the `break_even_exceeds_market_value_now` flag reports instead.
    """
    if accounting > market_value:
        return None

    horizon = draws.horizon_days
    day_grid = np.arange(1, horizon + 1, dtype=float)
    break_even_path = accounting + daily_cash * day_grid

    # Median depreciation path, recovered from the draws rather than re-derived.
    days = draws.days_to_sale[:, index].astype(float)
    values = draws.value_at_sale[:, index]
    order = np.argsort(days)
    value_path = np.interp(day_grid, days[order], values[order])

    crossed = np.nonzero(break_even_path > value_path)[0]
    return int(crossed[0] + 1) if crossed.size else None
