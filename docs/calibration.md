# Calibration — solar-v1

How the `solar-v1` scenario parameters are tuned, and the philosophy behind it.

## Goal

A scenario is well-calibrated when:

1. A **median decision** — a sensible-but-unremarkable play — produces a
   roughly break-even result, not a perpetual loss. A simulation where
   every team loses money every period regardless of skill is confusing and
   demoralising.
2. **Skill is rewarded.** A leaner or sharper decision visibly out-earns the
   median; a careless one visibly under-earns it.
3. **Strategic choices matter.** Ignoring the scenario's arc (e.g. never
   launching the successor product) leads to decline; adapting leads to
   growth.

Calibration is *not* about realism to two decimal places. It is about a
play experience where decisions have legible, fair consequences.

## What was tuned

The dominant cost in the panel business is input material. The first
calibration pass set `panel_gen1` input material too high relative to the
~EUR 2,800 price anchor, so a median decision lost ~EUR 9m/period.

Input-material purchase tiers were cut ~15–20 %:

| Product       | Before (EUR/unit)        | After (EUR/unit)        |
|---------------|--------------------------|-------------------------|
| `panel_gen1`  | 1150 / 1000 / 900 / 850  | 950 / 830 / 750 / 700   |
| `panel_gen2`  | 950 / 830 / 740 / 690    | 820 / 720 / 650 / 610   |

Period-0 inventory unit values were moved in step (`panel_gen1` input
material 1000 → 850, finished goods 1900 → 1700).

## Result (single company, period 1, measured)

| Decision archetype                       | Net income |
|------------------------------------------|------------|
| Median — price 2900, normal spend        | ≈ −1.7 mEUR |
| Lean — price 3000, low marketing/R&D     | ≈ +3.9 mEUR |
| Good — price 3150                        | ≈ +6.6 mEUR |

The median is roughly break-even (−1.3 % of revenue); skill clearly pays.

## Multi-period behaviour

- A **static `panel_gen1`-only** strategy treads water through period 7
  (equity drifts down slowly) and then collapses in periods 8–9 as the
  gen1 market is deliberately ramped away. This is the intended punishment
  for ignoring the successor.
- A **gen2-adopting** strategy takes deep losses in periods 2–3 (heavy
  pre-launch R&D) and recovers to growing profits in periods 7–9, ending
  with higher equity than the static strategy. This is the intended
  reward arc.
- Periods 5–6 are deliberately hard (the environmental law lifts the
  compliance penalty; the period-6 tax hike and one-off remediation charge
  bite). Teams are expected to dip there and recover.

## Known limitations / future work

- `storage_box` and `balcony_solar` economics are first-pass estimates and
  have not been play-tested as thoroughly as the panel line.
- Market potentials are sized for a full cohort (~5 teams). With a very
  small cohort the export market is hard to reach because the domestic
  market chronically under-supplies (see `sim-engine/README.md`).
- The attraction-model coefficients (`β_price`, `β_ad`, …) are unchanged
  from their first-principles defaults; a cohort play-test would refine them.
- Insolvency (negative equity) is not yet a game-over condition; the engine
  keeps running and a team can dig out.

Re-calibration after a real classroom pilot is expected and healthy.
