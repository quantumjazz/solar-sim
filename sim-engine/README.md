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
- **Sales channels.** Finished goods are allocated in priority order:
  won tenders (lowest valid bid wins) → bulk buyers → domestic retail →
  export retail. A `committed` ledger keeps retail from overselling.
- **Two markets.** `market_1` (domestic, base currency) and `market_2`
  (export) — export revenue is FX-converted to base currency.
- **Production lines.** Investment (lines bought from the catalog, available
  the same period) and disinvestment (residual revenue + book-value
  write-off as extraordinary items).
- **HR productivity.** Productivity Index I = competence × process
  optimisation × adaptation × motivation; Productivity Index II is the
  per-product learning curve. Training, process-optimisation spend, hiring
  waves and pay all move the indices. Purchasing and administration
  headcount auto-scale to revenue.
- **Period-event application.** `period-events.yaml` overrides — wages, tax
  rate, interest rates, factory-material cost, input-material price changes,
  market potentials, transport costs — all flow through via a resolved
  per-period context.
- **Three-phase period loop.** Pre-market (per company) → market settlement
  (across cohort) → post-market (per company).

### v0.3 — successor products (current)

- **Successor products.** `panel_gen2`, `storage_box`, and `balcony_solar`
  materialise into company state at their `available_from_period` (seeded
  with pre-launch indices), can be developed via R&D before launch, and
  become producible / sellable from their `launchable_from_period`.
- **Generation handover (coexistence model).** A successor and the product
  it `replaces` coexist as separate products; the scenario ramps the old
  generation's market down and the successor's up. No forced inventory
  scrapping — see `docs/spec/02-rnd.md` §5.
- **Launch gating.** Producing or selling a product before its launch
  period is rejected by decision validation.

Still simplified (explicit `TODO` markers in code):

- **Tender delivery lag** — won tenders deliver in the current period rather
  than honouring `delivery_period`.
- **Scenario `notable_events`** — typed events such as a one-off expense or
  an environmental-index step are carried in the context but not yet applied.
- **Overtime, environmental tech, the category-level price-elasticity of
  total market size, slow image/satisfaction dynamics, an explicit
  bad-launch penalty.**

> **Calibration note.** The `solar-v1` market potentials are sized for a
> full cohort at scale. With a small cohort or early in the game, market_1
> demand exceeds total cohort capacity, so the export market is hard to
> reach until teams have invested in production lines. Tuning is a Phase 6
> task and does not affect engine correctness.

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
