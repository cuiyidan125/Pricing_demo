"""Reusable Streamlit view functions.

Views render. They read finished skill results and never calculate — the architecture
guard asserts they import neither `domain` nor `simulation`.

`WorkflowContext` is **not** exported here. It moved to `pricing_agent.workflows.context`
in Phase 3: a workflow is a dealer business job, not a screen, so the type belongs with
the workflow layer. Import it from there.
"""

from pricing_agent.views.assistant_home import WorkflowCard, render_assistant_home
from pricing_agent.views.dashboard import render_dashboard
from pricing_agent.views.improve_aging import render_improve_aging
from pricing_agent.views.page_config import (
    APP_TITLE,
    PROMOTION_ICON,
    PROMOTION_TITLE,
    VEHICLE_DETAIL_TITLE,
    configure_page,
)
from pricing_agent.views.promotion import render_promotion_planner
from pricing_agent.views.vehicle_detail import render_vehicle_detail
from pricing_agent.views.workflow_copy import (
    WORKFLOW_COPY,
    WorkflowCopy,
    copy_for,
    render_workflow_header,
)

__all__ = [
    "APP_TITLE",
    "PROMOTION_ICON",
    "PROMOTION_TITLE",
    "VEHICLE_DETAIL_TITLE",
    "WORKFLOW_COPY",
    "WorkflowCard",
    "WorkflowCopy",
    "configure_page",
    "copy_for",
    "render_assistant_home",
    "render_dashboard",
    "render_improve_aging",
    "render_promotion_planner",
    "render_vehicle_detail",
    "render_workflow_header",
]
