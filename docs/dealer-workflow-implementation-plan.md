# Dealer Workflow Implementation Plan

**Status:** proposal. Nothing in this document has been implemented.
**Goal:** move the product from skill-first navigation to workflow-first navigation, with
the three existing skills unchanged in purpose and reused rather than duplicated.

---

## 1. Target model

| Workflow | Skills invoked |
| --- | --- |
| **Acquire Inventory** | single-vehicle-valuation, inventory-portfolio-forecast |
| **Price Inventory** | single-vehicle-valuation |
| **Merchandise Inventory** | dealer-event-promotion-planner |
| **Improve Aging Inventory** | all three, coordinated |

**Improve Aging Inventory is not a fourth skill.** It is an orchestration layer that
sequences the existing three and presents their results together. It must contain no
valuation, forecasting, or promotion arithmetic of its own.

---

## 2. Current architecture

### 2.1 Layers

```
app.py, pages/*.py        Streamlit. Renders only.
src/pricing_agent/
  agents/                 extraction, intent labelling, narration guard
  llm/                    explanation, prompts, client
  skills/                 three executable skills — orchestration of MCP + domain calls
  mcp_clients/            typed adapters over mocked MCP tools
  domain/                 all financial calculation, pure
  simulation/             seeded Monte Carlo, returns draw matrices
  policy/                 warnings, floors, approvals, freshness
  config/                 assumption loader
```

`tests/unit/test_architecture.py` enforces that `domain/` and `simulation/` import nothing
from `agents/`, `skills/`, `mcp_clients/`, `llm/`, the network, or Streamlit.

### 2.2 The three skills are executable, not specification-only

Both forms exist and both are current:

| Skill | Specification | Implementation | Entry point |
| --- | --- | --- | --- |
| single-vehicle-valuation | `skills/single-vehicle-valuation/SKILL.md` | `src/pricing_agent/skills/single_vehicle.py` | `analyze(vehicle_id, transport, *, config, requested_discount, user_id, dealer_id, request_id, input_text) -> dict` |
| inventory-portfolio-forecast | `skills/inventory-portfolio-forecast/SKILL.md` | `src/pricing_agent/skills/inventory_portfolio.py` | `analyze(transport, *, config, dealer_id, user_id, revenue_target_one_month, revenue_target_three_month, request_id, input_text) -> dict` |
| dealer-event-promotion-planner | `skills/dealer-event-promotion-planner/SKILL.md` | `src/pricing_agent/skills/promotion_planner.py` | `plan_event(transport, event_id, target_utilization, *, config, dealer_id, user_id, request_id, input_text) -> dict` |

Each returns a dict validated against its result schema. All three take a `MockTransport`
carrying the injected `as_of` clock, which is the natural seam for a workflow to pass
shared context down.

### 2.3 Navigation is skill-shaped today

Streamlit's filesystem page discovery drives the sidebar:

```
app.py                      "app"             — inventory dashboard (portfolio skill)
pages/1_Vehicle_Detail.py   "Vehicle Detail"  — single-vehicle skill
pages/2_Promotion.py        "Promotion"       — promotion skill
```

One page per skill, one skill per page. The sidebar is generated from filenames, so
regrouping requires replacing filesystem discovery with `st.navigation` (available —
Streamlit 1.60, `st.navigation` and `st.Page` both present).

### 2.4 There is no router and no orchestration abstraction

This is the most important finding, and it differs from what `docs/architecture.md` §4
implies:

* **`agents/router.py` does not exist.** It was planned and never built.
* **Intent routing is a label, not a dispatch.** `agents/extract.py` defines
  `INTENTS = ("SINGLE_VEHICLE", "INVENTORY_PORTFOLIO", "PROMOTION")` and `intent_of()`
  reads the intent the extraction already produced. It is called in exactly one place —
  `pages/1_Vehicle_Detail.py:143` — to render a caption reading *"routed to
  SINGLE_VEHICLE"*. **Nothing dispatches on it.**
* **`ROUTING_SYSTEM` in `llm/prompts.py` is dead code.** It is never imported.
* **No workflow, orchestration, or session abstraction exists.** Each page imports one
  skill directly and calls it.

So there is nothing to retrofit and nothing to reuse for orchestration — but equally,
nothing to unpick. The workflow layer is additive.

### 2.5 Conventions in force

| Thing | Convention | Examples |
| --- | --- | --- |
| Schemas | kebab-case, `*.schema.json`, `$id` = `https://pricing-demo.local/schemas/<file>` | `single-vehicle-result.schema.json` |
| Scenario files | kebab-case per suite | `tests/scenarios/{single-vehicle,portfolio,promotion}.json` |
| Scenario ids | two-letter prefix + number | `SV-01`, `PF-01`, `PR-01` |
| Skill specs | kebab-case directory + `SKILL.md` | `skills/single-vehicle-valuation/SKILL.md` |
| Skill modules | snake_case | `skills/single_vehicle.py` |
| Tests | `tests/{unit,integration,schema}/test_*.py` | `test_portfolio_aggregation.py` |
| Warning codes | SCREAMING_SNAKE, declared in `config/assumptions/warnings.yaml` | `HIGH_AGED_INVENTORY_CONCENTRATION` |

---

## 3. The constraint that shapes the whole design

**Each skill runs its own simulation.** `single_vehicle.analyze`,
`inventory_portfolio.analyze`, and `promotion_planner.plan_event` each call `simulate()`
independently, producing distinct `simulation_id` values.

`domain/summarize.py::require_same_simulation` raises `SimulationMismatch` when percentile
sets from different simulations are combined. That guard exists because §12.5 forbids
implying that figures from unrelated draws describe one scenario.

**Therefore Improve Aging Inventory must not arithmetically combine figures across the
three skill outputs.** It may present them side by side, rank by them, and narrate them.
It may not add a portfolio revenue figure to a promotion gross impact, or subtract one
skill's holding cost from another's.

Three options, in order of preference:

1. **Present side by side, combine nothing.** Zero risk, no engine change, and honest —
   the workflow's value is sequencing and framing, not new arithmetic. **Recommended for
   the first implementation.**
2. **Share one draw matrix across skills.** Would require the skills to accept an
   injected `DrawMatrix` instead of building their own. Substantial change to three
   public entry points and their tests, and it would need a shared vehicle set the
   skills currently do not agree on (single-vehicle simulates three candidate prices;
   portfolio simulates current prices).
3. Combine anyway and suppress the guard — **rejected**; it would make the guard
   decorative and reintroduce exactly the defect D2 was settled to prevent.

---

## 4. Files that must change

| File | Change |
| --- | --- |
| `app.py` | Becomes the navigation host. Replaces filesystem page discovery with `st.navigation` grouped by workflow. The current dashboard body moves to a view module. |
| `pages/1_Vehicle_Detail.py` | Becomes a thin workflow-scoped entry, or is replaced by entries under `views/`. Body moves to a reusable render function. |
| `pages/2_Promotion.py` | Same. |
| `README.md` | "Three pages" description and the run instructions describe skill-first navigation. |
| `docs/demo-script.md` | Every beat names a sidebar page by its current label. |
| `docs/architecture.md` | §2 layer diagram and §11 module map gain a workflows layer; §4 request lifecycle gains a workflow step. |
| `docs/product-spec.md` §7.1 | Intent routing currently maps requests to three skills. Needs a workflow tier above it. **Amendment, so it belongs in `docs/open-questions.md` section B alongside B1–B5.** |
| `tests/unit/test_architecture.py` | `FORBIDDEN_PREFIXES` must gain `pricing_agent.workflows` so the calculation layer still cannot reach upward. |

### New files

| File | Purpose |
| --- | --- |
| `src/pricing_agent/workflows/__init__.py` | Package exports |
| `src/pricing_agent/workflows/registry.py` | Declarative workflow definitions: id, label, description, ordered skills, entry views |
| `src/pricing_agent/workflows/aging.py` | The Improve Aging Inventory orchestration — calls the three skills, ranks and frames, computes nothing |
| `views/` (or `src/pricing_agent/presentation/`) | Render functions extracted from today's pages, callable from more than one workflow |
| `tests/unit/test_workflow_registry.py` | Every workflow references real skills; every skill is reachable from at least one workflow |
| `tests/integration/test_aging_workflow.py` | Orchestration returns all three skill results and combines no distributions |
| `tests/scenarios/aging-workflow.json` | Scenario definitions, prefix `AW-nn`, matching existing convention |

---

## 5. Files that must not change

**Skill implementations — the no-duplication rule depends on this.**

```
src/pricing_agent/skills/single_vehicle.py
src/pricing_agent/skills/inventory_portfolio.py
src/pricing_agent/skills/promotion_planner.py
skills/*/SKILL.md            (three specification files)
```

If a workflow needs something a skill does not return, the fix is to extend the skill's
result, never to recompute it in the workflow.

**Calculation and infrastructure — no reason to touch any of it.**

```
src/pricing_agent/domain/**        src/pricing_agent/simulation/**
src/pricing_agent/policy/**        src/pricing_agent/mcp_clients/**
src/pricing_agent/config/**        src/pricing_agent/llm/**
config/assumptions/**              mocks/**
schemas/**                         scripts/**
assets/**                          ui_components.py
```

**Existing tests and scenarios** keep their ids and assertions. `SV-`, `PF-`, `PR-`
scenarios describe skill behaviour, which is unchanged by definition.

`schemas/audit-metadata.schema.json` is listed as unchanged **provisionally** — see
open question Q3.

---

## 6. Implementation sequence

Each phase leaves the suite green and the app runnable.

### Phase 0 — Spike, no committed behaviour change
Confirm `st.navigation` can present the **same** page target under two workflow groups
(single-vehicle appears under three workflows). If it cannot, the fallback is thin
per-workflow wrapper modules delegating to one shared render function — still no
duplicated UI logic. Decide before Phase 2.

### Phase 1 — Workflow registry, no UI change
Add `workflows/registry.py` with the four workflows as data. Add
`tests/unit/test_workflow_registry.py`. Add `pricing_agent.workflows` to the architecture
guard's forbidden list. **Nothing renders differently.**

### Phase 2 — Extract views, no navigation change
Move the bodies of `app.py`, `1_Vehicle_Detail.py`, `2_Promotion.py` into render
functions. Existing pages become one-line callers. Pure refactor — verify by screenshot
comparison against the current app.

### Phase 3 — Workflow navigation
Replace filesystem discovery with `st.navigation` grouped by workflow. The three skill
views now appear under their workflows. Update `README.md` and `docs/demo-script.md` in
the same commit so the docs never describe a navigation that no longer exists.

### Phase 4 — Improve Aging Inventory orchestration
Add `workflows/aging.py`. It selects the aged cohort from the portfolio result, runs the
single-vehicle skill per aged unit, runs the promotion planner for the relevant event, and
returns the three results plus a ranking. **No distribution is combined across skills.**
Add the integration test and `AW-nn` scenarios.

### Phase 5 — Documentation and spec amendment
Update `docs/architecture.md`, record the §7.1 amendment in `docs/open-questions.md`
section B, and refresh `docs/demo-script.md` to walk workflows rather than pages.

### Phase 6 — Optional: make intent routing real
`intent_of()` is currently a caption. Routing free text to a *workflow* rather than a
skill is the natural place for `ROUTING_SYSTEM` (today dead code) to earn its keep.
Deliberately last: it is the only phase touching the LLM path, and the LLM path has never
run live (no `ANTHROPIC_API_KEY` present), so it carries the least verifiable risk.

---

## 7. Regression risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| **Cross-simulation combination** in the aging workflow | **High** | Present side by side; never call arithmetic across two skill results. `require_same_simulation` will raise loudly if violated — do not suppress it. |
| Streamlit `@st.cache_data` keyed on `as_of` only | Medium | Already bit us twice: a fixture edit did not appear until the server restarted. Workflow context must be part of any new cache key, or results will leak between workflows. |
| Aging workflow runs the single-vehicle skill per aged unit | Medium | Each call is a full simulation. With three aged units that is three extra runs on top of portfolio and promotion. Cache per vehicle and measure before adding a spinner. |
| Demo script drift | Medium | Phase 3 changes every sidebar label the script names. Update in the same commit. |
| Architecture guard silently weakened | Medium | Add `pricing_agent.workflows` to `FORBIDDEN_PREFIXES` in Phase 1, before the package exists, so the guard cannot be forgotten. |
| Page-level duplication creeping in | Medium | Phase 2 before Phase 3. Extracting views first makes duplication impossible rather than merely discouraged. |
| Deep links / `url_path` changes | Low | Existing URLs (`/Vehicle_Detail`, `/Promotion`) change. Only affects local bookmarks. |
| Scenario id collision | Low | New prefix `AW-`; `SV-`, `PF-`, `PR-` untouched. |

---

## 8. Unresolved questions

**Q1 — Does a workflow own its own state?**
If a manager picks a vehicle in Price Inventory and moves to Improve Aging Inventory,
does the selection follow? Session-scoped state is friendlier but adds a state model the
app does not currently have. *Recommendation: no shared state in the first pass.*

**Q2 — What does Acquire Inventory actually show?**
The other three map cleanly onto existing screens. Acquire is about vehicles **not yet in
inventory** — appraisal of a candidate purchase. The single-vehicle skill takes a
`vehicle_id` that must exist in `get_dealer_inventory`, so today it cannot price a
vehicle the dealer does not own. Either Acquire is scoped to "what would this do to my
portfolio" using existing units, or the skill needs to accept an ad-hoc vehicle. **This
is the largest unknown in the request.**

**Q3 — Should the audit record carry the workflow?**
§23 lists no workflow field. Adding `workflow_id` to `audit-metadata.schema.json` would
make it possible to answer "which workflow produced this recommendation", which seems
worth having. It is a schema change, so it needs a decision rather than an assumption.

**Q4 — Does Improve Aging Inventory need its own result schema?**
If it only presents three existing results plus a ranking, a schema may be unnecessary.
If it is to be audited as a unit, it needs one — `aging-workflow-result.schema.json`,
composing the three by `$ref`.

**Q5 — Do the SKILL.md files mention their workflows?**
They currently describe when to route to each skill. Workflow membership could live in
the registry only, or be cross-referenced in each spec. Registry-only avoids two sources
of truth. *Recommendation: registry only.*

**Q6 — Does `app.py` remain the entry point?**
`st.navigation` wants a single entry script. Keeping `app.py` matches `README.md` and
`.claude/launch.json`, both of which name it — changing it means changing both.

---

## 9. Verification

Current commands, unchanged by this work:

```bash
python -m pytest tests -q            # 158 tests
python scripts/validate_schemas.py   # 62 checks
streamlit run app.py                 # http://localhost:8501
```

`scripts/validate_structure.ps1` runs the subset needing no Python.

Each phase must leave all three green. Phase 2 additionally needs visual confirmation
that the extracted views render identically to the current pages — a pure refactor that
changes pixels is a failed refactor.

**A note on caching:** editing a fixture or a page body does not always surface in the
running app, because `@st.cache_data` keys on `as_of` rather than file state. Restart the
server before concluding a change did not work. This has produced two false negatives
already.
