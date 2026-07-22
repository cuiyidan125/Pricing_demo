"""Publication bars and price-point rounding. §19.1.

**The policy layer never alters a computed number.** A price violating a floor is
reported unchanged beside a BLOCKING warning; it is not quietly raised to the floor.
That keeps the audit record honest — what the system computed and what policy did about
it stay two separately reviewable facts (docs/architecture.md §7).

The one exception is `round_to_price_point`, which is a *presentation* rule applied when
constructing a candidate price, before policy runs — not a correction applied after.
"""

from __future__ import annotations

import math

from pricing_agent.config import Config


def round_to_price_point(price: float, config: Config, floor: float | None = None) -> float:
    """Round to a retail price point (18995, 24995).

    Never rounds below a supplied floor: shaving $5 off a price to make it look retail
    must not push it under the minimum safe list price.
    """
    settings = config.pricing.get("price_point_rounding", {})
    if not settings.get("enabled", False):
        return round(price, 2)

    step = float(settings.get("round_to", 100))
    offset = float(settings.get("offset", -5))

    rounded = math.floor(price / step) * step + offset
    if rounded > price:
        rounded -= step

    if (
        floor is not None
        and settings.get("never_round_below_floor", True)
        and rounded < floor
    ):
        rounded = math.ceil(floor / step) * step + offset
        if rounded < floor:
            rounded += step

    return float(rounded)


def publication_bars(warnings: list[dict]) -> list[str]:
    """Codes currently refusing publication."""
    return sorted({w["code"] for w in warnings if w.get("blocks_publication")})


def can_publish(warnings: list[dict], stale_realtime: list[str]) -> tuple[bool, list[str]]:
    """Whether `publish_vehicle_price` would be accepted, and why not."""
    reasons: list[str] = []
    bars = publication_bars(warnings)
    if bars:
        reasons.append("Unresolved BLOCKING warnings: " + ", ".join(bars))
    if stale_realtime:
        reasons.append("Stale REALTIME data: " + ", ".join(sorted(stale_realtime)))
    return (not reasons), reasons
