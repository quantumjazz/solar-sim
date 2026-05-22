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

Three modules sit under `app.py`:

| Module | Responsibility |
| --- | --- |
| `db.py` | SQLite schema and CRUD — the only module that touches SQLite. |
| `auth.py` | PBKDF2 password hashing (stdlib), register / login. |
| `service.py` | `GameService` — bridges the database to the engine: create a cohort, save / submit decisions, run a period, fetch reports. |

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
├── instructor_console.py   single-operator console (entry point)
├── forms.py                decision-entry form builders (shared)
├── views.py                report-rendering helpers (shared)
├── test_app.py             AppTest smoke test for the console
├── test_phase3.py          db / auth / service + AppTest tests for app.py
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
`AppTest`. `test_phase3.py` (22 tests) covers the database, accounts, and
the game service directly, plus `AppTest` smoke tests of `app.py` —
including an end-to-end student submission and an instructor period run.

## Known limitations (multi-user app)

A logged-in session lives in Streamlit `session_state`, so a hard browser
refresh requires logging in again. There are no real-time updates (refresh
to see others' progress), and two members of one team editing the same
draft is last-write-wins. See `../docs/current-task.md`.
