"""Typed adapters over MCP tools.

Read clients and the write client are separate by design (docs/architecture.md §8).
Skills are handed read clients only; `WriteClient` is reachable solely from an explicit
UI confirmation handler.
"""

from pricing_agent.mcp_clients.base import (
    CallRecord,
    FixtureStore,
    MockTransport,
    Mutation,
    SourceMeta,
    ToolResponse,
    ToolStatus,
    ToolUnavailable,
)
from pricing_agent.mcp_clients.capacity_client import CapacityClient
from pricing_agent.mcp_clients.cost_client import CostClient, PolicyClient
from pricing_agent.mcp_clients.event_client import EventClient
from pricing_agent.mcp_clients.vauto_client import VautoClient

__all__ = [
    "CallRecord",
    "CapacityClient",
    "CostClient",
    "EventClient",
    "FixtureStore",
    "MockTransport",
    "Mutation",
    "PolicyClient",
    "SourceMeta",
    "ToolResponse",
    "ToolStatus",
    "ToolUnavailable",
    "VautoClient",
]
