---
name: inventory-portfolio-forecast
description: Analyze an entire used-vehicle inventory and return portfolio valuation, 30-day and 90-day sales and revenue forecasts, capacity utilization, aging exposure, depreciation exposure, risk ranking, and per-vehicle recommended actions. Use when the user asks what their inventory is worth, how much they will sell or earn over a period, or which vehicles carry the most risk.
---

# Inventory Portfolio Forecast

Implements `docs/product-spec.md` §14.

## When to use

- "What is my total inventory worth?"
- "How much revenue will I make next month?"
- "How much should I expect to sell in 90 days?"
- "Which vehicles are creating the greatest aging risk?"
- "How much cash do I have tied up?"

---

## Hard rules

1. **Never add per-vehicle P50s to get a portfolio figure** (§14.7). Sum within each draw,
   then summarize. Adding medians credits every vehicle with a median outcome simultaneously
   and overstates the portfolio median.
2. **Never reimplement a vehicle-level calculation** (§28). Valuation, break-even,
   depreciation, holding cost, and the sales forecast come from the same modules the
   single-vehicle skill uses.
3. **Never present a run-off forecast as a full forecast.** See step 4.
4. **Never state a number the services did not produce.**

---

## Step 1 — Extract and validate

Produce `inventory-portfolio-request.schema.json`. Resolve scope (status filter, segments,
exclusions), horizons (default 30 and 90 days), and any targets the user stated — a revenue
target or a utilization target drives the risk probabilities and the corresponding warnings.

"How much will I make next month" implies a 30-day horizon and a revenue figure, not a gross
figure. If the user means gross, ask — the two differ by the entire cost basis and confusing
them is the most consequential misread in this workflow.

---

## Step 2 — Retrieve

`get_dealer_inventory`, then per vehicle: `get_vehicle_cost_basis`,
`get_vehicle_market_position`, `get_vehicle_inventory_age`. Plus `get_dealer_capacity`,
`get_inbound_inventory`, `get_market_sales_velocity`, `get_sales_event_calendar`,
`get_dealer_sales_history`.

Track coverage. Portfolio calls routinely return partial data; record every vehicle that could
not be fully analyzed in `data_coverage` rather than dropping it silently. Vehicles missing
cost basis are excluded from break-even aggregates and counted explicitly.

Below `low_forecast_confidence_coverage` (0.80), raise `LOW_PORTFOLIO_FORECAST_CONFIDENCE`.

---

## Step 3 — Value the portfolio

`domain/portfolio.py`, producing `inventory-portfolio-valuation.schema.json`.

Everything except expected transaction value is a point-in-time sum. Expected transaction
value comes from the draws, because transaction price is a distribution rather than a stored
fact.

`total_liquidation_value` is null in the MVP — §14.3 marks it "if available" and no tool
returns it.

---

## Step 4 — Forecast

**One simulation covering every vehicle**, then aggregate within draws (D2). Horizons 30 and
90 days.

The 90-day forecast adds inbound arrivals on their expected dates, aging transitions, event
lift within event windows, seasonality, wholesale disposition above the age threshold, and
capacity as a **constraint on the simulation** — arrivals that cannot physically fit are
deferred, not dropped. Modeling arrivals that cannot fit would produce an impossible ending
utilization and understate the cost of being full, which is the entire premise of the
promotion skill.

### Run-off

No MCP tool supplies planned acquisitions, so **run-off is the default path, not an edge
case.** Set `forecast_basis.mode = RUN_OFF`, raise `FUTURE_ACQUISITION_DATA_UNAVAILABLE`, and
populate `lower_bound_note`.

State the interpretation wherever the figures appear: ending inventory, utilization, and
revenue are **lower bounds**, because a real dealer replaces sold units. A general manager
reading a 90-day forecast showing utilization falling to 40% would otherwise conclude they are
about to run out of inventory, which is the opposite of what the forecast says.

---

## Step 5 — Capacity

Compute derived capacity from primitives (`docs/portfolio-forecast-methodology.md` §6).
Utilization is always measured against `total_physical_slots` (D6), and
`reserved_slots ⊇ confirmed_inbound`, so the two are never both deducted.

Warn on `PROJECTED_CAPACITY_OVER_TARGET`, `PROJECTED_CAPACITY_OVER_100_PERCENT`, and
`INBOUND_CAPACITY_CONFLICT` where inbound units have no slot to arrive into.

---

## Step 6 — Rank risk and assign actions

Risk ranking weights probability of aging, P90 depreciation loss, P90 cash holding cost,
probability of negative net value, underwater status, and **cost basis** — so that dollars at
stake drive the ordering, not risk percentage alone.

Assign exactly one action per vehicle from the decision table
(`docs/portfolio-forecast-methodology.md` §7.3), evaluated in order, first match wins, with
the matched rule recorded. `EVENT_PROMOTION` candidates from this step feed the promotion
skill directly rather than being re-derived there.

---

## Step 7 — Present

Return `inventory-portfolio-result.schema.json`.

- Lead with the answer asked for, not the full valuation dump.
- Give revenue and units as ranges. A point estimate for a 90-day portfolio forecast implies
  precision this model does not have.
- When a target was given, lead with the probability of missing it.
- Name the top risk vehicles with the dollars at stake, not just the count.
- Always state whether the forecast is `FULL` or `RUN_OFF`.
