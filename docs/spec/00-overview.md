# 00 — Overview, State, and Period Loop

> **Scope.** This document defines the simulation as a state machine: what state the
> engine carries between periods, what decisions a team submits each period, and the
> deterministic order in which the rule modules transform state into reports.
> Sub-specs (`01`–`06`) define each rule module in detail.

---

## 1. Conceptual model

The simulation is **discrete-time, deterministic, and multi-team**.

- **Time** advances in discrete *periods*. A period represents one fiscal year. Each
  period is a single transition: prior state + a vector of per-team decisions →
  new state + a bundle of reports.
- **Determinism.** Given the same (state, decisions) input, the engine always produces
  the same output. Randomness, if introduced, comes from a seeded RNG attached to the
  scenario; runs are reproducible.
- **Multi-team.** A *cohort* is a set of *N* teams playing the same scenario. Teams
  compete in shared markets; their decisions affect each other's market share and
  observed competitive context.

### 1.1 State and decision separation

We treat the world as three nested objects:

```
Cohort
└── Period (t)
    ├── Scenario parameters (read-only for this period)
    │     wages, interest rates, market potentials, currency rates, etc.
    └── Companies (1 per team)
        ├── Balance state         assets, equity, liabilities, inventories
        ├── Workforce state       headcount per cost centre, indices
        ├── Production state      production lines, cumulative experience
        ├── Product state         per-product indices (efficiency, etc.)
        └── Decisions for t       what the team submitted this period
```

Reports are derived from the *post-transition* state — they are views, not stored
fields. The single canonical artifact between periods is the company state.

### 1.2 Periods

| Phase                | Periods       | Purpose                          | Scored? |
|----------------------|---------------|----------------------------------|---------|
| **Initialisation**   | t = 0         | Imported from scenario           | n/a     |
| **Trial periods**    | t = 1 … 3     | Practice; teams learn the engine | No      |
| **Real periods**     | t = 4 … 9     | Counted toward grade             | Yes     |
| **Final settlement** | end of t = 9  | Score & rank cohort              | n/a     |

The trial/real boundary is a scenario parameter, not a hard-coded constant. A short
cohort can skip trials. The default scenario `solar-v1` is configured for **3 trial +
6 real** to match the workload of a one-semester course.

---

## 2. Period loop (the engine's `run_period` function)

Given the prior period's state `S_{t-1}` and a dictionary of decisions
`D_t = { team_id → decision }`, produce `S_t` and `Reports_t`:

```
1. Validate     Each decision: bounds, mutual exclusions, scenario constraints.
                Reject the whole period if any decision is invalid; never silently clamp.

2. R&D          For each company × product: update efficiency, sustainability,
                value-analysis indices from R&D spend.

3. Workforce    Apply hires/dismissals; recompute productivity & motivation indices;
                resolve attrition from the prior period.

4. Capacity     For each company: roll forward production lines (depreciation,
                disinvestment, new investments). Compute Available Capacity I → II → III
                from maintenance, rationalisation, and overtime.

5. Production   For each company: produce up to min(target volume, capacity, staff).
                If the company under-produces, finished-goods inventory accumulates
                or shortfalls flow through to lost sales next step.

6. Inventory    Update materials and finished-goods inventories with moving-average
                valuation.

7. Market       Across all companies: settle demand per market × channel × product
                using the attraction model (see `01-sales.md`). Compute market shares.

8. Allocation   Allocate each company's finished goods across channels in priority
                order: tenders won → bulk buyers → retail market 1 → retail market 2.

9. Costing      Compute cost-type, cost-centre, and cost-unit accounting; derive
                contribution margins per product per channel.

10. Finance     Compute interest, tax, dividend cash-flows. Resolve loan repayments
                and auto-overdraft. Settle pension reserve.

11. Articulate  Produce P&L, balance sheet, and cash-flow statement that all
                reconcile (this is verified by tests, not by chance — see
                `06-accounting.md`).

12. Indices     Update share price, rating, customer satisfaction, planning quality.

13. Reports     Emit the per-team report bundle and the public industry report.

14. Carry       Bundle (state-after, reports) and return.
```

Each numbered step corresponds to a function in the engine package. The order is
deterministic and documented in code via the orchestrator. Reordering steps within a
phase (e.g. swapping 7 and 8) breaks the model — these are sequential dependencies.

---

## 3. Decisions a team can submit

A *decision* is a single document submitted per team per period. The full schema is
defined alongside each rule module, but at the top level it has six sections matching
the six functional areas:

```yaml
team_id: t01
period: 5
sales:
  by_product:
    - product: residential_panel_gen1
      market_1:
        price: 320.0           # EUR/unit
        advertising: 8_000_000 # EUR
        sales_force: 210       # headcount
      market_2:
        price: 340.0           # in local currency of market_2
        advertising: 4_000_000
        sales_force: 50
      bulk_buyer:
        accept_offer: true
        bid_units: 5000
      tender:
        bid_price: 295.0
        bid_units: 4000
  corporate_identity: 9_000_000
  market_research_report: true

rnd:
  by_product:
    - product: residential_panel_gen1
      researchers: 200
      sustainability_spend: 4_000_000
      value_analysis_spend: 2_000_000

purchasing:
  by_product:
    - product: residential_panel_gen1
      order_units: 70_000

production:
  by_product:
    - product: residential_panel_gen1
      target_volume: 63_000
  lines:
    invest:  { stringer_v1: 0, laminator_v2: 0, fullauto_v3: 5 }
    disinvest: [ line_A1 ]                # by id
    maintenance:                          # mEUR per line per type
      stringer_v1: 1_000_000
      laminator_v2: 1_000_000
      fullauto_v3: 1_000_000
    rationalisation: { stringer_v1: 0, laminator_v2: 0, fullauto_v3: 0 }
  environmental_capex: 0

hr:
  production_workforce_change: -50        # negative = dismissals
  rnd_target_headcount: 200               # engine adjusts automatically
  sales_force_target:                     # under sales above; engine reconciles
  training_per_employee: 1_600            # EUR
  process_optimisation_spend: 3_000_000
  non_salary_pct: 0.40
  pension_reserve_pct: 0.02

finance:
  short_term_loan: 30_000_000
  long_term_loan: 0
  securities_purchase: 0
  dividend: 0                             # EUR
  planned_kpis:                           # used for planning-quality scoring
    revenue: 158_000_000
    return_on_equity: 0.035
    operating_cash_flow: 11_820_000
```

### 3.1 Decision validation

Validation runs before any rule module executes. A decision is invalid if any of:

- A monetary or count value is negative where the spec requires non-negative.
- A spend exceeds the company's available cash + maximum overdraft.
- A target headcount is below absolute minimums (e.g., production staff > 0).
- A scenario-specific constraint is violated (e.g., dismissal limits in a recession
  period, environmental compliance, currency-conversion bounds).

Invalid decisions are returned to the team for correction. The engine never
silently clamps values, because silent clamping makes the planning-quality scoring
unreliable and produces post-hoc surprises.

---

## 4. Time within a period (the "as of when" question)

| Quantity                                | Measured/applied at … |
|-----------------------------------------|------------------------|
| Initial inventories, workforce, equity  | Start of period (= end of prior period) |
| Decisions                               | Submitted before period runs |
| Hires, dismissals, attrition            | Happen instantaneously at start of period |
| R&D index changes                       | Effective at start of period |
| New production lines                    | Available from start of period |
| Production                              | Throughout the period |
| Sales settlement                        | At end of period, once for all companies |
| Cash receipts (80% / 20% split)         | 80% in period, 20% in next-period receivables |
| Interest                                | Settled at end of period |
| Tax, dividend                           | Paid at end of period |
| Final inventories, workforce, equity    | End of period (= start of next) |

This convention lets us treat each period as a pure function and avoid temporal
ambiguity.

---

## 5. State schema (minimal)

The engine's `PeriodState` is the canonical persistent object. In Python, expressed
as Pydantic / SQLModel dataclasses (Phase 1 will formalise this):

```
PeriodState
├── meta: { period_index, scenario_id, scenario_version, cohort_id, rng_seed }
├── scenario_snapshot: dict       (resolved scenario parameters for THIS period)
└── companies: List[CompanyState]
    └── CompanyState
        ├── id
        ├── inventories: { product_id → InventoryRecord }
        ├── workforce:   { cost_centre → headcount, salary_per_capita }
        ├── lines:       List[ProductionLine]
        ├── products:    { product_id → ProductState (indices, cumulative output) }
        ├── balance:     BalanceSheet  (assets, liabilities, equity)
        ├── pension_reserve: float
        ├── cash:        float
        ├── loans:       { short_term, long_term, overdraft } each with amount + rate
        ├── securities:  float
        ├── motivation_index, image_index, satisfaction_index, rating_index
        └── last_reports: ReportBundle | None
```

A *PeriodState* is immutable once produced. The engine writes a new one each period.

---

## 6. Reports emitted each period

Per company (private):

1. **Executive summary** — share price, ROE, revenue, net income, key indices
2. **Market** — units sold and revenue by product × market × channel; market shares
3. **Production** — line-by-line capacity, depreciation, utilisation
4. **R&D** — indices vs competitors, expenses
5. **Inventory** — materials and finished goods movement and valuation
6. **HR** — workforce by cost centre, salary, indices, hiring/dismissal costs
7. **Cost-type accounting** — total costs by category
8. **Cost-centre accounting** — costs allocated to each cost centre
9. **Cost-unit accounting** — costs per produced unit per product
10. **Contribution margin** — CM I/II/III/IV per product × channel
11. **P&L** — full income statement
12. **Cash receipts and disbursements** — period cash account
13. **Cash-flow statement** — operating / investing / financing
14. **Balance sheet** — assets / liabilities / equity (reconciles with 11 and 13)
15. **Planning quality** — planned vs actual KPIs, scored

Cohort-public (issued in parallel):

- **Industry report** — every company's P&L and balance sheet at the published level
  of detail (matches what a public competitor's annual report would show), plus
  market-wide unit sales and price data per product per market.

Reports are deterministic views over the state — they carry no information not
already in `PeriodState`. This simplifies replay and testing.

---

## 7. Replay, audit, and testing

Two properties the engine must hold:

1. **Replayability.** Given the scenario, the initial `PeriodState`, and the
   sequence of decision vectors `[D_1, D_2, …, D_n]`, replaying produces an
   identical sequence of states and reports.

2. **Articulation.** P&L, balance sheet, and cash-flow statement reconcile to the
   cent. Specifically:
   - `equity_end = equity_start + net_income − dividends`
   - `cash_end = cash_start + cash_flow_total`
   - `balance_sheet_total_assets == balance_sheet_total_liabilities_and_equity`

   These are enforced by golden-file tests over `solar-v1` (see `sim-engine/tests/`
   once Phase 1 begins).

---

## 8. Glossary (project-internal terminology)

| Term                       | Meaning |
|----------------------------|---------|
| **Cohort**                 | A set of teams playing one shared scenario instance |
| **Channel**                | A way to sell: retail market 1, retail market 2, bulk buyer, public tender |
| **Cost centre**            | Purchasing, Administration, Production, R&D, Sales — five fixed categories |
| **Index**                  | A normalised attribute on a [0, ∞) scale (efficiency, sustainability, etc.) with 100 = neutral starting baseline |
| **Line**                   | One production line; has a type (stringer_v1 etc.), capacity, residual life |
| **Productivity index I**   | Within-period productivity multiplier (process, motivation, competence) |
| **Productivity index II**  | Cumulative-experience multiplier (learning curve) |
| **Rating**                 | Lender's credit assessment of the company, 0–100; affects loan interest |
| **Scenario pack**          | A self-contained `scenarios/<name>/` folder defining one playable scenario |
| **Trial period**           | A period not counted toward the grade; same mechanics as a real period |

---

## 9. What's deliberately *not* in this overview

These belong in dedicated sub-specs:

- The demand attraction model and its formulas → `01-sales.md`
- R&D index dynamics → `02-rnd.md`
- Capacity laddering, depreciation, learning curves → `03-production.md`, `04-hr.md`
- Loan, rating, share-price formulas → `05-finance.md`
- Cost-type / centre / unit allocation and the P&L → BS → CF articulation → `06-accounting.md`
- Scenario-pack YAML schema → `07-scenario-format.md` (TBD)
- The solar-PV product narrative → `08-solar-narrative.md` (TBD)
