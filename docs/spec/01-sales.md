# 01 — Sales and Demand

> **Scope.** How market demand is generated, how it is allocated between competing
> companies, how channels (retail, bulk, tender) interact, and how customer
> satisfaction evolves. This document defines the formulas used in step 7 of the
> period loop.

---

## 1. Demand structure

For each `(period t, product p, market m)` triple, the total addressable demand
across all companies is:

```
M(t, p, m) = M_base(p, m) · g_eco(t) · g_segment(t, p, m) · price_anchor_factor(t, p, m)
```

Where:

- `M_base(p, m)` — the period-0 baseline market potential for product *p* on market
  *m* (set in the scenario pack).
- `g_eco(t)` — a macroeconomic multiplier for the period, set by the scenario
  (e.g., `1.05` in a growth period, `0.92` in a recession). Captures GDP and
  general consumer-investment sentiment.
- `g_segment(t, p, m)` — a product-segment growth multiplier (e.g., residential PV
  growing 8 %, utility-scale flat, balcony solar booming 40 %).
- `price_anchor_factor(t, p, m)` — sensitivity of total market size to the
  *industry average* price relative to a reference (separate from individual
  market-share competition; see §3). A simple form:

```
price_anchor_factor = (P_ref(p, m) / avg(P_c, p, m))^α_market
```

with `α_market` typically in the range `0.4–0.8` for industrial buyers (low
elasticity at the category level — buyers will still buy panels even if all
panels get 10 % more expensive, but they'll buy fewer). See sources §1.

The values `M_base`, `g_eco`, `g_segment`, `P_ref`, and `α_market` are all
scenario-supplied parameters.

---

## 2. Market share — the attraction model

Each company *c* offers product *p* on market *m* with a vector of marketing
instruments. We compute an **attractiveness score** `A(c)` per offering, and market
share is each company's share of total attractiveness. This is a *multinomial
attraction model* — the canonical demand-allocation model in quantitative marketing
(Lilien & Kotler 1983; Hanssens, Parsons, Schultz 2001; see sources §1).

### 2.1 Attractiveness components

```
A(c, p, m, t) = price_score(c)         ^ β_price
              · advertising_score(c)   ^ β_ad
              · salesforce_score(c)    ^ β_sf
              · product_score(c)       ^ β_prod
              · image_score(c)         ^ β_img
              · satisfaction_score(c)  ^ β_sat
```

All factors are dimensionless and ≥ 0. Each is built so that 1.0 = "exactly average
in the market for this period". The exponents `β` are sensitivity coefficients
(scenario-tunable; defaults in §6).

#### 2.1.1 Price score

```
price_score(c) = (avg_price(m, p) / P(c))^1
```

A company cheaper than the market average scores > 1, more expensive scores < 1.
The exponent `β_price` is the dominant lever in most consumer-PV markets — set
high (e.g., 2.0–3.0) so price moves market share visibly.

We **do not** use a kinked piecewise function. A smooth power function is closer
to empirical price-share research and is what makes the planning spreadsheet
useful (it has continuous derivatives, so teams can do "what if I cut 3 %?"
sensitivities).

#### 2.1.2 Advertising score

Diminishing returns relative to category benchmark:

```
e(c) = 1 − exp( − Ads(c) / Ads_ref(p, m) )
advertising_score(c) = e(c) / avg(e_c)
```

`Ads_ref` is the scenario-set "saturation reference" — the level above which extra
ad spend has little effect. For PV in the default scenario, `Ads_ref ≈ 12 mEUR`
for residential market 1.

#### 2.1.3 Sales-force score

Same diminishing-returns shape but with stronger long-run effects (sales relationships
persist):

```
s(c) = 1 − exp( − SF(c) / SF_ref(p, m) )
salesforce_score(c) = (s(c) / avg(s_c))^0.7 · carryover(c)
```

The 0.7 exponent dampens short-term competition (a 10 % swing in sales staff
doesn't immediately swing 10 % of market share). `carryover` is a slow-moving
factor reflecting that sales-force investments compound: it is a 3-period EMA of
the company's own `s(c)`, normalised. See sources §2 on long-run advertising and
sales-effort persistence.

#### 2.1.4 Product score

A weighted average of normalised product-attribute indices, each computed against
the cohort average for that period:

```
product_score(c) = (
    w_eff · (eff(c) / avg(eff_c))
  + w_sus · (sus(c) / avg(sus_c))
  + w_qly · (qly(c) / avg(qly_c))
)
```

with weights `w_eff + w_sus + w_qly = 1`. In `solar-v1`, residential consumers
weight efficiency 0.5, sustainability 0.3, and quality 0.2; utility-scale buyers
weight efficiency 0.7, sustainability 0.2, quality 0.1. The weights are set per
market segment in the scenario, not per product.

#### 2.1.5 Image score

```
image_score(c) = (image(c) / avg(image_c))^0.5
```

The image index evolves slowly (see §4). The exponent 0.5 dampens its
contribution — brand image matters, but not as much as price or product within a
period.

#### 2.1.6 Satisfaction score

```
satisfaction_score(c) = (sat(c) / avg(sat_c))^0.5
```

Customer satisfaction (§4) acts as a slow-moving multiplier. A company that
disappoints customers in *t-1* — by failing to deliver, raising prices sharply,
or shipping a worse product than promised — pays a satisfaction tax for several
periods.

### 2.2 Market share allocation

For each `(m, p)`, demand allocation across companies:

```
share(c) = A(c) / sum_c[A(c)]
demand(c) = M(t, p, m) · share(c)
```

Demand here is *demand observed* — the customer wants this many units. Whether the
company can supply them is settled next (§3).

---

## 3. Channels and supply allocation

Each company's finished-goods inventory is allocated across **channels** in a
fixed priority order:

| Priority | Channel              | Notes |
|----------|----------------------|-------|
| 1        | Won tenders          | Bidding decisions in *t-1* settled in *t*; bid won must be supplied this period. No transport cost. |
| 2        | Bulk buyers          | A scenario-published offer (max units × fixed price). Company can accept any amount up to max. No transport cost. |
| 3        | Retail market 1      | Domestic; transport cost per unit applies. |
| 4        | Retail market 2      | Export; higher transport cost; FX conversion applies. |

If `supply < demand` for a retail market: the company *under-supplies*. Up to
`spillover_fraction` (scenario param, default 0.80) of the unmet demand is
redistributed to other companies in the same market in proportion to their
existing share. (This redistribution does not cascade — once redistributed, any
remaining unmet demand is lost.)

If `supply > demand`: the excess remains as finished-goods inventory and accrues
storage cost (§5 in `06-accounting.md`).

### 3.1 Tender resolution

Each period the scenario publishes zero or more tenders, each with:

- `units_required`
- `max_acceptable_price` (often the retail price in market 1)

Each company may submit a bid `(units, price)`. The lowest bidder wins (if tied,
the company with the higher product score wins). Won tenders are *commitments* —
they pre-empt retail in the **next** period. Tender revenue is realised in the
period of delivery, not bid.

### 3.2 Bulk-buyer resolution

Bulk-buyer offers are non-competitive: every company can accept independently, up
to the per-company maximum. Acceptance is part of the period's decision.

---

## 4. Slow-moving indices

Three indices evolve gradually across periods, capturing brand and customer
relationship dynamics. All three are normalised so 100 = neutral.

### 4.1 Customer satisfaction `sat(c)`

```
Δsat = (
    + δ_supply    · supplied_fraction_prev          // could you deliver?
    − δ_price     · max(0, price_increase_pct)      // did you raise prices?
    + δ_ppr       · (product_score − image_score)   // value for money
    + δ_image     · (image_score − 1)               // brand confidence
)
sat(c, t) = clip( sat(c, t-1) + Δsat · σ_sat, 50, 150 )
```

Where `σ_sat` is a smoothing factor (≈ 5 index points per period), and `δ_*` are
weights (default 1.0 each). The clip keeps the index in a reasonable range.

### 4.2 Corporate image `image(c)`

Driven mainly by corporate-identity spend (see decision schema) and ecological
performance:

```
Δimage = ε_ci · ((CI_spend / CI_ref) − 1) + ε_eco · ((env_index − 1))
image(c, t) = clip( image(c, t-1) + Δimage · σ_img, 50, 150 )
```

CI spend is a discretionary marketing-mix decision; `env_index` comes from the
production module (`03-production.md`).

### 4.3 Loyalty/old-equipment penalty

If a company has not refreshed its product line in *n* periods, retail buyers
gradually shift to competitors offering newer generations. Implemented as a
shadow penalty on `product_score` proportional to the average age of the
product's installed base in the cohort.

---

## 5. Market research report

A team can purchase a market-research report each period (cost: `MR_cost`,
default 100 000 EUR). When purchased, the team's period report includes
competitor decisions disclosed at the published level:

- All competitors' prices per market × product
- All competitors' advertising and sales-force levels
- Aggregate units sold per competitor per market
- Industry-average prices and total market sizes

Without the report, only the *industry report* fields are visible (see
`00-overview.md` §6).

---

## 6. Default coefficients (solar-v1)

Initial values, to be calibrated during pilot runs. All in the scenario pack.

| Symbol            | Default      | Where set                          |
|-------------------|--------------|------------------------------------|
| `α_market`        | 0.6          | per market in `scenario.yaml`      |
| `β_price`         | 2.5          | per market segment                 |
| `β_ad`            | 0.7          | per market segment                 |
| `β_sf`            | 0.5          | per market segment                 |
| `β_prod`          | 1.2          | per market segment                 |
| `β_img`           | 0.5          | global                             |
| `β_sat`           | 0.5          | global                             |
| `w_eff:w_sus:w_qly` (residential) | 0.5 / 0.3 / 0.2 | per market |
| `w_eff:w_sus:w_qly` (utility)     | 0.7 / 0.2 / 0.1 | per market |
| `Ads_ref` (residential M1)        | 12 mEUR      | per market         |
| `SF_ref` (residential M1)         | 200 staff    | per market         |
| `CI_ref`                          | 3 mEUR       | global             |
| `MR_cost`                         | 100 000 EUR  | global             |
| `spillover_fraction`              | 0.80         | per market         |
| `δ_supply, δ_price, δ_ppr, δ_image` | 1.0 each  | global             |
| `σ_sat, σ_img`                    | 5 / 3        | global             |

The numerical defaults are *educated starting points*; they will be tuned during
the pilot so that the simulation produces realistic outcomes (e.g., a 5 % price
cut yields ≈ 10–15 % share gain for one company, ceteris paribus). Calibration
procedure documented in `docs/calibration.md` once Phase 6 begins.

---

## 7. Worked example (illustrative)

Three companies sell residential panels on market 1. Period 1.

| Variable                       | C1     | C2     | C3     |
|--------------------------------|--------|--------|--------|
| Price (EUR/unit)               | 310    | 305    | 320    |
| Advertising (mEUR)             | 8      | 10     | 7      |
| Sales force (staff)            | 200    | 220    | 180    |
| Efficiency index               | 102    | 105    | 100    |
| Sustainability index           | 105    | 100    | 102    |
| Quality index                  | 100    | 100    | 100    |
| Image                          | 100    | 100    | 100    |
| Satisfaction                   | 100    | 100    | 100    |

Industry averages: price 311.67, eff 102.33, sus 102.33, qly 100.

Compute `A(C1)`:

```
price_score    = (311.67 / 310)^2.5            = 1.0134
ads_score      = (1 - e^(-8/12)) / avg(...)    ≈ 1.014  (close to average)
sf_score       = ...
product_score  = 0.5·(102/102.33) + 0.3·(105/102.33) + 0.2·(100/100)
               = 0.5·0.9968 + 0.3·1.0261 + 0.2·1.0 = 1.0064
                 ^1.2 = 1.0077
image_score    = 1.0;  satisfaction_score = 1.0

A(C1) = 1.0134 · 1.014 · sf · 1.0077 · 1.0 · 1.0
```

Similar for C2 and C3, then divide by the sum. The team's `Decisions` page in the
planning spreadsheet (and later the Streamlit app) will let them play "what if I
nudge price by 1 %?" and see the share response live — this is the whole reason
the math is smooth and side-effect-free.

---

## 8. What's deliberately not here

- **R&D index dynamics** (how `efficiency`, `sustainability`, `quality` evolve from
  R&D spend) → `02-rnd.md`
- **Productivity and motivation** (which affect actual production, not demand) →
  `04-hr.md`
- **Cost of finished goods, contribution margins** → `06-accounting.md`
- **Specific solar-industry product definitions, market sizes, price points** →
  `scenarios/solar-v1/scenario.yaml`
- **Sources** for every formula and parameter family → `docs/sources.md`
