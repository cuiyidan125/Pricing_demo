"""Ask the Dealer AI Assistant — the product's primary entry point.

Phase 4 connects this page to deterministic routing. A dealer's question is classified,
the named vehicle is resolved against real inventory, and — for a supported single-workflow
request — one skill runs and its result is summarised here, with a button to open the full
analytical workspace.

Three things this page still does not do, by design:

* **No LLM.** Routing, parsing, and resolution are rules over strings
  (`pricing_agent.agents`). The only numbers shown come straight out of the skill result.
* **No orchestration.** Improve Aging, which would coordinate three skills, returns a
  transparent "not yet available" rather than running anything.
* **No publishing.** Nothing here writes a price.

The workflow cards are passed in by the caller, not imported, so the view stays free of an
import cycle with `workflows.registry`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, NamedTuple

import streamlit as st

from pricing_agent.agents import run_assistant
from pricing_agent.agents.assistant import AssistantResponse, AssistantState
from pricing_agent.workflows.context import WorkflowContext
from pricing_agent.workflows.pages import page_for

AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)

# Stable, non-widget session keys. Streamlit garbage-collects the state of any widget that
# is not rendered on a run, so the request and its result are held under plain keys that
# survive navigating to a workflow and back.
QUESTION_KEY = "assistant_question"
RESPONSE_KEY = "assistant_response"
SELECTED_VEHICLE_KEY = "assistant_selected_vehicle_id"

# Read by the Price Inventory view to preselect the routed vehicle.
SESSION_KEY = QUESTION_KEY  # kept for backward compatibility with earlier phases

SUGGESTED_PROMPTS = (
    "What should I price 2020 Ford F-150 XLT?",
    "What will my inventory look like in the next 30 days?",
    "Plan the Summer Clearance event to reach 70% utilization.",
    "Which aging vehicles should I promote?",
)


class WorkflowCard(NamedTuple):
    """The subset of registry metadata this view renders. Passed in, never imported."""

    display_name: str
    description: str
    icon: str
    availability: str
    skills: tuple[str, ...]


def md(text: str) -> str:
    """Escape dollar signs so Streamlit does not read `$…$` as LaTeX."""
    return str(text).replace("$", r"\$")


def _money(value: object) -> str:
    try:
        return f"\\${float(value):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _open_workflow_link(url_path: str, label: str) -> None:
    """A client-side link to a workflow page.

    `st.page_link` with the live `st.Page` navigates inside the Streamlit session, so the
    routed vehicle held in session state survives the jump. A raw HTML anchor would do a
    full page reload and wipe it, which is exactly the bug this avoids. If the page is not
    registered (e.g. imported outside the running app), fall back to guidance.
    """
    page = page_for(url_path)
    if page is not None:
        st.page_link(page, label=label, icon=":material/arrow_forward:")
    else:
        st.caption(f"Open the workflow from the sidebar (`{url_path}`).")


def render_assistant_home(
    workflow_context: WorkflowContext | None = None,
    workflows: Iterable[WorkflowCard] = (),
) -> None:
    """Render the assistant entry point."""
    st.title("Ask the Dealer AI Assistant")
    st.caption(
        "Describe a pricing or inventory decision in your own words. The assistant reads "
        "the request with deterministic rules, chooses the right dealer workflow, resolves "
        "the vehicle against real inventory, and hands the numbers to the engine — it never "
        "produces a price itself, and never calls a model."
    )

    st.markdown(
        "**What it can do now**\n\n"
        "- Price a vehicle already in inventory, end to end\n"
        "- Forecast what the lot will sell over the next 30 and 90 days\n"
        "- Plan a sale event when you name one on the calendar\n"
        "- Route an aging-inventory question (orchestration arrives in a later phase)"
    )

    request = st.text_area(
        "Your question",
        key="assistant_input",
        placeholder="e.g. What should I price 2020 Ford F-150 XLT?",
        height=110,
    )

    left, right = st.columns([1, 4])
    submitted = left.button("Analyze", type="primary")
    right.caption("Suggested questions — copy one into the box above.")

    for prompt in SUGGESTED_PROMPTS:
        st.markdown(f"- _{prompt}_")

    if submitted:
        if request.strip():
            st.session_state[QUESTION_KEY] = request
            response = run_assistant(request, as_of=AS_OF)
            st.session_state[RESPONSE_KEY] = response
            # Seed the Price Inventory preselect once, at submit time — not during render —
            # so it does not depend on the result being re-rendered before navigation.
            if response.resolved_vehicle_id:
                st.session_state[SELECTED_VEHICLE_KEY] = response.resolved_vehicle_id
            # Hand the aging orchestration result to its workspace so the page reflects the
            # question actually asked, not just the canned demo scenario. Cleared on any
            # non-aging query so a later visit to the workspace does not show a stale result.
            if response.improve_aging is not None:
                st.session_state["improve_aging_result"] = response.improve_aging
            else:
                st.session_state.pop("improve_aging_result", None)
        else:
            st.session_state.pop(RESPONSE_KEY, None)
            st.warning("Type a question first, or pick a workflow below.", icon="✍️")

    response: AssistantResponse | None = st.session_state.get(RESPONSE_KEY)
    if response is not None:
        st.divider()
        _render_response(response)

    st.divider()
    _render_cards(workflows)

    st.info(
        "Prototype on synthetic data. Forecasts are a **configured simulation**, not a "
        "trained prediction, and no price can be published from this application.",
        icon="ℹ️",
    )


# --- the six states -------------------------------------------------------------------


def _render_response(response: AssistantResponse) -> None:
    question = st.session_state.get(QUESTION_KEY, "")
    if question:
        st.caption(f"You asked: _{question[:160]}_")

    dispatch = {
        AssistantState.ROUTED_AND_EXECUTED: _render_executed,
        AssistantState.NEEDS_CLARIFICATION: _render_clarification,
        AssistantState.NO_MATCH: _render_no_match,
        AssistantState.AMBIGUOUS_MATCH: _render_ambiguous,
        AssistantState.WORKFLOW_NOT_YET_AVAILABLE: _render_not_available,
        AssistantState.EXECUTION_ERROR: _render_error,
        # Phase 5 — Improve Aging orchestration states.
        AssistantState.PARTIAL_RESULT: _render_executed,
        AssistantState.TARGET_NOT_ACHIEVABLE: _render_executed,
        AssistantState.NO_SAFE_ACTIONS: _render_clarification,
    }
    dispatch[response.state](response)

    _render_route_detail(response)


def _workflow_label(response: AssistantResponse) -> str:
    return response.workflow.label if response.workflow else "—"


def _render_executed(response: AssistantResponse) -> None:
    if response.workflow is WorkflowContext.PRICE_INVENTORY:
        _render_pricing_result(response)
    elif response.workflow is WorkflowContext.ACQUIRE_INVENTORY:
        _render_portfolio_result(response)
    elif response.workflow is WorkflowContext.MERCHANDISE_INVENTORY:
        _render_promotion_result(response)
    elif response.workflow is WorkflowContext.IMPROVE_AGING_INVENTORY:
        _render_improve_aging_result(response)


def _render_improve_aging_result(response: AssistantResponse) -> None:
    s = response.summary
    icon = "✅" if response.state is AssistantState.ROUTED_AND_EXECUTED else "🚫"
    st.markdown(f"{icon} **Improve Aging Inventory** — {md(response.message)}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Units on lot", s.get("current_inventory", "—"),
              f"{s.get('current_utilization', 0):.0%} utilized", delta_color="off")
    c2.metric("Aging candidates", s.get("candidate_count", 0),
              f"{s.get('deep_analysed_count', 0)} analysed", delta_color="off")
    c3.metric("Excluded / protected", s.get("excluded_count", 0))
    target = s.get("target_status", "NO_EVENT")
    c4.metric("Target", "No event" if target == "NO_EVENT" else target.replace("_", " ").title())

    reduction = s.get("required_unit_reduction")
    prob = s.get("probability_target_achieved")
    bits = []
    if reduction is not None:
        bits.append(f"needs **{reduction}** incremental sale(s)")
    if s.get("recommended_plan"):
        bits.append(f"recommended plan **{s['recommended_plan'].replace('_', ' ').title()}**")
    if prob is not None:
        bits.append(f"hits target **{prob:.0%}** of the time")
    if bits:
        st.caption(" · ".join(bits))

    counts = s.get("action_counts") or {}
    if counts:
        st.caption("Actions: " + " · ".join(
            f"{k.replace('_', ' ').title()} {v}" for k, v in counts.items()))
    if s.get("approvals_required"):
        st.caption(f"⚠️ {s['approvals_required']} approval(s) required before anything moves.")

    _render_warnings(response)

    if response.target_url:
        _open_workflow_link(response.target_url, "Open the full Improve Aging workspace →")
        st.caption("The workspace shows the diagnosis, per-vehicle evidence, plan comparison, "
                   "and the execution trace for this request.")


def _render_pricing_result(response: AssistantResponse) -> None:
    s = response.summary
    st.success(
        f"**{s.get('vehicle', response.resolved_vehicle_id)}** — priced with the "
        f"single-vehicle valuation skill (`{response.resolved_vehicle_id}`).",
        icon="✅",
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current list", _money(s.get("current_list_price")))
    c2.metric("Recommended", _money(s.get("recommended_price")))
    c3.metric(
        "Days to sell (P50)", f"{s.get('p50_days_to_sale', 0):.0f}",
        f"P90 {s.get('p90_days_to_sale', 0):.0f}", delta_color="off",
    )
    c4.metric("Break-even", _money(s.get("break_even_price")))

    st.caption(
        f"Promotional headroom {_money(s.get('promotional_headroom'))} · "
        f"strategy **{str(s.get('strategy', '')).replace('_', ' ').title()}**. "
        "Every figure is read from the skill result — the assistant computes nothing."
    )

    _render_warnings(response)

    if response.target_url:
        _open_workflow_link(response.target_url, "Open the full Price Inventory analysis →")
        st.caption("Opens the workspace with this vehicle already selected.")


def _render_portfolio_result(response: AssistantResponse) -> None:
    s = response.summary
    st.success("Ran the portfolio forecast for acquisition readiness and capacity.", icon="✅")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Units on lot", s.get("units_on_lot", "—"), f"{s.get('open_slots', 0)} open")
    c2.metric("Utilization", f"{s.get('utilization', 0):.0%}")
    c3.metric(
        "Sold, next 30 days (P50)", f"{s.get('thirty_day_units_p50', 0):.0f}",
        f"P10 {s.get('thirty_day_units_p10', 0):.0f} – P90 {s.get('thirty_day_units_p90', 0):.0f}",
        delta_color="off",
    )
    c4.metric("Below break-even", s.get("units_below_break_even", "—"))

    _render_warnings(response)

    if response.target_url:
        _open_workflow_link(response.target_url, "Open the full Acquire Inventory analysis →")


def _render_promotion_result(response: AssistantResponse) -> None:
    s = response.summary
    st.success(f"Planned the **{s.get('event_name')}** event with the promotion planner.", icon="✅")

    c1, c2, c3 = st.columns(3)
    c1.metric("Feasibility", str(s.get("feasibility_status", "")).replace("_", " ").title())
    c2.metric("Incremental sales needed", s.get("incremental_required", "—"))
    c3.metric("Hits target", f"{s.get('probability_target_achieved', 0):.0%}")

    st.caption(
        f"Target ending inventory {s.get('target_ending_inventory')} · recommended plan "
        f"**{str(s.get('recommended_plan', '')).replace('_', ' ').title()}**."
    )

    _render_warnings(response)

    if response.target_url:
        _open_workflow_link(response.target_url, "Open the full Merchandise Inventory plan →")


def _render_clarification(response: AssistantResponse) -> None:
    st.warning(response.message, icon="❓")
    if response.target_url:
        _open_workflow_link(response.target_url, "Open the workflow →")


def _render_no_match(response: AssistantResponse) -> None:
    st.error(response.message, icon="🚫")
    if response.target_url:
        _open_workflow_link(response.target_url, "Pick a vehicle in Price Inventory →")


def _render_ambiguous(response: AssistantResponse) -> None:
    st.warning(response.message, icon="🔀")
    for candidate in response.candidates:
        label = (
            f"{candidate.get('year')} {candidate.get('make')} {candidate.get('model')} "
            f"{candidate.get('trim')}".strip()
        )
        cols = st.columns([3, 2, 2])
        cols[0].markdown(f"**{label}** · `{candidate.get('vehicle_id')}`")
        cols[1].caption(f"{candidate.get('mileage'):,} mi" if candidate.get("mileage") else "—")
        if cols[2].button("Analyze this one", key=f"pick_{candidate.get('vehicle_id')}"):
            st.session_state[SELECTED_VEHICLE_KEY] = candidate.get("vehicle_id")
            # Re-run the resolved vehicle straight through the pricing path.
            st.session_state[RESPONSE_KEY] = run_assistant(
                str(candidate.get("vehicle_id")), as_of=AS_OF
            )
            st.rerun()


def _render_not_available(response: AssistantResponse) -> None:
    st.info(response.message, icon="🚧")
    if response.target_url:
        _open_workflow_link(response.target_url, "See the Improve Aging sequence →")


def _render_error(response: AssistantResponse) -> None:
    st.error(response.message, icon="⚠️")


def _render_warnings(response: AssistantResponse) -> None:
    if not response.warnings:
        return
    with st.expander(f"Top warnings ({len(response.warnings)})"):
        for warning in response.warnings:
            st.markdown(
                f"- **{warning.get('code')}** ({warning.get('severity')}) — "
                f"{str(warning.get('message', '')).replace('$', chr(92) + '$')}"
            )


def _render_route_detail(response: AssistantResponse) -> None:
    route = response.route
    with st.expander("How this was routed"):
        st.markdown(
            f"- Detected workflow: **{_workflow_label(response)}**\n"
            f"- Skill: `{response.skill or '—'}`\n"
            f"- Confidence: **{route.confidence.value}**\n"
            f"- Reason codes: {', '.join(f'`{code}`' for code in route.reason_codes) or '—'}\n"
            f"- Extracted entities: `{route.extracted_entities or '—'}`\n"
            f"- Missing fields: {', '.join(route.missing_fields) or '—'}\n"
            f"- Ambiguous fields: {', '.join(route.ambiguous_fields) or '—'}"
        )
        st.caption(
            "Deterministic rules only. No model was called, and no figure above the "
            "workflow line was generated by the router."
        )


def _render_cards(workflows: Iterable[WorkflowCard]) -> None:
    cards = list(workflows)
    if not cards:
        return
    st.subheader("Dealer workflows")
    st.caption("Open any of these directly from the sidebar.")
    columns = st.columns(2)
    for index, card in enumerate(cards):
        with columns[index % 2].container(border=True):
            st.markdown(f"**{card.icon} {card.display_name}**")
            st.caption(card.description)
            if card.skills:
                st.caption("Uses: " + ", ".join(card.skills))
            if card.availability != "AVAILABLE":
                st.caption(f"Status: {card.availability.replace('_', ' ').title()}")
