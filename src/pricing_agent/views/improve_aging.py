"""Improve Aging Inventory — evidence workspace. Phase 5.

Replaces the Phase 3 shell. This page runs the orchestration for a reproducible scenario
(Summer Clearance, 70% utilization, injected clock) and lays out the full evidence: the
portfolio diagnosis, the candidate ranking, the per-vehicle pricing evidence, the promotion
comparison, the projected ending inventory, warnings and approvals, and the execution trace.

If the assistant routed a specific aging request, its stored result is shown instead, so the
page reflects the question the dealer actually asked.

Nothing here computes a number — every figure is read from a skill result carried through the
orchestration, and each is shown with the `simulation_id` that produced it, because figures
from different simulations are never combined.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from pricing_agent.mcp_clients import MockTransport
from pricing_agent.views.workflow_copy import render_workflow_header
from pricing_agent.workflows.context import WorkflowContext
from pricing_agent.workflows.improve_aging import (
    ImproveAgingRequest,
    WorkflowState,
    run_improve_aging,
)

AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)

# The reproducible demo scenario: a real calendar event, its real dates, a stated target.
DEMO_REQUEST = ImproveAgingRequest(
    target_utilization=0.70,
    event_requested=True,
    event_id="EVT-SUMMER-2026",
    event_name="Summer Clearance",
    available_events=("Summer Clearance", "Labor Day Sales Event"),
)

STATE_STYLE = {
    WorkflowState.ROUTED_AND_EXECUTED: ("✅", "success"),
    WorkflowState.TARGET_NOT_ACHIEVABLE: ("🚫", "error"),
    WorkflowState.PARTIAL_RESULT: ("⚠️", "warning"),
    WorkflowState.NEEDS_CLARIFICATION: ("❓", "warning"),
    WorkflowState.NO_SAFE_ACTIONS: ("🛑", "warning"),
    WorkflowState.EXECUTION_ERROR: ("⚠️", "error"),
}


def md(text: str) -> str:
    return str(text).replace("$", r"\$")


@st.cache_data(show_spinner="Running the Improve Aging orchestration…")
def _run_demo(target: float, event_id: str | None):
    """Cached so revisiting the page does not re-run three skills. Keyed on the inputs that
    change the result."""
    request = ImproveAgingRequest(
        target_utilization=target,
        event_requested=event_id is not None,
        event_id=event_id,
        event_name="Summer Clearance" if event_id else None,
        available_events=DEMO_REQUEST.available_events,
    )
    return run_improve_aging(MockTransport(as_of=AS_OF), request)


def render_improve_aging(workflow_context: WorkflowContext | None = None) -> None:
    """Render the Improve Aging evidence workspace."""
    render_workflow_header(
        workflow_context,
        fallback_title="Improve Aging Inventory",
        fallback_subtitle=(
            "Coordinate portfolio forecasting, single-vehicle diagnostics, and event "
            "promotion planning against the aged cohort."
        ),
    )

    # Prefer the assistant's routed result if one is in session; otherwise the demo scenario.
    result = st.session_state.get("improve_aging_result")
    if result is None:
        result = _run_demo(0.70, "EVT-SUMMER-2026")

    icon, kind = STATE_STYLE.get(result.state, ("•", "info"))
    getattr(st, kind)(md(f"{icon} **{result.state.value.replace('_', ' ').title()}** — {result.message}"))

    _section_objective(result)
    _section_diagnosis(result)
    _section_candidates(result)
    _section_evidence(result)
    _section_promotion(result)
    _section_projection(result)
    _section_warnings_approvals(result)
    _section_trace(result)

    st.info(
        "Prototype on synthetic data. This workflow **coordinates** the three skills; it "
        "does not compute any figure itself, and no price can be published.",
        icon="ℹ️",
    )


# --- 1. objective + 10. handled below -------------------------------------------------


def _section_objective(result) -> None:
    st.subheader("1 · Workflow objective")
    req = result.request
    st.markdown(
        "Get aged units off a full lot without pricing below break-even, by coordinating "
        "three skills in order: **portfolio forecast → candidate selection → single-vehicle "
        "valuation → promotion plan → consolidated action plan**."
    )
    cols = st.columns(3)
    cols[0].caption(f"Target utilization: **{req.target_utilization:.0%}**"
                    if req.target_utilization is not None else "Target utilization: not set")
    cols[1].caption(f"Event: **{req.event_name or 'none supplied'}**")
    cols[2].caption("Execution order: " + " → ".join(result.execution_order))


def _section_diagnosis(result) -> None:
    st.subheader("2 · Portfolio diagnosis  ·  3 · Aging & capacity")
    d = result.portfolio_summary
    if not d:
        st.caption("No diagnosis available.")
        return
    c = st.columns(4)
    c[0].metric("Units on lot", d.get("current_inventory", "—"),
                f"{d.get('physical_open_slots', 0)} open", delta_color="off")
    c[1].metric("Utilization", f"{d.get('current_utilization', 0):.0%}",
                f"target {d.get('target_utilization'):.0%}" if d.get("target_utilization") else "no target",
                delta_color="off")
    c[2].metric("Over 90 days", f"{d.get('aged_concentration_pct', 0):.0%} of lot")
    c[3].metric("Below break-even", d.get("units_below_break_even", "—"))

    buckets = d.get("aging_buckets") or []
    if buckets:
        frame = pd.DataFrame([
            {"Age band (days)": b["label"], "Units now": b["unit_count"],
             "Projected at horizon": b["projected_unit_count_at_horizon"],
             "Cost basis": b["cost_basis"]}
            for b in buckets
        ])
        st.dataframe(frame, hide_index=True, column_config={
            "Cost basis": st.column_config.NumberColumn(format="$%d"),
        })
    st.caption(f"Diagnosis from the portfolio simulation `{d.get('simulation_id')}`.")


def _section_candidates(result) -> None:
    st.subheader("4 · Candidate ranking  ·  5 · Selected and excluded")
    if result.selection is None:
        st.caption("No selection available.")
        return
    sel = result.selection

    st.markdown(f"**Selected — {len(sel.candidates)} candidate(s)**, ranked by portfolio risk score.")
    if sel.candidates:
        st.dataframe(
            pd.DataFrame([
                {"Vehicle": c.description, "ID": c.vehicle_id, "Days": c.days_in_inventory,
                 "Risk": round(c.risk_score, 1), "Why selected": ", ".join(c.reason_codes)}
                for c in sel.candidates
            ]),
            hide_index=True,
            column_config={"Risk": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100)},
        )

    st.markdown(f"**Excluded — {len(sel.exclusions)}**, held back with a reason.")
    if sel.exclusions:
        st.dataframe(
            pd.DataFrame([
                {"Vehicle": e.description, "ID": e.vehicle_id,
                 "Why excluded": ", ".join(e.reason_codes)}
                for e in sel.exclusions
            ]),
            hide_index=True,
        )
        protected = [e.vehicle_id for e in sel.exclusions
                     if any(r in sel.PROTECTED_REASONS for r in e.reason_codes)]
        if protected:
            st.caption("🛡️ Protected from aggressive promotion: " + ", ".join(protected))


def _section_evidence(result) -> None:
    st.subheader("6 · Per-vehicle pricing & financial evidence")
    if not result.vehicle_evidence:
        st.caption("Single-vehicle analysis was not run (the workflow stopped earlier).")
        return
    st.caption(
        "Each row is a separate single-vehicle simulation, shown side by side — never "
        "combined, because each has its own `simulation_id`."
    )
    rows = []
    for ev in result.vehicle_evidence:
        r = ev.result
        strategy = r.get("recommended_strategy", {}).get("strategy", "")
        scenario = next(
            (s for s in r.get("pricing_scenarios", [])
             if s["strategy"] == strategy), {}
        )
        be = r.get("break_even_analysis", {})
        head = r.get("promotional_headroom", {})
        rows.append({
            "Vehicle": ev.description,
            "Action": ev.recommended_action.replace("_", " ").title(),
            "Current": ev.current_price,
            "Recommended": scenario.get("proposed_list_price"),
            "Days P50": (scenario.get("additional_days_to_sale") or {}).get("p50"),
            "Break-even": be.get("current_accounting_break_even"),
            "Headroom": head.get("max_safe_discount"),
            "sim_id": ev.simulation_id,
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={
            "Current": st.column_config.NumberColumn(format="$%d"),
            "Recommended": st.column_config.NumberColumn(format="$%d"),
            "Break-even": st.column_config.NumberColumn(format="$%d"),
            "Headroom": st.column_config.NumberColumn(format="$%d"),
            "Days P50": st.column_config.NumberColumn(format="%.0f"),
        },
    )


def _section_promotion(result) -> None:
    st.subheader("7 · Promotion-plan comparison")
    promotion = result.promotion_result
    if promotion is None:
        st.caption("No promotion plan — name a calendar event to add one. "
                   "Portfolio diagnosis and per-vehicle actions above stand on their own.")
        return
    feasibility = promotion["feasibility"]
    st.caption(
        f"Feasibility **{feasibility['status'].replace('_', ' ').title()}** · "
        f"needs {feasibility['required_incremental_units']} incremental sale(s) · "
        f"hits target {feasibility['probability_target_achieved']:.0%} of the time. "
        f"All from the promotion simulation `{result.portfolio_summary.get('outcome_simulation_id')}`."
    )
    rows = []
    for plan in promotion["plans"]:
        o = plan["outcomes"]
        rows.append({
            "Plan": plan["plan_type"].replace("_", " ").title(),
            "Vehicles": plan["totals"]["vehicle_count"],
            "Dealer-funded": plan["totals"]["total_dealer_funded"],
            "Incremental sold (P50)": o["incremental_units_sold"]["p50"],
            "Hits target": o["probability_target_achieved"],
            "Recommended": "★" if plan["plan_type"] == promotion["recommended_plan"]["plan_type"] else "",
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={
            "Dealer-funded": st.column_config.NumberColumn(format="$%d"),
            "Hits target": st.column_config.NumberColumn(format="%.0f%%"),
        },
    )
    if result.held_from_promotion:
        st.caption(
            "🛡️ Held back from promotion despite the skill's eligibility (workflow "
            "protection — recently acquired or high demand): "
            + ", ".join(result.held_from_promotion)
        )


def _section_projection(result) -> None:
    st.subheader("8 · Projected ending inventory")
    d = result.portfolio_summary
    ending = d.get("expected_ending_inventory")
    if not ending:
        st.caption("Available once a promotion plan runs (a single simulation is needed to "
                   "project a joint outcome).")
        return
    c = st.columns(4)
    c[0].metric("Required reduction", d.get("required_unit_reduction", "—"))
    c[1].metric("Ending inventory (P50)", f"{ending['p50']:.0f}",
                f"P10 {ending['p10']:.0f} – P90 {ending['p90']:.0f}", delta_color="off")
    c[2].metric("Hits target", f"{d.get('probability_target_achieved', 0):.0%}")
    gross = d.get("expected_gross_impact") or {}
    c[3].metric("Gross impact (P50)", f"${gross.get('p50', 0):,.0f}" if gross else "—")
    st.caption(f"Joint outcome from the promotion simulation `{d.get('outcome_simulation_id')}` "
               "— not combined with the per-vehicle simulations above.")


def _section_warnings_approvals(result) -> None:
    st.subheader("9 · Warnings and approvals")
    if result.approvals_required:
        st.markdown("**Approvals required**")
        st.dataframe(
            pd.DataFrame([
                {"Vehicle": a.get("vehicle_id") or "—", "Source": a.get("source"),
                 "Type": a.get("approval_type") or a.get("type"),
                 "Reason": a.get("reason", "")}
                for a in result.approvals_required
            ]),
            hide_index=True,
        )
    else:
        st.caption("No approvals required.")

    codes = sorted({
        w["code"]
        for ev in result.vehicle_evidence for w in ev.warnings
    } | ({w["code"] for w in (result.promotion_result or {}).get("warnings", [])}))
    if codes:
        st.caption("Warning codes across analysed vehicles and the plan: "
                   + ", ".join(f"`{c}`" for c in codes))


def _section_trace(result) -> None:
    st.subheader("10 · Workflow execution trace")
    st.caption(f"workflow_id `{result.workflow_id}` · type IMPROVE_AGING_INVENTORY")
    st.dataframe(
        pd.DataFrame([
            {"#": t.step_number, "Step": t.step_name, "Skill": t.skill_called or "—",
             "request_id": t.request_id or "—", "simulation_id": t.simulation_id or "—",
             "Status": t.status, "Warnings": len(t.warnings)}
            for t in result.trace
        ]),
        hide_index=True,
    )
    if result.unavailable:
        st.caption("Unavailable in this run: " + ", ".join(result.unavailable))
