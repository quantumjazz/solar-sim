# solar-sim (working title)

A multi-team classroom **business simulation** for university management courses,
set in the **solar PV and energy-storage** industry.

> **Status:** Phase 0 complete — mechanics specification, scenario pack, and
> licenses in place. No code yet. Phase 1 (engine MVP in Python) is next.
> **Public name:** TBD. The directory name `solar-sim` is a placeholder.

## What this is

Each team takes over the executive board of a virtual solar-PV manufacturer.
Every period (a fiscal year compressed into one classroom session) they decide:

- **Sales:** prices per market and channel, advertising, sales-force size,
  corporate identity spend, bulk-buyer and public-tender bids
- **R & D:** headcount and consulting budgets for module efficiency, sustainability,
  and bill-of-materials cost-down
- **Purchasing:** input-material order volumes with quantity-discount tiers
- **Production:** invest/disinvest/maintain/rationalize production lines,
  end-of-pipe environmental capex, production volume targets
- **HR:** hires and dismissals per cost centre, training, process optimisation,
  non-salary cost percentage, pension reserve
- **Finance:** short- and long-term loans, securities, dividends

After every team submits, the engine runs the period, settles a competitive market,
and emits a per-team report bundle plus a public industry report. Teams plan the
next period from those reports.

## Why another one

There are several closed-source commercial products in this space. The point of
this project is to give universities and self-learners:

1. An **open-source** engine that anyone can inspect, extend, and run on their own infrastructure.
2. A **transparent mechanics specification** — every formula derived from public sources
   (textbooks, academic papers, public industry reports), no proprietary derivations.
3. A **scenario-pack architecture** so the same engine can drive different industries
   (PV is the first pack; the design supports adding more without engine changes).
4. A **pedagogy layer** with planning-quality scoring, strategy-map authoring,
   peer assessment, and a board-meeting export — the assignments that make this a
   learning tool, not just a game.

## Repository layout

```
solar-sim/
├── README.md                 ← this file
├── LICENSE-CODE              ← MIT (applies to code)
├── LICENSE-CONTENT           ← CC-BY-SA 4.0 (applies to docs and scenarios)
├── docs/
│   ├── spec/                 ← mechanics specification (Phase 0 complete)
│   │   ├── 00-overview.md           state machine, period loop, glossary
│   │   ├── 01-sales.md              demand attraction model
│   │   ├── 02-rnd.md                R&D index dynamics
│   │   ├── 03-production.md         capacity laddering, depreciation, rework
│   │   ├── 04-hr.md                 productivity I/II, motivation, absenteeism
│   │   ├── 05-finance.md            loans, rating, share price
│   │   ├── 06-accounting.md         cost-type / cost-centre / cost-unit, P&L→BS→CF
│   │   ├── 07-scenario-format.md    YAML schema for scenario packs
│   │   └── 08-solar-narrative.md    style guide and product arc for solar-v1
│   └── sources.md            ← every formula and parameter cited here
├── scenarios/
│   └── solar-v1/             ← the solar-PV scenario pack
│       ├── scenario.yaml             starting state (Period 0)
│       ├── period-events.yaml        nine-period scenario (periods 1–9)
│       └── narrative/                public-domain news clippings (Phase 0 next pass)
├── sim-engine/               ← Python package (Phase 1)
└── app/                      ← Streamlit front-end (Phase 2+)
```

## How to read this repo (current state)

If you're picking this up fresh, read in this order:

1. `docs/spec/00-overview.md` — the period loop and state model
2. `docs/spec/06-accounting.md` — the central financial articulation
3. `docs/spec/01-sales.md` — the demand model
4. `scenarios/solar-v1/scenario.yaml` — what the world looks like at t=0
5. `docs/sources.md` — where every number comes from

## License

- **Code** (sim-engine/, app/, cli/, any source files): MIT — see `LICENSE-CODE`.
- **Content** (docs/, scenarios/, narrative): CC-BY-SA 4.0 — see `LICENSE-CONTENT`.

## Acknowledgements

The class of decision-driven, period-based, multi-team management simulations dates
back to the 1950s (the American Management Association's *Top Management Decision
Simulation*, 1957). The genre's modern conventions — multi-functional decision areas,
trial-then-real periods, planning-quality scoring, competitor reports — are now
standard. This project draws on that public lineage and on public-domain industry
data for the solar-PV sector. See `docs/sources.md` for full attribution.
