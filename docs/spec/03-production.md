# 03 — Production

> **Scope.** Production lines, the capacity-laddering computation, depreciation,
> rationalisation, environmental damage indicator, rework. This module decides
> *how much can physically be produced* in a period. Decisions about the
> production *staff* live in `04-hr.md`; the two interact at one specific point
> (overtime).

---

## 1. Production lines

A company owns *production lines*. Each line has:

| Attribute              | Set at … |
|------------------------|----------|
| `id`                   | acquisition |
| `type`                 | acquisition — references a row in the scenario's line catalog |
| `acquisition_period`   | acquisition |
| `purchase_value`       | acquisition |
| `normal_capacity`      | acquisition — units per period at full availability |
| `useful_life`          | acquisition |
| `remaining_life`       | rolled forward each period |
| `other_fixed_cost`     | acquisition — overhead per period independent of utilisation |
| `environmental_index`  | acquisition — affects the company's environmental damage indicator |
| `cumulative_rationalisation` | rolling — every rationalisation euro accrues here |

Line types are scenario-defined (in `solar-v1`: `stringer_v1`, `laminator_v2`,
`fullauto_v3` — see `scenario.yaml`). A team can buy up to
`max_purchase_per_period` lines of any one type per period (default 9).

### 1.1 Acquisition

When a team submits a `production.lines.invest` decision for `n` lines of
type *T*:

```
for k in 1..n:
    new_line = ProductionLine(
        id = generate_line_id(company, period, type, k),
        type = T,
        acquisition_period = current_period,
        purchase_value = T.purchase_price,                 // from catalog
        normal_capacity = T.normal_capacity,
        useful_life = T.useful_life,
        remaining_life = T.useful_life,
        other_fixed_cost = T.other_fixed_cost,
        environmental_index = T.environmental_index,
        cumulative_rationalisation = 0,
    )
    company.lines.append(new_line)

company.cash -= n · T.purchase_price                       // paid in full this period
```

New lines are **immediately available** for production in the same period.

### 1.2 Depreciation

Straight-line over `useful_life`:

```
depreciation_per_period(line) = line.purchase_value / line.useful_life
net_book_value(line)         = line.purchase_value · (line.remaining_life / line.useful_life)
```

At the end of every period, `remaining_life -= 1`. A line with
`remaining_life == 0` is **fully depreciated** but **still usable** for
production (matches industry practice — a paid-off machine still runs). Its
depreciation contribution drops to zero.

### 1.3 Disinvestment

A team can disinvest a line by listing its `id` in `production.lines.disinvest`:

```
proceeds = line.net_book_value · type.residual_revenue_pct   // e.g. 20% for v1
                                                              //      25% for v2
                                                              //      30% for v3
extraordinary_expense = line.net_book_value                   // booked at once
extraordinary_income  = proceeds                              // immediate cash
company.cash += proceeds
company.lines.remove(line)
```

The net P&L effect is `proceeds − net_book_value`, almost always negative. The
extraordinary income and expense appear separately in the P&L (see
`06-accounting.md` §5). Limit: at most 3 disinvestments of the same type per
period.

---

## 2. Capacity laddering — available capacity I → II → III

The available capacity in a period is built up in three stages from each
line's normal capacity:

```
Available Capacity I  =  Σ_lines normal_capacity(line) · availability_factor(line)
Available Capacity II =  Available Capacity I · rationalisation_factor(line_type)
Available Capacity III=  Available Capacity II · overtime_factor
```

These are the three "rungs" — each one corresponds to a different lever the
team can pull. Their structure mirrors the canonical TOC / capacity-management
framework taught in any operations textbook (Heizer & Render 2017; Slack &
Brandon-Jones 2018 — see sources §3 addenda).

### 2.1 Available Capacity I — maintenance

The team's `production.lines.maintenance` decision specifies a maintenance
spend **per line type** (not per individual line). All lines of a type share
the same maintenance budget per line.

The maintenance table (in the scenario) gives `availability_factor` as a
function of spend per line. Interpolated linearly between rows; clipped to
the lowest and highest rows.

In `solar-v1` defaults:

| Spend / line / period | Availability |
|-----------------------|--------------|
| 100 000 EUR (minimum) | 50 %         |
| 500 000 EUR           | 70 %         |
| 700 000 EUR           | 80 %         |
| 1 000 000 EUR         | 95 %         |
| 1 500 000 EUR         | 97 %         |
| 3 000 000 EUR         | 99 %         |
| 4 000 000 EUR         | 100 %        |

If no maintenance decision is submitted for a type, the engine defaults to
the *minimum* spend (100 000 EUR). This costs you 50 % capacity, deliberately
— students learn the hard way that maintenance is not optional.

### 2.2 Available Capacity II — rationalisation

Rationalisation is a cumulative R&D-like investment in the production
process. The `production.lines.rationalisation` decision specifies a spend
per line type. The spend is **expensed** in the period (not capitalised) but
its effect persists: future periods enjoy the same rationalisation factor
until the team adds more.

```
cumulative_rationalisation[type] += rationalisation_spend[type]

rationalisation_factor[type] = 1 + R_K · log(1 + cumulative_rationalisation[type] / R_ref)
```

Defaults: `R_K = 0.10`, `R_ref = 5 mEUR`. At 5 mEUR cumulative, factor ≈ 1.07.

Rationalisation is **per type**, not per line — buying a new line of an
already-rationalised type instantly gives the new line the type's
rationalisation factor.

### 2.3 Available Capacity III — overtime

If `Available Capacity II < target production volume`, the engine
automatically schedules overtime up to `overtime_max_pct` (default 10 %). The
overtime factor is therefore decided by the math, not the team:

```
shortfall = target_volume − Available Capacity II
overtime_factor = 1 + min(overtime_max_pct, shortfall / Available Capacity II)
Available Capacity III = Available Capacity II · overtime_factor
```

If even with maximum overtime the capacity is insufficient, the company is
**capacity-bound**: actual production = Available Capacity III, and the
shortfall vs target shows up in the inventory and sales modules as
under-supply.

Overtime triggers (the moment overtime > 0):

- A one-off **step fixed cost** (default 500 000 EUR for supervision and
  utility overhead) is added to other costs.
- A **wage premium** (default +25 %) is added to production-staff wages for
  the overtime hours only.

These are scenario-tunable; the default 0.5 mEUR step cost is deliberately
gentler than the 2.5 mEUR found in some commercial sims, on the theory that
modern factories incur less marginal supervision cost.

---

## 3. Required capacity (the demand side of the capacity equation)

Each product specifies `capacity_per_line_unit` — how many capacity units
are consumed per finished unit. For simple panels this is 1.0; for a more
complex product (e.g., battery storage) the scenario can set it to 2.0 or
similar to model that batteries take twice as long on a panel line.

```
required_capacity = Σ_p production_volume(p) · capacity_per_line_unit(p)
```

The engine compares this with Available Capacity III. If required exceeds
available, the company is capacity-bound (above).

### 3.1 Required staff

The other half of "can we produce X?" — the production staff requirement.
Decided in HR (`04-hr.md` §3); the engine reconciles both constraints
simultaneously in step 5 of the period loop (see `00-overview.md`).

---

## 4. Material consumption

### 4.1 Input materials (with value analysis)

For each product produced:

```
input_material_units_needed(p) = production_volume(p) · 100 / value_analysis_index(p)
```

A value-analysis index above 100 saves material; below 100 wastes more. The
team must have ordered enough input material:

```
if input_material_units_needed(p) > inventory_units_available(p):
    shortage = input_material_units_needed(p) − inventory_units_available(p)
    # Auto-procured via express delivery at a premium
    express_cost_per_unit = standard_tier_price_at_volume(...) · (1 + express_premium)
    # express_premium default = 0.20 (i.e. +20 %)
```

The express premium is a scenario constant.

### 4.2 Factory materials

Per-unit consumable cost (`factory_material_cost_per_unit` from the
scenario). These are auto-procured and always available; treat as a direct
production cost.

---

## 5. Production output

For each company, after capacity and staff constraints:

```
producible(p) = min(
    target_volume(p),
    capacity_available_for(p),       // share of capacity III allocated to p
    staff_available_for(p),          // share of staff allocated to p
)

units_produced(p) = producible(p)
```

If `units_produced(p) < target_volume(p)`, the company is **production-bound**,
and finished-goods supply for that product will be lower than planned. The
team's submitted plan in the period appears in the planning-quality scoring
as a *negative deviation*.

### 5.1 Allocation of shared capacity across multiple products

When a company produces multiple products on shared lines, capacity is
allocated **in proportion to each product's `target_volume` weighted by
`capacity_per_line_unit`**. This is a deliberate design choice: it gives
teams a meaningful capacity-mix decision. If two products compete for the
same lines and capacity is tight, the team should plan accordingly.

---

## 6. Environmental damage indicator

A composite index measuring the environmental impact of the company's
production:

```
environmental_damage_indicator =
    weighted_average(line.environmental_index, weight=line.normal_capacity)
  + environmental_tech_bonus
```

Where `environmental_tech_bonus` ("abatement") is a function of the **net
book value** of end-of-pipe environmental tech — linear, with a cap:

```
environmental_tech_bonus = min(
    ENV_ABATEMENT_CAP,
    environmental_tech_nbv / ENV_ABATEMENT_COST_PER_POINT
)
```

Defaults: `ENV_ABATEMENT_COST_PER_POINT = 1 mEUR` per index point,
`ENV_ABATEMENT_CAP = 20` points. NBV is used rather than cumulative capex
so the bonus *fades as the equipment depreciates* — a company must keep
reinvesting to hold its abatement, which makes env-tech a recurring
decision rather than a one-off.

### 6.1 Compliance threshold

The scenario sets `environmental_compliance_baseline` (default 100). If
`environmental_damage_indicator < baseline`, the company pays a penalty:

```
penalty = (baseline − indicator) · environmental_penalty_per_index_point
```

This penalty is an *other expense* allocated to the production cost centre.

### 6.2 Environmental tech investment

The `production.environmental_capex` decision purchases end-of-pipe
abatement (filters, scrubbers, waste-heat recovery, etc.). Capitalised on
the balance sheet and depreciated straight-line over 10 periods.

Environmental tech is **separate from** the per-line environmental index.
Buying a cleaner production line raises the average index (production
lines' own `environmental_index`); env-tech investment is a *bonus* on top
of whatever lines you have.

---

## 7. Rework

Production defects incur rework expense. A simple model:

```
rework_cost(p) = R_base
              · units_produced(p)
              · (1 + R_tech · max(0, eff_index(p) − 100) / 100)
              · (1 + R_val  · max(0, val_index(p) − 100) / 100)
              · (1 − R_mot  · max(0, motivation_index − 100) / 100)
              · (1 − R_nsc  · (non_salary_pct − non_salary_pct_min))
```

Higher tech / value-analysis indices *increase* rework (more complex
products are harder to assemble defect-free). Higher motivation and higher
non-salary staff costs *decrease* rework.

Defaults: `R_base = 30 EUR/unit`, `R_tech = 0.4`, `R_val = 0.3`, `R_mot = 0.3`,
`R_nsc = 0.5`.

Rework is an *other cost* in the cost-type accounting and allocates to the
production cost centre.

---

## 8. Default coefficients summary

| Symbol                       | Default        | Where set        |
|------------------------------|----------------|-------------------|
| `overtime_max_pct`           | 0.10           | world             |
| `overtime_step_fixed_cost`   | 500 000 EUR    | world             |
| `overtime_wage_premium_pct`  | 0.25           | world             |
| `R_K` (rationalisation)      | 0.10           | global            |
| `R_ref` (rationalisation)    | 5 000 000 EUR  | global            |
| `express_premium`            | 0.20           | global            |
| `E_K` (env. tech)            | 8              | global            |
| `E_ref` (env. tech)          | 5 000 000 EUR  | global            |
| `R_base` (rework)            | 30 EUR/unit    | global            |
| `R_tech`, `R_val`            | 0.4, 0.3       | global            |
| `R_mot`, `R_nsc`             | 0.3, 0.5       | global            |
| `environmental_penalty_per_index_point` | 150 000 EUR | scenario |

---

## 9. What's deliberately not here

- Production-staff workforce and productivity → `04-hr.md`
- Cost-of-goods-manufactured assembly and storage costs → `06-accounting.md`
- Line type catalog (capacities, prices, env indices) → scenario pack
- Maintenance table → scenario pack
- Per-product factory material costs and capacity-per-unit → scenario pack
