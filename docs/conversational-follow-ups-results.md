# Conversational Follow-ups (Slice 2) — results

**Branch:** `feat/conversational-follow-ups` (off merged `main` with Slice 1). Not committed.

**Result: PASS.** The Dealer AI Assistant is now multi-turn: after the Slice-1 first answer the
dealer can explain, filter, clarify, or trigger a validated deterministic rerun against the same
result, with full history and workspace continuity. The LLM produces no number; every value is
copied from an existing validated result.

## Conversation-state model

`agents/conversation.py` — `ConversationState` (conversation_id, messages, active_workflow_type /
_workflow_id / _request_id / _result / _response, active_vehicle_ids / _event / _target_utilization
/ _plan / _warnings / _approvals / _simulation_ids, last_user_request, last_assistant_response,
pending_clarification, previous_valid_result, rerun_count, last_referenced_vehicle_ids) and
`ConversationMessage` (role, source, text, result, response, referenced_vehicle_ids,
referenced_workflow_id, timestamp). `adopt(response)` copies every active_* field from a finished
result; rich turns store the result so history re-renders faithfully after a later rerun.

## Follow-up categories implemented

| Cat | Behaviour | Verified example |
| --- | --- | --- |
| **A explain** | from existing fields, no rerun | "Why is the BMW recommended for wholesale?" → 108 days on lot · asking $24,995 · break-even $28,963 · P50 70 / P90 144 · below the $29,859 safe floor |
| **B filter** | select existing rows, no rerun | "Show only vehicles over 90 days" → BMW, Jeep, Nissan; "Which vehicles have safe promotional room?" → Accord, RAV4; "Which vehicles require review?" → 5 vehicles (no 17) |
| **C clarify** | ask for the missing input | "Promote them." → asks which event; "Change the target." → asks for a percentage |
| **D rerun** | validated input, deterministic rerun | "Use Summer Clearance." → reruns, promotes Subaru + RAV4, target likelihood 43% (Capacity First); "Set target utilization to 75%."; "Protect the RAV4." |
| **E unsupported** | refuse, invent nothing | "Which vehicle has the most VDP views?" → shopper data unavailable; "Publish the new price." → never publishes |

## Reference resolution (deterministic)

"the BMW" → V-10005; "the wholesale vehicles" → {V-10005, V-10012, V-10004}; "those two
vehicles" → the most recently referenced pair; "the RAV4" → V-10001 (prefers the analysed one
over the excluded duplicate V-10007); "the 2019 model" → **ambiguous** (V-10012, V-10004) → asks.
Group / plan / event references resolve against the active result; a make matching two analysed
vehicles is never silently collapsed.

## Rerun rules

Modified `ImproveAgingRequest` via `dataclasses.replace(active.request, …)`; run
`run_improve_aging`; on success set `previous_valid_result`, adopt the new result, `rerun_count
+= 1`, render a what-changed summary from existing fields only; on failure keep the previous
active result and show the error. Verified: a monkeypatched failing rerun leaves the active
result, event, and rerun_count untouched.

## Approval presentation (unchanged Slice-1 rule)

"Which vehicles require review?" answers **5 vehicles** and the string "17" never appears in the
default chat; the 17 raw records remain in the result and in the workspace "View approval
details". `active_approvals` carries all 17 unchanged.

## No-rerun vs rerun

- **No rerun** (rerun_count stays 0): explain, all filters, clarification, unsupported.
- **Rerun** (rerun_count increments, active replaced only on success): add event, change target,
  protect/exclude a resolved vehicle.

## Grounding & safety

`agents/conversation.py` and `agents/followup.py` import neither `pricing_agent.domain` nor
`pricing_agent.simulation` and contain no `percentile` / `np.mean` / `np.average` / `simulate(` /
price-publishing symbols (AST-guarded). Reruns invoke the existing deterministic workflow; no
independent simulations are combined and no synthetic delta is computed.

## Invariants (before = after)

- Selected IDs: `[V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001]` — unchanged by
  explain/filter; changed only by an explicit exclude rerun (as designed).
- Excluded IDs: `[V-10003, V-10007, V-10009, V-10010, V-10011]` — unchanged by explain/filter.
- Final actions unchanged by explain/filter; V-10008/V-10001 stay `NO_ACTION`, V-10002/V-10006
  `MANAGER_REVIEW`, three wholesale.
- Numerical baseline unchanged — the follow-up layer copies fields, never recomputes.
- 17 raw approval records unchanged.

## Files

**New:** `agents/conversation.py`, `agents/followup.py`,
`tests/unit/test_conversation_state.py`, `tests/unit/test_followup_handlers.py`,
`docs/conversational-follow-ups-plan.md`, `docs/conversational-follow-ups-results.md`.
**Modified:** `agents/assistant.py` (`wrap_improve_aging`), `agents/__init__.py` (exports),
`views/assistant_home.py` (thread + chat input + clickable follow-ups), `README.md`,
`docs/demo-script.md`.
**Not touched:** skills, `workflows/` engine, `candidate_selection`, schemas, `mcp_clients`,
mocks, event fixtures, calculations, price publishing. First-turn routing unchanged.

## Tests / checks

- `python -m pytest tests -q` → **508 passed** (482 prior + 26 new).
- `python scripts/validate_schemas.py` → **62 checks passed**.
- Browser smoke reviewed: first turn (thread + chat input + clickable follow-ups, all vehicles,
  no 17); explanation follow-up (grounded, "🔎 From your current analysis", prior turn kept);
  event rerun via suggestion (🔄 chip, promoted Subaru+RAV4, 43% likelihood, prior turns
  preserved, updated-workspace link). No server errors.

## Known limitations

- Reruns cover event, target, and exclusions (the inputs `run_improve_aging` accepts). Plan
  choice and window-extension are not engine parameters → answered from pre-computed plans or
  clarified, never fabricated.
- Streamlit `st.chat_input` submits via its send button in the embedded browser; Enter alone may
  not submit in that harness (works normally in a real browser).
- Follow-up classification is conservative keyword/entity matching; novel phrasings fall to
  clarification. No LLM phrasing layer is enabled in this slice.
- Multi-turn conversation is implemented for the Improve Aging result; other workflows keep their
  Slice-1 single-turn summaries.

## Exact next recommended step

Review Slice 2; if approved, **commit** it (no auto-commit was performed). A natural Slice 3
would extend reruns to the plan-comparison selection (answering "what changes with the Balanced
plan?" from the already-computed plans as a first-class turn) and add an optional guarded LLM
phrasing layer over the deterministic answers.
