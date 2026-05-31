# Current task

A living snapshot of where development stands. Update it as work moves.

**As of 2026-05-27.**

## Status

Four phases landed in one omnibus commit on top of `1678cfb`: the
big-five engine gaps (insolvency, tender delivery lag, overtime /
Capacity III, dynamic credit rating + interest surcharge, share price),
pedagogy pass 2 (peer assessment + Markdown board export), Phase 3
polish (cookie-persistent login, self-refreshing submission dashboard,
read-only draft viewer), and a code-review cleanup pass.

- 36 engine tests + 62 app tests pass.

## Recently completed

### Engine gaps

Every item in the prior engine "Known limitations" list is now
implemented:

- **`docs/spec/05-finance.md` §11** — new insolvency spec.
- **`state.py`** — `CompanyState.is_bankrupt` (sticky), `share_price`,
  `committed_tenders` list. New `CommittedTender` model for deferred
  tender obligations.
- **`reports.py`** — `is_bankrupt` flags on `ExecutiveSummary` and
  `IndustryCompanyLine`.
- **`engine.py`** — insolvency check at period end; deferred-tender
  settlement (`_settle_committed_tenders`) running before current-period
  tenders; overtime factor in `_apply_production` with step fixed cost
  and wage premium; `_compute_rating`, `_compute_share_price`, and
  `_rating_surcharge` used by `_articulate` (rating-driven surcharge
  applied to all loan interest using the prior period's rating).
- **`docs/spec/05-finance.md` §4.1 and §5** — MVP-simplification notes:
  rating uses 7 of 11 components (weights renormalised to 1.0), share
  price uses 4 of 14 drivers, both flagged for pilot calibration.
- **7 new engine tests**: insolvency × 3, overtime × 1, rating × 2,
  share price × 1; the tender-bid test was updated to verify the
  deferred-delivery flow end-to-end.

### Phase 3 polish

Cookie-persistent login, self-refreshing submission dashboard,
instructor view of in-progress drafts. New dependency:
`extra-streamlit-components`. New `sessions` table; `auth.create_session`
/ `lookup_session` / `end_session`.

### Pedagogy pass 2

Peer assessment + board-meeting Markdown export. `peer_ratings` table,
`PeerRating` / `AggregatedRating` models, `board_export.py` renderer,
new Peer-review and Board-export tabs in both roles.

### Code-review cleanup

Five small but real fixes from a focused review pass:

- Stale "still simplified" lists in `engine.py` and `decisions.py`
  docstrings rewritten to match the actual state (the bullets about
  tender lag / overtime / rating / share price had become wrong).
- `PRICE_ANCHOR` hard-coded inside `_company_attractiveness` moved onto
  `MarketCoefficients.price_anchor` and set explicitly on both markets
  in `scenarios/solar-v1/scenario.yaml` — the only piece of solar-v1
  data that had leaked into the supposedly industry-agnostic engine.
- `validate_decision` now rejects unknown product ids in sales / R&D /
  purchasing / production decisions; a typo previously produced no
  error (the engine silently skipped it). One new engine test.
- Decision schemas (`TeamDecision`, `LineInvestDecision`,
  `LineMaintenanceDecision`, `LineRationalisationDecision`) switched
  from `extra="allow"` to `extra="forbid"` so form-side typos surface
  on submission. State models left on `allow` to avoid DB round-trip
  risk.
- `sim-engine/pyproject.toml` version synced 0.1.0 → 0.2.0 to match
  `__init__.py`.

## Immediate next step — open choice, not yet decided

The remaining limitations are narrower than what was just closed —
mostly inert indices and scenario calibration:

- **Pedagogy refinements.** Sharing peer comments to ratees anonymised,
  per-period peer ratings, weighted KPIs, strategy-map version history,
  multi-team consolidated board reports, native DOCX export. (Native
  PDF export shipped 2026-05-31 — see `app/pdf_export.py`; powers the
  period-briefing and board-meeting download buttons.)
- **Pilot-onboarding polish (2026-05-31):** the `email` column now
  accepts a plain username (no `@` required); the student "waiting
  for assignment" screen auto-refreshes via a fragment; the Teams &
  members tab has an "Onboarding instructions for students" expander
  with copy-paste setup steps. See `decisions.md` #28.
- **Deployment artifacts (2026-05-31):** `requirements.txt`,
  `deploy/solar-sim.service`, `.env.production.example`,
  `scripts/reset-db.sh`, and `docs/deployment.md` ship the
  Cloudflare Tunnel + systemd + Streamlit recipe. See
  `decisions.md` #29.
- **Engine indices and calibration.** Re-enable `image_index` /
  `satisfaction_index` dynamics (currently inert); use the now-dynamic
  rating in the share-price drivers; pilot-calibrate the rating
  component weights and the share-price β coefficients.
- **Scenario depth.** Better economics for `storage_box` /
  `balcony_solar` (first-pass estimates); open `market_2` to the
  successor products; rationalisation spend → real capacity effect.

A real classroom pilot would inform which of these matter most.

## Known limitations / deliberate simplifications

Engine — narrower now that the big-five gaps are closed:

- **Rationalisation spend** — booked as a cost but does not raise
  capacity (it is a no-op lever; not exposed in the instructor console
  form).
- **`image_index` / `satisfaction_index`** — not dynamic
  (`_update_slow_indices` is a no-op). They are not read by the
  attraction model, so this is inert. Customer satisfaction is one of
  the rating components in the spec; once it goes dynamic it can be
  added back to `_compute_rating`.
- **`storage_box` / `balcony_solar` economics** — first-pass estimates.
- **Market 2** — carries `panel_gen1` only.
- **Rating composite is 7 of 11 components.** EMA-style trend
  components, customer satisfaction, and efficiency-vs-industry are
  deferred; pilot calibration will tune the included weights too.
- **Share-price formula is 4 of 14 drivers.** Dividend signalling,
  marketing spend, planning quality, R&D cumulative, etc. await
  integration with their engine-side sources; β coefficients are
  pilot-calibration placeholders.
- **Tender non-delivery has no penalty.** If a team's inventory is
  short at a committed tender's delivery period they ship what they
  have; the spec leaves room for a future non-delivery penalty.

Multi-user app — same as before:

- **First-run cookie flash.** On a hard browser refresh the cookie
  arrives via a JS bridge in a follow-up script run, so the login
  screen flashes briefly before auto-login kicks in.
- **No real-time student-side updates.** Only the instructor's
  submission dashboard polls.
- **Draft concurrency** is last-write-wins.
- **Open instructor role at registration** — *partially closed.* The
  deployment can now set `SOLAR_SIM_INSTRUCTOR_TOKEN` to gate instructor
  signups behind a shared secret. Leaving it unset keeps registration
  open (the historical default).

Pedagogy layer — same as before; refinements listed in
`docs/spec/09-pedagogy.md` §4.5 and §5.
