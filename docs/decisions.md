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

### 18. Phase 3: per-student accounts, SQLite, one role-gated app

The student-facing app is a single Streamlit app, role-gated at login, over
a SQLite database, with per-student accounts. Each fork was an explicit
choice: **per-student accounts** (over team join codes) so individuals have
an identity — useful for a later peer-assessment layer; **SQLite** (over
PostgreSQL) — one file, zero setup, self-hostable, and ample for classroom
scale; **one app** (over separate student and instructor apps) — a single
codebase and process, with login deciding the view.
**Status: adopted.**

### 19. The instructor console is kept as a database-free mode

`instructor_console.py` was not replaced by the multi-user app. It remains a
single-operator tool with no database or login — the fastest way to run a
cohort solo, and it matches how the reference course ran. The two front ends
share `forms.py` and `views.py`.
**Status: adopted.**

### 20. Phase 3 scope: a persistence-and-UI layer, no engine changes

The student-facing app touches no engine code: `service.py` bridges the
SQLite store to the engine's existing public API. It adds no third-party
dependency — `sqlite3`, `hashlib` (PBKDF2 password hashing) and `secrets`
are all standard library. A logged-in session lives in Streamlit
`session_state`, so a hard browser refresh requires logging in again;
cookie-based persistence, real-time updates, and the graded pedagogy layer
were all deferred.
**Status: adopted.**

### 21. Pedagogy layer ships in two passes; pass 1 = student-authored artifacts

The pedagogy layer is too big to land in one phase, so it ships in two
passes. **Pass 1** is the student-authored artifacts: **planning quality**
(per-period plan-vs-actual scoring on the three KPIs already carried in
`TeamDecision.finance.planned_kpis`) and a freeform **balanced-scorecard
strategy map** per team. **Pass 2** is peer assessment and a
board-meeting export.

Planning quality is scored with **symmetric MAPE** per KPI, taking the
mean across the three KPIs and averaging real periods (trial periods are
shown but excluded from the headline). sMAPE was chosen over MAPE
because it is bounded, symmetric, and well-defined on negative ROE and
negative operating cash flow — both common in the simulation. The
formula is cited to public forecasting literature (`docs/sources.md` §8:
Makridakis 1993; Hyndman & Athanasopoulos 2021); the spec is in
`docs/spec/09-pedagogy.md`.

The strategy map is **freeform Markdown per balanced-scorecard
perspective**, not algorithmically graded — the instructor reviews each
team's map against the course rubric. The MVP keeps only the current
version (no edit history). The engine was not touched in either case.
**Status: adopted.**

### 22. Peer assessment: once per cohort, ratee-anonymised, multi-dimensional

The first half of pedagogy pass 2 — peer assessment — uses three choices
decided with the user. **Cadence**: one rating per (rater, ratee) per
cohort, editable any time the cohort is active and locked when it
finishes. **Visibility to the ratee**: aggregated per-dimension averages
only, shown only after the cohort closes — the standard anonymity-to-ratee
pattern (`docs/sources.md` §8: Topping 2009). Comments stay
instructor-only in this first pass. **Dimensions**: four Likert 1–5
scales (contribution, collaboration, reliability, communication) plus an
optional free-text comment, following Fellenz (2006)'s evaluation-of-
individual-contributions protocol. Self-rating is excluded.

The service layer enforces three rules the schema cannot — rater ≠ ratee,
same-team membership, cohort-active gating — alongside the database
CHECK constraints on the 1–5 dimension range. The spec is in
`docs/spec/09-pedagogy.md` §3. Board-meeting export remains for a
follow-up phase.
**Status: adopted.**

### 23. Board-meeting export is Markdown, zero new dependencies

The second half of pedagogy pass 2 — the capstone deliverable — is a
**Markdown** document, not PDF or DOCX. Markdown carries the project's
no-third-party-dependency stance: generation is a pure string-build
(`app/board_export.py`), it renders natively as a Streamlit preview, it
downloads as a plain `.md`, and downstream conversion to PDF / DOCX is
one `pandoc` call away. A native PDF or DOCX exporter would mean adding
a library; that's deferred.

The same renderer drives both viewer roles. Students get their own team's
document with the peer-assessment section filtered to their own
aggregated rating (gated by the cohort-status rule from decision #22);
instructors get the full per-team aggregate and rater→ratee detail with
comments. The spec is in `docs/spec/09-pedagogy.md` §4. After this lands,
all four pedagogy features named in the README are in place.
**Status: adopted.**

### 24. Phase 3 polish: real cookies over a URL-token workaround

The Phase 3 multi-user app originally kept the logged-in user in
Streamlit `session_state`, which a hard browser refresh clears — the
single most-felt friction point. Phase 3 polish fixes it with **real
cookies**, not a URL-query-parameter token. The cookie carries an opaque
random token (`secrets.token_urlsafe(32)`) backed by a server-side
`sessions` table (token PK, user_id, expiry); login mints, logout
deletes, expired rows are pruned on every lookup.

The price is one new third-party runtime dependency,
`extra-streamlit-components`, for its `CookieManager`. The trade-off was
decided with the user: a query-parameter token alternative would have
been stdlib-only but put the session token in the URL (visible in
history, leaked by copy-paste). Real cookies were judged worth the
modest dep cost; the library is small, well-maintained, and widely used.

Alongside the cookie fix, **`@st.fragment(run_every=5)`** wraps the
instructor's submission dashboard so submissions land without a manual
refresh, and a read-only **Team drafts** section shows each team's
in-progress decision for live monitoring. No engine changes.
**Status: adopted.**

### 25. Engine gaps closed (insolvency, tender lag, overtime, rating, share price)

A combined pass closes every gap listed in `docs/current-task.md`'s
"Known limitations / engine" section:

- **Insolvency.** Negative book equity at period end sets a sticky
  `is_bankrupt` flag (`docs/spec/05-finance.md` §11). The flag is a
  pedagogical signal — the company keeps playing — and is surfaced in
  `ExecutiveSummary` and `IndustryCompanyLine`. Articulation holds for
  solvent and bankrupt companies alike.
- **Tender delivery lag.** Won tenders are stored as
  `CompanyState.committed_tenders` and ship in their
  `tender.delivery_period` (`01-sales.md` §3.1). Revenue books at
  delivery; inventory is reserved at delivery time, not at bid time.
- **Overtime (Capacity III).** When aggregate production target exceeds
  Available Capacity II, the engine schedules overtime up to
  `overtime_max_pct` (`03-production.md` §2.3). The step fixed cost
  (500 k EUR) and a 25 % wage premium on overtime hours flow into
  `other_expenses`.
- **Dynamic rating + interest surcharge.** `rating_index` is now
  recomputed every period from seven of the eleven components in
  `05-finance.md` §4.1 — the ones available without time-series
  history. The rating drives a per-period interest-rate surcharge
  (§4.2); the loan rates already paid this period use the prior
  period's rating, which matches §1.2's floating-rate intent.
- **Share price.** `executive_summary.share_price` is now non-zero and
  responds to four core drivers (ROE, ROS, book equity level, debt /
  equity). Four-driver MVP instead of the spec's 14; pilot calibration
  will refine the β coefficients.

Both rating (7 of 11 components) and share price (4 of 14 drivers) ship
as documented MVP simplifications — added to `05-finance.md` §4.1 and §5
as inline notes. Tests added: insolvency × 3, tender lag × 1 (existing
test updated and extended), overtime × 1, rating × 2, share price × 1.
Engine test count goes 28 → 35; the articulation invariant still holds
in every test, for solvent and bankrupt companies, with and without
overtime, and after the rating-surcharge re-prices interest.
**Status: adopted.**
