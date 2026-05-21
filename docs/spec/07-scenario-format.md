# 07 — Scenario Pack Format

> **Scope.** The YAML schema for a scenario pack, validation rules, and how
> to author a new scenario. A scenario pack is the data half of the
> simulation: the engine has no industry knowledge; everything domain-specific
> lives in `scenarios/<id>/`.

---

## 1. Scenario pack layout

A scenario pack is a directory under `scenarios/`:

```
scenarios/<scenario_id>/
├── scenario.yaml          ← starting state and world defaults (Period 0)
├── period-events.yaml     ← what changes in periods 1, 2, …, N
├── narrative/             ← per-period news clippings (Markdown, one per period)
│   ├── period-1.md
│   ├── period-2.md
│   └── ...
└── README.md              ← human-readable design notes for the scenario
```

`<scenario_id>` is the directory name and the scenario's stable identifier
(`solar-v1`, `e-bikes-v1`, etc.). It is used in saved game states and
report headers.

---

## 2. `scenario.yaml` — the starting state

The structure documented in `scenarios/solar-v1/scenario.yaml`. Top-level
keys and what each is for:

| Top-level key                       | Purpose |
|-------------------------------------|---------|
| `scenario`                          | Metadata: id, version, display name, language, base currency, period structure, RNG seed |
| `world`                             | Default rates and constants that apply unless a period event overrides (interest, tax, hiring fees, building depreciation, etc.) |
| `company_state_period_0`            | The state a team inherits at the start: cash, debts, workforce, indices |
| `products`                          | Product catalog with starting indices and economics |
| `markets`                           | Market catalog with attraction-model coefficients, currency, transport, FX |
| `production_line_catalog`           | The line types a team can buy throughout the game |
| `existing_lines_period_0`           | The specific lines inherited at period 0 |
| `storage`                           | Inventory storage costs |
| `maintenance_table`                 | Maintenance spend → availability mapping |
| `index_decay`                       | Per-period decay for indices |
| `period_0_decisions_narrative_only` | The decisions the prior board "made" in period 0 — used only to initialise state |

### 2.1 Required fields

The following fields are required (engine will refuse to load otherwise):

- `scenario.id`, `scenario.version`, `scenario.base_currency`, `scenario.real_periods`
- `world.finance.tax_rate`, `world.finance.payment_in_period_pct`
- At least one product in `products[]`
- At least one market in `markets[]` with `open_from_period` ≤ first real period
- The starting company state with non-zero subscribed capital

All other fields are optional; defaults are documented in the spec docs.

### 2.2 Field validation

The engine validates a scenario on load. Validation errors abort the load
with a precise message ("`products[1].indices.efficiency` must be ≥ 0").
The validator lives in `sim-engine/scenario/validator.py` and uses Pydantic
for type-checked deserialisation.

---

## 3. `period-events.yaml` — the per-period delta

Each entry describes what the world looks like in one period. Structure:

```yaml
events:
  - period: 1
    headline: "..."                  # 1-line news headline
    narrative_file: period-1.md      # the longer narrative; optional, can inline
    economy:
      gdp_growth: 0.02
      inflation: 0.00
      wage_growth: 0.03
    parameter_changes:               # what overrides scenario defaults this period
      factory_material_cost_per_unit: 4.50
      wages:
        purchasing: 31_000
        administration: 29_000
        production: 31_000
        rnd: 46_000
        sales: 42_000
      hiring_cost_per_head: 12_500
      max_dismissals_production: null   # null = no limit
    market_changes:
      market_1:
        market_potential_units:
          panel_gen1: 230_000
      market_2:
        open_from_period: null           # null = stay closed
    product_unlocks: []
    bulk_buyers:                         # period-specific offers
      - market: market_1
        product: panel_gen1
        max_units_per_company: 5_000
        price: 250
    tenders:
      - market: market_1
        product: panel_gen1
        units_required: 0
        max_acceptable_price: null
    notable_events: []
  - period: 2
    ...
```

### 3.1 `product_unlocks`

A product can be unlocked (becomes available for production and sale) by a
period event:

```yaml
product_unlocks:
  - product_id: panel_gen2
    development_required: true        # team must reach min indices to launch without penalty
    pre_launch_indices_at_unlock:     # what indices the prior board already invested in
      efficiency: 85
      sustainability: 45
      value_analysis: 90
    notes: |
      The prior board has invested in a Gen-2 prototype. Indices are
      below the launch thresholds (set in products[].launch_min_indices).
      Continuing development costs roughly 105 researcher-years.
```

### 3.2 `notable_events`

One-off changes the scenario flags as significant. Each is a structured
record so the engine can apply it without ambiguity:

```yaml
notable_events:
  - type: env_index_step
    affects: all_production_lines
    delta: -15
    reason: "New environmental regulation (KWA II §4)"

  - type: overtime_ban
    duration_periods: 1

  - type: pension_reserve_pct_change
    new_value: 0.06

  - type: max_dismissals
    cost_centre: production
    limit: 0
    reason: "Collective bargaining agreement: job protection"

  - type: one_off_other_expense
    amount: 6_000_000
    reason: "Forced repair of industrial waste purification plant"
```

The engine has a fixed dispatch table from `type` to handler. New event
types can be added by extending the engine; scenarios cannot invent new
event types ad-hoc.

---

## 4. Narrative files

Per-period markdown files in `narrative/period-N.md` form the
human-readable "news" a team reads at the start of the period. These are
**creative-commons content** (CC-BY-SA) — anyone can fork the scenario,
edit the narrative, and re-publish, with attribution.

The required form:

```markdown
# Period N — <headline>

<lead paragraph: the general economic situation>

## News from the industry

<sub-headed paragraphs: what's changing in the company's industry, bulk buyers,
tender opportunities, regulatory news, etc.>

## What changes from period N-1 to period N

| Quantity | Period N-1 | Period N |
| --- | --- | --- |
| ... | ... | ... |
```

Style notes are in `docs/spec/08-solar-narrative.md` and apply to anyone
authoring narrative for the `solar-v1` pack.

---

## 5. Authoring a new scenario

A worked walkthrough for adding e.g. an `e-bikes-v1` pack:

1. **Decide the product family.** Roughly 1 starting product, 1 successor, 1
   adjacent (e.g. cargo e-bike), 1 budget tier. Plan when each becomes
   available.

2. **Decide the markets.** Domestic + export is the simplest; consider a
   "B2B fleet" channel as a third market type if it fits the pedagogy.

3. **Find public industry data** for: typical unit selling price, BOM cost,
   labour content per unit, capex per production line, typical R&D as % of
   revenue, market sizes. Cite all of it in `docs/sources.md` under a new
   `§7-<industry>` section.

4. **Adapt the formulas, not the numbers.** The engine formulas are universal;
   only the parameters change.

5. **Calibrate against a "no team, do nothing" run.** A company that submits
   identical decisions to period 0 every period should produce a roughly
   flat outcome. If the company runs away to riches or bankruptcy, tune
   `M_base`, `α_market`, and the index decay rates first.

6. **Write the 6-9 period narrative.** Each period should have a teaching
   theme: trial periods test the planning tool, real period 1 is
   business-as-usual, real period 2 introduces a successor, etc.

7. **Test for bugs that look like features.** Run the engine 100 times with
   small random decision perturbations. Anywhere the same input produces
   different output is a bug. Anywhere the output reveals a dominant
   strategy ("always max marketing") is a calibration problem.

---

## 6. Versioning

Each scenario pack carries `scenario.version`. Semantic-versioning rules:

- **Patch** (0.1.0 → 0.1.1): typo fixes, narrative edits, cosmetic.
- **Minor** (0.1.x → 0.2.0): parameter changes, balance tweaks, new optional
  fields. Saved game states from the prior minor *should* still load.
- **Major** (0.x → 1.0): structural changes to the schema or game flow.
  Saved game states from the prior major version are not guaranteed to
  load.

Scenarios shipped to classrooms should be on a major version (1.x, 2.x). The
`solar-v1` pack is currently at 0.1.0 — pre-calibration.

---

## 7. Internationalisation

The scenario pack carries `scenario.language` (ISO 639-1 code: `en`, `de`,
`es`, …). The engine itself is language-agnostic; the UI translates field
labels via standard gettext-style PO files. Narrative content is *not*
auto-translated — you ship a separate scenario pack per language if needed.

The default `solar-v1` is in English. A `solar-v1-de` companion pack is
planned for the pilot.
