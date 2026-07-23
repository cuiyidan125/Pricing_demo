"""Deterministic follow-up classification and handling for the Dealer AI Assistant.

After the first grounded answer, the dealer asks follow-ups against the *same* structured result.
This module decides — with rules, never the LLM — which of five things a follow-up is, and
produces a grounded reply:

    E  unsupported / unavailable   → say so; invent nothing; never publish
    D  workflow rerun              → validated new input; re-run the deterministic workflow
    C  clarification               → one concise question for the missing input
    B  filter existing result      → select existing rows; no rerun
    A  explain existing result     → explain from existing fields; no rerun, no new number

Order matters: unsupported and rerun are tested before answering, so "use Summer Clearance" or
"publish the price" can never be mistaken for a question about the current result. Every value in
a reply is copied from the active result; nothing here computes a price, a percentile, or a
probability, and a rerun keeps the previous valid result until the new one succeeds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime

from pricing_agent.agents.aging_answer import IMMEDIATE_ACTIONS, build_aging_answer
from pricing_agent.agents.assistant import (
    parse_explicit_target,
    resolve_event,
    wrap_improve_aging,
)
from pricing_agent.agents.conversation import (
    SOURCE_CLARIFICATION,
    SOURCE_ERROR,
    SOURCE_EXPLANATION,
    SOURCE_FILTERED,
    SOURCE_RERUN,
    SOURCE_UNSUPPORTED,
    ConversationState,
    VehicleRef,
    resolve_reference,
    vehicle_index,
)
from pricing_agent.mcp_clients import EventClient, MockTransport
from pricing_agent.workflows.improve_aging import WorkflowState, run_improve_aging

# --- signals --------------------------------------------------------------------------

# Data the prototype does not have, or actions it must never take. Checked first so none of these
# can be read as a question about the current result.
_UNSUPPORTED = re.compile(
    r"\b(vdp|vdp views?|page views?|shopper|shoppers|leads?|lead conversion|conversion rate|"
    r"click[\s-]?through|live market|market supply|days[\s-]?supply|inventory turn rate|"
    r"web traffic|test drives?|publish|push the price|go live)\b", re.IGNORECASE)

_EVENT_REFERENCE = re.compile(
    r"\b(event|promotion|promo|campaign|clearance|sale|labor\s*day|memorial\s*day|"
    r"black\s*friday|holiday|summer)\b", re.IGNORECASE)

_EXCLUDE = re.compile(
    r"\b(exclude|remove|drop|protect|hold|keep|don'?t\s+(?:promote|discount|touch)|"
    r"leave\s+(?:out|alone))\b", re.IGNORECASE)

_WHY = re.compile(r"\bwhy\b", re.IGNORECASE)

# Filter vocabulary → (dealer label, predicate over a VehicleRef). Analysed vehicles only.
_FILTERS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"over\s*90|past\s*90|already.*90|90\s*days?\b|120\s*days?\b", re.I),
     "already over 90 days on lot",
     "over_90"),
    (re.compile(r"wholesale", re.I), "flagged for wholesale / loss-minimization review", "wholesale"),
    (re.compile(r"manager[\s-]?review", re.I), "assigned to manager review", "manager_review"),
    (re.compile(r"safe\s+promotional\s+room|promotional\s+room|discount\s+room|safe\s+headroom", re.I),
     "have safe promotional room", "safe_room"),
    (re.compile(r"depreciation", re.I), "carry high depreciation risk", "depreciation"),
    (re.compile(r"inbound|replacement\s+pressure", re.I),
     "face inbound replacement pressure", "inbound"),
    (re.compile(r"below\s+break[\s-]?even|underwater|under\s+water", re.I),
     "are priced below break-even", "below_break_even"),
    (re.compile(r"require\s+review|need\s+review|needs?\s+a?\s*(?:manager\s+)?review|"
                r"require\s+a?\s*manager", re.I),
     "require review before any pricing action", "requires_review"),
    (re.compile(r"no[\s-]?immediate|don'?t\s+need\s+(?:immediate\s+)?action|"
                r"not\s+need\s+immediate", re.I),
     "do not need immediate action", "no_immediate"),
)


def _predicate(key: str):
    over90 = {"CURRENTLY_OVER_90_DAYS", "CURRENTLY_OVER_120_DAYS"}
    return {
        "over_90": lambda r: bool(set(r.reason_codes) & over90),
        "wholesale": lambda r: r.action_code == "WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW",
        "manager_review": lambda r: r.action_code == "MANAGER_REVIEW",
        "safe_room": lambda r: "HIGH_SAFE_PROMOTIONAL_HEADROOM" in r.reason_codes,
        "depreciation": lambda r: "HIGH_DEPRECIATION_RISK" in r.reason_codes,
        "inbound": lambda r: "INBOUND_REPLACEMENT_PRESSURE" in r.reason_codes,
        "below_break_even": lambda r: "BELOW_PROJECTED_BREAK_EVEN" in r.approvals,
        "requires_review": lambda r: bool(r.approvals),
        "no_immediate": lambda r: r.analysed and r.action_code not in IMMEDIATE_ACTIONS,
    }[key]


# --- result -----------------------------------------------------------------------


@dataclass(frozen=True)
class FollowupResult:
    kind: str
    text: str
    referenced_ids: tuple[str, ...] = ()
    reran: bool = False
    success: bool = True
    response: object | None = None      # a new AssistantResponse when a rerun succeeded


# --- entry point ------------------------------------------------------------------


def handle_followup(text: str, state: ConversationState, *, as_of: datetime) -> FollowupResult:
    """Classify and answer a follow-up, mutating `state` (history, and active result on a rerun).

    On a successful rerun the previous result is preserved in `previous_valid_result` and the new
    one is adopted; on any failure the previous active result is left untouched.
    """
    state.add_user(text)

    if not state.has_active_result:
        result = FollowupResult(
            SOURCE_ERROR,
            "I don't have an analysis to work from yet. Ask an aging question first — for "
            "example, \"Which aging vehicles should I promote?\"", success=False)
        return _record(state, result)

    handlers = (_unsupported, _rerun, _clarification, _filter, _explain)
    for handler in handlers:
        result = handler(text, state, as_of)
        if result is not None:
            return _record(state, result)
    return _record(state, _fallback(state))


def _record(state: ConversationState, result: FollowupResult) -> FollowupResult:
    """Append the assistant turn and update reference memory / active result."""
    if result.referenced_ids:
        state.last_referenced_vehicle_ids = result.referenced_ids
    if result.reran and result.success and result.response is not None:
        state.previous_valid_result = state.active_result
        state.adopt(result.response)
        state.rerun_count += 1
        state.pending_clarification = None
        state.add_assistant(result.text, SOURCE_RERUN, result=state.active_result,
                            response=result.response, referenced=result.referenced_ids,
                            workflow_id=state.active_workflow_id)
        return result
    if result.kind == SOURCE_CLARIFICATION:
        state.pending_clarification = result.text
    else:
        state.pending_clarification = None
    state.add_assistant(result.text, result.kind, referenced=result.referenced_ids,
                        workflow_id=state.active_workflow_id)
    return result


# --- E. unsupported / unavailable -------------------------------------------------


def _unsupported(text: str, state: ConversationState, as_of: datetime) -> FollowupResult | None:
    if not _UNSUPPORTED.search(text):
        return None
    if re.search(r"\bpublish|push the price|go live\b", text, re.IGNORECASE):
        return FollowupResult(
            SOURCE_UNSUPPORTED,
            "This prototype never publishes a price — every recommendation is decision support "
            "for a manager to act on. I can't push a price live.")
    return FollowupResult(
        SOURCE_UNSUPPORTED,
        "That relies on data this prototype doesn't have — shopper views, lead conversion, and "
        "live market supply aren't part of the analysis. I won't invent it. I can explain the "
        "vehicles, their prices, days on lot, break-even, and review conditions from the "
        "current result.")


# --- D. workflow rerun ------------------------------------------------------------


def _rerun(text: str, state: ConversationState, as_of: datetime) -> FollowupResult | None:
    event = _resolved_event(text, as_of)
    if event is not None and event["event_name"] == state.active_event:
        event = None    # already the active event — not a rerun
    target = parse_explicit_target(text)
    exclude_ids: tuple[str, ...] = ()
    if _EXCLUDE.search(text):
        ref = resolve_reference(text, state)
        if ref.ambiguous:
            return _ambiguous(ref)
        exclude_ids = ref.ids

    if event is None and target is None and not exclude_ids:
        return None

    base = state.active_result.request
    kwargs: dict = {}
    changed: list[str] = []
    if event is not None:
        kwargs.update(event_requested=True, event_id=event["event_id"],
                      event_name=event["event_name"])
        changed.append(f"added the {event['event_name']} event")
    if target is not None:
        kwargs.update(target_utilization=target)
        changed.append(f"set the target to {target:.0%}")
    if exclude_ids:
        merged = tuple(dict.fromkeys(base.excluded_vehicle_ids + exclude_ids))
        kwargs.update(excluded_vehicle_ids=merged)
        index = vehicle_index(state.active_result)
        names = ", ".join(index[i].description for i in exclude_ids if i in index)
        changed.append(f"protected {names}")

    new_request = replace(base, **kwargs)
    status = "Re-running the Improve Aging analysis — " + "; ".join(changed) + "."

    try:
        new_result = run_improve_aging(MockTransport(as_of=as_of), new_request)
    except Exception as error:  # noqa: BLE001 — a rerun must degrade, never overwrite
        return FollowupResult(
            SOURCE_ERROR,
            f"{status}\n\nThe re-run did not complete ({type(error).__name__}), so I've kept the "
            "previous analysis. Nothing changed.", success=False)

    if new_result.state is WorkflowState.EXECUTION_ERROR:
        return FollowupResult(
            SOURCE_ERROR,
            f"{status}\n\nThe re-run could not complete, so I've kept the previous analysis.",
            success=False)

    routed = getattr(state.active_response, "route", None)
    new_response = wrap_improve_aging(new_result, routed, message=new_result.message)
    text_out = _rerun_summary(status, state, new_result, new_response)
    return FollowupResult(SOURCE_RERUN, text_out, reran=True, success=True, response=new_response)


def _resolved_event(text: str, as_of: datetime) -> dict | None:
    if not _EVENT_REFERENCE.search(text):
        return None
    events = EventClient(MockTransport(as_of=as_of)).get_sales_event_calendar().data or []
    return resolve_event(text, events)


def _rerun_summary(status: str, state: ConversationState, new_result, new_response) -> str:
    """A what-changed summary built only from existing fields of the old and new results."""
    answer = build_aging_answer(new_result, workspace_url=new_response.target_url)
    lines = [status, "", answer.understood]
    block = answer.event_block
    if block and block.promoted:
        promoted = ", ".join(v.description for v in block.promoted)
        lines.append(f"Recommended for the {block.event_name} event: {promoted}.")
        if block.probability_target_achieved is not None:
            plan_note = ""
            if block.recommended_plan:
                plan_note = f" ({block.recommended_plan.replace('_', ' ').title()} plan)"
            lines.append(
                f"Target likelihood: reaches the target "
                f"{block.probability_target_achieved:.0%} of the time{plan_note}.")
    else:
        lines.append(f"{answer.immediate_count} need immediate action; "
                     f"{answer.no_immediate_count} have no immediate action.")
    if answer.review_vehicle_count:
        lines.append(f"{answer.review_vehicle_count} vehicles require review before pricing "
                     "changes.")
    lines.append("_The previous analysis is preserved; details are in the full workspace._")
    return "\n\n".join(lines)


# --- C. clarification -------------------------------------------------------------


def _clarification(text: str, state: ConversationState, as_of: datetime) -> FollowupResult | None:
    lowered = text.lower()
    # A rerun-shaped ask with no resolvable input reaches here (rerun already consumed the
    # resolvable cases).
    if re.search(r"\bpromote(\s+them| all)?\b|in the event|use the event|the sale event", lowered):
        events = EventClient(MockTransport(as_of=as_of)).get_sales_event_calendar().data or []
        names = ", ".join(e["event_name"] for e in events) or "none on the calendar"
        return FollowupResult(
            SOURCE_CLARIFICATION,
            f"Which sale event should I plan for? I won't assume one. Available: {names}.")
    if re.search(r"\btarget\b|\butilization\b|\blower\b|\braise\b", lowered) \
            and parse_explicit_target(text) is None:
        return FollowupResult(
            SOURCE_CLARIFICATION,
            "What utilization target should I use? Name a percentage, e.g. \"set the target to "
            "70%\".")
    if re.search(r"\bthat vehicle\b|\bthis one\b|\bit\b", lowered) \
            and not resolve_reference(text, state).ids:
        return FollowupResult(
            SOURCE_CLARIFICATION,
            "Which vehicle do you mean? Name it — for example \"the BMW\" or a vehicle id.")
    return None


# --- B. filter --------------------------------------------------------------------


def _filter(text: str, state: ConversationState, as_of: datetime) -> FollowupResult | None:
    # An explicit "why … <vehicle>" is an explanation, not a filter — defer to _explain.
    ref = resolve_reference(text, state)
    if _WHY.search(text) and (ref.ids or ref.ambiguous):
        return None
    match = next((f for f in _FILTERS if f[0].search(text)), None)
    if match is None:
        return None
    _pat, label, key = match
    index = vehicle_index(state.active_result)
    predicate = _predicate(key)
    rows = [r for r in index.values() if r.analysed and predicate(r)]
    if not rows:
        return FollowupResult(SOURCE_FILTERED,
                              f"No analysed vehicle in this result {label}.")
    listing = "\n".join(f"- {r.description}" for r in rows)
    header = (f"{_count_word(len(rows)).capitalize()} analysed "
              f"vehicle{'s' if len(rows) != 1 else ''} {label}:")
    return FollowupResult(SOURCE_FILTERED, f"{header}\n\n{listing}",
                          referenced_ids=tuple(r.vehicle_id for r in rows))


# --- A. explain -------------------------------------------------------------------


def _explain(text: str, state: ConversationState, as_of: datetime) -> FollowupResult | None:
    ref = resolve_reference(text, state)
    if ref.ambiguous:
        return _ambiguous(ref)
    if not ref.ids:
        if _WHY.search(text):
            return FollowupResult(
                SOURCE_CLARIFICATION,
                "Which vehicle do you mean? Name it — for example \"the BMW\" or a vehicle id.")
        return None
    index = vehicle_index(state.active_result)
    paragraphs = [_explain_vehicle(index[i]) for i in ref.ids if i in index]
    return FollowupResult(SOURCE_EXPLANATION, "\n\n".join(paragraphs),
                          referenced_ids=ref.ids)


def _explain_vehicle(ref: VehicleRef) -> str:
    from pricing_agent.views import improve_aging_copy as copy
    from pricing_agent.views import terminology as T

    immediate = ref.action_code in IMMEDIATE_ACTIONS
    action = copy.action_label(ref.action_code) if immediate else "no immediate action"
    reasons = "; ".join(copy.selection_label(c) for c in ref.reason_codes)
    lines = [f"**{ref.description}** — {action}."]
    if reasons:
        lines.append(f"Selected because: {reasons}.")

    res = ref.result or {}
    veh = res.get("vehicle", {})
    be = res.get("break_even_analysis", {})
    strat = res.get("recommended_strategy", {}).get("strategy")
    scen = next((s for s in res.get("pricing_scenarios", []) if s["strategy"] == strat), {})
    days_add = scen.get("additional_days_to_sale", {})
    facts: list[str] = []
    if veh.get("days_in_inventory") is not None:
        facts.append(f"{int(veh['days_in_inventory'])} days on the lot")
    if ref.current_price is not None:
        facts.append(f"asking ${ref.current_price:,.0f}")
    if be.get("current_accounting_break_even") is not None:
        facts.append(f"break-even ${be['current_accounting_break_even']:,.0f}")
    if days_add.get("p50") is not None and days_add.get("p90") is not None:
        facts.append(f"expected {days_add['p50']:.0f} days to sell (P50), "
                     f"{days_add['p90']:.0f} in the conservative case (P90)")
    if facts:
        lines.append(_capitalize(" · ".join(facts)) + ".")

    proposed = scen.get("proposed_list_price")
    min_safe = be.get("minimum_safe_list_price")
    if isinstance(proposed, (int, float)) and isinstance(min_safe, (int, float)) \
            and proposed < min_safe:
        lines.append(f"The proposed price ${proposed:,.0f} is below the lowest safe asking price "
                     f"${min_safe:,.0f} — that price floor is why it needs a manager review.")

    if ref.approvals:
        whys = list(dict.fromkeys(T.approval_why(a) for a in ref.approvals))
        lines.append("Review conditions before repricing: " + "; ".join(whys) + ".")
    return " ".join(lines)


# --- helpers ----------------------------------------------------------------------


def _ambiguous(ref) -> FollowupResult:
    options = ref.label
    return FollowupResult(
        SOURCE_CLARIFICATION,
        f"That matches more than one vehicle — {options}. Which one did you mean?",
        referenced_ids=ref.ids)


def _fallback(state: ConversationState) -> FollowupResult:
    return FollowupResult(
        SOURCE_CLARIFICATION,
        "I can explain a vehicle (\"why is the BMW recommended for wholesale?\"), filter the "
        "list (\"show only vehicles over 90 days\"), or re-run with a change (\"use Summer "
        "Clearance\", \"set the target to 70%\"). What would you like?")


_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _count_word(n: int) -> str:
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def _capitalize(s: str) -> str:
    return s[0].upper() + s[1:] if s else s
