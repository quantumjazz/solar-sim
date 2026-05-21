# 06 — Accounting: Cost Type, Cost Centre, Cost Unit, P&L → BS → CF

> **Scope.** The central financial articulation of the simulation. Every euro spent
> or earned passes through this chain. The P&L, balance sheet, and cash-flow
> statement *must* reconcile by construction. Tests enforce this in code; the spec
> defines it here.
>
> This is the most pedagogically important rule module: most undergraduate accounting
> learning happens here. It uses standard German commercial code (HGB) §266 balance
> sheet structure and is consistent with IFRS for the items modelled. Equivalent
> structures exist in US GAAP; ports to that vocabulary are straightforward.

---

## 1. The three accountings, layered

The simulation uses the classical three-layer managerial accounting view, which
is standard in continental-European business education (e.g., Drury 2018; Coenenberg
et al. 2018; see sources §3):

```
Cost type accounting     "What kind of cost is it?"      Material / Personnel / Depreciation / Other
        ↓
Cost centre accounting   "Where in the company?"         Purchasing / Production / R&D / Sales / Admin
        ↓
Cost unit accounting     "On what product?"              Per-product, per-unit
```

These three views show the *same* costs cut three different ways. They reconcile
horizontally — totals match.

---

## 2. Cost type accounting

Total costs in a period are decomposed into four primary categories:

### 2.1 Material costs

```
material_costs = input_material_cost + factory_material_cost
```

| Component | Formula |
|-----------|---------|
| `input_material_cost` | `units_consumed · weighted_avg_unit_price` (see §2.1.1) |
| `factory_material_cost` | `units_produced · factory_material_per_unit (scenario)` |

#### 2.1.1 Moving-average inventory valuation

Input materials and finished goods are valued at moving average cost. For input
materials:

```
opening_value = opening_units · opening_unit_value
purchase_value = purchased_units · current_price_tier_unit_value
new_unit_value = (opening_value + purchase_value) / (opening_units + purchased_units)
consumed_value = consumed_units · new_unit_value
closing_value = (opening_units + purchased_units − consumed_units) · new_unit_value
```

The same pattern applies to finished goods, where "purchase" is "produced" and
the per-unit value is the *cost of goods manufactured* (CGM) computed in §3.2.

### 2.2 Personnel costs

```
personnel_costs = wages_salaries
                + non_salary_costs       // = non_salary_pct · wages_salaries
                + pension_reserve_contrib // = pension_reserve_pct · wages_salaries
                + hiring_costs            // per-hire fee
                + dismissal_costs         // per-dismissal fee, plus social-plan if applicable
                + training_costs          // = training_per_employee · workforce
                + overtime_premium        // if applicable
```

Social-plan surcharge applies when dismissals in a single period exceed a
fraction of the cost centre's opening workforce (defaults: 10 % → +15 000 EUR per
dismissal; 30 % → +20 000 EUR; 50 % → +25 000 EUR). Scenario-tunable.

### 2.3 Depreciation

```
depreciation = buildings_depreciation
             + production_line_depreciation     // straight-line over remaining life
             + environmental_tech_depreciation  // straight-line over 10 periods
```

Disinvestment triggers *extraordinary depreciation* of the remaining net book
value (see §3.4); this is separated out for P&L presentation.

### 2.4 Other costs

```
other_costs = misc_fixed_line_costs
            + maintenance + rationalisation
            + process_optimisation_spend
            + environmental_compliance_penalties
            + rework_costs
            + storage_costs                   // materials + finished goods
            + advertising + corporate_identity + market_research_fee
            + rnd_consulting (ecology + value_analysis)
            + transport_costs                 // per unit per market
            + miscellaneous_overhead
```

### 2.5 Total costs (cost-type view)

```
total_costs_type = material_costs + personnel_costs + depreciation + other_costs
```

---

## 3. Cost centre accounting

Each line of cost type is allocated to one or more of the five cost centres.

| Cost centre        | Receives |
|--------------------|----------|
| **Purchasing**     | Purchasing-staff personnel, share of admin overhead, storage costs for materials |
| **Production**     | Production-staff personnel, all production-line depreciation, factory materials, maintenance, rationalisation, env. tech, overtime premium, rework, env. compliance |
| **R&D**            | R&D-staff personnel, ecology consulting, value-analysis consulting |
| **Sales**          | Sales-staff personnel, advertising, CI, market-research fee, transport, storage of finished goods |
| **Administration** | Administration-staff personnel, building depreciation, fixed admin contracts |

Some costs are split by *distribution keys* defined per scenario:

| Cost                | Distribution key                                   |
|---------------------|----------------------------------------------------|
| Building depreciation | 5/70/5/5/15 % (Purch/Prod/R&D/Sales/Admin)        |
| Administration overhead | by share of revenue per product               |
| Storage costs       | by physical location of inventory                  |

### 3.1 Direct vs overhead

For each cost centre, costs are further split into:

- **Direct costs** of a product (traceable: e.g., input materials for product P
  are a direct cost of P; R&D for product P is direct on P).
- **Overhead** of a cost centre (not directly traceable: e.g., administration
  staff salaries are overhead).

Distinguishing these is what makes contribution-margin analysis (§4) possible.

### 3.2 Cost of goods manufactured (CGM)

For each product *p*:

```
CGM(p) = direct_materials(p)                       // input + factory
       + direct_production_personnel(p)            // wages allocated to producing p
       + overhead_purchasing · key_purch(p)
       + overhead_production · key_prod(p)         // by units produced share
       + share_of_buildings_depreciation
       + share_of_other_production_other_costs
```

This is the per-unit value at which finished goods enter inventory.

### 3.3 Cost of goods sold (COGS)

```
COGS(p) = opening_finished_inventory_value
        + CGM(p) · units_produced
        − closing_finished_inventory_value
```

Or, equivalently:

```
COGS(p) = units_sold(p) · avg_unit_value
```

Both formulas reconcile because finished goods are valued at moving average.

### 3.4 Extraordinary items

Three sources of extraordinary income/expense:

| Event | Treatment |
|-------|-----------|
| **Production-line disinvestment** | Income = residual revenue (% of net book value, type-specific). Expense = full remaining depreciation booked at once. |
| **Discontinued product** (e.g., scrap Gen-1 inventory at Gen-2 launch) | Expense = remaining inventory value, booked once. |
| **One-off regulatory event** (scenario-set) | Income or expense as specified by the scenario period. |

---

## 4. Cost unit accounting and contribution margins

For each `(product, market, channel)` combination, build a tiered contribution
margin:

```
                                    Revenue
                                  − Direct material cost           (variable, per unit)
                                  − Direct production cost         (variable, per unit)
                                  − Transport cost                 (per unit, channel-specific)
                                  ────────────────────────────
                                  = Contribution Margin I (CM I)
                                  − Product-fixed material cost    (e.g., min order overhead)
                                  − Product-fixed production cost  (e.g., maintenance, line-specific)
                                  − Product-fixed sales cost       (advertising allocated to product)
                                  ────────────────────────────
                                  = Contribution Margin II (CM II)
                                  − Product-fixed R&D cost         (R&D allocated to product)
                                  ────────────────────────────
                                  = Contribution Margin III (CM III)
                                  − Company-fixed costs            (admin, building, etc.)
                                  ────────────────────────────
                                  = Contribution Margin IV (CM IV) = Operating income
```

Each CM is reported both in absolute terms (mEUR) and as percentage of revenue.
The MEUR view shows total profitability; the per-unit view (EUR/unit, with the
same tiering) shows where the product gains or loses money.

This tiered structure is the standard *Deckungsbeitragsrechnung* used widely in
German-language management education; equivalent in English-language texts to
"contribution costing" / "stepwise contribution margin" (Drury 2018; Bhimani et
al. 2019; sources §3).

---

## 5. Profit and Loss Statement

The P&L uses the **cost-of-sales method** (Umsatzkostenverfahren), which is the
most common presentation in IFRS and HGB practice:

```
Sales revenue
± Change in finished-goods inventory
+ Other operating income                     // disinvestment residuals, etc.
+ Own work capitalised                       // (zero in most periods)
− Material expenses
− Personnel costs
   ├── Wages and salaries
   ├── Hiring and dismissal costs
   ├── Pension reserve contribution
   └── Non-salary staff costs
− Depreciation                               // ordinary
− Other expenses
────────────────────────────
= Operating income (EBIT)
+ Investment income (from securities)
− Interest on short-term and long-term loans
− Interest on overdraft loan
────────────────────────────
= Earnings before tax (regular operations)
+ Extraordinary income
− Extraordinary expenses
────────────────────────────
= Earnings before tax
− Income tax (rate from scenario)
────────────────────────────
= Net income for the period
```

Tax: positive earnings taxed at the scenario rate (default 30 %). Losses carry
forward and offset future positive earnings before tax becomes payable.

---

## 6. Balance sheet (HGB §266 structure)

```
ASSETS                                LIABILITIES & EQUITY
────────────────                      ────────────────────
Fixed assets                          Equity
  Land and buildings                    Subscribed capital
  Production lines (net book val.)      Capital reserves
  Environmental tech.                   Retained earnings (P/L brought forward)
                                        Net income for period
Current assets
  Input materials                     Pension reserves
  Finished goods
  Trade receivables  (20 % of revenue) Liabilities
  Securities                            Long-term loans
  Cash                                  Short-term loans
                                        Overdraft loan
                                        Trade payables (zero in this model)

Total assets                          Total liabilities & equity
```

### 6.1 Required identities

These must hold exactly, period over period:

```
1. total_assets ≡ total_liabilities_and_equity
2. equity_end ≡ equity_start + net_income − dividends
3. retained_earnings_end ≡ retained_earnings_start + (net_income_prior − dividends_prior)
```

Identity 1 is checked at the end of each period; failure indicates a bug.

---

## 7. Cash flow statement

We use the **indirect method**: start from net income and adjust.

```
Operating activities
  Net income
  + Depreciation                           // ordinary + extraordinary
  + Increase in pension reserve
  ± Change in input-material inventory     // (decrease = source of cash)
  ± Change in finished-goods inventory
  ± Change in trade receivables            // (increase = use of cash)
────────────────────────────
= Operating cash flow

Investing activities
  − Purchase of production lines
  − Purchase of environmental tech.
  + Disinvestment residual revenue
  − Purchase of securities
  + Sale of securities (matures next period — receipts)
────────────────────────────
= Investing cash flow

Financing activities
  + Short-term loan drawdown
  − Short-term loan repayment
  + Long-term loan drawdown
  − Long-term loan repayment
  ± Overdraft change
  − Dividend paid                          // declared in prior period, paid this period
────────────────────────────
= Financing cash flow

Net change in cash = Operating + Investing + Financing
Cash_end = Cash_start + Net change in cash
```

### 7.1 Cash receipts and disbursements (direct cash account)

Reported separately for transparency (and to match the customer-payment-pattern
mechanic, see `00-overview.md` §4):

```
Cash in                                Cash out
  Sales receipts (80 % this period)      Material purchases
  Receivables collected (20 % prior)     Personnel costs (less pension reserve)
  Securities maturing                    Other operating expenses
  Investment income                      Loan repayments (short-term + overdraft)
  Disinvestment residual                 Production-line purchases
  Loans drawn                            Securities purchases
  (Extraordinary income)                 Environmental tech.
                                         Dividends (paid this period for prior decision)
                                         Tax
                                         Interest
                                         (Extraordinary expenses)
                                         (Auto-overdraft drawn if cash would fall below
                                          0.10 mEUR floor)
```

Total in − total out + opening cash = closing cash.

### 7.2 Auto-overdraft

If after all other cash movements `cash_balance < min_cash` (default 0.10 mEUR),
the engine automatically draws an overdraft loan to top up to the minimum.
Overdraft interest is the highest of the three loan rates (scenario param) and
is **always** repaid in full at the start of the next period before any other
financing activity.

---

## 8. Key derived ratios (for the executive summary and rating)

| Ratio                  | Formula                                          |
|------------------------|--------------------------------------------------|
| Return on equity (ROE) | `net_income / equity_start`                      |
| Return on sales (ROS)  | `operating_income / revenue`                     |
| Equity ratio           | `equity / total_assets`                          |
| Debt ratio             | `(short_term + long_term + overdraft) / total_assets` |
| Cash flow / debt       | `operating_cash_flow / total_debt`               |
| Interest coverage      | `EBIT / interest_paid`                           |
| Inventory turns        | `COGS / avg_finished_inventory_value`            |

These feed the **rating index** in `05-finance.md`, which in turn affects
next-period loan rates.

---

## 9. Reconciliation tests (Phase 1 acceptance criteria)

A canonical run of `solar-v1` for *N* periods must pass:

1. `assets[t] == liabilities_and_equity[t]` for every `t`, every company.
2. `equity[t] - equity[t-1] == net_income[t] - dividends_declared[t-1]` for every t, c.
3. `cash[t] - cash[t-1] == operating_cf[t] + investing_cf[t] + financing_cf[t]` for every t, c.
4. `sum_over_cost_centres(total) == sum_over_cost_types(total)` for every t, c.
5. `industry_report.total_revenue[t] == sum_c(revenue[t])` for every t.

These are golden-file tests; failure blocks engine release.

---

## 10. What's deliberately not here

- The full list of scenario-tunable rates and percentages → `scenarios/solar-v1/scenario.yaml`
- How depreciation interacts with disinvestment timing → `03-production.md`
- How taxes-loss-carryforward is implemented (an off-balance-sheet ledger) → `05-finance.md`
- Specific cost values (factory materials EUR/unit, hiring fees, etc.) → scenario pack
- How the engine writes report-bundle objects → `sim-engine/` (Phase 1)
