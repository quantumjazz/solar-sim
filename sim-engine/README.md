# sim-engine

The Python simulation engine for the solar-sim project.
Domain-free; all industry knowledge lives in scenario packs (`../scenarios/`).

## What this package does

- Loads a scenario pack from YAML
- Runs one period at a time: `(state, decisions) → (new_state, reports)`
- Emits structured report objects (P&L, balance sheet, cash flow, etc.)

It does **not** know about solar panels, copiers, or e-bikes. That is by design.

## Version status

### v0.2 — multi-team competitive play (current)

Working:

- **Multi-team cohorts.** Any number of companies compete in one cohort.
- **Full multinomial attraction model.** Each (product, market) demand is
  allocated across competing teams in proportion to their attractiveness
  score (price, advertising, sales force, product indices, image,
  satisfaction). Under-supply spillover is redistributed once.
- **Period-event application.** `period-events.yaml` overrides — wages, tax
  rate, interest rates, factory-material cost, input-material price changes,
  market potentials, transport costs — all flow through via a resolved
  per-period context.
- **Three-phase period loop.** Pre-market (per company) → market settlement
  (across cohort) → post-market (per company).

Still simplified (explicit `TODO(v0.2.x)` markers in code):

- **Bulk buyer / tender channels** — sales is retail market-1 only.
- **Multi-market** — `market_2` (export, FX) not yet wired into settlement.
- **Multi-product capacity allocation** — production wired for one product.
- **Productivity Index I / II** — cumulative units tracked; the
  motivation × competence × adaptation × process factor is a placeholder.
- **Auto-scaled purchasing/admin headcount.**
- **Successor-product launch, environmental tech, slow image/satisfaction
  dynamics.**

### v0.1 — MVP (superseded)

Single-company vertical slice. Correct end-to-end articulation.

## Invariants the engine always holds

- Full P&L → balance sheet → cash flow articulation (identities 1–3 of
  `docs/spec/06-accounting.md` §9 are tested).
- Deterministic and replayable: same scenario + same decisions → same outputs.
- Pydantic-typed end to end.

## Running the tests

From this directory:

```bash
pip install -e .[test]
pytest
```

Or without installing, set `PYTHONPATH`:

```bash
PYTHONPATH=src python -m pytest
```

## Package layout

```
src/sim_engine/
├── __init__.py        public surface: run_period, load_scenario_pack, ...
├── scenario.py        scenario pack models and loader
├── context.py         ResolvedPeriodContext — per-period overrides merged in
├── state.py           period state and company state models
├── decisions.py       team decision schema
├── reports.py         report bundle schema
└── engine.py          orchestrator (3-phase loop) + rule modules

tests/
└── test_run_period.py end-to-end tests: articulation, multi-team, events
```
