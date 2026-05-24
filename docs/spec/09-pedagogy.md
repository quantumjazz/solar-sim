# 09 — Pedagogy Layer

> **Scope.** This document specifies the pedagogical artifacts layered on
> top of the simulation: per-period **planning-quality scoring** and a
> per-team **balanced-scorecard strategy map**. These are graded-course
> features. They live in the app (`app/`), not in the engine; the engine
> stays pedagogy-agnostic and an instructor can ignore the pedagogy layer
> entirely without losing any simulation behaviour.
>
> Sub-spec ordering: this document depends on `00-overview.md` (the period
> loop), `06-accounting.md` (the KPI definitions referenced below) and the
> Phase 3 multi-user app described in `docs/architecture.md`.

---

## 1. Planning quality

### 1.1 What it scores

Alongside their decision each period, a team submits planned values for
three headline KPIs. These are already part of `TeamDecision.finance.planned_kpis`
(see `sim-engine/src/sim_engine/decisions.py`):

- **Revenue** — base-currency total over the period.
- **Return on equity (ROE)** — `net_income / opening_equity` (the
  executive-summary definition; see `06-accounting.md` §8).
- **Operating cash flow (OCF)** — from the indirect-method cash-flow
  statement.

After the period runs, the actual values are read from the team's
`ReportBundle`:

| KPI                 | Planned source                                       | Actual source                                |
|---------------------|------------------------------------------------------|----------------------------------------------|
| Revenue             | `decision.finance.planned_kpis.revenue`              | `bundle.profit_and_loss.sales_revenue`       |
| Return on equity    | `decision.finance.planned_kpis.return_on_equity`     | `bundle.executive_summary.return_on_equity`  |
| Operating cash flow | `decision.finance.planned_kpis.operating_cash_flow`  | `bundle.cash_flow.operating_cash_flow`       |

### 1.2 Scoring formula

For each KPI, we score forecast accuracy with the **symmetric mean
absolute percentage error** (sMAPE) — a standard forecasting metric
(`sources.md` §8: Makridakis 1993; Hyndman & Athanasopoulos 2021).

For a planned value *p* and an actual value *a*:

```
sMAPE(p, a) = |p − a| / (|p| + |a|)         when |p| + |a| > 0
            = 0                              when p = a = 0

score(p, a) = 1 − sMAPE(p, a)               ∈ [0, 1]
```

Properties relied on:

- **Symmetric.** Optimistic and pessimistic misses by the same absolute
  amount are penalised equally.
- **Bounded.** A perfect forecast scores 1; a sign flip or arbitrarily
  large miss scores 0.
- **Handles negatives.** Loss-making periods (negative ROE, negative
  OCF) are common; sMAPE is well-defined on signed inputs.
- **Both-zero is "perfect."** Predicting zero and getting zero scores 1
  — useful for the OCF KPI in early periods.

A **period score** for a team is the unweighted mean of the three KPI
scores, displayed as a percentage. (A scenario-configurable weight
vector is a possible later refinement; see §3.)

### 1.3 Aggregation across periods

The scenario distinguishes **trial periods** and **real periods** —
`scenarios/solar-v1/scenario.yaml` sets `trial_periods: [1, 2, 3]` and
`real_periods: [4..9]`. Trial periods are scored — students see the
feedback — but only real periods feed the cohort-wide **headline** score:

```
planning_quality(team) =
    mean( period_score(team, t)  for t in real_periods  if  t ≤ current_period )
```

Periods that have not yet been run yield no score; planned KPIs exist
from the moment a team submits, but no actual is available until
`run_period` lands.

### 1.4 Where the math lives

Pure functions in `app/pedagogy.py`, with no database or UI dependency,
so the formula is unit-testable on its own. The service layer
(`app/service.py`) reads decisions and reports from SQLite, calls the
scoring functions, and returns the Pydantic models the UI consumes.

The engine is not touched: planning quality is derived entirely from
artifacts (`TeamDecision`, `ReportBundle`) the engine already produces.

---

## 2. Strategy map (balanced scorecard)

### 2.1 What it is

A team-authored statement of strategy, organised under the four classical
balanced-scorecard perspectives (`sources.md` §8: Kaplan & Norton 1996,
2004):

- **Financial** — what financial results matter to the team.
- **Customer** — how the team intends to be seen by its customers.
- **Internal process** — what internal operations the strategy depends on.
- **Learning and growth** — what capabilities the team must build.

The simulation does not consume the strategy map mechanically; it is a
pedagogical artifact graded by the instructor against the course rubric.

### 2.2 Data model

One row per (cohort × team):

```
strategy_maps
  cohort_id          INTEGER, FK cohorts(id)
  team_id            INTEGER, FK teams(id),  PK part
  financial          TEXT  (Markdown)
  customer           TEXT  (Markdown)
  internal_process   TEXT  (Markdown)
  learning_growth    TEXT  (Markdown)
  updated_by         INTEGER, FK users(id)
  updated_at         TEXT  (ISO-8601)
```

Each perspective is **freeform Markdown**. Students can structure each
perspective as a list of objectives → measures → targets → initiatives,
or as prose, or as a mix — the app does not impose a schema beyond the
four perspectives.

The MVP keeps only the current version. Edit history is deliberately out
of scope (§3).

### 2.3 Visibility

A strategy map is visible to:

- **The team's members** — read and edit.
- **The cohort's instructor** — read-only.

Competing teams cannot see each other's strategy maps. The map is part
of a team's competitive position, like its draft decisions.

### 2.4 When it is written

The map can be edited any time the cohort is active. The MVP does not
enforce a deadline; convention is that teams write a first draft after
period 1-2 (when they know their market and their inherited company) and
revise it as the simulation proceeds.

---

## 3. Deliberately out of scope (first pass)

These are real concerns the pedagogy layer will eventually address.
They are not in the first pass:

- **Peer assessment** and **board-meeting export** — the other two
  pedagogy-layer features listed in `docs/current-task.md`. Each is its
  own follow-up phase.
- **Automated strategy-map grading.** The map is graded by the
  instructor against the course rubric, not by the engine.
- **Strategy-map version history.** Only the current version is stored;
  edits overwrite.
- **Weighted KPIs.** The three planning-quality KPIs are weighted
  equally. A scenario-configurable weight vector is a possible
  refinement (the `PlannedKPIs` model is fixed at three fields for now;
  growing it would be a coordinated change).
- **Cross-team strategy benchmarking.** No teams-vs-teams view of
  strategy maps; competitive secrecy is the simpler default.
