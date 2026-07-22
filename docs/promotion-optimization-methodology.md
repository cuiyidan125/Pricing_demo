# Promotion Optimization Methodology

**Companion to** `docs/product-spec.md` §15.
Implements **D6** (capacity basis) and reuses the shared modules per §28.

---

## 1. Target calculation

```text
target_ending_inventory =
    total_physical_slots × target_utilization                              (D6)

projected_inventory_without_promotion =
    current_inventory
  + confirmed_inbound
  − baseline_expected_sales
  − other_expected_exits

incremental_promotional_sales_required =
    projected_inventory_without_promotion − target_ending_inventory
```

Three points that §15.4 leaves open:

* **Capacity basis (D6).** Physical slots, not effective slots. "70% utilization" means 70% of
  the lot.
* **No double counting.** `reserved_slots ⊇ confirmed_inbound`, so only `confirmed_inbound`
  enters the flow; `reserved_not_inbound` is deducted separately. Counting both would inflate
  the promotional target by the entire inbound volume.
* **`baseline_expected_sales` is a distribution, not a number.** It is the P50 units sold
  within the event window from the no-promotion baseline simulation. The requirement is
  therefore also a distribution, and §9 reports its uncertainty rather than a single unit
  count.

`other_expected_exits` has no data source and is assumed zero in the MVP
(`open-questions.md` C1). Because it enters the target with a negative sign, assuming zero
makes the promotional requirement a **conservative overestimate**.

---

## 2. Baseline

Everything is measured against a no-promotion baseline simulated under the same seed (D2):

```text
baseline = simulate(inventory, current_prices, event_window, seed)
plan_k   = simulate(inventory, plan_k_prices,  event_window, seed)
incremental_units[k] = plan_k.units_sold − baseline.units_sold      per draw
```

Computed per draw, then summarized. Sharing the seed means the difference between a plan and
the baseline reflects the price change rather than sampling noise — without it, a plan with no
discounts would show nonzero "incremental" units.

---

## 3. Candidate scoring

Per §15.5. Each vehicle scores 0–100; all inputs come from shared modules, none recomputed.

| Signal | Source | Direction |
| --- | --- | --- |
| Days in inventory | `get_vehicle_inventory_age` | older → higher |
| P50 / P90 projected total age | `domain/sales_forecast.py` | longer → higher |
| P90 depreciation loss | `domain/depreciation.py` | larger → higher |
| P90 cash holding cost | `domain/holding_cost.py` | larger → higher |
| Price above market | `domain/valuation.py` | further above → higher |
| Deal rating | `get_vehicle_market_position` | poorer → higher |
| Shopper engagement | `get_shopper_engagement` | lower → higher |
| Promotional headroom | `domain/promotion.py` | more → higher |
| Slot opportunity cost | `domain/holding_cost.py` | higher → higher |
| Duplicate inventory | computed, see §7 | more duplicates → higher |
| Inbound replacement | `get_inbound_inventory` | replacement arriving → higher |

Weights in `config/assumptions/promotion.yaml`, configured rather than fitted.

---

## 4. Exclusions

§15.6, applied before scoring. Every exclusion is reported with its reason — a plan is not
reviewable if the reader cannot see what was left out.

| Rule | Threshold |
| --- | --- |
| Recently acquired | days in inventory < `min_promotion_age_days` (default 21) |
| Already a strong deal | deal rating `GREAT`, or price-to-market ≤ good-deal threshold |
| High-demand scarce | supply-to-sales ratio below `scarcity_threshold` |
| Likely to sell anyway | **P50 days to sale < days until event start** |
| No safe headroom | `max_safe_discount ≤ 0` |
| Insufficient data | missing cost basis, or valuation confidence `LOW` |
| Already in a campaign | `campaign_participation` active |
| Policy exclusion | listed in `get_dealer_pricing_policy.excluded_from_promotion` |

The "likely to sell anyway" threshold is undefined in §15.6; the P50-before-event-start rule
is this design's choice (`open-questions.md` C4). Discounting a vehicle that would have sold at
full price is a pure gross giveaway, and it is the most common way an event destroys margin.

---

## 5. Discount ladder

Per candidate (§15.7), all from `domain/break_even.py` and `domain/promotion.py`:

```text
minimum_safe_transaction_price = max(accounting_break_even, policy_floor,
                                     financing_constraint, risk_floor)
minimum_safe_list_price        = minimum_safe_transaction_price ÷ (1 − expected_discount_rate)

max_accounting_discount        = current_list_price − accounting_break_even_list_equivalent
max_safe_discount              = current_list_price − minimum_safe_list_price
economically_sensible_discount = argmax over the ladder of P50 net economic value
recommended_promotion_discount = min(economically_sensible_discount,
                                     max_safe_discount,
                                     budget_constrained_discount)
remaining_headroom             = max_safe_discount − recommended_promotion_discount
```

**`economically_sensible_discount` is found by simulation, not by formula.** The vehicle is
re-simulated at each rung of a configured discount ladder ($250 increments to `max_safe_discount`),
and the rung maximizing P50 net economic value is selected. This is the only defensible way to
locate the point where faster turn stops paying for the margin it costs, because that tradeoff
depends on the holding cost, depreciation rate, and price elasticity of the specific vehicle.

Slot opportunity cost is included here, per D3 — it belongs in an economic optimization. It is
excluded from `minimum_safe_transaction_price`, also per D3, because an imputed cost must never
raise a price floor.

---

## 6. Plan construction

Three plans (§15.8), all built from the same candidate pool and the same seed.

| Plan | Selection | Discount |
| --- | --- | --- |
| `MARGIN_PROTECT` | Highest-scoring candidates only, until target met or pool exhausted | min(economically sensible, 50% of max safe) |
| `BALANCED` | Candidates above the median score | economically sensible discount |
| `CAPACITY_FIRST` | Every eligible candidate, ordered by score | max safe discount, subject to budget |

Each is greedy over the ranked pool, adding vehicles until P50 incremental units meets the
requirement or the pool is exhausted, then re-simulating the whole selection jointly — because
per-vehicle effects do not aggregate independently, and cannibalization (§7) only appears when
the selection is evaluated as a set.

Budget is enforced during selection:
`Σ dealer_funded_discount ≤ promotion_budget`, with partner-funded incentives excluded from the
dealer budget but included in the customer-facing price.

`PROMOTION_BUDGET_EXCEEDED` is raised when the target cannot be met inside budget — the plan is
still returned, truncated at the budget, rather than suppressed.

---

## 7. Cannibalization

§20.4 defines `PRICE_CANNIBALIZATION_RISK` but §15.5 never defines "duplicate inventory". This
design uses: **same model, model year ± 1, same trim group, mileage within 15,000.**

Within a duplicate group, discounting one unit reduces the sale hazard of the others by a
configured cross-elasticity. Because plans are simulated jointly, this appears automatically in
the plan's incremental units rather than needing a separate adjustment.

`PRICE_CANNIBALIZATION_RISK` is raised when a plan discounts more than one unit in a duplicate
group. Both the grouping rule and the cross-elasticity are assumptions
(`open-questions.md` C4).

---

## 8. Feasibility

Per §15.9:

```text
required_incremental_units      from §1
max_safe_candidate_pool         count of candidates surviving §4 with max_safe_discount > 0
P50_achievable_incremental      median incremental units, CAPACITY_FIRST plan
conservative_achievable         P10 incremental units, CAPACITY_FIRST plan
P(target achieved)              count(draws : ending_inventory[d] ≤ target) ÷ draw_count
```

| Feasibility | Condition |
| --- | --- |
| `ACHIEVABLE` | P(target achieved) ≥ 0.70 under `BALANCED` |
| `ACHIEVABLE_WITH_MARGIN_COST` | ≥ 0.70 only under `CAPACITY_FIRST` |
| `AT_RISK` | 0.30 – 0.70 under `CAPACITY_FIRST` |
| `NOT_ACHIEVABLE` | < 0.30 under `CAPACITY_FIRST` |

`NOT_ACHIEVABLE` raises `UNREALISTIC_INVENTORY_TARGET` and returns the §15.9 alternatives —
longer campaign, revised target, additional budget, wholesale disposition, reduced inbound,
manager-approved loss minimization — each quantified: how many additional days, how many
percentage points, how many dollars.

Returning "not achievable" without the quantified alternatives would leave the merchandising
manager exactly where they started.

---

## 9. What the plan does not model

* **Advertising reach and creative.** Event lift is a single configured multiplier; a promotion
  nobody sees performs like no promotion, and this model cannot tell the difference.
* **Competitor response.** Other dealers also run July 4th events. Cross-dealer response is
  entirely absent.
* **Lift transferability.** How much a past event's lift predicts a different event type or
  season is unaddressed (`open-questions.md` C3).
* **Trade-in and finance-and-insurance profit.** Only front-end gross is modeled, so a plan
  that trades front-end gross for volume understates its own return.
