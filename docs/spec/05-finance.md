# 05 — Finance

> **Scope.** Loans (short-term, long-term, overdraft), securities, taxation
> with loss carryforward, dividend declaration and payment timing, credit
> rating, share-price model. The cash-flow articulation itself is in
> `06-accounting.md` §7; this module defines the *inputs* to that
> articulation.

---

## 1. Loans

### 1.1 Short-term loans

- Term: 1 period
- Interest accrues and is paid in the period of drawdown
- Principal repaid at the start of the following period
- Rate: scenario period rate × rating-based surcharge (§4)
- No prepayment penalty (you can just not roll it over)

Interest base:

```
interest_short_term(t) = principal_short_term(t) · rate_short_term(t)
```

If the principal exceeds the company's equity, a **stepwise surcharge** applies
to the excess:

```
if principal ≤ equity:            rate = base_rate
elif principal ≤ 2 · equity:      rate on excess = base_rate + 2 %
else:                              rate on excess = base_rate + 4 %
```

The surcharge applies only to the *fraction* above the threshold, not to the
whole loan.

### 1.2 Long-term loans

- Term: 10 periods (scenario-configurable)
- Interest accrues and is paid in each period of the loan's life
- Principal repaid in **full** at end of term (bullet maturity)
- Rate: scenario period rate × rating-based surcharge — but the rate of an
  existing long-term loan is **floating**: re-priced each period based on
  the new scenario rate and the company's current rating
- No prepayment

Reason for floating: it makes the rating-driven discipline visible. A team
that lets its rating slide pays more on existing debt, not just on new debt.

### 1.3 Overdraft

- Auto-drawn when cash would fall below `min_cash` (scenario, default 100 000 EUR)
- Term: 1 period
- Interest paid in period of drawdown
- Principal repaid at the **start** of next period, ahead of any other
  financing activity
- Rate: the highest of the three (scenario, default 13 %), with surcharge
  for poor rating

The overdraft is the "involuntary financing" — it costs more, signals
rating risk, and forces the team to plan cash. Heavy overdraft use in *t-1*
drops the rating in *t* (§4).

### 1.4 Cumulative interest

```
total_interest(t) = interest_short_term(t)
                  + interest_long_term(t)        // all outstanding LT loans
                  + interest_overdraft(t)
```

Reported in the P&L under financial expenses.

---

## 2. Securities

A simple cash-management instrument. The team can purchase fixed-income
securities with surplus cash:

- Term: 1 period
- Interest credited *in the period of purchase*
- Principal returned in the *following* period
- Rate: scenario period rate (default 3 %)

```
interest_securities(t) = securities_purchased(t) · rate_securities(t)
```

Securities are an alternative to keeping cash idle. They have no risk in
the model (the issuer is implicitly the central bank), so the rate is low.

---

## 3. Taxation

A flat corporate tax rate (default 30 %, scenario-configurable). Applied to
earnings before tax (positive only — losses are not refundable).

### 3.1 Tax-loss carryforward

A side ledger:

```
opening_loss_carryforward(t)
+ max(0, − earnings_before_tax(t))            // negative EBT adds to the pile
− min(loss_carryforward, earnings_before_tax(t))   // positive EBT consumes the pile
= closing_loss_carryforward(t)
```

The taxable amount is `max(0, earnings_before_tax − loss_carryforward)`.
Tax is paid in the current period (the simulation does not model deferred
tax — too much accounting overhead for the pedagogical gain).

There is no expiry on losses carried forward in this model.

---

## 4. Credit rating

A multi-factor score, 0–100. The rating index is **not** a magnitude visible
to teams; only a categorical level is (AAA, AA, A, BBB, BB, B, CCC, CC, C, D).
The numeric mapping is internal.

### 4.1 Rating components

Each component is a 0–100 normalised score; the composite is a weighted
average:

```
rating = (
    w_eq      · score(equity_ratio)
  + w_eqabs   · score(equity_absolute)
  + w_cf     · score(free_cash_flow_over_debt)
  + w_od     · score(overdraft_severity)
  + w_sat    · score(customer_satisfaction)
  + w_mot    · score(motivation_index)
  + w_ocf    · score(operating_cash_flow_over_debt)
  + w_inc    · score(net_income_trend)
  + w_plan   · score(planning_quality)
  + w_prod   · score(productivity_total)
  + w_tech   · score(efficiency_index_vs_industry)
)
```

with weights summing to 1.0.

Default weights (calibrated so that financial-ratio drivers dominate but
operational discipline matters):

| Symbol     | Default | Component                                |
|------------|---------|------------------------------------------|
| `w_eq`     | 0.18    | Equity ratio                             |
| `w_eqabs`  | 0.10    | Absolute equity                          |
| `w_cf`     | 0.10    | Free cash flow / total debt              |
| `w_od`     | 0.08    | Overdraft as % of equity (penalty)       |
| `w_sat`    | 0.06    | Customer satisfaction index              |
| `w_mot`    | 0.06    | Motivation index                         |
| `w_ocf`    | 0.10    | Operating CF / total debt                |
| `w_inc`    | 0.10    | Net income 3-period EMA                  |
| `w_plan`   | 0.08    | Planning quality 3-period EMA            |
| `w_prod`   | 0.08    | (Index I × Index II) for production      |
| `w_tech`   | 0.06    | Best product efficiency vs industry avg  |

This composite structure echoes Altman's Z-score (sources §6) but is
broader — it incorporates operational and customer-experience drivers that
modern credit agencies factor in (Moody's, S&P methodology papers cite
similar non-financial components).

### 4.2 Rating → interest-rate surcharge

```
score   surcharge        category
  90+   −1.0 % (discount)  AAA / AA
  80    −0.5 %             A
  70     0.0 %             BBB    ← reference
  60    +1.0 %             BB
  50    +2.0 %             B
  40    +3.5 %             CCC
  30    +5.0 %             CC
  20    +7.0 %             C
   0   +10.0 %             D   (effectively no new loans)
```

Surcharge applies on top of the scenario base rate for that loan type, and
on top of the equity-based stepwise surcharge for short-term loans (§1.1).
Interpolated linearly between rows.

### 4.3 Initial rating

Period 0: 87 (in the AA range, per the inherited scenario state). Teams can
move it up or down based on their decisions.

---

## 5. Share price

A weighted sum of value drivers, normalised so that period-0 share price
matches the scenario constant (default 113.8 EUR/share, with 500 000 shares
outstanding).

```
share_price(t) = β_0
               + β_eq    · equity_growth(t)
               + β_inc   · net_income_normalised(t)
               + β_div   · dividend_yield(t)
               + β_cdiv  · cumulative_dividends_normalised(t)
               + β_ros   · return_on_sales(t)
               + β_mkt   · cumulative_marketing_spend_normalised(t)
               + β_diversity · number_of_products_markets(t)
               + β_image · image_index_normalised(t)
               + β_rel   · sales_vs_competitors(t)
               + β_plan  · planning_quality(t)
               + β_eco   · ecology_index_normalised(t)
               − β_debt  · debt_equity_ratio(t)
               + β_tech  · cumulative_rnd_normalised(t)
               + β_prod  · productivity_total(t)
```

The exact `β` coefficients are calibrated so that:

1. A baseline period (no big moves) keeps the share price roughly flat.
2. A breakout strategy (top-quartile across 3+ drivers) yields ≈ 20–30 %
   share-price growth per period.
3. A failing strategy (bottom-quartile across 3+ drivers, especially equity
   and rating) yields ≈ 20–30 % decline.

This is **not** an attempt at a valuation model. It is a teaching device
that makes the link between management decisions and shareholder value
legible. Sources §6 cites the literature on intangibles-and-valuation; the
caveats are documented in `docs/sources.md`.

### 5.1 Shareholder earnings

A separate cumulative measure for the executive summary:

```
shareholder_earnings(t) = (share_price(t) − share_price(0)) · shares_outstanding
                        + cumulative_dividends_paid
```

---

## 6. Dividends

The team's `finance.dividend` decision in period *t* declares a dividend.
Declared dividends:

- Are subtracted from retained earnings at the end of period *t*
- Are paid out in cash at the start of period *t+1*
- The maximum declarable in *t* is the cumulative profit available
  (retained earnings + period *t* net income)
- Positive declared dividends push share price up (the β_div term, §5)
- If the company has insufficient cash, the dividend is financed by
  drawdown (auto-overdraft, with the usual rating penalty)

### 6.1 Why the timing matters

The "declare now, pay next period" pattern matches how real annual
dividends work (declared after the financial year ends; paid in the
following months). The simulation enforces this so that students learn the
cash-flow timing of distributions.

---

## 7. Pension reserve

A simple defined-benefit-style reserve. Each period:

```
pension_contribution(t) = wages_salaries(t) · pension_reserve_pct(t)
pension_reserve(t) = pension_reserve(t-1) + pension_contribution(t)
```

The contribution is an *expense* on the P&L. The reserve sits on the
balance sheet as a non-cash liability — it builds up but is not paid out
during the simulation. Period 0: 13.86 mEUR (per the inherited scenario).

Scenarios can step the `pension_reserve_pct` mid-game (e.g., a regulatory
change from 5 % → 6 %).

---

## 8. Foreign exchange

When the company sells in market 2 (denominated in the foreign currency):

```
revenue_in_base = revenue_in_foreign · fx_rate(t)
```

The FX rate is set per period in the scenario events. Receivables from
prior-period market-2 sales are converted at the *current* rate, not the
historical rate (a simplification — no FX hedging in this model).

Costs of materials/labour for market-2-bound production are in the base
currency. The company's market-2 contribution margin is therefore exposed
to FX risk.

---

## 9. Period-zero finance state (solar-v1)

| Quantity                 | Value         |
|--------------------------|---------------|
| Cash                     | 0             |
| Securities               | 0             |
| Short-term loan          | 27 000 000    |
| Long-term loan           | 0             |
| Overdraft                | 0             |
| Pension reserve          | 13 860 000    |
| Subscribed capital       | 15 000 000    |
| Capital reserves         | 2 500 000     |
| Retained earnings        | 12 500 000    |
| Prior-period net income  | 3 770 000     |
| Last dividend            | 1 000 000     |
| Receivables from prior   | 7 500 000     |
| Share price              | 113.8 EUR     |
| Shares outstanding       | 500 000       |
| Rating                   | 87 (AA range) |

---

## 10. Default coefficients summary

| Symbol                       | Default              |
|------------------------------|----------------------|
| `min_cash`                   | 100 000 EUR          |
| `tax_rate`                   | 0.30                 |
| `pension_reserve_pct`        | 0.05                 |
| `payment_in_period_pct`      | 0.80                 |
| short-term surcharge step    | +2 %, +4 % on excess |
| Securities rate              | 0.03                 |

Rating component weights and share-price `β` coefficients — see §4.1 and §5
respectively; both calibrated during pilot.

---

## 11. What's deliberately not here

- Cash-flow articulation itself → `06-accounting.md` §7
- Auto-overdraft trigger logic → `06-accounting.md` §7.2
- Reception of sales revenue (80/20 split) → `06-accounting.md` §7.1
- Wage and salary tables → scenario pack `world.hr` and period events
- Currency definitions and FX schedules → scenario pack `markets[].currency`
  and `period-events.yaml`
