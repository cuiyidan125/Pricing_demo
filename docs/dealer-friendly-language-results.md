# Dealer-friendly language pass — results

**Result: PASS.** The interface now reads for a dealer, used-vehicle manager, or performance
manager without machine-learning, simulation, or schema knowledge. Business meaning leads;
P10/P50/P90 sit in parentheses; raw codes and IDs moved to collapsed audit sections. **No
number, vehicle selection, plan, warning, or approval changed** — verified in-browser and by
test. This was copy, labels, hierarchy, and explanation only.

**Companion to** `docs/dealer-friendly-language-plan.md`.

---

## Files created
- `src/pricing_agent/views/terminology.py` — the one centralized copy module (metric labels +
  definitions, plan/strategy/state/feasibility names, warning + approval labels, glossary,
  table columns, audit-label humanizer). Re-exports the reason/exclusion maps.
- `src/pricing_agent/views/glossary.py` — the shared "How to read these estimates" expander.
- `tests/unit/test_terminology.py` — 39 proofs (numbers/selection/plan unchanged; no
  snake_case or raw codes in default labels; business-before-P; glossary wording; no MDS; no
  publish; centralized use).
- `docs/dealer-friendly-language-{plan,results}.md`.

## Files modified
- `views/assistant_home.py`, `views/dashboard.py`, `views/vehicle_detail.py`,
  `views/promotion.py`, `views/improve_aging.py`, `views/improve_aging_copy.py`, `ui_components.py`.
- `tests/unit/test_improve_aging_view.py` (two label assertions updated to the new wording).
- `README.md`, `docs/demo-script.md`.

## Files NOT changed (verified clean in git)
Skills, SKILL.md, `domain/`, `simulation/`, `policy/`, `mcp_clients/`, `agents/` (routing),
the Improve Aging engine + candidate selection, `schemas/`, mocks, config.

---

## Centralized terminology module

`terminology.py` is the single source; views import `terminology as T` and read a label
instead of hand-building one. A test asserts every view imports it, and that plan/strategy/
state/feasibility names resolve only through it. Reason-code and exclusion maps live in
`improve_aging_copy` and are re-exported through `terminology`.

## P10 / P50 / P90 — before → after (examples)

| Before | After |
| --- | --- |
| P50 gross | **Expected front-end gross (P50)** |
| Days to sell · P90 65 days | **Expected days to sale (P50)** · Conservative (P90) 65 days |
| P50 net value / P10 net value | **Expected total economic value (P50)** / **Downside total economic value (P10)** |
| Ending utilization (P50) | **Expected lot capacity used (P50)** |
| Ending inventory (P50) | **Expected ending inventory (P50)** |
| Sold in 30d | **Chance of selling within 30 days** |
| Hits target / P(target achieved) | **Likelihood of reaching the target** / **Target likelihood** |

Every primary label leads with the business meaning; the P-term is parenthesised, never first.
A regex test enforces this across all five views.

## Page-by-page

- **Ask the Assistant** — input "What are you trying to decide?", button "Get recommendation";
  states via friendly labels; plan/strategy/feasibility names humanised.
- **Price Inventory** — Recommended asking price · Estimated market value · Expected front-end
  gross (P50) · Expected days to sale (P50) · Break-even price · Lowest safe asking price ·
  Maximum safe discount. Sections: Time on lot · Profit and sales-speed trade-off · Financial
  safety · How price reductions affect value · Comparable vehicles. Pricing table reordered to
  the decision order and relabelled. Rationale/warning codes behind "View technical reason codes".
- **Acquire Inventory** — Units on lot · Lot capacity used · Over 90 days on lot · Cash tied up
  in inventory · Priced below break-even. Tabs: Lot today · Inventory outlook · Vehicles
  needing attention. One-sentence caption above each non-obvious table.
- **Merchandise Inventory** — "Compare sale-event approaches"; plan names via terminology
  (Prioritize profit protection / Balance sales and profit / Prioritize freeing inventory
  space); "Target likelihood"; states plainly a plan improves the odds and does not guarantee
  sales.
- **Improve Aging** — kept the dealer-first hierarchy; five dealer-facing steps (Review the lot
  → Identify vehicles requiring action → Evaluate pricing options → Build the sale-event plan →
  Create the dealer action plan); friendly capacity/target/likelihood/plan labels; skill names
  only in the audit trace.

## Charts (labels only, data untouched)

Aging timeline legend "Days on the lot" → **Time on lot**, "Projected to sale (P50)" →
**Expected time to sale (P50)**, x-axis "Days since acquisition" → **Days on lot**. Pricing
scatter/ladder axes: "P50 days to sale" → **Expected days to sale (P50)**, "P50 net economic
value ($)" → **Expected total economic value (P50), $**. No "percentile" as a primary label.

## Reason-code translations added

All selection and exclusion codes now have dealer-friendly labels (e.g. `CURRENTLY_OVER_90_DAYS`
→ "Already over 90 days on lot", `RECENTLY_ACQUIRED` → "Recently acquired — protect the current
strategy", `DUPLICATE_INVENTORY` → "Similar vehicles are competing for the same demand"). Raw
codes remain in a "View technical reason codes" expander on every page that shows reasons.

## Warning & approval copy

Warnings show a friendly label plus the existing message and remediation (risk / why / what to
do); the raw code moves to the audit expander. Approvals read "Manager review required" with the
triggering-boundary sentence, and **no role is invented** — the result names none.

## Glossary added

"How to read these estimates" expander on Price, Acquire, Merchandise, and Improve Aging:
Expected (P50) = median; Conservative (P90) = a cautious estimate, most outcomes fall within it,
**not a guarantee and not the worst possible case**; Downside (P10); plus Days on lot, Expected
days to sale, Break-even price, Lowest safe asking price, Total economic value, Lot capacity
used, Human approval. Only terms used in the UI.

## Numerical baseline — unchanged

| Scenario | Baseline (before) | After |
| --- | --- | --- |
| Price V-10001 | 28,995 / 29,195 / 28,400 / P50 30 / P90 65 / gross 2,597 / break-even 26,148 | **identical** |
| Acquire | 12 units · 86% · 2 open · 3 below break-even · cash 26,765 | **identical** |
| Merchandise (Summer 70%) | AT_RISK · 43% · required 2 · CAPACITY_FIRST · 1/3/5 | **identical** |
| Improve Aging | selected 7, excluded 5, CAPACITY_FIRST, required 2, 43%, ending 10, 17 approvals | **identical** |

Selected: V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001 — **unchanged**.
Excluded: V-10003, V-10007, V-10009, V-10010, V-10011 — **unchanged**. Recommended plan
CAPACITY_FIRST — **unchanged**. A test re-asserts these against the baseline.

## Validation

```
python -m pytest tests -q          455 passed   (410 before + 39 terminology + 6 others)
python scripts/validate_schemas.py PASSED  62 checks
```

## Screenshots reviewed (running app)

Price Inventory headline metrics, life-on-lot, pricing trade-off, financial safety, comparable
vehicles; Acquire forecast/KPIs; Merchandise plan comparison; Improve Aging executive summary
and vehicle-action table; glossary; audit details. **No horizontal clipping** (`scrollWidth ==
clientWidth`) on any page at a laptop viewport; primary recommendations are readable without
opening an audit expander; **no server errors**.

## Remaining terms not translated (deliberately)

- "Break-even price" and "Maximum safe discount" are kept as the clearest dealer terms (with a
  clarifying caption) rather than longer paraphrases.
- The dashboard lot-table "Suggested action" values come from the portfolio skill's own action
  map (already dealer-worded); left as-is.
- Streamlit `st.dataframe` renders cells on a canvas, so table text is not in the DOM — verified
  visually rather than by DOM scraping.

## Known limitations

- Some deep audit strings (simulation seed, model label) remain technical by design inside
  audit expanders.
- The pricing scatter still encodes plan by marker; a colour legend keyed to the friendly plan
  name is a possible refinement.

## Next recommended step

A short "How this forecast should be interpreted" note on the Acquire and Merchandise forecast
charts (mirroring the glossary), and a colour-coded legend on the pricing trade-off scatter —
both copy-only, no calculation.
