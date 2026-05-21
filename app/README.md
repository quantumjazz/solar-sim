# app — Instructor Console

A Streamlit app for running a cohort of the solar-sim business simulation.

## What it does

One screen per period. The instructor:

1. **Sets up a cohort** — picks a scenario pack and names the teams.
2. **Enters decisions** — one expandable form per team (sales, R&D,
   purchasing, production, HR, finance), pre-filled from the team's previous
   period.
3. **Runs the period** — decisions are validated first; invalid ones are
   shown inline and block the run.
4. **Reviews reports** — per-team executive summary, market, P&L, balance
   sheet and cash flow, plus the cohort-wide industry report.

Cohort state lives in the Streamlit session. There is no database or login:
a game can be saved to / loaded from a JSON file via the sidebar. This
matches how the reference course ran — teams submit decision forms, the
instructor runs them centrally.

## Running it

From the repository root (`solar-sim/`):

```bash
pip install streamlit
pip install -e sim-engine          # or rely on the app's sys.path shim
streamlit run app/instructor_console.py
```

The app adds `sim-engine/src` to `sys.path` itself, so installing the engine
is optional for local use.

## Files

```
app/
├── instructor_console.py   the Streamlit app (entry point)
├── forms.py                decision-entry form builders
├── views.py                report-rendering helpers
├── test_app.py             AppTest smoke test (headless)
└── README.md               this file
```

## Testing

The app has a headless smoke test using Streamlit's `AppTest` harness:

```bash
PYTHONPATH=sim-engine/src:app python3 -m pytest app/test_app.py
```

It exercises the full flow — initial screen, cohort setup, running a period,
and rendering reports — without a browser.

## Scope (this iteration)

This is the **instructor console**: a single operator drives the whole
cohort. A student-facing app with per-team logins, decision submission and a
shared database is a later phase.
