"""Workflow-specific page copy, in one typed table.

The views are shared: `render_dashboard` serves Acquire Inventory, `render_vehicle_detail`
serves Price Inventory, and a later phase may bind either to a second workflow. What the
page *says* has to follow the workflow; what it *computes* must not. Keeping the copy here
means a view asks for its heading rather than branching on a workflow name, and a new
workflow needs one table entry instead of an `if` in every view.

`scope_note` exists for one reason worth naming: Acquire Inventory sounds like it appraises
a vehicle you are thinking of buying, and it does not. A page whose title implies a
capability the engine does not have is a correctness problem, not a wording problem, so the
limit is rendered on the page rather than left to the reader.

No arithmetic here, and no Streamlit state — only strings and the header that prints them.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

import streamlit as st

from pricing_agent.workflows.context import WorkflowContext


@dataclass(frozen=True)
class WorkflowCopy:
    """What a page calls itself when it is rendered for a given dealer workflow."""

    title: str
    subtitle: str
    instruction: str | None = None
    """The next action, when the page needs a control set before it means anything."""

    scope_note: str | None = None
    """A capability the workflow's name implies but the product does not have."""


WORKFLOW_COPY: Mapping[WorkflowContext, WorkflowCopy] = MappingProxyType(
    {
        WorkflowContext.ACQUIRE_INVENTORY: WorkflowCopy(
            title="Acquire Inventory",
            subtitle=(
                "Understand available capacity, aging pressure, and portfolio needs before "
                "adding more vehicles."
            ),
            instruction=(
                "Read capacity and open slots first, then the risk table for the capital "
                "already committed."
            ),
            scope_note=(
                "Scope: this evaluates the portfolio you already hold. It does **not** "
                "appraise an external acquisition candidate — that would need a valuation "
                "of a vehicle not in inventory and an acquisition-cost source, neither of "
                "which is in the MVP."
            ),
        ),
        WorkflowContext.PRICE_INVENTORY: WorkflowCopy(
            title="Price Inventory",
            subtitle=(
                "Evaluate market position, sales velocity, break-even economics, and "
                "pricing headroom for a vehicle already in inventory."
            ),
            instruction="Choose a vehicle in the sidebar.",
        ),
        WorkflowContext.MERCHANDISE_INVENTORY: WorkflowCopy(
            title="Merchandise Inventory",
            subtitle=(
                "Build a sale-event promotion plan that balances inventory velocity, gross "
                "protection, and safe promotional headroom."
            ),
            instruction="Choose an event and a utilization target in the sidebar.",
        ),
        WorkflowContext.IMPROVE_AGING_INVENTORY: WorkflowCopy(
            title="Improve Aging Inventory",
            subtitle=(
                "Coordinate portfolio forecasting, single-vehicle diagnostics, and event "
                "promotion planning against the aged cohort."
            ),
            scope_note=(
                "The orchestration is not implemented yet. This page describes the "
                "sequence; it runs none of it."
            ),
        ),
    }
)


def copy_for(workflow_context: WorkflowContext | None) -> WorkflowCopy | None:
    """Copy for a workflow, or `None` when the view is rendered without one."""
    if workflow_context is None:
        return None
    return WORKFLOW_COPY.get(workflow_context)


def render_workflow_header(
    workflow_context: WorkflowContext | None,
    *,
    fallback_title: str | None = None,
    fallback_subtitle: str | None = None,
) -> WorkflowCopy | None:
    """Print the page heading and return the copy that produced it.

    With no workflow bound the view keeps whatever heading it had before — the fallback is
    the generic copy, not a stand-in for a missing workflow. Returning the copy lets a
    caller place `instruction` and `scope_note` where they belong on that particular page
    rather than forcing one layout on all of them.
    """
    copy = copy_for(workflow_context)

    if copy is None:
        if fallback_title is not None:
            st.title(fallback_title)
        if fallback_subtitle is not None:
            st.caption(fallback_subtitle)
        return None

    st.title(copy.title)
    st.caption(copy.subtitle)
    return copy
