# Testing

How solar-sim is tested, how to run the tests, and what they do and do not
cover.

## Layout

| Suite | File | Count | Harness |
| --- | --- | --- | --- |
| Engine | `sim-engine/tests/test_run_period.py` | 28 | `pytest` |
| Console app | `app/test_app.py` | 4 | `pytest` + Streamlit `AppTest` |
| Multi-user app + pedagogy | `app/test_phase3.py` | 33 | `pytest` + Streamlit `AppTest` |

As of 2026-05-22 all 65 pass.

## Running the tests

Engine — from `sim-engine/` (the `pyproject.toml` there sets `testpaths`
and `-v --tb=short`):

```
PYTHONPATH=src python3 -m pytest
```

App — from the project root (`solar-sim/`); pointing pytest at `app/` runs
both app suites:

```
PYTHONPATH=sim-engine/src:app python3 -m pytest app/
```

There is no continuous-integration setup yet; tests are run locally.

## The central property: articulation

The simulation's correctness anchor is **articulation** — every period,
the three financial statements must reconcile:

- balance sheet: assets = liabilities + equity;
- cash-flow statement: opening cash + net cash flow = closing cash;
- equity roll-forward: opening equity + retained result = closing equity.

The report models expose an `articulates` boolean. Several tests assert it
directly, and the multi-period and full-playthrough tests assert it for
every period. A change that breaks articulation is a failed build.

## What the engine tests cover

- **Loading & initial state** — a scenario pack loads; `build_initial_state`
  produces a consistent period-0 balance sheet.
- **Articulation** — the three identities individually, across three
  consecutive periods, and across a full nine-period playthrough.
- **Multi-team settlement** — demand splits across competing teams; the
  export market opens in period 3 with FX conversion.
- **Period events** — wage changes flow through; the period-5 environmental
  law cuts line indices; the period-6 one-off charge lands; the
  dismissal cap is enforced.
- **HR** — productivity responds to training; purchasing/administration
  headcount auto-scales to revenue.
- **Sales channels** — bulk-buyer acceptance and lowest-bid tender wins.
- **Production** — line investment grows capacity.
- **Successor products** — the Gen-2 lifecycle (develop, launch, sell);
  producing a product before its launch period is rejected.
- **Validation** — invalid decisions (non-positive price, over-dismissal,
  sub-minimum non-salary cost) raise `InvalidDecisionError`.
- **Industry report** — every team receives it; market totals reconcile.
- **Environmental tech** — env capex articulates (a regression test for the
  balance-sheet bug); env-tech abatement reduces the compliance penalty.
- **Determinism** — re-running a period with identical inputs is identical.

The suite uses `pytest` fixtures (`pack`, `state_0`, `default_decision_p1`)
and module-level helper functions (`_build_decision`, `_plain_decision`,
`_develop_gen2`) to construct decisions concisely.

## What the app tests cover

`app/test_app.py` drives the Streamlit console headlessly with the
`AppTest` harness: the initial screen renders, a cohort starts, a period
runs and produces reports, and a pre-launch product appears in the
period-2 form as R&D-only. Helpers `_start_two_team_cohort` and
`_click_run` set up common flows.

## What the multi-user-app tests cover

`app/test_phase3.py` exercises the Phase 3 layer:

- **Database** — user / cohort / team / membership CRUD, append-only period
  states.
- **Auth** — PBKDF2 hash round-trip; register and login; rejection of
  duplicate emails, weak passwords, and unknown roles.
- **Service** — cohort creation seeds period-0 state and period-1 drafts;
  submission status; submit rejects an invalid decision; running a period
  persists state, reports and the next drafts; the all-submitted gate and
  its override; a full nine-period playthrough that asserts articulation
  every period and finishes the cohort.
- **App (AppTest)** — the login screen renders; registering lands on the
  correct role view; an existing user logs in; an instructor creates a
  cohort; a student fills and submits a decision end to end; an instructor
  runs a period end to end; a student sees the planning-quality tab after a
  period has been run; a student saves a strategy map.

## What the pedagogy-layer tests cover

Bundled into `app/test_phase3.py`:

- **`pedagogy.py` (pure)** — sMAPE edge cases (perfect, both zero, sign
  flip, half off), bound assertions across random inputs; aggregation
  rules (the headline averages only real periods, returns `None` if no
  real period has run); the `StrategyMap.is_empty` rule (whitespace-only
  is empty).
- **`db.py` strategy_maps** — upsert creates a row; upsert again
  overwrites; list returns the cohort's maps.
- **`service.py` pedagogy** — strategy-map roundtrip; per-period
  planning-quality computation after a period runs (three KPIs scored,
  trial-period correctly flagged, headline `None` when only trial
  periods have run); planning quality before any period yields an empty
  result.

The AppTest tests point the app at a throwaway database via the
`SOLAR_SIM_DB` environment variable. As with the console suite, a logout →
re-login round trip is not driven through `AppTest` — its element tree
cannot follow the widget-tree change across that `st.rerun()`; re-login
works in a real browser.

## Known coverage gaps

Truthful limits of the current suite:

- **`storage_box` and `balcony_solar`** are exercised only lightly
  (materialisation and the successor-product test focus on `panel_gen2`);
  their economics are not directly asserted.
- **Calibration is not asserted.** That a median decision is roughly
  break-even is checked by hand (see `docs/calibration.md`), not by a
  test — such an assertion would be brittle.
- **App tests are single-period.** `AppTest` does not follow the widget-key
  change across the `st.rerun()` period transition, so multi-period running
  through the UI is not tested there; the engine tests cover multi-period
  behaviour.
- **Unimplemented features are untested** — overtime, rationalisation
  capacity effect, dynamic rating, share price (see
  `docs/current-task.md`).
- **Browser rendering** — the multi-user app is verified headlessly with
  `AppTest` (server-side script execution), not in a real browser; visual
  layout is not asserted.
- **Concurrency** — simultaneous multi-user writes to one cohort are not
  tested; the suite is single-process.
- No line-coverage measurement is collected.

## Conventions

- A new engine rule or fix ships with a test in `test_run_period.py`; if it
  touches the financial statements, that test asserts `articulates`.
- Regression tests are kept and labelled as such (e.g.
  `test_environmental_capex_articulates`).
- Tests must not perform real I/O beyond loading the scenario pack, and
  must be deterministic.
