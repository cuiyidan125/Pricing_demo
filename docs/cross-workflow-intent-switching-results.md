# Cross-workflow intent switching — results

**Branch:** `fix/cross-workflow-intent-switching` (off merged `main` with Slice 1 + Slice 2). Not
committed.

**Result: PASS.** With an Improve Aging conversation active, a new top-level pricing request now
switches to the Single Vehicle Valuation workflow instead of being answered as an aging
explanation. Genuine aging follow-ups (explain, filter, rerun) stay put. Deterministic routing
throughout; the router selects an existing workflow and computes nothing.

## Root cause

`handle_followup` ran the A–E follow-up handlers with no prior check for a new-workflow intent.
"What should I price 2021 Honda Accord EX?" matched the analysed V-10002 by reference resolution,
so `_explain` returned the Accord's **aging** evidence. The top-level `route()` already classified
the message as `PRICE_INVENTORY`, but that signal was never consulted inside the follow-up path.

## Routing order — before / after

- **Before:** unsupported → rerun → clarification → filter → **explain** (matched the Accord).
- **After:** **unsupported** → **detect new workflow** (switch if a strong pricing intent) → aging
  A–E follow-ups. (Unsupported/publish is checked first so "publish the price" can never be read
  as a valuation.)

## New workflow intents supported

Single Vehicle Valuation (`PRICE_INVENTORY`) only. Confirmed against `route()` for every example:

**Switch** — "What should I price 2021 Honda Accord EX?" · "Price the Honda Accord." · "Run a
valuation for V-10002." · "Is the BMW priced competitively?" · "Revalue the BMW" · "What should I
list the Accord for?"

**Stay a follow-up** — "Why does the Accord require manager review?" (explain) · "Why was the
Accord selected?" (explain) · "Is the Accord below break-even?" (explain) · "Which aging risks
apply to the Accord?" · "Should the Accord be included in Summer Clearance?" · "Show me the aging
evidence for the Accord." · "Use Summer Clearance" (**aging rerun**).

The decision rule is: switch only when `route()` selects `PRICE_INVENTORY`; event/promotion
phrases route to `MERCHANDISE` and remain aging reruns; same-workflow (`IMPROVE_AGING`) routes are
follow-ups. An explicit aging-intent guard (why / selected / aging / wholesale / manager review /
break-even / days on lot / included in / promotion candidate / review condition / no-immediate)
keeps a message a follow-up even if it brushes a pricing word.

## Router vocabulary extension (minimal)

`PRICING_TERMS` gained `revalue`, `re-valuation`, `appraise/appraisal`, `priced`, `list price`,
and `what should I list` — nothing else. No new workflow, no calculation.

## State-transition behavior

`ConversationState` gained `prior_workflows: list[PriorWorkflow]` and `adopt_response` /
`switch_to`. On a successful switch: the user message is appended, a workflow-transition assistant
message is added ("Switching from Improve Aging Inventory to Single Vehicle Valuation for 2021
Honda Accord EX."), all prior messages are preserved, the prior aging result is pushed to
`prior_workflows`, and `active_workflow_type` / `_workflow_id` / `_request_id` / `_result` /
`_vehicle_ids` / `_simulation_ids` are updated. References that only applied to the prior workflow
are cleared.

## Target resolution & ambiguity

Reuses the Slice-2 `resolve_reference`: "the BMW" → V-10005, "the Accord" → V-10002, "the RAV4" →
**V-10001** (the analysed one is preferred over the excluded duplicate V-10007 — the single
documented exception, tested). A reference matching two analysed vehicles ("the 2019 model" →
V-10012 + V-10004) asks the user to choose; it never silently switches.

## Failure preservation

A failing valuation (the `run_assistant` call raises, or returns `EXECUTION_ERROR`) does **not**
switch: the previous Improve Aging active result stays active, an honest error turn is added ("I
couldn't complete the valuation; I've kept the previous analysis."), `prior_workflows` stays
empty, and there is no fallback to explaining the old aging result and no fabricated valuation.
`NO_MATCH` / `NEEDS_CLARIFICATION` / `AMBIGUOUS_MATCH` produce a clarification, also without
switching.

## Grounding / invariants (unchanged)

Valuation, pricing, break-even, P10/P50/P90, candidate selection, approval rules, schemas, MCP
clients, mock data, event logic, and price publishing are untouched. AST guard confirms
`router.py`, `followup.py`, and `conversation.py` import no calculation layer and contain no
`percentile` / `simulate(` / `np.mean` / publish symbols.

## Files

**New:** `agents` (none) · `tests/unit/test_cross_workflow_switching.py`,
`docs/cross-workflow-intent-switching-plan.md`, `docs/cross-workflow-intent-switching-results.md`.
**Modified:** `agents/router.py` (PRICING_TERMS), `agents/conversation.py` (PriorWorkflow,
adopt_response, switch_to, prior_workflows, SOURCE_SWITCH), `agents/followup.py`
(detect_new_workflow, _switch_workflow, unsupported-first ordering, _record SWITCH branch,
specific-vehicle explain preference), `agents/__init__.py` (export PriorWorkflow),
`views/assistant_home.py` (render any active workflow + switch turn + workspace preselect),
`README.md`, `docs/demo-script.md`.
**Not touched:** skills, `workflows/` engine, `single_vehicle` valuation, `candidate_selection`,
schemas, `mcp_clients`, mocks, event fixtures.

## Tests / checks

- `python -m pytest tests -q` → **534 passed** (508 prior + 26 new).
- `python scripts/validate_schemas.py` → **62 checks passed**.
- Browser scenarios verified: aging first turn, then "What should I price 2021 Honda Accord EX?" →
  "🔀 Switched workflow" chip, "Switching from Improve Aging Inventory to Single Vehicle
  Valuation" transition, the valuation result rendered, the prior aging thread preserved, no server
  errors.

## Known limitations

- Only `PRICE_INVENTORY` switches from an active aging conversation; portfolio/acquire/merchandise
  intents remain within the aging conversation (rerun/explain) to avoid colliding with legitimate
  aging follow-ups ("how many…", event phrases). A future pass could add guarded switching for
  those.
- After switching to a valuation, deep valuation follow-ups are not yet a full engine: the
  valuation result and workspace link are shown, and any further message is re-evaluated for a new
  switch (including pricing another vehicle). Returning to the aging analysis is available by
  asking a fresh aging question in the main box (which starts a new conversation).
- No LLM routing is introduced; classification is deterministic keyword/entity matching.
