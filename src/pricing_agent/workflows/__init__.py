"""Dealer workflows.

A **workflow** is a dealer business job. A **skill** is a reusable analytical capability
invoked underneath one. Workflows never contain calculation — they sequence and frame.

Only `context` is re-exported here. `registry` imports `pricing_agent.views` to bind
render callables, and views import `WorkflowContext` from this package, so exporting the
registry at package level would close an import cycle. Import it explicitly:

    from pricing_agent.workflows.registry import WORKFLOWS
"""

from pricing_agent.workflows.context import WorkflowContext

__all__ = ["WorkflowContext"]
