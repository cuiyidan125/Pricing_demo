"""Depreciation. §18, implementing D1.

    future_market_value = current_market_value * (1 - monthly_rate) ^ (days_to_sale / 30)

Applied per draw, so depreciation is consistent with that draw's days to sale.

Both `value_at_sale` and `depreciation_loss` are emitted as full percentile sets on their
own distributions. They are inversely related: `depreciation_loss.p90` and
`value_at_sale.p10` describe the same draws. §13.7 originally asked for a "P90" of each,
which cannot mean one scenario — that is the ambiguity D1 resolves.
"""

from __future__ import annotations

from pricing_agent.config import Config, banded_lookup
from pricing_agent.domain.summarize import percentile_set
from pricing_agent.simulation.engine import DrawMatrix


def effective_monthly_rate(
    segment: str,
    powertrain: str,
    age_years: float,
    mileage: int,
    config: Config,
) -> tuple[float, dict]:
    """Segment rate adjusted for powertrain, age, mileage, and market trend.

    Every factor is a prototype assumption (docs/open-questions.md C2). The EV path is
    the most consequential: a 0.026 segment rate against a 1.45 BEV multiplier compounds
    over a long holding period, which is what makes the §26.1 high-depreciation scenario
    reachable without contriving inputs.
    """
    dep = config.depreciation

    segment_rate = float(dep["by_segment"].get(segment, dep["default_monthly_rate"]))
    powertrain_mult = float(dep["powertrain_multiplier"].get(powertrain, 1.0))
    age_mult = banded_lookup(dep["vehicle_age_multiplier"], age_years, 1.0)
    mileage_mult = banded_lookup(dep["mileage_multiplier"], mileage, 1.0)
    trend_mult = float(dep.get("market_trend_multiplier", 1.0))

    rate = segment_rate * powertrain_mult * age_mult * mileage_mult * trend_mult

    components = {
        "segment_rate": segment_rate,
        "powertrain_multiplier": powertrain_mult,
        "vehicle_age_multiplier": age_mult,
        "mileage_multiplier": mileage_mult,
        "market_trend_multiplier": trend_mult,
    }
    # A monthly rate at or above 1.0 would zero the vehicle out.
    return min(rate, 0.20), components


def forecast(
    draws: DrawMatrix,
    vehicle_id: str,
    market_value: float,
    monthly_rate: float,
    components: dict,
    confidence: dict,
) -> dict:
    """Build a `depreciation-forecast.schema.json` block from the draws."""
    i = draws.index_of(vehicle_id)

    return {
        "simulation": draws.reference(),
        "current_market_value": float(market_value),
        "monthly_depreciation_rate": float(monthly_rate),
        "rate_components": components,
        "value_at_sale": percentile_set(
            draws.value_at_sale[:, i], "USD", draws.simulation_id
        ),
        "depreciation_loss": percentile_set(
            draws.depreciation_loss[:, i], "USD", draws.simulation_id
        ),
        "confidence": confidence,
        "model_version": draws.model_version,
    }


def wholesale_value(market_value: float, config: Config) -> float:
    """Disposition value for the wholesale action. No tool supplies this
    (docs/open-questions.md C1), so it is a configured fraction of market value."""
    return float(market_value) * float(config.depreciation["wholesale_value_pct_of_market"])
