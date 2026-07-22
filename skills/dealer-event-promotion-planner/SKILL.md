---
name: dealer-event-promotion-planner
description: Build a portfolio-level sale-event promotion plan. Determines how many vehicles must sell to hit an inventory or utilization target, which vehicles to discount and by how much, which to protect, whether the target is achievable, and the gross and capacity impact of three alternative plans. Use for sale events, inventory-reduction targets, or promotional discount planning.
---

# Dealer Event Promotion Planner

Implements `docs/product-spec.md` §15.

## When to use

- "Create a July 4th promotion plan."
- "I need to reduce inventory utilization to 70 percent."
- "Which cars should I discount for Christmas?"
- "How much promotion budget is required to clear 25 vehicles?"

---

## Hard rules

1. **Resolve exact dates before anything else** (§15.2). "Starting in two days" is never
   carried forward. Resolve through `get_sales_event_calendar` or ask. Every downstream figure
   depends on the event window length.
2. **Never discount below the minimum safe list price.** Exceeding safe headroom is a
   `BLOCKING` warning, not a tradeoff to weigh.
3. **Never reimplement headroom, break-even, or forecasting** (§28). Call the shared modules.
4. **Never activate a promotion.** Plans are recommendations; activation requires explicit
   user confirmation and, where §22.2 applies, manager approval.
5. **Always return all three plans**, even when one is clearly better. The choice between
   margin and capacity belongs to the general manager, not to this skill.

---

## Step 1 — Objective

Produce `promotion-objective.schema.json`: event name, resolved start and end dates,
`date_source`, target utilization or target ending inventory, optimization priority, discount
budget, minimum gross target, exclusions, approval policy.

If the user gives a utilization target, convert it in step 2 — do not assume they mean the
same basis the system uses. If they give neither a utilization nor an inventory target, ask.
There is no sensible default for how empty a lot should be.

---

## Step 2 — Target and baseline

```text
target_ending_inventory = total_physical_slots × target_utilization           (D6)

projected_inventory_without_promotion =
    current_inventory + confirmed_inbound − baseline_expected_sales − other_expected_exits

incremental_promotional_sales_required =
    projected_inventory_without_promotion − target_ending_inventory
```

Three points that matter:

- **Physical slots, not effective slots.** "70% utilization" means 70% of the lot.
- **Only `confirmed_inbound` enters the flow.** `reserved_slots` is a superset of it; counting
  both would inflate the target by the entire inbound volume. `reserved_not_inbound` is
  deducted separately.
- **`baseline_expected_sales` is a distribution**, from the no-promotion baseline simulation
  under the shared seed. The requirement is therefore uncertain, and step 7 reports that
  uncertainty rather than a single unit count.

`other_expected_exits` has no data source and is assumed zero. Because it enters with a
negative sign, that assumption makes the requirement a conservative overestimate — say so if
the number looks high to the user.

---

## Step 3 — Exclude

Apply §15.6 exclusions before scoring, recording a reason for each
(`docs/promotion-optimization-methodology.md` §4).

The rule worth flagging to users: vehicles whose **P50 days to sale falls before the event
start** are excluded as likely to sell anyway. Discounting a vehicle that would have sold at
full price is a pure gross giveaway, and it is the most common way an event destroys margin.

If fewer than `min_safe_candidates` (5) survive, raise
`INSUFFICIENT_SAFE_PROMOTION_CANDIDATES` and stop before building plans that cannot work.

---

## Step 4 — Score

Score each surviving candidate on aging, projected age, depreciation risk, holding cost, price
above market, deal rating, engagement, headroom, slot opportunity cost, duplicate inventory,
and inbound replacement. Report component contributions, not just the total.

All signals come from the shared modules. None is recomputed here.

---

## Step 5 — Discount ladder

Per candidate, compute the ladder in `docs/promotion-optimization-methodology.md` §5.

`economically_sensible_discount` is found by **re-simulating each rung** and taking the argmax
of P50 net economic value — not by formula. The point where faster turn stops paying for the
margin it costs depends on the specific vehicle's holding cost, depreciation rate, and price
position. Retain the evaluated ladder so the chosen rung is auditable.

Slot opportunity cost is included in this optimization (D3) and excluded from the floor.

---

## Step 6 — Build three plans

`MARGIN_PROTECT`, `BALANCED`, `CAPACITY_FIRST` (§15.8), all from the same candidate pool and
the same seed as the baseline.

Each is greedy over the ranked pool until the P50 requirement is met, then **re-simulated as a
set** — per-vehicle effects do not aggregate independently, and cannibalization only appears
when the selection is evaluated jointly.

Enforce budget during selection. Partner-funded incentives are excluded from the dealer budget
but included in the customer-facing price. When the target cannot be met within budget, raise
`PROMOTION_BUDGET_EXCEEDED` and return the plan truncated at budget rather than suppressing it.

Raise `PRICE_CANNIBALIZATION_RISK` when a plan discounts more than one unit in a duplicate
group.

---

## Step 7 — Feasibility

Classify per `docs/promotion-optimization-methodology.md` §8 using P(target achieved).

When the status is `NOT_ACHIEVABLE`, raise `UNREALISTIC_INVENTORY_TARGET` and return the
§15.9 alternatives **quantified**: how many additional days, how many percentage points of
utilization, how many dollars of budget, how many wholesale units. Returning "not achievable"
without them leaves the merchandising manager exactly where they started.

---

## Step 8 — Present

Return `promotion-plan-result.schema.json`.

- Lead with feasibility. It is the question actually being asked.
- Give the required units and the achievable units side by side.
- For each plan: units, ending utilization, probability of hitting the target, and gross
  impact. Gross impact is negative for capacity-first plans; say so directly rather than
  framing a real cost as a "tradeoff".
- Name the vehicles being protected and why — the plan's discipline is as informative as its
  discounts.
- State every approval the recommended plan requires before the user asks.
