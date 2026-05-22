# Architecture

How solar-sim is put together. For mechanics (formulas, parameters) see
`docs/spec/`; for why the structure is what it is see `docs/decisions.md`.

## Three components

```
   scenarios/solar-v1/         sim-engine/              app/
   (data: YAML + Markdown)  →  (pure functions)     ←  (Streamlit UI)
```

- **`sim-engine/`** — the simulation. A pure-Python package, `sim_engine`.
  No I/O, no UI, deterministic. It is the only component with rules in it.
- **`scenarios/`** — data, not code. A scenario pack is YAML (starting
  state + per-period events) plus Markdown narrative briefings. The engine
  is industry-agnostic; `solar-v1` is the solar-PV scenario.
- **`app/`** — a Streamlit instructor console that drives the engine.

Dependency direction is strict: `app` imports `sim_engine`; `sim_engine`
never imports `app`; scenarios are inert data loaded by the engine. This
keeps the engine reusable (it could later drive a different UI or an
export) and keeps it testable without a UI.

## The engine package

| Module | Responsibility |
| --- | --- |
| `scenario.py` | Load a scenario pack from disk; scenario-side Pydantic models (`ProductSpec`, `MarketSpec`, `WorldDefaults`, `PeriodEvent`, `LoadedScenarioPack`, …). |
| `state.py` | Runtime state models: `PeriodState` (the canonical snapshot), `CompanyState`, `ProductState`, `ProductionLineState`, `CostCentreState`, `InventoryRecord`, `LoanState`. |
| `decisions.py` | `TeamDecision` and its nested decision models — one team's choices for one period. |
| `reports.py` | Output models: `ReportBundle` (per team) with `ExecutiveSummary`, `MarketReport`, `ProfitLossStatement`, `BalanceSheetReport`, `CashFlowStatement`, plus the cohort-public `IndustryReport`. |
| `context.py` | `resolve_period_context()` — folds a period's events onto the base world to produce a `ResolvedPeriodContext` (effective wages, prices, market potentials, FX, offers, caps). |
| `validation.py` | `validate_decision()` — rejects hard-invalid decisions; `InvalidDecisionError`. |
| `engine.py` | `run_period()` orchestrator, `build_initial_state()`, and every rule sub-module (R&D, HR, production, sales settlement, accounting, articulation). |

## Public API

```python
from sim_engine import (
    load_scenario_pack,    # (path) -> LoadedScenarioPack
    build_initial_state,   # (pack, cohort_id=, company_ids=) -> PeriodState
    run_period,            # (state, decisions, pack) -> (PeriodState, reports)
    validate_decision,     # (decision, company, ctx) -> list[str]  ([] == valid)
    InvalidDecisionError,
)
```

`run_period` takes the current `PeriodState`, a `dict[team_id -> TeamDecision]`,
and the scenario pack; it returns the next `PeriodState` and a
`dict[team_id -> ReportBundle]`. It is a pure function — same inputs, same
outputs — and validates every decision first, raising `InvalidDecisionError`
if any team's decision is invalid (it never silently clamps).

## The period loop

`run_period` advances the cohort by one period in three phases:

1. **Pre-market (per company).** Materialise newly available products,
   apply scenario notable events, then R&D, HR, production-line
   invest/disinvest, capacity laddering, material purchasing, and
   production. Finished-goods inventory is updated; nothing is sold yet.

2. **Market settlement (across the cohort).** Tenders settle first (lowest
   valid bid wins), then bulk-buyer offers, then retail in each open market
   via a multinomial attraction model — each market's demand is split
   across companies in proportion to attractiveness and capped by available
   inventory, with one round of under-supply spillover. A `committed`
   ledger ensures the priority channels and retail never oversell.

3. **Post-market (per company).** Deduct sales from inventory, compute cost
   of goods sold, overhead, depreciation, interest and tax, then produce
   the profit & loss, balance sheet, and cash-flow statements. Finally the
   `IndustryReport` is built from all teams' reports and attached to each
   bundle.

## Invariants

- **Articulation.** Every period: profit & loss → balance sheet → cash
  flow reconcile (assets = liabilities + equity; the cash-flow statement
  ties opening to closing cash). The report models carry an `articulates`
  flag; tests assert it.
- **Determinism.** `run_period` has no hidden state; re-running a period
  with the same inputs yields identical output.
- **Purity.** The engine performs no I/O. Loading happens once via
  `load_scenario_pack`; everything else is in-memory model transformation.

## The front ends

`app/` holds two Streamlit front ends, both built on the same engine and the
shared `forms.py` (decision-entry forms) and `views.py` (report rendering).
Each adds `sim-engine/src` to `sys.path` so the engine need not be installed
for local use.

**Instructor console** (`instructor_console.py`) — a single operator drives
the whole cohort: load a scenario, enter every team's decisions, run the
period, review reports. Cohort state lives in the Streamlit session and is
saved to / loaded from a JSON file. No database, no login.

**Multi-user app** (`app.py`) — per-student logins over a shared SQLite
database, so each team enters its own decisions. One Streamlit app,
role-gated at login:

- *Instructors* create cohorts, assign students to teams, watch the
  submission dashboard, advance periods, and review every team's reports.
- *Students* see the period briefing, fill and submit their team's
  decision, and review their own reports plus the public industry report.

Three modules sit under `app.py`:

| Module | Responsibility |
| --- | --- |
| `db.py` | SQLite schema and CRUD. One connection per operation; WAL mode. The only module that touches SQLite. |
| `auth.py` | PBKDF2 password hashing (stdlib), `register_user`, `authenticate`. |
| `service.py` | `GameService` — the bridge between `db.py` and the engine: create a cohort (`build_initial_state`), save / submit decisions, `run_next_period` (`run_period`), persist state and reports. The UI never imports the engine directly. |

Engine models cross the database boundary as JSON (`model_dump_json` /
`model_validate_json`). The period history is append-only: every
`PeriodState` is kept, so a cohort is fully replayable.

### Data model

`users` · `cohorts` · `teams` · `team_members` · `period_states`
(append-only) · `decisions` (one draft / submitted row per cohort × team ×
period) · `reports` (one `ReportBundle` per cohort × team × period — the
industry report is embedded in each bundle). See `app/db.py` for the schema.

### Decision flow

Each period, a team's decision starts as a **draft** — seeded for period 1
from a sensible default, and for later periods carried forward from the
team's prior decision. Team members edit the draft; **submitting** validates
it and locks it. The instructor advances the period once every team has
submitted (or with an explicit override that uses current drafts).
`run_period` validates all decisions again and either advances the cohort or
rejects the period.

## Scenario pack layout

```
scenarios/solar-v1/
  scenario.yaml         period-0 starting state, products, markets, world defaults
  period-events.yaml    per-period economy, parameter/market changes, offers, events
  narrative/            period-1..9.md — the briefing shown to teams each period
```

The full pack schema is specified in `docs/spec/07-scenario-format.md`.
