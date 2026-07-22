"""Intent routing, entity extraction, and the narration guard.

The agent layer may compare, sort, filter and select. It may not compute a price, a
duration, a cost, or a probability — those come from `domain/` and `simulation/`.
"""

from pricing_agent.agents import narration_guard
from pricing_agent.agents.extract import INTENTS, extract, intent_of

__all__ = ["INTENTS", "extract", "intent_of", "narration_guard"]
