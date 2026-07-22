"""All financial calculation. Pure functions, no I/O, no model calls.

Imports nothing from agents, skills, mcp_clients, or llm. tests/unit/test_architecture.py
enforces the LLM half of that by walking the AST of every module here.
"""

from pricing_agent.domain.summarize import (
    PERCENTILE_CONVENTION,
    SimulationMismatch,
    collect_explanation_inputs,
    explanation_value,
    percentile_set,
    probability,
    require_same_simulation,
    risk_direction,
)
from pricing_agent.domain.vehicle import CostBasis, MissingCostBasis, Vehicle

__all__ = [
    "PERCENTILE_CONVENTION",
    "CostBasis",
    "MissingCostBasis",
    "SimulationMismatch",
    "Vehicle",
    "collect_explanation_inputs",
    "explanation_value",
    "percentile_set",
    "probability",
    "require_same_simulation",
    "risk_direction",
]
