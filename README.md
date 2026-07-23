# Used Vehicle Pricing and Inventory Optimization Agent

A prototype decision-support tool for used-vehicle dealership inventory managers. It
recommends a list price for a vehicle, forecasts what the whole lot will do over 30 and 90
days, and plans discounting for a sale event — showing its reasoning and refusing to
publish a price that breaks a floor.

**Everything here runs on synthetic data.** No live integration, no real market feed.

---

## The one architectural claim

> The LLM orchestrates. A deterministic engine decides.

The model reads a request into validated JSON and explains a finished result. It never
produces a price, a forecast, a cost, or a probability. That is enforced in two places
rather than asserted in a comment:

| Boundary | Mechanism | Test |
| --- | --- | --- |
| A number cannot *originate* in a model | `domain/` and `simulation/` may not import an LLM SDK, an MCP client, or the network | `tests/unit/test_architecture.py` walks the AST of all 14 calculation modules |
| A number cannot *appear* in prose | Every figure in generated narrative must match `explanation_inputs`; unmatched output is discarded | `tests/unit/test_narration_guard.py` |

The second is worth seeing work: feed the guard *"I'd price this around $26,400, which
should move it in about 45 days"* and it rejects all three figures, because the engine
never produced them.

---

## Running it

Requires Python 3.11+.

```bash
pip install -r requirements.txt
pip install -e .

streamlit run app.py           # http://localhost:8501
```

The application opens on **Ask the Dealer AI Assistant** and is organised by the dealer's
job, not by the tool's internals — see [How it is organised](#how-it-is-organised) below.

An `ANTHROPIC_API_KEY` is optional. Without one, natural-language intake falls back to a
recorded extraction and narration falls back to a deterministic template assembled from
the computed values — so it degrades rather than breaking, and the UI says which is in
use.

### Tests

```bash
python -m pytest tests -q            # 387 tests
python scripts/validate_schemas.py   # 62 checks: schemas, refs, fixtures, scenarios
```

`scripts/validate_structure.ps1` runs the subset that needs no Python.

---

## How it is organised

Five words, used consistently:

| Term | What it means here |
| --- | --- |
| **Agent** | The entry point that reads a request in the dealer's words. It orchestrates; it never computes. |
| **Workflow** | A job a dealer actually has — *acquire*, *price*, *merchandise*, *improve aging*. This is what the navigation is made of. |
| **Skill** | A reusable capability a workflow calls. There are three, and none of them is a menu item. |
| **MCP tool** | A read adapter over a system of record (vAuto, DMS, dealer costs), plus one isolated write client. |
| **Dashboard** | A view that renders a finished result. Views never calculate. |

Navigation is declared as data in `src/pricing_agent/workflows/registry.py`, so the sidebar
and the product's vocabulary cannot drift apart:

```
Dealer AI Assistant
  Ask the Assistant            ← default entry point
Dealer Workflows
  Acquire Inventory            capacity, gaps, open slots, replacement pressure
  Price Inventory              value one vehicle: market, gross vs turn, floor
  Merchandise Inventory        plan a sale event: who to discount, and whether the target is reachable
  Improve Aging Inventory      coordinates all three skills against aged units
```

### The assistant routes and executes — deterministically

Ask a question in plain words and the assistant classifies it, resolves the named vehicle
against real inventory, runs **one** skill, and shows a concise result with a link into the
full workspace. **No model is involved** — routing, entity extraction, and vehicle
resolution are rules over strings (`src/pricing_agent/agents/`), and every number shown is
copied from the skill result, never generated.

```
"What should I price 2020 Ford F-150 XLT?"   → resolves V-10003 → single-vehicle valuation → result
"What will my inventory look like in 30 days?" → inventory portfolio forecast → result
"Plan the Summer Clearance event to reach 70%" → dealer event promotion planner → result
"Reduce inventory utilization to 70% during Summer Clearance" → Improve Aging orchestration → plan
```

It answers with one of six honest states: routed-and-executed, needs-clarification (which
vehicle?), no-match (not in inventory — it will not invent one), ambiguous-match (pick from
the candidates), workflow-not-yet-available (Improve Aging orchestration), or
execution-error. See `docs/deterministic-agent-routing-results.md`.

**Improve Aging Inventory** is the orchestration that proves the architecture: it is **not a
fourth skill** but a workflow that runs the three skills in order — portfolio forecast →
candidate selection → single-vehicle valuation for the aged cohort → promotion plan when a
real event is named → one consolidated action plan. It adds no arithmetic of its own, and it
keeps each skill's simulation separate: percentiles from different simulations are shown side
by side, never summed. See `docs/improve-aging-orchestration-results.md`.

**Still not built, and the UI says so:** LLM-based routing (the deterministic router stands
in for it).

---

## Layout

```
docs/       specification, architecture, MCP contract, methodology, policy, open questions
schemas/    18 JSON Schemas (draft 2020-12)
config/     every prototype assumption, versioned — no constant is hard-coded in the code
mocks/      12-vehicle synthetic dealer across all 9 vAuto tools plus internal systems
skills/     the three agent skill definitions
src/pricing_agent/
    config/       assumption loader
    mcp_clients/  read adapters, plus an isolated write client
    simulation/   seeded Monte Carlo producing the draw matrix
    domain/       all financial calculation, pure
    policy/       warnings, floors, approvals, freshness — runs last, adds only
    skills/       orchestration
    agents/, llm/ intake and explanation
    workflows/    the dealer-workflow registry, plus the Improve Aging orchestration
                  (candidate_selection + improve_aging) that coordinates the three skills
    agents/       deterministic router, vehicle resolver, and assistant orchestrator
    views/        Streamlit render functions, bound to a workflow by the registry
tests/      unit, schema, integration, plus 37 scenario definitions
```

---

## Things worth knowing before trusting a number

- **Forecasts are a configured simulation, not a trained model.** Every output carries the
  label `CONFIGURABLE_PROTOTYPE_SIMULATION`.
- **The most consequential assumption is price elasticity** — it alone decides every
  velocity-versus-gross tradeoff, and it is not calibrated. It lives in
  `config/assumptions/simulation.yaml` with the reasoning attached.
- **Comparables are asking prices, not sold prices**, so the market read is biased upward.
  Decile trimming dampens it; nothing removes it.
- **The portfolio forecast is a run-off**: no tool supplies planned acquisitions, so
  ending inventory and revenue are lower bounds.
- **Two of the four inputs to the price floor have no data source** in the specification.
  They are read from config here. See `docs/open-questions.md` section C.

`docs/open-questions.md` is the honest list: six specification ambiguities that were
settled and why, five deviations, and everything still unresolved.
