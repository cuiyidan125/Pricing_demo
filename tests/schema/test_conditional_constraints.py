"""Verify the schemas' conditional subschemas actually fire.

A malformed `if`/`then` compiles cleanly and then silently never applies, so
`check_schema` passing proves nothing about these three constraints. Each test
below asserts both directions: the violating instance is rejected AND the
conforming instance is accepted. Only the pair is meaningful -- a rule that
rejects everything would pass a rejection-only test.

Constraints under test:
  1. warning.schema.json                 severity BLOCKING => blocks_publication true (D7)
  2. promotion-candidate.schema.json     eligibility implies the right required fields
  3. inventory-sales-forecast.schema.json  RUN_OFF => a non-empty lower_bound_note
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "schemas"
BASE_URI = "https://pricing-demo.local/schemas/"


@pytest.fixture(scope="module")
def registry() -> Registry:
    resources = []
    for path in SCHEMA_DIR.glob("*.schema.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((f"{BASE_URI}{path.name}", Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def validator_for(name: str, registry: Registry) -> Draft202012Validator:
    doc = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return Draft202012Validator(doc, registry=registry)


def is_valid(name: str, registry: Registry, instance: dict) -> bool:
    return validator_for(name, registry).is_valid(instance)


# --- 1. BLOCKING implies blocks_publication -------------------------------------------

def _warning(**overrides) -> dict:
    base = {
        "code": "P50_TRANSACTION_PRICE_BELOW_BREAK_EVEN",
        "severity": "BLOCKING",
        "scope": "VEHICLE",
        "subject_id": "V-10005",
        "message": "Median modeled transaction price is below break-even.",
        "observed": 24180,
        "threshold": 25340,
        "unit": "USD",
        "blocks_publication": True,
    }
    base.update(overrides)
    return base


def test_blocking_requires_blocks_publication(registry):
    """D7: 'BLOCKING' must always mean publication is refused, never merely 'serious'."""
    assert not is_valid("warning.schema.json", registry, _warning(blocks_publication=False))


def test_blocking_with_blocks_publication_is_accepted(registry):
    assert is_valid("warning.schema.json", registry, _warning())


def test_non_blocking_may_set_blocks_publication_false(registry):
    """Only BLOCKING is constrained; other severities are free to not block."""
    assert is_valid(
        "warning.schema.json",
        registry,
        _warning(code="CURRENT_PRICE_POOR_DEAL", severity="MEDIUM", blocks_publication=False),
    )


def test_unknown_warning_code_is_rejected(registry):
    assert not is_valid("warning.schema.json", registry, _warning(code="MADE_UP_CODE"))


# --- 2. Candidate eligibility implies required fields ---------------------------------

def test_ineligible_candidate_must_give_a_reason(registry):
    """A plan is not reviewable if the reader cannot see what was left out."""
    assert not is_valid(
        "promotion-candidate.schema.json",
        registry,
        {"vehicle_id": "V-10005", "eligible": False},
    )


def test_ineligible_candidate_with_null_reason_is_rejected(registry):
    """exclusion_reason permits null in the enum; the conditional must still demand a string."""
    assert not is_valid(
        "promotion-candidate.schema.json",
        registry,
        {"vehicle_id": "V-10005", "eligible": False, "exclusion_reason": None},
    )


def test_ineligible_candidate_with_reason_is_accepted(registry):
    assert is_valid(
        "promotion-candidate.schema.json",
        registry,
        {"vehicle_id": "V-10005", "eligible": False, "exclusion_reason": "NO_SAFE_HEADROOM"},
    )


def test_eligible_candidate_must_be_scored_and_priced(registry):
    assert not is_valid(
        "promotion-candidate.schema.json",
        registry,
        {"vehicle_id": "V-10001", "eligible": True},
    )


def test_eligible_candidate_with_score_and_pricing_is_accepted(registry):
    assert is_valid(
        "promotion-candidate.schema.json",
        registry,
        {
            "vehicle_id": "V-10001",
            "eligible": True,
            "score": 72.4,
            "pricing": {
                "current_list_price": 28995,
                "minimum_safe_list_price": 26410,
                "max_safe_discount": 2585,
            },
        },
    )


# --- 3. RUN_OFF requires the lower-bound note -----------------------------------------

SIM = {
    "simulation_id": "sim_test_0001",
    "seed": 20260721,
    "draw_count": 2000,
    "model_label": "CONFIGURABLE_PROTOTYPE_SIMULATION",
    "model_version": "prototype-sim-0.1.0",
    "assumption_version": "assumptions-2026-07-21",
}


def _pset(unit: str = "USD") -> dict:
    return {
        "p10": 1.0, "p50": 2.0, "p90": 3.0, "mean": 2.0,
        "unit": unit, "simulation_id": "sim_test_0001",
    }


def _forecast(**basis_overrides) -> dict:
    basis = {
        "mode": "RUN_OFF",
        "includes_confirmed_inbound": True,
        "includes_expected_acquisitions": False,
    }
    basis.update(basis_overrides)
    return {
        "horizon_days": 90,
        "simulation": SIM,
        "unit_sales": _pset("UNITS"),
        "sales_revenue": _pset(),
        "front_end_gross": _pset(),
        "net_economic_value": _pset(),
        "ending_inventory": _pset("UNITS"),
        "ending_utilization": _pset("RATIO"),
        "cash_holding_cost": _pset(),
        "depreciation_loss": _pset(),
        "risk_probabilities": {"utilization_above_100_percent": 0.04},
        "forecast_basis": basis,
    }


def test_run_off_without_lower_bound_note_is_rejected(registry):
    """A RUN_OFF forecast understates ending inventory and revenue. Saying so is mandatory."""
    assert not is_valid("inventory-sales-forecast.schema.json", registry, _forecast())


def test_run_off_with_empty_lower_bound_note_is_rejected(registry):
    """minLength 1 -- an empty string must not satisfy the requirement."""
    assert not is_valid(
        "inventory-sales-forecast.schema.json", registry, _forecast(lower_bound_note="")
    )


def test_run_off_with_lower_bound_note_is_accepted(registry):
    assert is_valid(
        "inventory-sales-forecast.schema.json",
        registry,
        _forecast(lower_bound_note="Lower bound: assumes no replacement acquisitions."),
    )


def test_full_mode_does_not_require_the_note(registry):
    assert is_valid(
        "inventory-sales-forecast.schema.json",
        registry,
        _forecast(mode="FULL", includes_expected_acquisitions=True),
    )


# --- 4. The request schemas offer no field for an invented number ---------------------

def test_single_vehicle_request_rejects_a_computed_field(registry):
    """Structural half of section 4.1: additionalProperties false means there is no
    property an LLM could populate with a price it invented."""
    request = {
        "request_id": "req_1",
        "dealer_id": "DEALER-1001",
        "user_id": "u_1",
        "as_of": "2026-07-29T14:00:00Z",
        "vehicle": {"year": 2022, "make": "Toyota", "model": "RAV4"},
        "extraction_provenance": [{"field": "year", "source": "USER_STATED"}],
        "recommended_price": 28995,
    }
    assert not is_valid("single-vehicle-request.schema.json", registry, request)

    del request["recommended_price"]
    assert is_valid("single-vehicle-request.schema.json", registry, request)


def test_percentile_set_rejects_unknown_keys(registry):
    """percentileSet is additionalProperties false, so a stray tail cannot be smuggled in."""
    bad = _forecast(lower_bound_note="note")
    bad["unit_sales"]["p95"] = 4.0
    assert not is_valid("inventory-sales-forecast.schema.json", registry, bad)


def test_percentile_set_requires_simulation_id(registry):
    """D2: without simulation_id there is no way to police joint combination (section 12.5)."""
    bad = _forecast(lower_bound_note="note")
    del bad["sales_revenue"]["simulation_id"]
    assert not is_valid("inventory-sales-forecast.schema.json", registry, bad)
