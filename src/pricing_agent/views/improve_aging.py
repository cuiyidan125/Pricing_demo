"""Improve Aging Inventory — workflow landing page.

A **placeholder that describes the sequence, not a fourth skill.** Improve Aging is an
orchestration of the three existing skills; the orchestration itself is the next phase.

This page fabricates nothing. It shows no vehicle list, no candidate ranking, and no
projected outcome, because every one of those would have to be invented to appear here —
and a placeholder that invents numbers is worse than one that admits it is a placeholder.
"""

from __future__ import annotations

import streamlit as st

from pricing_agent.views.workflow_copy import render_workflow_header
from pricing_agent.workflows.context import WorkflowContext

STEPS = (
    (
        "Diagnose portfolio aging and capacity risk",
        "inventory-portfolio-forecast",
        "Which cohort is aging, how much capital it holds, and what the lot looks like in "
        "30 and 90 days.",
    ),
    (
        "Identify candidate vehicles",
        "inventory-portfolio-forecast",
        "Rank by expected economic damage — aging, depreciation, negative-value "
        "probability, and dollars at stake.",
    ),
    (
        "Run single-vehicle financial and pricing analysis",
        "single-vehicle-valuation",
        "Per candidate: valuation, break-even, the binding floor, and how much discount "
        "room actually exists.",
    ),
    (
        "Build a targeted promotion plan",
        "dealer-event-promotion-planner",
        "Which of those candidates can be promoted safely, by how much, and against which "
        "event window.",
    ),
    (
        "Project ending inventory and target-achievement probability",
        "dealer-event-promotion-planner",
        "What the plan does to utilization, and how often it actually hits the target.",
    ),
    (
        "Review warnings and approvals",
        "policy layer",
        "Publication bars, loss-minimization exceptions, and what needs a manager's "
        "signature before anything moves.",
    ),
)


def render_improve_aging(workflow_context: WorkflowContext | None = None) -> None:
    """Render the Improve Aging Inventory landing page."""
    render_workflow_header(
        workflow_context,
        fallback_title="Improve Aging Inventory",
        fallback_subtitle=(
            "Coordinate portfolio forecasting, single-vehicle diagnostics, and event "
            "promotion planning against the aged cohort."
        ),
    )
    st.caption(
        "One job: getting aged units off the lot without breaking a price floor."
    )

    st.warning(
        "**Workflow orchestration will be implemented in the next phase.** This page "
        "describes the sequence; it does not run it yet.",
        icon="🚧",
    )

    st.subheader("The sequence")
    for index, (title, capability, detail) in enumerate(STEPS, start=1):
        with st.container(border=True):
            st.markdown(f"**{index}. {title}**")
            st.caption(detail)
            st.caption(f"Capability: `{capability}`")

    st.subheader("Why this is a workflow and not a skill")
    st.markdown(
        "The three skills stay exactly as they are. This workflow sequences them and "
        "frames the result — it adds no new valuation, forecasting, or promotion "
        "arithmetic of its own.\n\n"
        "That boundary is not stylistic. Each skill runs its **own** simulation with its "
        "own `simulation_id`, and combining percentile figures across two simulations "
        "would imply they describe one scenario when they do not. The orchestration will "
        "present its results side by side rather than adding them together."
    )

    st.info(
        "In the meantime, **Acquire Inventory** shows the aging cohort and capacity "
        "pressure, **Price Inventory** analyses any single aged unit, and "
        "**Merchandise Inventory** builds the promotion plan.",
        icon="🧭",
    )
