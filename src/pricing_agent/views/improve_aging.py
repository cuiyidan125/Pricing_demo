"""Improve Aging Inventory — evidence workspace. Phase 5, polished in Phase 5.1.

The page tells a story in the order a dealer or a product interviewer reads it: what is the
problem, can the target be met, what does the Agent recommend, what should I do next, which
vehicles and why, then the supporting evidence, warnings, five-step summary, and the full
audit trace at the bottom.

If the assistant routed a specific aging request, its stored result is shown; otherwise a
reproducible scenario (Summer Clearance, 70%, injected clock) runs by default.

Nothing here computes a number. Every figure is read from a skill result carried through the
orchestration; the dealer-facing labels and the "what to do next" actions come from
`improve_aging_copy`, which maps codes to words and counts items the workflow already decided.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from pricing_agent.mcp_clients import MockTransport, VautoClient
from pricing_agent.views import improve_aging_copy as copy
from pricing_agent.views.workflow_copy import render_workflow_header
from pricing_agent.workflows.context import WorkflowContext
from pricing_agent.workflows.improve_aging import (
    ImproveAgingRequest,
    WorkflowState,
    run_improve_aging,
)

AS_OF = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)

DEMO_REQUEST = ImproveAgingRequest(
    target_utilization=0.70,
    event_requested=True,
    event_id="EVT-SUMMER-2026",
    event_name="Summer Clearance",
    available_events=("Summer Clearance", "Labor Day Sales Event"),
)

# The five business steps the default summary shows, mapped from the technical trace.
BUSINESS_STEPS = (
    ("Diagnose portfolio", "PORTFOLIO_FORECAST", "inventory-portfolio-forecast"),
    ("Select candidates", "CANDIDATE_SELECTION", None),
    ("Analyze selected vehicles", "SINGLE_VEHICLE_VALUATION", "single-vehicle-valuation"),
    ("Build promotion plan", "PROMOTION_PLAN", "dealer-event-promotion-planner"),
    ("Consolidate action plan", "CONSOLIDATE", None),
)

# Recommended-plan card ordering: conservative → recommended → aggressive.
PLAN_STANCE = {"MARGIN_PROTECT": "Conservative", "BALANCED": "Balanced", "CAPACITY_FIRST": "Aggressive"}


def md(text: str) -> str:
    return str(text).replace("$", r"\$")


def _pct(value) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def _usd(value) -> str:
    return f"\\${value:,.0f}" if isinstance(value, (int, float)) else "—"


@st.cache_data(show_spinner="Running the Improve Aging orchestration…")
def _run_demo(target: float, event_id: str | None):
    request = ImproveAgingRequest(
        target_utilization=target,
        event_requested=event_id is not None,
        event_id=event_id,
        event_name="Summer Clearance" if event_id else None,
        available_events=DEMO_REQUEST.available_events,
    )
    return run_improve_aging(MockTransport(as_of=AS_OF), request)


@st.cache_data(show_spinner=False)
def _inventory_facts(as_of: datetime) -> dict:
    """vehicle_id → static facts (age, price, status) for excluded-vehicle display. A fixture
    read, not a calculation."""
    data = VautoClient(MockTransport(as_of=as_of)).get_dealer_inventory().data or []
    return {v["vehicle_id"]: v for v in data}


def render_improve_aging(workflow_context: WorkflowContext | None = None) -> None:
    render_workflow_header(
        workflow_context,
        fallback_title="Improve Aging Inventory",
        fallback_subtitle=(
            "Coordinate portfolio forecasting, single-vehicle diagnostics, and event "
            "promotion planning against the aged cohort."
        ),
    )

    result = st.session_state.get("improve_aging_result")
    if result is None:
        result = _run_demo(0.70, "EVT-SUMMER-2026")

    facts = _inventory_facts(AS_OF)

    # Narrative order: situation → recommendation → impact → actions → evidence → audit.
    _executive_summary(result)
    _achievability(result)
    _next_steps(result)
    _recommended_plan(result)
    _vehicles_requiring_action(result)
    _vehicles_excluded(result, facts)
    _why_these_vehicles(result)
    _plan_comparison(result)
    _warnings_and_approvals(result)
    _five_step_summary(result)
    _full_trace(result)
    _disclosure()


# --- 1. executive summary -------------------------------------------------------------


def executive_metrics(result) -> dict:
    """The five executive-summary values, every one read straight from the result. Kept as a
    pure function so a test can assert it invents nothing."""
    d = result.portfolio_summary or {}
    promotion = result.promotion_result
    return {
        "current_utilization": d.get("current_utilization"),
        "target_utilization": d.get("target_utilization"),
        "required_unit_reduction": d.get("required_unit_reduction"),
        "candidate_count": len(result.selection.candidates) if result.selection else 0,
        "target_status": (promotion["feasibility"]["status"] if promotion else "NO_EVENT"),
        "probability_target_achieved": d.get("probability_target_achieved"),
    }


def _executive_summary(result) -> None:
    m = executive_metrics(result)
    status = "No event" if m["target_status"] == "NO_EVENT" else m["target_status"].replace("_", " ").title()

    c = st.columns(5)
    c[0].metric("Current utilization", _pct(m["current_utilization"]))
    c[1].metric("Target utilization",
                _pct(m["target_utilization"]) if m["target_utilization"] is not None else "—")
    c[2].metric("Units to release",
                m["required_unit_reduction"] if m["required_unit_reduction"] is not None else "—")
    c[3].metric("Action candidates", m["candidate_count"])
    prob = m["probability_target_achieved"]
    c[4].metric("Target status", status,
                _pct(prob) + " likely" if isinstance(prob, (int, float)) else None,
                delta_color="off")

    statement = copy.recommendation_statement(result)
    if result.state is WorkflowState.TARGET_NOT_ACHIEVABLE:
        st.error(md(f"**{statement}**"), icon="🚫")
    elif result.state in (WorkflowState.NEEDS_CLARIFICATION, WorkflowState.NO_SAFE_ACTIONS):
        st.warning(md(f"**{statement}**"), icon="❓")
    else:
        st.success(md(f"**{statement}**"), icon="✅")


# --- 2. achievability -----------------------------------------------------------------


def _achievability(result) -> None:
    if result.state is not WorkflowState.TARGET_NOT_ACHIEVABLE or not result.promotion_result:
        return
    st.subheader("Why the target is not achievable")
    f = result.promotion_result["feasibility"]
    d = result.portfolio_summary
    required = d.get("required_unit_reduction")
    achievable = f.get("p50_achievable_incremental_units")
    gap = None
    if isinstance(required, (int, float)) and isinstance(achievable, (int, float)):
        gap = required - achievable   # subtraction of two result figures, for display only

    c = st.columns(3)
    c[0].metric("Units the target needs", required if required is not None else "—")
    c[1].metric("The safe plan can release", f"{achievable:.0f}" if isinstance(achievable, (int, float)) else "—")
    c[2].metric("Remaining gap", f"{gap:.0f}" if gap is not None else "—")

    reasons = _gap_reasons(result)
    if reasons:
        st.markdown("**Why the gap exists**")
        for line in reasons:
            st.markdown(f"- {line}")

    alts = f.get("alternatives", [])
    if alts:
        st.markdown("**What would close it**")
        for a in alts:
            st.markdown(f"- {_alternative_line(a)}")
    st.caption("All figures from the promotion simulation "
               f"`{d.get('outcome_simulation_id')}` and the portfolio diagnosis.")


def _gap_reasons(result) -> list[str]:
    """Only reasons the actual result supports."""
    reasons: list[str] = []
    sel = result.selection
    if sel:
        protected = [e for e in sel.exclusions
                     if any(r in sel.PROTECTED_REASONS for r in e.reason_codes)]
        recently = [e for e in protected if "RECENTLY_ACQUIRED" in e.reason_codes]
        campaign = [e for e in protected if "ALREADY_ASSIGNED_TO_CAMPAIGN" in e.reason_codes]
        if recently:
            reasons.append(f"{len(recently)} recently-acquired vehicle(s) are protected from discounting.")
        if campaign:
            reasons.append(f"{len(campaign)} vehicle(s) are already committed to another campaign.")
    # Price-floor: candidates that need approval because they are below break-even.
    review = sum(1 for a in result.consolidated_actions
                 if a["recommended_action"] in ("MANAGER_REVIEW", "WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW"))
    if review:
        reasons.append(f"{review} aged vehicle(s) are at or below their price floor, so they "
                       "cannot be discounted safely.")
    if result.promotion_result:
        codes = {w["code"] for w in result.promotion_result.get("warnings", [])}
        if "PRICE_CANNIBALIZATION_RISK" in codes:
            reasons.append("Discounting more units risks cannibalizing sales of the others.")
        window = result.promotion_result["feasibility"].get("event_duration_days")
        if isinstance(window, (int, float)):
            reasons.append(f"The event window is only {window} days.")
    if result.portfolio_result:
        pcodes = {w["code"] for w in result.portfolio_result.get("warnings", [])}
        if "INBOUND_CAPACITY_CONFLICT" in pcodes:
            reasons.append("Committed inbound units add capacity pressure on top of the aged cohort.")
    return reasons


def _alternative_line(a: dict) -> str:
    option = a.get("option")
    change, unit = a.get("quantified_change"), a.get("unit")
    prob = a.get("resulting_probability_target_achieved")
    prob_txt = f" → {prob:.0%} likely" if isinstance(prob, (int, float)) else ""
    label = copy._ALTERNATIVE_COPY.get(option, str(option).replace("_", " ").lower())
    if unit == "DAYS":
        return f"Extend the window to {change:.0f} days{prob_txt}."
    if unit == "RATIO":
        return f"Revise the target to {change:.0%}{prob_txt}."
    if unit == "UNITS":
        return f"Wholesale {change:.0f} unit(s){prob_txt}."
    return f"{label.capitalize()}{prob_txt}."


# --- 3. what should I do next? --------------------------------------------------------


def _next_steps(result) -> None:
    steps = copy.next_steps(result)
    if not steps:
        return
    st.subheader("What should I do next?")
    for i, step in enumerate(steps, start=1):
        st.markdown(f"**{i}. {step.title}**")
        st.caption(md(step.detail))


# --- 4. recommended plan --------------------------------------------------------------


def _recommended_plan(result) -> None:
    promotion = result.promotion_result
    if promotion is None:
        return
    st.subheader("Recommended plan")
    rec = promotion["recommended_plan"]
    plan = next((p for p in promotion["plans"] if p["plan_type"] == rec["plan_type"]), None)
    if plan is None:
        return
    o = plan["outcomes"]
    d = result.portfolio_summary

    st.markdown(f"### {rec['plan_type'].replace('_', ' ').title()}  "
                f"·  _{PLAN_STANCE.get(rec['plan_type'], '')} stance_")
    if rec.get("rationale_codes"):
        st.caption("Why: " + ", ".join(f"`{c}`" for c in rec["rationale_codes"]))

    c = st.columns(4)
    c[0].metric("Ending inventory (P50)", f"{o['ending_inventory']['p50']:.0f}",
                f"util {_pct(o['ending_utilization']['p50'])}", delta_color="off")
    c[1].metric("Hits target", _pct(o["probability_target_achieved"]))
    c[2].metric("Gross impact (P50)", _usd(o["gross_impact"]["p50"]))
    c[3].metric("Approvals required", len(result.approvals_required))

    c2 = st.columns(3)
    hs = (d.get("expected_holding_cost_savings") or {}).get("p50")
    ds = (d.get("expected_depreciation_savings") or {}).get("p50")
    c2[0].metric("Holding-cost savings (P50)", _usd(hs) if hs is not None else "Not available")
    c2[1].metric("Depreciation savings (P50)", _usd(ds) if ds is not None else "Not available")
    c2[2].metric("Dealer-funded discount", _usd(plan["totals"]["total_dealer_funded"]))

    if result.state is WorkflowState.TARGET_NOT_ACHIEVABLE:
        st.caption("This is the most aggressive safe plan — it still does **not** reach the "
                   "target. It does not guarantee the target; see the gap above.")
    if result.held_from_promotion:
        st.caption("🛡️ Held back from promotion by workflow protection: "
                   + ", ".join(result.held_from_promotion))


# --- 5. vehicles requiring action -----------------------------------------------------


def _vehicles_requiring_action(result) -> None:
    st.subheader("Vehicles requiring action")
    evidence_by_id = {e.vehicle_id: e for e in result.vehicle_evidence}
    acting = [a for a in result.consolidated_actions
              if a["recommended_action"] not in ("PROTECT_PRICE", "NO_ACTION")]
    if not acting:
        st.caption("No vehicle needs an action in this run.")
        return

    rows = []
    for a in acting:
        ev = evidence_by_id.get(a["vehicle_id"])
        res = ev.result if ev else {}
        scenario = {}
        if res:
            strat = res.get("recommended_strategy", {}).get("strategy")
            scenario = next((s for s in res.get("pricing_scenarios", [])
                             if s["strategy"] == strat), {})
        be = res.get("break_even_analysis", {})
        days = (scenario.get("additional_days_to_sale") or {})
        rows.append({
            "Vehicle": ev.description if ev else a["vehicle_id"],
            "Action": copy.action_label(a["recommended_action"]),
            "Current": a.get("current_price"),
            "Days P50": days.get("p50"),
            "Days P90": days.get("p90"),
            "Break-even": be.get("current_accounting_break_even"),
            "Approvals": len(a["approvals_required"]),
            "Why": ", ".join(copy.selection_label(c) for c in a["reason_codes"]),
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={
            "Current": st.column_config.NumberColumn(format="$%d"),
            "Break-even": st.column_config.NumberColumn(format="$%d"),
            "Days P50": st.column_config.NumberColumn(format="%.0f"),
            "Days P90": st.column_config.NumberColumn(format="%.0f"),
        },
    )
    with st.expander("Raw reason codes & per-vehicle simulation ids (audit)"):
        st.dataframe(
            pd.DataFrame([
                {"Vehicle": (evidence_by_id.get(a["vehicle_id"]).description
                             if a["vehicle_id"] in evidence_by_id else a["vehicle_id"]),
                 "Reason codes": ", ".join(a["reason_codes"]),
                 "request_id": a["referenced_request_id"] or "—",
                 "simulation_id": a["referenced_simulation_id"] or "—"}
                for a in acting
            ]),
            hide_index=True,
        )
    st.caption("Each vehicle is a separate single-vehicle simulation, shown side by side — "
               "never combined.")


# --- 6. vehicles protected or excluded ------------------------------------------------


def _vehicles_excluded(result, facts: dict) -> None:
    st.subheader("Vehicles protected or excluded")
    if result.selection is None or not result.selection.exclusions:
        st.caption("No vehicles were excluded.")
        return
    rows = []
    for e in result.selection.exclusions:
        fact = facts.get(e.vehicle_id, {})
        rows.append({
            "Vehicle": e.description,
            "Why": "; ".join(copy.exclusion_label(c) for c in e.reason_codes),
            "Days": fact.get("days_in_inventory"),
            "Status": (fact.get("status") or "ACTIVE").title(),
            "Rule type": copy.exclusion_category(e.reason_codes),
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={"Days": st.column_config.NumberColumn(format="%.0f")},
    )
    with st.expander("Raw exclusion codes (audit)"):
        st.dataframe(
            pd.DataFrame([{"Vehicle": e.description, "Codes": ", ".join(e.reason_codes)}
                         for e in result.selection.exclusions]),
            hide_index=True,
        )


# --- 7. why these vehicles? -----------------------------------------------------------


def _why_these_vehicles(result) -> None:
    if result.selection is None or not result.selection.candidates:
        return
    st.subheader("Why these vehicles?")
    categories = copy.candidate_categories(result.selection.candidates)
    for name, description, count in categories:
        st.markdown(f"- **{name}** ({count}) — {description}")
    with st.expander("Detailed candidate ranking & raw reason codes"):
        st.dataframe(
            pd.DataFrame([
                {"Vehicle": c.description, "Days": c.days_in_inventory,
                 "Risk score": round(c.risk_score, 1),
                 "Reason codes": ", ".join(c.reason_codes)}
                for c in result.selection.candidates
            ]),
            hide_index=True,
            column_config={"Risk score": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100)},
        )


# --- 8. plan comparison ---------------------------------------------------------------


def _plan_comparison(result) -> None:
    promotion = result.promotion_result
    if promotion is None:
        return
    st.subheader("Plan comparison")
    rec = promotion["recommended_plan"]["plan_type"]
    rows = []
    for plan in promotion["plans"]:
        o = plan["outcomes"]
        rows.append({
            "Plan": plan["plan_type"].replace("_", " ").title(),
            "Stance": PLAN_STANCE.get(plan["plan_type"], ""),
            "Vehicles": plan["totals"]["vehicle_count"],
            "Dealer-funded": plan["totals"]["total_dealer_funded"],
            "Incremental (P50)": o["incremental_units_sold"]["p50"],
            "Hits target": o["probability_target_achieved"],
            "Recommended": "★" if plan["plan_type"] == rec else "",
        })
    st.dataframe(
        pd.DataFrame(rows), hide_index=True,
        column_config={
            "Dealer-funded": st.column_config.NumberColumn(format="$%d"),
            "Hits target": st.column_config.NumberColumn(format="%.0f%%"),
        },
    )


# --- 9. warnings and approvals --------------------------------------------------------


def _warnings_and_approvals(result) -> None:
    st.subheader("Warnings and approvals")
    if result.approvals_required:
        by_vehicle: dict[str, list[str]] = {}
        for a in result.approvals_required:
            kind = a.get("approval_type") or a.get("type") or "REVIEW"
            by_vehicle.setdefault(a.get("vehicle_id") or "—", []).append(kind)
        st.dataframe(
            pd.DataFrame([
                {"Vehicle": vid, "Approvals": ", ".join(sorted(set(kinds)))}
                for vid, kinds in by_vehicle.items()
            ]),
            hide_index=True,
        )
    else:
        st.caption("No approvals required.")

    codes = sorted(
        {w["code"] for ev in result.vehicle_evidence for w in ev.warnings}
        | {w["code"] for w in (result.promotion_result or {}).get("warnings", [])}
        | {w["code"] for w in (result.portfolio_result or {}).get("warnings", [])}
    )
    if codes:
        st.caption("Warning codes across the diagnosis, vehicles, and plan: "
                   + ", ".join(f"`{c}`" for c in codes))


# --- 10. five-step workflow summary ---------------------------------------------------


def _five_step_summary(result) -> None:
    st.subheader("How the Agent got here")
    counts = result.skill_invocation_counts
    ran = set(result.execution_order)
    rows = []
    for i, (label, step_name, skill) in enumerate(BUSINESS_STEPS, start=1):
        did_run = step_name in ran
        rows.append({
            "Step": f"{i}. {label}",
            "Status": "Done" if did_run else "Skipped",
            "Skill": skill or "—",
            "Summary": _step_summary(step_name, result, counts),
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True)


def _step_summary(step_name: str, result, counts: dict) -> str:
    d = result.portfolio_summary or {}
    if step_name == "PORTFOLIO_FORECAST":
        return (f"{d.get('current_inventory', '—')} units, "
                f"{_pct(d.get('current_utilization'))} utilized, "
                f"{_pct(d.get('aged_concentration_pct'))} over 90 days")
    if step_name == "CANDIDATE_SELECTION":
        sel = result.selection
        return (f"{len(sel.candidates)} selected, {len(sel.exclusions)} excluded"
                if sel else "—")
    if step_name == "SINGLE_VEHICLE_VALUATION":
        return f"{counts.get('single-vehicle-valuation', 0)} vehicle(s) analysed in depth"
    if step_name == "PROMOTION_PLAN":
        if result.promotion_result:
            return (f"{result.promotion_result['recommended_plan']['plan_type'].replace('_', ' ').title()} "
                    f"recommended · {_pct(d.get('probability_target_achieved'))} likely")
        return "Not run (no event supplied)"
    if step_name == "CONSOLIDATE":
        n = len(result.consolidated_actions)
        return f"{n} vehicle action(s) grouped"
    return "—"


# --- 11. full trace -------------------------------------------------------------------


def _full_trace(result) -> None:
    with st.expander("View full workflow execution trace"):
        st.caption(f"workflow_id `{result.workflow_id}` · type IMPROVE_AGING_INVENTORY")
        st.dataframe(
            pd.DataFrame([
                {"#": t.step_number, "Step": t.step_name, "Skill": t.skill_called or "—",
                 "request_id": t.request_id or "—", "simulation_id": t.simulation_id or "—",
                 "Start": t.start_timestamp, "End": t.end_timestamp,
                 "Status": t.status, "Warnings": len(t.warnings),
                 "Error": t.error or ""}
                for t in result.trace
            ]),
            hide_index=True,
        )
        if result.unavailable:
            st.caption("Unavailable in this run: " + ", ".join(result.unavailable))


# --- 12. disclosure -------------------------------------------------------------------


def _disclosure() -> None:
    st.divider()
    st.info(
        "**Synthetic data · prototype simulation · human review required.** The vehicles and "
        "market data are mocked; forecasts are a configured prototype simulation, not a trained "
        "prediction; every recommendation is a decision-support suggestion that a manager must "
        "review; and **no price is ever published from this application.**",
        icon="ℹ️",
    )
