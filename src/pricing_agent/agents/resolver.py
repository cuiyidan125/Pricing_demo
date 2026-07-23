"""Resolve a parsed vehicle against real dealer inventory. Phase 4, no model.

A name is not a match. `parse_vehicle` reads what the dealer said; this decides which
inventory record — if any — that describes. The rule the product cannot break is that it
does **not** invent a vehicle: an unresolved name returns NO_MATCH with the honest reason
that the MVP analyses inventory the dealer already holds, and an ambiguous name returns the
candidates for the dealer to choose between rather than picking one silently.

Matching priority (most specific first):

1. exact `vehicle_id`
2. exact VIN
3. year + make + model + trim, unique
4. year + make + model, unique
5. make + model, unique  (a unique match is not a guess even without the year)

Anything that leaves more than one candidate is AMBIGUOUS. Too little to resolve — no id,
no VIN, and not both a make and a model — is INSUFFICIENT, which the assistant turns into a
request for more detail rather than an error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pricing_agent.agents.router import ParsedVehicle


class MatchStatus(str, Enum):
    EXACT = "EXACT"
    AMBIGUOUS = "AMBIGUOUS"
    NONE = "NONE"
    INSUFFICIENT = "INSUFFICIENT"


# The subset of an inventory record the assistant shows when disambiguating. No computed
# field — these are the fixture's own values, copied through.
CANDIDATE_FIELDS = (
    "vehicle_id", "vin", "year", "make", "model", "trim", "mileage",
    "current_list_price", "days_in_inventory",
)


@dataclass(frozen=True)
class MatchResult:
    status: MatchStatus
    vehicle_id: str | None = None
    candidates: tuple[dict, ...] = ()
    missing_fields: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


def _card(vehicle: dict) -> dict:
    return {name: vehicle.get(name) for name in CANDIDATE_FIELDS}


def _norm(value: object) -> str:
    return str(value).strip().casefold() if value is not None else ""


def _model_key(value: object) -> str:
    """Compare models ignoring the punctuation that spelling varies on (F-150 vs F150)."""
    return _norm(value).replace("-", "").replace(" ", "")


def resolve_vehicle(parsed: ParsedVehicle, inventory: list[dict]) -> MatchResult:
    """Resolve `parsed` against `inventory` by the documented priority."""

    # 1. exact vehicle_id
    if parsed.vehicle_id:
        for vehicle in inventory:
            if _norm(vehicle.get("vehicle_id")) == _norm(parsed.vehicle_id):
                return MatchResult(
                    MatchStatus.EXACT, vehicle["vehicle_id"], (_card(vehicle),),
                    reason_codes=("MATCHED_VEHICLE_ID",),
                )
        return MatchResult(
            MatchStatus.NONE, reason_codes=("NO_SUCH_VEHICLE_ID",)
        )

    # 2. exact VIN
    if parsed.vin:
        for vehicle in inventory:
            if _norm(vehicle.get("vin")) == _norm(parsed.vin):
                return MatchResult(
                    MatchStatus.EXACT, vehicle["vehicle_id"], (_card(vehicle),),
                    reason_codes=("MATCHED_VIN",),
                )
        return MatchResult(MatchStatus.NONE, reason_codes=("NO_SUCH_VIN",))

    # 3–5. structured match. Requires at least a make and a model.
    if not (parsed.make and parsed.model):
        missing = tuple(f for f in ("make", "model") if getattr(parsed, f) is None)
        return MatchResult(
            MatchStatus.INSUFFICIENT,
            missing_fields=missing or ("vehicle_id",),
            reason_codes=("INSUFFICIENT_IDENTITY",),
        )

    make_model = [
        v for v in inventory
        if _norm(v.get("make")) == _norm(parsed.make)
        and _model_key(v.get("model")) == _model_key(parsed.model)
    ]

    if not make_model:
        return MatchResult(MatchStatus.NONE, reason_codes=("NO_MAKE_MODEL_MATCH",))

    # Narrow by year, then trim, but never past the point of emptiness — a stated trim that
    # matches nothing should surface the make/model candidates, not a dead end.
    candidates = make_model
    reason: list[str] = ["MATCHED_MAKE_MODEL"]

    if parsed.year is not None:
        by_year = [v for v in candidates if v.get("year") == parsed.year]
        if by_year:
            candidates = by_year
            reason.append("NARROWED_BY_YEAR")
        else:
            return MatchResult(
                MatchStatus.NONE, reason_codes=("YEAR_NOT_IN_INVENTORY",)
            )

    if parsed.trim is not None:
        by_trim = [v for v in candidates if _norm(v.get("trim")) == _norm(parsed.trim)]
        if by_trim:
            candidates = by_trim
            reason.append("NARROWED_BY_TRIM")
        # A non-matching trim is left as-is: show what the make/model/year did match.

    if len(candidates) == 1:
        return MatchResult(
            MatchStatus.EXACT, candidates[0]["vehicle_id"], (_card(candidates[0]),),
            reason_codes=tuple(reason),
        )

    return MatchResult(
        MatchStatus.AMBIGUOUS,
        candidates=tuple(_card(v) for v in candidates),
        reason_codes=tuple(reason + ["MULTIPLE_MATCHES"]),
    )
