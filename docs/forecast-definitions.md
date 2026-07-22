# Forecast Definitions

**Companion to** `docs/product-spec.md` §12, §13.6, §16.
Implements **D1** (percentile convention) and **D2** (draw-level simulation).

---

## 1. The percentile convention

**`OWN_DISTRIBUTION_V1`** — recorded in audit metadata on every result.

> Every percentile is taken on the distribution of the quantity it names.
> `P90 depreciation loss` is the 90th percentile of *loss*.
> `P90 value at sale` is the 90th percentile of *value*.

These two are **not** the same scenario. Loss decreases as value increases, so the 90th
percentile of loss corresponds to the 10th percentile of value. §13.7 originally requested
both under a "P90" label, which is the ambiguity D1 resolves.

Both are emitted, correctly labeled. Nothing is renamed to encode good or bad.

### 1.1 Risk direction

Which tail matters depends on the quantity. This table is normative: warning rules and the
explanation allow-list both reference it.

| Quantity | Downside tail | Upside tail |
| --- | --- | --- |
| Additional days to sale | **P90** | P10 |
| Projected total inventory age | **P90** | P10 |
| Transaction price | **P10** | P90 |
| Value at sale | **P10** | P90 |
| Depreciation loss | **P90** | P10 |
| Cash holding cost | **P90** | P10 |
| Slot opportunity cost | **P90** | P10 |
| Projected break-even | **P90** | P10 |
| Front-end gross | **P10** | P90 |
| Net economic value | **P10** | P90 |
| Portfolio unit sales | **P10** | P90 |
| Portfolio revenue | **P10** | P90 |
| Ending inventory | **P90** | P10 |
| Ending utilization | **P90** | P10 |

§12.4 already noted that P10 transaction price matters more than P90 for downside risk. This
table generalizes that observation to every distributional quantity in the system.

### 1.2 Why not name the tails

Renaming fields to `downside_value_at_sale` would prevent misreading but discards the upside
figure and makes schemas asymmetric — a `pessimistic_*`/`optimistic_*` pair per quantity, with
the direction baked into names that then contradict the percentile numerals. The convention
above keeps one naming scheme and puts the interpretation in one table.

The residual risk is that a consumer quotes the wrong tail. Two guards apply: warning rules
reference the risk tail explicitly rather than "the P90", and the explanation allow-list
(architecture §3.4) exposes only the fields a narrative may cite.

---

## 2. Percentile set shape

Every distributional field is an object, never a bare number:

```json
{
  "p10": 12, "p25": 19, "p50": 31, "p75": 48, "p90": 67,
  "mean": 35.4,
  "simulation_id": "sim_01J8X...",
  "unit": "DAYS"
}
```

`p25` and `p75` are optional; `p10`, `p50`, `p90`, `mean`, `simulation_id`, and `unit` are
required. `simulation_id` is what makes §12.5 enforceable — see §4.

---

## 3. Time-to-sale definitions

### 3.1 Additional days to sale

Days from `as_of` until sale. **P50 = 31** means an estimated 50% probability the vehicle
sells within 31 more days.

### 3.2 Projected total inventory age

```text
projected_total_inventory_age = days_in_inventory + additional_days_to_sale
```

Computed **per draw**, then summarized. It is not `days_in_inventory + P50_additional_days`,
though for this particular quantity the two coincide because `days_in_inventory` is a
constant. The per-draw rule is stated anyway, so no implementer treats it as a special case
that licenses combining marginals elsewhere.

The §20.2 warnings (`P50_PROJECTED_INVENTORY_AGE_OVER_90_DAYS` and its variants) evaluate
against this quantity, not against additional days to sale.

### 3.3 Sale probabilities

```text
P(sold within H) = count(draws where days_to_sale ≤ H) ÷ draw_count
```

Horizons: 7, 30, 60, 90 days (§13.6).

### 3.4 Censoring

Draws that do not sell within the simulation horizon (default 365 days) are recorded as
`sold_within_horizon = false` with `days_to_sale = horizon`. Percentiles above the censoring
point are reported as `>= horizon` rather than as a number.

This matters at the tail: a vehicle whose P90 is genuinely beyond the horizon must not report
a precise-looking 365. §16.1 notes survival analysis as the production direction for exactly
this reason — unsold vehicles are censored observations, and the prototype preserves the
censoring flag even though its hazard model is simpler.

---

## 4. Joint distributions

§12.5 forbids implying that P90 transaction price, P90 days to sale, and P90 holding cost
occur in the same scenario. They do not: each is the 90th percentile of its own marginal.

### 4.1 The enforcement mechanism

Per D2, all quantities derive from one seeded draw matrix, and every percentile set carries
the `simulation_id` it came from.

* Any quantity that is a **function** of several others — front-end gross, net economic value,
  projected break-even, portfolio revenue — is computed **per draw**, then summarized.
* Two percentile sets may be combined arithmetically **only** when their `simulation_id`
  values match. Mismatched combination raises rather than silently producing a §12.5
  violation.
* Reporting code may never add, subtract, or compare percentiles across quantities to
  synthesize a new figure.

### 4.2 Worked example

A vehicle listed at $29,900:

| Quantity | P50 | P90 |
| --- | --- | --- |
| Additional days to sale | 31 | 67 |
| Cash holding cost | $604 | $1,305 |
| Net economic value | $1,842 | $2,970 |

`$1,842` is **not** `gross − $604 − depreciation`. It is the median of net economic value
computed across 2000 draws, each internally consistent. The P90 net value of `$2,970` comes
predominantly from draws that sold *quickly* at a strong price — draws in which holding cost
was well below its own P50, not at its P90.

Stating the arithmetic that does not hold is the clearest way to prevent someone
reconstructing it.

---

## 5. Simulation model

Labeled **`CONFIGURABLE_PROTOTYPE_SIMULATION`** on every output (§16.2). It is a configured
simulation, not a trained model, and the UI must say so (§27 item 13).

### 5.1 Hazard

Daily sale probability, from `get_market_sales_velocity` scaled by vehicle-specific factors:

```text
base_daily_hazard  = 1 ÷ market_median_days_to_sale

adjusted_hazard    = base_daily_hazard
                   × price_position_multiplier(price_to_market_ratio)
                   × mileage_multiplier
                   × condition_multiplier
                   × supply_multiplier(supply_to_sales_ratio)
                   × engagement_multiplier          (1.0 when §9.8 unavailable)
                   × seasonality_multiplier
                   × dealer_performance_multiplier
                   × event_lift_multiplier          (event window only)
```

Day of sale is drawn from the resulting discrete-time hazard, with a small aging drift so a
vehicle that has already sat is modeled as slightly harder to move.

`price_position_multiplier` is the elasticity that drives every velocity-versus-gross tradeoff
in the product. It is **assumed, not calibrated** (`open-questions.md` C3) and lives in
`config/assumptions/simulation.yaml`.

### 5.2 Transaction price per draw

```text
transaction_price = list_price × (1 − discount_draw) − promotion_discount
```

`discount_draw` is centered on `expected_discount_rate` (D4) with configured dispersion, and
is negatively correlated with sale speed within a draw: fast sales concede less. That
correlation is why net economic value must be summarized from draws rather than assembled.

### 5.3 Per-draw financial chain

For each draw, in order:

```text
cash_holding_cost      = daily_cash_holding_cost × days_to_sale
slot_opportunity_cost  = daily_slot_cost × days_to_sale          (imputed, D3)
value_at_sale          = market_value × (1 − monthly_dep_rate)^(days_to_sale ÷ 30)
depreciation_loss      = market_value − value_at_sale
front_end_gross        = transaction_price − acquisition − recon − transport − selling_costs
net_economic_value     = front_end_gross − cash_holding_cost − depreciation_loss
                         − promotion_cost − slot_opportunity_cost
```

Only after all draws are complete does `domain/summarize.py` produce percentiles and stamp
each with the `simulation_id`.

### 5.4 Seeding

Fixed configured seed, recorded in audit alongside `draw_count`, `model_version`, and
`assumption_version`. Pricing scenarios (§13.5), promotion plans (§15.8), and the
no-promotion baseline all reuse the same seed, so differences between them reflect the price
change rather than sampling noise.
