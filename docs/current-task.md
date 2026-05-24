# Current task

A living snapshot of where development stands. Update it as work moves.

**As of 2026-05-22.**

## Status

Pedagogy layer — first pass — is complete: planning-quality scoring and
balanced-scorecard strategy-map authoring. All work below is **in the
working tree, not yet committed**.

- 28 engine tests + 37 app tests pass.
- Last commit on `main`: `f6515a4` (Phase 3 multi-user app).

## Recently completed (uncommitted)

The first two pedagogy-layer features — the student-authored artifacts:

- **`docs/spec/09-pedagogy.md`** — formula (sMAPE-based planning-quality
  scoring) and data model spec, cited to public forecasting literature.
- **`app/pedagogy.py`** — pure scoring (`smape`, `kpi_score`,
  `PeriodPlanningQuality`, `TeamPlanningQuality`) and the `StrategyMap`
  Pydantic model. No DB or Streamlit coupling.
- **`db.py`** — new `strategy_maps` table; `get_strategy_map`,
  `upsert_strategy_map`, `list_strategy_maps`.
- **`service.py`** — `team_planning_quality(cohort, team)` composes
  per-period scores from stored decisions and reports; `get_strategy_map`
  and `save_strategy_map` for the map.
- **`forms.py`** — three planned-KPI inputs (revenue, ROE, operating
  cash flow) added to the Finance section. Until now `PlannedKPIs` was
  always zero because the form did not capture it.
- **`app.py`** — students get **Planning quality** (own scores by
  period) and **Strategy** (edit own balanced scorecard) tabs;
  instructors get a planning-quality dashboard and a read-only per-team
  strategy-map viewer.
- **`docs/sources.md` §8** — expanded with Hyndman & Athanasopoulos
  (2021) and Makridakis (1993) for sMAPE.
- **11 new tests** in `test_phase3.py`: sMAPE edge cases and bounds,
  planning-quality aggregation rules, strategy-map CRUD and roundtrip,
  planning quality after a period, plus AppTest smoke tests for both new
  tabs.

The engine was not touched; Phase 3 (the multi-user app) and the
single-operator console both still work.

## Immediate next step

Commit the working-tree changes. (Commits are made only when the
maintainer asks; pushing is done by the maintainer over SSH.)

## Then — open choice, not yet decided

- **Pedagogy layer — pass 2.** Peer assessment (anonymous teammate
  ratings, aggregation, instructor distributions) and board-meeting
  export (package per-team reports + strategy + planning quality into a
  Markdown or PDF deliverable). Each is its own phase.
- **Phase 3 polish.** Cookie-persistent login (today a browser refresh
  logs you out), a self-refreshing submission view, an instructor view
  of each team's in-progress draft.

## Known limitations / deliberate simplifications

Engine — genuine gaps, not bugs; the simulation is coherent without them
and every articulation identity holds:

- **Tender delivery lag** — a won tender delivers and bills in the
  current period; the scenario's `delivery_period` field is not yet
  honoured.
- **Overtime** — production hard-caps at Available Capacity II; there is
  no Available Capacity III / overtime stretch.
- **Rationalisation spend** — booked as a cost but does not raise
  capacity (it is a no-op lever; not exposed in the instructor console
  form).
- **`rating_index`** — static; never updates and does not feed back into
  borrowing rates.
- **`image_index` / `satisfaction_index`** — not dynamic
  (`_update_slow_indices` is a no-op). They are not read by the
  attraction model, so this is inert.
- **Share price** — not modelled; reported as `0` in the executive
  summary and industry report.
- **`storage_box` / `balcony_solar` economics** — first-pass estimates,
  not play-tested as thoroughly as the panel line.
- **Insolvency** — negative equity is not a game-over condition; the
  engine keeps running.
- **Market 2** — carries `panel_gen1` only; the successor products are
  domestic-market only.

Multi-user app — deliberate first-pass simplifications:

- **Session login** — a logged-in session lives in Streamlit
  `session_state`; a hard browser refresh requires logging in again.
- **No real-time updates** — users refresh to see others' progress; the
  submission dashboard does not push.
- **Draft concurrency** — two members of one team editing the same
  draft is last-write-wins.
- **Open instructor role** — the role is chosen freely at registration;
  there is no instructor-signup gate.
- **Seeded default decision** — the period-1 default is tuned for a
  ~5-team cohort; a much smaller cohort will see a large period-1 loss
  if a team submits it untouched (a calibration matter — see
  `docs/calibration.md`).

Pedagogy layer first pass:

- **Planned KPIs default to zero.** A team that submits without
  entering planned values scores 0 on any period where actuals are
  non-zero. This is a pedagogical signal — planning is what is being
  measured — rather than a bug.
- **Strategy maps have no version history.** Edits overwrite.
- **Strategy maps are not algorithmically graded.** The instructor
  reviews each team's map manually against the course rubric.
- **Three equally-weighted KPIs.** Revenue, ROE and operating cash flow
  contribute one-third each to a period's planning-quality score; the
  `PlannedKPIs` model is fixed at three fields. A scenario-configurable
  weight vector is a possible refinement.

## Small known issues

- Version mismatch: `sim-engine/pyproject.toml` says `0.1.0` while
  `sim_engine/__init__.py` says `0.2.0`. Harmless, but pick one.
