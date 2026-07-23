# Conversational Follow-ups (Slice 2) — plan

**Branch:** `feat/conversational-follow-ups` (off merged `main`, which carries Slice 1 — PR #7).
Working tree clean.

**Goal:** add multi-turn follow-up behaviour to the Dealer AI Assistant. After the Slice-1
first-turn answer, the dealer can ask follow-ups against the *same* structured result — explain,
filter, clarify, or trigger a validated deterministic **rerun** — with full conversation history
and workspace continuity. **The LLM never produces a number; every value is copied from an
existing validated result.**

Slice 1 behaviour is the baseline and is not changed except where the conversation wrapper must
integrate it (the first-turn rich answer becomes the first assistant turn in a thread).

---

## 1. Confirmed baseline (unchanged, source of truth)

"Which aging vehicles should I promote?" (no event, `as_of 2026-07-29`):
7 analysed [V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001] · 5 immediate
[V-10005/12/02/06/04] · 2 no-immediate [V-10008, V-10001] · excluded [V-10003, 07, 09, 10, 11] ·
5 review-condition vehicles · 17 raw records · 2 `MANAGER_REVIEW`. Currently-over-90 =
{V-10005 BMW, V-10012 Jeep, V-10004 Nissan Altima}.

---

## 2. Conversation-state model (`agents/conversation.py`)

Deterministic dataclasses held in one Streamlit `session_state` key (`CONVERSATION_KEY`).

```
ConversationState
  conversation_id: str
  messages: list[ConversationMessage]          # full, ordered, never truncated
  active_workflow_type: str | None
  active_workflow_id: str | None
  active_request_id: str | None
  active_result: ImproveAgingResult | None     # the current grounded result
  active_response: AssistantResponse | None     # carries target_url / summary / route
  active_vehicle_ids: tuple[str, ...]
  active_event: str | None
  active_target_utilization: float | None
  active_plan: str | None
  active_warnings: tuple[dict, ...]
  active_approvals: tuple[dict, ...]            # the 17 raw records, unchanged
  active_simulation_ids: tuple[str, ...]
  last_user_request: str | None
  last_assistant_response: str | None
  pending_clarification: str | None
  previous_valid_result: ImproveAgingResult | None   # kept across a rerun until it succeeds
  rerun_count: int
  last_referenced_vehicle_ids: tuple[str, ...]  # backs "those two vehicles"

ConversationMessage
  role: "user" | "assistant"
  source: user | first_turn | rerun | explanation | filtered_result |
          existing_result | clarification | unsupported | error
  text: str
  result: ImproveAgingResult | None            # set for rich turns (first_turn / rerun)
  response: AssistantResponse | None
  referenced_vehicle_ids: tuple[str, ...]
  referenced_workflow_id: str | None
  timestamp: str
```

`adopt(response)` populates every `active_*` field from an `AssistantResponse` whose
`improve_aging` is set (workflow_id, request_id, sim ids, vehicle ids, event, target, plan,
warnings, the 17 approvals). Rich turns store the `result` so history re-renders faithfully even
after a later rerun changes the active result.

Corrupt-state handling: if the stored object cannot be read as a `ConversationState`, the view
resets **only** the conversation key and explains it; a recoverable workflow result in
`improve_aging_result` is left intact.

---

## 3. Reference resolution (deterministic)

`resolve_reference(text, state) -> ReferenceMatch(ids, label, ambiguous)` against the active
result — never the LLM alone:

| Phrase | Resolves to |
| --- | --- |
| `V-10005`, a VIN | that id |
| "the BMW", "2019 Jeep Wrangler", make/model/trim | `parse_vehicle` → match on active descriptions |
| "the wholesale vehicles" | action `WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW` |
| "manager review vehicles" | action `MANAGER_REVIEW` |
| "the protected/excluded vehicles" | `selection.exclusions` |
| "the five vehicles", "immediate action" | the 5 immediate |
| "the two vehicles", "those two", "no immediate action" | the 2 no-immediate (or `last_referenced_vehicle_ids`) |
| "the recommended plan" | `active_plan` |
| "the same event" | `active_event` |

A make matching **more than one** vehicle sets `ambiguous=True`; the handler lists the options
and asks — it never silently picks one. Each resolution updates `last_referenced_vehicle_ids`
so a subsequent "those two" refers to the most recent pair.

---

## 4. Follow-up classifier (`agents/followup.py`, rules-first, first match wins)

`classify(text, state) -> FollowupIntent(category, …)`, then `handle_followup(text, state, *,
as_of) -> FollowupResult`. Order is chosen so a rerun is never mistaken for an answer:

1. **E — Unsupported/unavailable.** Keywords for data the prototype does not have or actions it
   must not take: `vdp|page views|shopper|leads?|conversion|live market|market supply|days
   supply|publish`. State it is unavailable; invent nothing; never publish. (`publish` is caught
   here so it can never reach a rerun.)
2. **D — Rerun.** A resolvable **event** not already active, a **target %**, or an
   **exclude/protect** of a resolvable vehicle → build a modified `ImproveAgingRequest` from
   `active_result.request` and re-run `run_improve_aging`. Preserve the previous result until the
   new one succeeds.
3. **C — Clarification.** A rerun-shaped verb with **no** resolvable entity — "promote them",
   "use the event", "change/lower the target" — → ask one concise question for the missing
   event / target / vehicle; keep the active result.
4. **B — Filter.** "show only…", "which vehicles…" over: over-90 (`CURRENTLY_OVER_90/120_DAYS`),
   wholesale-review / manager-review (action), safe promotional room
   (`HIGH_SAFE_PROMOTIONAL_HEADROOM`), depreciation risk (`HIGH_DEPRECIATION_RISK`), inbound
   pressure (`INBOUND_REPLACEMENT_PRESSURE`), below break-even (approval
   `BELOW_PROJECTED_BREAK_EVEN`), requires-review (non-empty approvals), no-immediate-action.
   Filters existing rows; **no rerun**.
5. **A — Explain.** "why …" + a vehicle reference (or any bare vehicle reference) → explain from
   that vehicle's final action, reason codes, warnings, approvals, days on lot, current/proposed
   price, P50/P90 days, break-even, minimum-safe price, headroom. **No rerun, no new number.**
6. **Fallback → C** with a general "could you rephrase / here's what you can ask" clarification.

"Use the Balanced plan": if an event is active, explain that plan from the already-computed
`promotion_result.plans` (A, no rerun); otherwise clarify (need an event first). Documented as a
limitation — plan choice is a display selection over pre-computed plans, not an engine parameter.

---

## 5. Rerun mechanics & comparison

`assistant.py` gains `wrap_improve_aging(result, routed, message=None) -> AssistantResponse` so a
follow-up can run the workflow with an explicit request and reuse the Slice-1 summary/warnings/
url wrapping. The follow-up builds the new request with `dataclasses.replace(active.request,
…)`:

- **event:** `event_requested=True, event_id, event_name` from `resolve_event`.
- **target:** `target_utilization` from `parse_explicit_target`.
- **exclude/protect:** append the resolved id to `excluded_vehicle_ids`.

Flow: show "Re-running the Improve Aging analysis with …"; run inside `try`; on **success** set
`previous_valid_result = active_result`, adopt the new result, `rerun_count += 1`, and render a
**what-changed** summary from existing fields only — event added, target changed, recommended
plan changed, vehicles newly promoted / removed, target likelihood, approvals count (vehicle-
based). On **failure** (exception or an unexpected error state) keep the previous active result,
show the error, fabricate nothing. No synthetic deltas; no combining independent simulations.

---

## 6. Approval presentation (unchanged Slice-1 rule)

Default chat and workspace show **vehicle counts** ("5 vehicles require review"); the raw **17**
and per-vehicle/raw records stay inside "View approval details". Follow-up answers obey the same
rule — "Which vehicles require review?" lists the 5 vehicles, never 17. All 17 raw records remain
unchanged.

---

## 7. Chat UX (`views/assistant_home.py`)

- First submission keeps the Slice-1 path (`run_assistant`) and becomes the **first turn**:
  a user bubble (the question) + an assistant bubble containing the Slice-1 rich answer.
- The thread renders `state.messages` with `st.chat_message`; rich turns (first_turn / rerun)
  re-render via the stored `result`, text turns render markdown. Prior turns are never erased.
- `st.chat_input` drives `handle_followup`; a provenance caption marks each answer
  (from your last analysis / re-ran the analysis / needs more info / not available).
- Suggested follow-ups become **clickable** once a result exists (they submit as follow-ups):
  "Why was the BMW selected?", "Which vehicles have safe promotional room?", "Show only vehicles
  over 90 days", "Use Summer Clearance", "Which vehicles require review?", "Open full evidence
  workspace". The initial suggested questions remain when no conversation exists.
- Workspace continuity: navigation stays `st.page_link`-based; `improve_aging_result` is kept in
  sync with `active_result` so opening the workspace and returning preserves history, active
  result, event, target, referenced vehicles, and ids.

---

## 8. Grounding & safety (hard boundary)

May: read/select/filter/sort existing rows, translate codes, explain warnings/approvals,
reference existing financials and P10/P50/P90, rerun the deterministic workflow with validated
inputs, navigate to the workspace. Must not: compute price/break-even/holding/depreciation/
probability/percentile, average or combine simulations, invent a vehicle/market/shopper/event/
plan, override actions/approvals, or publish a price. Optional LLM phrasing (if ever enabled) is
allow-list-guarded; all tests run and pass with no credentials on the deterministic path. AST
guards assert `conversation.py`/`followup.py` import neither `pricing_agent.domain` nor
`pricing_agent.simulation` and contain no `percentile`/`simulate(`/`np.mean`/publish symbols.

---

## 9. Files

**New:** `agents/conversation.py`, `agents/followup.py`,
`tests/unit/test_conversation_state.py`, `tests/unit/test_followup_classifier.py`,
`tests/unit/test_followup_handlers.py`, `docs/conversational-follow-ups-plan.md`,
`docs/conversational-follow-ups-results.md`.
**Modified:** `agents/assistant.py` (`wrap_improve_aging`), `agents/aging_answer.py`
(explain/filter builders), `agents/__init__.py` (exports), `views/assistant_home.py` (thread +
chat input), `README.md`, `docs/demo-script.md`.
**Not touched:** skills, `workflows/` engine, `candidate_selection`, schemas, `mcp_clients`,
mocks, event fixtures, calculations, price publishing. First-turn routing unchanged; the
follow-up layer is additive.

---

## 10. Test strategy (27 assertions)

History preserves turns; Slice-1 first turn unchanged; explain answers from existing result with
no rerun; filter filters with no rerun; "safe promotional room" / "require review" use existing
codes and vehicle counts; default follow-ups never show 17; 17 preserved in audit; event and
target reruns run; rerun updates active only on success; failed rerun preserves previous; ambiguous
reference asks; "those two" resolves to the most recent pair; unsupported returns unavailable and
invents nothing; no follow-up path calculates or combines simulations; state preserves
workflow/request/simulation ids; selected/excluded ids and final actions unchanged unless a
validated rerun changed a supported input; no price-publishing symbol; existing suite green. Plus
AST guards. Commands: `pytest tests -q`, `scripts/validate_schemas.py`, then the seven smoke
conversations.

## 11. Known limitations

- Reruns cover event, target, and exclusions (the inputs `run_improve_aging` accepts). Plan
  choice and window-extension are not engine parameters → answered from pre-computed plans or
  clarified, never fabricated.
- Deep-analysis is capped at 8 vehicles (existing engine behaviour); references resolve within
  the analysed + excluded set of the active result.
- Follow-up classification is conservative keyword/entity matching; genuinely novel phrasings
  fall to clarification rather than guessing. No LLM phrasing layer is enabled in this slice.
