"""The §14.7 prohibition, tested directly on the aggregation rather than through a skill.

§14.7 says do not add individual P50 forecasts. The reason is easiest to see at P10: with
five vehicles each ~40% likely to sell, no single vehicle has a 90% chance, so every
per-vehicle P10 contribution is exactly zero — while the portfolio obviously sells
something even in a bad month. Marginals cannot reconstruct that.

Constructed here rather than read off the fixtures, so the property is asserted on
arithmetic we control instead of on whatever the current calibration happens to produce.
"""

from __future__ import annotations

import numpy as np

from pricing_agent.simulation.engine import DrawMatrix


def _matrix(draws: int = 2000, vehicles: int = 5, sale_probability: float = 0.4) -> DrawMatrix:
    rng = np.random.default_rng(20260721)
    sold = rng.random((draws, vehicles)) < sale_probability
    days = np.where(sold, 15, 400).astype(np.int32)
    price = np.full((draws, vehicles), 25_000.0)
    zeros = np.zeros((draws, vehicles))

    return DrawMatrix(
        simulation_id="sim_test",
        seed=20260721,
        draw_count=draws,
        horizon_days=365,
        model_label="CONFIGURABLE_PROTOTYPE_SIMULATION",
        model_version="test",
        assumption_version="test",
        vehicle_ids=tuple(f"V-{i}" for i in range(vehicles)),
        days_to_sale=days,
        sold_within_horizon=sold,
        transaction_price=price,
        cash_holding_cost=zeros,
        slot_opportunity_cost=zeros,
        depreciation_loss=zeros,
        value_at_sale=price,
        front_end_gross=zeros,
        net_economic_value=zeros,
    )


def test_no_vehicle_reaches_the_ninetieth_percentile_alone():
    matrix = _matrix()
    mask = matrix.sold_within(30)
    assert mask.mean(axis=0).max() < 0.9


def test_marginal_p10_contributions_sum_to_zero_while_the_portfolio_does_not():
    matrix = _matrix()
    mask = matrix.sold_within(30)
    contributions = matrix.transaction_price * mask

    marginal_sum = sum(
        float(np.percentile(contributions[:, i], 10)) for i in range(len(matrix.vehicle_ids))
    )
    portfolio = float(np.percentile(contributions.sum(axis=1), 10))

    # Every marginal contributes nothing at P10, yet the lot still moves a car in its
    # 10th-percentile draw. That gap is the whole reason §14.7 exists.
    assert marginal_sum == 0.0
    assert portfolio >= 25_000.0, "the portfolio sells at least one car in a bad month"
    assert portfolio > marginal_sum


def test_portfolio_median_is_not_the_sum_of_medians():
    matrix = _matrix()
    mask = matrix.sold_within(30)
    contributions = matrix.transaction_price * mask

    marginal_sum = sum(
        float(np.percentile(contributions[:, i], 50)) for i in range(len(matrix.vehicle_ids))
    )
    portfolio = float(np.percentile(contributions.sum(axis=1), 50))

    # At a 40% sale probability every marginal median is zero, yet the lot sells two cars
    # in its median draw. The direction is not the point; the inequality is.
    assert portfolio != marginal_sum
