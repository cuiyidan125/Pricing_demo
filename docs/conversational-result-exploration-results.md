# Conversational Result Exploration — results (slice 1 of 2)

**Branch:** `feat/conversational-result-exploration` (off merged `main`). Not committed.

This phase was staged. **Slice 1 (this delivery)** lands the highest-value part: the grounded
first-turn **direct answer** (the Assistant names the actual vehicles in the conversation) and
the **approval progressive-disclosure** (the raw 17 moves into "View approval details"). **Slice
2 (deferred)** is the multi-turn follow-up engine — conversation state, the A–E classifier, and
workflow reruns — described in the plan and scoped in *Known limitations* below.

Result: **PASS** for the slice-1 scope.

---

## 1. Before / after — first-turn response ("Which aging vehicles should I promote?", no event)

**Before:** three metrics (7 analysed · 5 need action now · No event), a workspace link, and a
chat line reading "5 vehicle(s) need a manager review (**17** review item(s))". The dealer had
to open the workspace to learn *which* vehicles.

**After (verified in the browser):**

> ✅ Improve Aging Inventory — Diagnosed the lot and selected 7 aging candidate(s)…
>
> **I analysed 7 vehicles.**
>
> **5 need immediate action:**
> - **2018 BMW 540i BASE** — Wholesale / loss-minimization review · *already over 90 days on lot and expected to exceed 90 days before sale*
> - **2019 Jeep Wrangler SPORT** — Wholesale / loss-minimization review · *already over 120 days on lot and expected to exceed 90 days before sale*
> - **2021 Honda Accord EX** — Manager review before repricing · *expected to exceed 90 days before sale and room for a safer promotional adjustment*
> - **2023 Chevrolet Bolt EUV LT** — Manager review before repricing · *expected to exceed 90 days before sale and high risk of further value loss*
> - **2019 Nissan Altima SV** — Wholesale / loss-minimization review · *already over 90 days on lot and expected to exceed 90 days before sale*
>
> **2 do not need immediate action but may be sale-event candidates:**
> - 2021 Subaru Outback PREMIUM
> - 2022 Toyota RAV4 XLE
>
> 🗓️ No event is selected, so promotion eligibility is not finalized.
> 🔍 5 vehicles require review before any pricing action.
>
> *You could ask next:* Why is the BMW recommended for wholesale? · Which vehicles have safe promotional room? · Show only vehicles over 90 days · Use Summer Clearance · Open the full evidence workspace
>
> → Open the full Improve Aging workspace

The vehicle list is built from `consolidated_actions` / `vehicle_evidence`; nothing is
hard-coded. Each reason is the dealer label of the top one–two existing `reason_codes`.

## 2. Approval presentation — before / after

| Surface | Before | After |
| --- | --- | --- |
| Assistant chat line | "5 vehicles … (**17** review item(s))" | "🔍 **5 vehicles** require review before any pricing action." |
| Workspace "What should I do next?" | "**17** approval(s) are required…" | "**5** vehicle(s) have review conditions to clear…" |
| Workspace recommended-plan card | "Vehicles needing a manager review 5 / **17** review item(s)" | "Vehicles requiring review **5**" |
| Workspace review section | "5 vehicles … carrying **17** … item(s)" | "**5** require review — **2** assigned to manager review…" + **View approval details** |
| Raw **17** | in default views | only inside **"View approval details"** (Assistant + workspace) |

Browser-verified: with the expander **collapsed**, the string "17" appears nowhere in the
rendered page; **expanded**, "View approval details" shows *Vehicles requiring review: 5 ·
Vehicles assigned to manager review: 2 · Review conditions triggered: 17*.

- **Default review vehicle count:** 5
- **Hidden raw review-item count:** 17 (audit only)
- **5 affected vehicles vs 2 `MANAGER_REVIEW` vehicles:** preserved as distinct concepts
  (`review_vehicle_count` = 5, `manager_review_count` = 2 in the summary and `DirectAnswer`).

## 3. Grounding proof (invariants)

- **Selected IDs (before = after):** V-10005, V-10012, V-10002, V-10006, V-10004, V-10008, V-10001.
- **Excluded IDs (before = after):** V-10003, V-10007, V-10009, V-10010, V-10011.
- **Final actions (before = after):** V-10008/V-10001 `NO_ACTION`; V-10002/V-10006 `MANAGER_REVIEW`;
  V-10005/V-10012/V-10004 `WHOLESALE_OR_LOSS_MINIMIZATION_REVIEW`.
- **All 17 raw approval records unchanged:** 17 records, per-vehicle {V-10005:3, V-10012:3,
  V-10002:4, V-10006:3, V-10004:4}, reason types {LOSS_MINIMIZATION, BELOW_PROJECTED_BREAK_EVEN,
  NEGATIVE_VALUE_RISK, AGGRESSIVE_ADJUSTMENT}.
- **Numerical baseline unchanged** (spot: V-10001 list 28,995 · break-even preserved; portfolio
  86% used; probability 0.4305 with event) — the conversational layer copies, never computes.
- **AST guard:** `agents/aging_answer.py` imports neither `pricing_agent.domain` nor
  `pricing_agent.simulation`, and contains no `percentile` / `simulate(` / `np.mean` / price-
  publishing symbol.

## 4. Files

**New**
- `src/pricing_agent/agents/aging_answer.py` — `DirectAnswer`, `VehicleLine`, `EventBlock`,
  `build_aging_answer`, `vehicle_reason` (pure; view-copy imported lazily to avoid a cycle).
- `tests/unit/test_aging_direct_answer.py` (13 tests) — the direct answer.
- `tests/unit/test_approval_presentation.py` (9 tests) — the approval rule.
- `docs/conversational-result-exploration-plan.md`, `docs/conversational-result-exploration-results.md`.

**Modified**
- `src/pricing_agent/agents/assistant.py` — add `manager_review_count` to the summary.
- `src/pricing_agent/agents/__init__.py` — export `build_aging_answer`, `DirectAnswer`, `VehicleLine`.
- `src/pricing_agent/views/assistant_home.py` — render the direct answer; "View approval details".
- `src/pricing_agent/views/improve_aging.py` — vehicle-based review metric; "View approval details".
- `src/pricing_agent/views/improve_aging_copy.py` — vehicle-based review step.

**Not touched:** skills, `workflows/` engine, `candidate_selection`, schemas, `mcp_clients`,
mocks, event fixtures, calculations, routing, price publishing.

## 5. Tests / checks

- `python -m pytest tests -q` → **482 passed** (460 prior + 22 new).
- `python scripts/validate_schemas.py` → **62 checks passed**.
- Smoke reviewed (no-event direct answer; approval progressive disclosure collapsed/expanded).
  No application console errors; server logs clean (the `/_stcore/health` console lines are
  preview-harness polling, not app errors).

## 6. Requirement coverage in this slice

Delivered: direct-answer requirements 1–7, 9–11 (understood, counts, names, actions, reasons,
review requirement, promotion-finalized state, next questions, workspace link); no-event wording
rules; event-enabled distinctions; approval-presentation rules 17–22; invariants 23–28.

## 7. Known limitations / deferred to slice 2

- **Follow-up engine deferred.** Suggested follow-ups render as copyable prompts, not yet wired
  to an in-conversation follow-up handler. The A–E classifier, deterministic entity matching
  ("the BMW", "those two"), result filtering without rerun, and validated workflow reruns
  (event/target/protect/exclude) are specified in the plan and are the next pass. Test
  assertions 6–8 and 13–16 land with that slice.
- **Conversation state / multi-turn thread deferred.** This slice keeps the existing single
  active-response model; `render_assistant_home` shows one grounded answer at a time.
- The optional LLM phrasing layer is not enabled; all conversational text is deterministic and
  passes with no API credentials.

## 8. Exact next recommended step

Review this slice; if approved, **commit** it (no auto-commit was performed), then start slice 2:
`agents/conversation.py` (state) + `agents/followup.py` (A–E classifier, entity matching, rerun
builder), wire `st.chat_input` follow-ups into `assistant_home`, and add the deferred tests
(6–8, 13–16) plus the six smoke conversations.
