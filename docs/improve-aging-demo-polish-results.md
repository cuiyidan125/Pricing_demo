# Phase 5.1 — Improve Aging demo polish — results

**Result: PASS.** The Improve Aging workspace was reorganised into a dealer-first narrative
and the assistant summary tightened. It is a **presentation-only** change: the workflow
engine, candidate selection, all skills, schemas, and mock data are byte-identical, so every
displayed number is unchanged by construction.

**Companion to** `docs/improve-aging-demo-polish-plan.md` and
`docs/improve-aging-orchestration-results.md` (Phase 5).

---

## 1. Files created
- `src/pricing_agent/views/improve_aging_copy.py` — centralized presentation mapping:
  reason-code → dealer label, exclusion → rule category, "why these vehicles" categories,
  `next_steps(result)`, `recommendation_statement(result)`. Pure strings + counting of
  existing result items; no calculation.
- `tests/unit/test_improve_aging_view.py` — 20 tests (the 13 required proofs + extras).
- `docs/improve-aging-demo-polish-plan.md`, `docs/improve-aging-demo-polish-results.md`.

## 2. Files modified
- `src/pricing_agent/views/improve_aging.py` — reordered into the new hierarchy; executive
  summary, achievability explanation, "what should I do next?", explicit recommended-plan
  card, unified vehicle-action tables with friendly labels, "why these vehicles?", five-step
  business summary, full-trace expander, disclosure footer. Added the pure helper
  `executive_metrics(result)`.
- `src/pricing_agent/views/assistant_home.py` — tightened the aging chat summary; fixed a
  stale capability line that still said orchestration "arrives in a later phase."
- `README.md`, `docs/demo-script.md`.

## 3. Files NOT changed (verified byte-identical via `git status`)
`workflows/improve_aging.py`, `workflows/candidate_selection.py`, all three skills, SKILL.md,
`domain/`, `simulation/`, `policy/`, `mcp_clients/`, `schemas/`, and mock data.

---

## 4. Before → after page structure

| Before (Phase 5) | After (Phase 5.1) |
| --- | --- |
| 1 Workflow objective | 1 **Executive summary** (5 metrics + recommendation statement) |
| 2 Portfolio diagnosis · 3 Aging & capacity | 2 **Why the target is not achievable** (needs / can release / gap + reasons + what would close it) |
| 4 Candidate ranking · 5 Selected & excluded | 3 **What should I do next?** (3–5 prioritized actions) |
| 6 Per-vehicle evidence | 4 **Recommended plan** (explicit card, conservative/aggressive framing) |
| 7 Promotion-plan comparison | 5 **Vehicles requiring action** (friendly labels; raw codes in expander) |
| 8 Projected ending inventory | 6 **Vehicles protected or excluded** (friendly labels + rule type) |
| 9 Warnings & approvals | 7 **Why these vehicles?** (business categories) |
| 10 Execution trace | 8 Plan comparison |
| | 9 Warnings & approvals |
| | 10 **How the Agent got here** (five business steps) |
| | 11 **Full execution trace** (collapsed expander — ids/timestamps/warnings preserved) |
| | 12 Disclosure (synthetic · prototype · human review · no price published) |

Ten equally-weighted technical sections became a **situation → recommendation → impact →
actions → evidence → audit** story.

## 5. Final executive-summary metrics (all read from the result)

| Metric | Source field | Value |
| --- | --- | --- |
| Current utilization | `portfolio_summary.current_utilization` | 86% |
| Target utilization | `portfolio_summary.target_utilization` | 70% |
| Units to release | `portfolio_summary.required_unit_reduction` | 2 |
| Action candidates | `len(selection.candidates)` | 7 |
| Target status | `feasibility.status` / `probability_target_achieved` | At Risk · ~43% likely |

> Values reflect the 2026-08-17 Summer Clearance window. When this polish landed the same
> scenario read *Not Achievable · 1% likely* with 4 to release; the forward-looking window
> moved the promotion outcome (the recommendation statement now reads "Recommended approach:
> Capacity First"). A tighter 60% target still renders the full "not achievable" explanation.

Recommendation statement (derived from state, not hard-coded): for the 70% canonical it now
reads *"Recommended approach: Capacity First."*; for a not-achievable target it reads *"The
requested target is not achievable within the current event window and price-floor
constraints…"*

## 6. Final recommended-plan presentation

**Capacity First · Aggressive stance** — with rationale codes `FEASIBILITY_NOT_ACHIEVABLE`,
`TARGET_NOT_REACHABLE_WITHIN_SAFE_HEADROOM`; ending inventory P50 12 (util 86%); hits target
1%; gross impact P50 $0; approvals 17; holding-cost savings P50 ~$1,202; depreciation savings
P50 ~$978; dealer-funded discount ~$9,323. Plan comparison shows Margin Protect (conservative)
/ Balanced / **Capacity First ★** (aggressive, recommended). The card states plainly that the
most aggressive safe plan still does not reach the target — it does not imply a guarantee.

## 7. No outputs changed — numerical comparison

| | Before (Phase 5) | After (Phase 5.1) |
| --- | --- | --- |
| Selected vehicle IDs | V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001 | **identical** |
| Excluded vehicle IDs | V-10003, V-10007, V-10009, V-10010, V-10011 | **identical** |
| Recommended plan | CAPACITY_FIRST | **identical** |
| Required reduction | 4 | **identical** |
| P(target achieved) | 0.0085 | **identical** |
| Ending inventory P50 | 12 | **identical** |
| Approvals | 17 | **identical** |

The workflow engine and every calculation module are byte-identical in git, so the numbers
cannot have moved. `test_improve_aging_view.py` re-asserts the selected/excluded/plan values
against the Phase 5 baseline.

## 8. Tests

```
python -m pytest tests -q          410 passed   (387 before + 20 new view tests + 3 parametrized guard cases)
python scripts/validate_schemas.py PASSED  62 checks
```

The 13 required proofs are covered: exec-summary values trace to result fields; TNA copy shows
the real gap (4); actions map only from existing fields/codes and reference counts; selected &
excluded IDs unchanged; recommended plan unchanged; the view and copy modules import no
calculation layer and call no `percentile`/`np.`/`simulate`; raw codes map to friendly labels;
the default summary has exactly five business steps; the full trace is preserved and rendered
in an expander with request/simulation ids; the assistant summary links to the workspace; no
price-publishing tool is referenced; and all Phase 4/5 tests stay green.

## 9. Screenshots reviewed (in the running app)

| View | Confirmed |
| --- | --- |
| Executive summary | 86% → 70%, 7 candidates; captured before the date move (4 to release, Not Achievable · 1%). At the current 2026-08-17 window it reads 2 to release, At Risk · ~43%, green recommendation banner |
| Target-not-achievable | renders for a not-achievable target (e.g. a 60% probe: needs 3 / can release 1 / gap 2); grounded reasons; "what would close it" |
| Recommended plan | Capacity First · Aggressive; ending/util/gross/approvals; savings; held-back note |
| Vehicles requiring action | friendly "Why" labels; raw codes + sim ids in expander |
| Vehicles protected/excluded | friendly labels + rule type (Business rule / Data limitation) |
| Five-step summary + full trace | five business steps; full 12-row trace with ids in the expander |
| Ask-the-Assistant aging result | concise: utilization→target, status, candidates, plan/prob/approvals, workspace link |

No server errors. `document.body.scrollWidth == clientWidth` → **no horizontal clipping** at a
1138 px laptop viewport; the important content (summary, achievability, next steps) appears
before any detailed table.

## 10. Known limitations

1. The recommended plan here is also the most aggressive (Capacity First); the card labels the
   stance honestly rather than implying a safer alternative would do better.
2. Excluded-vehicle age/status is read from the inventory fixture in the view (a fact lookup),
   since the `Exclusion` record carries only id, description, and reason codes.
3. Streamlit `st.dataframe` renders on a canvas, so table cell text is not in the DOM as plain
   text — verified visually and via the underlying result rather than DOM scraping.
4. The `st.components.v1.html` deprecation in the single-vehicle image path is still pending
   (out of scope; unrelated to this workspace).

## 11. Next recommended step

Wire the **conservative/recommended/aggressive** plan cards to an interactive selector so an
interviewer can flip stance and watch the ending-inventory and approval counts change — still
reading every figure from the existing per-plan result, no new calculation. Beyond that, the
standing next phase is LLM-assisted routing above the deterministic layer.
