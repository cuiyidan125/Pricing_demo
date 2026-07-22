"""The dealer workflow a view is being rendered under.

Moved here from `pricing_agent.views.context` in Phase 3. A workflow is a dealer business
job, not a screen, so the type belongs with the workflow layer rather than the
presentation layer that happens to consume it.

This module imports nothing from `views` — deliberately. `workflows.registry` imports
views to bind render callables, so a dependency in the other direction would close a
cycle. `workflows/__init__.py` therefore exports only this module, and the registry is
imported explicitly by whoever needs it.
"""

from __future__ import annotations

from enum import Enum


class WorkflowContext(str, Enum):
    """Which dealer job a view is serving.

    A `str` enum so it serialises cleanly into a URL, a cache key, or an audit record
    without a conversion step at each boundary.
    """

    ACQUIRE_INVENTORY = "ACQUIRE_INVENTORY"
    PRICE_INVENTORY = "PRICE_INVENTORY"
    MERCHANDISE_INVENTORY = "MERCHANDISE_INVENTORY"
    IMPROVE_AGING_INVENTORY = "IMPROVE_AGING_INVENTORY"

    @property
    def label(self) -> str:
        """Human-readable name, e.g. 'Acquire Inventory'."""
        return self.value.replace("_", " ").title()
