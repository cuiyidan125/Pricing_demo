# Improve Aging — count reconciliation — plan

**Branch:** `fix/improve-aging-count-reconciliation` (off merged main; carries the Summer
Clearance dates and the dealer-friendly language). Working tree clean.

**Scope:** presentation and counting only. No change to candidate selection, action
classification, calculations, skills, workflow, approval logic, schemas, mocks, routing,
numerical outputs, or price publishing. Every figure keeps coming from the existing result;
the fix only stops the view from **conflating three different counts**.

---

## 1. Reproduced diagnosis

Request: **"Which aging vehicles should I promote?"** → Improve Aging, **no event**, `as_of
2026-07-29`.

### The seven analysed vehicles (candidates with deep single-vehicle analysis)
V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001.

### Consolidated action per vehicle (unchanged — this classification stays)
| Vehicle | Action | Approvals |
| --- | --- | --- |
| V-10005 | Wholesale / loss-min review | LOSS_MINIMIZATION, BELOW_PROJECTED_BREAK_EVEN, NEGATIVE_VALUE_RISK |
| V-10012 | Wholesale / loss-min review | (same 3) |
| V-10004 | Wholesale / loss-min review | (same 3) + AGGRESSIVE_ADJUSTMENT |
| V-10002 | Manager review | (same 3) + AGGRESSIVE_ADJUSTMENT |
| V-10006 | Manager review | (same 3) |
| **V-10008** | **No action** (no event ⇒ no promotion; hold-gross ⇒ no reprice) | — |
| **V-10001** | **No action** (same) | — |
| V-10003, V-10009 | No action (excluded) | — |
| V-10007, V-10010, V-10011 | Protect price (excluded) | — |

### The three conflated counts (the bug)
| Where | Shows | Should mean |
| --- | --- | --- |
| Exec-summary metric "Vehicles requiring action" | **7** (= `candidate_count`) | that is the **analysed** count, not the action count |
| "Vehicles requiring action" table rows | **5** (filter drops NO_ACTION/PROTECT) | hides the **2 analysed** no-action vehicles V-10008, V-10001 |
| "Manager reviews required" metric | **17** (= `len(approvals_required)` records) | **5 vehicles** need review; 17 is the count of review **items** |

So the dealer sees "7 requiring action" up top, 5 rows in the table, and "17 manager reviews"
— three numbers that do not reconcile. **With an event** (workspace default) the two no-action
vehicles become EVENT_PROMOTION, so the table shows 7 and only the approval count (17 vs 5)
still misleads.

### The two omitted vehicles
**V-10008, V-10001** — analysed, currently **No action** without an event, and **eligible for a
sale event** (they become the promoted pair when Summer Clearance is planned).

### The 17-vs-approvals discrepancy
`result.approvals_required` holds **17 records** across **5 distinct vehicles**
(V-10005:3, V-10012:3, V-10002:4, V-10006:3, V-10004:4) drawn from **4 reason types**. Only
**2** vehicles carry the *Manager review* action label; the other 3 carry *Wholesale /
loss-min review* (which also requires approval). The single number "17" is a record count
displayed where a vehicle count is expected.

---

## 2. The reconciled model (all derived from the existing result)

Compute one small breakdown from `vehicle_evidence`, `consolidated_actions`, and
`approvals_required` — no new classification:

```
analysed vehicles        = len(vehicle_evidence)                                 # 7
  immediate action       = analysed whose action ∈ {WHOLESALE…, MANAGER_REVIEW,   # 5 (no event)
                           REPRICE_NOW, EVENT_PROMOTION}                          # 7 (with event)
  no immediate action    = analysed whose action == NO_ACTION                     # 2 (no event) / 0 (with event)
promotion-eligible       = the no-immediate-action analysed vehicles when no       # V-10008, V-10001
                           event is planned (they become EVENT_PROMOTION with one)
vehicles needing review  = distinct vehicle_ids in approvals_required              # 5
review items             = len(approvals_required)                                # 17
```

Invariant, asserted by a test: `immediate_action + no_immediate_action == analysed`, and
`vehicles_needing_review == number of consolidated rows with a non-empty approvals list`.

---

## 3. The fix (presentation only)

1. **Exec summary** — relabel the ambiguous metric. "Vehicles requiring action" (which was the
   analysed count) becomes **"Aging vehicles analysed"** = 7, with a one-line reconciliation:
   *"N need immediate action; M have no immediate action (eligible for a sale event)."*

2. **"Vehicles requiring action" section** — show **all analysed vehicles**, not a filtered
   subset. The two no-immediate-action analysed vehicles appear with a clear
   **"No immediate action — eligible for a sale event"** label instead of being dropped. The
   *excluded/protected* five remain in their own "protected or excluded" section (unchanged).
   Section retitled **"Analysed aging vehicles"** with a caption stating the immediate /
   no-immediate split.

3. **Approval count** — everywhere it appears (exec summary, recommended-plan card, warnings &
   approvals): **"5 vehicles need a manager review"** with **"17 review items"** as the detail,
   instead of a bare "17". The raw records stay in the approvals table and audit.

4. **Assistant summary** (`agents/assistant.py::_improve_aging_summary` +
   `views/assistant_home.py`) — carry the same reconciled fields so the chat card agrees with
   the workspace: analysed, immediate/no-immediate, promotion-eligible, vehicles-needing-review,
   review-items.

Nothing in `workflows/improve_aging.py` (the engine), `candidate_selection.py`, the skills, or
the approval records changes. The reconciliation is a pure read over the existing result.

---

## 4. Tests (added/updated)

- Selected (7) and excluded (5) IDs unchanged; recommended plan unchanged; every consolidated
  action label unchanged (byte-for-byte per vehicle); `approvals_required` still 17 records.
- Reconciliation invariants: `immediate + no_immediate == analysed`; the two no-action analysed
  vehicles are exactly {V-10008, V-10001} in the no-event case; `vehicles_needing_review == 5`
  and `review_items == 17`.
- The "Analysed aging vehicles" section renders all 7 analysed vehicles (no analysed vehicle is
  hidden).
- No number recomputed in the view; no Market Days Supply; no publish; existing suite green.

## 5. Risks / decisions

- "No immediate action — eligible for a sale event" is a **display grouping** of the existing
  NO_ACTION classification for an analysed candidate; it is not a reclassification and does not
  touch `consolidated_actions`.
- The reconciled counts are computed in a small pure helper in the view (and mirrored in the
  agent summary) reading only existing result fields — consistent with the "views render,
  never calculate a business figure" rule (counting existing items is not a new metric).
