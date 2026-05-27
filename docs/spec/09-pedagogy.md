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

## 3. Peer assessment

Each student rates every other member of their team on four dimensions,
plus an optional free-text comment per teammate. Ratings are visible to
the instructor in full; ratees see only their own aggregated per-dimension
averages, and only once the cohort has finished — the standard
anonymity-to-ratee pattern in classroom peer assessment (`sources.md` §8:
Topping 2009; Fellenz 2006).

### 3.1 Dimensions and scale

| Dimension      | What it captures                                              |
|----------------|---------------------------------------------------------------|
| Contribution   | Share of useful work done                                     |
| Collaboration  | Willingness to work with others; supportiveness               |
| Reliability    | Meeting commitments, attendance, follow-through               |
| Communication  | Clarity, responsiveness, sharing information                  |

Each on an integer **1–5 Likert scale** (5 highest), plus an optional
free-text **comments** field. The multi-dimensional "evaluation of
individual contributions" pattern follows Fellenz (2006).

### 3.2 Cadence and editing

Each rating is **one row per (rater, ratee) per cohort**. The rater can
edit any time the cohort is `active`; when the cohort moves to
`finished`, ratings are locked and the service refuses further writes.

### 3.3 Visibility

- **The rater** sees their own draft ratings any time.
- **The ratee** sees aggregated per-dimension averages of all ratings they
  received, plus the count of raters, **only after the cohort closes**.
  Comments are *not* shown to the ratee in this first pass (a possible
  refinement is to share them anonymised); they go to the instructor.
- **The instructor** sees everything: rater identity, scores, comments,
  per-team aggregates and the full rater→ratee matrix.

### 3.4 Data model

One row per (cohort × rater × ratee):

```
peer_ratings
  cohort_id      INTEGER, FK cohorts(id)
  rater_id       INTEGER, FK users(id)
  ratee_id       INTEGER, FK users(id)
  contribution   INTEGER, CHECK 1..5
  collaboration  INTEGER, CHECK 1..5
  reliability    INTEGER, CHECK 1..5
  communication  INTEGER, CHECK 1..5
  comments       TEXT
  updated_at     TEXT (ISO-8601)
PK (cohort_id, rater_id, ratee_id)
```

The schema's CHECK constraints catch out-of-range scores at the database
boundary; the service layer adds three rules that aren't expressible in
schema:

- **Rater ≠ ratee** — no self-rating in this first pass.
- **Same team** — rater and ratee must both be members of the same team
  in the cohort at the moment the rating is saved.
- **Cohort still active** — once the cohort is `finished`, ratings are
  locked.

### 3.5 Aggregation

The aggregated view shown to the ratee (after close) and to the
instructor (any time) is the unweighted mean per dimension across all
that ratee's raters, plus the count of raters. Pure functions in
`app/pedagogy.py` (`aggregate_ratings`) compute this; the service layer
fetches the rows.

### 3.6 Deliberately out of scope (first pass)

- **Self-assessment.** Including self-ratings as a calibration mechanism
  is a possible refinement.
- **Per-period ratings.** This pass takes one rating per (rater, ratee)
  per cohort; per-period ratings would require a `period` column and a
  different UI flow.
- **Weighted aggregation / trimmed means.** All ratings are averaged
  equally; outlier protection (trimming, weighting by rater consistency)
  can come later.
- **Comments to ratees.** Comments go to the instructor only in this
  first pass; sharing them anonymised to ratees is the obvious next
  refinement.
- **Team-membership churn.** A rating persists if its ratee is later
  moved to a different team mid-cohort; the rate-form only shows
  *current* teammates, so the rater cannot edit a "stale" rating. The
  instructor can clear stale ratings out-of-band if needed.

---

## 4. Board-meeting export

The capstone deliverable. A team's work over the cohort is packaged into
a single portable **Markdown** document, downloadable from the app and
suitable for sharing, printing, or converting to PDF / DOCX via pandoc.

### 4.1 Why Markdown

Markdown carries the project's no-third-party-dependency stance:
generation is a pure string-build, it renders natively as a Streamlit
preview, and downstream conversion to PDF or DOCX is one `pandoc` (or
text-editor paste) away. A native PDF / DOCX exporter is a possible
future refinement.

### 4.2 Document structure

A board-meeting document has, in order:

1. **Cover** — cohort name, team name, team members, generated date,
   period range played.
2. **Cohort standing** — final-period industry table (the team
   highlighted) with revenue, operating income, net income, equity,
   total debt, and market share.
3. **Period-by-period** — for each completed period: the headline
   executive summary, market lines, P&L summary, balance-sheet check,
   and cash-flow totals.
4. **Planning quality** — headline score plus the per-period KPI table.
5. **Strategy map** — the four balanced-scorecard perspectives as the
   team authored them.
6. **Peer assessment** — visibility-gated; see §4.3.

### 4.3 Viewer-role visibility

The same document generator runs for two viewer roles, and the peer
assessment section is filtered accordingly:

- **Student viewer.** Only their own aggregated per-dimension averages,
  and only if the cohort is `finished` (matches §3.3). Other teammates'
  ratings, comments, and the full matrix are excluded.
- **Instructor viewer.** The full per-team aggregates and the rater→
  ratee detail including comments, any time.

### 4.4 Where it lives

A pure renderer in `app/board_export.py` takes a data bundle and returns
the Markdown string. `app/service.py` orchestrates the fetch from SQLite
and the viewer-role visibility filtering. The Streamlit tab in
`app/app.py` calls the service, renders the document as a preview, and
offers an `st.download_button` save-as-Markdown.

### 4.5 Deliberately out of scope (first pass)

- **PDF / DOCX export.** A future refinement; would add a library
  dependency.
- **Custom templates.** The document structure is fixed; per-course
  template customisation is a later concern.
- **Multi-team consolidated reports.** The export is per team; an
  instructor wanting a cohort-wide deliverable currently exports each
  team's document and combines manually.

---

## 5. Deliberately out of scope (whole pedagogy layer)

These are real concerns the pedagogy layer will eventually address.
They are not in the current scope:

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
