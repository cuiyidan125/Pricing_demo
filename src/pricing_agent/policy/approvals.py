"""Approval triggers. §22.2, docs/approval-policy.md.

Two independent gates: user confirmation and manager approval. Neither substitutes for
the other, and a BLOCKING warning is cleared by neither — only by changing the price or
by a documented §19.2 loss-minimization exception.

The thresholds §22.2 leaves qualitative ("unusually aggressive", "material gross
reduction") come from dealer policy, so changing one is a policy change rather than a
code change.
"""

from __future__ import annotations

from pricing_agent.config import Config


def evaluate_single_vehicle(
    *,
    current_list_price: float | None,
    proposed_price: float,
    accounting_break_even: float,
    projected_break_even_p50: float,
    transaction_price_p50: float,
    probability_negative_net_value: float,
    uses_emergency_reserve: bool,
    policy: dict | None,
    config: Config,
) -> list[dict]:
    """Which approvals §22.2 requires for this price."""
    policy = policy or {}
    thresholds = policy.get("approval_thresholds", config.pricing["approval_thresholds"])
    out: list[dict] = []

    def add(kind: str, trigger: str, observed: float | None, threshold: float | None) -> None:
        out.append(
            {
                "approval_type": kind,
                "trigger": trigger,
                "observed": None if observed is None else round(float(observed), 4),
                "threshold": None if threshold is None else round(float(threshold), 4),
            }
        )

    if transaction_price_p50 < accounting_break_even:
        add(
            "LOSS_MINIMIZATION",
            "Median modeled transaction price is below accounting break-even",
            transaction_price_p50,
            accounting_break_even,
        )

    if transaction_price_p50 < projected_break_even_p50:
        add(
            "BELOW_PROJECTED_BREAK_EVEN",
            "Median transaction price does not recover projected costs to sale",
            transaction_price_p50,
            projected_break_even_p50,
        )

    negative_threshold = float(config.pricing["negative_value_threshold"])
    if probability_negative_net_value > negative_threshold:
        add(
            "NEGATIVE_VALUE_RISK",
            "High probability of negative net economic value",
            probability_negative_net_value,
            negative_threshold,
        )

    if uses_emergency_reserve:
        add("EMERGENCY_MARKDOWN", "Discount reaches the emergency markdown reserve", None, None)

    if current_list_price:
        change = abs(proposed_price - current_list_price) / current_list_price
        limit = float(thresholds["aggressive_adjustment_pct"])
        if change > limit:
            add(
                "AGGRESSIVE_ADJUSTMENT",
                "Price change exceeds the dealer's aggressive-adjustment threshold",
                change,
                limit,
            )

    return out


def loss_minimization_payload(
    *,
    immediate_loss: float,
    expected_future_loss: float,
    expected_cash_holding_cost: float,
    expected_depreciation: float,
    capacity_opportunity_cost: float,
) -> dict:
    """The §19.2 quantified impact.

    All five figures are required so the comparison is explicit: an immediate loss is
    justified only when it is smaller than the modeled cost of continuing to hold. The
    system computes both sides and presents them; it does not decide.
    """
    return {
        "immediate_loss": round(immediate_loss, 2),
        "expected_future_loss": round(expected_future_loss, 2),
        "expected_holding_cost": round(expected_cash_holding_cost, 2),
        "expected_depreciation": round(expected_depreciation, 2),
        "capacity_opportunity_cost": round(capacity_opportunity_cost, 2),
    }
