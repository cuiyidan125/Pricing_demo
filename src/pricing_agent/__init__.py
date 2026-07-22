"""Internal Used Vehicle Pricing and Inventory Optimization Agent (prototype).

Layer boundaries are documented in docs/architecture.md §2. The rule that matters:
`domain` and `simulation` import nothing from `agents`, `skills`, `mcp_clients`, or
`llm`, perform no I/O, and never call a model. tests/unit/test_architecture.py enforces
the LLM half of that mechanically.
"""

__version__ = "0.1.0"
