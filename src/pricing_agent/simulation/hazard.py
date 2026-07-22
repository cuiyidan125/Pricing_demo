"""Daily sale hazard. docs/forecast-definitions.md §5.1.

Produces a per-day hazard curve per vehicle. Time-varying, so event windows and
seasonality are modeled where they actually fall rather than averaged across the horizon.

Every multiplier here is a configured assumption. `price_position` in particular is the
elasticity driving every velocity-versus-gross tradeoff in the product, and it is not
calibrated (docs/open-questions.md C3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from pricing_agent.config import Config, banded_lookup, interpolate


@dataclass(frozen=True)
class EventWindow:
    """A lift multiplier applying only between two day offsets from `as_of`."""

    start_day: int
    end_day: int
    lift: float


@dataclass(frozen=True)
class VehicleSimInput:
    """Everything the simulation needs about one vehicle.

    Assembled by the skill layer from MCP responses. The simulation performs no I/O and
    never looks anything up for itself.
    """

    vehicle_id: str
    list_price: float
    market_value: float
    days_in_inventory: int
    mileage: int
    condition: str
    segment: str
    vehicle_age_years: float
    median_days_to_sale: float
    supply_to_sales_ratio: float
    total_cost: float  # acquisition + auction fee + transport + reconditioning
    direct_selling_costs: float
    daily_cash_holding_cost: float
    daily_slot_opportunity_cost: float
    monthly_depreciation_rate: float
    expected_discount_rate: float
    engagement_vdp_views: float | None = None
    promotion_discount: float = 0.0
    event_windows: tuple[EventWindow, ...] = field(default_factory=tuple)

    @property
    def price_to_market(self) -> float:
        if self.market_value <= 0:
            return 1.0
        return self.effective_list_price / self.market_value

    @property
    def effective_list_price(self) -> float:
        return max(self.list_price - self.promotion_discount, 0.0)


def engagement_multiplier(vdp_views: float | None, config: Config) -> float:
    """Bounded multiplier from shopper engagement, or exactly 1.0 when unavailable.

    §9.8 requires the system to continue with reduced confidence when engagement is
    missing. The term is dropped rather than defaulted, because substituting a neutral
    value that *looks* like data would hide the gap from the confidence score.
    """
    settings = config.simulation["hazard"]["engagement"]
    if vdp_views is None or not settings.get("enabled_when_available", True):
        return float(settings["neutral_multiplier"])

    reference = float(settings["reference_vdp_views"])
    elasticity = float(settings["elasticity"])
    if reference <= 0 or vdp_views <= 0:
        return float(settings["neutral_multiplier"])

    raw = (vdp_views / reference) ** elasticity
    return float(
        np.clip(raw, float(settings["min_multiplier"]), float(settings["max_multiplier"]))
    )


def static_multiplier(vehicle: VehicleSimInput, config: Config) -> float:
    """The part of the hazard that does not vary across the horizon."""
    hazard = config.simulation["hazard"]

    price_mult = interpolate(hazard["price_position"], vehicle.price_to_market)
    mileage_mult = banded_lookup(hazard["mileage"], vehicle.mileage, 1.0)
    condition_mult = float(hazard["condition"].get(vehicle.condition, hazard["condition"]["UNKNOWN"]))
    supply_mult = interpolate(hazard["supply"], vehicle.supply_to_sales_ratio)
    engagement_mult = engagement_multiplier(vehicle.engagement_vdp_views, config)
    dealer_mult = float(hazard.get("dealer_performance_multiplier", 1.0))

    # A vehicle that has already sat is modeled as slightly harder to move.
    drift = float(hazard.get("aging_drift_per_30_days", 0.0))
    aging_mult = max(0.40, 1.0 + drift * (vehicle.days_in_inventory / 30.0))

    return (
        price_mult
        * mileage_mult
        * condition_mult
        * supply_mult
        * engagement_mult
        * dealer_mult
        * aging_mult
    )


def build_hazard_curve(
    vehicle: VehicleSimInput,
    config: Config,
    horizon_days: int,
    as_of: date,
) -> np.ndarray:
    """Per-day hazard over the horizon, shape (horizon_days,).

    Seasonality is applied by the calendar month each day actually falls in, and event
    lift only inside its window, so a promotion three weeks out does not silently speed
    up the first three weeks.
    """
    if vehicle.median_days_to_sale <= 0:
        raise ValueError(f"{vehicle.vehicle_id}: median_days_to_sale must be positive")

    base = 1.0 / float(vehicle.median_days_to_sale)
    curve = np.full(horizon_days, base * static_multiplier(vehicle, config), dtype=float)

    # Seasonality, by the month each day lands in.
    seasonality = config.simulation["hazard"].get("seasonality", {})
    if seasonality:
        day_offsets = np.arange(horizon_days)
        months = np.array(
            [((as_of.month - 1 + int(d // 30)) % 12) + 1 for d in day_offsets]
        )
        factors = np.array([float(seasonality.get(str(m), 1.0)) for m in months])
        curve *= factors

    # Event lift, only inside the window.
    max_lift = float(config.simulation.get("event", {}).get("max_lift_multiplier", 2.5))
    for window in vehicle.event_windows:
        start = max(0, window.start_day)
        end = min(horizon_days, window.end_day + 1)
        if start < end:
            curve[start:end] *= min(float(window.lift), max_lift)

    # A daily hazard at or above 1.0 is not meaningful.
    return np.clip(curve, 1e-6, 0.95)
