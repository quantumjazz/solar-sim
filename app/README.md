# app — Streamlit front ends

Two ways to run the solar-sim business simulation, both built on the same
engine (`../sim-engine/`) and the shared `forms.py` / `views.py` helpers.

## Multi-user app — `app.py`

A single Streamlit app with per-student logins over a shared SQLite
database, role-gated at login:

- **Instructors** create a cohort (scenario + named teams), assign
  registered students to teams, watch a submission dashboard, advance
  periods, and review every team's reports.
- **Students** log in, read the period briefing, enter and submit their
  team's decision (sales, R&D, purchasing, production, HR, finance), and
  review their team's reports plus the public industry report.

Each period a team's decision starts as a **draft**; **submitting** it
validates and locks it. The instructor advances the period once all teams
have submitted (an override can run with current drafts). State is shared,
so the instructor and every student see the same cohort.

```bash
pip install streamlit pydantic pyyaml
streamlit run app/app.py
```

The cohort database is `solar-sim.db` at the repository root; set the
`SOLAR_SIM_DB` environment variable to put it elsewhere. There is no hosted
deployment — the instructor runs the app and students connect over the
local network. Register the first instructor account from the login screen.

Four modules sit under `app.py`:

| Module | Responsibility |
| --- | --- |
| `db.py` | SQLite schema and CRUD — the only module that touches SQLite. |
| `auth.py` | PBKDF2 password hashing (stdlib), register / login. |
| `service.py` | `GameService` — bridges the database to the engine: create a cohort, save / submit decisions, run a period, fetch reports, score planning quality, store / load the strategy map. |
| `pedagogy.py` | Planning-quality scoring (sMAPE) and the `StrategyMap` model — pure, no DB / Streamlit dependency. See `docs/spec/09-pedagogy.md`. |

The multi-user app also surfaces the **pedagogy layer**: students get a
**Planning quality** tab (period-by-period plan-vs-actual scoring across
three KPIs — revenue, ROE, operating cash flow) and a **Strategy** tab
(freeform Markdown balanced-scorecard authoring across the four classical
perspectives). Instructors get a cohort planning-quality dashboard and a
read-only per-team strategy-map viewer.

## Instructor console — `instructor_console.py`

A single-operator tool: one person loads a scenario, enters every team's
decisions, runs the period, and reviews reports. Cohort state lives in the
Streamlit session and is saved to / loaded from a JSON file. No database,
no login — the quickest way to run a cohort solo.

```bash
streamlit run app/instructor_console.py
```

## Files

```
app/
├── app.py                  multi-user app (entry point)
├── db.py                   SQLite schema + CRUD
├── auth.py                 accounts: hashing, register, login
├── service.py              database-to-engine bridge (GameService)
├── pedagogy.py             planning-quality scoring + StrategyMap model (pure)
├── instructor_console.py   single-operator console (entry point)
├── forms.py                decision-entry form builders (shared)
├── views.py                report-rendering helpers (shared)
├── test_app.py             AppTest smoke test for the console
├── test_phase3.py          db / auth / service / pedagogy + AppTest tests
└── README.md               this file
```

Both entry points add `sim-engine/src` to `sys.path`, so the engine need
not be installed for local use.

## Testing

From the repository root (`solar-sim/`):

```bash
PYTHONPATH=sim-engine/src:app python3 -m pytest app/
```

`test_app.py` (4 tests) drives the console headlessly with Streamlit's
`AppTest`. `test_phase3.py` (33 tests) covers the database, accounts, the
game service, and the pedagogy scoring directly, plus `AppTest` smoke
tests of `app.py` — including an end-to-end student submission, an
instructor period run, and a student saving a strategy map.

## Known limitations (multi-user app)

A logged-in session lives in Streamlit `session_state`, so a hard browser
refresh requires logging in again. There are no real-time updates (refresh
to see others' progress), and two members of one team editing the same
draft is last-write-wins. See `../docs/current-task.md`.
