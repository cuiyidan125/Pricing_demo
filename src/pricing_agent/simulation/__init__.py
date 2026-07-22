"""Seeded Monte Carlo. Imports nothing outside config and numpy (docs/architecture.md §2)."""

from pricing_agent.simulation.engine import DrawMatrix, simulate
from pricing_agent.simulation.hazard import (
    EventWindow,
    VehicleSimInput,
    build_hazard_curve,
    engagement_multiplier,
    static_multiplier,
)

__all__ = [
    "DrawMatrix",
    "EventWindow",
    "VehicleSimInput",
    "build_hazard_curve",
    "engagement_multiplier",
    "simulate",
    "static_multiplier",
]
