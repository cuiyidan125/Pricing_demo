"""Grounded direct answer for an Improve Aging result — conversational layer, no calculation.

This turns a finished `ImproveAgingResult` into a structured `DirectAnswer` the Assistant can
speak *in the conversation*: how many aging vehicles were analysed, which need immediate action
(each with a concise reason built only from the reason codes the workflow already produced),
which do not, and — when no event is selected — a clear statement that promotion eligibility is
not finalized.

Every field is copied or selected from the result. Nothing here computes a price, a percentile,
a probability, or a count that the workflow did not already decide, and the vehicle list is never
hard-coded — it is read from `consolidated_actions` / `vehicle_evidence`. The view renders this
object; it does not assemble vehicle strings itself.
"""

from __future__ import annotations

from dataclasses import dataclass


def _copy():
    """The dealer reason/action copy, imported lazily.

    aging_answer lives in `agents/`, but the reason-code → dealer-label maps live in `views/`.
    Importing that module at load time would drag the whole `views` package into the `agents`
    package initialisation and form an import cycle (views.assistant_home and .vehicle_detail
    import from `agents`). By the time any function here runs, both packages are fully loaded,
    so a call-time import is safe and cycle-free.
    """
    from pricing_agent.views import improve_aging_copy
    return improve_aging_copy


# Actions that ask the dealer to do something now. A display grouping of the classification the
# workflow already made — NO_ACTION / PROTECT_PRICE mean "no immediate action". Kept in step with
# the same set in views/improve_aging.py and agents/assistant.py.
IMMEDIATE_ACTIONS = frozenset({
    "REPRICE_NOW", "EVENT_PROMOTION", "MANAGER_REVIEW",
    "WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW",
})


@dataclass(frozen=True)
class VehicleLine:
    """One vehicle as the conversation should name it — all fields from the result."""
    vehicle_id: str
    description: str
    action_code: str
    action_label: str
    reason: str
    needs_review: bool


@dataclass(frozen=True)
class EventBlock:
    """The extra distinctions a selected event makes visible. Only populated when an event ran."""
    event_name: str | None
    promoted: tuple[VehicleLine, ...]
    analysed_not_selected: tuple[VehicleLine, ...]
    protected_or_excluded: tuple[VehicleLine, ...]
    target_status: str | None
    probability_target_achieved: float | None
    recommended_plan: str | None


@dataclass(frozen=True)
class DirectAnswer:
    understood: str
    analysed_count: int
    immediate_count: int
    no_immediate_count: int
    immediate: tuple[VehicleLine, ...]
    no_immediate: tuple[VehicleLine, ...]
    event_selected: bool
    promotion_finalized: bool
    promotion_note: str
    review_vehicle_count: int          # 5 — the default dealer-facing review count
    manager_review_count: int          # 2 — vehicles whose final action is MANAGER_REVIEW
    review_item_count: int             # 17 — raw records, audit only (never in the default text)
    key_review_note: str
    event_block: EventBlock | None
    suggested_followups: tuple[str, ...]
    workspace_url: str | None


def _plural(n: int, singular: str = "vehicle") -> str:
    return f"{n} {singular}" if n == 1 else f"{n} {singular}s"


def vehicle_reason(reason_codes: tuple[str, ...] | list[str]) -> str:
    """A concise dealer reason built from the top one or two existing reason codes.

    No new fact is introduced: each phrase is the dealer label for a code the candidate selection
    already recorded. The codes are already salience-ordered, so the first two carry the answer.
    """
    copy = _copy()
    labels = [copy.selection_label(c) for c in list(reason_codes)[:2]]
    if not labels:
        return ""
    # Lead lower-case so the phrase reads inside a sentence ("Reason: already over 90 days …").
    parts = [(label[0].lower() + label[1:]) if label else label for label in labels]
    return " and ".join(parts)


def _line(action: dict) -> VehicleLine:
    code = action["recommended_action"]
    immediate = code in IMMEDIATE_ACTIONS
    return VehicleLine(
        vehicle_id=action["vehicle_id"],
        description=action["description"],
        action_code=code,
        action_label=(_copy().action_label(code) if immediate
                      else "No immediate action — potential sale-event candidate"),
        reason=vehicle_reason(tuple(action.get("reason_codes", ()))),
        needs_review=bool(action.get("approvals_required")),
    )


def build_aging_answer(result, *, workspace_url: str | None = None) -> DirectAnswer | None:
    """Build the grounded `DirectAnswer` from an `ImproveAgingResult`, or None if unavailable."""
    if result is None or not getattr(result, "vehicle_evidence", None):
        return None

    analysed_ids = [e.vehicle_id for e in result.vehicle_evidence]
    analysed = set(analysed_ids)
    action_by_id = {a["vehicle_id"]: a for a in result.consolidated_actions}

    # Preserve the workflow's own attention order (the order of vehicle_evidence).
    immediate: list[VehicleLine] = []
    no_immediate: list[VehicleLine] = []
    for vid in analysed_ids:
        a = action_by_id.get(vid)
        if a is None:
            continue
        line = _line(a)
        (immediate if a["recommended_action"] in IMMEDIATE_ACTIONS else no_immediate).append(line)

    review_vehicle_ids = {a.get("vehicle_id") for a in result.approvals_required if a.get("vehicle_id")}
    manager_review_count = sum(
        1 for a in result.consolidated_actions if a["recommended_action"] == "MANAGER_REVIEW"
    )
    review_vehicle_count = len(review_vehicle_ids)

    event_selected = result.promotion_result is not None
    promotion_finalized = event_selected
    if event_selected:
        promotion_note = (
            f"The {result.request.event_name} plan determines which vehicles are included."
        )
    else:
        promotion_note = "No event is selected, so promotion eligibility is not finalized."

    key_review_note = (
        f"{_plural(review_vehicle_count)} require review before any pricing action."
        if review_vehicle_count else "No vehicle needs a manager review."
    )

    understood = f"I analysed {_plural(len(analysed_ids))}."

    return DirectAnswer(
        understood=understood,
        analysed_count=len(analysed_ids),
        immediate_count=len(immediate),
        no_immediate_count=len(no_immediate),
        immediate=tuple(immediate),
        no_immediate=tuple(no_immediate),
        event_selected=event_selected,
        promotion_finalized=promotion_finalized,
        promotion_note=promotion_note,
        review_vehicle_count=review_vehicle_count,
        manager_review_count=manager_review_count,
        review_item_count=len(result.approvals_required),
        key_review_note=key_review_note,
        event_block=_event_block(result, analysed) if event_selected else None,
        suggested_followups=_suggested_followups(immediate, event_selected),
        workspace_url=workspace_url,
    )


def _event_block(result, analysed: set[str]) -> EventBlock:
    copy = _copy()
    action_by_id = {a["vehicle_id"]: a for a in result.consolidated_actions}
    promoted = tuple(
        _line(a) for vid in analysed
        if (a := action_by_id.get(vid)) and a["recommended_action"] == "EVENT_PROMOTION"
    )
    not_selected = tuple(
        _line(a) for vid in analysed
        if (a := action_by_id.get(vid))
        and a["recommended_action"] not in IMMEDIATE_ACTIONS
    )
    excluded = tuple(
        VehicleLine(
            vehicle_id=e.vehicle_id, description=e.description,
            action_code="PROTECT_OR_EXCLUDE",
            action_label=copy.exclusion_category(e.reason_codes),
            reason="; ".join(copy.exclusion_label(c) for c in e.reason_codes),
            needs_review=False,
        )
        for e in (result.selection.exclusions if result.selection else ())
    )
    promotion = result.promotion_result or {}
    feasibility = promotion.get("feasibility", {})
    return EventBlock(
        event_name=result.request.event_name,
        promoted=promoted,
        analysed_not_selected=not_selected,
        protected_or_excluded=excluded,
        target_status=feasibility.get("status"),
        probability_target_achieved=result.portfolio_summary.get("probability_target_achieved"),
        recommended_plan=(promotion.get("recommended_plan") or {}).get("plan_type"),
    )


def _suggested_followups(immediate: list[VehicleLine], event_selected: bool) -> tuple[str, ...]:
    """Dealer-friendly next questions. Rendered as copyable suggestions until the follow-up
    engine lands; each is grounded in a vehicle or action actually present in this result."""
    out: list[str] = []
    wholesale = next(
        (v for v in immediate if v.action_code == "WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW"), None
    )
    if wholesale:
        out.append(f"Why is the {_make(wholesale.description)} recommended for wholesale?")
    out.append("Which vehicles have safe promotional room?")
    out.append("Show only vehicles over 90 days")
    if not event_selected:
        out.append("Use Summer Clearance")
    out.append("Open the full evidence workspace")
    return tuple(out)


def _make(description: str) -> str:
    """The make from a '2018 BMW 540i BASE' style description (second token), else the whole."""
    parts = description.split()
    return parts[1] if len(parts) >= 2 and parts[0].isdigit() else description
