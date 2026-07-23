# Phase 3.1 — Workflow copy alignment

**Result: PASS.** Each shared view now takes its heading from the workflow that rendered it.
No calculation, schema, skill, policy, MCP client, or registry structure was touched.

**Companion to** `docs/workflow-navigation-results.md`, which recorded the title mismatch
this phase fixes (§10.1: *"The Acquire Inventory page still titles itself 'Used Vehicle
Pricing Advisor'"*).

---

## 1. The problem this closes

Phase 3 made the navigation workflow-first but left the page bodies as they were, because
that phase's claim was that behaviour did not change. The result was a sidebar and a page
that disagreed: clicking **Acquire Inventory** produced a page headed *Used Vehicle Pricing
Advisor*, and clicking **Merchandise Inventory** produced *Event promotion planner*.

For Acquire Inventory the mismatch was more than cosmetic. The workflow's name implies the
product can appraise a vehicle you are considering buying. It cannot — the single-vehicle
skill needs a `vehicle_id` already in dealer inventory. A page that leaves that implication
standing is wrong in the same way a fabricated number is wrong, just less obviously, so the
limit is now printed on the page rather than left in the registry where only a developer
sees it.

---

## 2. Final copy

| Workflow | Title | Subtitle |
| --- | --- | --- |
| **Acquire Inventory** | Acquire Inventory | Understand available capacity, aging pressure, and portfolio needs before adding more vehicles. |
| **Price Inventory** | Price Inventory | Evaluate market position, sales velocity, break-even economics, and pricing headroom for a vehicle already in inventory. |
| **Merchandise Inventory** | Merchandise Inventory | Build a sale-event promotion plan that balances inventory velocity, gross protection, and safe promotional headroom. |
| **Improve Aging Inventory** | Improve Aging Inventory | Coordinate portfolio forecasting, single-vehicle diagnostics, and event promotion planning against the aged cohort. |

Two supporting fields, rendered where each page has room for them:

| Workflow | Instruction | Scope note |
| --- | --- | --- |
| Acquire Inventory | Read capacity and open slots first, then the risk table for the capital already committed. | *Scope: this evaluates the portfolio you already hold. It does **not** appraise an external acquisition candidate — that would need a valuation of a vehicle not in inventory and an acquisition-cost source, neither of which is in the MVP.* |
| Price Inventory | Choose a vehicle in the sidebar. | — |
| Merchandise Inventory | Choose an event and a utilization target in the sidebar. | — |
| Improve Aging Inventory | — | The orchestration is not implemented yet. This page describes the sequence; it runs none of it. |

One further copy fix, on the Acquire Inventory risk table: *"Open a vehicle from the sidebar
for its price recommendation"* → *"Open **Price Inventory** for any one of these to see its
price recommendation and floor."* The old wording described navigation that no longer
exists.

---

## 3. How copy selection works

`src/pricing_agent/views/workflow_copy.py` holds one frozen `WorkflowCopy` per
`WorkflowContext`, in a `MappingProxyType` so no view can rewrite another workflow's
heading at runtime.

```python
copy = render_workflow_header(workflow_context, fallback_title="Used Vehicle Pricing Advisor")
```

The helper prints the heading and returns the copy that produced it. Returning it — rather
than printing everything — is what lets each page put `instruction` and `scope_note` where
that page has room, without forcing one layout on all four.

**No view compares a workflow name.** `test_views_do_not_compare_raw_workflow_names` asserts
that no view module contains `WorkflowContext.PRICE_INVENTORY` or the raw string
`"PRICE_INVENTORY"`; a view looks its heading up instead of branching on identity. Adding a
fifth workflow is one table entry, not an `if` in four files.

### Heading hierarchy on Price Inventory

Vehicle detail had no page-level title before this phase — the vehicle name was the `<h1>`.
Two `<h1>`s on one page would be worse than the mismatch this phase set out to fix, so when
a workflow is bound the vehicle name renders as `st.header` beneath the workflow title, and
without one it stays `st.title` exactly as before. Verified in the DOM: `h1` is *Price
Inventory*, `h2` is *2022 Toyota RAV4 XLE*.

### Rendering without a workflow context

Requirement 5, held by two tests. `render_workflow_header(None, fallback_title=...)` prints
the original generic title and returns `None`; with no fallback it prints nothing at all,
so vehicle detail keeps leading with the vehicle. Every `if copy is not None` guard in the
views exists for this path.

---

## 4. Nothing underneath the copy moved

| Check | Result |
| --- | --- |
| `git status` over `skills/`, `schemas/`, `mocks/`, `config/`, `domain/`, `simulation/`, `policy/`, `mcp_clients/`, `src/pricing_agent/skills/` | empty |
| Files changed | 5 views + 1 new copy module + 1 new test |
| Registry structure | unchanged — no field added, no entry reordered |
| Navigation structure | unchanged — same five entries, same groups, same url_paths |
| Widget keys | unchanged |

`test_no_calculation_or_skill_module_was_modified_in_this_phase` runs that same `git status`
check inside the suite, so the boundary is enforced rather than promised. It skips cleanly
outside a git checkout.

Every figure on every page is identical to the values recorded in
`docs/workflow-navigation-results.md` §8:

| Page | Figures |
| --- | --- |
| Acquire Inventory | 12 units · 86% · 3 over 90 days · $26,765 · 3 below break-even |
| Price Inventory | $29,195 · $28,400 · P50 gross $2,597 · 30 days · break-even $26,148 |
| Merchandise Inventory | 9 · 13 · 4 · 5 · 1 promoted · $349 |
| Improve Aging Inventory | six steps, no figures — unchanged placeholder |

---

## 5. Verification

```
python -m pytest tests -q          266 passed   (225 before, +41)
python scripts/validate_schemas.py PASSED  62 checks
```

`tests/unit/test_workflow_copy.py` covers: each context produces its title; every context
has copy; titles match the registry `display_name` so sidebar and page cannot drift; the
copy table is immutable; Acquire does not claim external appraisal **and** states the limit
explicitly; Improve Aging names all three capabilities; views do not compare raw workflow
names; the four workflow views render through the shared helper; the no-context fallback in
both its forms; views still call the same data and skill entry points; the copy module holds
no calculation and imports nothing below the view layer; and the protected paths are clean.

### Smoke tests, on a restarted server

| Page | `h1` | Verified |
| --- | --- | --- |
| `/acquire-inventory` | Acquire Inventory | subtitle, instruction, scope note all present; KPIs unchanged |
| `/price-inventory` | Price Inventory | `h2` is the vehicle; all five metrics unchanged |
| `/merchandise-inventory` | Merchandise Inventory | subtitle and instruction present; all six metrics unchanged |
| `/improve-aging-inventory` | Improve Aging Inventory | new subtitle; still says it does not run yet; six steps intact |

No server errors. Streamlit does not reload `src/` modules on edit — the first smoke run
still showed the old title against stale bytecode, and the server had to be restarted. That
is the same `@st.cache_data`-adjacent gotcha recorded earlier in the project: **restart
before believing a negative result.**

---

## 6. Out of scope, unchanged

As instructed: the deprecated `st.components.v1.html` image renderer, natural-language
intent routing, and Improve Aging orchestration were all left alone.
