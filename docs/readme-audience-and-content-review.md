# README audience & content review (documentation-only)

**Branch:** `docs/readme-restructure` (off `main`). No application code, tests, schemas, mocks,
or UI behavior change in this task.

## Why the old README needed restructuring

The previous README was **engineering-first** and, for a first-time reader, buried the product.
Specific problems found by inspection:

| Problem | Detail |
| --- | --- |
| **Stale test count** | Stated "455 tests"; the suite is now **534** (verified this commit). |
| **No business framing** | Opened with "The one architectural claim" and enforcement tables — credible for engineers, opaque for a dealer / PM / interviewer. |
| **Workflows under-explained** | The four dealer workflows appeared only as a code block; no business table, decisions supported, or examples. |
| **Missing conversational capabilities** | Grounded first-turn answers, multi-turn follow-ups, filtering, reruns, and cross-workflow switching were absent or only hinted (some was added later in one dense paragraph). |
| **Contradicted current behavior** | Said "Still not built … LLM-based routing (the deterministic router stands in for it)" and implied Improve Aging was not orchestrating — but routing + orchestration + multi-turn + switching are all implemented and verified end-to-end. |
| **No glossary / output interpretation** | No plain-English definitions of P50/P90, break-even, safe floor, review conditions, etc. |
| **No safety/governance section** | Human-in-the-loop, approval presentation (vehicle count vs raw records), audit IDs were scattered, not consolidated. |
| **No limitations / evolution / disclaimer sections** | Prototype boundaries and non-affiliation were implicit. |
| **Acronyms undefined** | MCP, P50/P90 not defined on first use for non-technical readers. |

## Known code/label inconsistencies (NOT changed here — out of scope)

The workflow registry (`src/pricing_agent/workflows/registry.py`) still marks the **Assistant** and
**Improve Aging Inventory** as `SHELL_ONLY` with "not connected yet" disclaimers, so their cards
show "Status: Shell Only." This is **stale metadata**: both fully execute (verified in the browser
and by 534 tests). The README documents the *actual, verified* behavior. Correcting the registry's
`availability`/`disclaimer` flags is a small code change for a separate task.

## New structure (business-first, 16 sections)

1. What problem does this solve? · 2. What can the tool do? (workflow table) · 3. Quick product
walkthrough (Improve Aging) · 4. How to interpret the outputs (glossary) · 5. What makes this an
AI product? (conversation/orchestration vs deterministic services) · 6. Product architecture
(Mermaid) · 7. Conversation & workflow behavior · 8. Safety, governance, human control · 9.
Prototype data & MCP boundary · 10. Getting started · 11. Example prompts · 12. Testing &
validation · 13. Repository map · 14. Current limitations · 15. Product evolution · 16. Disclaimer.

Business overview leads; technical detail follows. Plain English first; MCP and P50/P90 defined on
first use. Claims verified against current code; commands and paths verified; Mermaid checked.

## Verified facts used

- Entry point: `app.py`; launch `streamlit run app.py` (Streamlit default URL http://localhost:8501).
- `spike_navigation.py` is **untracked / not part of the app** — README warns against it.
- Tests: **534 passed**; schema checks: **62 passed** (this commit). Python ≥ 3.11.
- 3 reusable skills (single-vehicle-valuation, inventory-portfolio-forecast,
  dealer-event-promotion-planner); 4 dealer workflows; Improve Aging orchestrates all three.
- 12-vehicle synthetic dealer; 18 JSON Schemas; mock MCP tools under `mocks/`.
