# Phase 5.1 — Improve Aging demo polish — plan

**Branch:** `feature/improve-aging-demo-polish` (confirmed, working tree clean).
**Scope:** presentation and usability only. No algorithm, skill, selection, schema, mock, or
routing change. Every displayed number continues to come from the Phase 5 workflow result.

---

## 1. Inspection — fields available in the existing result

Run of the Summer Clearance scenario (`as_of=2026-07-21`, `EVT-SUMMER-2026`, target 70%)
returns state **TARGET_NOT_ACHIEVABLE** with all of the following already present. Nothing new
needs to be computed.

### Executive summary (all from `portfolio_summary` / `selection` / `promotion_result`)
| Metric | Field | Value now |
| --- | --- | --- |
| Current utilization | `portfolio_summary.current_utilization` | 0.857 |
| Target utilization | `portfolio_summary.target_utilization` | 0.70 |
| Units to release | `portfolio_summary.required_unit_reduction` | 4 |
| Action candidates | `len(selection.candidates)` | 7 |
| Target status / probability | `promotion_result.feasibility.status` / `probability_target_achieved` | NOT_ACHIEVABLE / 0.0085 |
| Recommended plan | `promotion_result.recommended_plan.plan_type` | CAPACITY_FIRST |

### Target-achievability (all present)
- required incremental units = 4; recommended-plan achievable ≈ 0 (`p50_achievable_incremental_units` 0.0) → **gap = 4**
- `feasibility.alternatives`: LONGER_CAMPAIGN (+7 days → 1.36%), REVISED_UTILIZATION_TARGET (0.80 → 70%), WHOLESALE_DISPOSITION (4 units → 100%)
- Supporting reasons present in the result: protected recently-acquired (V-10007, V-10010), campaign-assigned (V-10011), below-break-even approvals on most candidates (price-floor), inbound capacity conflict (`INBOUND_CAPACITY_CONFLICT`), promo warnings `UNREALISTIC_INVENTORY_TARGET`, `CAPACITY_TARGET_UNLIKELY_TO_BE_ACHIEVED`, `PRICE_CANNIBALIZATION_RISK`.

### Recommended plan block (`promotion_result.plans[*].outcomes` / `totals`)
MARGIN_PROTECT (1 veh) · BALANCED (3 veh) · **CAPACITY_FIRST (5 veh, recommended, also the most aggressive)**. Each has `ending_inventory`, `ending_utilization`, `probability_target_achieved`, `gross_impact`, and the summary carries `expected_holding_cost_savings` / `expected_depreciation_savings`. Approval count = 17 (from single-vehicle results). `recommended_plan.rationale_codes` = `FEASIBILITY_NOT_ACHIEVABLE`, `TARGET_NOT_REACHABLE_WITHIN_SAFE_HEADROOM`.

### Per-vehicle evidence (`vehicle_evidence[*].result`)
current price, recommended price, P50/P90 days to sale, break-even, minimum safe list, headroom, deal rating, warnings, approvals, `request_id`, `simulation_id` — all present per candidate.

### Consolidated actions (`consolidated_actions`) — the authoritative per-vehicle decision
EVENT_PROMOTION ×2 (V-10008, V-10001) · MANAGER_REVIEW ×2 (V-10002, V-10006) · WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW ×3 (V-10005, V-10012, V-10004) · PROTECT_PRICE ×3 (V-10007, V-10010, V-10011) · NO_ACTION ×2 (V-10003, V-10009).

### Excluded records (`selection.exclusions`)
carry `vehicle_id`, `description`, `reason_codes` only. **Age/price/status for excluded vehicles
will be looked up in the view from the inventory fixture** (a fact read, not a calculation) —
the workflow is not modified.

### Trace
12 entries (1 portfolio, 1 selection, 7 single-vehicle, 1 promotion, 1 consolidate), each with
`request_id`, `simulation_id`, timestamps, warnings, status.

**Baseline to hold identical:**
- Selected: V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001
- Excluded: V-10003, V-10007, V-10009, V-10010, V-10011
- Recommended plan CAPACITY_FIRST; required reduction 4; P(target) 0.0085; ending inv P50 12

---

## 2. Files to create

| File | Purpose |
| --- | --- |
| `src/pricing_agent/views/improve_aging_copy.py` | **Centralized** presentation mapping: reason-code → dealer label, exclusion → category (safety / business / data), "why these vehicles" categories, and `next_steps(result)` deriving 3–5 prioritized actions from existing state / action counts / approvals / feasibility alternatives. Pure strings + counting; no numeric calculation. |
| `tests/unit/test_improve_aging_view.py` | The 13 required proofs. |
| `docs/improve-aging-demo-polish-results.md` | End-of-phase report. |

## 3. Files to modify

| File | Change |
| --- | --- |
| `views/improve_aging.py` | Reorder into the narrative hierarchy (§8 below); add executive summary, achievability explanation, "what should I do next?", explicit recommended-plan card with conservative/aggressive alternatives, unified vehicle-action tables with friendly labels, "why these vehicles?", five-step business summary, full-trace expander, disclosure footer. Every value read from the result. |
| `views/assistant_home.py` | Tighten the aging summary: current vs target utilization, target status, recommended plan, candidate count, top 1–2 warnings, approvals count, workspace link. |
| `README.md`, `docs/demo-script.md` | Reflect the new page hierarchy briefly. |

## 4. Files NOT changed
The three skills, SKILL.md, `domain/`, `simulation/`, `policy/`, `mcp_clients/`, `schemas/`,
mocks, `candidate_selection.py`, and `improve_aging.py` (the orchestration engine). Selection,
scores, plan choice, and every number are untouched.

---

## 5. New page hierarchy (§8 of the brief)

1. Executive summary (≤5 metrics) + one recommendation statement
2. Target-achievability explanation (only when TARGET_NOT_ACHIEVABLE)
3. What should I do next? (3–5 grounded actions)
4. Recommended plan (explicit card; conservative / recommended / aggressive)
5. Vehicles requiring action (friendly labels; P50/P90, break-even, approval; raw codes in expander)
6. Vehicles protected or excluded (friendly labels + category)
7. Why these vehicles? (business categories present)
8. Plan comparison table
9. Warnings and approvals
10. Five-step workflow summary
11. Full execution trace (collapsed expander — preserves ids/timestamps/warnings)
12. Model / source / prototype disclosure

## 6. Reason-code → dealer label (centralized)
Selection: over-90/120, P50/P90 projected, priced above market, high depreciation, duplicate,
priority to free a slot, safe discount room, inbound of same type arriving. Exclusion:
recently acquired (protect price), assigned to another campaign, expected to sell before the
event, not enough data, high demand (protect gross), already priced to sell, on manual hold.
Exclusion categories: DATA_LIMITATION (insufficient data), SAFETY_RULE (no safe headroom /
price-floor), BUSINESS_RULE (everything else). Raw codes stay visible in an expander/tooltip.

## 7. "What should I do next?" mapping
`next_steps(result)` → ordered actions, each grounded and count-referenced:
- state TARGET_NOT_ACHIEVABLE → "Revise the target or extend the window" (from `feasibility.alternatives`)
- MANAGER_REVIEW count → "Review N vehicles needing manager approval"
- WHOLESALE count → "Wholesale / loss-minimization review for N units"
- EVENT_PROMOTION count → "Approve the recommended plan — promotes N vehicles"
- PROTECT_PRICE count → "Hold price on N protected vehicles"
- INBOUND_CAPACITY_CONFLICT warning → "Review inbound commitments"
Only those supported by the actual result are shown; capped at 5, priority-ordered.

## 8. Tests (map to the 13 required proofs)
exec-summary values equal result fields; TNA copy reflects the real gap (4); actions map only
from existing fields/codes; selected & excluded ids unchanged; recommended plan unchanged; the
view/copy modules do no pricing/forecasting math (AST + token guard); raw codes map to labels;
default summary has exactly five business steps; full trace remains accessible; assistant
summary links to the workspace; no price-publishing tool; all existing tests stay green.

## 9. Known risks / decisions
- Excluded-vehicle age/price are read from the inventory fixture in the view (a fact lookup).
- Recommended == most aggressive here (CAPACITY_FIRST); the card labels that honestly rather
  than implying a safer choice exists.
- No number is recomputed; counting result items is not a pricing/forecasting calculation.
