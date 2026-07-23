"""Intent routing, entity extraction, and the narration guard.

The agent layer may compare, sort, filter and select. It may not compute a price, a
duration, a cost, or a probability — those come from `domain/` and `simulation/`.
"""

from pricing_agent.agents import narration_guard
from pricing_agent.agents.assistant import (
    AssistantResponse,
    AssistantState,
    run_assistant,
)
from pricing_agent.agents.extract import INTENTS, extract, intent_of
from pricing_agent.agents.resolver import MatchResult, MatchStatus, resolve_vehicle
from pricing_agent.agents.router import ParsedVehicle, RouteResult, parse_vehicle, route

__all__ = [
    "INTENTS",
    "AssistantResponse",
    "AssistantState",
    "MatchResult",
    "MatchStatus",
    "ParsedVehicle",
    "RouteResult",
    "extract",
    "intent_of",
    "narration_guard",
    "parse_vehicle",
    "resolve_vehicle",
    "route",
    "run_assistant",
]
