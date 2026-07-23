"""Explainable aging-candidate selection. Phase 5.

Selection ranks and filters values the portfolio skill already produced; it must not
recalculate, and it must protect the vehicles that should not be discounted. These tests
drive it with a synthetic portfolio result so the reason-code rules are pinned exactly.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from pricing_agent.workflows.candidate_selection import Selection, select_candidates

SELECTION_SRC = (
    Path(__file__).resolve().parents[2]
    / "src" / "pricing_agent" / "workflows" / "candidate_selection.py"
)
AS_OF = date(2026, 7, 21)


def _inventory():
    return [
        {"vehicle_id": "V-1", "year": 2019, "make": "Jeep", "model": "Wrangler", "trim": "SPORT",
         "segment": "SUV", "days_in_inventory": 130, "current_list_price": 28495,
         "acquisition_date": "2026-03-13", "campaign_participation": []},
        {"vehicle_id": "V-2", "year": 2022, "make": "Toyota", "model": "RAV4", "trim": "XLE",
         "segment": "SUV", "days_in_inventory": 37, "current_list_price": 28995,
         "acquisition_date": "2026-06-14", "campaign_participation": []},
        {"vehicle_id": "V-3", "year": 2022, "make": "Toyota", "model": "RAV4", "trim": "XLE",
         "segment": "SUV", "days_in_inventory": 12, "current_list_price": 29495,
         "acquisition_date": "2026-07-15", "campaign_participation": []},
        {"vehicle_id": "V-4", "year": 2020, "make": "Toyota", "model": "Camry", "trim": "LE",
         "segment": "SEDAN", "days_in_inventory": 73, "current_list_price": 19495,
         "acquisition_date": "2026-05-09", "campaign_participation": ["CAMP-JUNE"]},
        {"vehicle_id": "V-5", "year": 2021, "make": "Honda", "model": "Accord", "trim": "EX",
         "segment": "SEDAN", "days_in_inventory": 44, "current_list_price": 26495,
         "acquisition_date": "2026-06-07", "campaign_participation": []},
    ]


def _portfolio(risk=None, actions=None, analyzed=None):
    inv = _inventory()
    analyzed = analyzed if analyzed is not None else [v["vehicle_id"] for v in inv]
    return {
        "top_risk_vehicles": risk or [],
        "recommended_actions": actions or [],
        "audit": {"vehicle_identifiers": analyzed},
    }


def _risk(vid, prob_age=0.0, dep=0.0, score=50.0):
    return {"vehicle_id": vid, "prob_age_over_90": prob_age,
            "p90_depreciation_loss": dep, "risk_score": score}


def _action(vid, action):
    return {"vehicle_id": vid, "action": action}


INBOUND_SUV = [{"segment": "SUV", "committed_slot": True}]


# --- selection uses the portfolio result ----------------------------------------------


def test_selection_consumes_the_portfolio_result():
    portfolio = _portfolio(
        risk=[_risk("V-1", prob_age=0.8, score=90)],
        actions=[_action("V-1", "WHOLESALE_DISPOSITION")],
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v1 = next(c for c in sel.candidates if c.vehicle_id == "V-1")
    assert "CURRENTLY_OVER_120_DAYS" in v1.reason_codes
    assert "P50_PROJECTED_OVER_90_DAYS" in v1.reason_codes
    assert "CAPACITY_RELEASE_PRIORITY" in v1.reason_codes


def test_over_90_and_over_120_bands():
    inv = _inventory()
    portfolio = _portfolio(risk=[_risk("V-1", 0.8), _risk("V-4", 0.6)],
                           actions=[_action("V-1", "VELOCITY_REPRICE")])
    sel = select_candidates(portfolio, inv, [], as_of=AS_OF)
    v1 = next(c for c in sel.candidates if c.vehicle_id == "V-1")
    assert "CURRENTLY_OVER_120_DAYS" in v1.reason_codes  # 130 days


def test_p50_vs_p90_projection_bands():
    portfolio = _portfolio(
        risk=[_risk("V-5", prob_age=0.6), _risk("V-1", prob_age=0.2)],
        actions=[_action("V-5", "BALANCED_REPRICE"), _action("V-1", "BALANCED_REPRICE")],
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v5 = next(c for c in sel.candidates if c.vehicle_id == "V-5")
    v1 = next(c for c in sel.candidates if c.vehicle_id == "V-1")
    assert "P50_PROJECTED_OVER_90_DAYS" in v5.reason_codes    # prob 0.6 ≥ 0.5
    assert "P90_PROJECTED_OVER_90_DAYS" in v1.reason_codes    # 0.1 ≤ 0.2 < 0.5


def test_duplicate_inventory_flagged():
    # V-2 and V-3 are both 2022 Toyota RAV4 XLE; V-3 is recently acquired and excluded.
    portfolio = _portfolio(
        risk=[_risk("V-2", prob_age=0.3)], actions=[_action("V-2", "BALANCED_REPRICE")],
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v2 = next(c for c in sel.candidates if c.vehicle_id == "V-2")
    assert "DUPLICATE_INVENTORY" in v2.reason_codes


def test_inbound_replacement_pressure():
    portfolio = _portfolio(
        risk=[_risk("V-1", prob_age=0.8)], actions=[_action("V-1", "VELOCITY_REPRICE")],
    )
    sel = select_candidates(portfolio, _inventory(), INBOUND_SUV, as_of=AS_OF)
    v1 = next(c for c in sel.candidates if c.vehicle_id == "V-1")
    assert "INBOUND_REPLACEMENT_PRESSURE" in v1.reason_codes  # SUV inbound, V-1 is SUV


# --- exclusions / protection ----------------------------------------------------------


def test_campaign_vehicle_is_excluded():
    portfolio = _portfolio(risk=[_risk("V-4", prob_age=0.9)],
                           actions=[_action("V-4", "VELOCITY_REPRICE")])
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v4 = next(e for e in sel.exclusions if e.vehicle_id == "V-4")
    assert "ALREADY_ASSIGNED_TO_CAMPAIGN" in v4.reason_codes
    assert "V-4" not in sel.candidate_ids


def test_recently_acquired_is_protected():
    portfolio = _portfolio(risk=[_risk("V-3", prob_age=0.9)],
                           actions=[_action("V-3", "VELOCITY_REPRICE")])
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v3 = next(e for e in sel.exclusions if e.vehicle_id == "V-3")
    assert "RECENTLY_ACQUIRED" in v3.reason_codes


def test_high_demand_vehicle_is_protected_from_promotion():
    portfolio = _portfolio(
        risk=[_risk("V-5", prob_age=0.9)], actions=[_action("V-5", "INCREASE_PRICE")],
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v5 = next(e for e in sel.exclusions if e.vehicle_id == "V-5")
    assert "HIGH_DEMAND_PROTECT_GROSS" in v5.reason_codes
    assert "V-5" not in sel.candidate_ids


def test_insufficient_data_when_not_analyzed():
    portfolio = _portfolio(
        risk=[_risk("V-1", 0.9)], actions=[_action("V-1", "VELOCITY_REPRICE")],
        analyzed=["V-2", "V-3", "V-4", "V-5"],  # V-1 not analyzed
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    v1 = next(e for e in sel.exclusions if e.vehicle_id == "V-1")
    assert "INSUFFICIENT_DATA" in v1.reason_codes


def test_only_supporting_signals_is_not_a_candidate():
    # A young vehicle with only a mild P90 tail and headroom is expected to sell.
    portfolio = _portfolio(
        risk=[_risk("V-5", prob_age=0.2)], actions=[_action("V-5", "EVENT_PROMOTION")],
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    assert "V-5" not in sel.candidate_ids
    v5 = next(e for e in sel.exclusions if e.vehicle_id == "V-5")
    assert "EXPECTED_TO_SELL_BEFORE_EVENT" in v5.reason_codes


def test_candidates_are_risk_ranked():
    portfolio = _portfolio(
        risk=[_risk("V-1", 0.8, score=40), _risk("V-5", 0.6, score=95)],
        actions=[_action("V-1", "BALANCED_REPRICE"), _action("V-5", "BALANCED_REPRICE")],
    )
    sel = select_candidates(portfolio, _inventory(), [], as_of=AS_OF)
    scores = [c.risk_score for c in sel.candidates]
    assert scores == sorted(scores, reverse=True)


# --- no calculation -------------------------------------------------------------------


def test_selection_does_not_recalculate():
    """The module ranks and filters; it must not import the calculation layer or reach for
    numpy/percentile/simulate."""
    tree = ast.parse(SELECTION_SRC.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        assert not name.startswith(
            ("pricing_agent.domain", "pricing_agent.simulation", "numpy", "pandas")
        ), f"selection imports {name}"
    # Target actual calculation calls, not the docstring that describes the rule.
    source = SELECTION_SRC.read_text(encoding="utf-8")
    for banned in ("np.percentile", ".percentile(", "simulate(", "np.mean", "np.median"):
        assert banned not in source, f"selection references {banned}"
