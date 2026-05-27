# CLAUDE.md

Guidance for AI agents (and humans) working in this repository.

**solar-sim** is an open-source, copyright-safe classroom business simulation
set in the solar-PV industry: a separable pure-Python engine plus two
Streamlit front ends — a single-operator instructor console and a multi-user,
SQLite-backed app with per-student logins. It is a clean-room alternative to
commercial management simulations — see "IP discipline" below.

## Commands

Engine tests — run from `sim-engine/`:

```
PYTHONPATH=src python3 -m pytest
```

App tests — run from the project root (`solar-sim/`):

```
PYTHONPATH=sim-engine/src:app python3 -m pytest app/
```

Run a front end — from `solar-sim/`:

```
streamlit run app/app.py                 # multi-user app (logins + SQLite)
streamlit run app/instructor_console.py  # single-operator console (no DB)
```

As of 2026-05-25: 35 engine tests + 62 app tests, all passing. Runtime
dependencies: `pydantic` (v2), `pyyaml`, `streamlit`, and
`extra-streamlit-components` (cookies for the multi-user app's
persistent login). The multi-user app also uses `sqlite3`, `hashlib`,
and `secrets` — all from the standard library. Test dependency:
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
app/                 Streamlit front ends (depend on the engine)
  app.py               multi-user app: logins, role-gating, SQLite-backed
  db.py                SQLite schema + CRUD
  auth.py              account hashing, register / login
  service.py           bridges the database to the engine
  pedagogy.py          planning-quality + StrategyMap + peer-rating models (pure)
  board_export.py      Markdown renderer for the board-meeting deliverable (pure)
  forms.py / views.py  decision-entry forms / report rendering (shared)
  instructor_console.py  single-operator console (no database)
docs/                spec/ (incl. 09-pedagogy.md), sources.md, calibration.md,
                     architecture.md, current-task.md, decisions.md, testing.md
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
- Do not commit `__pycache__/`, `.pytest_cache/`, `.DS_Store`, or the
  `*.db` cohort database (the `.gitignore` already excludes them).

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
- **No hosted deployment.** Both front ends run locally. The multi-user
  app (`app/app.py`) keeps cohort state in a SQLite file (`solar-sim.db` at
  the repo root, or `$SOLAR_SIM_DB`); students connect to the instructor's
  machine over the local network. The console (`instructor_console.py`) has
  no database and saves a game as a JSON file.
