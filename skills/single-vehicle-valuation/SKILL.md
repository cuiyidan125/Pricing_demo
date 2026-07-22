---
name: single-vehicle-valuation
description: Analyze one used vehicle and return valuation, market position, three pricing scenarios, P50/P90 sales forecasts, break-even analysis, promotional headroom, and depreciation exposure. Use when the user asks what a vehicle is worth, how to price it, how much discount room it has, how long it will take to sell, or what their break-even is.
---

# Single Vehicle Valuation

Implements `docs/product-spec.md` §13.

## When to use

Route here for single-vehicle questions (§7.1):

- "What is this vehicle worth?"
- "How much can I discount this RAV4?"
- "How long will this vehicle take to sell?"
- "What is my break-even price?"
- "Should I reprice stock 10028?"

Route elsewhere for portfolio-wide questions (`inventory-portfolio-forecast`) or event
planning (`dealer-event-promotion-planner`).

---

## Hard rules

These are not style guidance. Violating any of them defeats the product's core principle.

1. **Never state a price, duration, cost, or probability that did not come from a service
   response.** Not as an estimate, not as a range, not as a "roughly". If a number is needed
   and no service produced it, say the data is unavailable.
2. **Never call a calculation tool from unvalidated free text** (§4.2). Produce
   `single-vehicle-request.schema.json`-valid JSON first.
3. **Never fill a missing input with a plausible value.** A guessed acquisition cost produces
   a wrong floor, and the floor is a publication bar. Mark it `MISSING` and let the policy
   layer decide.
4. **Never publish or save.** Recommend only. Writes require explicit user confirmation
   through the UI (§4.3, §22.3).
5. **Quote only from `explanation_inputs`.** Every currency figure and duration in your
   narrative must appear there; the response check will fail otherwise.

---

## Step 1 — Extract and validate

Produce a `single-vehicle-request.schema.json` object.

Vehicle: VIN, year, make, model, trim, mileage, condition, accident history, title status,
drivetrain, powertrain, optional equipment, certified status.
Dealer context: dealer id, postal code, acquisition cost, reconditioning cost, transportation
cost, current price, days in inventory, floorplan rate.

For each field record `fieldProvenance`: `USER_STATED`, `MCP`, `CONFIG`, `ESTIMATED`, or
`MISSING`.

**Transcription only.** "We paid $23,500" → `acquisition_cost: 23500`, source `USER_STATED`.
Inferring a trim from a price, or a condition from tone, is `ESTIMATED` and must be labeled.

If `acquisition_cost` or `reconditioning_cost` is missing and cannot be retrieved from
`get_vehicle_cost_basis`, **stop and ask**. Without cost basis there is no floor, and a
recommendation without a floor is the exact failure §4.5 exists to prevent.

For other ambiguities, record them in `ambiguities[]` and either ask or proceed with the field
flagged — ask when the field feeds a floor, proceed when it only affects confidence.

---

## Step 2 — Retrieve

Call in parallel where independent:

| Tool | Purpose | If unavailable |
| --- | --- | --- |
| `get_vehicle_cost_basis` | cost basis | **hard stop** |
| `get_vehicle_market_position` | external anchor | internal fallback, `EXTERNAL_VALUATION_UNAVAILABLE` |
| `get_vehicle_pricing_recommendation` | external recommendation | fall back to reference price |
| `get_vehicle_comparables` | internal check | anchor only, `LOW_VALUATION_CONFIDENCE` |
| `get_market_sales_velocity` | base hazard | **hard stop** — no forecast is possible |
| `get_vehicle_inventory_age` | days in inventory | use user-stated value |
| `get_vehicle_price_history` | used headroom | headroom reported without history |
| `get_shopper_engagement` | hazard adjustment | drop the term, reduce confidence |
| `get_dealer_pricing_policy` | floors, approval thresholds | config defaults |

Check freshness against the injected `as_of` (§21). Stale data degrades analysis and blocks
publication; it does not stop the analysis.

---

## Step 3 — Valuate

Call `domain/valuation.py`. See `docs/valuation-methodology.md`.

The external source anchors the number; the internal comparable-based estimate runs
independently as a check. Divergence above 5% raises `EXTERNAL_PROVIDER_VARIANCE` and lowers
confidence; above 10% it also widens the range. **Divergence never moves the point estimate.**

Below 5 usable comparables the internal check is not computed at all — a weighted median of
three listings is noise presented as a second opinion.

---

## Step 4 — Simulate

One seeded call to `simulation/` covering all three pricing scenarios, so they are comparable
(D2). Returns a draw matrix; `domain/summarize.py` produces every percentile.

Never combine percentiles across quantities to synthesize a figure. Net economic value is
summarized from draws, not computed from P50 costs (§12.5).

---

## Step 5 — Analyze

| Output | Module |
| --- | --- |
| Sales forecast, sale probabilities, projected age | `domain/sales_forecast.py` |
| Depreciation — value at sale and loss, both full percentile sets | `domain/depreciation.py` |
| Cash holding cost and slot opportunity cost, **reported separately** | `domain/holding_cost.py` |
| Break-even, minimum safe transaction and list prices | `domain/break_even.py` |
| Promotional headroom and the discount ladder | `domain/promotion.py` |

Only cash holding cost enters break-even (D3). Slot opportunity cost is imputed and appears in
net economic value and the discount optimization only.

---

## Step 6 — Policy

`policy/` runs over the assembled result and may only add warnings, approvals, and bars. It
never alters a computed number: a price violating a floor is reported unchanged next to a
`BLOCKING` warning, never quietly raised.

---

## Step 7 — Present

Return `single-vehicle-result.schema.json`. In the narrative:

- Lead with the recommendation and the strategy it assumes.
- State the market position in terms the manager uses — deal rating and price-to-market.
- Name the **binding constraint** when a floor is active. "Priced at the policy floor" is
  actionable; "priced at $24,995" alone is not.
- Give both tails for anything risk-bearing, in the correct direction: P90 for days to sale
  and depreciation loss, P10 for transaction price and net value.
- Say plainly when confidence is low and which factor caused it.
- Never present the forecast as a prediction. It is a configured prototype simulation.

---

## Worked routing example

> "Analyze this 2022 Toyota RAV4 XLE with 42,000 miles. We paid $23,500 and spent $1,200 on
> reconditioning. It has been in inventory for 37 days. Tell me what it is worth, how much
> discount room we have, and the expected P50 and P90 sales time."

Extract: year 2022, make Toyota, model RAV4, trim XLE, mileage 42000, acquisition_cost 23500,
reconditioning_cost 1200, days_in_inventory 37 — all `USER_STATED`. VIN missing; segment and
powertrain resolved from inventory as `MCP`. Transportation cost missing → retrieve from
`get_vehicle_cost_basis`.

Requested outputs: `VALUATION`, `PROMOTIONAL_HEADROOM`, `SALES_FORECAST`. Run all steps;
report all three, plus any warning at MEDIUM or above.
