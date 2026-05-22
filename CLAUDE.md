# CLAUDE.md

Guidance for AI agents (and humans) working in this repository.

**solar-sim** is an open-source, copyright-safe classroom business simulation
set in the solar-PV industry: a separable pure-Python engine plus a Streamlit
instructor console. It is a clean-room alternative to commercial management
simulations — see "IP discipline" below.

## Commands

Engine tests — run from `sim-engine/`:

```
PYTHONPATH=src python3 -m pytest
```

App tests — run from the project root (`solar-sim/`):

```
PYTHONPATH=sim-engine/src:app python3 -m pytest app/test_app.py
```

Run the instructor console — from `solar-sim/`:

```
streamlit run app/instructor_console.py
```

As of 2026-05-22: 28 engine tests + 4 app tests, all passing. Runtime
dependencies: `pydantic` (v2), `pyyaml`, `streamlit`. Test dependency:
`pytest`. There is no build step.

## Architecture map

```
sim-engine/        pure-Python simulation engine — package `sim_engine`
  scenario.py        scenario loading + scenario-side models
  state.py           runtime state (PeriodState, CompanyState, …)
  decisions.py       TeamDecision input models
  reports.py         output report models (incl. IndustryReport)
  context.py         applies period events → ResolvedPeriodContext
  validation.py      validate_decision / InvalidDecisionError
  engine.py          run_period orchestrator + all rule modules
scenarios/solar-v1/  the scenario pack (scenario.yaml, period-events.yaml,
                     narrative/period-1..9.md)
app/                 Streamlit instructor console (depends on the engine)
docs/                spec/, sources.md, calibration.md, architecture.md,
                     current-task.md, decisions.md, testing.md
```

Public API: `load_scenario_pack`, `build_initial_state`, `run_period`,
`validate_decision`. The period loop has three phases — pre-market →
cohort settlement → post-market. Full detail in `docs/architecture.md`.

## Coding rules

- **Python 3.9** — no PEP-604 unions (`X | Y`). Use `Optional[...]` /
  `Union[...]` and `from __future__ import annotations`.
- All data crossing a module boundary is a **Pydantic v2 model**.
- The engine is **pure and deterministic**: no file or network I/O, no
  global mutable state, no unseeded randomness. `run_period` returns new
  state; it does not mutate its inputs in place.
- **Articulation invariant** — every period, profit & loss → balance sheet
  → cash flow must reconcile. Tests assert it; never merge a change that
  breaks it.
- `app/` may import `sim_engine`; `sim_engine` must never import `app`.
- Keep `docs/spec/` consistent with the engine — change a formula, update
  the spec.

## Do not touch

- `../Business Sims/` — copyrighted commercial-simulation archives. A
  sibling folder inside the same git repo, deliberately **untracked**.
  Never read it into code or docs, and never `git add` it.
- `LICENSE-CODE` (MIT) and `LICENSE-CONTENT` (CC-BY-SA 4.0) — do not change
  licensing.
- Do not commit `__pycache__/`, `.pytest_cache/`, or `.DS_Store` (the
  `.gitignore` already excludes them).

## IP discipline (non-negotiable)

This is a clean-room project. No text, screen layout, name, or parameter
may be copied from any commercial simulation product. Every formula and
parameter must be traceable to a public source cited in `docs/sources.md`.
Code is MIT-licensed; documentation and scenario content are CC-BY-SA 4.0.

## Git & deployment

- The git repository root is the **parent** of `solar-sim/`. Only the
  `solar-sim/` subtree is tracked.
- Commit only when explicitly asked. Never run `git push` — the maintainer
  pushes to GitHub over SSH.
- **There is no deployment.** The app runs locally; cohort state lives in
  the Streamlit session and is saved/loaded as a JSON file. No database,
  no authentication. A hosted multi-team setup is a future phase.
