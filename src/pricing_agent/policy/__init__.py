"""Policy and fail-safe engine.

Runs after result assembly and may only ADD — warnings, approval requirements, and
publication bars. It never alters a computed number (docs/architecture.md §7).
"""

from pricing_agent.policy import approvals, freshness, price_floor, warnings

__all__ = ["approvals", "freshness", "price_floor", "warnings"]
