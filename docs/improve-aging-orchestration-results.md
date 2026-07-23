# Phase 5 — Improve Aging Inventory orchestration — results

**Result: PASS.** Improve Aging Inventory is now a working orchestration that coordinates the
three existing skills in dependency order and consolidates their results into one dealer
action plan. It is **not a fourth skill**: it adds no valuation, forecasting, or promotion
arithmetic, and it keeps each skill's simulation separate. No skill implementation, schema,
or mock fixture was modified.

**Companion to** `docs/improve-aging-orchestration-plan.md` (the plan) and
`docs/architecture.md` §3.6.

---

## 1. Workflow sequence

The engine (`src/pricing_agent/workflows/improve_aging.py`) records and exposes this order:

```
1 PORTFOLIO_FORECAST        inventory_portfolio.analyze   sim_P     run once
2 CANDIDATE_SELECTION        candidate_selection            —        ranks/filters sim_P + inventory facts
3 SINGLE_VEHICLE_VALUATION   single_vehicle.analyze × k    sim_V1…k  selected candidates only
4 PROMOTION_PLAN             promotion_planner.plan_event  sim_M     only when a real event resolves
5 CONSOLIDATE                improve_aging                  —        group actions, side-by-side figures
```

**Verified skill-invocation counts** (Summer Clearance scenario): portfolio ×1,
single-vehicle ×7 (one per selected candidate), promotion ×1. Without an event: portfolio ×1,
single-vehicle ×7, promotion ×0.

---

## 2. Candidate rules

Selection ranks and filters the portfolio result and static inventory facts. A candidate
needs at least one **primary** reason; supporting reasons add context but do not, alone,
select a vehicle.

| Primary reason | Signal (all read from the portfolio result or a fixture fact) |
| --- | --- |
| CURRENTLY_OVER_90 / _120_DAYS | `days_in_inventory` |
| P50_PROJECTED_OVER_90_DAYS | `top_risk_vehicles.prob_age_over_90 ≥ 0.5` |
| CURRENT_PRICE_POOR_DEAL | `recommended_actions.action == BALANCED_REPRICE` |
| HIGH_DEPRECIATION_RISK | `p90_depreciation_loss ≥ 60%` of the cohort's worst |
| DUPLICATE_INVENTORY | shares make+model+trim with another active unit |
| CAPACITY_RELEASE_PRIORITY | portfolio action is a wholesale / loss-minimization disposition |

Supporting: P90_PROJECTED_OVER_90_DAYS (`0.1 ≤ prob < 0.5`), HIGH_SAFE_PROMOTIONAL_HEADROOM
(`action ∈ {EVENT_PROMOTION, VELOCITY_REPRICE}`), INBOUND_REPLACEMENT_PRESSURE (inbound of the
same committed segment).

## 3. Exclusion rules

| Exclusion | Signal |
| --- | --- |
| ALREADY_ASSIGNED_TO_CAMPAIGN | `campaign_participation` non-empty |
| RECENTLY_ACQUIRED | acquired within 30 days |
| HIGH_DEMAND_PROTECT_GROSS | portfolio action is `INCREASE_PRICE` |
| ALREADY_GOOD_DEAL | `RETAIN_PRICE` and under 60 days |
| INSUFFICIENT_DATA | not in the portfolio's analysed set |
| EXPECTED_TO_SELL_BEFORE_EVENT | only supporting reasons — not aged enough to act on |
| MANUAL_HOLD / caller exclusions | status flag or a `excluded_vehicle_ids` / `excluded_makes` input |

**Protected** = RECENTLY_ACQUIRED, ALREADY_GOOD_DEAL, HIGH_DEMAND_PROTECT_GROSS,
ALREADY_ASSIGNED_TO_CAMPAIGN, MANUAL_HOLD. Protected vehicles are excluded before analysis and
never promoted (§7).

---

## 4. The cross-simulation constraint

The portfolio (`sim_P`), each single-vehicle candidate (`sim_Vi`), and the promotion plan
(`sim_M`) are different probability spaces. The engine **never** sums or averages a percentile
across them:

- Portfolio diagnosis figures come from `sim_P` alone.
- Per-vehicle evidence is shown **side by side**, each row stamped with its own `request_id`
  and `simulation_id`.
- Joint outcome figures (required reduction, ending inventory, target probability, joint
  gross / holding / depreciation impact) come from a **single** source — the recommended
  promotion plan's simulation — and are marked *unavailable* when no event ran.

`test_independent_simulations_are_kept_separate` confirms ≥3 distinct simulation ids are in
play, that the joint-outcome simulation id equals the recommended plan's (not the per-vehicle
ones), and that ending inventory carries that same id. `test_workflow_modules_do_not_recalculate`
confirms the engine imports neither `domain` nor `simulation` and calls no `percentile` /
`np.` / `simulate(`.

---

## 5. Failure behaviour

- A single-vehicle or promotion call that raises is caught: completed results are preserved,
  the trace entry is marked `ERROR`, the gap is named in `unavailable`, and the workflow
  returns `PARTIAL_RESULT`. No missing value is fabricated.
- A portfolio failure (the first step, on which everything depends) returns `EXECUTION_ERROR`.
- An event named but not on the calendar ("July 4th") returns `NEEDS_CLARIFICATION` listing
  the real events, and **never** substitutes Summer Clearance — the promotion step does not run.

States: `ROUTED_AND_EXECUTED`, `NEEDS_CLARIFICATION`, `PARTIAL_RESULT`, `TARGET_NOT_ACHIEVABLE`,
`NO_SAFE_ACTIONS`, `EXECUTION_ERROR`.

---

## 6. Protection is authoritative over the promotion skill

The promotion skill has its own eligibility (days ≥ 21). When its raw plan selects a vehicle
the workflow protected (e.g. V-10007, recently acquired at 29 days), the workflow **holds it
back**: it is recorded in `held_from_promotion`, removed from `effective_promotion_ids`, and
its consolidated action is PROTECT_PRICE, never EVENT_PROMOTION. The workspace shows the note
("Held back from promotion despite the skill's eligibility"). Tested by
`test_workflow_holds_back_protected_vehicles_the_skill_would_promote`.

---

## 7. Scenario used

The reproducible demo scenario (an event that truly exists in the calendar; injected clock):

- **as_of** 2026-07-29 14:00Z (via `MockTransport`, never the wall clock)
- **event** Summer Clearance (`EVT-SUMMER-2026`), 2026-08-17 → 2026-08-21
- **target** 70% utilization

> Scenario dates were moved forward so the demo reads as forward-looking from a late-July
> vantage. The event now sits 19 days after `as_of` (a 23-day promotion horizon vs 6 before),
> which legitimately changes the promotion outcome — see the note on the "unrealistic target"
> row below.

No mock data was added — the existing 12-vehicle `DEALER-1001` fixture already contains every
required element. Result:

| Element | Vehicle(s) |
| --- | --- |
| Selected candidates (7) | V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001 |
| Currently over 90 / 120 days | V-10004 (96d), V-10005 (108d), V-10012 (130d) |
| P50 projected over 90 | V-10005, V-10012, V-10002, V-10006, V-10004 |
| P90-only tail (excluded) | V-10003, V-10009 → EXPECTED_TO_SELL_BEFORE_EVENT |
| Poor-deal | V-10008 (priced above market) |
| High depreciation | V-10006 (Bolt EUV / EV) |
| Duplicate inventory | V-10001 (its twin V-10007 is protected) |
| Protected — recently acquired | V-10007 (29d), V-10010 (26d) |
| Excluded — campaign | V-10011 (`CAMP-JUNE-2026`) |
| Manager-approval cases | present — 17 approvals across the analysed cohort |
| Target at the new window | 70% → feasibility **AT_RISK** (hits target ~43%), required reduction 2, ending inventory P50 10. A tighter 60% target still yields NOT_ACHIEVABLE, so both states remain demonstrable. |

Selected candidates (7), excluded (5): V-10003, V-10007, V-10009, V-10010, V-10011.

---

## 8. Assistant integration

Routing was refined so an **inventory-reduction** request executes the orchestration, while a
plain event plan still goes to Merchandise:

| Request | Routes to |
| --- | --- |
| "My lot is full and 30 vehicles are over 60 days old. Which should I reprice?" | Improve Aging (executes) |
| "Reduce my inventory utilization to 70% during the Summer Clearance event." | Improve Aging (executes → TARGET_NOT_ACHIEVABLE) |
| "Reduce inventory utilization to 70% by the July 4th event." | Improve Aging → NEEDS_CLARIFICATION |
| "Plan the Summer Clearance event to reach 70% utilization." | **Merchandise** (unchanged from Phase 4) |
| "Which aging vehicles should I promote?" | Improve Aging (executes) |

The assistant summary shows the detected workflow, the aging diagnosis, selected/excluded
counts, the recommended plan, target status, major warnings, required approvals, and a link
into the full workspace. No LLM is involved.

---

## 9. The workspace

`views/improve_aging.py` replaced the Phase 3 shell with a ten-section evidence workspace:
workflow objective, portfolio diagnosis, aging & capacity, candidate ranking, selected &
excluded, per-vehicle pricing evidence, promotion-plan comparison, projected ending inventory,
warnings & approvals, and the execution trace. It runs the reproducible scenario by default
and shows the assistant's routed result when one is in session. It renders the workflow's
result; it does not itself call a skill or compute a figure. Verified in-browser: all ten
sections render, the TARGET_NOT_ACHIEVABLE banner shows, the protection and held-back notes
appear, seven data tables populate, and there are no server errors.

---

## 10. Validation

```
python -m pytest tests -q          387 passed   (350 before Phase 5, +37)
python scripts/validate_schemas.py PASSED  62 checks
```

New tests: `test_candidate_selection.py` (12 — reason-code rules, protection, ranking, no
recalculation) and `test_improve_aging_workflow.py` (25 — the 15 required proofs plus trace
shape and no-event handling). Two Phase 4 tests were updated because Phase 5 supersedes them
(aging is now executable, not deferred), and the Phase 3 "improve aging page is a shell" test
was rewritten for the working workspace.

### Smoke tests (all covered by passing tests; UI confirmed in-browser)

| # | Scenario | Result |
| --- | --- | --- |
| 1 | Aging diagnosis without event | ROUTED_AND_EXECUTED, promotion skipped, joint figures marked unavailable |
| 2 | Valid Summer Clearance event | full pipeline; at the new window, feasibility AT_RISK (~43%) with complete evidence |
| 3 | Invalid July 4th event | NEEDS_CLARIFICATION, no substitution, promotion not run |
| 4 | Missing target utilization | ROUTED_AND_EXECUTED (diagnosis + per-vehicle actions) |
| 5 | Unrealistic target | TARGET_NOT_ACHIEVABLE (60% probe → ~19% chance) |
| 6 | Partial skill failure | PARTIAL_RESULT, completed results preserved, gap named |
| 7 | Protected-price vehicle | V-10007 / V-10010 excluded and held from promotion |
| 8 | Manager-approval case | 17 approvals surfaced, MANAGER_REVIEW / WHOLESALE actions |

---

## 11. Schema decision (as flagged in the plan)

No JSON schema was added. The consolidated result is an in-memory typed structure assembled
from already-schema-valid skill results; it is consumed by the assistant and the view and is
not persisted or exchanged across a process boundary. `scripts/validate_schemas.py` stays at
62 checks and the protected `schemas/` tree is untouched. A schema becomes genuinely required
only if a future phase persists or transmits the consolidated plan.

---

## 12. Known limitations

1. **Joint outcomes need an event.** Without a resolved calendar event, portfolio-level
   ending inventory / target probability / joint impact are unavailable (a single simulation
   is required to project a joint outcome); only per-vehicle evidence and portfolio exposure
   are shown.
2. **Candidate selection infers headroom presence** from the portfolio's `recommended_actions`
   rather than an exact dollar figure; the exact headroom appears once single-vehicle runs.
3. **The promotion skill's raw plan can still list a protected vehicle** — the workflow holds
   it back and says so, but the skill's own plan comparison (shown for transparency) reflects
   the skill's eligibility, not the workflow's protection.
4. **Deep analysis is capped at 8 candidates** (risk-ranked) to bound runtime; on this lot all
   7 candidates are analysed, so the cap is not currently binding.
5. **Run-off assumption inherited** — no modelled replacement acquisitions.

---

## 13. Next phase

- **LLM-assisted routing** above the deterministic layer (the model selects the workflow and
  fills the same request shape; the orchestration and skills are unchanged; §4.1 still holds).
- **Persisting / exchanging the consolidated plan**, which would then justify a result schema.
- **Multi-event and multi-horizon planning**, and letting the workflow pass its protected set
  into the promotion skill so the raw plan and the workflow agree without a post-filter.
