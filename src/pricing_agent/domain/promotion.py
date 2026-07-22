"""Promotional headroom and the discount ladder. §13.9, §15.7.

`economically_sensible_discount` is found by **simulation, not formula**: the vehicle is
re-simulated at each rung of a discount ladder and the rung maximizing P50 net economic
value wins. The point where faster turn stops paying for the margin it costs depends on
the specific vehicle's holding cost, depreciation rate, and price position, so no closed
form would be defensible.

Slot opportunity cost IS included in that optimization (D3) — it belongs in an economic
tradeoff. It is excluded from `minimum_safe_list_price`, which is a floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from pricing_agent.config import Config
from pricing_agent.simulation.engine import DrawMatrix

# A callable that re-runs the simulation with `discount` taken off the list price.
Resimulate = Callable[[float], DrawMatrix]


@dataclass(frozen=True)
class Headroom:
    reference_list_price: float
    minimum_safe_list_price: float
    max_safe_discount: float
    max_accounting_discount: float
    used_headroom: float
    reserves: dict[str, float]

    def as_dict(self, economically_sensible: float, recommended: float, ladder: list[dict]) -> dict:
        return {
            "reference_list_price": self.reference_list_price,
            "minimum_safe_list_price": self.minimum_safe_list_price,
            "reserves": self.reserves,
            "max_accounting_discount": self.max_accounting_discount,
            "max_safe_discount": self.max_safe_discount,
            "economically_sensible_discount": economically_sensible,
            "recommended_promotion_discount": recommended,
            "used_headroom": self.used_headroom,
            "remaining_headroom": max(0.0, self.max_safe_discount - recommended),
            "ladder": ladder,
        }


def headroom(
    reference_list_price: float,
    minimum_safe_list_price: float,
    accounting_break_even: float,
    expected_discount_rate: float,
    original_list_price: float | None,
    config: Config,
) -> Headroom:
    """Distance from the reference price down to the safe floor, split into reserves."""
    max_safe = max(0.0, reference_list_price - minimum_safe_list_price)

    # The list price at which the expected transaction lands exactly on break-even.
    accounting_list_equivalent = accounting_break_even / (1.0 - expected_discount_rate)
    max_accounting = max(0.0, reference_list_price - accounting_list_equivalent)

    shares = config.discounting["reserves"]
    reserves = {
        "negotiation_reserve": max_safe * float(shares["negotiation"]),
        "event_promotion_reserve": max_safe * float(shares["event_promotion"]),
        "emergency_markdown_reserve": max_safe * float(shares["emergency_markdown"]),
    }

    used = 0.0
    if original_list_price is not None:
        used = max(0.0, original_list_price - reference_list_price)

    return Headroom(
        reference_list_price=reference_list_price,
        minimum_safe_list_price=minimum_safe_list_price,
        max_safe_discount=max_safe,
        max_accounting_discount=max_accounting,
        used_headroom=used,
        reserves=reserves,
    )


def discount_ladder(
    resimulate: Resimulate,
    vehicle_id: str,
    reference_list_price: float,
    max_safe_discount: float,
    config: Config,
) -> tuple[list[dict], float]:
    """Walk the ladder, returning (rungs, economically_sensible_discount).

    The evaluated ladder is retained so the chosen rung is auditable rather than
    asserted — a merchandising manager can see the curve that produced the answer.

    Rungs are simulated at a reduced draw count for the search; the caller re-runs the
    winning rung at full count.
    """
    settings = config.promotion["discount_ladder"]
    step = float(settings["step_usd"])
    max_steps = int(settings["max_steps"])

    if max_safe_discount <= 0 or step <= 0:
        return [], 0.0

    rungs: list[dict] = []
    for n in range(max_steps):
        discount = min(n * step, max_safe_discount)
        draws = resimulate(discount)
        i = draws.index_of(vehicle_id)

        rungs.append(
            {
                "discount": discount,
                "list_price": reference_list_price - discount,
                "p50_net_economic_value": float(
                    np.percentile(draws.net_economic_value[:, i], 50)
                ),
                "p50_days_to_sale": float(np.percentile(draws.days_to_sale[:, i], 50)),
                "exceeds_safe_discount": discount > max_safe_discount,
            }
        )
        if discount >= max_safe_discount:
            break

    best = max(rungs, key=lambda r: r["p50_net_economic_value"])
    return rungs, float(best["discount"])


def recommended_discount(
    economically_sensible: float,
    max_safe: float,
    budget_remaining: float | None = None,
) -> float:
    """min(economically sensible, max safe, what the budget allows)."""
    candidates = [economically_sensible, max_safe]
    if budget_remaining is not None:
        candidates.append(max(0.0, budget_remaining))
    return float(min(candidates))
