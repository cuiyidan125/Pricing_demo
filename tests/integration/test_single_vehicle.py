"""SV-01 .. SV-15 from tests/scenarios/single-vehicle.json, executed.

The scenario file is the source of truth: a scenario and its test cannot drift apart,
because the test reads the scenario's own `expect` block. Prose assertions in the JSON
that are not machine-checkable are covered by the named tests further down.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pricing_agent.mcp_clients import FixtureStore, MockTransport, Mutation
from pricing_agent.skills.single_vehicle import analyze
from tests.conftest import DEFAULT_AS_OF

SUITE = "single-vehicle"

# Mutation paths that address the caller rather than a fixture.
_REQUEST_PATHS = {
    "promotion.requested_discount": "requested_discount",
}


def _run(scenario: dict):
    as_of = (
        datetime.fromisoformat(scenario["as_of_override"].replace("Z", "+00:00"))
        if scenario.get("as_of_override")
        else DEFAULT_AS_OF
    )

    fixture_mutations = []
    kwargs: dict = {}
    for raw in scenario.get("mutations", []):
        path = raw.get("path")
        if path in _REQUEST_PATHS:
            kwargs[_REQUEST_PATHS[path]] = raw["value"]
            continue
        if path and path.startswith("request."):
            continue  # e.g. proposed_price: exercised through the warning rules instead
        fixture_mutations.append(Mutation(**raw))

    transport = MockTransport(as_of=as_of, store=FixtureStore(mutations=fixture_mutations))
    return analyze(scenario["vehicle_id"], transport, **kwargs)


def _codes(result: dict) -> set[str]:
    return {w["code"] for w in result["warnings"]}


def _scenarios(load) -> dict:
    return load(SUITE)


def _ids(load) -> list[str]:
    return list(load(SUITE))


@pytest.fixture(scope="module")
def suite(scenarios):
    return scenarios(SUITE)


@pytest.mark.parametrize(
    "scenario_id",
    [f"SV-{n:02d}" for n in range(1, 16)],
)
def test_scenario(scenario_id, suite, validator_for):
    scenario = suite[scenario_id]

    if scenario_id == "SV-12":
        # Missing cost basis is a hard stop: no result is produced at all.
        from pricing_agent.domain.vehicle import MissingCostBasis

        with pytest.raises(MissingCostBasis):
            _run(scenario)
        return

    result = _run(scenario)
    expect = scenario["expect"]
    codes = _codes(result)

    errors = list(validator_for("single-vehicle-result.schema.json").iter_errors(result))
    assert not errors, f"{scenario_id} produced a schema-invalid result: {errors[:2]}"

    for code in expect.get("warnings_must_include", []):
        assert code in codes, f"{scenario_id}: expected {code}, got {sorted(codes)}"
    for code in expect.get("warnings_must_not_include", []):
        assert code not in codes, f"{scenario_id}: {code} should not have fired"

    if "valuation_anchor" in expect:
        assert result["valuation"]["anchor"] == expect["valuation_anchor"]
    if "internal_check_computed" in expect:
        computed = result["valuation"]["internal_estimate"] is not None
        assert computed is expect["internal_check_computed"]
    if "valuation_confidence_level" in expect:
        assert result["valuation"]["confidence"]["level"] == expect["valuation_confidence_level"]


# --- claims the scenario prose makes that deserve their own assertions -----------------


def test_sv01_strategies_are_ordered_and_share_a_simulation(suite):
    """SV-01: three scenarios from one seeded run, priced high to low."""
    result = _run(suite["SV-01"])
    prices = {s["strategy"]: s["proposed_list_price"] for s in result["pricing_scenarios"]}
    assert prices["MAXIMIZE_GROSS"] >= prices["BALANCED"] >= prices["INCREASE_VELOCITY"]

    simulations = {
        s["expected_net_economic_value"]["simulation_id"] for s in result["pricing_scenarios"]
    }
    assert len(simulations) == 1, "strategies must share one simulation, else the "
    "differences between them include sampling noise"


def test_sv03_p90_age_warning_is_milder_than_its_p50_counterpart(suite):
    """SV-03: a 10% chance of exceeding 90 days is unremarkable; an even chance is not.
    Ranking them by threshold rather than percentile would invert the alarm."""
    result = _run(suite["SV-03"])
    by_code = {w["code"]: w for w in result["warnings"]}
    order = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKING"]

    p90 = by_code.get("P90_PROJECTED_INVENTORY_AGE_OVER_90_DAYS")
    assert p90 is not None
    assert order.index(p90["severity"]) < order.index("MEDIUM")


def test_sv05_underwater_vehicle_is_refused_not_repriced_upward(suite):
    """SV-05: the system must not price above the market ceiling to manufacture a paper
    break-even, and it must refuse publication rather than silently clamping."""
    result = _run(suite["SV-05"])
    break_even = result["break_even_analysis"]

    assert break_even["market_value_crossover_risk"]["break_even_exceeds_market_value_now"]
    assert break_even["current_accounting_break_even"] > result["valuation"]["market_value"]

    recommended = next(
        s for s in result["pricing_scenarios"]
        if s["strategy"] == result["recommended_strategy"]["strategy"]
    )
    # The price is reported unchanged beside the violation, never raised to the floor.
    assert recommended["proposed_list_price"] < break_even["minimum_safe_list_price"]
    assert "MINIMUM_SAFE_LIST_PRICE_VIOLATION" in _codes(result)
    assert any(w["blocks_publication"] for w in result["warnings"])
    assert any(a["approval_type"] == "LOSS_MINIMIZATION" for a in result["approvals_required"])


def test_sv08_thin_comparables_produce_no_second_opinion(suite):
    """SV-08: a weighted median of two listings is noise presented as corroboration."""
    result = _run(suite["SV-08"])
    assert result["valuation"]["internal_estimate"] is None
    assert result["valuation"]["divergence"] is None
    assert result["valuation"]["market_value"] > 0, "a valuation is still returned"


def test_sv10_depreciation_tails_describe_opposite_scenarios(suite):
    """SV-10 and D1: loss.p90 and value.p10 are the same draws; loss.p90 and value.p90
    are not. This is the inversion the spec originally asked for."""
    result = _run(suite["SV-10"])
    depreciation = result["depreciation_forecast"]

    value = depreciation["value_at_sale"]
    loss = depreciation["depreciation_loss"]
    market = depreciation["current_market_value"]

    assert value["p10"] < value["p50"] < value["p90"]
    assert loss["p10"] < loss["p50"] < loss["p90"]
    # High loss corresponds to low value.
    assert loss["p90"] == pytest.approx(market - value["p10"], rel=0.02)
    assert loss["p10"] == pytest.approx(market - value["p90"], rel=0.02)


def test_sv13_external_unavailable_falls_back_to_internal(suite):
    result = _run(suite["SV-13"])
    assert result["valuation"]["anchor"] == "INTERNAL_FALLBACK"
    assert "EXTERNAL_VALUATION_UNAVAILABLE" in _codes(result)
    assert result["valuation"]["confidence"]["level"] in ("MEDIUM", "LOW")


def test_sv14_divergence_widens_the_range_but_never_moves_the_anchor(suite):
    """D5: disagreement lowers confidence and widens the range. It does not blend."""
    result = _run(suite["SV-14"])
    valuation = result["valuation"]

    assert "EXTERNAL_PROVIDER_VARIANCE" in _codes(result)
    assert valuation["anchor"] == "EXTERNAL"
    assert valuation["market_value"] == pytest.approx(valuation["external_estimate"])
    assert valuation["divergence"] > 0.10
    # Range widened to contain the internal estimate.
    assert valuation["market_supported_range"]["high"] >= valuation["internal_estimate"]


def test_determinism(suite):
    """Identical inputs and versions produce identical output."""
    first = _run(suite["SV-01"])
    second = _run(suite["SV-01"])
    assert (
        first["sales_outcome_distribution"]["additional_days_to_sale"]
        == second["sales_outcome_distribution"]["additional_days_to_sale"]
    )
    assert first["audit"]["simulation"]["simulation_id"] == second["audit"]["simulation"]["simulation_id"]
