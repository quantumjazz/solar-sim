# Testing

How solar-sim is tested, how to run the tests, and what they do and do not
cover.

## Layout

| Suite | File | Count | Harness |
| --- | --- | --- | --- |
| Engine | `sim-engine/tests/test_run_period.py` | 35 | `pytest` |
| Console app | `app/test_app.py` | 4 | `pytest` + Streamlit `AppTest` |
| Multi-user app + pedagogy | `app/test_phase3.py` | 58 | `pytest` + Streamlit `AppTest` |

As of 2026-05-25 all 97 pass.

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
- **Peer assessment (pure)** — `PeerRating` validation rejects scores
  outside 1–5; `aggregate_ratings` returns all-`None` means for an empty
  input, filters to one ratee, and computes per-dimension means
  correctly.
- **Peer assessment (db)** — `peer_ratings` CRUD: upsert creates and
  overwrites; `delete_peer_rating` removes; the schema CHECK constraints
  reject out-of-range scores at the database boundary.
- **Peer assessment (service)** — `team_peer_targets` excludes self and
  other-team members; `save_peer_rating` rejects self-rating, cross-team
  pairs, out-of-range scores, and any save after the cohort is
  `finished`; `my_aggregated_rating` returns `None` until the cohort
  closes; the instructor's `team_peer_aggregates` returns the right
  per-ratee summary.
- **Peer assessment (AppTest)** — a student logs in, sets the four
  Likert inputs and a comment for a teammate, clicks save, and the
  rating persists; the aggregated view is hidden while the cohort is
  active and appears after the cohort closes.
- **Board export (pure renderer)** — the cover carries team and cohort
  identity; an empty data bundle yields placeholder strings for each
  section; the role filter keeps peer comments in the instructor
  document and out of the student document; `_md_table` escapes pipes
  and collapses newlines inside cells.
- **Board export (service)** — student view on an active cohort hides
  peer aggregates and comments but renders the period reports and
  strategy map; student view on a finished cohort shows the user's own
  aggregate while still hiding comments; instructor view always shows
  per-member aggregates, detailed rater→ratee rows, and comments.
- **Board export (AppTest)** — the Board export tab renders, and the
  rendered document's H1 (`Board-meeting document — Apex`) appears in
  the preview.
- **Cookie sessions (db + auth)** — `sessions` table CRUD round-trips;
  expired sessions don't resolve and are pruned by `purge_expired`;
  `auth.create_session` mints a 32+ char token that `lookup_session`
  resolves to the user, and `end_session` invalidates it.
- **Instructor draft view (AppTest)** — the Run-period tab shows a
  "Team drafts (read-only)" section, and each team's expander label
  reflects its current draft / submitted state.

### Untested by design

- **Cookie browser persistence end-to-end.** The cookie value crosses a
  JS bridge inside `extra_streamlit_components.CookieManager`; AppTest
  is server-side script execution, not a browser, so it cannot drive
  the cookie round trip. The DB and auth layers under the cookie are
  unit-tested; the UI integration is verified only by the app loading
  without exception and login still working in the headless harness.
- **Auto-refresh timing.** `@st.fragment(run_every=5)` polls the DB on
  a wall-clock timer; AppTest does not advance wall-clock time. The
  fragment's *content* (status table, override, Run button) is still
  exercised by the existing instructor-runs-period test.

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
