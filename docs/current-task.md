# Current task

A living snapshot of where development stands. Update it as work moves.

**As of 2026-05-22.**

## Status

The "finish & calibrate solar-v1" milestone is complete, plus a follow-up
bug fix. All work below is **in the working tree, not yet committed**.

- 28 engine tests + 4 app tests pass.
- Last commit on `main`: `a562169` (v0.3 successor products).

## Recently completed (uncommitted)

- **Wired the scenario's `notable_events`** — the period-6 €6m one-off
  remediation charge, the period-5 environmental law (line env indices
  −15, compliance baseline → 115), one-period production-line price
  offers, and the `max_dismissals_production` cap. Added a standing
  environmental compliance penalty.
- **Calibrated `solar-v1`** — cut `panel_gen1`/`panel_gen2` input-material
  tiers; a median period-1 decision is now roughly break-even. Documented
  in `docs/calibration.md`.
- **Wrote the nine narrative briefings** (`scenarios/solar-v1/narrative/`),
  rendered in the instructor console.
- **Fixed the environmental-capex bug** — env capex used to remove cash
  without recording an asset, breaking the balance sheet. It is now
  capitalised, depreciated straight-line over 10 periods, and its net book
  value provides "abatement" that offsets the compliance penalty.
- Added five project docs (`CLAUDE.md` and the four files in `docs/`).

## Immediate next step

Commit the working-tree changes. (Commits are made only when the
maintainer asks; pushing is done by the maintainer over SSH.)

## Then — open choice, not yet decided

Two candidate directions, neither started:

- **Phase 3 — student-facing app.** Per-team logins, a database, teams
  submit their own decisions, instructor advances periods. Widens reach
  beyond the single-operator instructor console.
- **Pedagogy layer.** Planning-quality scoring (forecast vs actual),
  strategy-map / balanced-scorecard authoring, peer assessment,
  board-meeting export — the graded-course features.

## Known limitations / deliberate simplifications

These are genuine gaps, not bugs — the simulation is coherent without them
and every articulation identity holds. Listed so they are not forgotten:

- **Tender delivery lag** — a won tender delivers and bills in the current
  period; the scenario's `delivery_period` field is not yet honoured.
- **Overtime** — production hard-caps at Available Capacity II; there is no
  Available Capacity III / overtime stretch.
- **Rationalisation spend** — booked as a cost but does not raise capacity
  (it is a no-op lever; not exposed in the instructor console form).
- **`rating_index`** — static; never updates and does not feed back into
  borrowing rates.
- **`image_index` / `satisfaction_index`** — not dynamic (`_update_slow_indices`
  is a no-op). They are not read by the attraction model, so this is inert.
- **Share price** — not modelled; reported as `0` in the executive summary
  and industry report.
- **`storage_box` / `balcony_solar` economics** — first-pass estimates,
  not play-tested as thoroughly as the panel line.
- **Insolvency** — negative equity is not a game-over condition; the engine
  keeps running.
- **Market 2** — carries `panel_gen1` only; the successor products are
  domestic-market only.

## Small known issues

- Version mismatch: `sim-engine/pyproject.toml` says `0.1.0` while
  `sim_engine/__init__.py` says `0.2.0`. Harmless, but pick one.
