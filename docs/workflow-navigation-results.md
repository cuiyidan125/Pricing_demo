# Phase 3 — Workflow registry and agent-first navigation

**Result: PASS.** The application now opens on *Ask the Dealer AI Assistant* and its
navigation is generated from a typed registry. The Streamlit `pages/` directory is gone.
All three skill implementations, every schema, and every calculation are untouched.

**Companion to** `docs/dealer-workflow-implementation-plan.md` (the plan),
`docs/navigation-spike-results.md` (Phase 1), `docs/view-extraction-results.md` (Phase 2).

---

## 1. What changed

| | Before | After |
| --- | --- | --- |
| Navigation source | filenames in `pages/`, ordered by a numeric prefix | `workflows/registry.py`, declared as frozen dataclasses |
| Entry point | the lot dashboard | Ask the Dealer AI Assistant |
| Organising idea | the tool's three capabilities | the dealer's four jobs |
| Skills in the menu | three, as pages | none — always reached through a workflow |
| `set_page_config` | one call per page file | one call, in `views/page_config.py` |

The vocabulary is now the same in the sidebar, the registry, `README.md`,
`docs/architecture.md` §2.1 and `docs/product-spec.md` §6.1: **Agent → Workflow → Skill →
MCP tool → Dashboard**.

---

## 2. Registry design

`src/pricing_agent/workflows/registry.py` holds one `WorkflowDefinition` per entry. Three
kinds of metadata are kept in separate types rather than flattened into one blob, because
they change for different reasons:

| Type | Answers | Changes when |
| --- | --- | --- |
| `NavigationEntry` | Where does it appear, what is it called, what is its URL? | the interface is reorganised |
| `WorkflowDefinition` | What dealer job is this, what serves it, how much is built? | the product changes |
| `SkillId` | Which reusable capabilities does it draw on? | a skill is added — which has not happened |

Three deliberate constraints:

**No Streamlit import.** The registry is importable and testable without a Streamlit
runtime. `st.Page` objects are built in `app.py` from registry data. This is what lets
`tests/unit/test_workflows.py` assert on the whole navigation tree in-process.

**No calculation.** Asserted, not just intended: `test_the_registry_holds_no_calculation`
rejects `simulate(`, `percentile`, `np.`, `numpy`, `pandas` anywhere in the module.

**One-way dependency.** The registry imports views to bind render callables. A view that
imported the registry back would close a cycle, so `render_assistant_home` receives its
workflow cards as an argument (`WorkflowDefinition.as_card()`). This is why
`workflows/__init__.py` exports only `WorkflowContext` and not the registry — a package-level
re-export would reintroduce the cycle through the views that need the enum.

### `availability` earns its place

`AVAILABLE` vs `SHELL_ONLY` is a field rather than a comment because two entries are honestly
incomplete, and the UI reads the field to say so. A shell that looked finished is the one
failure mode worth avoiding in a prototype whose entire claim is that it does not make
things up.

---

## 3. Navigation map

```
Dealer AI Assistant
  Ask the Assistant          /            forum        default   SHELL_ONLY   —
Dealer Workflows
  Acquire Inventory          /acquire-inventory      inventory   AVAILABLE    portfolio forecast
  Price Inventory            /price-inventory        sell        AVAILABLE    single-vehicle valuation
  Merchandise Inventory      /merchandise-inventory  campaign    AVAILABLE    promotion planner
  Improve Aging Inventory    /improve-aging-inventory timelapse  SHELL_ONLY   all three
```

`url_path` for the assistant is declared as `ask`; because it is the default page, Streamlit
serves it at `/` and the sidebar link points there. Both `/` and `/ask` resolve to it.

---

## 4. Page reuse — one view, many workflows

`WorkflowDefinition.bound_render()` returns `partial(self.render, workflow_context=self.context)`.
The view is shared; only the binding differs. Nothing was copied to create a workflow:

| Workflow | View | Reused from |
| --- | --- | --- |
| Acquire Inventory | `render_dashboard` | the former `app.py` body |
| Price Inventory | `render_vehicle_detail` | the former `pages/1_Vehicle_Detail.py` |
| Merchandise Inventory | `render_promotion_planner` | the former `pages/2_Promotion.py` |
| Improve Aging Inventory | `render_improve_aging` | new — placeholder only |
| Ask the Assistant | `render_assistant_home` | new |

`test_the_same_render_function_can_be_bound_to_different_contexts` proves the mechanism
directly: it binds `render_dashboard` to two different contexts and asserts the two
definitions hold the *same function object*, not two copies.

Every view accepts `workflow_context: WorkflowContext | None = None`. No view branches on it
yet — the parameter exists so a workflow can vary presentation later without a signature
change.

---

## 5. What the agent shell does not do

This was the sharpest constraint of the phase, and the shell is written to make it visible
rather than to hide it.

**It does not call a model.** `test_assistant_shell_calls_no_model_and_no_write_tool` asserts
that `assistant_home.py` references none of `pricing_agent.llm`, `pricing_agent.agents`,
`anthropic`, `pricing_agent.skills`, `publish_vehicle_price`, `save_pricing_decision`.

**It does not route.** On submit it stores the text in `st.session_state["assistant_request"]`
and shows:

> Natural-language workflow routing will be connected in the next phase. Select a dealer
> workflow below to continue with the current prototype.

**It derives nothing from the text.** An expander shows exactly what was captured, labelled
*"Held in session state only. No model was called, no skill was invoked, and no figure was
derived from this text."*

**Improve Aging Inventory does not orchestrate.** The page lists its six steps and names the
capability behind each, then explains why it is a workflow and not a fourth skill —
including the constraint that will shape the implementation: each skill runs its own
simulation with its own `simulation_id`, and percentiles from two simulations cannot be
added together (§12.5). The orchestration will present results side by side rather than
summing them.

---

## 6. Legacy removal

Removed: `pages/1_Vehicle_Detail.py`, `pages/2_Promotion.py`, the `pages/` directory,
`spike_navigation.py`, `src/pricing_agent/views/context.py`.

Streamlit ignores `pages/` once `st.navigation` is used — verified during the phase, with
both navigations present and no duplicate sidebar appearing. The directory was removed
anyway: leaving a dead navigation source in the tree invites the question of which one is
live. `test_legacy_filesystem_pages_are_not_simultaneously_active` keeps it gone.

`WorkflowContext` moved from `views/context.py` to `workflows/context.py`. A workflow is a
dealer business job, not a screen; Phase 2 put the enum in `views/` only because
`workflows/` did not exist yet. `test_no_module_still_imports_the_old_location` scans the
repository for stale imports — by AST, not by substring, so the docstring in the new module
recording where it moved from does not trip its own rule.

---

## 7. Session and cache decisions

**Cache keys are unchanged.** The `@st.cache_data` loaders still key on `as_of` only. This is
safe *today* precisely because no view branches on `workflow_context` — the same inputs
produce the same result whichever workflow rendered them. **The moment a view's behaviour
differs by workflow, the context must enter the cache key** or results will leak between
workflows. This is the single most likely way to introduce a silent bug in the next phase.

**Session state was verified across in-app navigation**, not assumed:

| Check | Result |
| --- | --- |
| Submit a question, navigate to Price Inventory, return | `assistant_request` survives — "Last question captured" renders |
| Full page reload | State is lost — a new Streamlit session, expected |
| The `assistant_input` widget value itself | Cleared on page switch |

That last row is Streamlit's own behaviour: widget state is garbage-collected when the
widget is not rendered. It is the reason the submitted text is copied into a **plain**
session key rather than read back from the widget key — the plain key persists, the widget
key does not. The next phase must read the request from `SESSION_KEY`.

---

## 8. Verification

```
python -m pytest tests -q          225 passed
python scripts/validate_schemas.py PASSED  62 checks
```

`tests/unit/test_workflows.py` is new (registry completeness, unique ids and paths,
importable callables, assistant default, skills absent from navigation, context relocation,
shared render binding, Improve Aging is not a skill, no calculation in workflows or views,
assistant calls no model or write tool, legacy pages gone).

`tests/unit/test_views.py` was rewritten: its `ENTRY_POINTS` map asserted on
`pages/1_Vehicle_Detail.py` and `pages/2_Promotion.py`, which no longer exist. The
wrapper-specific tests were dropped; the render-function contract, the workflow-context
signature, the render/calculate boundary and the single `set_page_config` call site were
kept.

`tests/unit/test_architecture.py` gained `pricing_agent.views` to its forbidden-import
prefixes.

### Smoke tests, on a server restarted after `pages/` was deleted

| Check | Result |
| --- | --- |
| Startup | clean; only the pre-existing `st.components.v1.html` deprecation in the log |
| Default page | Ask the Dealer AI Assistant |
| Sidebar | two groups, five entries, exactly one sidebar element in the DOM |
| Direct URL `/acquire-inventory` | 12 units, 86%, 3 over 90 days, $26,765, 3 below break-even |
| Direct URL `/price-inventory` | $29,195 / $28,400 / P50 gross $2,597 / 30 days |
| Direct URL `/merchandise-inventory` | Not Achievable — 9 / 13 / 4 / 5 |
| Direct URL `/improve-aging-inventory` | six steps, no figures |
| In-app navigation | client-side, no page reload (verified with a `window` marker) |
| New errors or warnings | none |

Every figure matches the pre-migration values recorded in
`docs/view-extraction-results.md` §8.

### Screenshots

Captured and compared during verification; described here rather than committed as
binaries, following Phase 2.

| Screen | What it shows |
| --- | --- |
| Ask the Assistant | Title, capability list, question box, Analyze, four suggested prompts, four workflow cards with their skills and status, prototype disclaimer |
| Ask the Assistant, submitted | The routing-not-connected banner and the "What was captured" expander — no recommendation, no figures |
| Acquire Inventory | Five KPIs, both warning banners, Lot/Forecast/Risk tabs, risk-ordered table with thumbnails |
| Price Inventory | Vehicle photo, four headline metrics, strategy comparison, narrative, audit trail |
| Merchandise Inventory | Not Achievable verdict, four metrics, three plan cards, excluded tab |
| Improve Aging Inventory | Six numbered steps with the capability behind each, and the "why this is a workflow" rationale |

---

## 9. Rollback

`git revert` of this phase's commit restores the previous navigation, because nothing
outside the presentation layer moved: no schema, no config, no skill, no MCP client, no
simulation or domain module was touched. The two files a revert must restore are `app.py`
and the `pages/` directory; both are recoverable from history.

A partial rollback — keeping the registry but restoring the dashboard as the entry point —
is a one-line change: move `default=True` from `ASSISTANT` to the `acquire-inventory`
`NavigationEntry`.

---

## 10. Known limitations

1. **The Acquire Inventory page still titles itself "Used Vehicle Pricing Advisor."** It was
   the application home before this phase and Phase 2 was a pure refactor, so the `st.title`
   was never revisited. The sidebar says *Acquire Inventory* and the page says something
   else. Worth fixing, but it is a copy change to a view, not a navigation change, so it was
   left out of a phase whose claim is that behaviour did not change. The same applies to its
   caption *"Open a vehicle from the sidebar"*, which is still true but no longer precise.
2. **Cache keys do not include workflow** (§7). Harmless now, load-bearing later.
3. **`views/` imports `ui_components` from the repository root.** Carried over from Phase 2;
   still a layering smell.
4. **`st.components.v1.html` is past its removal date** (2026-06-01). Pre-existing, in the
   vehicle-silhouette fallback path. It still works, and migrating it needs a check that
   `st.iframe` does not sanitize inline SVG — which is why the silhouette left `st.html` in
   the first place.
5. **Two entries are `SHELL_ONLY`.** By design this phase, but the demo must say so out loud;
   `docs/demo-script.md` now scripts both admissions.

---

## 11. Next phase

In dependency order:

1. **Natural-language intent routing.** Read `st.session_state["assistant_request"]`, run the
   existing extraction path in `agents/`, and map the intent onto a `workflow_id` from the
   registry. The registry is already the routing table — `by_id()` exists for this. The
   routing decision must be shown to the user and overridable, and §4.1 still holds: routing
   selects a workflow, it never produces a number.
2. **Improve Aging orchestration.** Sequence the three skills against the aged cohort.
   The binding constraint is §12.5: results from different `simulation_id`s are presented
   side by side, never combined arithmetically. Decide before building whether the cohort
   gets one shared simulation.
3. **Workflow-aware caching**, before either of the above changes a view's behaviour.
4. The copy fixes in §10.1.
