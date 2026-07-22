"""Vehicle identity and cost-basis assembly.

Pure. Takes MCP payloads as plain dicts and returns a normalized object; performs no I/O
and never fetches anything for itself (docs/architecture.md §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class MissingCostBasis(ValueError):
    """The one hard stop in the system.

    Without cost basis there is no floor, and a recommendation without a floor is exactly
    the failure §4.5 exists to prevent. Never substitute a default — a zero acquisition
    cost produces a floor of zero.
    """


@dataclass(frozen=True)
class CostBasis:
    acquisition_cost: float
    auction_fee: float
    transportation_cost: float
    reconditioning_cost: float
    accrued_cash_holding_cost: float
    financing_amount: float
    direct_selling_costs: float

    @property
    def capitalized_cost(self) -> float:
        """§11.4 cost basis: the dealer's invested cost, excluding holding and selling."""
        return (
            self.acquisition_cost
            + self.auction_fee
            + self.transportation_cost
            + self.reconditioning_cost
        )

    @classmethod
    def from_payload(cls, payload: dict | None, vehicle_id: str) -> "CostBasis":
        if not payload:
            raise MissingCostBasis(
                f"{vehicle_id}: no cost basis available; cannot derive a price floor"
            )
        required = ("acquisition_cost", "reconditioning_cost")
        for field_name in required:
            if payload.get(field_name) is None:
                raise MissingCostBasis(f"{vehicle_id}: {field_name} is missing")
        return cls(
            acquisition_cost=float(payload["acquisition_cost"]),
            auction_fee=float(payload.get("auction_fee") or 0.0),
            transportation_cost=float(payload.get("transportation_cost") or 0.0),
            reconditioning_cost=float(payload["reconditioning_cost"]),
            accrued_cash_holding_cost=float(payload.get("accrued_holding_cost") or 0.0),
            financing_amount=float(payload.get("financing_amount") or 0.0),
            direct_selling_costs=float(payload.get("direct_selling_costs") or 0.0),
        )


@dataclass(frozen=True)
class Vehicle:
    vehicle_id: str
    vin: str | None
    year: int
    make: str
    model: str
    trim: str | None
    mileage: int
    segment: str
    powertrain: str
    condition: str
    current_list_price: float | None
    original_list_price: float | None
    days_in_inventory: int
    status: str
    campaign_participation: tuple[str, ...] = ()
    # Merchandising photo. Null throughout the prototype: there is no image source, and
    # the UI falls back to a generated body-style silhouette.
    image_url: str | None = None

    @property
    def description(self) -> str:
        parts = [str(self.year), self.make, self.model]
        if self.trim and self.trim != "BASE":
            parts.append(self.trim)
        return " ".join(parts)

    def age_years(self, as_of: date) -> float:
        """Model-year age. Approximate by design — trim-level build dates are not
        available from any tool in the contract."""
        return max(0.0, float(as_of.year - self.year))

    @classmethod
    def from_payload(cls, payload: dict) -> "Vehicle":
        return cls(
            vehicle_id=payload["vehicle_id"],
            vin=payload.get("vin"),
            year=int(payload["year"]),
            make=payload["make"],
            model=payload["model"],
            trim=payload.get("trim"),
            mileage=int(payload["mileage"]),
            segment=payload.get("segment", "UNKNOWN"),
            powertrain=payload.get("powertrain", "UNKNOWN"),
            condition=payload.get("condition", "UNKNOWN"),
            current_list_price=(
                float(payload["current_list_price"])
                if payload.get("current_list_price") is not None
                else None
            ),
            original_list_price=(
                float(payload["original_list_price"])
                if payload.get("original_list_price") is not None
                else None
            ),
            days_in_inventory=int(payload["days_in_inventory"]),
            status=payload.get("status", "ACTIVE"),
            campaign_participation=tuple(payload.get("campaign_participation") or ()),
            image_url=payload.get("image_url"),
        )
