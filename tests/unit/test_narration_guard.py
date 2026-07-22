"""The output half of §4.1.

The import guard keeps a model out of the calculation layer; this keeps invented numbers
out of the prose. Both directions are asserted — a guard that only ever rejects would
pass a rejection-only test while making the product unusable.
"""

from __future__ import annotations

from pricing_agent.agents import narration_guard

INPUTS = {
    "values": [
        {"label": "Recommended price", "value": 29195, "unit": "USD"},
        {"label": "Market value", "value": 28400, "unit": "USD"},
        {"label": "P50 front-end gross", "value": -5134, "unit": "USD"},
        {"label": "P50 days to sale", "value": 30, "unit": "DAYS"},
        {"label": "P90 days to sale", "value": 65, "unit": "DAYS"},
        {"label": "Strategy", "value": "MAXIMIZE_GROSS"},
    ],
    "narratable_warning_codes": [],
}


def test_faithful_narrative_is_accepted():
    text = "List at $29,195 against a market value of $28,400; expect a sale in 30 days."
    assert narration_guard.check(text, INPUTS).ok


def test_invented_price_is_rejected():
    result = narration_guard.check("I'd price this around $26,400.", INPUTS)
    assert not result.ok
    assert "$26,400" in result.violations


def test_invented_duration_is_rejected():
    assert not narration_guard.check("It should move in about 45 days.", INPUTS).ok


def test_rounding_is_rejected():
    """'About $29,000' is an invented number. The tolerance is a dollar, deliberately —
    anything wider and the guard becomes decorative."""
    assert not narration_guard.check("Price it near $29,000.", INPUTS).ok


def test_negative_currency_is_checked_not_skipped():
    """The pattern once required a digit immediately after the dollar sign, so negative
    amounts were never matched and therefore never verified."""
    assert narration_guard.check("Median gross is -$5,134.", INPUTS).ok
    assert not narration_guard.check("Median gross is -$4,200.", INPUTS).ok


def test_prose_without_figures_passes():
    assert narration_guard.check("Hold this one for margin; it is priced well.", INPUTS).ok


def test_template_passes_by_construction():
    """The fallback is assembled from the allow-list, so the degraded path is always
    correct rather than merely available."""
    text = narration_guard.deterministic_summary(INPUTS, [])
    assert narration_guard.check(text, INPUTS).ok


def test_template_reports_blocking_warnings():
    warnings = [
        {"code": "MINIMUM_SAFE_LIST_PRICE_VIOLATION", "blocks_publication": True},
        {"code": "CURRENT_PRICE_POOR_DEAL", "blocks_publication": False},
    ]
    text = narration_guard.deterministic_summary(INPUTS, warnings)
    assert "MINIMUM_SAFE_LIST_PRICE_VIOLATION" in text
    assert "CURRENT_PRICE_POOR_DEAL" not in text
