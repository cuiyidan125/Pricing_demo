"""Seeded Monte Carlo producing the DrawMatrix. Implements D2.

The load-bearing interface of the system (docs/architecture.md §6). Every reported figure
in every skill is summarized from one of these, so §12.5 holds by construction rather than
by discipline: quantities that are functions of several others are computed per draw and
only then summarized.

Two modeling choices carry weight:

* **One simulation covers every vehicle in scope**, sharing a per-draw market factor.
  Per-vehicle simulations stitched together would be independent, which would discard the
  shared market conditions that make portfolio outcomes correlated — and would make the
  §14.7 prohibition on summing medians a distinction without a difference.
* **Sale timing uses cumulative hazard with an exponential threshold.** A draw sells on
  the first day its accumulated hazard exceeds its threshold. This handles a time-varying
  hazard exactly, lets the market factor scale the threshold instead of the whole curve,
  and keeps memory at (vehicles × horizon) rather than (draws × vehicles × horizon).
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Sequence

import numpy as np

from pricing_agent.config import Config
from pricing_agent.simulation.hazard import VehicleSimInput, build_hazard_curve

_NAMESPACE = uuid.UUID("6f9d3d5a-1c2b-4f7e-9a10-5c1d2e3f4a5b")


@dataclass(frozen=True)
class DrawMatrix:
    """Per-draw outcomes. All arrays are shape (draw_count, n_vehicles)."""

    simulation_id: str
    seed: int
    draw_count: int
    horizon_days: int
    model_label: str
    model_version: str
    assumption_version: str
    vehicle_ids: tuple[str, ...]

    days_to_sale: np.ndarray
    sold_within_horizon: np.ndarray
    transaction_price: np.ndarray
    cash_holding_cost: np.ndarray
    slot_opportunity_cost: np.ndarray
    depreciation_loss: np.ndarray
    value_at_sale: np.ndarray
    front_end_gross: np.ndarray
    net_economic_value: np.ndarray

    def index_of(self, vehicle_id: str) -> int:
        return self.vehicle_ids.index(vehicle_id)

    def column(self, vehicle_id: str) -> int:
        return self.index_of(vehicle_id)

    def sold_within(self, horizon: int) -> np.ndarray:
        """Boolean mask of draws in which a vehicle sold within `horizon` days."""
        return self.sold_within_horizon & (self.days_to_sale <= horizon)

    def slice_vehicle(self, vehicle_id: str) -> "DrawMatrix":
        """A single-vehicle view retaining the same simulation_id.

        The id is preserved deliberately: these draws came from the same simulation as
        the portfolio's, so quantities derived from them remain jointly combinable.
        """
        i = self.index_of(vehicle_id)
        take = lambda a: a[:, i : i + 1]  # noqa: E731
        return DrawMatrix(
            simulation_id=self.simulation_id,
            seed=self.seed,
            draw_count=self.draw_count,
            horizon_days=self.horizon_days,
            model_label=self.model_label,
            model_version=self.model_version,
            assumption_version=self.assumption_version,
            vehicle_ids=(vehicle_id,),
            days_to_sale=take(self.days_to_sale),
            sold_within_horizon=take(self.sold_within_horizon),
            transaction_price=take(self.transaction_price),
            cash_holding_cost=take(self.cash_holding_cost),
            slot_opportunity_cost=take(self.slot_opportunity_cost),
            depreciation_loss=take(self.depreciation_loss),
            value_at_sale=take(self.value_at_sale),
            front_end_gross=take(self.front_end_gross),
            net_economic_value=take(self.net_economic_value),
        )

    def reference(self) -> dict:
        """The `simulationRef` block required by every result schema."""
        return {
            "simulation_id": self.simulation_id,
            "seed": self.seed,
            "draw_count": self.draw_count,
            "horizon_days": self.horizon_days,
            "model_label": self.model_label,
            "model_version": self.model_version,
            "assumption_version": self.assumption_version,
        }


def _simulation_id(
    seed: int, draw_count: int, horizon: int, vehicles: Sequence[VehicleSimInput]
) -> str:
    """Deterministic from the inputs, so identical runs share an id and differing runs
    do not. That is what makes the §12.5 joint-combination check meaningful: two
    distributions carry the same id exactly when they came from the same draws."""
    fingerprint = "|".join(
        [
            str(seed),
            str(draw_count),
            str(horizon),
            *(
                f"{v.vehicle_id}:{v.effective_list_price:.2f}:{v.market_value:.2f}:"
                f"{v.days_in_inventory}:{v.median_days_to_sale:.4f}:"
                f"{len(v.event_windows)}"
                for v in vehicles
            ),
        ]
    )
    return f"sim_{uuid.uuid5(_NAMESPACE, fingerprint).hex[:16]}"


def simulate(
    vehicles: Sequence[VehicleSimInput],
    config: Config,
    as_of: date,
    seed: int | None = None,
    draw_count: int | None = None,
    horizon_days: int | None = None,
) -> DrawMatrix:
    """Run one simulation covering every supplied vehicle."""
    if not vehicles:
        raise ValueError("simulate() requires at least one vehicle")

    run = config.simulation["run"]
    seed = int(run["seed"]) if seed is None else int(seed)
    draws = int(run["draw_count"]) if draw_count is None else int(draw_count)
    horizon = int(run["horizon_days"]) if horizon_days is None else int(horizon_days)

    n = len(vehicles)
    rng = np.random.default_rng(seed)

    # --- sale timing ------------------------------------------------------------------

    # Cumulative hazard per vehicle, shape (n, horizon).
    cumulative = np.empty((n, horizon), dtype=float)
    for i, vehicle in enumerate(vehicles):
        cumulative[i] = np.cumsum(build_hazard_curve(vehicle, config, horizon, as_of))

    # One market factor per draw, applied to every vehicle in that draw.
    sd = float(run.get("market_factor_sd", 0.0))
    if sd > 0:
        # Mean-one lognormal, so the factor reweights draws without shifting the
        # average pace of the market.
        market_factor = rng.lognormal(mean=-0.5 * sd**2, sigma=sd, size=(draws, 1))
    else:
        market_factor = np.ones((draws, 1))

    thresholds = rng.exponential(scale=1.0, size=(draws, n))

    # Weibull shape. With k = 1 the hazard is memoryless and P90/P50 is locked at ~3.3;
    # k > 1 models a rising hazard and compresses the tail. The (ln 2) factor renormalizes
    # so the median is unchanged by the reshaping — only the spread moves.
    shape_k = float(run.get("time_to_sale_shape_k", 1.0))
    if shape_k != 1.0:
        thresholds = thresholds ** (1.0 / shape_k) * (math.log(2.0) ** (1.0 - 1.0 / shape_k))

    thresholds = thresholds / market_factor

    days_to_sale = np.empty((draws, n), dtype=np.int32)
    sold = np.empty((draws, n), dtype=bool)
    for i in range(n):
        # First day on which accumulated hazard exceeds the draw's threshold.
        idx = np.searchsorted(cumulative[i], thresholds[:, i], side="left")
        sold[:, i] = idx < horizon
        days_to_sale[:, i] = np.minimum(idx + 1, horizon)

    # --- transaction price ------------------------------------------------------------

    price_cfg = config.simulation["transaction_price"]
    price_sd = float(price_cfg["discount_dispersion_sd"])
    # Config states the correlation between *speed* and discount; fast sales concede
    # less. Days is the inverse of speed, so the sign flips here.
    rho = -float(price_cfg["speed_discount_correlation"])
    rho = float(np.clip(rho, -0.99, 0.99))

    days_float = days_to_sale.astype(float)
    mean = days_float.mean(axis=0, keepdims=True)
    std = days_float.std(axis=0, keepdims=True)
    days_z = np.divide(days_float - mean, std, out=np.zeros_like(days_float), where=std > 0)

    z_indep = rng.standard_normal(size=(draws, n))
    z_discount = rho * days_z + np.sqrt(1.0 - rho**2) * z_indep

    expected_rate = np.array([v.expected_discount_rate for v in vehicles])[None, :]
    discount_rate = np.clip(
        expected_rate + price_sd * z_discount,
        float(price_cfg["min_discount_rate"]),
        float(price_cfg["max_discount_rate"]),
    )

    list_price = np.array([v.effective_list_price for v in vehicles])[None, :]
    transaction_price = list_price * (1.0 - discount_rate)

    # --- per-draw financial chain (docs/forecast-definitions.md §5.3) -----------------

    daily_cash = np.array([v.daily_cash_holding_cost for v in vehicles])[None, :]
    daily_slot = np.array([v.daily_slot_opportunity_cost for v in vehicles])[None, :]
    market_value = np.array([v.market_value for v in vehicles])[None, :]
    monthly_dep = np.array([v.monthly_depreciation_rate for v in vehicles])[None, :]
    total_cost = np.array([v.total_cost for v in vehicles])[None, :]
    selling_costs = np.array([v.direct_selling_costs for v in vehicles])[None, :]

    cash_holding_cost = daily_cash * days_float
    slot_opportunity_cost = daily_slot * days_float

    value_at_sale = market_value * np.power(1.0 - monthly_dep, days_float / 30.0)
    depreciation_loss = market_value - value_at_sale

    front_end_gross = transaction_price - total_cost - selling_costs

    # NOTE: a price discount is NOT subtracted again here. It already flows through
    # `effective_list_price` into transaction_price, so adding it as a separate promotion
    # cost would double-count it. §11.6's promotion-cost term covers costs not reflected
    # in the price, of which this prototype models none.
    net_economic_value = (
        front_end_gross - cash_holding_cost - depreciation_loss - slot_opportunity_cost
    )

    return DrawMatrix(
        simulation_id=_simulation_id(seed, draws, horizon, vehicles),
        seed=seed,
        draw_count=draws,
        horizon_days=horizon,
        model_label=config.model_label,
        model_version=config.model_version,
        assumption_version=config.assumption_version,
        vehicle_ids=tuple(v.vehicle_id for v in vehicles),
        days_to_sale=days_to_sale,
        sold_within_horizon=sold,
        transaction_price=transaction_price,
        cash_holding_cost=cash_holding_cost,
        slot_opportunity_cost=slot_opportunity_cost,
        depreciation_loss=depreciation_loss,
        value_at_sale=value_at_sale,
        front_end_gross=front_end_gross,
        net_economic_value=net_economic_value,
    )
