# View Extraction Results

**Phase 2 of `docs/dealer-workflow-implementation-plan.md`.**
**Result: PASS** — the three page bodies are now reusable render functions, and the
application behaves identically.

No navigation changed. `app.py` is still a plain Streamlit script, filesystem page
discovery still drives the sidebar, and both existing page URLs still resolve.

---

## 1. Files created

| File | Purpose |
| --- | --- |
| `src/pricing_agent/views/__init__.py` | Package exports |
| `src/pricing_agent/views/context.py` | `WorkflowContext` enum |
| `src/pricing_agent/views/page_config.py` | Single definition of title/icon/layout values |
| `src/pricing_agent/views/dashboard.py` | `render_dashboard(workflow_context=None)` |
| `src/pricing_agent/views/vehicle_detail.py` | `render_vehicle_detail(workflow_context=None)` |
| `src/pricing_agent/views/promotion.py` | `render_promotion_planner(workflow_context=None)` |
| `tests/unit/test_views.py` | 31 tests covering the extraction |
| `docs/view-extraction-results.md` | This document |

## 2. Files modified

| File | Change |
| --- | --- |
| `app.py` | 280 lines → 16. Now configures the page and calls `render_dashboard()`. |
| `pages/1_Vehicle_Detail.py` | 531 lines → 17. Calls `render_vehicle_detail()`. |
| `pages/2_Promotion.py` | 295 lines → 18. Calls `render_promotion_planner()`. |
| `tests/unit/test_architecture.py` | Added `pricing_agent.views` to `FORBIDDEN_PREFIXES`. |

Nothing else was touched. Skills, schemas, MCP clients, domain, simulation, policy,
scenarios, configs, mocks and `ui_components.py` are unmodified.

---

## 3. Was the extraction faithful?

Rather than trusting a reading of the diff, each extracted body was compared against the
original page body programmatically — parse the render function, dedent it, and diff it
against the source lines it replaced.

| Page → view | Original body | Extracted | Executable differences |
| --- | --- | --- | --- |
| `pages/2_Promotion.py` → `promotion.py` | 236 lines | 236 | **none** — byte-for-byte |
| `pages/1_Vehicle_Detail.py` → `vehicle_detail.py` | 427 lines | 427 | **none** — only comment-banner dash lengths |
| `app.py` → `dashboard.py` | 193 lines | 189 | **one**, see below |

The promotion page was extracted with a script rather than retyped, precisely so the body
could not drift. The other two were hand-moved and then verified the same way.

### The one executable change

`app.py` contained a dead local:

```python
underwater = [
    a for a in result["recommended_actions"] if a["action"] == "LOSS_MINIMIZATION_REVIEW"
]
```

It was assigned and never read — nothing downstream referenced it. Removed during the
move. It has no side effects, so no rendered output changes. Recording it here because a
"pure refactor" claim should account for every difference rather than round it away.

---

## 4. Legacy wrapper structure

Each entry point is now:

```python
from pricing_agent.views import APP_TITLE, configure_page, render_dashboard

configure_page(APP_TITLE)
render_dashboard()
```

A test asserts each wrapper has **at most two statements** and does not import
`pricing_agent.skills`, so a wrapper cannot quietly grow logic back and drift from the
view it is supposed to delegate to.

---

## 5. Page configuration

**Not fully centralised, and it cannot be while filesystem pages remain active.**

Streamlit executes each page under `pages/` as its own top-level script. Each therefore
needs its own `st.set_page_config` call to control its browser tab title — there is no
shared parent execution to inherit from. This is a Streamlit constraint, not a design
choice.

What *was* centralised:

* All title, icon and layout **values** live in `views/page_config.py`.
* There is exactly **one `st.set_page_config` call site** in the entire repository, inside
  `configure_page()`. Previously there were three, each with its own literal arguments.
* Each entry point makes one call through that helper.

A test enforces both: no other module may call `set_page_config`, and `page_config.py`
must contain exactly one call. Once Phase 3 replaces filesystem pages with
`st.navigation`, the entry script can make the single call and the wrappers disappear
entirely.

The navigation spike already confirmed a repeat call does not raise on Streamlit 1.60 —
the last call wins — so this arrangement stays safe when `st.navigation` also configures
the page.

---

## 6. Workflow-context interface

```python
class WorkflowContext(str, Enum):
    ACQUIRE_INVENTORY = "ACQUIRE_INVENTORY"
    PRICE_INVENTORY = "PRICE_INVENTORY"
    MERCHANDISE_INVENTORY = "MERCHANDISE_INVENTORY"
    IMPROVE_AGING_INVENTORY = "IMPROVE_AGING_INVENTORY"
```

A `str` enum, so it serialises into a URL, a cache key or an audit record without a
conversion step at each boundary.

Every render function takes `workflow_context: WorkflowContext | None = None` and
**ignores it**. That is deliberate: Phase 2 changes no behaviour. The parameter exists so
Phase 3 can bind a workflow through `st.Page` and `functools.partial` without touching
these signatures again:

```python
st.Page(partial(render_vehicle_detail, WorkflowContext.PRICE_INVENTORY), ...)
```

**Temporary home.** The enum lives under `views/` because the workflow package does not
exist yet and creating it early would prejudge the registry design. Moving it to
`pricing_agent/workflows/` later is an import change and nothing more.

Acquire Inventory is scoped to portfolio capacity and acquisition readiness. Nothing here
claims the product can appraise an external acquisition candidate — the single-vehicle
skill requires a `vehicle_id` already in dealer inventory, so ad-hoc appraisal remains a
future enhancement.

---

## 7. Verification

```
python -m pytest tests -q            189 passed   (was 158; +31 new)
python scripts/validate_schemas.py   PASSED 62 checks
```

Both applications were restarted and driven:

| Check | Result |
| --- | --- |
| `streamlit run app.py` starts | yes, no errors |
| Flat filesystem navigation | unchanged — `app` / `Vehicle Detail` / `Promotion` |
| `/Vehicle_Detail` direct URL | resolves |
| `/Promotion` direct URL | resolves |
| Navigation spike on 8502 | still works against the refactored pages |
| Grouped workflow navigation | renders as before |
| Page reuse across workflows | still reported SUPPORTED |
| New Streamlit warnings | none |
| Server errors | none on either port |

The only log output remains the pre-existing `st.components.v1.html` deprecation, which is
explicitly out of scope for this phase.

---

## 8. Screenshot comparison

Before-shots were captured on the pre-refactor build, after-shots on the refactored one.

| Screen | Compared | Result |
| --- | --- | --- |
| Dashboard | Title, caption, five KPI metrics and their deltas, both warning banners, tab strip, lot table rows and thumbnails, sidebar input and captions | **identical** — 12 units, 86%, 3 over 90 days, $26,765, 3 below break-even; V-10005/V-10012/V-10002 in the same order with the same risk bars |
| Vehicle detail | Photo card, title, caption, four headline metrics, strategy line, narrative box, section headings | **identical** — $29,195 / $28,400 / $2,597 / 30 days, same rationale codes, same explanation text and source label |
| Promotion planner | Feasibility banner, four metrics, expander, three plan cards, sidebar event selector and slider | **identical** — Not Achievable, 9 / 13 / 4 / 5, Capacity First recommended |

No difference in headings, controls, metrics, tables, charts, warnings, spacing or result
content was observed on any screen.

---

## 9. Known limitations

1. **`views/` imports `ui_components` from the repository root.** A package under `src/`
   reaching for a root-level module works because Streamlit and pytest both put the repo
   root on `sys.path`, but it is a layering smell. Folding `ui_components` into
   `views/components.py` is a natural follow-up; it was left alone here because it would
   have meant editing image tests during a refactor whose whole claim is that nothing
   else changed.
2. **Page config cannot be one call** while `pages/` exists (§5).
3. **Cache keys do not yet include workflow.** The `@st.cache_data` functions key on
   `as_of` only. Once one view serves several workflows with different behaviour, workflow
   must enter the key or results will leak between workflows. Harmless today because the
   context is ignored.
4. **The enum is in a temporary location** (§6).

---

## 10. Rollback

The refactor is four modified files and one new package:

```bash
git checkout -- app.py pages/1_Vehicle_Detail.py pages/2_Promotion.py tests/unit/test_architecture.py
rm -r src/pricing_agent/views tests/unit/test_views.py docs/view-extraction-results.md
```

`spike_navigation.py` is independent and can be removed separately.

---

## 11. Recommended next phase

**Phase 3 — workflow navigation**, as sequenced in the implementation plan:

1. Add `workflows/registry.py` declaring the four workflows as data, and move
   `WorkflowContext` there from `views/`.
2. Replace filesystem discovery in `app.py` with `st.navigation` built from the registry,
   registering views as `functools.partial(render_x, WorkflowContext.Y)` callables.
3. Add workflow to the `@st.cache_data` keys.
4. Delete `pages/` in the same commit, so there is never a moment with two live navigation
   mechanisms.
5. Update `README.md` and `docs/demo-script.md` in that same commit — both name the
   current sidebar labels.
6. Delete `spike_navigation.py` once the real migration lands.

Improve Aging Inventory orchestration stays out of scope until Phase 4.
