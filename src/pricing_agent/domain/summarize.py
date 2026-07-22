"""The only producer of percentile sets. Implements D1 and D2.

Every distributional figure in every result passes through here, which is what lets the
system enforce two rules mechanically rather than by convention:

* **Percentiles are taken on the named quantity's own distribution** (convention
  `OWN_DISTRIBUTION_V1`). `depreciation_loss.p90` and `value_at_sale.p10` describe the
  same draws; `depreciation_loss.p90` and `value_at_sale.p90` do not. Risk direction per
  quantity is normative in docs/forecast-definitions.md §1.1.
* **Every set carries the `simulation_id` it came from.** `require_same_simulation`
  refuses to combine sets from different runs, which is the enforceable form of the
  §12.5 joint-distribution warning.

Nothing else in the codebase may call `numpy.percentile` on simulation output.
"""

from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

PERCENTILE_CONVENTION = "OWN_DISTRIBUTION_V1"

# Which tail is the adverse one, per docs/forecast-definitions.md §1.1. Consumed by the
# explanation allow-list so a narrative cannot quote the optimistic tail of a
# loss-bearing quantity.
RISK_DIRECTION: Mapping[str, str] = {
    "additional_days_to_sale": "UPSIDE_IS_P10",
    "projected_total_inventory_age": "UPSIDE_IS_P10",
    "transaction_price": "UPSIDE_IS_P90",
    "value_at_sale": "UPSIDE_IS_P90",
    "depreciation_loss": "UPSIDE_IS_P10",
    "cash_holding_cost": "UPSIDE_IS_P10",
    "slot_opportunity_cost": "UPSIDE_IS_P10",
    "projected_break_even": "UPSIDE_IS_P10",
    "front_end_gross": "UPSIDE_IS_P90",
    "net_economic_value": "UPSIDE_IS_P90",
    "unit_sales": "UPSIDE_IS_P90",
    "sales_revenue": "UPSIDE_IS_P90",
    "ending_inventory": "UPSIDE_IS_P10",
    "ending_utilization": "UPSIDE_IS_P10",
}


class SimulationMismatch(RuntimeError):
    """Raised when figures from different simulations would be combined.

    §12.5 forbids implying that the P90 of several quantities occur in one scenario.
    Combining across simulations is the mechanical form of that error.
    """


def percentile_set(
    values: np.ndarray,
    unit: str,
    simulation_id: str,
    *,
    quartiles: bool = False,
    censored_above: float | None = None,
    censored_fraction: float | None = None,
) -> dict:
    """Summarize one quantity. Shape may be (draws,) or (draws, 1)."""
    flat = np.asarray(values, dtype=float).reshape(-1)
    if flat.size == 0:
        raise ValueError("Cannot summarize an empty distribution")

    result = {
        "p10": float(np.percentile(flat, 10)),
        "p50": float(np.percentile(flat, 50)),
        "p90": float(np.percentile(flat, 90)),
        "mean": float(flat.mean()),
        "unit": unit,
        "simulation_id": simulation_id,
    }
    if quartiles:
        result["p25"] = float(np.percentile(flat, 25))
        result["p75"] = float(np.percentile(flat, 75))
    if censored_above is not None:
        # A vehicle whose P90 lies beyond the horizon must not report a precise-looking
        # number (docs/forecast-definitions.md §3.4).
        result["censored_above"] = float(censored_above)
        result["censored_fraction"] = float(censored_fraction or 0.0)
    return result


def probability(mask: np.ndarray) -> float:
    """Direct draw count. Never a normal approximation — these distributions are skewed
    and bounded, and an approximation would misstate exactly the tail being asked about."""
    flat = np.asarray(mask).reshape(-1)
    if flat.size == 0:
        return 0.0
    return float(np.count_nonzero(flat) / flat.size)


def require_same_simulation(*sets: Mapping) -> str:
    """Assert that percentile sets are jointly combinable, returning their shared id."""
    ids = {s["simulation_id"] for s in sets if s is not None}
    if len(ids) > 1:
        raise SimulationMismatch(
            "Refusing to combine distributions from different simulations "
            f"({sorted(ids)}). Compute the combined quantity per draw instead (§12.5)."
        )
    if not ids:
        raise ValueError("No percentile sets supplied")
    return ids.pop()


def risk_direction(quantity: str) -> str:
    return RISK_DIRECTION.get(quantity, "NOT_DISTRIBUTIONAL")


def explanation_value(
    label: str, value: float | str | None, unit: str | None = None, quantity: str | None = None
) -> dict:
    """One entry of the narration allow-list (docs/architecture.md §3.4)."""
    entry: dict = {"label": label, "value": value}
    if unit:
        entry["unit"] = unit
    if quantity:
        entry["risk_direction"] = risk_direction(quantity)
    return entry


def collect_explanation_inputs(
    values: Iterable[dict], narratable_warning_codes: Iterable[str] = ()
) -> dict:
    """Assemble the block the explanation layer is allowed to see.

    The LLM receives this and the warning list, not the raw result tree. A currency
    figure in generated prose that does not appear here fails the response rather than
    reaching the user.
    """
    return {
        "values": list(values),
        "narratable_warning_codes": list(narratable_warning_codes),
    }
