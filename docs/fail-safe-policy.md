# Fail-Safe Policy

**Companion to** `docs/product-spec.md` §11, §17, §19, §20, §21.
Implements **D3** (cash vs. imputed cost) and **D7** (severity mapping).

---

## 1. The cost separation

The single most important rule in this document, because getting it wrong makes the system
refuse profitable sales.

| | Cash holding cost | Slot opportunity cost |
| --- | --- | --- |
| Nature | Out-of-pocket or accrued: floorplan interest, lot, insurance, maintenance, admin | Imputed: the economic value of the slot's next-best use |
| Break-even (§11.7, §11.8) | included | **excluded** |
| Minimum safe transaction price (§11.10) | included | **excluded** |
| §19.1 publication bars | included | **excluded** |
| Net economic value (§11.6) | included | included |
| Promotion candidate ranking, discount optimization | included | included |

An imputed cost inside a price floor raises the floor above the dealer's real recovery point
and blocks sales that are profitable in accounting terms. Since §19.1 makes the floor a
publication bar, that error would silently prevent legitimate transactions. Slot opportunity
cost is a real economic consideration and belongs in optimization — never in a floor.

Its magnitude is also the least defensible number in the system: the value of a slot depends on
the portfolio that would occupy it, which is circular (`open-questions.md` C2). That is a second
reason to keep it away from anything with veto power.

---

## 2. Break-even

```text
current_accounting_break_even =
      acquisition_cost + auction_fee + transportation_cost + reconditioning_cost
    + accrued_cash_holding_cost          (incurred to date)
    + direct_selling_costs
```

Costs already incurred or contractually committed as of today (§11.7). No future costs, no
imputed costs.

```text
projected_break_even[draw] =
      current_accounting_break_even
    + future_cash_holding_cost(days_to_sale[draw])
```

Computed per draw, then summarized (D2). `P90 projected break-even` is the 90th percentile of
break-even — the pessimistic case, consistent with the risk-direction table in
`forecast-definitions.md`.

### 2.1 Minimum safe prices

```text
minimum_safe_transaction_price = max(
    current_accounting_break_even,
    policy_price_floor,                    # get_dealer_pricing_policy
    financing_constraint,                  # financing_amount payoff
    risk_floor                             # configured % of market value
)

minimum_safe_list_price =
    minimum_safe_transaction_price ÷ (1 − expected_discount_rate)      (D4)
```

The list-price conversion exists because a vehicle listed exactly at its minimum safe
transaction price will transact **below** it after normal negotiation. `expected_discount_rate`
is a configured assumption and must be visible in the UI, not buried.

Two of the four inputs — policy floor and risk floor — have no MCP source in the specification
and are read from config in the MVP (`open-questions.md` C1).

---

## 3. Publication bars

§19.1. These four conditions raise `BLOCKING` warnings, and `BLOCKING` means exactly one thing:
`publish_vehicle_price` is refused.

| Bar | Condition | Warning |
| --- | --- | --- |
| Hard floor | expected transaction price < hard price floor | `MINIMUM_SAFE_LIST_PRICE_VIOLATION` |
| Break-even | P50 transaction price < current accounting break-even | `P50_TRANSACTION_PRICE_BELOW_BREAK_EVEN` |
| Headroom | promotion price exceeds available safe headroom | `DISCOUNT_EXCEEDS_SAFE_HEADROOM` / `PROMOTION_EXCEEDS_SAFE_HEADROOM` |
| Negative value | P(net economic value < 0) > `negative_value_threshold` | `HIGH_PROBABILITY_OF_NEGATIVE_NET_VALUE` |

Plus, from §21: any `REALTIME`-class data stale at publication time blocks publication
(`STALE_MARKET_DATA`), and missing cost basis blocks any recommendation at all
(`INSUFFICIENT_VEHICLE_DATA`) — without cost basis there is no floor, and a recommendation
without a floor is the exact failure §4.5 exists to prevent.

### 3.1 Policy never alters a number

The policy layer runs **after** calculation and may only add warnings, approvals, and bars
(`architecture.md` §7). A price that violates a floor is reported unchanged alongside a
`BLOCKING` warning; it is never quietly raised to the floor.

This keeps the audit record honest: what the system computed and what policy did about it stay
two separate, separately reviewable facts. Silent clamping would make the two
indistinguishable after the fact.

---

## 4. Severity mapping

§20.1 defines six severities but maps no codes to them (D7). `BLOCKING` is reserved
exclusively for §3 above — so "blocking" always means publication is refused, and never merely
"serious". Anything a user can proceed past with documentation is `CRITICAL` at most.

Authoritative copy: `config/assumptions/warnings.yaml`.

### 4.1 Single vehicle (§20.2)

| Code | Severity |
| --- | --- |
| `P50_TRANSACTION_PRICE_BELOW_BREAK_EVEN` | `BLOCKING` |
| `MINIMUM_SAFE_LIST_PRICE_VIOLATION` | `BLOCKING` |
| `DISCOUNT_EXCEEDS_SAFE_HEADROOM` | `BLOCKING` |
| `HIGH_PROBABILITY_OF_NEGATIVE_NET_VALUE` | `BLOCKING` |
| `PRICE_BELOW_CURRENT_BREAK_EVEN` | `CRITICAL` |
| `BREAK_EVEN_EXCEEDS_MARKET_VALUE` | `CRITICAL` |
| `INSUFFICIENT_VEHICLE_DATA` | `HIGH` — `BLOCKING` when cost basis is missing |
| `RECOMMENDED_PRICE_POOR_DEAL` | `HIGH` |
| `P10_TRANSACTION_PRICE_BELOW_BREAK_EVEN` | `HIGH` |
| `BREAK_EVEN_MARKET_CROSSOVER_RISK` | `HIGH` |
| `P50_PROJECTED_INVENTORY_AGE_OVER_120_DAYS` | `HIGH` |
| `EXTERNAL_PROVIDER_VARIANCE` | `MEDIUM` at >5%, `HIGH` at >10% (D5) |
| `LOW_VALUATION_CONFIDENCE` | `MEDIUM` |
| `EXTERNAL_VALUATION_UNAVAILABLE` | `MEDIUM` |
| `CURRENT_PRICE_POOR_DEAL` | `MEDIUM` |
| `P50_PROJECTED_INVENTORY_AGE_OVER_90_DAYS` | `MEDIUM` |
| `P90_PROJECTED_INVENTORY_AGE_OVER_120_DAYS` | `MEDIUM` |
| `HIGH_DEPRECIATION_RISK` | `MEDIUM` |
| `HOLDING_COST_EXCEEDS_INCREMENTAL_GROSS` | `MEDIUM` |
| `P90_PROJECTED_INVENTORY_AGE_OVER_90_DAYS` | `LOW` |

`P90_PROJECTED_INVENTORY_AGE_OVER_90_DAYS` is deliberately the lowest severity in the group:
a 10% chance of exceeding 90 days is unremarkable for used inventory. Its P50 counterpart —
an even chance of exceeding 90 days — is a genuine problem. Ranking them by percentile rather
than by threshold would invert the alarm.

### 4.2 Portfolio (§20.3)

| Code | Severity |
| --- | --- |
| `HIGH_PERCENTAGE_BELOW_BREAK_EVEN` | `CRITICAL` |
| `STALE_MARKET_DATA` | `HIGH` for analysis; `BLOCKING` at publication of affected vehicles |
| `HIGH_AGED_INVENTORY_CONCENTRATION` | `HIGH` |
| `PROJECTED_CAPACITY_OVER_100_PERCENT` | `HIGH` |
| `INBOUND_CAPACITY_CONFLICT` | `HIGH` |
| `INCOMPLETE_INVENTORY_DATA` | `MEDIUM` |
| `LOW_PORTFOLIO_FORECAST_CONFIDENCE` | `MEDIUM` |
| `HIGH_PROJECTED_DEPRECIATION` | `MEDIUM` |
| `PROJECTED_CAPACITY_OVER_TARGET` | `MEDIUM` |
| `ONE_MONTH_REVENUE_BELOW_TARGET` | `MEDIUM` |
| `THREE_MONTH_REVENUE_BELOW_TARGET` | `MEDIUM` |
| `HIGH_PORTFOLIO_HOLDING_COST` | `LOW` |
| `FUTURE_ACQUISITION_DATA_UNAVAILABLE` | `INFO` |

### 4.3 Promotion (§20.4)

| Code | Severity |
| --- | --- |
| `PROMOTIONAL_PRICE_BELOW_BREAK_EVEN` | `BLOCKING` |
| `PROMOTION_EXCEEDS_SAFE_HEADROOM` | `BLOCKING` |
| `UNREALISTIC_INVENTORY_TARGET` | `HIGH` |
| `INSUFFICIENT_SAFE_PROMOTION_CANDIDATES` | `HIGH` |
| `PROMOTION_COST_EXCEEDS_EXPECTED_SAVINGS` | `HIGH` |
| `EMERGENCY_MARKDOWN_APPROVAL_REQUIRED` | `HIGH` |
| `PROMOTION_BUDGET_EXCEEDED` | `MEDIUM` |
| `LOW_EXPECTED_EVENT_LIFT` | `MEDIUM` |
| `PRICE_CANNIBALIZATION_RISK` | `MEDIUM` |
| `CAPACITY_TARGET_UNLIKELY_TO_BE_ACHIEVED` | `MEDIUM` |
| `VEHICLE_EXPECTED_TO_SELL_BEFORE_EVENT` | `LOW` |
| `VEHICLE_ALREADY_ASSIGNED_TO_CAMPAIGN` | `LOW` |

### 4.4 Warning payload

Severity alone is not actionable. Every warning carries:

```json
{
  "code": "P50_TRANSACTION_PRICE_BELOW_BREAK_EVEN",
  "severity": "BLOCKING",
  "scope": "VEHICLE | PORTFOLIO | PLAN",
  "subject_id": "V-10028",
  "message": "Median modeled transaction price of $24,180 is below break-even of $25,340.",
  "observed": 24180,
  "threshold": 25340,
  "unit": "USD",
  "remediation": "Raise list price, reduce planned discount, or request loss-minimization approval.",
  "blocks_publication": true
}
```

`observed` and `threshold` are mandatory, so the user sees the margin by which a rule was
missed rather than only that it was.

---

## 5. Loss-minimization exception

§19.2. The only path to a below-floor sale, and it is a documentation workflow rather than an
override switch.

Requires **all** of:

1. Manager approval via `request_manager_approval`
2. A documented reason, entered by the user
3. Quantified `immediate_loss` — the loss taken now
4. Quantified `expected_future_loss` — the modeled loss from continuing to hold
5. Quantified `expected_holding_cost` through P50 sale
6. Quantified `expected_depreciation` through P50 sale
7. Quantified `capacity_opportunity_cost`
8. A complete audit record per §23

Items 3–7 exist so the comparison is explicit: an immediate loss is justified only when it is
smaller than the modeled cost of holding. The system computes both sides and presents them; it
does not decide.

`BREAK_EVEN_EXCEEDS_MARKET_VALUE` — an underwater vehicle — is the ordinary trigger. The
system never recommends pricing above the market ceiling to manufacture a paper break-even,
because that produces a vehicle that does not sell and a loss that grows.

---

## 6. Freshness enforcement

Per §21 and D8. Every check uses the injected `as_of`, never the wall clock.

| Class | Max age | Effect when stale |
| --- | --- | --- |
| `REALTIME` | 1 h | Analysis proceeds; **publication barred** |
| `NEAR_REALTIME` | 4 h | Warning; portfolio confidence reduced |
| `DAILY` | 24 h | Warning; valuation confidence reduced one level |
| `VERSIONED` | n/a | Model-version controlled |

Stale data degrades analysis but blocks only publication. A manager exploring options with
two-hour-old inventory data is doing something reasonable; publishing a price from it is not.
