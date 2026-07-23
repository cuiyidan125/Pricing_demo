# Phase 4 — Deterministic natural-language routing and single-skill execution

**Result: PASS.** The Ask the Dealer AI Assistant page now classifies a question, resolves
the named vehicle against real inventory, runs one skill, and shows a concise result with a
link into the full workspace — all deterministically, with no model in the path. Improve
Aging is routed but deliberately not executed.

**Companion to** `docs/workflow-navigation-results.md` (Phase 3, which built the shell this
connects) and `docs/architecture.md` §3.5.

---

## 1. The flow

```
text → classify intent → parse vehicle → resolve against inventory → run one skill
     → concise summary (copied from the result) → link to the full workspace
```

Three deterministic modules under `src/pricing_agent/agents/`:

| Module | Responsibility | Produces a number? |
| --- | --- | --- |
| `router.py` | Intent by keyword precedence; vehicle entity extraction with per-field confidence | **No** — extracted values are the user's own words, copied through |
| `resolver.py` | Match the parsed vehicle to a real inventory record | No |
| `assistant.py` | Orchestrate: run one skill, select summary fields, return a state | No — every figure is copied from the skill result |

No LLM is imported or called anywhere in this path. `test_assistant.py` makes any model call
raise and asserts the pricing path still executes.

---

## 2. Supported and unsupported intents

| Intent | Workflow | Skill | Executes this phase? |
| --- | --- | --- | --- |
| Price a vehicle | PRICE_INVENTORY | single-vehicle-valuation | **Yes**, when a vehicle resolves uniquely |
| Portfolio / forecast / capacity | ACQUIRE_INVENTORY | inventory-portfolio-forecast | **Yes** |
| Sale event | MERCHANDISE_INVENTORY | dealer-event-promotion-planner | **Yes**, when an event resolves on the calendar |
| Aging cohort | IMPROVE_AGING_INVENTORY | (all three) | **No** — returns WORKFLOW_NOT_YET_AVAILABLE |

Routing precedence, most specific first, so overlapping signals resolve correctly:

```
aging cohort   ("which aging vehicles should I promote?")   → IMPROVE_AGING
promotion      ("create a labor day promotion plan")        → MERCHANDISE
forecast       ("what will inventory look like in 30 days") → ACQUIRE
pricing        ("what should I price the F-150")            → PRICE
```

"which aging vehicles should I **promote**?" contains a promotion verb but is an aging
question — aging cohort is tested before promotion, so it routes to Improve Aging. The
router returns `selected_workflow`, `required_skill`, `confidence`, `reason_codes`,
`extracted_entities`, `missing_fields`, `ambiguous_fields`, and `execution_allowed`.

---

## 3. Vehicle entity extraction

For a pricing request the parser pulls, when present: `vehicle_id`, `VIN`, `year`, `make`,
`model`, `trim`, `mileage` — each with a confidence, and never a guess for a field the user
did not state.

Normalization (so spelling variants resolve): `F150` / `F 150` → `F-150`, `RAV 4` → `RAV4`,
`CRV` / `cr v` → `CR-V`, `Model 3` variants, and so on. Mileage understands `42,000 miles`,
`42000 mi`, and `42k`.

What it will **not** do:

* Guess a trim, mileage, or id that was not stated (`test_does_not_guess_a_trim`).
* Pick one of two matched trims silently — it flags `trim` as ambiguous instead.
* Read a 17-digit number as a VIN (a real VIN is never all digits).

---

## 4. Vehicle resolution

Priority, each tier requiring a unique match:

1. exact `vehicle_id`
2. exact VIN
3. year + make + model + trim
4. year + make + model
5. make + model (a unique match is not a guess even without the year)

Model comparison ignores punctuation, so `F150` matches the fixture's `F-150`.

| Outcome | Behaviour |
| --- | --- |
| One match | EXACT → the skill runs |
| More than one | AMBIGUOUS → the candidates are shown; the assistant picks nothing |
| No inventory match | NO_MATCH → a clear message; **no vehicle is fabricated** |
| Too little to resolve | INSUFFICIENT → a request for year/make/model/trim |

A stated trim that matches nothing does not dead-end into NO_MATCH when the make/model do
match — it surfaces the make/model candidates, so "2022 Toyota RAV4 LIMITED" (no LIMITED on
the lot) shows the two RAV4 XLEs rather than nothing.

---

## 5. The six assistant states

| State | When | What the dealer sees |
| --- | --- | --- |
| ROUTED_AND_EXECUTED | A supported workflow ran | Detected workflow, matched vehicle, skill, concise metrics, top warnings, link to the full workspace |
| NEEDS_CLARIFICATION | Missing vehicle, unresolvable event, or unclear intent | A specific question ("Which vehicle…?", "Which event…?") |
| NO_MATCH | Vehicle not in inventory | Plain statement that the MVP analyses inventory it already holds |
| AMBIGUOUS_MATCH | Several vehicles match | The candidates, each with an "Analyze this one" button |
| WORKFLOW_NOT_YET_AVAILABLE | Improve Aging | Transparent "orchestration not connected yet" + link to the sequence |
| EXECUTION_ERROR | A skill raised | The failure surfaced as a state, never a crash |

For a successful pricing request the concise summary shows current list price, recommended
price, P50 and P90 days to sale, break-even, promotional headroom, and the top warnings —
**every one copied from the skill result**, with `test_every_summary_number_comes_from_the_skill_result`
asserting field-by-field equality.

---

## 6. Opening the full workspace

The result carries a link to the full Price Inventory workspace, and it opens on the
resolved vehicle. Two details made this correct:

* **Preselect via a stable session key.** On submit, the resolved `vehicle_id` is written to
  `st.session_state["assistant_selected_vehicle_id"]`; `render_vehicle_detail` pops it and
  seeds the selectbox before the widget is created. It is popped so a later manual change
  wins.
* **Client-side navigation.** The link is an `st.page_link` to the live `st.Page`, not a raw
  HTML anchor. **This was a real bug caught in smoke testing:** the first implementation used
  `<a href="/price-inventory">`, which does a full browser reload and wipes session state, so
  the workspace opened on the default vehicle instead of the routed one. `app.py` now
  registers each page by `url_path` in `workflows/pages.py`, and the assistant links through
  the registered `st.Page` — verified in-browser to land on V-10003 with session intact.

---

## 7. Session state

Held under stable, non-widget keys (Streamlit garbage-collects unmounted widget state):

| Key | Holds |
| --- | --- |
| `assistant_question` | The original text |
| `assistant_response` | The `AssistantResponse` (workflow, skill, resolved id, summary, result, state) |
| `assistant_selected_vehicle_id` | The routed vehicle, for the Price Inventory preselect |

`SESSION_KEY` is kept as an alias of `assistant_question` for continuity with earlier phases.

---

## 8. The demo request

**"What should I price 2020 Ford F-150 XLT?"** resolves to **V-10003** (2020 Ford F-150 XLT,
in the fixture) and runs the single-vehicle valuation skill. No fixture change was needed —
the vehicle already exists. The suggested prompts on the page were updated so each routes to
a guaranteed outcome:

| Prompt | Outcome |
| --- | --- |
| What should I price 2020 Ford F-150 XLT? | Executes → V-10003 |
| What will my inventory look like in the next 30 days? | Executes → portfolio forecast |
| Plan the Summer Clearance event to reach 70% utilization. | Executes → promotion plan |
| Which aging vehicles should I promote? | Routed → Improve Aging, deferred |

---

## 9. Verification

```
python -m pytest tests -q          350 passed   (225 before Phase 3.1, +41 copy, +83 routing, +1 page reg)
python scripts/validate_schemas.py PASSED  62 checks
```

New tests: `test_router.py` (intent precedence, entity extraction, normalization, the
router-generates-no-number property), `test_resolver.py` (exact / ambiguous / none /
insufficient, no fabrication), `test_assistant.py` (all six states, exactly-one-skill,
result preserved, summary numbers copied, no model called even when one is available, no
write path, the demo request end to end).

Three Phase 3 tests were updated because Phase 4 supersedes them: the assistant now routes
(so it may reference `pricing_agent.agents`, but still never a model or the write path); the
"routing is not connected" disclaimer is gone; and the suggested prompts changed. The
`workflow_copy` test that forbids branching on workflow identity now exempts
`assistant_home.py`, whose job *is* to dispatch rendering by workflow.

### Smoke tests, in the running app

| Scenario | Result |
| --- | --- |
| Successful vehicle pricing | F-150 XLT → V-10003; metrics $32,995 / $33,095 / 32 (P90 70) / $30,908; routed expander correct |
| Open full analysis | `st.page_link` navigates client-side to Price Inventory **on V-10003** (2020 Ford F-150 XLT), session preserved |
| Missing vehicle | NEEDS_CLARIFICATION — "Which vehicle…?" |
| Ambiguous vehicle | AMBIGUOUS_MATCH — both 2022 RAV4 XLE (V-10001, V-10007) with "Analyze this one" buttons |
| No matching vehicle | NO_MATCH — "analyzes vehicles already in dealer inventory" |
| Portfolio request | Executes — 12 units, 86% utilization |
| Promotion request | Summer Clearance plan executes; "July 4th" (no calendar match) → clarification |
| Improve-aging request | WORKFLOW_NOT_YET_AVAILABLE |

No server errors on any run.

---

## 10. Known limitations

1. **The assistant is the default page, served at `/`.** Navigating directly to `/ask`
   returns Streamlit's "Page not found" and falls back to the main page. Direct-linking the
   assistant should use `/`, not `/ask`. Pre-existing to this phase; noted because Phase 4
   is the first to lean on the assistant URL.
2. **Promotion target defaults to 70%** when the request states no percentage. Reasonable,
   but it is an assumed value; the plan says so.
3. **Event matching is name- or holiday-window based.** "July 4th" resolves to no event
   because no calendar window contains July 4 — honest, but a dealer who *means* the
   late-July clearance has to name it. A fuzzier matcher is deliberately not built.
4. **One skill only.** By design this phase. A request that would need two skills
   (Improve Aging) is routed and deferred, never partially executed.
5. **Streamlit text-commit quirk.** Typing into the box and clicking Analyze commits the
   text on blur; automated testing had to Tab out first. Real users clicking away or the
   button directly are unaffected, but it is why the smoke tests press Tab before Analyze.

---

## 11. Next phase

1. **LLM-based routing**, sitting *above* the deterministic router — the model chooses a
   workflow and extracts entities into the same `RouteResult` shape, the deterministic
   resolver and skills stay exactly as they are, and §4.1 still holds: the model selects,
   it never produces a figure. The deterministic router remains as the offline fallback.
2. **Improve Aging orchestration** — coordinate the three skills against the aged cohort,
   presenting results side by side (never summing percentiles across simulations, §12.5).
3. **Multi-vehicle and comparative requests** ("price my three oldest trucks").
4. The `/ask` direct-link fix (§10.1).
