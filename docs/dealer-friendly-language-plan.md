# Dealer-friendly language pass — plan

**Branch:** `feature/dealer-friendly-language` (off the committed Summer Clearance date change).
**Scope:** copy, labels, information hierarchy, and explanation only. No calculation, skill,
workflow, selection, schema, MCP, mock, routing, or number changes. Every displayed number
keeps coming from the existing validated result. **No Market Days Supply.**

---

## 1. Numerical baseline (must be identical after the pass)

Captured at `as_of = 2026-07-29`, the committed demo scenario.

| Scenario | Key figures |
| --- | --- |
| **Price Inventory** (V-10001) | current 28,995 · recommended 29,195 · market 28,400 · P50 days 30 · P90 days 65 · P50 gross 2,597 · break-even 26,148 · min-safe 26,846 · headroom 2,349 · rating FAIR · strategy MAXIMIZE_GROSS · warning `P90_PROJECTED_INVENTORY_AGE_OVER_90_DAYS` |
| **Acquire Inventory** | 12 units · 86% util · 2 open slots · 3 below break-even · cash tied 26,765 · 30-day units P50 4 · 90-day units P50 9 · warnings HIGH_PERCENTAGE_BELOW_BREAK_EVEN, INBOUND_CAPACITY_CONFLICT, FUTURE_ACQUISITION_DATA_UNAVAILABLE |
| **Merchandise** (Summer, 70%) | AT_RISK · 43% · required 2 · plan CAPACITY_FIRST · plan counts 1/3/5 |
| **Improve Aging** (Summer, 70%) | ROUTED · selected 7 (V-10005,12,02,06,04,08,01) · excluded 5 (V-10003,07,09,10,11) · plan CAPACITY_FIRST · required 2 · 43% · ending P50 10 · 17 approvals · actions WHOLESALE 3 / MANAGER 2 / EVENT_PROMOTION 2 / NO_ACTION 2 / PROTECT 3 |

A test re-asserts each of these after the copy pass.

---

## 2. Centralized terminology module

Create **`src/pricing_agent/views/terminology.py`** as the single source of user-facing copy.
It absorbs and extends the two existing partial modules:

- `views/improve_aging_copy.py` — already holds reason/exclusion/action labels, candidate
  categories, `next_steps`, `recommendation_statement`. Its maps move into `terminology.py`;
  `improve_aging_copy` re-exports them for compatibility so the aging view keeps working.
- `views/workflow_copy.py` — workflow titles/subtitles; left as-is (page identity), but the
  glossary/step/state copy it lacks is added to `terminology.py`.

`terminology.py` exposes:

| Group | Content |
| --- | --- |
| `METRIC` | label + one-line definition per metric (e.g. `expected_days_to_sale` → "Expected days to sale (P50)") |
| `TABLE_COLUMNS` | friendly column headers, decision-ordered |
| `REASON_LABELS` / `EXCLUSION_LABELS` | from `improve_aging_copy` (verified against real codes) |
| `WARNING_LABELS` | code → action-oriented label (risk / why / what to do handled by existing message+remediation) |
| `APPROVAL_LABELS` | approval_type → "Manager review required" + triggering-boundary sentence |
| `PLAN` | MARGIN_PROTECT/BALANCED/CAPACITY_FIRST → friendly name + one-line trade-off |
| `STRATEGY` | MAXIMIZE_GROSS/BALANCED/INCREASE_VELOCITY → "Protect profit" / "Balance profit and sales speed" / "Sell faster" |
| `STATE` | workflow/analysis states → "Analysis completed", "More information is needed", … |
| `STEP` | five dealer-facing steps for the aging workflow |
| `GLOSSARY` | "How to read these estimates" entries |
| helpers | `pct_label`, `audit_label` (snake_case → Title Case for audit only) |

A test asserts the views import labels from `terminology` and contain no ad-hoc snake_case or
raw-enum display strings.

---

## 3. Conventions

- **Business meaning first, statistic in parentheses:** `Expected days to sale (P50)`,
  `Conservative days to sale (P90)`, `Downside total economic value (P10)`.
- **P-definitions** (glossary, consistent everywhere): P50 = expected/median; P90 = a
  conservative planning estimate, most outcomes fall within it, **not** guaranteed and **not**
  the worst case; P10 = a downside estimate. Never "worst case", "guaranteed", or "average"
  (unless a true mean).
- **Progressive disclosure:** dealer decision + recommendation + business explanation +
  financial impact + next action + warning/approval by default; P-defs, raw codes, ids,
  trace, assumptions inside expanders (`How to read these estimates`, `View technical reason
  codes`, `View full workflow execution trace`, `View audit details`).
- Currency as `$`, probabilities/utilization as `%`, time with `days`.

---

## 4. Key term conversions (verified against the repo)

Forecast/probability, pricing, inventory/aging, financial, promotion, and workflow terms per
the brief — implemented in `terminology.py`. Notable ones actually present in the UI:

`Current list` → **Current asking price** · `Recommended` → **Recommended asking price** ·
`Market value` → **Estimated market value** · `P50 gross` → **Expected front-end gross (P50)** ·
`Days to sell / P50 days` → **Expected days to sale (P50)** · `P90` → **Conservative … (P90)** ·
`Break-even` → **Break-even price** · `Minimum safe list price` → **Lowest safe asking price** ·
`Maximum safe discount` → **Maximum safe discount** (kept, with caption) · `Net economic value`
→ **Total economic value** · `Utilization` → **Lot capacity used** · `Units on lot` → **Units
on lot** (kept) · `Over 90 days` → **Over 90 days on lot** · `Units to release` → **Vehicles
to sell or release** · `Feasibility` → **Target likelihood** · `Hits target` → **Likelihood of
reaching the target** · plan/strategy/state per the maps above. `Gross against turn` →
**Profit and sales-speed trade-off** · `Discount ladder` / `Where discounting stops paying` →
**How price reductions affect value**.

Reason/exclusion codes: the full dealer-friendly map from the brief (already largely present
in `improve_aging_copy`) — verified against the codes the app actually emits.

## 5. Table column reorders

- **Pricing comparison** (vehicle detail "Gross against turn"): Pricing approach · Recommended
  asking price · Expected days to sale (P50) · Chance of selling within 30 days · Expected
  front-end gross (P50) · Expected total economic value (P50) · Downside total economic value
  (P10) · Approval needed. (Only columns the result already provides; nothing computed.)
- **Vehicle-action** (aging): Vehicle · Days on lot · Recommended action · Why action is
  needed · Current asking price · Recommended asking price · Expected days to sale (P50) ·
  Conservative days to sale (P90) · Approval needed.
- **Lot table** (dashboard), **candidate/excluded** (aging), **comparables**, **plan
  comparison** (promotion): friendly headers; ids/raw codes to audit expanders.

## 6. Charts (labels only, data untouched)

- Aging timeline: legend `Days on the lot` / `Projected to sale (P50)` → **Time on lot** /
  **Expected time to sale (P50)**; x `Days since acquisition` → **Days on lot**.
- Vehicle detail gross/turn scatter & discount chart: `P50 days to sale` → **Expected days to
  sale (P50)**; `P50 front-end gross ($)` → **Expected front-end gross (P50), $**; `P50 net
  economic value ($)` → **Expected total economic value (P50), $**; `Discount off list ($)` →
  **Discount off asking price, $**.
- Dashboard revenue/aging charts: `Revenue ($)` kept; percentile-labelled series get business
  labels with the P-term in parentheses. No "percentile" as a primary label.

## 7. Glossary — "How to read these estimates"

Expected (P50), Conservative (P90), Downside (P10), Days on lot, Expected days to sale,
Break-even price, Lowest safe asking price, Total economic value, Lot capacity used, Human
approval — brief, business-worded, only terms used in the UI.

## 8. Page-by-page

1. **Ask the Assistant** — input `Your question` → **"What are you trying to decide?"**;
   button `Analyze` → **Get recommendation**; result leads with understood → recommendation →
   why → warning/approval → next action → link; states use `STATE` labels; routing detail into
   `View audit details`.
2. **Price Inventory / Vehicle Detail** — headline metrics relabelled; captions for life-on-lot,
   pricing approach, financial safety, comparables; pricing table reordered; discount ladder
   retitled; glossary expander; audit expander keeps ids/assumptions.
3. **Acquire Inventory** — "Inventory outlook"; today/30/90 framing; friendly KPI + table
   labels; one-sentence caption above each non-obvious table.
4. **Merchandise Inventory** — event objective framing; plan names via `PLAN`; recommended
   approach + trade-off + "target not guaranteed"; friendly columns.
5. **Improve Aging** — keep the dealer-first hierarchy; five dealer-facing steps; friendly
   labels for capacity/target/vehicles/likelihood/plan; skill names to audit only.

## 9. Tests (map to the 20 required proofs)

Numeric/selection/plan/warning/approval unchanged (re-assert baseline); no snake_case or raw
enum in default table headers/labels (AST/scan of view sources for banned patterns outside
audit expanders); raw reason codes absent from default but present in audit; business-before-
P convention (regex: any `P10|P50|P90` label has words before it and the P-term parenthesised);
glossary P-definitions worded per spec (P90 not "worst/guaranteed"); no new metric in a view
(no arithmetic operators producing displayed numbers beyond formatting); no "Market Days
Supply"; no publish; terminology centralised (views reference `terminology`); existing suite
green.

## 10. Risks / decisions

- "Maximum safe discount" and "Break-even" are retained as the clearest dealer terms (with a
  clarifying caption) rather than longer paraphrases, per principle 12 (concise).
- Warning *messages* already read reasonably (policy layer) and are numeric-bearing; I relabel
  the **code** to an action-oriented label and keep the message+remediation, without editing
  policy text (that would risk changing meaning). Raw code stays in audit.
- No metric is computed in a view; existing percent/currency formatting of result fields is
  retained.
