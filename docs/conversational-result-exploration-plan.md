# Conversational Result Exploration — plan

**Branch:** `feat/conversational-result-exploration` (off merged `main`, which already carries
the count-reconciliation fix from PR #6). Working tree clean at start.

**One-line goal:** turn the Assistant from a single-turn workflow launcher into a grounded,
multi-turn decision assistant that answers directly in the conversation, supports follow-ups
against the same result, and preserves the workspace for deep evidence — **without the LLM ever
producing a number.**

---

## 1. Current gap (reproduced)

For **"Which aging vehicles should I promote?"** (no event, `as_of 2026-07-29`) the Assistant
today shows three metrics and a workspace link:

- Aging vehicles analysed: 7 · 5 need action now · No event
- It does **not** name the seven vehicles, the five immediate-action vehicles, or the two
  no-immediate ones. The dealer must open the workspace to discover the answer.
- The chat card still shows the raw approval-record count ("5 vehicles … (17 review item(s))"),
  putting **17** in the default dealer view.

**Confirmed baseline (source of truth for every count below):**

| | Vehicles |
| --- | --- |
| Analysed (7) | V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001 |
| Immediate action (5) | V-10005 wholesale · V-10012 wholesale · V-10002 manager-review · V-10006 manager-review · V-10004 wholesale |
| No immediate action (2) | V-10008, V-10001 (`NO_ACTION`) |
| Excluded (5) | V-10003, V-10007, V-10009, V-10010, V-10011 |
| Review-condition vehicles | 5 (V-10005/12/02/06/04) |
| Raw approval records | 17 (3,3,4,3,4) |
| `MANAGER_REVIEW` action vehicles | 2 (V-10002, V-10006) |
| Event / target | none / none / `target_status = NO_EVENT` |

These are read live from `run_assistant(...).improve_aging`; nothing is hard-coded into a view.

---

## 2. Desired experience

**Conversation gives the answer; workspace gives the evidence.**

First-turn no-event answer names all seven vehicles, the five immediate actions with a concise
reason each, the two no-immediate (sale-event-candidate) vehicles, a clear "no event ⇒ promotion
eligibility not finalized" statement, suggested follow-ups, and a workspace link — exactly the
structure in the task's "Desired first-turn response". The vehicle list is built from the
structured result, never hard-coded.

Follow-ups continue against the **same active result** (answer / filter), ask for missing inputs
(clarify), or **re-run the same deterministic workflow** with validated new inputs (event,
target, protect/exclude, window). Prior turns are never erased.

---

## 3. Conversation-state model

New deterministic dataclass `ConversationState` (module `agents/conversation.py`), held in
Streamlit `session_state` under one stable non-widget key (`CONVERSATION_KEY`). It stores
**references to existing validated results**, never recomputed numbers.

```
ConversationState
  conversation_id: str
  as_of: datetime
  turns: list[Turn]                     # ordered user/assistant history (never truncated)
  active: ActiveResult | None           # the current grounded result

ActiveResult
  workflow: WorkflowContext             # IMPROVE_AGING_INVENTORY for this phase
  response: AssistantResponse           # the whole response object (carries .improve_aging)
  workflow_id, request_ids, simulation_ids
  vehicle_index: dict[str, VehicleRef]  # vehicle_id -> {description, action, reason_codes,
                                        #   warnings, approvals, price, single-vehicle result}
  selected_event: str | None
  target_utilization: float | None
  recommended_plan: str | None
  warnings, approval_records            # copied straight from the result
  last_clarification: str | None

Turn
  role: "user" | "assistant"
  text: str                             # rendered dealer-facing text
  answer: DirectAnswer | None           # structured payload for assistant turns
  kind: "direct" | "answer" | "filter" | "clarify" | "rerun" | "unsupported" | "error"
  source: "new_result" | "active_result"   # tells the UI where the answer came from
```

Reference resolution ("the BMW", "those two", "the RAV4", "the recommended plan", "the same
event", "the five vehicles") is **deterministic** against `vehicle_index` and the active plan/
event — the LLM is never the sole resolver. On a failed rerun the previous `active` is kept.

---

## 4. Follow-up classification (deterministic, rules-first)

Module `agents/followup.py`, pure functions over `(text, ConversationState)`. Returns a
`FollowupIntent` with a category and resolved entities. Ordered rules (first match wins):

| Cat | Meaning | Trigger examples | Action |
| --- | --- | --- | --- |
| **D** | Workflow rerun | "use Summer Clearance", "change target to 75%", "extend the event", "protect the RAV4", "exclude the BMW" | build a new `ImproveAgingRequest` (reuse `build_improve_aging_request` + state deltas), re-run `run_improve_aging`, replace `active` on success |
| **C** | Clarification | "promote them", "use the event", "make the target lower" (no resolvable event/target/vehicle) | ask for the missing event / target / vehicle / plan / window; set `last_clarification` |
| **B** | Filter active result | "show only vehicles over 90 days", "only wholesale-review vehicles", "only depreciation risk" | filter `vehicle_index` rows; no rerun |
| **A** | Answer from active result | "why is the BMW wholesale?", "which have safe promotional room?", "which two don't need immediate action?", "which require review?" | select/explain from existing fields |
| **E** | Unsupported | shopper-demand, live market, lead-conversion, any new calculation | state the limitation; invent nothing |

Rerun (D) is detected **before** answer (A) so "use Summer Clearance" reruns rather than being
answered from stale state. Clarification (C) fires when a rerun-shaped verb ("promote", "use the
event", "lower the target") appears **without** a resolvable entity. Category is decided by
keyword/entity rules; an optional LLM pass may only *rephrase* the resulting grounded answer
(guarded), never choose numbers or categories in a way tests depend on — tests run with no
credentials and must pass on the deterministic path.

**Filter vocabulary (B)** maps to existing fields only: over-90 (`CURRENTLY_OVER_90_DAYS`,
`CURRENTLY_OVER_120_DAYS`), safe promotional room (`HIGH_SAFE_PROMOTIONAL_HEADROOM`),
depreciation risk (`HIGH_DEPRECIATION_RISK`), inbound pressure (`INBOUND_REPLACEMENT_PRESSURE`),
below break-even (approval `BELOW_PROJECTED_BREAK_EVEN` / warning
`PRICE_BELOW_CURRENT_BREAK_EVEN`), wholesale-review / manager-review (consolidated action),
requires-review (non-empty approvals).

---

## 5. Direct-answer model

New pure builder `agents/aging_answer.py` → `DirectAnswer` dataclass, consumed by the view. All
content derived from the result; the view only renders.

```
DirectAnswer
  understood: str                       # "I analysed 7 aging vehicles."
  analysed_count, immediate_count, no_immediate_count: int
  immediate: list[VehicleLine]          # description, action_label, concise reason
  no_immediate: list[VehicleLine]       # description (+ "sale-event candidate")
  event_selected: bool
  promotion_finalized: bool
  event_block: EventBlock | None        # when an event is active: promoted / not-selected /
                                        #   protected-excluded / target likelihood / approach
  review_vehicle_count: int             # 5 (default dealer-facing)
  manager_review_count: int             # 2 (distinct concept, shown in detail)
  review_item_count: int                # 17 (audit only, never in the default text)
  key_review_note: str                  # "5 vehicles require review before any pricing action."
  suggested_followups: tuple[str, ...]
  workspace_url: str
```

**Concise per-vehicle reason** (`vehicle_reason`) composes the top one–two existing
`reason_codes` (and, only when already present, a warning label) via `improve_aging_copy`
labels — e.g. `CURRENTLY_OVER_120_DAYS` + `INBOUND_REPLACEMENT_PRESSURE` → "over 120 days on lot
and inbound inventory is increasing space pressure." No new fact is introduced.

**No-event wording rules** (enforced by tests): never "all seven should be promoted", "seven
recommended for promotion", "promotion plan completed", or "target likelihood"; always
"analysed / immediate action / no immediate action / potential sale-event candidates /
promotion eligibility pending", and the explicit sentence *"No event is selected, so promotion
eligibility is not finalized."*

**Event-enabled wording** distinguishes analysed vs immediate-action vs event-promotion vs
analysed-not-selected vs protected/excluded, plus target likelihood and recommended approach —
never conflated. Every count reconciles to visible vehicle records.

---

## 6. Grounding rules (hard boundary)

The conversational layer **may** read result fields, select/filter/sort existing rows, translate
reason/warning/approval codes, reference existing financial and P10/P50/P90 values, and re-invoke
the deterministic workflow with changed inputs. It **must not** calculate a price, break-even,
holding cost, depreciation, probability, or percentile; combine or average independent
simulations; invent a vehicle, market value, plan, or likelihood; change a classification;
override a warning or approval; or publish a price. **Every number in chat is copied from an
existing validated result.** The existing `narration_guard` (currency/duration allow-list) gates
any optional LLM prose; without credentials the deterministic template/answer is used.

---

## 7. Approval presentation (critical)

**Default dealer surfaces show unique vehicle-level counts only.** The value **17** (raw review
records) is removed from: the primary Assistant response, the executive summary, the "What
should I do next?" step, and the default Improve Aging workspace view. It moves into a collapsed
**"View approval details"** section.

Changes:
- `views/assistant_home.py`: chat card shows "**5 vehicles** require review before pricing
  changes" — no "(17 review item(s))" in the default line.
- `agents/assistant.py::_improve_aging_summary`: keep `review_vehicle_count` (5),
  `manager_review_count` (add, = 2), `review_item_count` (17) — but the view renders only the
  vehicle count by default; 17 lives in audit.
- `views/improve_aging_copy.py::next_steps`: step 2 becomes vehicle-based ("**5 vehicles**
  require review before any pricing action"), not "17 approval(s) are required".
- `views/improve_aging.py`: recommended-plan card metric shows "Vehicles requiring review: 5"
  with **no** 17 in the default; the "What to review" section's raw 17, per-vehicle breakdown,
  raw records, reason codes, and request/simulation ids move inside a **"View approval details"**
  expander containing: *Vehicles requiring review: 5 · Review conditions triggered: 17 · Review
  conditions by vehicle · Raw approval records · Raw reason codes · request/simulation ids.*

**Manager-review wording** keeps the two concepts distinct everywhere they meet:
- Vehicles with review conditions: **5**
- Vehicles assigned to manager review (final action `MANAGER_REVIEW`): **2**

All 17 raw records are preserved unchanged in `result.approvals_required`; only their *placement*
in the UI changes.

---

## 8. Progressive disclosure & chat UX

`render_assistant_home` becomes a conversation thread:
- Renders `ConversationState.turns` in order with `st.chat_message` (user + assistant bubbles);
  prior turns persist across reruns and workspace round-trips.
- A follow-up input (`st.chat_input`) drives `handle_followup`. Assistant turns show: direct
  answer → vehicle lines → recommended action → short reason → key review note → missing input
  (if any) → suggested follow-ups (clickable) → workspace link.
- Clear per-turn provenance chips: "answered from your last analysis" (A/B), "re-ran the
  analysis with …" (D), "needs more info" (C), "not available in this prototype" (E).
- Workspace navigation stays `st.page_link`-based (Streamlit-safe) so conversation state, active
  result, event, target, and referenced vehicles survive the jump and return.

The workspace remains the home of the full vehicle table, plan comparison, warnings, approvals
detail, methodology, request/simulation ids, and execution trace.

---

## 9. Failure behavior

- **No active result** on a follow-up → explain nothing has been analysed yet; ask to run/select
  a workflow.
- **Ambiguous vehicle reference** → list the matching vehicles and ask which one.
- **Rerun fails** → keep the previous valid `active`, return an error turn naming which updated
  answer is unavailable; never overwrite the good result.
- **Unavailable field** (shopper views, lead conversion, live market) → state the prototype does
  not have that data; do not infer it.

---

## 10. Files

**New**
- `src/pricing_agent/agents/conversation.py` — `ConversationState`, `Turn`, `ActiveResult`, entity/reference resolution.
- `src/pricing_agent/agents/followup.py` — deterministic classifier (A–E) + rerun request builder.
- `src/pricing_agent/agents/aging_answer.py` — `DirectAnswer` + `vehicle_reason` (pure).
- `tests/unit/test_conversation_state.py`, `tests/unit/test_followup_classifier.py`,
  `tests/unit/test_aging_direct_answer.py`, `tests/unit/test_approval_presentation.py`.
- `docs/conversational-result-exploration-plan.md` (this), `docs/conversational-result-exploration-results.md`.

**Modified**
- `src/pricing_agent/agents/assistant.py` — add `manager_review_count`; expose a helper to
  build/refresh `ActiveResult` from a response.
- `src/pricing_agent/agents/__init__.py` — export the new entry points.
- `src/pricing_agent/views/assistant_home.py` — conversation thread; approval default copy.
- `src/pricing_agent/views/improve_aging.py` — "View approval details" progressive disclosure.
- `src/pricing_agent/views/improve_aging_copy.py` — vehicle-based review step.
- `README.md`, `docs/demo-script.md`; `docs/architecture.md` only if the state model is material.

**Not touched:** skills, `workflows/` engine, `candidate_selection`, schemas, `mcp_clients`,
mocks, event fixtures, calculations. Routing is extended only with a follow-up layer; the
first-turn router is unchanged.

---

## 11. Test strategy

The 28 required assertions map to four new test files plus the existing suite:

- **Direct answer** (1–5): names all 7; lists 5 immediate; identifies 2 no-immediate; never
  implies all 7 promoted; states promotion pending without an event.
- **Follow-ups** (6–12): explain a vehicle (A, no rerun); filter rows (B, no rerun); event and
  target trigger reruns (D); answers use only active-result fields; no follow-up path imports the
  calculation layer or calls a percentile/simulate; independent simulations never combined.
- **State & robustness** (13–16): state preserves workflow_id/request_ids/simulation_ids;
  ambiguous reference asks; missing data not invented; prior result survives a failed rerun.
- **Approval presentation** (17–22): default Assistant and workspace show only the vehicle count;
  "17 approvals required" never in default surfaces; 17 available in "View approval details"; 17
  raw records unchanged; 5-affected vs 2-`MANAGER_REVIEW` distinction accurate.
- **Invariants** (23–28): candidate selection, final actions, selected/excluded ids, numerical
  outputs unchanged; no price-publishing symbol introduced; existing tests green.

Plus AST guards (mirroring `test_improve_aging_view`/`test_terminology`): the conversational
modules import neither `pricing_agent.domain` nor `pricing_agent.simulation`, and contain no
`percentile` / `simulate(` / `np.mean` / publish symbols.

Commands: `python -m pytest tests -q` and `python scripts/validate_schemas.py`. Then the six
smoke conversations (no-event, vehicle-explanation, filter, event, approval-details, missing-data)
in the browser.

---

## 12. Safety boundaries (restated)

No LLM-produced numbers; deterministic entity matching; no calculation, no simulation combining,
no fabrication, no classification/warning/approval override, no price publishing, no Market Days
Supply. Optional LLM prose is allow-list-guarded and fully degrades to deterministic text.

## 13. Known limitations (to document in results)

- Reruns are limited to inputs the existing workflow accepts (event, target, exclusions);
  window-extension follow-ups map to the promotion planner's existing window handling only if a
  parameter exists, otherwise they are treated as clarification/unsupported and say so.
- Follow-up classification is keyword/entity deterministic — deliberately conservative; genuinely
  novel phrasings fall to clarification rather than guessing.
- The conversational layer covers the Improve Aging result in depth; other workflows keep their
  existing single-turn summaries this phase.
