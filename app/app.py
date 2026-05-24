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
from pathlib import Path

# Make the engine importable without installing it (dev convenience).
_ENGINE_SRC = Path(__file__).resolve().parent.parent / "sim-engine" / "src"
if str(_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SRC))

import streamlit as st  # noqa: E402

from sim_engine.validation import InvalidDecisionError  # noqa: E402

import auth  # noqa: E402
import forms  # noqa: E402
import views  # noqa: E402
from db import Database  # noqa: E402
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
    """One Database for the whole process (its methods open per-call conns)."""
    return Database(_DB_PATH)


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
# Login / registration
# ---------------------------------------------------------------------------


def _render_auth() -> None:
    st.title("solar-sim")
    st.caption("A multi-team classroom business simulation — solar-PV industry")

    tab_login, tab_register = st.tabs(["Log in", "Create an account"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Log in", type="primary"):
            user = auth.authenticate(_get_db(), email, password)
            if user is None:
                st.error("Incorrect email or password.")
            else:
                _set_user(user)
                st.rerun()

    with tab_register:
        name = st.text_input("Display name", key="reg_name")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input(
            "Password (at least 8 characters)", type="password", key="reg_pw"
        )
        role_label = st.selectbox("I am a…", ["Student", "Instructor"], key="reg_role")
        if st.button("Create account", type="primary"):
            role = "instructor" if role_label == "Instructor" else "student"
            try:
                uid = auth.register_user(_get_db(), email, name, password, role)
            except auth.AuthError as exc:
                st.error(str(exc))
            else:
                _set_user(_get_db().get_user(uid))
                st.rerun()


def _render_sidebar(user: dict) -> None:
    with st.sidebar:
        st.title("solar-sim")
        st.write(f"**{user['display_name']}**")
        st.caption(f"{user['email']} · {user['role']}")
        if st.button("Log out"):
            st.session_state.user = None
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


def _render_run_panel(cohort) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]

    if cohort["status"] == "finished":
        st.success("This cohort has played all of its periods.")
        return

    upcoming = svc.upcoming_period(cohort_id)
    fc = form_context(svc.load_pack(cohort_id), upcoming)
    _render_period_header(cohort, fc, expand_briefing=False)

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
        st.caption("Not every team has submitted yet.")

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


def _render_members(cohort) -> None:
    svc = _svc()
    db = _get_db()
    cohort_id = cohort["id"]
    teams = db.list_teams(cohort_id)

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
# Student
# ---------------------------------------------------------------------------


def _render_student(user: dict) -> None:
    db = _get_db()
    st.header("My team")

    cohorts = db.list_cohorts_for_user(user["id"])
    if not cohorts:
        st.info(
            "You have not been assigned to a team yet. Ask your instructor "
            "to add you to a cohort, then reload this page."
        )
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
    tabs = st.tabs(["Decision", "Reports", "Planning quality", "Strategy"])
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

_user = st.session_state.user
if _user is None:
    _render_auth()
else:
    _render_sidebar(_user)
    if _user["role"] == "instructor":
        _render_instructor(_user)
    else:
        _render_student(_user)
