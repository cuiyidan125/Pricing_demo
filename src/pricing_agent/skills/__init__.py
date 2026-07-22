"""Workflow orchestration. Sequences MCP calls and domain calls; computes nothing itself."""

from pricing_agent.skills import single_vehicle

__all__ = ["single_vehicle"]
