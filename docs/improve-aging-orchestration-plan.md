# Phase 5 — Improve Aging Inventory orchestration — plan

**Branch:** `feature/improve-aging-orchestration` (confirmed, working tree clean).
**Status:** inspection complete; this document is the plan. No implementation has begun.

Improve Aging is **not a fourth skill.** It is an orchestration that runs the three existing
skills in dependency order, ranks and filters their results, and consolidates them into one
dealer action plan. It performs **no numerical calculation of its own.**

---

## 1. Inspection findings

### Existing skill interfaces (all reused unchanged)

| Skill | Entry point | Key outputs the workflow consumes |
| --- | --- | --- |
| inventory-portfolio-forecast | `skills.inventory_portfolio.analyze(transport, *, revenue_target_*)` | `capacity_position`, `aging_profile.buckets`, `top_risk_vehicles` (with `prob_age_over_90`, `p90_depreciation_loss`, `prob_negative_net_value`, `risk_score`, `cost_basis`), `recommended_actions` (action + matched_rule), `financial_risk`, `one_/three_month_forecast`, `audit.simulation.simulation_id` |
| single-vehicle-valuation | `skills.single_vehicle.analyze(vehicle_id, transport)` | `valuation`, `market_position.deal_rating`, `break_even_analysis`, `promotional_headroom`, `sales_outcome_distribution`, `depreciation_forecast`, `pricing_scenarios`, `recommended_strategy`, `warnings`, `approvals_required`, `audit.request_id`, `audit.simulation.simulation_id` |
| dealer-event-promotion-planner | `skills.promotion_planner.plan_event(transport, event_id, target_utilization)` | `feasibility` (status ∈ ACHIEVABLE / ACHIEVABLE_WITH_MARGIN_COST / AT_RISK / NOT_ACHIEVABLE; `probability_target_achieved`; `required_incremental_units`), `plans` (MARGIN_PROTECT / BALANCED / CAPACITY_FIRST), `recommended_plan`, `projected_ending_inventory`, `financial_impact` (gross/holding/depreciation, one simulation), `per_vehicle_actions`, `warnings`, `approvals_required`, `audit.simulation.simulation_id` |

Every skill result carries its **own** `simulation_id` (`DrawMatrix.reference()`), and each
single-vehicle call runs an independent simulation. This is the central constraint (§4).

### Assistant / router (Phase 4)

- `agents/router.py` — `IMPROVE_AGING_INVENTORY` is currently routed via the aging-cohort rule
  and returns `execution_allowed = False`. Needs an inventory-pressure signal and
  `execution_allowed = True`.
- `agents/assistant.py` — currently returns `WORKFLOW_NOT_YET_AVAILABLE` for aging. Needs a
  `_run_improve_aging` branch; `AssistantState` needs three new members.

### Shell view

`views/improve_aging.py` is a static `STEPS` description. It will be replaced by an evidence
workspace.

### Scenario data — no mock change needed

The existing 12-vehicle `DEALER-1001` fixture already represents every required element:

| Required element | Vehicle(s) in fixture |
| --- | --- |
| Inventory above a 70% target | 12 of 14 slots (86%) |
| Inbound vehicles | `capacity.confirmed_inbound = 2`, `inbound.json` |
| Over 90 days | V-10004 (96d), V-10005 (108d), V-10012 (130d) |
| P50 < 90 but P90 > 90 | mid-aged e.g. V-10011 (73d) — simulation-driven |
| Both P50 and P90 > 90 | V-10012 (130d) |
| Poor-deal vehicle | a unit priced above market (from `recommended_actions` matched_rule) |
| High-depreciation vehicle | V-10005 (BMW 540i luxury), V-10006 (Bolt EUV / EV) |
| Large safe-headroom vehicle | V-10012 (list 28,495 vs original 31,995) |
| Protected high-demand vehicle | V-10010 (Kia Telluride, 26d), V-10008 (Outback, 33d, EXCELLENT) |
| Recently acquired | V-10010 (26d), V-10007 (29d) |
| Duplicate inventory | V-10001 **and** V-10007 (both 2022 Toyota RAV4 XLE) |
| Manager-approval case | V-10005 (underwater/aged → approvals_required) |
| Unrealistic-target risk | 70% target on this lot → promotion feasibility NOT_ACHIEVABLE |

**Scenario:** `as_of = 2026-07-21 14:00Z` (injected clock via `MockTransport`), event **Summer
Clearance** (`EVT-SUMMER-2026`, 2026-07-23 → 2026-07-27), target utilization 70%. This is the
only event named; "July 4th" legitimately resolves to nothing.

---

## 2. Files to create

| File | Purpose |
| --- | --- |
| `src/pricing_agent/workflows/candidate_selection.py` | Explainable ranking/filtering of portfolio results into candidates + exclusions, with reason codes. No calculation. |
| `src/pricing_agent/workflows/improve_aging.py` | The orchestration engine: validate → portfolio → select → single-vehicle → promotion (conditional) → consolidate → trace. Typed dataclasses. No calculation. |
| `tests/unit/test_candidate_selection.py` | Selection/exclusion reason-code rules. |
| `tests/unit/test_improve_aging_workflow.py` | Sequence, counts, states, cross-sim constraint, failure handling, id preservation. |
| `docs/improve-aging-orchestration-results.md` | End-of-phase report. |

## 3. Files to modify

| File | Change |
| --- | --- |
| `agents/router.py` | Add an inventory-pressure signal so a reduction request routes to IMPROVE_AGING even with a named event; `execution_allowed = True`; keep aging-cohort routing. |
| `agents/assistant.py` | `_run_improve_aging`: extract target utilization + resolve event (reusing `parse_target_utilization`/`resolve_event`), build a structured `ImproveAgingRequest`, call the orchestration, map its state to `AssistantState`, build the summary. Add `PARTIAL_RESULT`, `TARGET_NOT_ACHIEVABLE`, `NO_SAFE_ACTIONS` to `AssistantState`. |
| `agents/__init__.py` | Export the new orchestration entry + result types. |
| `views/improve_aging.py` | Replace the shell with the 10-section evidence workspace. |
| `views/assistant_home.py` | Render the improve-aging assistant summary and the new states. |
| `tests/unit/test_workflows.py` | Extend the workflow-layer guard to also forbid `numpy`/`percentile`/`simulate(` in the new orchestration modules (proving no calculation), and update the "aging is a shell / fabricates nothing" assertions that Phase 5 supersedes. |
| `tests/unit/test_architecture.py` | No change needed — the calculation-layer guard already covers it; the workflow-layer "no domain/simulation import" guard in `test_workflows.py` is the relevant one and is strengthened. |
| `README.md`, `docs/architecture.md`, `docs/product-spec.md`, `docs/demo-script.md` | Document the orchestration. |

## 4. Files that will NOT change (confirmed)

The three skills (`skills/*.py`), their `skills/*/SKILL.md`, `domain/*`, `simulation/*`,
`policy/*`, `mcp_clients/*`, `schemas/*`, and the mock data. The workflow reuses skill
*results*; it never re-derives a number.

---

## 5. The cross-simulation constraint (the load-bearing rule)

The portfolio runs one simulation (`sim_P`). Each single-vehicle candidate runs its own
(`sim_V1…sim_Vn`). The promotion planner runs its own (`sim_M`). **These are different
probability spaces.** The workflow therefore:

- **Never** sums or averages percentiles across simulations. No P50 of a sum is built from
  independent P50s.
- Takes **portfolio-level** figures (ending inventory, utilization, probability of reaching
  the target, joint gross/holding/depreciation impact) from a **single** source: the
  promotion planner's `sim_M` when an event is resolved; otherwise these are marked
  "unavailable — requires an event," and only the portfolio's own single-simulation exposure
  figures (`financial_risk`, `sim_P`) are shown.
- Shows per-vehicle single-vehicle evidence **side by side**, each labelled with its own
  `request_id` and `simulation_id`.
- A test (`test_percentiles_from_independent_simulations_are_not_summed`) asserts the
  consolidation code contains no summation of percentile fields across results.

---

## 6. Execution sequence (recorded in an ordered trace)

```
1  PORTFOLIO_FORECAST        inventory_portfolio.analyze   sim_P      (exactly once)
2  CANDIDATE_SELECTION        —                             (no sim)   ranks/filters sim_P + inventory facts
3  SINGLE_VEHICLE_VALUATION   single_vehicle.analyze × k    sim_V1..k  (only selected candidates)
4  PROMOTION_PLAN             promotion_planner.plan_event  sim_M      (only if event resolved)
5  CONSOLIDATE                —                             (no sim)   groups actions, side-by-side figures
```

Each trace entry: `step_number`, `step_name`, `skill_called`, `request_id`, `simulation_id`,
`start_timestamp`, `end_timestamp`, `status`, `warnings`, `error`.

### Candidate selection (Step 2) reason codes

Derived only from `sim_P` outputs and static inventory facts — never recalculated:

| Code | Signal |
| --- | --- |
| CURRENTLY_OVER_90 / _120 | `days_in_inventory` (fact) |
| P50_PROJECTED_OVER_90 | `top_risk_vehicles.prob_age_over_90 > 0.5` |
| P90_PROJECTED_OVER_90 | `0.1 < prob_age_over_90 ≤ 0.5` |
| CURRENT_PRICE_POOR_DEAL | `recommended_actions.action == BALANCED_REPRICE` (priced above market) |
| HIGH_HOLDING_COST / HIGH_DEPRECIATION_RISK | `top_risk_vehicles` p90 figures above a percentile of the cohort |
| DUPLICATE_INVENTORY | same make+model+trim as another active unit (fact) |
| INBOUND_REPLACEMENT_PRESSURE | inbound shares segment/model (fact) |
| HIGH_SAFE_PROMOTIONAL_HEADROOM | `recommended_actions.action ∈ {EVENT_PROMOTION, VELOCITY_REPRICE}` |
| CAPACITY_RELEASE_PRIORITY | high `risk_score` while utilization exceeds target |

Exclusions: RECENTLY_ACQUIRED (acquisition_date), ALREADY_GOOD_DEAL / HIGH_DEMAND_PROTECT_GROSS
(`action ∈ {INCREASE_PRICE, RETAIN_PRICE}`), EXPECTED_TO_SELL_BEFORE_EVENT (RETAIN_PRICE, low
days), INSUFFICIENT_DATA (not in analyzed set), NO_SAFE_DISCOUNT_HEADROOM (no headroom signal
and aged), ALREADY_ASSIGNED_TO_CAMPAIGN (`campaign_participation`), MANUAL_HOLD (status flag).

**Protected vehicles** (RECENTLY_ACQUIRED, HIGH_DEMAND_PROTECT_GROSS, ALREADY_GOOD_DEAL) are
excluded before single-vehicle valuation and never enter aggressive promotion — test #15.

### Consolidated action grouping (Step 5)

Per vehicle → REPRICE_NOW, EVENT_PROMOTION, PROTECT_PRICE, MANAGER_REVIEW,
WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW, NO_ACTION — derived from the single-vehicle
`recommended_strategy` / `warnings` / `approvals_required` and the promotion `per_vehicle_actions`.

---

## 7. Result states

`ROUTED_AND_EXECUTED`, `NEEDS_CLARIFICATION`, `PARTIAL_RESULT`, `TARGET_NOT_ACHIEVABLE`,
`NO_SAFE_ACTIONS`, `EXECUTION_ERROR`.

Event handling:
- **No event named** → diagnosis + candidates + per-vehicle valuation; promotion step marked
  "no event supplied"; `ROUTED_AND_EXECUTED`.
- **Event named and resolved** (Summer Clearance) → full pipeline; state reflects promotion
  feasibility (`TARGET_NOT_ACHIEVABLE` when the planner says so, else `ROUTED_AND_EXECUTED`).
- **Event named but unresolved** ("July 4th") → `NEEDS_CLARIFICATION`, listing the real
  calendar events; **never** substituted with Summer Clearance (tests #5, #13).

Failure: if a single-vehicle or promotion call raises, completed results are preserved, no
value is fabricated, and the workflow returns `PARTIAL_RESULT` naming what is unavailable
(test #9).

---

## 8. Schema decision (flagged per the phase instruction)

**No JSON schema change is required, and none will be made.** The orchestration result is an
in-memory typed structure (dataclasses) assembled from already-schema-valid skill results; it
is consumed by the assistant and the view and is not persisted or re-validated. Adding a
`schemas/improve-aging-*.schema.json` would touch the protected `schemas/` tree and the schema
validator for no functional gain, since every embedded skill result is already validated at
its own boundary. If a future phase persists or exchanges the consolidated plan across a
process boundary, a schema becomes genuinely required; it is not today. `scripts/validate_schemas.py`
stays at 62 checks.

---

## 9. Test plan (maps to the 15 required proofs)

1. Portfolio runs first and exactly once — monkeypatch counter + trace order.
2. Candidate selection consumes the portfolio result — selection given a portfolio dict.
3. Single-vehicle runs only for selected candidates — counter equals candidate count, ids match.
4. Promotion runs only after inputs exist / event resolved — counter 0 when no event.
5. "July 4th" does not resolve to Summer Clearance — NEEDS_CLARIFICATION, no promotion call.
6. No numerical calculation duplicated — AST guard: orchestration imports no domain/simulation,
   no `numpy`/`percentile`/`simulate(`.
7. request_id and simulation_id preserved — present per embedded result and in the trace.
8. Percentiles from independent sims not summed — guard on the consolidation source.
9. Skill failure → PARTIAL_RESULT — monkeypatch a raising single-vehicle call.
10. Warnings and approvals preserved — equal to the skill results'.
11. No price-publishing tool called — orchestration references no write client.
12. Assistant executes end to end — `run_assistant` on the demo prompt → executed.
13. Missing information → NEEDS_CLARIFICATION — unresolved event.
14. Unrealistic target → TARGET_NOT_ACHIEVABLE — 70% Summer Clearance.
15. Protected vehicles not aggressively promoted — recently-acquired / high-demand excluded.

---

## 10. Import-cycle discipline

`agents.assistant → workflows.improve_aging → skills` is the allowed direction. The
orchestration must **not** import `agents` or `workflows.registry` (which imports views, which
import agents) — that would close a cycle. Text parsing (target %, event name) stays in the
assistant, which passes a structured `ImproveAgingRequest` to the orchestration. The
orchestration validates the structured request and calls skills only.

---

## 11. Known limitations (anticipated)

- Portfolio-level joint impact requires a resolved event (from `sim_M`); without one, only
  per-vehicle side-by-side evidence and portfolio exposure are shown.
- Candidate selection infers headroom presence from the portfolio's `recommended_actions`
  rather than an exact dollar figure; the exact figure appears once single-vehicle runs.
- The scenario is a run-off with no modelled replacement acquisitions (inherited).

## 12. Next phase (anticipated)

LLM-assisted routing above the deterministic layer; persisting/exchanging the consolidated
plan (which would then justify a result schema); and multi-event / multi-horizon planning.
