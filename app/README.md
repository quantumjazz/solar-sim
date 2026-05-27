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
pip install streamlit pydantic pyyaml extra-streamlit-components
streamlit run app/app.py
```

The cohort database is `solar-sim.db` at the repository root; set the
`SOLAR_SIM_DB` environment variable to put it elsewhere. There is no hosted
deployment — the instructor runs the app and students connect over the
local network. Register the first instructor account from the login screen.

Logged-in sessions persist across browser refreshes via an HTTP cookie
backed by a server-side `sessions` table (7-day expiry). The instructor's
**Run period** tab auto-refreshes its submission dashboard every 5
seconds (via `@st.fragment(run_every=5)`), and shows a read-only "Team
drafts" view of each team's in-progress decision below.

Five modules sit under `app.py`:

| Module | Responsibility |
| --- | --- |
| `db.py` | SQLite schema and CRUD — the only module that touches SQLite. |
| `auth.py` | PBKDF2 password hashing (stdlib), register / login. |
| `service.py` | `GameService` — bridges the database to the engine: create a cohort, save / submit decisions, run a period, fetch reports, score planning quality, store / load the strategy map, validate and aggregate peer ratings, generate the board-meeting document. |
| `pedagogy.py` | Planning-quality scoring (sMAPE), `StrategyMap`, and the `PeerRating` / `AggregatedRating` models — pure, no DB / Streamlit dependency. See `docs/spec/09-pedagogy.md`. |
| `board_export.py` | Markdown renderer for the board-meeting document — pure, no DB / Streamlit dependency. See `09-pedagogy.md` §4. |

The multi-user app also surfaces the **pedagogy layer**: students get a
**Planning quality** tab (period-by-period plan-vs-actual scoring across
three KPIs — revenue, ROE, operating cash flow), a **Strategy** tab
(freeform Markdown balanced-scorecard authoring across the four classical
perspectives), a **Peer review** tab (rate each teammate on four Likert
dimensions plus an optional comment, once per cohort, editable until
close), and a **Board export** tab (download the team's capstone
deliverable as Markdown). Instructors get a cohort planning-quality
dashboard, a read-only per-team strategy-map viewer, a peer-reviews view
with per-team aggregates plus the full rater→ratee detail, and a
per-team board-export downloader. Ratees see only aggregated averages of
themselves, and only once the cohort closes.

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
├── pedagogy.py             scoring + strategy + peer-rating models (pure)
├── board_export.py         Markdown board-meeting renderer (pure)
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
`AppTest`. `test_phase3.py` (58 tests) covers the database, accounts and
sessions, the game service, the pedagogy scoring and peer-assessment
models, and the board-export Markdown renderer directly, plus `AppTest`
smoke tests of `app.py` — including end-to-end flows for submitting a
decision, running a period, saving a strategy map, saving a peer rating,
the board-export tab, and the instructor "Team drafts" view.

## Known limitations (multi-user app)

Two members of one team editing the same draft is last-write-wins;
real-time push is limited to the instructor's submission dashboard
(everywhere else, a normal Streamlit interaction triggers a rerun). The
role chosen at registration is ungated — anyone can register as an
instructor on a self-hosted install. See `../docs/current-task.md`.
