"""solar-sim — Instructor Console.

A Streamlit app for running a cohort of the solar-sim business simulation.
The instructor loads a scenario, sets up teams, enters each team's decisions,
runs the period, and reviews the per-team and industry reports.

Run it with:

    cd solar-sim
    streamlit run app/instructor_console.py

No database or login: cohort state lives in the Streamlit session and can
be saved to / loaded from a JSON file via the sidebar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make the engine importable without installing it (dev convenience).
_ENGINE_SRC = Path(__file__).resolve().parent.parent / "sim-engine" / "src"
if str(_ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SRC))

import streamlit as st  # noqa: E402

from sim_engine.context import resolve_period_context  # noqa: E402
from sim_engine.decisions import TeamDecision  # noqa: E402
from sim_engine.engine import build_initial_state, run_period  # noqa: E402
from sim_engine.scenario import load_scenario_pack  # noqa: E402
from sim_engine.state import PeriodState  # noqa: E402
from sim_engine.validation import validate_decision  # noqa: E402

import forms  # noqa: E402
import views  # noqa: E402

_DEFAULT_SCENARIO = str(
    Path(__file__).resolve().parent.parent / "scenarios" / "solar-v1"
)

st.set_page_config(page_title="solar-sim — Instructor Console", layout="wide")


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


def _init_session() -> None:
    st.session_state.setdefault("pack", None)
    st.session_state.setdefault("scenario_path", _DEFAULT_SCENARIO)
    st.session_state.setdefault("period_state", None)
    st.session_state.setdefault("last_decisions", {})   # team_id -> TeamDecision
    st.session_state.setdefault("last_reports", {})      # team_id -> ReportBundle
    st.session_state.setdefault("last_reports_period", None)


_init_session()


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------


def _serialise_game() -> str:
    state: PeriodState = st.session_state.period_state
    payload = {
        "scenario_path": st.session_state.scenario_path,
        "period_state": state.model_dump(),
        "last_decisions": {
            tid: dec.model_dump()
            for tid, dec in st.session_state.last_decisions.items()
        },
    }
    return json.dumps(payload, indent=2)


def _load_game(raw: bytes) -> None:
    payload = json.loads(raw)
    scenario_path = payload["scenario_path"]
    pack = load_scenario_pack(scenario_path)
    state = PeriodState.model_validate(payload["period_state"])
    st.session_state.scenario_path = scenario_path
    st.session_state.pack = pack
    st.session_state.period_state = state
    st.session_state.last_decisions = {
        tid: TeamDecision.model_validate(d)
        for tid, d in payload.get("last_decisions", {}).items()
    }
    st.session_state.last_reports = {}
    st.session_state.last_reports_period = None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def _render_sidebar() -> None:
    with st.sidebar:
        st.title("solar-sim")
        st.caption("Instructor Console")

        if st.session_state.period_state is None:
            st.subheader("Set up a cohort")
            scenario_path = st.text_input(
                "Scenario pack folder", value=st.session_state.scenario_path
            )
            names_raw = st.text_area(
                "Team names (one per line)",
                value="Team A\nTeam B\nTeam C",
                height=140,
            )
            if st.button("Start cohort", type="primary"):
                names = [n.strip() for n in names_raw.splitlines() if n.strip()]
                if not names:
                    st.error("Enter at least one team name.")
                else:
                    try:
                        pack = load_scenario_pack(scenario_path)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Could not load scenario: {exc}")
                    else:
                        st.session_state.pack = pack
                        st.session_state.scenario_path = scenario_path
                        st.session_state.period_state = build_initial_state(
                            pack, cohort_id="cohort", company_ids=names
                        )
                        st.session_state.last_decisions = {}
                        st.session_state.last_reports = {}
                        st.rerun()

            st.divider()
            st.subheader("…or load a saved game")
            uploaded = st.file_uploader("Game file (.json)", type="json")
            if uploaded is not None and st.button("Load game"):
                try:
                    _load_game(uploaded.getvalue())
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not load game: {exc}")
                else:
                    st.rerun()
        else:
            state: PeriodState = st.session_state.period_state
            pack = st.session_state.pack
            st.metric("Completed periods", state.period_index)
            st.metric("Teams", len(state.companies))
            st.caption(f"Scenario: {pack.pack.scenario.id} {pack.pack.scenario.version}")

            st.divider()
            st.download_button(
                "Save game",
                data=_serialise_game(),
                file_name=f"solar-sim-period-{state.period_index}.json",
                mime="application/json",
            )
            if st.button("Reset cohort"):
                st.session_state.period_state = None
                st.session_state.pack = None
                st.session_state.last_decisions = {}
                st.session_state.last_reports = {}
                st.session_state.last_reports_period = None
                st.rerun()


# ---------------------------------------------------------------------------
# Main workspace
# ---------------------------------------------------------------------------


def _load_narrative(event) -> str:
    """Return the period's narrative briefing markdown, or "" if there is none.

    `event.narrative_file` is a path relative to the scenario pack folder.
    """
    if event is None or not getattr(event, "narrative_file", None):
        return ""
    path = Path(st.session_state.scenario_path) / event.narrative_file
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _render_workspace() -> None:
    state: PeriodState = st.session_state.period_state
    pack = st.session_state.pack
    next_period = state.period_index + 1
    ctx = resolve_period_context(pack, next_period)
    event = pack.event_for_period(next_period)

    real_periods = pack.pack.scenario.real_periods
    is_final = next_period >= max(real_periods) if real_periods else False

    st.header(f"Period {next_period}")
    if event is not None:
        phase = event.phase.capitalize()
        st.subheader(f"{phase} period — {event.headline}")
        if event.economy:
            st.caption(" · ".join(f"{k}: {v}" for k, v in event.economy.items()))
        briefing = _load_narrative(event)
        if briefing:
            with st.expander("Period briefing", expanded=True):
                st.markdown(briefing)
    if is_final:
        st.warning("This is the final scored period — equity at its close is the result.")

    # ---- Decision context ----
    product_ids = [
        p.id for p in ctx.products if p.available_from_period <= next_period
    ]
    launchable_product_ids = [
        p.id for p in ctx.products if p.first_launch_period <= next_period
    ]
    catalog_types = [t.type_id for t in pack.pack.production_line_catalog]
    market_2_open = any(
        m.id == "market_2" and m.open_from_period <= next_period
        for m in ctx.markets
    )
    bulk_products = [b.product for b in ctx.bulk_buyers]
    tender_products = [t.product for t in ctx.tenders]

    if ctx.bulk_buyers:
        for b in ctx.bulk_buyers:
            st.info(
                f"Bulk buyer: up to {b.max_units_per_company:,} units of "
                f"{b.product} at €{b.price:,.0f}/unit."
            )
    if ctx.tenders:
        for t in ctx.tenders:
            cap = (
                f"max €{t.max_acceptable_price:,.0f}"
                if t.max_acceptable_price is not None
                else "no price cap"
            )
            st.info(
                f"Tender: {t.units_required:,} units of {t.product} "
                f"({cap}); lowest valid bid wins."
            )

    # ---- Decision entry ----
    st.markdown("## Enter decisions")
    decisions: dict = {}
    expanded = len(state.companies) <= 2
    for company in state.companies:
        with st.expander(f"Team — {company.id}", expanded=expanded):
            defaults = st.session_state.last_decisions.get(company.id)
            if defaults is None:
                defaults = forms.default_decision(
                    company.id, next_period, product_ids
                )
            decisions[company.id] = forms.team_decision_form(
                team_id=company.id,
                period=next_period,
                product_ids=product_ids,
                launchable_product_ids=launchable_product_ids,
                catalog_types=catalog_types,
                defaults=defaults,
                market_2_open=market_2_open,
                bulk_offer_products=bulk_products,
                tender_products=tender_products,
            )

    # ---- Validation preview ----
    problems: dict = {}
    for company in state.companies:
        errs = validate_decision(decisions[company.id], company, ctx)
        if errs:
            problems[company.id] = errs
    if problems:
        for tid, errs in problems.items():
            st.error(f"**{tid}** — " + " · ".join(errs))
    else:
        st.success("All decisions pass validation.")

    # ---- Run the period ----
    if st.button(
        f"Run period {next_period}", type="primary", disabled=bool(problems)
    ):
        new_state, reports = run_period(state, decisions, pack)
        st.session_state.period_state = new_state
        st.session_state.last_decisions = decisions
        st.session_state.last_reports = reports
        st.session_state.last_reports_period = new_state.period_index
        st.rerun()

    # ---- Reports from the most recent run ----
    if st.session_state.last_reports:
        st.divider()
        st.markdown(
            f"## Reports — period {st.session_state.last_reports_period}"
        )
        reports = st.session_state.last_reports
        team_ids = list(reports.keys())
        tabs = st.tabs(team_ids + ["Industry"])
        for i, tid in enumerate(team_ids):
            with tabs[i]:
                views.show_report_bundle(reports[tid])
        with tabs[-1]:
            industry = next(iter(reports.values())).industry
            if industry is not None:
                views.show_industry_report(industry)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_render_sidebar()

if st.session_state.period_state is None:
    st.title("solar-sim — Instructor Console")
    st.markdown(
        "Set up a cohort in the sidebar to begin, or load a saved game.\n\n"
        "This console runs one cohort of the solar-PV business simulation: "
        "load a scenario, enter each team's decisions for the period, run it, "
        "and review the per-team and industry reports."
    )
else:
    _render_workspace()
