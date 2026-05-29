"""Tests for the multi-user layer: db.py, auth.py, service.py.

These exercise the database and the DB-to-engine bridge directly, with no
Streamlit involved. Run from the repo root:

    PYTHONPATH=sim-engine/src:app python3 -m pytest app/test_phase3.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import auth
import board_export
import pedagogy
import sqlite3
from pydantic import ValidationError

from board_export import PeerRatingWithNames, TeamBoardData, render_document
from db import Database
from pedagogy import (
    AggregatedRating,
    KPILine,
    PeerRating,
    PeriodPlanningQuality,
    StrategyMap,
    TeamPlanningQuality,
    aggregate_ratings,
)
from service import GameService, ServiceError, form_context

_SCENARIO = str(Path(__file__).resolve().parent.parent / "scenarios" / "solar-v1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "test.db")


@pytest.fixture
def svc(db) -> GameService:
    return GameService(db)


@pytest.fixture
def instructor(db) -> int:
    return auth.register_user(db, "prof@uni.edu", "Prof", "password1", "instructor")


@pytest.fixture
def cohort(svc, instructor) -> int:
    return svc.create_cohort(
        instructor_id=instructor,
        name="Spring cohort",
        scenario_path=_SCENARIO,
        team_names=["Helios", "Lumen", "Aurora"],
    )


def _submit_all(svc: GameService, db: Database, cohort_id: int, period: int):
    """Submit each team's current draft for `period`."""
    for team in db.list_teams(cohort_id):
        decision = svc.get_decision(cohort_id, team["id"], period)
        svc.submit_decision(cohort_id, team["id"], period, decision, user_id=1)


# ---------------------------------------------------------------------------
# db.py
# ---------------------------------------------------------------------------


def test_db_user_crud(db):
    uid = db.create_user("a@b.c", "Alice", "hash", "student")
    assert db.get_user(uid)["display_name"] == "Alice"
    assert db.get_user_by_email("a@b.c")["id"] == uid
    assert db.get_user(9999) is None


def test_db_cohort_team_membership(db):
    uid = db.create_user("i@x.c", "Ins", "h", "instructor")
    sid = db.create_user("s@x.c", "Stu", "h", "student")
    cid = db.create_cohort("C", "/path", uid)
    tid = db.create_team(cid, "c1", "Team A")
    db.add_team_member(tid, sid)
    assert db.get_user_team(cid, sid)["id"] == tid
    assert [u["id"] for u in db.list_team_members(tid)] == [sid]
    db.remove_team_member(tid, sid)
    assert db.get_user_team(cid, sid) is None


def test_db_period_state_roundtrip(db):
    uid = db.create_user("i@x.c", "Ins", "h", "instructor")
    cid = db.create_cohort("C", "/path", uid)
    db.save_period_state(cid, 0, '{"period": 0}')
    db.save_period_state(cid, 1, '{"period": 1}')
    assert db.latest_period_state(cid) == (1, '{"period": 1}')
    assert db.get_period_state(cid, 0) == '{"period": 0}'


# ---------------------------------------------------------------------------
# auth.py
# ---------------------------------------------------------------------------


def test_auth_hash_roundtrip():
    stored = auth.hash_password("correct horse")
    assert auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong", stored)


def test_auth_register_and_login(db):
    uid = auth.register_user(db, "Stu@X.com ", "Stu", "password1", "student")
    # Email is normalised; login is case-insensitive.
    user = auth.authenticate(db, "stu@x.com", "password1")
    assert user is not None and user["id"] == uid
    assert auth.authenticate(db, "stu@x.com", "nope") is None
    assert auth.authenticate(db, "ghost@x.com", "password1") is None


def test_auth_rejects_duplicate_email(db):
    auth.register_user(db, "dup@x.com", "One", "password1", "student")
    with pytest.raises(auth.AuthError):
        auth.register_user(db, "dup@x.com", "Two", "password2", "student")


def test_auth_rejects_weak_input(db):
    with pytest.raises(auth.AuthError):
        auth.register_user(db, "x@y.com", "X", "short", "student")
    with pytest.raises(auth.AuthError):
        auth.register_user(db, "not-an-email", "X", "password1", "student")
    with pytest.raises(auth.AuthError):
        auth.register_user(db, "x@y.com", "X", "password1", "wizard")


def test_instructor_registration_open_when_env_unset(db, monkeypatch):
    """Default deployment (no env var set) leaves instructor registration open.

    This is the historical behaviour. The token gate is opt-in: an
    administrator sets `SOLAR_SIM_INSTRUCTOR_TOKEN` to lock it down.
    """
    monkeypatch.delenv(auth.INSTRUCTOR_TOKEN_ENV, raising=False)
    assert not auth.instructor_token_required()
    uid = auth.register_user(db, "open@uni.edu", "Prof", "password1", "instructor")
    assert uid > 0


def test_instructor_registration_requires_token_when_env_set(db, monkeypatch):
    """With the env var set, instructor registration without a token is rejected."""
    monkeypatch.setenv(auth.INSTRUCTOR_TOKEN_ENV, "s3cret-classroom-token")
    assert auth.instructor_token_required()
    with pytest.raises(auth.AuthError, match="Instructor registration requires"):
        auth.register_user(db, "noToken@uni.edu", "Prof", "password1", "instructor")


def test_instructor_registration_rejects_wrong_token(db, monkeypatch):
    monkeypatch.setenv(auth.INSTRUCTOR_TOKEN_ENV, "s3cret-classroom-token")
    with pytest.raises(auth.AuthError, match="Instructor registration requires"):
        auth.register_user(
            db, "wrong@uni.edu", "Prof", "password1", "instructor",
            instructor_token="not-the-right-one",
        )


def test_instructor_registration_accepts_correct_token(db, monkeypatch):
    monkeypatch.setenv(auth.INSTRUCTOR_TOKEN_ENV, "s3cret-classroom-token")
    uid = auth.register_user(
        db, "right@uni.edu", "Prof", "password1", "instructor",
        instructor_token="  s3cret-classroom-token  ",  # whitespace-tolerant
    )
    assert uid > 0


def test_student_registration_ignores_instructor_token(db, monkeypatch):
    """The token gate applies only to role=instructor; students are unaffected."""
    monkeypatch.setenv(auth.INSTRUCTOR_TOKEN_ENV, "s3cret-classroom-token")
    uid = auth.register_user(
        db, "stu@uni.edu", "Stu", "password1", "student",
        instructor_token=None,  # explicit: students never present a token
    )
    assert uid > 0


def test_default_admin_seeded_on_empty_db_when_env_unset(db, monkeypatch):
    """Fresh DB + no env var → ensure_default_admin creates the admin row."""
    monkeypatch.delenv(auth.INSTRUCTOR_TOKEN_ENV, raising=False)
    assert auth.ensure_default_admin(db) is True

    row = db.get_user_by_email(auth.DEFAULT_ADMIN_EMAIL)
    assert row is not None
    assert row["display_name"] == auth.DEFAULT_ADMIN_NAME
    assert row["role"] == "instructor"
    # The default password authenticates against the seeded row.
    authed = auth.authenticate(
        db, auth.DEFAULT_ADMIN_EMAIL, auth.DEFAULT_ADMIN_PASSWORD
    )
    assert authed is not None and authed["id"] == row["id"]


def test_default_admin_not_seeded_when_env_set(db, monkeypatch):
    """Production lockdown (env var set) → seed is skipped, DB stays empty."""
    monkeypatch.setenv(auth.INSTRUCTOR_TOKEN_ENV, "s3cret-classroom-token")
    assert auth.ensure_default_admin(db) is False
    assert db.get_user_by_email(auth.DEFAULT_ADMIN_EMAIL) is None


def test_default_admin_not_seeded_when_users_exist(db, monkeypatch):
    """An existing user (any role) suppresses the seed on subsequent calls."""
    monkeypatch.delenv(auth.INSTRUCTOR_TOKEN_ENV, raising=False)
    auth.register_user(db, "first@uni.edu", "First", "password1", "student")
    # First call now sees an existing user → no seed.
    assert auth.ensure_default_admin(db) is False
    assert db.get_user_by_email(auth.DEFAULT_ADMIN_EMAIL) is None


# ---------------------------------------------------------------------------
# service.py — cohort setup
# ---------------------------------------------------------------------------


def test_create_cohort_seeds_state_teams_and_drafts(svc, db, cohort):
    teams = db.list_teams(cohort)
    assert [t["company_id"] for t in teams] == ["c1", "c2", "c3"]
    assert [t["name"] for t in teams] == ["Helios", "Lumen", "Aurora"]

    # Period-0 state exists and carries the chosen team names.
    state = svc.get_state(cohort)
    assert state.period_index == 0
    assert sorted(c.name for c in state.companies) == ["Aurora", "Helios", "Lumen"]

    # Every team has a valid period-1 draft.
    assert svc.upcoming_period(cohort) == 1
    for team in teams:
        decision = svc.get_decision(cohort, team["id"], 1)
        assert decision is not None
        assert svc.validate(cohort, team["id"], 1, decision) == []
    assert svc.submission_status(cohort, 1) == {t["id"]: "draft" for t in teams}


def test_form_context_tracks_product_lifecycle(svc, cohort):
    pack = svc.load_pack(cohort)
    p1 = form_context(pack, 1)
    assert p1.product_ids == ["panel_gen1"]
    assert not p1.is_final
    # panel_gen2 exists for R&D from period 2 but is not launchable until 4.
    p2 = form_context(pack, 2)
    assert "panel_gen2" in p2.product_ids
    assert "panel_gen2" not in p2.launchable_product_ids
    p4 = form_context(pack, 4)
    assert "panel_gen2" in p4.launchable_product_ids
    assert form_context(pack, 9).is_final


# ---------------------------------------------------------------------------
# service.py — decisions
# ---------------------------------------------------------------------------


def test_submit_rejects_invalid_decision(svc, db, cohort):
    team = db.list_teams(cohort)[0]
    decision = svc.get_decision(cohort, team["id"], 1)
    decision.sales.by_product[0].market_1.price = 0  # non-positive price
    assert svc.validate(cohort, team["id"], 1, decision) != []
    with pytest.raises(ServiceError):
        svc.submit_decision(cohort, team["id"], 1, decision, user_id=1)
    # A draft save imposes no validation.
    svc.save_draft(cohort, team["id"], 1, decision, user_id=1)
    assert svc.decision_status(cohort, team["id"], 1) == "draft"


def test_submission_status_reflects_submits(svc, db, cohort):
    teams = db.list_teams(cohort)
    first = teams[0]
    svc.submit_decision(
        cohort, first["id"], 1, svc.get_decision(cohort, first["id"], 1), 1
    )
    status = svc.submission_status(cohort, 1)
    assert status[first["id"]] == "submitted"
    assert status[teams[1]["id"]] == "draft"


# ---------------------------------------------------------------------------
# service.py — running periods
# ---------------------------------------------------------------------------


def test_run_requires_all_submitted(svc, db, cohort):
    teams = db.list_teams(cohort)
    svc.submit_decision(
        cohort, teams[0]["id"], 1, svc.get_decision(cohort, teams[0]["id"], 1), 1
    )
    with pytest.raises(ServiceError, match="not submitted"):
        svc.run_next_period(cohort)  # two teams still on draft


def test_run_anyway_override_uses_drafts(svc, db, cohort):
    # No team has submitted, but the override runs with the seeded drafts.
    new_period = svc.run_next_period(cohort, require_all_submitted=False)
    assert new_period == 1
    assert svc.upcoming_period(cohort) == 2


def test_run_period_persists_state_reports_and_next_drafts(svc, db, cohort):
    teams = db.list_teams(cohort)
    _submit_all(svc, db, cohort, 1)
    new_period = svc.run_next_period(cohort)
    assert new_period == 1

    state = svc.get_state(cohort)
    assert state.period_index == 1

    for team in teams:
        bundle = svc.get_report(cohort, team["id"], 1)
        assert bundle is not None
        assert bundle.balance_sheet.articulates
        assert bundle.cash_flow.articulates
        # The next period's draft has been seeded.
        nxt = svc.get_decision(cohort, team["id"], 2)
        assert nxt is not None and nxt.period == 2

    industry = svc.get_industry_report(cohort, 1)
    assert industry is not None
    assert industry.market_total_units > 0


def test_full_playthrough_articulates_and_finishes(svc, db, cohort):
    """Run all nine periods; articulation must hold and the cohort finishes."""
    teams = db.list_teams(cohort)
    for period in range(1, 10):
        _submit_all(svc, db, cohort, period)
        assert svc.run_next_period(cohort) == period
        for team in teams:
            bundle = svc.get_report(cohort, team["id"], period)
            assert bundle.balance_sheet.articulates, f"period {period}"
            assert bundle.cash_flow.articulates, f"period {period}"

    assert db.get_cohort(cohort)["status"] == "finished"
    # No period-10 draft is seeded past the final period.
    assert svc.get_decision(cohort, teams[0]["id"], 10) is None
    with pytest.raises(ServiceError, match="finished"):
        svc.run_next_period(cohort, require_all_submitted=False)


# ---------------------------------------------------------------------------
# app.py — Streamlit smoke tests (AppTest harness)
# ---------------------------------------------------------------------------
#
# These drive the multi-user app headlessly. The app is pointed at a throwaway
# database via the SOLAR_SIM_DB environment variable, forced here on import so
# the tests never touch a real cohort database. A logout -> re-login round
# trip is deliberately not exercised: AppTest's element tree cannot follow the
# widget-tree change across that `st.rerun()` (the same limitation noted in
# test_app.py). Re-login works in a real browser.

_APP = str(Path(__file__).resolve().parent / "app.py")
os.environ["SOLAR_SIM_DB"] = str(Path(tempfile.mkdtemp()) / "apptest.db")


def _fresh_app() -> AppTest:
    at = AppTest.from_file(_APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _register(at: AppTest, name: str, email: str, role_label: str) -> AppTest:
    at.text_input(key="reg_name").set_value(name)
    at.text_input(key="reg_email").set_value(email)
    at.text_input(key="reg_pw").set_value("password1")
    at.selectbox(key="reg_role").set_value(role_label)
    next(b for b in at.button if b.label == "Create account").click().run()
    return at


def test_app_login_screen_renders():
    at = _fresh_app()
    assert any("solar-sim" in t.value for t in at.title)
    assert {tab.label for tab in at.tabs} >= {"Log in", "Create an account"}


def test_app_register_instructor_lands_on_instructor_view():
    at = _register(_fresh_app(), "Prof A", "insta@uni.edu", "Instructor")
    assert not at.exception, at.exception
    assert any("Instructor" in h.value for h in at.header)


def test_app_register_student_lands_on_student_view():
    at = _register(_fresh_app(), "Stu A", "studa@uni.edu", "Student")
    assert not at.exception, at.exception
    assert any("My team" in h.value for h in at.header)
    assert any("not been assigned" in i.value for i in at.info)


def test_app_instructor_creates_cohort():
    at = _register(_fresh_app(), "Prof B", "instb@uni.edu", "Instructor")
    at.text_input(key="cc_name").set_value("AppTest Cohort")
    at.text_area(key="cc_teams").set_value("Alpha\nBeta")
    next(b for b in at.button if b.label == "Create cohort").click().run()
    assert not at.exception, at.exception
    assert any("AppTest Cohort" in s.value for s in at.subheader)
    assert {tab.label for tab in at.tabs} >= {
        "Run period",
        "Teams & members",
        "Reports",
    }


def test_app_login_existing_user():
    # Seed a user straight into the app's database file, then log in.
    seeded = Database(os.environ["SOLAR_SIM_DB"])
    auth.register_user(
        seeded, "seeded@uni.edu", "Seeded Prof", "password1", "instructor"
    )
    at = _fresh_app()
    at.text_input(key="login_email").set_value("seeded@uni.edu")
    at.text_input(key="login_pw").set_value("password1")
    next(b for b in at.button if b.label == "Log in").click().run()
    assert not at.exception, at.exception
    assert any("Instructor" in h.value for h in at.header)


def _login(at: AppTest, email: str) -> AppTest:
    at.text_input(key="login_email").set_value(email)
    at.text_input(key="login_pw").set_value("password1")
    next(b for b in at.button if b.label == "Log in").click().run()
    assert not at.exception, at.exception
    return at


def test_app_student_submits_decision():
    """A student logs in, sees the decision form, and submits it end to end."""
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "sf_i@uni.edu", "Prof", "password1", "instructor")
    sid = auth.register_user(db, "sf_s@uni.edu", "Stu", "password1", "student")
    cohort_id = svc.create_cohort(iid, "Submit Cohort", _SCENARIO, ["Photon"])
    team = db.list_teams(cohort_id)[0]
    svc.assign_student(cohort_id, team["id"], sid)

    at = _login(_fresh_app(), "sf_s@uni.edu")
    assert any("My team" in h.value for h in at.header)
    # The decision form rendered, with its period header and submit button.
    assert any("Period 1" in str(m.value) for m in at.markdown)
    submit = next(b for b in at.button if b.label == "Submit for the period")
    submit.click().run()
    assert not at.exception, at.exception
    # The decision is now locked.
    assert any(
        "submitted and locked" in str(s.value) for s in at.success
    ), [s.value for s in at.success]
    assert svc.decision_status(cohort_id, team["id"], 1) == "submitted"


def test_app_instructor_runs_period():
    """An instructor logs in, overrides the submit gate, and runs a period."""
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "rp_i@uni.edu", "Prof", "password1", "instructor")
    cohort_id = svc.create_cohort(iid, "Run Cohort", _SCENARIO, ["Sol", "Vega"])

    at = _login(_fresh_app(), "rp_i@uni.edu")
    assert any("Run period 1" in b.label for b in at.button)
    # No team has submitted; use the override, then run.
    at.checkbox(key=f"override_{cohort_id}").set_value(True).run()
    next(b for b in at.button if b.label.startswith("Run period")).click().run()
    assert not at.exception, at.exception
    # The cohort advanced: the run button now targets period 2.
    assert any("Run period 2" in b.label for b in at.button)
    assert db.get_cohort(cohort_id)["current_period"] == 1


# ---------------------------------------------------------------------------
# pedagogy.py — pure scoring (no DB, no Streamlit)
# ---------------------------------------------------------------------------


def test_pedagogy_smape_edge_cases():
    assert pedagogy.smape(0, 0) == 0.0           # both zero → perfect
    assert pedagogy.smape(100, 100) == 0.0       # perfect match
    assert pedagogy.smape(100, 0) == 1.0         # one side zero → max error
    assert pedagogy.smape(50, -50) == 1.0        # sign flip → max error
    assert abs(pedagogy.smape(100, 200) - 100 / 300) < 1e-12


def test_pedagogy_kpi_score_is_one_minus_smape_and_bounded():
    assert pedagogy.kpi_score(100, 100) == 1.0
    assert pedagogy.kpi_score(50, -50) == 0.0
    # Bounded [0, 1] by triangle inequality, across many random inputs.
    import random
    rng = random.Random(42)
    for _ in range(500):
        p, a = rng.uniform(-1e9, 1e9), rng.uniform(-1e9, 1e9)
        assert 0.0 <= pedagogy.kpi_score(p, a) <= 1.0


def _period(period: int, is_real: bool, score: float) -> PeriodPlanningQuality:
    return PeriodPlanningQuality(
        period=period,
        is_real_period=is_real,
        kpis=[KPILine(name="x", planned=0, actual=0, score=score)],
        period_score=score,
    )


def test_pedagogy_team_quality_headline_uses_only_real_periods():
    tpq = TeamPlanningQuality.from_periods(
        99,
        [
            _period(1, False, 0.50),
            _period(4, True, 0.80),
            _period(5, True, 0.60),
        ],
    )
    assert tpq.real_period_count == 2
    assert abs(tpq.headline_score - 0.70) < 1e-12


def test_pedagogy_team_quality_no_real_periods_yields_none_headline():
    tpq = TeamPlanningQuality.from_periods(
        99, [_period(1, False, 0.5), _period(2, False, 0.6)]
    )
    assert tpq.headline_score is None
    assert tpq.real_period_count == 0


def test_pedagogy_strategy_map_is_empty_only_when_blank():
    sm = pedagogy.StrategyMap(cohort_id=1, team_id=1)
    assert sm.is_empty
    sm.financial = "   "
    assert sm.is_empty  # whitespace only is still empty
    sm.financial = "be #1"
    assert not sm.is_empty


# ---------------------------------------------------------------------------
# db.py — strategy_maps
# ---------------------------------------------------------------------------


def test_db_strategy_map_crud(db):
    uid = db.create_user("i@x.c", "I", "h", "instructor")
    cid = db.create_cohort("C", "/p", uid)
    tid = db.create_team(cid, "c1", "T")
    assert db.get_strategy_map(cid, tid) is None
    db.upsert_strategy_map(cid, tid, "fin", "cus", "ip", "lg", uid)
    row = db.get_strategy_map(cid, tid)
    assert row["financial"] == "fin"
    assert row["customer"] == "cus"
    assert row["internal_process"] == "ip"
    assert row["learning_growth"] == "lg"
    # Upsert overwrites.
    db.upsert_strategy_map(cid, tid, "fin2", "cus2", "ip2", "lg2", uid)
    row = db.get_strategy_map(cid, tid)
    assert row["financial"] == "fin2"
    assert [r["team_id"] for r in db.list_strategy_maps(cid)] == [tid]


# ---------------------------------------------------------------------------
# service.py — pedagogy
# ---------------------------------------------------------------------------


def test_service_strategy_map_roundtrip(svc, db, cohort, instructor):
    team = db.list_teams(cohort)[0]
    assert svc.get_strategy_map(cohort, team["id"]).is_empty
    svc.save_strategy_map(
        cohort, team["id"],
        "Cost leadership", "Quality leader", "Lean ops", "Train everyone",
        instructor,
    )
    sm = svc.get_strategy_map(cohort, team["id"])
    assert sm.financial == "Cost leadership"
    assert sm.customer == "Quality leader"
    assert not sm.is_empty


def test_service_planning_quality_scores_after_period(svc, db, cohort):
    teams = db.list_teams(cohort)
    for team in teams:
        decision = svc.get_decision(cohort, team["id"], 1)
        decision.finance.planned_kpis.revenue = 100_000_000
        decision.finance.planned_kpis.return_on_equity = 0.05
        decision.finance.planned_kpis.operating_cash_flow = 5_000_000
        svc.submit_decision(cohort, team["id"], 1, decision, 1)
    svc.run_next_period(cohort)

    tpq = svc.team_planning_quality(cohort, teams[0]["id"])
    assert len(tpq.periods) == 1
    p = tpq.periods[0]
    assert p.period == 1
    # solar-v1 sets trial_periods=[1,2,3]; period 1 is trial.
    assert p.is_real_period is False
    assert {k.name for k in p.kpis} == {
        "Revenue",
        "Return on equity",
        "Operating cash flow",
    }
    assert 0.0 <= p.period_score <= 1.0
    # No real period has run yet → no headline.
    assert tpq.headline_score is None
    assert tpq.real_period_count == 0


def test_service_planning_quality_before_first_period_is_empty(svc, cohort):
    teams = svc.db.list_teams(cohort)
    tpq = svc.team_planning_quality(cohort, teams[0]["id"])
    assert tpq.periods == []
    assert tpq.headline_score is None


# ---------------------------------------------------------------------------
# app.py — pedagogy tabs (AppTest)
# ---------------------------------------------------------------------------


def test_app_student_sees_planning_quality_tab_after_period():
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "pq_i@uni.edu", "Prof", "password1", "instructor")
    sid = auth.register_user(db, "pq_s@uni.edu", "Stu", "password1", "student")
    cid = svc.create_cohort(iid, "PQ Cohort", _SCENARIO, ["Apex"])
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], sid)
    decision = svc.get_decision(cid, team["id"], 1)
    decision.finance.planned_kpis.revenue = 100_000_000
    decision.finance.planned_kpis.return_on_equity = 0.05
    decision.finance.planned_kpis.operating_cash_flow = 5_000_000
    svc.submit_decision(cid, team["id"], 1, decision, sid)
    svc.run_next_period(cid)

    at = _login(_fresh_app(), "pq_s@uni.edu")
    tab_labels = {tab.label for tab in at.tabs}
    assert {"Planning quality", "Strategy"} <= tab_labels
    # The planning-quality detail renders Period 1 as "Trial" (real_periods 4+).
    rendered = " ".join(str(m.value) for m in at.markdown)
    assert "Period 1" in rendered and "Trial" in rendered


def test_app_student_saves_strategy_map():
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "sm_i@uni.edu", "Prof", "password1", "instructor")
    sid = auth.register_user(db, "sm_s@uni.edu", "Stu", "password1", "student")
    cid = svc.create_cohort(iid, "SM Cohort", _SCENARIO, ["Helios"])
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], sid)

    at = _login(_fresh_app(), "sm_s@uni.edu")
    at.text_area(key=f"sm_fin_{cid}_{team['id']}").set_value("Be #1 on cost")
    at.text_area(key=f"sm_cus_{cid}_{team['id']}").set_value("Quality leader")
    at.text_area(key=f"sm_ip_{cid}_{team['id']}").set_value("Lean ops")
    at.text_area(key=f"sm_lg_{cid}_{team['id']}").set_value("Train everyone")
    next(b for b in at.button if b.label == "Save strategy").click().run()
    assert not at.exception, at.exception
    sm = svc.get_strategy_map(cid, team["id"])
    assert sm.financial == "Be #1 on cost"
    assert sm.customer == "Quality leader"
    assert sm.internal_process == "Lean ops"
    assert sm.learning_growth == "Train everyone"


# ---------------------------------------------------------------------------
# pedagogy.py — peer-assessment models (pure)
# ---------------------------------------------------------------------------


def test_pedagogy_peer_rating_validates_dimension_range():
    # Each dimension must be an integer in 1..5.
    with pytest.raises(ValidationError):
        PeerRating(
            cohort_id=1, rater_id=1, ratee_id=2,
            contribution=0, collaboration=3, reliability=3, communication=3,
        )
    with pytest.raises(ValidationError):
        PeerRating(
            cohort_id=1, rater_id=1, ratee_id=2,
            contribution=6, collaboration=3, reliability=3, communication=3,
        )
    # 1 and 5 are accepted.
    r = PeerRating(
        cohort_id=1, rater_id=1, ratee_id=2,
        contribution=1, collaboration=5, reliability=3, communication=4,
    )
    assert r.overall == (1 + 5 + 3 + 4) / 4


def test_pedagogy_aggregate_ratings_empty():
    agg = aggregate_ratings(ratee_id=99, ratings=[])
    assert agg.n_raters == 0
    assert agg.contribution_mean is None
    assert agg.overall_mean is None


def _r(rater, ratee, c, co, re, cm):
    return PeerRating(
        cohort_id=1, rater_id=rater, ratee_id=ratee,
        contribution=c, collaboration=co, reliability=re, communication=cm,
    )


def test_pedagogy_aggregate_ratings_means_and_filtering():
    # Multiple ratings, multiple ratees; aggregate only for ratee_id=2.
    ratings = [
        _r(1, 2, 5, 5, 5, 5),
        _r(3, 2, 3, 4, 4, 4),
        _r(1, 4, 1, 1, 1, 1),  # ignored — different ratee
    ]
    agg = aggregate_ratings(ratee_id=2, ratings=ratings)
    assert agg.n_raters == 2
    assert abs(agg.contribution_mean - 4.0) < 1e-12
    assert abs(agg.collaboration_mean - 4.5) < 1e-12
    assert abs(agg.reliability_mean - 4.5) < 1e-12
    assert abs(agg.communication_mean - 4.5) < 1e-12
    # Overall is the mean of the four dimension means.
    assert abs(agg.overall_mean - (4.0 + 4.5 + 4.5 + 4.5) / 4) < 1e-12


# ---------------------------------------------------------------------------
# db.py — peer_ratings
# ---------------------------------------------------------------------------


def test_db_peer_ratings_crud(db):
    iid = db.create_user("i@x.c", "I", "h", "instructor")
    a = db.create_user("a@x.c", "Alice", "h", "student")
    b = db.create_user("b@x.c", "Bob", "h", "student")
    cid = db.create_cohort("C", "/p", iid)
    db.upsert_peer_rating(cid, a, b, 5, 4, 5, 4, "ok")
    row = db.get_peer_rating(cid, a, b)
    assert row["contribution"] == 5
    assert row["comments"] == "ok"
    # Upsert overwrites and updates the timestamp.
    first_updated = row["updated_at"]
    db.upsert_peer_rating(cid, a, b, 3, 3, 3, 3, "revised")
    row = db.get_peer_rating(cid, a, b)
    assert row["contribution"] == 3
    assert row["comments"] == "revised"
    assert row["updated_at"] >= first_updated
    # Listings.
    assert [r["ratee_id"] for r in db.list_peer_ratings_by_rater(cid, a)] == [b]
    assert [r["rater_id"] for r in db.list_peer_ratings_by_ratee(cid, b)] == [a]
    assert len(db.list_peer_ratings(cid)) == 1
    # Delete.
    db.delete_peer_rating(cid, a, b)
    assert db.get_peer_rating(cid, a, b) is None


def test_db_peer_ratings_check_constraint_rejects_out_of_range(db):
    iid = db.create_user("i@x.c", "I", "h", "instructor")
    a = db.create_user("a@x.c", "Alice", "h", "student")
    b = db.create_user("b@x.c", "Bob", "h", "student")
    cid = db.create_cohort("C", "/p", iid)
    # The schema CHECK constraint catches out-of-range scores.
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_peer_rating(cid, a, b, 0, 3, 3, 3, "")
    with pytest.raises(sqlite3.IntegrityError):
        db.upsert_peer_rating(cid, a, b, 3, 3, 3, 6, "")


# ---------------------------------------------------------------------------
# service.py — peer-assessment validation and visibility
# ---------------------------------------------------------------------------


@pytest.fixture
def peer_cohort(svc, db, instructor):
    """A cohort with two students on one team and two on another."""
    cid = svc.create_cohort(
        instructor, "Peer Cohort", _SCENARIO, ["Apex", "Vega"]
    )
    alice = auth.register_user(db, "alice@u.e", "Alice", "password1", "student")
    bob = auth.register_user(db, "bob@u.e", "Bob", "password1", "student")
    carol = auth.register_user(db, "carol@u.e", "Carol", "password1", "student")
    dave = auth.register_user(db, "dave@u.e", "Dave", "password1", "student")
    apex, vega = db.list_teams(cid)
    svc.assign_student(cid, apex["id"], alice)
    svc.assign_student(cid, apex["id"], bob)
    svc.assign_student(cid, vega["id"], carol)
    svc.assign_student(cid, vega["id"], dave)
    return {"cohort": cid, "apex": apex, "vega": vega,
            "alice": alice, "bob": bob, "carol": carol, "dave": dave}


def test_service_peer_targets_excludes_self_and_other_teams(svc, peer_cohort):
    targets = svc.team_peer_targets(peer_cohort["cohort"], peer_cohort["alice"])
    assert [t["id"] for t in targets] == [peer_cohort["bob"]]


def test_service_save_peer_rating_rejects_self(svc, peer_cohort):
    with pytest.raises(ServiceError, match="rate yourself"):
        svc.save_peer_rating(
            peer_cohort["cohort"], peer_cohort["alice"], peer_cohort["alice"],
            3, 3, 3, 3, "",
        )


def test_service_save_peer_rating_rejects_cross_team(svc, peer_cohort):
    with pytest.raises(ServiceError, match="same team"):
        svc.save_peer_rating(
            peer_cohort["cohort"], peer_cohort["alice"], peer_cohort["carol"],
            3, 3, 3, 3, "",
        )


def test_service_save_peer_rating_rejects_out_of_range(svc, peer_cohort):
    with pytest.raises(ServiceError, match="1-5"):
        svc.save_peer_rating(
            peer_cohort["cohort"], peer_cohort["alice"], peer_cohort["bob"],
            0, 3, 3, 3, "",
        )


def test_service_save_peer_rating_locked_after_cohort_finishes(svc, db, peer_cohort):
    db.set_cohort_status(peer_cohort["cohort"], "finished")
    with pytest.raises(ServiceError, match="locked"):
        svc.save_peer_rating(
            peer_cohort["cohort"], peer_cohort["alice"], peer_cohort["bob"],
            3, 3, 3, 3, "",
        )


def test_service_my_aggregated_rating_hidden_until_cohort_closes(svc, db, peer_cohort):
    svc.save_peer_rating(
        peer_cohort["cohort"], peer_cohort["bob"], peer_cohort["alice"],
        5, 5, 5, 5, "Strong",
    )
    # Active cohort: Alice cannot see her aggregated rating yet.
    assert svc.my_aggregated_rating(peer_cohort["cohort"], peer_cohort["alice"]) is None
    # Finish the cohort: Alice now sees the aggregate.
    db.set_cohort_status(peer_cohort["cohort"], "finished")
    agg = svc.my_aggregated_rating(peer_cohort["cohort"], peer_cohort["alice"])
    assert agg is not None
    assert agg.n_raters == 1
    assert agg.overall_mean == 5.0


def test_service_team_peer_aggregates_for_instructor(svc, peer_cohort):
    svc.save_peer_rating(
        peer_cohort["cohort"], peer_cohort["alice"], peer_cohort["bob"],
        4, 5, 5, 4, "",
    )
    svc.save_peer_rating(
        peer_cohort["cohort"], peer_cohort["bob"], peer_cohort["alice"],
        5, 5, 5, 5, "",
    )
    aggs = {
        a.ratee_id: a
        for a in svc.team_peer_aggregates(peer_cohort["cohort"], peer_cohort["apex"]["id"])
    }
    assert aggs[peer_cohort["alice"]].n_raters == 1
    assert aggs[peer_cohort["alice"]].overall_mean == 5.0
    assert aggs[peer_cohort["bob"]].n_raters == 1
    # Bob got 4 + 5 + 5 + 4 = 18 / 4 = 4.5 overall
    assert aggs[peer_cohort["bob"]].overall_mean == 4.5


# ---------------------------------------------------------------------------
# app.py — peer review (AppTest)
# ---------------------------------------------------------------------------


def test_app_student_saves_peer_rating_end_to_end():
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "pr_i@uni.edu", "Prof", "password1", "instructor")
    a = auth.register_user(db, "pr_alice@uni.edu", "Alice", "password1", "student")
    b = auth.register_user(db, "pr_bob@uni.edu", "Bob", "password1", "student")
    cid = svc.create_cohort(iid, "PR Cohort", _SCENARIO, ["Apex"])
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], a)
    svc.assign_student(cid, team["id"], b)

    at = _login(_fresh_app(), "pr_alice@uni.edu")
    assert any(t.label == "Peer review" for t in at.tabs)
    # Set rating widgets for Bob.
    at.number_input(key=f"pr_contrib_{cid}_{b}").set_value(5)
    at.number_input(key=f"pr_collab_{cid}_{b}").set_value(4)
    at.number_input(key=f"pr_reli_{cid}_{b}").set_value(5)
    at.number_input(key=f"pr_comm_{cid}_{b}").set_value(4)
    at.text_area(key=f"pr_text_{cid}_{b}").set_value("Strong partner")
    next(
        btn for btn in at.button if btn.label == "Save rating for Bob"
    ).click().run()
    assert not at.exception, at.exception
    rating = svc.get_my_rating(cid, a, b)
    assert rating is not None
    assert rating.contribution == 5
    assert rating.collaboration == 4
    assert rating.reliability == 5
    assert rating.communication == 4
    assert rating.comments == "Strong partner"


def test_app_aggregated_rating_visible_only_after_close():
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "fc_i@uni.edu", "Prof", "password1", "instructor")
    a = auth.register_user(db, "fc_alice@uni.edu", "Alice", "password1", "student")
    b = auth.register_user(db, "fc_bob@uni.edu", "Bob", "password1", "student")
    cid = svc.create_cohort(iid, "FC Cohort", _SCENARIO, ["Apex"])
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], a)
    svc.assign_student(cid, team["id"], b)
    svc.save_peer_rating(cid, b, a, 5, 5, 5, 5, "Excellent")

    # Active cohort: Alice's aggregated rating is not yet shown.
    at = _login(_fresh_app(), "fc_alice@uni.edu")
    rendered_active = " ".join(str(m.value) for m in at.markdown)
    assert "Your peer ratings" not in rendered_active

    # Finish the cohort, log in fresh: aggregated view now appears.
    db.set_cohort_status(cid, "finished")
    at2 = _login(_fresh_app(), "fc_alice@uni.edu")
    rendered_finished = " ".join(str(m.value) for m in at2.markdown)
    assert "Your peer ratings" in rendered_finished


# ---------------------------------------------------------------------------
# board_export.py — Markdown renderer (pure)
# ---------------------------------------------------------------------------


def _minimal_board_data(**overrides):
    base = dict(
        cohort_name="Cohort C",
        cohort_status="active",
        scenario_id="solar-v1",
        team_name="Apex",
        team_company_id="c1",
        member_names=["Alice", "Bob"],
        strategy_map=StrategyMap(cohort_id=1, team_id=1),
        viewer_role="student",
        generated_at="2026-05-22",
    )
    base.update(overrides)
    return TeamBoardData(**base)


def test_render_document_cover_includes_team_and_cohort():
    doc = render_document(_minimal_board_data())
    assert "# Board-meeting document — Apex" in doc
    assert "Cohort C" in doc
    assert "solar-v1" in doc
    assert "Alice, Bob" in doc


def test_render_document_handles_empty_state_with_placeholders():
    doc = render_document(_minimal_board_data())
    assert "_No periods have been run yet._" in doc
    assert "_No periods scored yet._" in doc
    assert "_This team has not authored a strategy map._" in doc
    # Student view, active cohort → peer section is gated.
    assert "released once the cohort is finished" in doc


def test_render_document_role_filters_peer_comments_to_instructor():
    rating = PeerRatingWithNames(
        rater_name="Alice", ratee_name="Bob",
        rating=PeerRating(
            cohort_id=1, rater_id=1, ratee_id=2,
            contribution=4, collaboration=5, reliability=5, communication=4,
            comments="DRIVES_RESULTS_marker",
        ),
    )
    aggregate = AggregatedRating(
        ratee_id=2, n_raters=1,
        contribution_mean=4.0, collaboration_mean=5.0,
        reliability_mean=5.0, communication_mean=4.0, overall_mean=4.5,
    )
    instr_doc = render_document(
        _minimal_board_data(
            viewer_role="instructor",
            detailed_peer_ratings=[rating],
            team_peer_aggregates=[aggregate],
        )
    )
    stu_doc = render_document(
        _minimal_board_data(
            viewer_role="student", detailed_peer_ratings=[rating]
        )
    )
    assert "DRIVES_RESULTS_marker" in instr_doc
    assert "Per-member aggregates" in instr_doc
    # Student doc never carries individual comments.
    assert "DRIVES_RESULTS_marker" not in stu_doc
    # Student doc, active cohort: gated message instead of aggregates.
    assert "released once the cohort is finished" in stu_doc


def test_md_table_escapes_pipes_and_collapses_newlines():
    out = board_export._md_table(["A", "B"], [["x|y", "line1\nline2"]])
    assert "x\\|y" in out
    assert "line1 / line2" in out
    assert board_export._md_table(["A"], []) == ""


# ---------------------------------------------------------------------------
# service.py — board document generation
# ---------------------------------------------------------------------------


def _setup_board_cohort(svc, db, instructor):
    """Cohort with two students on one team, one period run, one peer rating."""
    cid = svc.create_cohort(instructor, "Spring", _SCENARIO, ["Apex"])
    alice = auth.register_user(db, "bd_alice@u.e", "Alice", "password1", "student")
    bob = auth.register_user(db, "bd_bob@u.e", "Bob", "password1", "student")
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], alice)
    svc.assign_student(cid, team["id"], bob)
    decision = svc.get_decision(cid, team["id"], 1)
    decision.finance.planned_kpis.revenue = 100_000_000
    decision.finance.planned_kpis.return_on_equity = 0.05
    decision.finance.planned_kpis.operating_cash_flow = 5_000_000
    svc.submit_decision(cid, team["id"], 1, decision, instructor)
    svc.run_next_period(cid)
    svc.save_strategy_map(
        cid, team["id"], "Cost lead", "Quality", "Lean", "Train", instructor
    )
    svc.save_peer_rating(
        cid, alice, bob, 4, 5, 5, 4, "MARKER_INSTRUCTOR_ONLY"
    )
    return {"cohort": cid, "team_id": team["id"], "alice": alice, "bob": bob}


def test_service_board_doc_student_active_hides_peer_data(svc, db, instructor):
    case = _setup_board_cohort(svc, db, instructor)
    doc = svc.build_board_document(
        case["cohort"], case["team_id"], "student",
        viewer_user_id=case["alice"],
    )
    # Student documents never include individual peer comments.
    assert "MARKER_INSTRUCTOR_ONLY" not in doc
    # During active cohort, the aggregated section is gated.
    assert "released once the cohort is finished" in doc
    # The non-peer sections are present.
    assert "Period-by-period reports" in doc
    assert "## Strategy map" in doc


def test_service_board_doc_student_finished_shows_own_aggregate(svc, db, instructor):
    case = _setup_board_cohort(svc, db, instructor)
    db.set_cohort_status(case["cohort"], "finished")
    doc = svc.build_board_document(
        case["cohort"], case["team_id"], "student",
        viewer_user_id=case["bob"],   # Bob was rated by Alice
    )
    assert "Aggregated across" in doc
    # Comments stay instructor-only even after the cohort closes.
    assert "MARKER_INSTRUCTOR_ONLY" not in doc


def test_service_board_doc_instructor_includes_full_detail(svc, db, instructor):
    case = _setup_board_cohort(svc, db, instructor)
    doc = svc.build_board_document(
        case["cohort"], case["team_id"], "instructor"
    )
    assert "Per-member aggregates" in doc
    assert "MARKER_INSTRUCTOR_ONLY" in doc
    assert "Detailed ratings" in doc
    assert "Period-by-period reports" in doc


# ---------------------------------------------------------------------------
# app.py — Board export tab (AppTest)
# ---------------------------------------------------------------------------


def test_app_student_board_export_tab_renders():
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "be_i@uni.edu", "Prof", "password1", "instructor")
    sid = auth.register_user(db, "be_s@uni.edu", "Stu", "password1", "student")
    cid = svc.create_cohort(iid, "BE Cohort", _SCENARIO, ["Apex"])
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], sid)

    at = _login(_fresh_app(), "be_s@uni.edu")
    assert any(t.label == "Board export" for t in at.tabs)
    rendered = " ".join(str(m.value) for m in at.markdown)
    # The rendered document's H1 appears in the preview.
    assert "Board-meeting document — Apex" in rendered


# ---------------------------------------------------------------------------
# Phase 3 polish — cookie-backed sessions
# ---------------------------------------------------------------------------


def test_db_session_crud_and_expiry(db):
    """create / lookup / delete / purge round-trip with expiry honouring."""
    from datetime import datetime, timedelta, timezone

    uid = db.create_user("p@x.c", "P", "h", "instructor")
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    db.create_session("tok-active", uid, future)
    row = db.lookup_session("tok-active")
    assert row is not None
    assert int(row["user_id"]) == uid

    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    db.create_session("tok-expired", uid, past)
    # Expired tokens don't resolve.
    assert db.lookup_session("tok-expired") is None
    # purge_expired clears them out.
    assert db.purge_expired_sessions() >= 1

    db.delete_session("tok-active")
    assert db.lookup_session("tok-active") is None


def test_auth_create_lookup_end_session(db):
    """auth.create_session round-trips through lookup_session and end_session."""
    uid = auth.register_user(db, "s@x.c", "S", "password1", "student")
    token = auth.create_session(db, uid)
    assert isinstance(token, str) and len(token) >= 32

    user = auth.lookup_session(db, token)
    assert user is not None and int(user["id"]) == uid

    auth.end_session(db, token)
    assert auth.lookup_session(db, token) is None
    assert auth.lookup_session(db, "made-up-token") is None


# ---------------------------------------------------------------------------
# Phase 3 polish — instructor draft view (AppTest)
# ---------------------------------------------------------------------------


def test_app_instructor_sees_team_drafts():
    """The Run-period tab shows a 'Team drafts' section with the team listed."""
    db = Database(os.environ["SOLAR_SIM_DB"])
    svc = GameService(db)
    iid = auth.register_user(db, "drv_i@uni.edu", "Prof", "password1", "instructor")
    sid = auth.register_user(db, "drv_s@uni.edu", "Stu", "password1", "student")
    cid = svc.create_cohort(iid, "Drafts Cohort", _SCENARIO, ["Apex"])
    team = db.list_teams(cid)[0]
    svc.assign_student(cid, team["id"], sid)

    at = _login(_fresh_app(), "drv_i@uni.edu")
    assert not at.exception, at.exception
    rendered = " ".join(str(m.value) for m in at.markdown)
    assert "Team drafts (read-only)" in rendered
    # Apex's draft expander label includes its draft tag.
    expander_labels = [e.label for e in at.expander]
    assert any("Apex" in label and "draft" in label for label in expander_labels)
