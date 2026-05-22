# Decision log

The significant design and process decisions, with their rationale. Newest
context first within each entry. This is a record, not a plan — see
`docs/current-task.md` for what is in progress.

Project started 2026-05-20; entries below span the work to 2026-05-22.

---

### 1. Build a clean-room, open-source classroom simulation

A self-hostable, openly licensed alternative to commercial management
simulations, so universities are not locked into a proprietary product.
Two real student archives of a commercial simulation showed how the
mechanics and the surrounding pedagogy work; the new project re-derives
the mechanics from public sources rather than copying them.
**Status: adopted — the project's premise.**

### 2. Industry: solar PV and energy storage

The simulated company manufactures residential PV system kits (later a
high-efficiency successor, battery storage, and a mid-market balcony kit).
A distinct, contemporary industry — chosen partly so the project shares no
domain detail with any reference product.
**Status: adopted.**

### 3. Strict IP discipline

No text, screen layout, name, or parameter is copied from any commercial
product. Every formula and parameter is traceable to a public source cited
in `docs/sources.md`. Code is MIT-licensed; documentation and scenario
content are CC-BY-SA 4.0.
**Status: adopted — non-negotiable.**

### 4. Specification before code

The full mechanics specification (`docs/spec/`, nine documents) was written
before any engine code, to lock down IP-safe, internally consistent
mechanics first. The spec is kept in sync with the engine as rules change.
**Status: adopted.**

### 5. Python + Streamlit, with a separable engine

The simulation lives in a pure-Python package, `sim-engine`, independent of
any UI. The front end is Streamlit. Keeping the engine separable means it
stays testable on its own and could later drive a different UI or an export.
**Status: adopted.**

### 6. The engine is pure, deterministic, and must articulate

`run_period` performs no I/O, holds no global state, and returns new state.
Every period, profit & loss → balance sheet → cash flow must reconcile;
this invariant is asserted by tests and treated as a release gate.
**Status: adopted — core engineering rule.**

### 7. Pydantic v2 for all data models; Python 3.9 baseline

All data crossing a module boundary is a Pydantic model. The code targets
Python 3.9 (the maintainer's system Python), so it avoids PEP-604 (`X | Y`)
unions and uses `from __future__ import annotations`.
**Status: adopted.**

### 8. Multi-team cohort with a multinomial attraction model

Demand in a market is split across competing teams in proportion to a
per-team "attractiveness" score (price, advertising, sales force, product
indices), then capped by each team's supply. This makes the simulation
genuinely competitive rather than single-player.
**Status: adopted.**

### 9. Generation handover: a coexistence model

When a successor product (e.g. Gen-2 panels) launches, it does **not**
forcibly replace its predecessor or scrap its inventory. Instead the two
coexist as separate products, and the scenario's period events ramp the
predecessor's market down while the successor's grows. The "when to switch"
pressure comes from that ramp.
*Why:* simpler and less punishing than a hard replacement, and it avoids a
shared-market-segment rewrite of the settlement code.
**Status: adopted; a hard-replacement variant remains a possible future
refinement.**

### 10. Decisions are validated and rejected, never silently clamped

`validate_decision` rejects hard-invalid decisions (negative values,
non-positive price, over-dismissal, sub-minimum non-salary cost, etc.).
Silent clamping was rejected because it makes outcomes unpredictable for
the team and undermines planning-quality scoring.
**Status: adopted.**

### 11. First UI: an instructor console, not a student app

The first front end is a single-operator instructor console — load a
scenario, enter every team's decisions, run the period, review reports.
*Why:* it matches how the reference course actually ran (teams submit
forms, the instructor runs them), is the fastest route to something usable
in a classroom, and defers authentication and a database.
**Status: adopted; a student-facing multi-team app is a later phase.**

### 12. Close engine gaps before building the UI

Decision validation and the cohort-public industry report were added to
the engine before the instructor console, so the UI was built against a
complete engine surface.
**Status: adopted; done.**

### 13. Environmental-tech abatement uses net book value, linear with a cap

End-of-pipe environmental investment is capitalised and depreciated; its
*net book value* (not cumulative spend) buys index points of "abatement"
that offset the compliance penalty, linearly up to a cap.
*Why:* using NBV makes abatement fade as equipment depreciates, so it is a
recurring decision rather than a one-off; linear-with-cap is simpler than
the spec's original log curve. `docs/spec/03-production.md` was updated to
match the implementation.
**Status: adopted.**

### 14. No separate bad-launch penalty

Launching a successor product with weak indices is already punished by the
attraction model — low indices yield low attractiveness and low sales — so
a distinct "bad launch" penalty was judged redundant and not implemented.
**Status: adopted.**

### 15. Calibration target: median ≈ break-even

`solar-v1` is tuned so a median, unremarkable decision is roughly
break-even and skilful play visibly out-earns it. Precise balancing is
left for a post-pilot pass. See `docs/calibration.md`.
**Status: adopted; first pass done, refinement expected after a real
classroom pilot.**

### 16. Game state saved as JSON; no database yet

The instructor console keeps cohort state in the Streamlit session and
saves/loads it as a JSON file. A database is deferred to the phase that
introduces student logins.
**Status: adopted.**

### 17. Reference archives stay in the repo tree but untracked

The copyrighted commercial-simulation archives sit in a sibling folder of
`solar-sim/` inside the same git repository. They are deliberately
untracked (copyright, and ~2 GB in size) and must never be committed.
**Status: adopted.**
