"""Warning emission. Implements D7.

Severity is resolved from config/assumptions/warnings.yaml, never hard-coded here, so a
severity change is a policy change rather than a code change.

`BLOCKING` is reserved exclusively for the §19.1 publication bars. "Blocking" therefore
always means publication is refused, never merely "serious" — anything a user can proceed
past with documentation is `CRITICAL` at most.

Every warning carries `observed` and `threshold`, so the user sees the margin by which a
rule was missed rather than only that it was.
"""

from __future__ import annotations

from typing import Any

from pricing_agent.config import Config

_GROUPS = ("single_vehicle", "portfolio", "promotion")


class UnknownWarningCode(KeyError):
    pass


def _rule(config: Config, code: str) -> dict:
    for group in _GROUPS:
        rules = config.warnings.get(group, {})
        if code in rules:
            return rules[code]
    raise UnknownWarningCode(
        f"{code} is not mapped in config/assumptions/warnings.yaml. Every emitted code "
        "must have a declared severity (D7)."
    )


def emit(
    code: str,
    scope: str,
    message: str,
    observed: float | None,
    threshold: float | None,
    unit: str,
    config: Config,
    *,
    subject_id: str | None = None,
    remediation: str = "",
    escalate: bool = False,
) -> dict:
    """Build one `warning.schema.json`-valid object.

    `escalate` applies a rule's declared escalation — used by
    EXTERNAL_PROVIDER_VARIANCE above 10% divergence (D5) and by INSUFFICIENT_VEHICLE_DATA
    when the missing field is cost basis.
    """
    rule = _rule(config, code)
    severity = rule.get("severity", "MEDIUM")

    if escalate:
        if rule.get("escalate_to_blocking_when"):
            severity = "BLOCKING"
        elif rule.get("escalate_to"):
            severity = str(rule["escalate_to"])

    blocks = bool(rule.get("blocks_publication", False)) or severity == "BLOCKING"

    return {
        "code": code,
        "severity": severity,
        "scope": scope,
        "subject_id": subject_id,
        "message": message,
        "observed": observed,
        "threshold": threshold,
        "unit": unit,
        "remediation": remediation,
        "blocks_publication": blocks,
        "requires_approval": bool(rule.get("requires_approval", False)),
    }


SEVERITY_ORDER = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKING"]


def sort_by_severity(warnings: list[dict]) -> list[dict]:
    return sorted(
        warnings, key=lambda w: SEVERITY_ORDER.index(w["severity"]), reverse=True
    )


def blocking_codes(warnings: list[dict]) -> list[str]:
    return [w["code"] for w in warnings if w.get("blocks_publication")]


def at_or_above(warnings: list[dict], severity: str) -> list[dict]:
    floor = SEVERITY_ORDER.index(severity)
    return [w for w in warnings if SEVERITY_ORDER.index(w["severity"]) >= floor]


# --- single-vehicle rules -------------------------------------------------------------


def evaluate_single_vehicle(
    *,
    vehicle_id: str,
    current_list_price: float | None,
    recommended_price: float,
    market_value: float,
    deal_thresholds: dict,
    break_even: dict,
    sales: dict,
    depreciation: dict,
    net_value_p10: float,
    probability_negative_net_value: float,
    valuation_warnings: list[str],
    requested_discount: float | None,
    max_safe_discount: float,
    config: Config,
) -> list[dict]:
    """Apply §20.2. Runs over assembled numbers and only ever adds."""
    out: list[dict] = []
    poor = float(deal_thresholds.get("poor_deal", 1.03))
    accounting = break_even["current_accounting_break_even"]

    def add(**kwargs: Any) -> None:
        out.append(emit(scope="VEHICLE", subject_id=vehicle_id, config=config, **kwargs))

    # --- market position ---
    if current_list_price and market_value:
        ratio = current_list_price / market_value
        if ratio > poor:
            add(
                code="CURRENT_PRICE_POOR_DEAL",
                message=(
                    f"Current price is {ratio:.1%} of market, above the "
                    f"{poor:.0%} poor-deal threshold."
                ),
                observed=round(ratio, 4),
                threshold=poor,
                unit="RATIO",
                remediation="Reprice toward market to restore search visibility.",
            )

    if market_value and recommended_price / market_value > poor:
        add(
            code="RECOMMENDED_PRICE_POOR_DEAL",
            message="The recommended price still sits in poor-deal territory.",
            observed=round(recommended_price / market_value, 4),
            threshold=poor,
            unit="RATIO",
            remediation="A floor is holding the price above market; see break-even.",
        )

    # --- aging ---
    age = sales["projected_total_inventory_age"]
    exceed = sales["projected_age_exceedance"]
    for pct, key in (("p50", "P50"), ("p90", "P90")):
        for limit in (90, 120):
            if age[pct] > limit:
                add(
                    code=f"{key}_PROJECTED_INVENTORY_AGE_OVER_{limit}_DAYS",
                    message=(
                        f"{key} projected total age is {age[pct]:.0f} days "
                        f"(P(over {limit}d) = {exceed[f'over_{limit}_days']:.0%})."
                    ),
                    observed=round(age[pct], 1),
                    threshold=float(limit),
                    unit="DAYS",
                    remediation="Consider a velocity strategy or event promotion.",
                )

    # --- depreciation ---
    loss_p90 = depreciation["depreciation_loss"]["p90"]
    dep_threshold = float(config.portfolio["thresholds"]["high_projected_depreciation_pct"])
    if market_value and loss_p90 / market_value > dep_threshold:
        add(
            code="HIGH_DEPRECIATION_RISK",
            message=(
                f"P90 depreciation loss of ${loss_p90:,.0f} is "
                f"{loss_p90 / market_value:.1%} of market value."
            ),
            observed=round(loss_p90, 2),
            threshold=round(market_value * dep_threshold, 2),
            unit="USD",
            remediation="Faster turn reduces exposure; check the discount ladder.",
        )

    # --- break-even (§19.1 bars) ---
    price = sales["transaction_price"]
    if price["p50"] < accounting:
        add(
            code="P50_TRANSACTION_PRICE_BELOW_BREAK_EVEN",
            message=(
                f"Median modeled transaction price of ${price['p50']:,.0f} is below "
                f"break-even of ${accounting:,.0f}."
            ),
            observed=round(price["p50"], 2),
            threshold=round(accounting, 2),
            unit="USD",
            remediation="Raise price, reduce discount, or request loss-minimization approval.",
        )
    elif price["p10"] < accounting:
        add(
            code="P10_TRANSACTION_PRICE_BELOW_BREAK_EVEN",
            message=(
                f"Downside transaction price of ${price['p10']:,.0f} falls below "
                f"break-even of ${accounting:,.0f}."
            ),
            observed=round(price["p10"], 2),
            threshold=round(accounting, 2),
            unit="USD",
            remediation="Acceptable if the median clears; watch the negotiation floor.",
        )

    if current_list_price is not None and current_list_price < accounting:
        add(
            code="PRICE_BELOW_CURRENT_BREAK_EVEN",
            message="The advertised price is already below accounting break-even.",
            observed=round(current_list_price, 2),
            threshold=round(accounting, 2),
            unit="USD",
            remediation="Every sale at this price books a loss.",
        )

    minimum_safe_list = break_even["minimum_safe_list_price"]
    if recommended_price < minimum_safe_list:
        add(
            code="MINIMUM_SAFE_LIST_PRICE_VIOLATION",
            message=(
                f"Recommended price of ${recommended_price:,.0f} is below the minimum "
                f"safe list price of ${minimum_safe_list:,.0f}."
            ),
            observed=round(recommended_price, 2),
            threshold=round(minimum_safe_list, 2),
            unit="USD",
            remediation="Publication is refused until the price clears the floor.",
        )

    crossover = break_even["market_value_crossover_risk"]
    if crossover["break_even_exceeds_market_value_now"]:
        add(
            code="BREAK_EVEN_EXCEEDS_MARKET_VALUE",
            message=(
                f"Break-even of ${accounting:,.0f} exceeds market value of "
                f"${market_value:,.0f}. This vehicle cannot be sold at a profit today."
            ),
            observed=round(accounting, 2),
            threshold=round(market_value, 2),
            unit="USD",
            remediation="Loss-minimization review: compare taking the loss now against holding.",
        )
    elif crossover["probability_crossover_within_horizon"] > 0.5:
        add(
            code="BREAK_EVEN_MARKET_CROSSOVER_RISK",
            message=(
                "Rising break-even is likely to overtake falling market value before sale "
                f"(P = {crossover['probability_crossover_within_horizon']:.0%})."
            ),
            observed=round(crossover["probability_crossover_within_horizon"], 4),
            threshold=0.5,
            unit="RATIO",
            remediation="Act now; the position worsens with time.",
        )

    negative_threshold = float(config.pricing["negative_value_threshold"])
    if probability_negative_net_value > negative_threshold:
        add(
            code="HIGH_PROBABILITY_OF_NEGATIVE_NET_VALUE",
            message=(
                f"{probability_negative_net_value:.0%} of modeled outcomes destroy "
                f"economic value (downside ${net_value_p10:,.0f})."
            ),
            observed=round(probability_negative_net_value, 4),
            threshold=negative_threshold,
            unit="RATIO",
            remediation="Reprice for velocity or consider wholesale disposition.",
        )

    # --- headroom ---
    if requested_discount is not None and requested_discount > max_safe_discount:
        add(
            code="DISCOUNT_EXCEEDS_SAFE_HEADROOM",
            message=(
                f"Requested discount of ${requested_discount:,.0f} exceeds the safe "
                f"maximum of ${max_safe_discount:,.0f}."
            ),
            observed=round(requested_discount, 2),
            threshold=round(max_safe_discount, 2),
            unit="USD",
            remediation="Reduce the discount or seek an emergency markdown approval.",
        )

    # --- valuation quality, raised upstream in domain/valuation.py ---
    for code in valuation_warnings:
        add(
            code=code,
            message=_VALUATION_MESSAGES.get(code, code),
            observed=None,
            threshold=None,
            unit="RATIO",
            remediation="Treat the valuation as indicative; verify against local knowledge.",
        )

    return sort_by_severity(out)


_VALUATION_MESSAGES = {
    "LOW_VALUATION_CONFIDENCE": (
        "Too few usable comparables to compute an independent internal estimate; "
        "the external reference stands alone."
    ),
    "EXTERNAL_PROVIDER_VARIANCE": (
        "The internal comparable estimate disagrees materially with the external "
        "reference price."
    ),
    "EXTERNAL_VALUATION_UNAVAILABLE": (
        "External market data was unavailable or stale; the internal comparable "
        "estimate was used instead."
    ),
}
