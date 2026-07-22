# Navigation Spike Results

**Phase 1 of `docs/dealer-workflow-implementation-plan.md`.**
**Result: PASS** — `st.navigation` can replace filesystem page discovery while preserving
all existing page behaviour.

Nothing has been migrated. The spike runs alongside the real app and is deleted by
removing one file.

---

## 1. Approach

Rather than converting `app.py` and risking the working demo, the spike is a **separate
entry script** that groups the existing page files under dealer workflows:

```bash
streamlit run spike_navigation.py --server.port 8502    # spike
streamlit run app.py                                    # real app, port 8501, untouched
```

Both were run at the same time. The real app kept its flat `app / Vehicle Detail /
Promotion` sidebar throughout, which is the proof that nothing was disturbed.

The spike renders its own findings into the sidebar, so it reports on itself rather than
relying on interpretation of a screenshot.

Workflow groups exercised:

| Group | Pages | Target script |
| --- | --- | --- |
| Acquire Inventory | Portfolio capacity | `app.py` |
| | Vehicle valuation | `pages/1_Vehicle_Detail.py` |
| Price Inventory | Price a vehicle | `pages/1_Vehicle_Detail.py` |
| Merchandise Inventory | Event promotion | `pages/2_Promotion.py` |

Improve Aging Inventory is deliberately absent — orchestration is a later phase.

Acquire Inventory is scoped to portfolio capacity and acquisition readiness. It makes no
claim to appraise an external candidate: the single-vehicle skill requires a `vehicle_id`
already present in dealer inventory, so ad-hoc appraisal stays a future enhancement rather
than something the navigation quietly implies.

---

## 2. Files changed

| File | Status |
| --- | --- |
| `spike_navigation.py` | **new, temporary** — the entire spike |
| `docs/navigation-spike-results.md` | new — this document |

**No other file was touched.** `app.py`, both page scripts, all skills, schemas, domain,
simulation, policy, MCP clients, scenarios and configs are unmodified.

---

## 3. Findings

### 3.1 Does `st.navigation` work? — **Yes**

Streamlit 1.60 has both `st.navigation` and `st.Page`. Grouped navigation rendered with
workflow headers in the sidebar and the four page entries beneath them. All three page
scripts ran to completion: the dashboard with its tabs and image table, the vehicle detail
page with photo and charts, and the promotion planner with its three plans.

Server log across the whole session contained **no errors or tracebacks**.

### 3.2 Can one page appear under several workflows? — **Yes**

This was the open question from the plan, and it is the one that decides whether view
extraction is mandatory.

`pages/1_Vehicle_Detail.py` was registered twice — as *"Vehicle valuation"*
(`url_path="acquire-vehicle"`) and *"Price a vehicle"* (`url_path="price-vehicle"`).
Streamlit accepted both, rendered both, and the in-app visit log recorded both as distinct
pages. **Distinct `url_path` and `title` per registration is sufficient; the same script
may back several entries.**

### 3.3 `st.set_page_config` in page scripts — **no error, but last call wins**

Each of the three page scripts calls `st.set_page_config` today, and so does the spike's
entry script. This does **not** raise. What happens instead is that the page's call
overrides the entry's: the browser tab title read *"Used Vehicle Pricing Advisor"* on the
dashboard and *"Promotion Planner"* on the promotion page, never the spike's own title.

Harmless here, and arguably desirable — per-page titles are good. But it means page config
is set in four places, and `layout="wide"` is repeated in each. Worth centralising during
the real migration rather than leaving four sources of truth.

### 3.4 Session state — **preserved in-app, reset on hard URL navigation**

The app has **no `st.session_state` usage at all** today, so the spike injected a probe: a
run counter, a visit log, and a button-driven counter.

* **In-app navigation preserves state.** After six sidebar navigations across all four
  entries and ten script runs, the visit log had accumulated every page and the
  button-driven counter held its value.
* **A hard browser navigation to a `url_path` starts a new session.** Loading
  `http://localhost:8502/merchandise-event` directly reset the run counter to 1 and
  emptied the visit log.

That second point is ordinary Streamlit behaviour rather than a navigation defect, but it
matters for the workflow design: **anything a workflow remembers must be reconstructible
from the URL or from defaults**, because a deep link arrives with an empty session. It
argues against carrying a selected vehicle across workflows in session state alone.

### 3.5 Direct page selection — **works**

`/merchandise-event` loaded the promotion page directly and the sidebar highlighted the
correct entry under Merchandise Inventory. Custom `url_path` values are honoured, so
workflow-shaped URLs are available without extra routing.

### 3.6 Compatibility with the existing pages — **complete, no changes needed**

The page scripts ran unmodified. Their sidebar widgets (`Vehicle` selectbox, `Event`
selectbox, `Target utilization` slider, `30-day revenue target` input) all rendered and
functioned. No widget-key collisions appeared — the labels differ per page, so Streamlit's
auto-generated keys do not clash.

### 3.7 Test suite — **unaffected**

```
python -m pytest tests -q            158 passed
python scripts/validate_schemas.py   PASSED  62 checks
```

The spike file is not imported by any test and not scanned by
`tests/unit/test_architecture.py`, which walks only `domain/` and `simulation/`.

### 3.8 Incidental finding, unrelated to navigation

The spike's server log surfaced a deprecation the main app's log had been hiding:

```
Please replace `st.components.v1.html` with `st.iframe`.
`st.components.v1.html` will be removed after 2026-06-01.
```

`components.html` is what renders **every vehicle photo and every silhouette**. The
removal date has already passed on this build, so a Streamlit upgrade would break all
vehicle imagery. This is the same class of trap as the `use_container_width` deprecation
fixed earlier, and it is pre-existing — the spike merely revealed it. Worth a small
separate change; it does not belong in the navigation work.

---

## 4. Is view extraction required?

**Not for navigation to work — but yes, before the real migration.** These are different
questions and the honest answer differs.

Navigation alone does not need it: §3.2 shows raw script targets can be reused across
workflows. If the only goal were relabelling the same three screens under workflow
headings, the spike could be promoted almost as-is.

Extraction is required for what comes next:

1. **Workflows need to differ, not just be relabelled.** Single-vehicle valuation appears
   under Acquire, Price, and Improve Aging with genuinely different intent. A raw script
   target takes no arguments, so all three would render identically. `st.Page` also
   accepts a **callable**, and a callable can be parameterised with
   `functools.partial(render_vehicle, workflow="PRICE")`. That is the seam.
2. **Improve Aging Inventory cannot be a filesystem script.** It orchestrates three skills
   and must be callable with context.
3. **`set_page_config` is currently set in four places** (§3.3). Extraction centralises it.
4. **Caching keys.** The existing `@st.cache_data` functions key on `as_of` only. Once one
   view serves several workflows, workflow context must enter the cache key or results
   will leak between workflows.

So: extract views in Phase 2, then migrate navigation in Phase 3, exactly as the plan
sequenced it. The spike confirms the sequence rather than changing it.

---

## 5. Risks

| Risk | Severity | Note |
| --- | --- | --- |
| Deep links arrive with empty session state | Medium | §3.4. Workflow state must be reconstructible from URL or defaults. |
| Cache leakage between workflows sharing a view | Medium | Add workflow to the `@st.cache_data` key when views become parameterised. |
| `set_page_config` in four places | Low | Centralise during extraction. |
| `st.components.v1.html` removal breaks all vehicle imagery | Medium | Pre-existing, unrelated to navigation, fix separately. |
| `url_path` changes break existing bookmarks | Low | `/Vehicle_Detail` → `/price-vehicle`. Local only. |
| `pages/` directory left in place after migration | Medium | Once `st.navigation` is in `app.py`, a stray `pages/` directory is ignored — but leaving it invites confusion about which is live. Remove in the same commit. |

---

## 6. Rollback

```bash
rm spike_navigation.py
```

That is the whole rollback. No other file was modified, so `git status` should show only
this document afterwards. The real app on `app.py` was never altered and kept running on
port 8501 throughout.

To stop the spike server:

```powershell
Get-NetTCPConnection -LocalPort 8502 -State Listen |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

---

## 7. Recommended final implementation

1. **Extract views** — move the bodies of `app.py`, `pages/1_Vehicle_Detail.py` and
   `pages/2_Promotion.py` into render functions taking a workflow context argument.
   Existing pages become one-line callers. Verify by screenshot comparison; a pure
   refactor that changes pixels is a failed refactor.
2. **Centralise `set_page_config`** into the entry script during that move.
3. **Build the workflow registry** as data (`workflows/registry.py`), then have `app.py`
   construct `st.navigation` from it rather than from a hard-coded dict as the spike does.
4. **Register views as callables**, parameterised per workflow with `functools.partial`.
5. **Add workflow to cache keys** wherever a shared view is cached.
6. **Delete `pages/`** in the same commit that switches `app.py` to `st.navigation`, so
   there is never a moment with two live navigation mechanisms.
7. **Delete `spike_navigation.py`** once the real migration lands.

Improve Aging Inventory remains out of scope until the orchestration phase.
