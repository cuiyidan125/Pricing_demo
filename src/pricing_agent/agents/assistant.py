"""The assistant orchestrator: question in, executed workflow out. Phase 4, no model.

This is the layer that turns *"what should I price the 2020 Ford F-150 XLT?"* into a
resolved vehicle, a single skill invocation, and a concise result — deterministically, from
repository mock data, with no LLM anywhere in the path.

The flow is fixed:

    text → route → (resolve) → invoke one skill → concise summary → response

and the response is one of six honest states. What the orchestrator will **not** do is as
important as what it does:

* It runs at most one skill. Improve Aging, which would coordinate three, returns
  WORKFLOW_NOT_YET_AVAILABLE instead of running anything.
* It generates no numbers. Every figure in a summary is copied straight out of the
  schema-valid skill result; the orchestrator only selects and labels.
* It resolves against real inventory and the real event calendar. An unmatched vehicle is
  NO_MATCH, never a fabricated one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from pricing_agent.agents.resolver import MatchResult, MatchStatus, resolve_vehicle
from pricing_agent.agents.router import RouteResult, route
from pricing_agent.mcp_clients import EventClient, MockTransport, VautoClient
from pricing_agent.policy.warnings import sort_by_severity
from pricing_agent.skills import inventory_portfolio, promotion_planner, single_vehicle
from pricing_agent.workflows.context import WorkflowContext


class AssistantState(str, Enum):
    ROUTED_AND_EXECUTED = "ROUTED_AND_EXECUTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NO_MATCH = "NO_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    WORKFLOW_NOT_YET_AVAILABLE = "WORKFLOW_NOT_YET_AVAILABLE"
    EXECUTION_ERROR = "EXECUTION_ERROR"


# The workflow the dealer opens to see the full analysis behind a summary.
WORKFLOW_URL: dict[WorkflowContext, str] = {
    WorkflowContext.PRICE_INVENTORY: "price-inventory",
    WorkflowContext.ACQUIRE_INVENTORY: "acquire-inventory",
    WorkflowContext.MERCHANDISE_INVENTORY: "merchandise-inventory",
    WorkflowContext.IMPROVE_AGING_INVENTORY: "improve-aging-inventory",
}


@dataclass(frozen=True)
class AssistantResponse:
    state: AssistantState
    message: str
    route: RouteResult
    workflow: WorkflowContext | None = None
    skill: str | None = None
    resolved_vehicle_id: str | None = None
    match: MatchResult | None = None
    candidates: tuple[dict, ...] = ()
    summary: dict = field(default_factory=dict)
    warnings: tuple[dict, ...] = ()
    result: dict | None = None
    target_url: str | None = None

    @property
    def executed(self) -> bool:
        return self.state is AssistantState.ROUTED_AND_EXECUTED


# --- event resolution for the promotion workflow --------------------------------------

_PERCENT = re.compile(r"(\d{1,3})\s*(?:%|percent)")

# Holiday phrases that identify an event by its date, with a representative (month, day).
# A holiday matches an event only when that date falls inside the event's window — so
# "July 4th" does not silently become a late-July clearance sale that happens to share the
# month. Being wrong about which event the dealer meant is worse than asking.
_HOLIDAYS: tuple[tuple[re.Pattern[str], tuple[int, int]], ...] = (
    (re.compile(r"july\s*4|fourth\s*of\s*july|independence"), (7, 4)),
    (re.compile(r"memorial\s*day"), (5, 25)),
    (re.compile(r"labor\s*day"), (9, 7)),
    (re.compile(r"black\s*friday"), (11, 27)),
    (re.compile(r"president'?s?\s*day"), (2, 16)),
)


def parse_target_utilization(text: str, default: float = 0.70) -> float:
    """A percentage from the text, or the conventional 70% target when none is stated."""
    if match := _PERCENT.search(text):
        value = int(match.group(1))
        if 0 < value <= 100:
            return value / 100.0
    return default


def resolve_event(text: str, events: list[dict]) -> dict | None:
    """Match a named or dated event against the calendar. No fuzzy guessing.

    Name match first (the dealer said "Summer Clearance"), then a holiday whose month lands
    inside an event window. Returns the calendar record or `None` — and `None` is a real
    answer: it drives a clarification that lists what events exist, never a fabricated one.
    """
    lowered = text.lower()

    for event in events:
        name = event.get("event_name", "")
        # Every significant word of the event name present in the request.
        words = [w for w in re.split(r"\W+", name.lower()) if len(w) > 2]
        if words and all(w in lowered for w in words):
            return event

    for pattern, (month, day) in _HOLIDAYS:
        if pattern.search(lowered):
            for event in events:
                if _within_window(event, month, day):
                    return event
    return None


def _within_window(event: dict, month: int, day: int) -> bool:
    """Whether (month, day) falls inside the event's [start_date, end_date], year-agnostic."""
    try:
        start = date.fromisoformat(event["start_date"])
        end = date.fromisoformat(event["end_date"])
    except (KeyError, ValueError):
        return False
    holiday = (month, day)
    return (start.month, start.day) <= holiday <= (end.month, end.day)


# --- summaries (selection only; every value is copied from the skill result) -----------


def _pricing_summary(result: dict) -> dict:
    strategy = result["recommended_strategy"]["strategy"]
    scenario = next(s for s in result["pricing_scenarios"] if s["strategy"] == strategy)
    return {
        "vehicle": result["vehicle"]["description"]
        if "description" in result["vehicle"]
        else f"{result['vehicle']['year']} {result['vehicle']['make']} "
        f"{result['vehicle']['model']} {result['vehicle']['trim']}".strip(),
        "current_list_price": result["vehicle"]["current_list_price"],
        "recommended_price": scenario["proposed_list_price"],
        "p50_days_to_sale": scenario["additional_days_to_sale"]["p50"],
        "p90_days_to_sale": scenario["additional_days_to_sale"]["p90"],
        "break_even_price": result["break_even_analysis"]["current_accounting_break_even"],
        "promotional_headroom": result["promotional_headroom"]["max_safe_discount"],
        "strategy": strategy,
    }


def _portfolio_summary(result: dict) -> dict:
    capacity = result["capacity_position"]
    valuation = result["portfolio_valuation"]
    one_month = result["one_month_forecast"]
    return {
        "units_on_lot": capacity["current_inventory"],
        "open_slots": capacity["physical_open_slots"],
        "utilization": capacity["current_utilization"],
        "units_below_break_even": result["financial_risk"]["units_below_break_even"],
        "cash_tied_up": valuation["cash_tied_up"],
        "thirty_day_units_p50": one_month["unit_sales"]["p50"],
        "thirty_day_units_p10": one_month["unit_sales"]["p10"],
        "thirty_day_units_p90": one_month["unit_sales"]["p90"],
    }


def _promotion_summary(result: dict, event: dict) -> dict:
    feasibility = result["feasibility"]
    target_block = result["inventory_target_calculation"]
    return {
        "event_name": event["event_name"],
        "feasibility_status": feasibility["status"],
        "target_ending_inventory": target_block["target_ending_inventory"],
        "incremental_required": target_block["incremental_promotional_sales_required"],
        "probability_target_achieved": feasibility["probability_target_achieved"],
        "recommended_plan": result["recommended_plan"]["plan_type"],
    }


def _top_warnings(result: dict, limit: int = 3) -> tuple[dict, ...]:
    return tuple(sort_by_severity(list(result.get("warnings", [])))[:limit])


# --- orchestration --------------------------------------------------------------------


def run_assistant(text: str, *, as_of: datetime) -> AssistantResponse:
    """Route, resolve, and execute a single supported workflow for `text`."""
    routed = route(text)
    workflow = routed.selected_workflow

    if workflow is None:
        return AssistantResponse(
            state=AssistantState.NEEDS_CLARIFICATION,
            message=(
                "I could not tell which decision this is about. Try naming a vehicle to "
                "price, asking what the lot will do over the next 30 days, or describing a "
                "sale event."
            ),
            route=routed,
        )

    if workflow is WorkflowContext.IMPROVE_AGING_INVENTORY:
        return AssistantResponse(
            state=AssistantState.WORKFLOW_NOT_YET_AVAILABLE,
            message=(
                "Improving aging inventory coordinates all three skills — forecast, "
                "single-vehicle pricing, and promotion planning — and that orchestration is "
                "not connected yet. In the meantime, open Improve Aging Inventory to see "
                "the sequence, or ask me to price one aged vehicle."
            ),
            route=routed,
            workflow=workflow,
            target_url=WORKFLOW_URL[workflow],
        )

    try:
        if workflow is WorkflowContext.PRICE_INVENTORY:
            return _run_pricing(text, routed, as_of=as_of)
        if workflow is WorkflowContext.ACQUIRE_INVENTORY:
            return _run_portfolio(routed, as_of=as_of)
        if workflow is WorkflowContext.MERCHANDISE_INVENTORY:
            return _run_promotion(text, routed, as_of=as_of)
    except Exception as error:  # noqa: BLE001 — surfaced as a state, never swallowed
        return AssistantResponse(
            state=AssistantState.EXECUTION_ERROR,
            message=(
                "The workflow was identified, but the analysis did not complete. Open the "
                f"workflow directly to retry. ({type(error).__name__})"
            ),
            route=routed,
            workflow=workflow,
            skill=routed.required_skill,
            target_url=WORKFLOW_URL.get(workflow),
        )

    # Unreachable: every non-None workflow is handled above.
    return AssistantResponse(
        state=AssistantState.NEEDS_CLARIFICATION,
        message="This request is not supported yet.",
        route=routed,
        workflow=workflow,
    )


def _run_pricing(text: str, routed: RouteResult, *, as_of: datetime) -> AssistantResponse:
    parsed = routed.parsed_vehicle
    url = WORKFLOW_URL[WorkflowContext.PRICE_INVENTORY]

    if parsed is None or not routed.execution_allowed:
        return AssistantResponse(
            state=AssistantState.NEEDS_CLARIFICATION,
            message=(
                "Which vehicle do you want to analyze? Select a vehicle or provide year, "
                "make, model, and trim."
            ),
            route=routed,
            workflow=WorkflowContext.PRICE_INVENTORY,
            skill=routed.required_skill,
            target_url=url,
        )

    transport = MockTransport(as_of=as_of)
    inventory = VautoClient(transport).get_dealer_inventory().data
    match = resolve_vehicle(parsed, inventory)

    if match.status is MatchStatus.EXACT:
        result = single_vehicle.analyze(match.vehicle_id, transport, input_text=text)
        return AssistantResponse(
            state=AssistantState.ROUTED_AND_EXECUTED,
            message=f"Priced {match.vehicle_id} with the single-vehicle valuation skill.",
            route=routed,
            workflow=WorkflowContext.PRICE_INVENTORY,
            skill=routed.required_skill,
            resolved_vehicle_id=match.vehicle_id,
            match=match,
            summary=_pricing_summary(result),
            warnings=_top_warnings(result),
            result=result,
            target_url=url,
        )

    if match.status is MatchStatus.AMBIGUOUS:
        return AssistantResponse(
            state=AssistantState.AMBIGUOUS_MATCH,
            message=(
                "More than one vehicle matches that description. Which one did you mean?"
            ),
            route=routed,
            workflow=WorkflowContext.PRICE_INVENTORY,
            skill=routed.required_skill,
            match=match,
            candidates=match.candidates,
            target_url=url,
        )

    if match.status is MatchStatus.NONE:
        return AssistantResponse(
            state=AssistantState.NO_MATCH,
            message=(
                "No vehicle in the current inventory matches that description. This "
                "prototype analyzes vehicles already in dealer inventory, so it will not "
                "invent one. Check the details, or pick a vehicle from Price Inventory."
            ),
            route=routed,
            workflow=WorkflowContext.PRICE_INVENTORY,
            skill=routed.required_skill,
            match=match,
            target_url=url,
        )

    # INSUFFICIENT
    return AssistantResponse(
        state=AssistantState.NEEDS_CLARIFICATION,
        message=(
            "Which vehicle do you want to analyze? Select a vehicle or provide year, make, "
            "model, and trim."
        ),
        route=routed,
        workflow=WorkflowContext.PRICE_INVENTORY,
        skill=routed.required_skill,
        match=match,
        target_url=url,
    )


def _run_portfolio(routed: RouteResult, *, as_of: datetime) -> AssistantResponse:
    transport = MockTransport(as_of=as_of)
    result = inventory_portfolio.analyze(transport)
    return AssistantResponse(
        state=AssistantState.ROUTED_AND_EXECUTED,
        message="Ran the portfolio forecast for acquisition readiness and capacity.",
        route=routed,
        workflow=WorkflowContext.ACQUIRE_INVENTORY,
        skill=routed.required_skill,
        summary=_portfolio_summary(result),
        warnings=_top_warnings(result),
        result=result,
        target_url=WORKFLOW_URL[WorkflowContext.ACQUIRE_INVENTORY],
    )


def _run_promotion(text: str, routed: RouteResult, *, as_of: datetime) -> AssistantResponse:
    transport = MockTransport(as_of=as_of)
    url = WORKFLOW_URL[WorkflowContext.MERCHANDISE_INVENTORY]
    events = EventClient(transport).get_sales_event_calendar().data
    event = resolve_event(text, events)

    if event is None:
        names = ", ".join(e["event_name"] for e in events) or "none on the calendar"
        return AssistantResponse(
            state=AssistantState.NEEDS_CLARIFICATION,
            message=(
                "Which event should I plan for? I could not match one on the calendar. "
                f"Available events: {names}. Name one, and I'll build the plan."
            ),
            route=routed,
            workflow=WorkflowContext.MERCHANDISE_INVENTORY,
            skill=routed.required_skill,
            target_url=url,
        )

    target = parse_target_utilization(text)
    result = promotion_planner.plan_event(
        transport, event["event_id"], target, input_text=text
    )
    return AssistantResponse(
        state=AssistantState.ROUTED_AND_EXECUTED,
        message=f"Planned the {event['event_name']} event with the promotion planner.",
        route=routed,
        workflow=WorkflowContext.MERCHANDISE_INVENTORY,
        skill=routed.required_skill,
        summary=_promotion_summary(result, event),
        warnings=_top_warnings(result),
        result=result,
        target_url=url,
    )
