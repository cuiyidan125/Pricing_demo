"""Data freshness. §21, using the injected clock only (D8).

Stale data degrades analysis but blocks only publication. A manager exploring options
with two-hour-old inventory data is doing something reasonable; publishing a price from
it is not.
"""

from __future__ import annotations

from pricing_agent.config import Config
from pricing_agent.mcp_clients.base import ToolResponse
from pricing_agent.policy.warnings import emit


def stale_responses(responses: list[ToolResponse]) -> list[ToolResponse]:
    return [r for r in responses if r.meta is not None and r.meta.is_stale]


def stale_realtime_sources(responses: list[ToolResponse], config: Config) -> list[str]:
    """Sources whose staleness bars publication (§21)."""
    gate = config.freshness.get("publication_gate", {})
    blocking_classes = set(gate.get("block_on_stale_classes", []))
    return [
        r.tool
        for r in stale_responses(responses)
        if r.meta is not None and r.meta.freshness_class in blocking_classes
    ]


def evaluate(responses: list[ToolResponse], config: Config, scope: str = "VEHICLE",
             subject_id: str | None = None) -> list[dict]:
    """One STALE_MARKET_DATA warning per stale source."""
    out: list[dict] = []
    classes = config.freshness["classes"]

    for response in stale_responses(responses):
        assert response.meta is not None
        max_age = classes.get(response.meta.freshness_class, {}).get("max_age_hours")
        out.append(
            emit(
                code="STALE_MARKET_DATA",
                scope=scope,
                subject_id=subject_id,
                message=(
                    f"{response.tool} data is {response.meta.age_hours:.0f}h old, past the "
                    f"{response.meta.freshness_class} limit of {max_age}h."
                ),
                observed=round(response.meta.age_hours, 1),
                threshold=float(max_age) if max_age is not None else None,
                unit="DAYS",
                config=config,
                remediation="Refresh the source before publishing a price.",
            )
        )
    return out
