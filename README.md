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

Three pages: the **lot** (inventory, risk, 30/90-day forecast), **vehicle detail**
(recommendation, strategies, floor, discount ladder, audit), and the **promotion planner**.

An `ANTHROPIC_API_KEY` is optional. Without one, natural-language intake falls back to a
recorded extraction and narration falls back to a deterministic template assembled from
the computed values — so it degrades rather than breaking, and the UI says which is in
use.

### Tests

```bash
python -m pytest tests -q            # 85 tests
python scripts/validate_schemas.py   # 62 checks: schemas, refs, fixtures, scenarios
```

`scripts/validate_structure.ps1` runs the subset that needs no Python.

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
