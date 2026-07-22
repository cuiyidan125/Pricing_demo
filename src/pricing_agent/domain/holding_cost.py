"""Holding cost. Implements D3.

The rule that matters, from docs/fail-safe-policy.md §1:

    cash holding cost   -> enters break-even, minimum safe price, §19.1 publication bars
    slot opportunity    -> enters net economic value and promotion ranking ONLY

They are returned as two values and are never summed into one. An imputed cost inside a
price floor raises the floor above the dealer's real recovery point, and since §19.1 makes
that floor a publication bar, it would silently refuse profitable sales.
"""

from __future__ import annotations

from dataclasses import dataclass

from pricing_agent.config import Config


@dataclass(frozen=True)
class DailyHoldingCost:
    cash: float
    slot_opportunity: float
    breakdown: dict[str, float]

    @property
    def economic_total(self) -> float:
        """Both components. Valid for net economic value; never for a floor."""
        return self.cash + self.slot_opportunity


def daily_cash_holding_cost(financing_amount: float, config: Config) -> tuple[float, dict]:
    """Out-of-pocket or accrued cost per day. §17.1."""
    cash = config.holding_cost["cash"]
    floorplan = float(financing_amount) * float(cash["floorplan_annual_rate"]) / 365.0

    breakdown = {
        "floorplan_interest": floorplan,
        "lot_allocation": float(cash["lot_allocation_per_day"]),
        "insurance": float(cash["insurance_per_day"]),
        "maintenance": float(cash["maintenance_per_day"]),
        "administrative": float(cash["administrative_per_day"]),
    }
    return sum(breakdown.values()), breakdown


def daily_slot_opportunity_cost(config: Config, utilization: float | None = None) -> float:
    """Imputed cost of occupying a finite slot. §17.2.

    Circular by nature — the value of a slot depends on the portfolio that would occupy
    it — so the prototype uses a configured constant scaled by utilization rather than
    solving the fixed point (docs/open-questions.md C2). A full lot makes each slot
    dearer, which is the behaviour that makes the promotion planner's slot-release
    argument work at all.
    """
    settings = config.holding_cost["slot_opportunity"]
    base = float(settings["cost_per_day"])

    scaling = settings.get("utilization_scaling", {})
    if not scaling.get("enabled", False) or utilization is None:
        return base

    points: list[tuple[float, float]] = []
    for key, factor in scaling.items():
        if key.startswith("at_utilization_"):
            points.append((float(key.removeprefix("at_utilization_")), float(factor)))
    if not points:
        return base

    points.sort()
    if utilization <= points[0][0]:
        return base * points[0][1]
    if utilization >= points[-1][0]:
        return base * points[-1][1]

    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= utilization <= x1:
            weight = (utilization - x0) / (x1 - x0) if x1 > x0 else 0.0
            return base * (y0 + weight * (y1 - y0))
    return base


def daily_holding_cost(
    financing_amount: float, config: Config, utilization: float | None = None
) -> DailyHoldingCost:
    cash, breakdown = daily_cash_holding_cost(financing_amount, config)
    slot = daily_slot_opportunity_cost(config, utilization)
    breakdown = dict(breakdown)
    breakdown["slot_opportunity_imputed"] = slot
    return DailyHoldingCost(cash=cash, slot_opportunity=slot, breakdown=breakdown)
