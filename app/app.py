"""solar-sim — multi-user classroom app.

A single Streamlit app, role-gated by login:

  - **Instructors** create cohorts, assign students to teams, watch
    submissions, advance periods, and review every team's reports.
  - **Students** log in, see the period briefing, enter and submit their
    team's decision, and review their team's reports.

All shared state lives in a SQLite database (`solar-sim.db` at the repo
root); see `db.py`, `auth.py`, and `service.py`. The original
`instructor_console.py` remains as a database-free single-operator tool.

Run it from the repository root (`solar-sim/`):

    streamlit run app/app.py
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Make the engine importable without installing it (dev convenience).
_ENGINE_SRC = Path(__file__).resolve().parent.parent / "sim-engine" / "src"
if str(_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SRC))

import extra_streamlit_components as stx  # noqa: E402
import streamlit as st  # noqa: E402

from sim_engine.validation import InvalidDecisionError  # noqa: E402

import auth  # noqa: E402
import forms  # noqa: E402
import views  # noqa: E402
from db import Database  # noqa: E402
import pdf_export  # noqa: E402
from service import GameService, ServiceError, form_context, load_narrative  # noqa: E402

# The cohort database. Defaults to `solar-sim.db` at the repo root; set the
# SOLAR_SIM_DB environment variable to put it elsewhere.
_DB_PATH = Path(
    os.environ.get(
        "SOLAR_SIM_DB", Path(__file__).resolve().parent.parent / "solar-sim.db"
    )
)
_DEFAULT_SCENARIO = str(
    Path(__file__).resolve().parent.parent / "scenarios" / "solar-v1"
)

st.set_page_config(page_title="solar-sim", layout="wide")


# ---------------------------------------------------------------------------
# Shared resources & session
# ---------------------------------------------------------------------------


@st.cache_resource
def _get_db() -> Database:
    """One Database for the whole process (its methods open per-call conns).

    Side effect: on first construction, seeds the dev-mode default admin
    account if the database is empty and the instructor-token gate is
    not in force. See `auth.ensure_default_admin` for the policy.
    """
    db = Database(_DB_PATH)
    auth.ensure_default_admin(db)
    return db


def _svc() -> GameService:
    return GameService(_get_db())


st.session_state.setdefault("user", None)


def _set_user(row) -> None:
    st.session_state.user = {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
    }


# ---------------------------------------------------------------------------
# Cookie-backed session persistence
# ---------------------------------------------------------------------------
#
# A logged-in user gets a server-side session row (via `auth.create_session`)
# whose token rides in an HTTPS cookie called `auth.SESSION_COOKIE`. On every
# script run we read the cookie; if the token resolves to a live session, we
# populate `st.session_state.user` and skip the login screen.
#
# Timing note: the cookie value arrives via a JS bridge inside
# `extra_streamlit_components.CookieManager`. On the very first script run
# after a hard refresh, `get_all()` may return `{}` until the bridge has
# replied — Streamlit then triggers a follow-up rerun where the cookie is
# visible. The result is a brief "login screen flash" on hard refresh; once
# the cookie lands the user is auto-logged-in.


_cookie_manager = stx.CookieManager(key="solar_sim_cookies")
_cookies = _cookie_manager.get_all(key="cookies_get_all") or {}


def _current_session_token() -> str:
    """The session token currently in the browser cookie, or '' if none."""
    return _cookies.get(auth.SESSION_COOKIE, "") if _cookies else ""


def _restore_session_from_cookie() -> None:
    """Populate `session_state.user` from a valid cookie, if present."""
    if st.session_state.user is not None:
        return
    token = _current_session_token()
    if not token:
        return
    user = auth.lookup_session(_get_db(), token)
    if user is None:
        # Stale token — clear the cookie so we don't keep retrying.
        _cookie_manager.delete(auth.SESSION_COOKIE, key="cookies_del_stale")
        return
    _set_user(user)


def _login_with_cookie(user_row) -> None:
    """Set the in-session user, mint a server session and cookie."""
    _set_user(user_row)
    token = auth.create_session(_get_db(), int(user_row["id"]))
    _cookie_manager.set(
        auth.SESSION_COOKIE,
        token,
        key="cookies_set_login",
        expires_at=datetime.now(timezone.utc) + auth.SESSION_DURATION,
    )


def _logout_and_clear_cookie() -> None:
    """End the server session, drop the cookie, and clear session_state."""
    token = _current_session_token()
    if token:
        auth.end_session(_get_db(), token)
    _cookie_manager.delete(auth.SESSION_COOKIE, key="cookies_del_logout")
    st.session_state.user = None


# ---------------------------------------------------------------------------
# Login / registration
# ---------------------------------------------------------------------------


def _render_auth() -> None:
    st.title("solar-sim")
    st.caption("A multi-team classroom business simulation — solar-PV industry")

    tab_login, tab_register = st.tabs(["Log in", "Create an account"])

    with tab_login:
        # Dev-mode convenience: when the registration gate isn't in force,
        # surface the seeded default admin credentials so a fresh clone is
        # testable without going through registration. Hidden in production
        # mode (env var set) where no such account is seeded.
        if not auth.instructor_token_required():
            st.caption(
                f"Default dev account: **{auth.DEFAULT_ADMIN_EMAIL}** / "
                f"**{auth.DEFAULT_ADMIN_PASSWORD}** "
                "(disabled when $SOLAR_SIM_INSTRUCTOR_TOKEN is set)."
            )
        email = st.text_input(
            "Username or email",
            key="login_email",
            help="Whatever you chose when registering.",
        )
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Log in", type="primary"):
            user = auth.authenticate(_get_db(), email, password)
            if user is None:
                st.error("Incorrect username/email or password.")
            else:
                _login_with_cookie(user)
                st.rerun()

    with tab_register:
        name = st.text_input("Display name", key="reg_name")
        email = st.text_input(
            "Username or email",
            key="reg_email",
            help=(
                "Pick a short username (e.g. `alice`) or use your email. "
                "Whatever you enter is what you'll log in with."
            ),
        )
        password = st.text_input(
            "Password (at least 8 characters)", type="password", key="reg_pw"
        )
        role_label = st.selectbox("I am a…", ["Student", "Instructor"], key="reg_role")
        # Only the deployment's administrator knows the instructor token, so
        # surface the field only when a token is configured AND the user is
        # asking for an instructor account. Students never see it.
        token_required = (
            role_label == "Instructor" and auth.instructor_token_required()
        )
        instructor_token = ""
        if token_required:
            instructor_token = st.text_input(
                "Instructor registration token",
                type="password",
                key="reg_instr_token",
                help=(
                    "Set by the administrator via the "
                    f"${auth.INSTRUCTOR_TOKEN_ENV} environment variable."
                ),
            )
        if st.button("Create account", type="primary"):
            role = "instructor" if role_label == "Instructor" else "student"
            try:
                uid = auth.register_user(
                    _get_db(), email, name, password, role,
                    instructor_token=instructor_token or None,
                )
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                _login_with_cookie(_get_db().get_user(uid))
                st.rerun()


def _render_sidebar(user: dict) -> None:
    with st.sidebar:
        st.title("solar-sim")
        st.write(f"**{user['display_name']}**")
        st.caption(f"{user['email']} · {user['role']}")
        if st.button("Log out"):
            _logout_and_clear_cookie()
            st.rerun()


# ---------------------------------------------------------------------------
# Shared period header
# ---------------------------------------------------------------------------


def _render_period_header(cohort, fc, expand_briefing: bool) -> None:
    """Headline, economy line, briefing expander, and final-period warning."""
    st.markdown(f"### Period {fc.period}")
    if fc.event is not None:
        if fc.event.headline:
            st.caption(fc.event.headline)
        if fc.event.economy:
            st.caption(" · ".join(f"{k}: {v}" for k, v in fc.event.economy.items()))
        briefing = load_narrative(cohort["scenario_path"], fc.event)
        if briefing:
            with st.expander("Period briefing", expanded=expand_briefing):
                st.markdown(briefing)
                _offer_pdf_download(
                    briefing,
                    filename=f"briefing-period-{fc.period}.pdf",
                    title=f"Period {fc.period} briefing",
                    label="Download briefing as PDF",
                    key=f"briefing_pdf_{cohort['id']}_{fc.period}",
                )
    for b in fc.bulk_buyers:
        st.info(
            f"Bulk buyer: up to {b.max_units_per_company:,} units of "
            f"{b.product} at €{b.price:,.0f}/unit."
        )
    for t in fc.tenders:
        cap = (
            f"max €{t.max_acceptable_price:,.0f}"
            if t.max_acceptable_price is not None
            else "no price cap"
        )
        st.info(
            f"Tender: {t.units_required:,} units of {t.product} "
            f"({cap}); lowest valid bid wins."
        )
    if fc.is_final:
        st.warning("This is the final scored period — equity at its close is the result.")


# ---------------------------------------------------------------------------
# Instructor
# ---------------------------------------------------------------------------


def _render_instructor(user: dict) -> None:
    db = _get_db()
    st.header("Instructor")

    cohorts = db.list_cohorts(instructor_id=user["id"])
    with st.expander("Create a new cohort", expanded=not cohorts):
        _render_create_cohort(user)

    if not cohorts:
        st.info("Create a cohort to begin.")
        return

    labels = {c["id"]: f"{c['name']}  (#{c['id']})" for c in cohorts}
    cohort_id = st.selectbox(
        "Cohort",
        [c["id"] for c in cohorts],
        format_func=lambda i: labels[i],
        key="instr_cohort",
    )
    _render_cohort_detail(db.get_cohort(cohort_id))


def _render_create_cohort(user: dict) -> None:
    name = st.text_input("Cohort name", key="cc_name")
    scenario = st.text_input(
        "Scenario pack folder", value=_DEFAULT_SCENARIO, key="cc_scenario"
    )
    names_raw = st.text_area(
        "Team names (one per line)",
        value="Team A\nTeam B\nTeam C",
        height=120,
        key="cc_teams",
    )
    if st.button("Create cohort", type="primary"):
        team_names = [n.strip() for n in names_raw.splitlines() if n.strip()]
        if not name.strip():
            st.error("Enter a cohort name.")
        elif not team_names:
            st.error("Enter at least one team name.")
        else:
            try:
                _svc().create_cohort(
                    user["id"], name.strip(), scenario, team_names
                )
            except ServiceError as exc:
                st.error(str(exc))
            else:
                st.success(f"Created cohort “{name.strip()}”.")
                st.rerun()


def _render_cohort_detail(cohort) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]
    finished = cohort["status"] == "finished"
    upcoming = svc.upcoming_period(cohort_id)

    st.subheader(cohort["name"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Completed periods", cohort["current_period"])
    c2.metric("Teams", len(db.list_teams(cohort_id)))
    c3.metric("Status", "Finished" if finished else f"Period {upcoming} open")

    tabs = st.tabs(
        [
            "Run period",
            "Teams & members",
            "Reports",
            "Planning quality",
            "Strategy maps",
            "Peer reviews",
            "Board export",
        ]
    )
    with tabs[0]:
        _render_run_panel(cohort)
    with tabs[1]:
        _render_members(cohort)
    with tabs[2]:
        _render_reports(cohort, role="instructor")
    with tabs[3]:
        _render_planning_quality(cohort, role="instructor")
    with tabs[4]:
        _render_strategy(cohort, role="instructor")
    with tabs[5]:
        _render_peer_review(cohort, role="instructor")
    with tabs[6]:
        _render_board_export(cohort, role="instructor")


def _render_run_panel(cohort) -> None:
    svc = _svc()
    cohort_id = cohort["id"]

    if cohort["status"] == "finished":
        st.success("This cohort has played all of its periods.")
        return

    upcoming = svc.upcoming_period(cohort_id)
    fc = form_context(svc.load_pack(cohort_id), upcoming)
    _render_period_header(cohort, fc, expand_briefing=False)

    # Auto-refreshing dashboard + run controls (see fragment below).
    _render_run_dashboard(cohort_id, upcoming)

    # Read-only view of each team's draft, below the dashboard.
    _render_team_drafts(cohort_id, upcoming)


def _render_team_drafts(cohort_id: int, upcoming: int) -> None:
    svc = _svc()
    db = _get_db()
    st.markdown("#### Team drafts (read-only)")
    st.caption(
        "What each team has entered for the upcoming period so far. The "
        "dashboard above auto-refreshes; this section updates when the page "
        "reruns."
    )
    for team in db.list_teams(cohort_id):
        status = svc.decision_status(cohort_id, team["id"], upcoming)
        suffix = {
            "submitted": "  ·  ✓ submitted",
            "draft": "  ·  draft",
            "none": "  ·  no decision yet",
        }[status]
        with st.expander(f"{team['name']}{suffix}"):
            decision = svc.get_decision(cohort_id, team["id"], upcoming)
            if decision is None:
                st.caption("No decision entered yet.")
                continue
            _render_draft_summary(decision)


def _render_draft_summary(decision) -> None:
    """Compact read-only summary of one team's decision — for instructors."""
    rnd_by_p = {r.product: r for r in decision.rnd.by_product}
    prod_by_p = {p.product: p for p in decision.production.by_product}
    rows = []
    for sd in decision.sales.by_product:
        rnd = rnd_by_p.get(sd.product)
        prod = prod_by_p.get(sd.product)
        m1 = sd.market_1
        rows.append(
            {
                "Product": sd.product,
                "Price M1": f"€{m1.price:,.0f}" if m1 else "—",
                "Target volume": f"{prod.target_volume:,}" if prod else "—",
                "R&D heads": rnd.researchers if rnd else 0,
                "Advertising M1": f"€{m1.advertising:,.0f}" if m1 else "—",
            }
        )
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")

    col_hr, col_fin = st.columns(2)
    pk = decision.finance.planned_kpis
    with col_hr:
        st.caption("HR & finance")
        st.dataframe(
            [
                {"Item": "Workforce Δ",
                 "Value": f"{decision.hr.production_workforce_change:+d}"},
                {"Item": "Training / employee",
                 "Value": f"€{decision.hr.training_per_employee:,.0f}"},
                {"Item": "Process-opt spend",
                 "Value": f"€{decision.hr.process_optimisation_spend:,.0f}"},
                {"Item": "Short-term loan",
                 "Value": f"€{decision.finance.short_term_loan:,.0f}"},
                {"Item": "Dividend",
                 "Value": f"€{decision.finance.dividend:,.0f}"},
            ],
            hide_index=True,
            width="stretch",
        )
    with col_fin:
        st.caption("Planned KPIs")
        st.dataframe(
            [
                {"Item": "Revenue", "Value": f"€{pk.revenue:,.0f}"},
                {"Item": "Return on equity",
                 "Value": f"{pk.return_on_equity:.1%}"},
                {"Item": "Operating cash flow",
                 "Value": f"€{pk.operating_cash_flow:,.0f}"},
            ],
            hide_index=True,
            width="stretch",
        )

    with st.expander("Raw decision (JSON)"):
        st.json(decision.model_dump(exclude={"team_id", "period"}))


@st.fragment(run_every=5)
def _render_run_dashboard(cohort_id: int, upcoming: int) -> None:
    """Submission status + run controls, polled every 5 seconds.

    Wrapping these widgets in a fragment means the instructor sees
    submissions arrive without manually refreshing the page — and the
    Run-period button is enabled/disabled in step with the live status.
    Clicking Run triggers a full-app rerun via `st.rerun()` so the rest of
    the UI (period counter, reports) updates too.
    """
    svc = _svc()
    db = _get_db()

    status = svc.submission_status(cohort_id, upcoming)
    teams = db.list_teams(cohort_id)
    label = {"submitted": "✓ submitted", "draft": "draft", "none": "—"}
    st.dataframe(
        [
            {
                "Team": t["name"],
                "Members": len(db.list_team_members(t["id"])),
                "Decision": label[status[t["id"]]],
            }
            for t in teams
        ],
        hide_index=True,
        width="stretch",
    )

    all_submitted = bool(status) and all(
        s == "submitted" for s in status.values()
    )
    override = st.checkbox(
        "Run anyway — use current drafts for teams that have not submitted",
        key=f"override_{cohort_id}",
    )
    if not all_submitted and not override:
        st.caption("Not every team has submitted yet — this view refreshes every 5s.")

    if st.button(
        f"Run period {upcoming}",
        type="primary",
        disabled=not (all_submitted or override),
    ):
        try:
            new_period = svc.run_next_period(
                cohort_id, require_all_submitted=not override
            )
        except (ServiceError, InvalidDecisionError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Period {new_period} complete.")
            st.rerun()


def _render_onboarding_panel(cohort) -> None:
    """Copy-paste instructions the instructor can send to students."""
    public_url = os.environ.get("SOLAR_SIM_PUBLIC_URL", "").strip()
    url_line = public_url if public_url else "<paste your app URL here>"
    with st.expander("Onboarding instructions for students", expanded=False):
        st.caption(
            "Share the message below with your students. They register "
            "themselves, then appear in the 'Assign a student to a team' "
            "list below — their screen updates automatically once you "
            "assign them. "
            + (
                ""
                if public_url
                else "Set `$SOLAR_SIM_PUBLIC_URL` on the server to "
                "pre-fill the URL here."
            )
        )
        st.code(
            f"""Hi! We're playing the solar-sim business simulation in class.

1. Open: {url_line}
2. Click "Create an account".
3. Pick a short username (e.g. your first name) or use your email,
   plus a password (8+ characters). Leave the role on "Student".
4. After registering, you'll see a "waiting for assignment" screen.
   Don't reload — once I add you to a team, the screen will switch
   to your team's dashboard automatically.
5. Cohort: {cohort['name']}""",
            language="text",
        )


def _render_members(cohort) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]
    teams = db.list_teams(cohort_id)

    _render_onboarding_panel(cohort)

    st.markdown("#### Teams")
    for team in teams:
        members = db.list_team_members(team["id"])
        with st.expander(f"{team['name']} — {len(members)} member(s)"):
            if not members:
                st.caption("No members yet.")
            for m in members:
                left, right = st.columns([4, 1])
                left.write(f"{m['display_name']} · {m['email']}")
                if right.button("Remove", key=f"rm_{team['id']}_{m['id']}"):
                    svc.unassign_student(cohort_id, m["id"])
                    st.rerun()

    st.markdown("#### Assign a student to a team")
    students = db.list_users(role="student")
    if not students:
        st.caption("No students have registered yet.")
        return

    def _student_label(uid: int) -> str:
        s = next(s for s in students if s["id"] == uid)
        current = db.get_user_team(cohort_id, uid)
        where = current["name"] if current is not None else "unassigned"
        return f"{s['display_name']} ({s['email']}) — {where}"

    col_s, col_t = st.columns(2)
    student_id = col_s.selectbox(
        "Student",
        [s["id"] for s in students],
        format_func=_student_label,
        key=f"assign_student_{cohort_id}",
    )
    team_id = col_t.selectbox(
        "Team",
        [t["id"] for t in teams],
        format_func=lambda i: next(t["name"] for t in teams if t["id"] == i),
        key=f"assign_team_{cohort_id}",
    )
    if st.button("Assign"):
        svc.assign_student(cohort_id, team_id, student_id)
        st.success("Assigned.")
        st.rerun()


# ---------------------------------------------------------------------------
# Reports (shared by both roles)
# ---------------------------------------------------------------------------


def _render_reports(cohort, role: str, team_id: int = None) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]
    completed = cohort["current_period"]

    if completed < 1:
        st.info("No periods have been run yet.")
        return

    period = st.selectbox(
        "Period",
        list(range(1, completed + 1)),
        index=completed - 1,
        key=f"report_period_{role}_{cohort_id}",
    )

    if role == "instructor":
        teams = db.list_teams(cohort_id)
        tabs = st.tabs([t["name"] for t in teams] + ["Industry"])
        for i, team in enumerate(teams):
            with tabs[i]:
                bundle = svc.get_report(cohort_id, team["id"], period)
                if bundle is not None:
                    views.show_report_bundle(bundle)
                else:
                    st.caption("No report for this team.")
        with tabs[-1]:
            industry = svc.get_industry_report(cohort_id, period)
            if industry is not None:
                views.show_industry_report(industry)
    else:
        bundle = svc.get_report(cohort_id, team_id, period)
        if bundle is None:
            st.caption("No report for this period.")
            return
        views.show_report_bundle(bundle)
        if bundle.industry is not None:
            st.markdown("#### Industry report")
            views.show_industry_report(bundle.industry)


# ---------------------------------------------------------------------------
# Pedagogy: planning quality
# ---------------------------------------------------------------------------


def _fmt_kpi(name: str, value: float) -> str:
    """KPI-aware formatting: ROE as percent, money as compact EUR."""
    if name == "Return on equity":
        return f"{value:.1%}"
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:,.1f}k"
    return f"€{value:,.0f}"


def _show_team_planning_quality(tpq, show_headline: bool = True) -> None:
    if not tpq.periods:
        st.caption("No periods scored yet.")
        return
    if show_headline:
        col_h, col_n = st.columns(2)
        if tpq.headline_score is not None:
            col_h.metric(
                "Planning quality (real periods)",
                f"{tpq.headline_score:.1%}",
            )
        else:
            col_h.metric("Planning quality (real periods)", "—")
        col_n.metric("Real periods scored", tpq.real_period_count)
        if tpq.headline_score is None and tpq.periods:
            st.caption(
                "Trial periods are scored below; the headline begins once "
                "the first real period is complete."
            )
    for p in tpq.periods:
        label = "Real" if p.is_real_period else "Trial"
        st.markdown(
            f"**Period {p.period}** · {label} · period score **{p.period_score:.1%}**"
        )
        st.dataframe(
            [
                {
                    "KPI": k.name,
                    "Planned": _fmt_kpi(k.name, k.planned),
                    "Actual": _fmt_kpi(k.name, k.actual),
                    "Score": f"{k.score:.1%}",
                }
                for k in p.kpis
            ],
            hide_index=True,
            width="stretch",
        )


def _render_planning_quality(cohort, role: str, team_id: int = None) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]

    if cohort["current_period"] < 1:
        st.info("Planning quality appears after the first period has been run.")
        return

    if role == "student":
        _show_team_planning_quality(svc.team_planning_quality(cohort_id, team_id))
        return

    # Instructor: a headline table across teams, then per-team detail.
    teams = db.list_teams(cohort_id)
    table = []
    for team in teams:
        tpq = svc.team_planning_quality(cohort_id, team["id"])
        table.append(
            {
                "Team": team["name"],
                "Real periods scored": tpq.real_period_count,
                "Headline": (
                    f"{tpq.headline_score:.1%}"
                    if tpq.headline_score is not None
                    else "—"
                ),
            }
        )
    st.dataframe(table, hide_index=True, width="stretch")

    for team in teams:
        with st.expander(f"{team['name']} — period-by-period"):
            _show_team_planning_quality(
                svc.team_planning_quality(cohort_id, team["id"]),
                show_headline=False,
            )


# ---------------------------------------------------------------------------
# Pedagogy: strategy map
# ---------------------------------------------------------------------------


def _render_strategy(
    cohort, role: str, team_id: int = None, user_id: int = None
) -> None:
    svc = _svc()
    cohort_id = cohort["id"]

    if role == "student":
        sm = svc.get_strategy_map(cohort_id, team_id)
        st.markdown(
            "Author your team's **balanced-scorecard strategy**. Each "
            "perspective takes freeform Markdown — list objectives, "
            "measures, targets and initiatives as you see fit."
        )
        col_f, col_c = st.columns(2)
        financial = col_f.text_area(
            "Financial",
            value=sm.financial,
            height=180,
            key=f"sm_fin_{cohort_id}_{team_id}",
            help="What financial results does the team aim for?",
        )
        customer = col_c.text_area(
            "Customer",
            value=sm.customer,
            height=180,
            key=f"sm_cus_{cohort_id}_{team_id}",
            help="How does the team intend to be seen by its customers?",
        )
        col_p, col_l = st.columns(2)
        process = col_p.text_area(
            "Internal process",
            value=sm.internal_process,
            height=180,
            key=f"sm_ip_{cohort_id}_{team_id}",
            help="What internal operations does the strategy depend on?",
        )
        learning = col_l.text_area(
            "Learning & growth",
            value=sm.learning_growth,
            height=180,
            key=f"sm_lg_{cohort_id}_{team_id}",
            help="What capabilities must the team build over the simulation?",
        )
        if st.button("Save strategy", type="primary"):
            svc.save_strategy_map(
                cohort_id,
                team_id,
                financial,
                customer,
                process,
                learning,
                user_id,
            )
            st.toast("Strategy saved.")
            st.rerun()
        if sm.updated_at:
            st.caption(f"Last updated: {sm.updated_at}")
        return

    # Instructor: read-only view of every team's strategy.
    db = _get_db()
    teams = db.list_teams(cohort_id)
    for team in teams:
        sm = svc.get_strategy_map(cohort_id, team["id"])
        suffix = "  ·  empty" if sm.is_empty else ""
        with st.expander(f"{team['name']}{suffix}"):
            if sm.is_empty:
                st.caption("This team has not authored a strategy yet.")
                continue
            for label, text in (
                ("Financial", sm.financial),
                ("Customer", sm.customer),
                ("Internal process", sm.internal_process),
                ("Learning & growth", sm.learning_growth),
            ):
                st.markdown(f"**{label}**")
                st.markdown(text.strip() or "_(empty)_")
            if sm.updated_at:
                st.caption(f"Last updated: {sm.updated_at}")


# ---------------------------------------------------------------------------
# Pedagogy: peer assessment
# ---------------------------------------------------------------------------


def _fmt_mean(value) -> str:
    return f"{value:.1f}" if value is not None else "—"


def _render_peer_review(
    cohort, role: str, team_id: int = None, user_id: int = None
) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]
    finished = cohort["status"] == "finished"

    if role == "student":
        if finished:
            agg = svc.my_aggregated_rating(cohort_id, user_id)
            if agg is None or agg.n_raters == 0:
                st.info("No peer ratings were recorded for you in this cohort.")
                return
            st.markdown(
                f"### Your peer ratings  ·  {agg.n_raters} rater(s)"
            )
            cols = st.columns(5)
            cols[0].metric("Contribution", _fmt_mean(agg.contribution_mean))
            cols[1].metric("Collaboration", _fmt_mean(agg.collaboration_mean))
            cols[2].metric("Reliability", _fmt_mean(agg.reliability_mean))
            cols[3].metric("Communication", _fmt_mean(agg.communication_mean))
            cols[4].metric(
                "Overall",
                f"{agg.overall_mean:.2f}" if agg.overall_mean is not None else "—",
            )
            st.caption(
                "Means per dimension across your raters, on a 1–5 scale. "
                "Comments are visible to the instructor only."
            )
            return

        targets = svc.team_peer_targets(cohort_id, user_id)
        if not targets:
            st.info(
                "You have no teammates to rate yet — check back once your "
                "instructor has added more students to your team."
            )
            return
        st.markdown(
            "Rate each teammate from **1** (lowest) to **5** (highest) on "
            "the four dimensions, plus an optional comment. You can edit "
            "any time the cohort is active; ratings are locked when the "
            "cohort closes. Only the instructor sees your individual "
            "ratings while the cohort runs."
        )
        for member in targets:
            existing = svc.get_my_rating(cohort_id, user_id, member["id"])
            tag = "  ·  rated" if existing is not None else ""
            with st.expander(f"{member['display_name']}{tag}"):
                c1, c2, c3, c4 = st.columns(4)
                contribution = c1.number_input(
                    "Contribution",
                    min_value=1, max_value=5, step=1,
                    value=int(existing.contribution) if existing else 3,
                    key=f"pr_contrib_{cohort_id}_{member['id']}",
                )
                collaboration = c2.number_input(
                    "Collaboration",
                    min_value=1, max_value=5, step=1,
                    value=int(existing.collaboration) if existing else 3,
                    key=f"pr_collab_{cohort_id}_{member['id']}",
                )
                reliability = c3.number_input(
                    "Reliability",
                    min_value=1, max_value=5, step=1,
                    value=int(existing.reliability) if existing else 3,
                    key=f"pr_reli_{cohort_id}_{member['id']}",
                )
                communication = c4.number_input(
                    "Communication",
                    min_value=1, max_value=5, step=1,
                    value=int(existing.communication) if existing else 3,
                    key=f"pr_comm_{cohort_id}_{member['id']}",
                )
                comments = st.text_area(
                    "Comments (optional, instructor only)",
                    value=existing.comments if existing else "",
                    key=f"pr_text_{cohort_id}_{member['id']}",
                    height=100,
                )
                if st.button(
                    f"Save rating for {member['display_name']}",
                    key=f"pr_save_{cohort_id}_{member['id']}",
                ):
                    try:
                        svc.save_peer_rating(
                            cohort_id,
                            user_id,
                            member["id"],
                            int(contribution),
                            int(collaboration),
                            int(reliability),
                            int(communication),
                            comments,
                        )
                    except ServiceError as exc:
                        st.error(str(exc))
                    else:
                        st.success("Rating saved.")
                        st.rerun()
        return

    # Instructor view: per-team aggregates plus detailed rater→ratee matrix.
    teams = db.list_teams(cohort_id)
    name_by_id = {u["id"]: u["display_name"] for u in db.list_users()}
    if not finished:
        st.caption(
            "Cohort is still active — ratings will continue to come in "
            "until it closes."
        )
    for team in teams:
        members = db.list_team_members(team["id"])
        st.markdown(f"#### {team['name']}")
        if not members:
            st.caption("No members on this team.")
            continue
        aggs = svc.team_peer_aggregates(cohort_id, team["id"])
        st.dataframe(
            [
                {
                    "Ratee": name_by_id.get(a.ratee_id, str(a.ratee_id)),
                    "n raters": a.n_raters,
                    "Contribution": _fmt_mean(a.contribution_mean),
                    "Collaboration": _fmt_mean(a.collaboration_mean),
                    "Reliability": _fmt_mean(a.reliability_mean),
                    "Communication": _fmt_mean(a.communication_mean),
                    "Overall": (
                        f"{a.overall_mean:.2f}"
                        if a.overall_mean is not None
                        else "—"
                    ),
                }
                for a in aggs
            ],
            hide_index=True,
            width="stretch",
        )
        with st.expander("Detailed ratings (rater → ratee)"):
            ratings = svc.peer_ratings_for_team(cohort_id, team["id"])
            if not ratings:
                st.caption("No ratings yet.")
            else:
                st.dataframe(
                    [
                        {
                            "Rater": name_by_id.get(r.rater_id, str(r.rater_id)),
                            "Ratee": name_by_id.get(r.ratee_id, str(r.ratee_id)),
                            "Contrib": r.contribution,
                            "Collab": r.collaboration,
                            "Reli": r.reliability,
                            "Comm": r.communication,
                            "Overall": f"{r.overall:.2f}",
                            "Comments": r.comments,
                        }
                        for r in ratings
                    ],
                    hide_index=True,
                    width="stretch",
                )


# ---------------------------------------------------------------------------
# Pedagogy: board-meeting export
# ---------------------------------------------------------------------------


def _safe_filename_piece(text: str) -> str:
    """Make a string safe for a filename — keep alnums, '-' and '_'."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in text)


def _offer_pdf_download(
    md_text: str,
    *,
    filename: str,
    title: str,
    label: str,
    key: str,
    primary: bool = False,
) -> None:
    """Render a PDF download button, or a caption if PDF deps are missing."""
    if not pdf_export.PDF_AVAILABLE:
        st.caption(
            "PDF download unavailable on this server "
            "(install `markdown` and `weasyprint`)."
        )
        return
    try:
        pdf_bytes = pdf_export.markdown_to_pdf(md_text, title=title)
    except Exception as exc:  # pragma: no cover - defensive
        st.caption(f"PDF rendering failed: {exc}")
        return
    st.download_button(
        label,
        data=pdf_bytes,
        file_name=filename,
        mime="application/pdf",
        type="primary" if primary else "secondary",
        key=key,
    )


def _render_board_export(
    cohort, role: str, team_id: int = None, user_id: int = None
) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]

    st.markdown(
        "The capstone deliverable — every team's reports, planning quality, "
        "strategy map and peer-assessment summary in one portable PDF "
        "document, with a preview below."
    )

    if role == "instructor":
        teams = db.list_teams(cohort_id)
        if not teams:
            st.caption("No teams in this cohort yet.")
            return
        target_id = st.selectbox(
            "Team",
            [t["id"] for t in teams],
            format_func=lambda i: next(t["name"] for t in teams if t["id"] == i),
            key=f"be_team_{cohort_id}",
        )
        target = db.get_team(target_id)
    else:
        target = db.get_team(team_id)

    try:
        document = svc.build_board_document(
            cohort_id,
            target["id"],
            viewer_role=role,
            viewer_user_id=user_id if role == "student" else None,
        )
    except ServiceError as exc:
        st.error(str(exc))
        return

    filename = (
        f"board-meeting-{_safe_filename_piece(cohort['name'])}-"
        f"{_safe_filename_piece(target['name'])}-{date.today().isoformat()}.pdf"
    )
    _offer_pdf_download(
        document,
        filename=filename,
        title=f"Board meeting — {target['name']}",
        label="Download as PDF",
        key=f"be_download_{cohort_id}_{target['id']}",
        primary=True,
    )

    with st.expander("Preview document", expanded=False):
        st.markdown(document)


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------


@st.fragment(run_every=3)
def _render_waiting_for_assignment(user: dict) -> None:
    """Polls the cohort assignment so the student doesn't have to reload."""
    db = _get_db()
    if db.list_cohorts_for_user(user["id"]):
        # Just got assigned — rerun the whole app so the team view appears.
        st.rerun(scope="app")
    st.info(
        "You're registered as **"
        f"{user['display_name']}** ("
        f"`{user['email']}`). Your instructor needs to add you to a "
        "team — give them your username if they're nearby, otherwise "
        "wait a moment. This screen updates automatically when you're "
        "assigned, no need to reload."
    )


def _render_student(user: dict) -> None:
    db = _get_db()
    st.header("My team")

    cohorts = db.list_cohorts_for_user(user["id"])
    if not cohorts:
        _render_waiting_for_assignment(user)
        return

    cohort_id = st.selectbox(
        "Cohort",
        [c["id"] for c in cohorts],
        format_func=lambda i: next(c["name"] for c in cohorts if c["id"] == i),
        key="student_cohort",
    )
    cohort = db.get_cohort(cohort_id)
    team = db.get_user_team(cohort_id, user["id"])

    st.subheader(f"{cohort['name']} — {team['name']}")
    tabs = st.tabs(
        [
            "Decision",
            "Reports",
            "Planning quality",
            "Strategy",
            "Peer review",
            "Board export",
        ]
    )
    with tabs[0]:
        _render_student_decision(user, cohort, team)
    with tabs[1]:
        _render_reports(cohort, role="student", team_id=team["id"])
    with tabs[2]:
        _render_planning_quality(cohort, role="student", team_id=team["id"])
    with tabs[3]:
        _render_strategy(
            cohort, role="student", team_id=team["id"], user_id=user["id"]
        )
    with tabs[4]:
        _render_peer_review(
            cohort, role="student", team_id=team["id"], user_id=user["id"]
        )
    with tabs[5]:
        _render_board_export(
            cohort, role="student", team_id=team["id"], user_id=user["id"]
        )


def _render_student_decision(user: dict, cohort, team) -> None:
    svc = _svc()
    cohort_id = cohort["id"]

    if cohort["status"] == "finished":
        st.success("The simulation is complete — see the Reports tab.")
        return

    upcoming = svc.upcoming_period(cohort_id)
    fc = form_context(svc.load_pack(cohort_id), upcoming)
    company_id = team["company_id"]

    _render_period_header(cohort, fc, expand_briefing=True)

    if svc.decision_status(cohort_id, team["id"], upcoming) == "submitted":
        st.success("Your decision for this period is submitted and locked.")
        st.caption("Unlock it if you need to make further changes before the deadline.")
        if st.button("Unlock to edit"):
            svc.reopen_decision(cohort_id, team["id"], upcoming)
            st.rerun()
        return

    defaults = svc.get_decision(cohort_id, team["id"], upcoming)
    if defaults is None:
        defaults = forms.default_decision(company_id, upcoming, fc.product_ids)

    st.markdown("#### Enter your decision")
    decision = forms.team_decision_form(
        team_id=company_id,
        period=upcoming,
        product_ids=fc.product_ids,
        launchable_product_ids=fc.launchable_product_ids,
        catalog_types=fc.catalog_types,
        defaults=defaults,
        market_2_open=fc.market_2_open,
        bulk_offer_products=fc.bulk_products,
        tender_products=fc.tender_products,
    )

    errors = svc.validate(cohort_id, team["id"], upcoming, decision)
    if errors:
        st.error("Fix before submitting — " + " · ".join(errors))
    else:
        st.success("All decisions pass validation.")

    col_save, col_submit = st.columns(2)
    if col_save.button("Save draft"):
        svc.save_draft(cohort_id, team["id"], upcoming, decision, user["id"])
        st.toast("Draft saved.")
    if col_submit.button(
        "Submit for the period", type="primary", disabled=bool(errors)
    ):
        try:
            svc.submit_decision(
                cohort_id, team["id"], upcoming, decision, user["id"]
            )
        except ServiceError as exc:
            st.error(str(exc))
        else:
            st.success("Decision submitted.")
            st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

# Try to auto-login from a cookie (sets st.session_state.user if a valid
# session token is in the browser); on the very first run after a refresh
# the cookies may not have arrived yet — the next rerun catches them.
_restore_session_from_cookie()

_user = st.session_state.user
if _user is None:
    _render_auth()
else:
    _render_sidebar(_user)
    if _user["role"] == "instructor":
        _render_instructor(_user)
    else:
        _render_student(_user)
