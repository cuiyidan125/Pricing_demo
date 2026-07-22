# Approval Policy

**Companion to** `docs/product-spec.md` §4.3, §19.2, §22, §23.

---

## 1. Two independent gates

The specification describes two controls that are easy to conflate. They are separate and both
must pass.

| Gate | Question | Who clears it | §22 |
| --- | --- | --- | --- |
| **User confirmation** | Does the person operating the system intend this action? | The operating user | §22.3 |
| **Manager approval** | Does someone with authority accept this financial risk? | A manager, out of band | §22.2 |

A manager approval does not substitute for user confirmation, and user confirmation never
substitutes for manager approval. A `BLOCKING` warning is cleared by neither — it is cleared
only by changing the price or by an explicit §19.2 loss-minimization exception, which is itself
a manager approval with additional required documentation.

---

## 2. No approval required (§22.1)

* Read-only analysis of any kind
* A recommendation at or above all applicable floors
* A promotion within approved budget and above every price floor

Analysis is always free. The product is a decision-support tool, and gating exploration would
defeat it.

---

## 3. Manager approval required (§22.2)

| Trigger | Threshold | Source |
| --- | --- | --- |
| Use of emergency markdown reserve | any | §13.9 reserve tiers |
| Price below projected break-even | P50 basis | `domain/break_even.py` |
| High probability of negative P10 net value | `P(net < 0) > negative_value_threshold` | draws |
| Unusually aggressive price adjustment | `> aggressive_adjustment_pct` from current list | `get_dealer_pricing_policy` |
| Loss-minimization strategy | any | §19.2 |
| Capacity-first plan with material gross reduction | `> material_gross_reduction_pct` of baseline gross | `get_dealer_pricing_policy` |
| Promotion budget exception | `> promotion_budget` | event calendar |

§22.2 states two of these qualitatively — "unusually aggressive" and "material gross
reduction" — without magnitudes (`open-questions.md` C4). Both are configured thresholds,
sourced from dealer policy rather than hard-coded, so a threshold change is a policy change
rather than a code change.

### 3.1 Request payload

`request_manager_approval` requires the quantified impact, not a narrative:

```json
{
  "pricing_decision_id": "pd_01J8X...",
  "approval_type": "LOSS_MINIMIZATION",
  "justification": "user-entered text",
  "immediate_loss": 1160,
  "expected_future_loss": 2480,
  "expected_holding_cost": 1305,
  "expected_depreciation": 1870,
  "capacity_opportunity_cost": 940,
  "requesting_user": "u_442",
  "warnings": ["BREAK_EVEN_EXCEEDS_MARKET_VALUE"]
}
```

The approving manager sees both sides of the comparison — the loss taken now against the
modeled cost of continuing to hold — computed by the system. The system quantifies; the
manager decides.

Approvals are never auto-granted, and the tool has no code path that returns `APPROVED`
without a human action.

---

## 4. User confirmation required (§22.3)

Before: saving a pricing decision, sending a promotion plan for approval, publishing a price,
or activating a promotion.

Confirmation must present, in the confirming view itself:

1. The final price or plan
2. The system recommendation, where the two differ, and the variance
3. The override reason, where one was entered
4. All warnings at `MEDIUM` and above
5. Approval status where §22.2 applies
6. Data timestamps for any source at more than half its freshness allowance

A confirmation dialog that shows only a price is not a control. Items 2 and 3 exist so a user
overriding a recommendation must see what they are overriding at the moment of the decision.

---

## 5. Publication preconditions

`publish_vehicle_price` verifies all of the following server-side, not merely in the caller
(`architecture.md` §8):

1. No unresolved `BLOCKING` warning
2. Manager approval satisfied where §22.2 applies
3. Explicit user confirmation recorded
4. No `REALTIME`-class data stale per §21
5. `final_price` equals the price in the referenced `pricing_decision_id`
6. Valid `idempotency_key`

Condition 5 prevents an approval obtained for one price from being used to publish another.
The idempotency key is `hash(pricing_decision_id + final_price)`, so a retry cannot
double-publish and a changed price cannot reuse an existing approval.

---

## 6. Audit

Every approval writes to the §23 record: `approval_id`, type, requesting user, approving
manager, decision, timestamps for both request and decision, the quantified impact as
presented, the warnings outstanding at the time, and every model, config, and assumption
version in effect.

The versions matter as much as the decision. An approval granted against a set of assumptions
is not evidence about a later recommendation produced under different ones, and without the
version stamps there is no way to tell the two apart after the fact.
