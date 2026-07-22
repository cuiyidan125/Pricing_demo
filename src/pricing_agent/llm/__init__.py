"""Explanation layer. Consumes finished results only.

Never imported by `domain/` or `simulation/` — tests/unit/test_architecture.py fails the
build if it ever is.
"""

from pricing_agent.llm.client import LlmResult, complete, credentials_present
from pricing_agent.llm.explain import Narrative, explain

__all__ = ["LlmResult", "Narrative", "complete", "credentials_present", "explain"]
