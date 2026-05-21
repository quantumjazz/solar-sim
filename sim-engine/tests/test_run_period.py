"""End-to-end test: load solar-v1, run one period, verify articulation.

Five articulation identities are enforced (from docs/spec/06-accounting.md §9):

  1. total_assets == total_liabilities_and_equity
  2. equity[t] - equity[t-1] == net_income[t] - dividends_declared[t-1]
  3. cash[t] - cash[t-1] == operating_cf + investing_cf + financing_cf
  4. (cost-centre vs cost-type) — deferred to v0.2, when all 5 cost centres are wired
  5. industry_report total == sum(team revenues) — deferred to multi-team v0.3
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from sim_engine.decisions import (
    FinanceDecision,
    HRDecision,
    PlannedKPIs,
    ProductionByProductDecision,
    ProductionDecision,
    ProductionLinesDecision,
    PurchasingByProductDecision,
    PurchasingDecision,
    RnDByProductDecision,
    RnDDecision,
    SalesByProductDecision,
    SalesDecision,
    SalesPerMarketDecision,
    LineMaintenanceDecision,
)
from sim_engine.engine import build_initial_state, run_period
from sim_engine.scenario import load_scenario_pack


SCENARIO_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "solar-v1"


@pytest.fixture(scope="module")
def pack():
    return load_scenario_pack(SCENARIO_PATH)


@pytest.fixture
def state_0(pack):
    return build_initial_state(pack)


@pytest.fixture
def default_decision_p1(pack):
    """A reasonable, sub-optimal default decision for period 1.

    Roughly mirrors the prior board's period-0 actions, with mild adjustments
    appropriate to the period-1 economic situation.
    """
    return {
        "c1": _build_decision(
            team_id="c1",
            period=1,
            price=2_800,
            advertising=6_000_000,
            sales_force=100,
            researchers=34,
            sustainability_spend=2_500_000,
            value_analysis_spend=1_000_000,
            order_units=30_000,
            target_volume=40_000,
            maintenance_spend_per_line=1_000_000,
            production_workforce_change=0,
            training_per_employee=500,
            process_optimisation_spend=0,
            non_salary_pct=0.40,
            pension_reserve_pct=0.05,
            short_term_loan=30_000_000,
            dividend=0,
        )
    }


def _build_decision(**kw):
    from sim_engine.decisions import TeamDecision

    return TeamDecision(
        team_id=kw["team_id"],
        period=kw["period"],
        sales=SalesDecision(
            by_product=[
                SalesByProductDecision(
                    product="panel_gen1",
                    market_1=SalesPerMarketDecision(
                        price=kw["price"],
                        advertising=kw["advertising"],
                        sales_force=kw["sales_force"],
                    ),
                )
            ],
            corporate_identity=2_000_000,
            market_research_report=True,
        ),
        rnd=RnDDecision(
            by_product=[
                RnDByProductDecision(
                    product="panel_gen1",
                    researchers=kw["researchers"],
                    sustainability_spend=kw["sustainability_spend"],
                    value_analysis_spend=kw["value_analysis_spend"],
                )
            ]
        ),
        purchasing=PurchasingDecision(
            by_product=[
                PurchasingByProductDecision(
                    product="panel_gen1",
                    order_units=kw["order_units"],
                )
            ]
        ),
        production=ProductionDecision(
            by_product=[
                ProductionByProductDecision(
                    product="panel_gen1",
                    target_volume=kw["target_volume"],
                )
            ],
            lines=ProductionLinesDecision(
                maintenance=LineMaintenanceDecision(
                    spend_per_line={"stringer_v1": kw["maintenance_spend_per_line"]}
                ),
            ),
        ),
        hr=HRDecision(
            production_workforce_change=kw["production_workforce_change"],
            training_per_employee=kw["training_per_employee"],
            process_optimisation_spend=kw["process_optimisation_spend"],
            non_salary_pct=kw["non_salary_pct"],
            pension_reserve_pct=kw["pension_reserve_pct"],
        ),
        finance=FinanceDecision(
            short_term_loan=kw["short_term_loan"],
            dividend=kw["dividend"],
            planned_kpis=PlannedKPIs(),
        ),
    )


def test_scenario_loads(pack):
    assert pack.pack.scenario.id == "solar-v1"
    assert pack.pack.scenario.version == "0.1.0"
    assert len(pack.events) == 9
    assert {p.id for p in pack.pack.products} == {"panel_gen1"}


def test_initial_state(state_0):
    assert state_0.period_index == 0
    assert len(state_0.companies) == 1

    c = state_0.companies[0]
    assert c.id == "c1"
    assert c.cash == 0
    assert c.retained_earnings == 12_500_000
    assert "production" in c.cost_centres
    assert "panel_gen1" in c.products
    assert len(c.lines) == 4


def test_period_1_runs(state_0, default_decision_p1, pack):
    new_state, reports = run_period(state_0, default_decision_p1, pack)
    assert new_state.period_index == 1
    assert "c1" in reports
    bundle = reports["c1"]

    # Sanity: positive revenue, sensible costs
    assert bundle.profit_and_loss.sales_revenue > 0
    assert bundle.profit_and_loss.material_expenses > 0
    assert bundle.profit_and_loss.wages_and_salaries > 0
    # Some units sold
    assert bundle.market.total_units_sold > 0


def test_articulation_identity_1_balance_sheet(state_0, default_decision_p1, pack):
    """Identity 1: total_assets == total_liabilities_and_equity."""
    _, reports = run_period(state_0, default_decision_p1, pack)
    bs = reports["c1"].balance_sheet
    assert bs.articulates, (
        f"Balance sheet does not articulate: assets={bs.total_assets}, "
        f"L+E={bs.total_liabilities_and_equity}, "
        f"delta={bs.total_assets - bs.total_liabilities_and_equity}"
    )


def test_articulation_identity_3_cash_flow(state_0, default_decision_p1, pack):
    """Identity 3: cash[t] - cash[t-1] == ocf + icf + fcf."""
    _, reports = run_period(state_0, default_decision_p1, pack)
    cf = reports["c1"].cash_flow
    assert cf.articulates, (
        f"Cash flow does not articulate: "
        f"end={cf.cash_end}, start={cf.cash_start}, "
        f"sum_flows={cf.operating_cash_flow + cf.investing_cash_flow + cf.financing_cash_flow}"
    )


def test_articulation_identity_2_equity_rollforward(state_0, default_decision_p1, pack):
    """Identity 2: equity[t] - equity[t-1] == net_income[t] - dividends_declared[t-1].

    The change in equity from t-1 to t should equal the period's net income
    minus the dividend that was declared at t-1 (and paid at t).
    """
    new_state, reports = run_period(state_0, default_decision_p1, pack)

    c_before = state_0.companies[0]
    c_after = new_state.companies[0]

    equity_before = (
        c_before.subscribed_capital
        + c_before.capital_reserves
        + c_before.retained_earnings
        + c_before.last_period_net_income
    )
    equity_after = (
        c_after.subscribed_capital
        + c_after.capital_reserves
        + c_after.retained_earnings
        + c_after.last_period_net_income
    )
    delta_equity = equity_after - equity_before

    net_income = reports["c1"].profit_and_loss.net_income
    dividend_declared_prior = c_before.last_dividend_declared

    expected_delta = net_income - dividend_declared_prior
    assert math.isclose(delta_equity, expected_delta, abs_tol=1.0), (
        f"Equity roll-forward broken: Δequity = {delta_equity:.2f}, "
        f"expected (NI - prior dividend) = {expected_delta:.2f}"
    )


def test_multi_team_market_split(pack):
    """Two teams compete: total units sold in market_1 should be <= market potential.

    Team A submits a strong offer (low price, high ads, high indices),
    Team B submits a weak offer. A should capture more share than B.
    """
    from sim_engine.engine import build_initial_state

    state_0 = build_initial_state(pack, company_ids=["A", "B"])
    assert len(state_0.companies) == 2

    decision_strong = _build_decision(
        team_id="A", period=1,
        price=2_700, advertising=8_000_000, sales_force=120,
        researchers=50, sustainability_spend=4_000_000, value_analysis_spend=2_000_000,
        order_units=40_000, target_volume=45_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=20, training_per_employee=1_000,
        process_optimisation_spend=2_000_000, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    decision_weak = _build_decision(
        team_id="B", period=1,
        price=3_000, advertising=4_000_000, sales_force=80,
        researchers=20, sustainability_spend=1_000_000, value_analysis_spend=500_000,
        order_units=20_000, target_volume=20_000, maintenance_spend_per_line=500_000,
        production_workforce_change=-50, training_per_employee=200,
        process_optimisation_spend=0, non_salary_pct=0.37, pension_reserve_pct=0.05,
        short_term_loan=15_000_000, dividend=0,
    )

    new_state, reports = run_period(
        state_0, {"A": decision_strong, "B": decision_weak}, pack
    )
    assert "A" in reports and "B" in reports

    units_A = reports["A"].market.total_units_sold
    units_B = reports["B"].market.total_units_sold

    # Both should sell something
    assert units_A > 0
    assert units_B > 0
    # Stronger offer should capture more units (modulo supply constraints)
    assert units_A > units_B, f"strong should beat weak: A={units_A}, B={units_B}"

    # Total sold must not exceed market potential (215_000 in p0; event-overridden to 230_000 in p1)
    total_sold = units_A + units_B
    assert total_sold <= 230_000, f"total sold {total_sold} exceeded market potential"

    # Both balance sheets articulate
    assert reports["A"].balance_sheet.articulates
    assert reports["B"].balance_sheet.articulates


def test_period_event_wage_changes_flow_through(pack):
    """Production cost-centre salary should rise from 30 000 (P0) to 31 000 (P1)."""
    from sim_engine.engine import build_initial_state

    state_0 = build_initial_state(pack)
    # Sanity check on starting state
    assert state_0.companies[0].cost_centres["production"].salary_per_capita == 30_000

    decision = _build_decision(
        team_id="c1", period=1,
        price=2_800, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )

    new_state, _ = run_period(state_0, {"c1": decision}, pack)
    # Period 1 event sets production wage to 31 000
    assert new_state.companies[0].cost_centres["production"].salary_per_capita == 31_000


def test_determinism(state_0, default_decision_p1, pack):
    """Same inputs should yield identical reports."""
    s1a, r1a = run_period(state_0, default_decision_p1, pack)
    # Build a fresh initial state so the second run is fully independent
    s0_again = build_initial_state(pack)
    s1b, r1b = run_period(s0_again, default_decision_p1, pack)

    assert r1a["c1"].profit_and_loss.model_dump() == r1b["c1"].profit_and_loss.model_dump()
    assert r1a["c1"].balance_sheet.model_dump() == r1b["c1"].balance_sheet.model_dump()
    assert r1a["c1"].cash_flow.model_dump() == r1b["c1"].cash_flow.model_dump()
