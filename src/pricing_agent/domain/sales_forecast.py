"""Sales outcome summaries. §13.6, implementing D1 and D2.

Everything here is summarized from one draw matrix, so the reported figures are jointly
consistent by construction. Sale probabilities are direct draw counts rather than normal
approximations — the underlying distribution is skewed and bounded, and an approximation
would misstate exactly the tail being asked about.
"""

from __future__ import annotations

import numpy as np

from pricing_agent.domain.summarize import percentile_set, probability
from pricing_agent.simulation.engine import DrawMatrix

SALE_HORIZONS = (7, 30, 60, 90)
AGE_THRESHOLDS = (60, 90, 120)


def build(draws: DrawMatrix, vehicle_id: str, days_in_inventory: int) -> dict:
    """Build a `sales-outcome-distribution.schema.json` block."""
    i = draws.index_of(vehicle_id)

    days = draws.days_to_sale[:, i].astype(float)
    sold = draws.sold_within_horizon[:, i]
    censored_fraction = float(1.0 - sold.mean())

    # §12.3 — computed per draw. days_in_inventory is a constant here, so the result
    # coincides with a shifted marginal; the per-draw rule is followed anyway so nobody
    # reads this as licence to combine marginals elsewhere.
    projected_age = days + float(days_in_inventory)

    return {
        "simulation": draws.reference(),
        "additional_days_to_sale": percentile_set(
            days,
            "DAYS",
            draws.simulation_id,
            quartiles=True,
            censored_above=draws.horizon_days,
            censored_fraction=censored_fraction,
        ),
        "projected_total_inventory_age": percentile_set(
            projected_age,
            "DAYS",
            draws.simulation_id,
            quartiles=True,
            censored_above=draws.horizon_days + days_in_inventory,
            censored_fraction=censored_fraction,
        ),
        "transaction_price": percentile_set(
            draws.transaction_price[:, i], "USD", draws.simulation_id, quartiles=True
        ),
        "sale_probabilities": {
            f"within_{h}_days": probability(sold & (days <= h)) for h in SALE_HORIZONS
        },
        "projected_age_exceedance": {
            f"over_{t}_days": probability(projected_age > t) for t in AGE_THRESHOLDS
        },
        "censoring": {
            "horizon_days": draws.horizon_days,
            "censored_fraction": censored_fraction,
        },
    }


def scenario_block(draws: DrawMatrix, vehicle_id: str, days_in_inventory: int) -> dict:
    """The distributional fields §13.5 requires on each pricing scenario."""
    i = draws.index_of(vehicle_id)
    days = draws.days_to_sale[:, i].astype(float)
    sold = draws.sold_within_horizon[:, i]

    return {
        "transaction_price": percentile_set(
            draws.transaction_price[:, i], "USD", draws.simulation_id
        ),
        "additional_days_to_sale": percentile_set(days, "DAYS", draws.simulation_id),
        "projected_total_inventory_age": percentile_set(
            days + float(days_in_inventory), "DAYS", draws.simulation_id
        ),
        "sale_probabilities": {
            f"within_{h}_days": probability(sold & (days <= h)) for h in (30, 60, 90)
        },
        # Exposure to the bad tail, which is what the strategy-selection rule keys on
        # for aged vehicles rather than the median.
        "projected_age_exceedance": {
            f"over_{t}_days": probability(days + float(days_in_inventory) > t)
            for t in AGE_THRESHOLDS
        },
        # D3: the two holding-cost components stay separate all the way to the output.
        "expected_cash_holding_cost": percentile_set(
            draws.cash_holding_cost[:, i], "USD", draws.simulation_id
        ),
        "expected_slot_opportunity_cost": percentile_set(
            draws.slot_opportunity_cost[:, i], "USD", draws.simulation_id
        ),
        "expected_depreciation_loss": percentile_set(
            draws.depreciation_loss[:, i], "USD", draws.simulation_id
        ),
        "expected_front_end_gross": percentile_set(
            draws.front_end_gross[:, i], "USD", draws.simulation_id
        ),
        # NOT gross minus the P50 of each cost — summarized from draws in which price,
        # timing, and costs are jointly consistent (§12.5).
        "expected_net_economic_value": percentile_set(
            draws.net_economic_value[:, i], "USD", draws.simulation_id
        ),
    }
