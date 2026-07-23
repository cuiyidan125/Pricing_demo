# Improve Aging — count reconciliation — results

Presentation-only fix on `fix/improve-aging-count-reconciliation`. The workspace and the
assistant card conflated three different counts; they now agree, with no change to selection,
classification, calculations, approvals, or any number the engine produced.

## What changed (view + assistant summary only)

| Surface | Before | After |
| --- | --- | --- |
| Exec-summary metric | "Vehicles requiring action" = **7** (was the analysed count) | "Aging vehicles analysed" = **7**, with a caption: *"Of 7 analysed, 5 need immediate action and 2 have no immediate action (eligible for a sale event)."* |
| Action table | "Vehicles requiring action" — **5 rows** (filter dropped the 2 no-action analysed vehicles) | "Analysed aging vehicles" — **all 7 rows**, with an *Attention* column; the two no-action vehicles show **"No immediate action — eligible for a sale event"** |
| Recommended-plan card | "Manager reviews required" = **17** (approval records) | "Vehicles needing a manager review" = **5**, detail "**17** review item(s)" |
| Warnings & approvals caption | "These recommendations require a manager review…" | "**5** vehicle(s) need a manager review before anything changes, carrying **17** individual review item(s) in total." |
| Assistant chat card | "Vehicles requiring action 7 / 7 analysed" and "**17** manager review(s) required" | "Aging vehicles analysed 7 / 5 need action now" and "**5** vehicle(s) need a manager review (17 review item(s))" |

New reconciled fields in the assistant summary: `immediate_action_count`,
`no_immediate_action_count`, `review_vehicle_count`, `review_item_count`. The raw
`approvals_required` = 17 is retained unchanged.

## Verified — browser smoke, both scenarios

- **No event** ("Which aging vehicles should I promote?"): 7 analysed, 5 immediate, 2 no
  immediate. The table renders all seven; the two formerly hidden vehicles — **2021 Subaru
  Outback (V-10008)** and **2022 Toyota RAV4 (V-10001)** — appear labelled *No immediate action
  — eligible for a sale event*. Review line: **5 vehicles / 17 items**.
- **With event** (Summer Clearance default): 7 analysed, all 7 immediate (the two become
  EVENT_PROMOTION), 0 no-immediate. Review line: **5 vehicles / 17 items**.

## Preserved (unchanged)

- Selected 7 `[V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001]`; excluded 5
  `[V-10003, V-10007, V-10009, V-10010, V-10011]`; recommended plan `CAPACITY_FIRST`.
- Every per-vehicle `recommended_action` (V-10008/V-10001 stay `NO_ACTION` without an event).
- `approvals_required` = 17 records across 5 vehicles; all prices, break-evens, probabilities.

## Checks

- `pytest`: **460 passed** (was 455; +5 reconciliation tests in
  `tests/unit/test_improve_aging_view.py`).
- `scripts/validate_schemas.py`: **62 checks passed**.
- No calculation added to the view/summary; no Market Days Supply; no price-publishing path;
  no console or server errors in the smoke run.
