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

To gate instructor signups on the multi-user app, set
`SOLAR_SIM_INSTRUCTOR_TOKEN=<some-secret>` before launching; the
registration form then asks for the matching token whenever someone
chooses the "Instructor" role. Leave unset to keep instructor
registration open (the historical default).

**Dev-mode default admin.** When the env var above is unset *and* the
database is empty, the app seeds a single instructor account
(`admin@solar-sim.local` / `tester`) so a fresh clone is testable
without going through registration. The Log in tab shows this hint.
Production deployments that set the env var get **no seed** — that
way a hardcoded password can never accidentally ship live. Delete the
row from the `users` table to remove the seed once you've created
your own account.

As of 2026-05-31: 36 engine tests + 72 app tests pass; 1 PDF
round-trip test is skipped unless the optional PDF stack is installed.

Install: `pip install -r requirements.txt` (engine + app + tests in
one file). On Ubuntu, weasyprint also needs
`apt install libpango-1.0-0 libpangoft2-1.0-0`; on macOS,
`brew install pango cairo libffi`. Deployment recipe (Cloudflare Tunnel
+ systemd + Streamlit) lives at `docs/deployment.md`, with the unit
template at `deploy/solar-sim.service` and a pilot-reset helper at
`scripts/reset-db.sh`. Runtime
dependencies: `pydantic` (v2), `pyyaml`, `streamlit`, and
`extra-streamlit-components` (cookies for the multi-user app's
persistent login). Optional runtime dependencies for the PDF download
buttons (period briefing, board-meeting export): `markdown` and
`weasyprint`; the app degrades to a disabled button + caption when
they are not installed. WeasyPrint needs system libraries — on Ubuntu
`apt install libpango-1.0-0 libpangoft2-1.0-0`, on macOS
`brew install pango cairo libffi`. The multi-user app also uses
`sqlite3`, `hashlib`, `secrets`, and `os` — all from the standard
library. Test dependency: `pytest`. There is no build step.

## Architecture map

```
sim-engine/        pure-Python simulation engine — package `sim_engine`
  scenario.py        scenario loading + scenario-side models
  state.py           runtime state (PeriodState, CompanyState, …)
  decisions.py       TeamDecision input models
  reports.py         output report models (incl. IndustryReport)
  context.py         applies period events → ResolvedPeriodContext
  validation.py      validate_decision / InvalidDecisionError
  engine.py          run_period orchestrator + build_initial_state
  rules/             per-phase rule modules: rnd, hr, production, sales,
                       accounting, finance (called by the orchestrator)
scenarios/solar-v1/  the scenario pack (scenario.yaml, period-events.yaml,
                     narrative/period-1..9.md)
app/                 Streamlit front ends (depend on the engine)
  app.py               multi-user app: logins, role-gating, SQLite-backed
  db.py                SQLite schema + CRUD
  auth.py              account hashing, register / login
  service.py           bridges the database to the engine
  pedagogy.py          planning-quality + StrategyMap + peer-rating models (pure)
  board_export.py      Markdown renderer for the board-meeting deliverable (pure)
  pdf_export.py        Markdown -> PDF renderer (optional weasyprint dep)
  forms.py / views.py  decision-entry forms / report rendering (shared)
  instructor_console.py  single-operator console (no database)
docs/                spec/ (incl. 09-pedagogy.md), sources.md, calibration.md,
                     architecture.md, current-task.md, decisions.md, testing.md,
                     deployment.md
deploy/              solar-sim.service (systemd unit template)
scripts/             reset-db.sh (between-pilot DB rotation)
requirements.txt     pinned runtime + test deps
.env.production.example  template for deploy-time secrets (gitignored
                         when filled in)
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
