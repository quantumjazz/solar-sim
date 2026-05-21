# 02 — Research & Development

> **Scope.** How the three product attribute indices — *efficiency*,
> *sustainability*, *value-analysis* — evolve from R&D spend, and how they
> couple into the sales (`01`), production (`03`), and HR (`04`) modules.

---

## 1. Index conceptual model

Each product carries three normalised indices. All are dimensionless; **100** =
neutral starting baseline; higher is better.

| Index               | What it represents (solar-PV scenario)                                  | Affected by                              |
|---------------------|--------------------------------------------------------------------------|------------------------------------------|
| **Efficiency**      | Module conversion efficiency, copy speed-equivalent, throughput, etc.    | R&D headcount on the product             |
| **Sustainability**  | Embodied carbon, recyclability, energy payback time                      | Sustainability-consulting spend          |
| **Value-analysis**  | Bill-of-materials cost-down — fewer or cheaper materials per unit        | Value-analysis-consulting spend          |

Each operates on the same dynamic skeleton (§2) with index-specific
coefficients. The three indices are partially substitutable but not entirely:
a team can't trade all of efficiency for all of sustainability without losing
market share, because retail customers weight them differently (see
`01-sales.md` §2.1.4).

---

## 2. Index dynamics — the general form

For each product *p* and each index *i ∈ {eff, sus, val}*:

```
index_p_i(t) = index_p_i(t-1) · (1 − decay_i)             // forgetting / competition catching up
             + gain_i( spend_p_i(t) )                     // benefit from this period's investment
             − adjustment_i(t)                            // scenario shocks (regulatory tightening, etc.)
```

The form of `gain_i(.)` is a **diminishing-returns log function**:

```
gain_i(spend) = K_i · log(1 + spend / spend_ref_i)
```

where:

- `K_i` is the *marginal index gain at the reference spend* (scenario-set)
- `spend_ref_i` is the reference investment level

This shape matches public empirical findings on R&D-to-productivity returns
(Mansfield 1965; Griliches 1979; Hall & Lerner 2010 — see sources §2.1
addenda below). The diminishing returns reflect saturation: each additional
euro buys less marginal index than the previous one.

### 2.1 Adjustment terms (scenario events)

Scenario events can apply a one-time or persistent `adjustment_i(t)`. Two
typical patterns from solar-v1:

| Event                                     | Effect |
|-------------------------------------------|--------|
| New environmental regulation (period 5)   | One-time `−15` to every company's sustainability index |
| Major industry breakthrough (technology shift) | Decay rate doubled for one period — competitors who don't invest fall faster |

These are not silent; the scenario reports the event in narrative and the
adjustment is visible in the post-period report.

---

## 3. Per-index particulars

### 3.1 Efficiency

R&D headcount is the input, not direct euro spend, because it changes the
shape of the personnel cost and links to HR mechanics.

```
spend_eff_p(t) = researchers_p(t) · salary_rnd(t) · (1 + non_salary_pct(t))
```

Where `researchers_p(t)` is the team's decision and `salary_rnd(t)` comes from
the scenario period.

Default coefficients:

| Symbol           | Default value | Notes |
|------------------|---------------|-------|
| `K_eff`          | 7.0 index points / period | At ref spend, gain ≈ 4.9 index points |
| `spend_ref_eff`  | 7.0 mEUR      | Roughly 100–150 researchers at €50k loaded cost |
| `decay_eff`      | 0.01 / period | Competition closes a 1 % gap per period if you stand still |

A team investing **at the reference level every period** holds index steady;
investing more makes it climb; investing less makes it slip.

### 3.2 Sustainability

Driven by external consulting spend rather than headcount, because
sustainability work at the BOM and process level is typically outsourced to
specialised consultancies.

```
spend_sus_p(t) = sustainability_spend_p(t)
```

| Symbol           | Default value | Notes |
|------------------|---------------|-------|
| `K_sus`          | 6.0           | |
| `spend_ref_sus`  | 4.0 mEUR      | |
| `decay_sus`      | 0.01 / period | |

### 3.3 Value-analysis

Same shape as sustainability, but its index has a *production* effect, not a
*sales* effect. A higher value-analysis index reduces the amount of input
material required per finished unit. See `03-production.md` §4.1.

```
input_material_units(p, t) = production_volume(p, t) · 100 / value_analysis_index(p, t)
```

So a value-analysis index of 110 means 100 units of input material yield 110
units of finished product — a 10 % material saving.

| Symbol           | Default value | Notes |
|------------------|---------------|-------|
| `K_val`          | 4.0           | More restrained — too generous makes the index dominate |
| `spend_ref_val`  | 2.0 mEUR      | |
| `decay_val`      | 0.01 / period | |

The smaller `K_val` is deliberate: value-analysis has powerful compounding
effects through reduced material costs, so its gain function is more
conservative than the other two.

---

## 4. Multi-product R&D

When a team manages more than one product (e.g., panel_gen1 *and*
panel_gen2 in period 4+), R&D spend is **per product**. There is no shared
"company R&D" pool that benefits both products at once.

Researcher headcount is decided per product. The engine sums per-product
headcounts to determine total R&D cost-centre headcount; any difference from
the prior period is realised as hires/dismissals in the R&D cost centre, with
the standard hiring/dismissal cost treatment (see `04-hr.md`).

### 4.1 Reshuffles

Moving researchers from product *A* to product *B* (when both belong to the
team's portfolio) is **not** counted as a dismissal-and-rehire. This is a
critical pedagogical point: teams should be free to redirect R&D effort
without artificial cost penalties. The engine implements this by computing
hires/dismissals as the *net change in R&D cost-centre headcount*, not the
sum of per-product changes.

---

## 5. Product launches and pre-launch development

A successor product (e.g., `panel_gen2`) typically becomes *available* in a
later period than the period of game start. Before its `available_from_period`,
teams can invest in its indices — this is **pre-launch development**.

During pre-launch:

- The product's indices accumulate normally per the dynamics above.
- The product cannot be produced or sold.
- R&D spend on it appears in the P&L normally.

At launch (the team decides to launch in the first period the product is
available, or later):

- Inventory of any *replaced* prior-generation product is treated as discontinued
  (see `06-accounting.md` §3.4 — extraordinary expense at production cost).
- Won tenders from prior periods committed in the old generation can be
  fulfilled by the new generation.
- The new generation's starting indices reflect the cumulative R&D up to launch.

### 5.1 Index thresholds for launch

The scenario can specify *minimum index values* for a product to launch
without market penalty. From the solar-v1 narrative:

```
panel_gen2:
  launch_min_indices:
    efficiency: 100      # at least matching the old product
    sustainability: 100  # market expects modern sustainability
```

A team can launch below these thresholds, but suffers a one-period
**bad-launch penalty** on `product_score` (see `01-sales.md` §2.1.4) until
the indices recover.

---

## 6. R&D cost recognition

R&D expenditure is **fully expensed in the period of spend** — we do not
capitalise development costs. This matches the conservative IFRS treatment
under IAS 38 §57 (research costs always expensed; development costs only
capitalised under strict criteria).

Reasons for this choice:

1. **Pedagogical clarity.** Capitalising R&D hides the trade-off the
   simulation is teaching ("R&D costs money *now* for revenue *later*").
2. **Comparability.** Different teams shouldn't disagree about whether their
   R&D meets the IAS 38 §57 capitalisation criteria — it's a judgement call
   that would clutter the simulation.
3. **Realism.** Most public PV manufacturers expense the bulk of their R&D
   in practice.

---

## 7. Default coefficients summary

| Symbol             | Default          | Scope            |
|--------------------|------------------|------------------|
| `K_eff`            | 7.0              | global           |
| `K_sus`            | 6.0              | global           |
| `K_val`            | 4.0              | global           |
| `spend_ref_eff`    | 7 000 000 EUR    | global           |
| `spend_ref_sus`    | 4 000 000 EUR    | global           |
| `spend_ref_val`    | 2 000 000 EUR    | global           |
| `decay_eff`        | 0.01 / period    | global           |
| `decay_sus`        | 0.01 / period    | global           |
| `decay_val`        | 0.01 / period    | global           |
| `launch_min_indices` | per product    | scenario / product |

These live in `scenarios/<id>/scenario.yaml` under the `rnd:` section and can
be overridden per product or per period.

---

## 8. What's deliberately not here

- How indices feed into market share → `01-sales.md` §2.1.4
- How value-analysis reduces material consumption → `03-production.md` §4.1
- How R&D headcount affects HR balances → `04-hr.md` §2
- How R&D spend flows through accounting → `06-accounting.md` §2 (other costs) and §4 (CM III)
- The specific solar-PV narrative for indices ("efficiency = module conversion %") → `08-solar-narrative.md`
