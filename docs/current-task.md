# Current task

A living snapshot of where development stands. Update it as work moves.

**As of 2026-05-22.**

## Status

Phase 3 — the student-facing multi-user app — is complete. All Phase 3 work
is **in the working tree, not yet committed**.

- 28 engine tests + 26 app tests pass.
- Last commit on `main`: `ba2982a` (finish & calibrate solar-v1).

## Recently completed (uncommitted)

Phase 3 — a multi-user, SQLite-backed Streamlit app with per-student logins,
alongside the existing instructor console:

- **`app/db.py`** — SQLite schema and CRUD (users, cohorts, teams,
  team_members, period_states, decisions, reports); one connection per
  operation, WAL mode.
- **`app/auth.py`** — PBKDF2 password hashing and register / login, stdlib
  only.
- **`app/service.py`** — `GameService`, the bridge from the database to the
  engine: create a cohort, save / submit decisions, run a period, fetch
  reports. Period history is append-only, so a cohort stays replayable.
- **`app/app.py`** — one Streamlit app, role-gated at login. Instructors
  create cohorts, assign students to teams, watch a submission dashboard,
  run periods, and review every team's reports; students see the briefing,
  fill and submit their team's decision, and review their own reports.
- **`app/test_phase3.py`** — 22 tests: db / auth / service units, a full
  nine-period playthrough, and headless AppTest smoke tests (including an
  end-to-end student submit and instructor period run).
- Docs updated: `CLAUDE.md`, `architecture.md`, `decisions.md` (#18–#20),
  `README.md`, `app/README.md`, `testing.md`.

The engine was not touched; the instructor console still works unchanged.

## Immediate next step

Commit the Phase 3 working-tree changes. (Commits are made only when the
maintainer asks; pushing is done by the maintainer over SSH.)

## Then — open choice, not yet decided

- **Pedagogy layer.** Planning-quality scoring (forecast vs actual),
  strategy-map / balanced-scorecard authoring, peer assessment,
  board-meeting export — the graded-course features. Per-student accounts
  are now in place, which peer assessment needs.
- **Phase 3 polish.** Cookie-persistent login (today a browser refresh logs
  you out), a self-refreshing submission view, an instructor view of each
  team's in-progress draft.

## Known limitations / deliberate simplifications

Engine — genuine gaps, not bugs; the simulation is coherent without them and
every articulation identity holds:

- **Tender delivery lag** — a won tender delivers and bills in the current
  period; the scenario's `delivery_period` field is not yet honoured.
- **Overtime** — production hard-caps at Available Capacity II; there is no
  Available Capacity III / overtime stretch.
- **Rationalisation spend** — booked as a cost but does not raise capacity
  (it is a no-op lever; not exposed in the instructor console form).
- **`rating_index`** — static; never updates and does not feed back into
  borrowing rates.
- **`image_index` / `satisfaction_index`** — not dynamic (`_update_slow_indices`
  is a no-op). They are not read by the attraction model, so this is inert.
- **Share price** — not modelled; reported as `0` in the executive summary
  and industry report.
- **`storage_box` / `balcony_solar` economics** — first-pass estimates,
  not play-tested as thoroughly as the panel line.
- **Insolvency** — negative equity is not a game-over condition; the engine
  keeps running.
- **Market 2** — carries `panel_gen1` only; the successor products are
  domestic-market only.

Multi-user app — deliberate first-pass simplifications:

- **Session login** — a logged-in session lives in Streamlit
  `session_state`; a hard browser refresh requires logging in again.
- **No real-time updates** — users refresh to see others' progress; the
  submission dashboard does not push.
- **Draft concurrency** — two members of one team editing the same draft is
  last-write-wins.
- **Open instructor role** — the role is chosen freely at registration;
  there is no instructor-signup gate.
- **Seeded default decision** — the period-1 default is tuned for a ~5-team
  cohort; a much smaller cohort will see a large period-1 loss if a team
  submits it untouched (a calibration matter — see `docs/calibration.md`).

## Small known issues

- Version mismatch: `sim-engine/pyproject.toml` says `0.1.0` while
  `sim_engine/__init__.py` says `0.2.0`. Harmless, but pick one.
