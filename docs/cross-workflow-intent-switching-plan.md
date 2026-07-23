# Cross-workflow intent switching — plan

**Branch:** `fix/cross-workflow-intent-switching` (off merged `main`, which carries Slice 1 + Slice
2). Working tree clean.

**Goal:** when an Improve Aging conversation is active and the user asks a *new top-level workflow*
question (notably a Single Vehicle Valuation), route it to that workflow instead of forcing it into
the active result as a follow-up. Deterministic routing only — the router picks an existing
workflow; it never computes a result.

---

## 1. Root cause (reproduced)

With an Improve Aging result active, `handle_followup("What should I price 2021 Honda Accord EX?")`
runs the A–E follow-up handlers directly. Reference resolution matches "Honda Accord EX" to the
analysed V-10002, and `_explain` returns the Accord's **aging** evidence. Follow-up classification
runs with **no prior check for a new-workflow intent**, so a pricing request is answered as an
aging explanation.

The top-level `route()` already classifies the message correctly as `PRICE_INVENTORY`
(`PRICING_VERB`, `VEHICLE_DESCRIPTOR`) — that signal is simply never consulted inside the
follow-up path.

## 2. Routing order — before vs after

**Before:** `handle_followup` → unsupported → rerun → clarification → filter → **explain** (matched
the Accord).

**After:** `handle_followup` → **detect new workflow** → (if a strong new-workflow intent) switch
and run that workflow → else the existing A–E follow-up handlers.

New-workflow detection runs **first**; a vehicle name alone never forces a switch — the **action
verb** decides.

## 3. Which workflows switch (and which don't)

Confirmed against `route()` for every spec example:

| Message | route() | Decision |
| --- | --- | --- |
| "What should I price 2021 Honda Accord EX?" | PRICE_INVENTORY | **switch** |
| "Price the Honda Accord." / "Run a valuation for V-10002." | PRICE_INVENTORY | **switch** |
| "Is the BMW priced competitively?" / "Revalue the BMW" | PRICE_INVENTORY | **switch** |
| "Why does the Accord require manager review?" | None | follow-up (explain) |
| "Is the Accord below break-even?" / "Why was the Accord selected?" | None | follow-up (explain) |
| "Which aging risks apply to the Accord?" | IMPROVE_AGING | follow-up (same workflow) |
| "Should the Accord be included in Summer Clearance?" | MERCHANDISE | stays in aging (rerun/explain) |
| "Use Summer Clearance" | MERCHANDISE | stays an aging **rerun** |

**Decision rule:** switch **only** when `route()` selects `PRICE_INVENTORY`. Event/promotion
phrases route to `MERCHANDISE` and must remain aging reruns (the aging workflow already
incorporates promotion), so `MERCHANDISE` and `IMPROVE_AGING` routes are *not* switches. A
belt-and-braces **aging-intent guard** (why / selected / aging / wholesale / manager review /
break-even / days on lot / included in / promotion candidate / review condition / no-immediate)
suppresses a switch even if a stray pricing word appears in an explanation question.

`ACQUIRE`/`MERCHANDISE`/`PORTFOLIO` switching is intentionally **out of scope** here: those routes
collide with legitimate aging follow-ups ("how many…", event phrases) and are not part of the bug
or the tests. Documented as a limitation.

## 4. Router vocabulary extension (minimal)

`route()` already catches price / pricing / reprice / value / valuation / worth / "asking price"
(via `price`) / "list it". It misses **revalue**, **appraise/appraisal**, **priced**, and
**"what should I list …"**. `PRICING_TERMS` gains exactly those alternations — nothing else. This
is the "extend the existing router vocabulary only where required" the spec allows; no new
workflow and no calculation.

## 5. Target resolution for the valuation

The valuation needs a specific vehicle. Resolution reuses existing machinery, in order:
1. If `route()` resolved a full identity (id, or make+model) → run the existing
   `run_assistant("price …")` path, which resolves against inventory (EXACT / AMBIGUOUS / NONE).
2. Otherwise resolve the reference against the **active result** with the Slice-2
   `resolve_reference` — "the BMW" → V-10005, "the Accord" → V-10002, "the RAV4" → **V-10001** (the
   analysed one is preferred over the excluded duplicate V-10007; documented and tested), "this
   vehicle"/"it" → the single most-recently-referenced vehicle.
3. Then run the deterministic single-vehicle valuation via `run_assistant("price <id>")`.

**Ambiguity:** a reference matching **two analysed** vehicles ("the 2019 model" → V-10012 +
V-10004) asks the user to choose — never a silent pick. The analysed-over-excluded preference is
the single documented exception, carried over from Slice 2.

## 6. Conversation-state transition

`ConversationState` gains a workflow-history collection and a generic adopt:

```
prior_workflows: list[PriorWorkflow]     # (type, workflow_id, request_id, result, response, timestamp)

switch_to(response):
    if active_result is not None: prior_workflows.append(snapshot of current active)
    last_referenced_vehicle_ids = ()      # drop references that only applied to the prior workflow
    adopt_response(response)              # aging → existing adopt(); else generic adopt

adopt_response(response):
    aging result present → adopt() (unchanged)
    else → set active_workflow_type/id, active_request_id, active_result(dict), active_vehicle_ids,
           active_simulation_ids from response.result.audit; clear event/target/plan
```

On a successful switch: append the user message, append a **workflow-transition** assistant
message ("Switching from Improve Aging Inventory to Single Vehicle Valuation for …"), preserve all
prior messages, push the prior result into `prior_workflows`, and update active_workflow_type /
_workflow_id / _request_id / _result / _vehicle_ids / _simulation_ids. Prior valid results are
never discarded.

## 7. Failure preservation

If the valuation cannot complete — the `run_assistant` call raises, or returns
`EXECUTION_ERROR` — the switch is **not** applied: the previous Improve Aging active result stays
active, an honest error turn is added ("I couldn't complete the valuation; I've kept the previous
analysis."), and there is **no** silent fallback to explaining the old aging result and **no**
fabricated valuation. `NO_MATCH` / `NEEDS_CLARIFICATION` / `AMBIGUOUS_MATCH` produce a
clarification turn (also without switching).

## 8. UI

- The conversation thread renders for **any** active workflow (not only aging).
- A switch turn shows a transition caption ("Switching from Improve Aging Inventory to Single
  Vehicle Valuation.") then the normal Single Vehicle Valuation result (`_render_pricing_result`).
- Prior Improve Aging turns remain visible; the user can keep chatting. `_sync_workspace` seeds the
  Price Inventory preselect on a pricing switch and keeps the aging workspace result in sync while
  aging is active.

## 9. Grounding & safety

Unchanged: valuation / pricing / break-even / P10–P50–P90 logic, candidate selection, approval
rules, schemas, MCP clients, mock data, event logic, price publishing. The router selects an
existing workflow and computes nothing. AST guards keep `followup.py`/`conversation.py` free of the
calculation layer and any publish symbol.

## 10. Files

**New:** `docs/cross-workflow-intent-switching-plan.md`,
`docs/cross-workflow-intent-switching-results.md`,
`tests/unit/test_cross_workflow_switching.py`.
**Modified:** `agents/router.py` (PRICING_TERMS), `agents/conversation.py` (PriorWorkflow,
adopt_response, switch_to, prior_workflows), `agents/followup.py` (detect_new_workflow,
_switch_workflow, _record SWITCH branch), `agents/__init__.py` (exports if needed),
`views/assistant_home.py` (render any active workflow + switch turn), `README.md`,
`docs/demo-script.md`.
**Not touched:** skills, `workflows/` engine, `candidate_selection`, `single_vehicle` valuation,
schemas, `mcp_clients`, mocks, event fixtures.

## 11. Tests (15)

Accord-pricing switches to valuation and is not an aging explanation; the existing valuation
workflow is invoked; active updates only after success; the prior aging result stays in history;
manager-review / below-break-even / aging questions remain follow-ups; "list the Accord for" and
"revalue the BMW" switch; "Use Summer Clearance" stays an aging rerun; an ambiguous request asks;
a failed valuation preserves the prior aging result and does not fall back; no pricing calculation
is added to router/follow-up; Slice-1/Slice-2 suites stay green. Plus `pytest`, `validate_schemas`,
and the browser scenarios.

## 12. Known limitations

- Only `PRICE_INVENTORY` switches from an active aging conversation; portfolio/acquire/merchandise
  intents remain within the aging conversation (rerun/explain) to avoid colliding with aging
  follow-ups. A later pass could add guarded switching for those.
- After switching to a valuation, deep valuation follow-ups are not a full engine yet; the
  valuation result + workspace link is shown and any further message is re-evaluated for a new
  switch (including back to pricing another vehicle). No LLM routing is introduced.
