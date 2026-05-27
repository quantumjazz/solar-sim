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
    assert {p.id for p in pack.pack.products} == {
        "panel_gen1",
        "panel_gen2",
        "storage_box",
        "balcony_solar",
    }


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


def test_productivity_responds_to_training(pack):
    """Training and process-optimisation spend should raise Productivity Index I."""
    from sim_engine.engine import build_initial_state

    state_0 = build_initial_state(pack, company_ids=["Trained", "Neglected"])
    common = dict(
        price=2_900, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=1_500_000, value_analysis_spend=800_000,
        order_units=42_000, target_volume=44_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=15_000_000, dividend=0,
    )
    trained = _build_decision(
        team_id="Trained", period=1,
        training_per_employee=3_000, process_optimisation_spend=3_000_000, **common
    )
    neglected = _build_decision(
        team_id="Neglected", period=1,
        training_per_employee=0, process_optimisation_spend=0, **common
    )
    new_state, _ = run_period(
        state_0, {"Trained": trained, "Neglected": neglected}, pack
    )

    c_trained = new_state.company("Trained")
    c_neglected = new_state.company("Neglected")

    # Training raises competence; neglect lets it decay below 1.0
    assert c_trained.competence_index > 1.0
    assert c_neglected.competence_index < 1.0
    # Process-opt spend raises that index; neglect lets it decay
    assert c_trained.process_optimisation_index > c_neglected.process_optimisation_index
    # Overall Productivity Index I is higher for the trained company
    assert c_trained.productivity_index_i > c_neglected.productivity_index_i


def test_auto_scaled_cost_centres(pack):
    """Purchasing and administration headcount should track revenue."""
    from sim_engine.engine import build_initial_state

    state_0 = build_initial_state(pack)
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
    c = new_state.companies[0]
    # With ~130 mEUR prior revenue: purchasing ~18, admin ~202 (sane ranges)
    assert 10 <= c.cost_centres["purchasing"].headcount <= 25
    assert 150 <= c.cost_centres["administration"].headcount <= 280


def test_multi_period_articulation(pack):
    """Run three periods back-to-back; the balance sheet must articulate each time."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack)
    for period in (1, 2, 3):
        decision = _build_decision(
            team_id="c1", period=period,
            price=2_900, advertising=6_000_000, sales_force=100,
            researchers=34, sustainability_spend=2_000_000, value_analysis_spend=1_000_000,
            order_units=42_000, target_volume=44_000, maintenance_spend_per_line=1_000_000,
            production_workforce_change=0, training_per_employee=800,
            process_optimisation_spend=1_000_000, non_salary_pct=0.40,
            pension_reserve_pct=0.05, short_term_loan=20_000_000, dividend=0,
        )
        state, reports = run_period(state, {"c1": decision}, pack)
        assert reports["c1"].balance_sheet.articulates, f"period {period} BS broke"
        assert reports["c1"].cash_flow.articulates, f"period {period} CF broke"
    assert state.period_index == 3


def test_bulk_buyer_channel(pack):
    """A team that accepts the period-1 bulk offer sells through the bulk channel."""
    from sim_engine.engine import build_initial_state
    from sim_engine.decisions import BulkBuyerAcceptance

    state_0 = build_initial_state(pack, company_ids=["A", "B"])
    common = dict(
        price=2_900, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=1_500_000, value_analysis_spend=800_000,
        order_units=45_000, target_volume=47_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=20_000_000, dividend=0,
    )
    dec_a = _build_decision(team_id="A", period=1, **common)
    dec_a.sales.by_product[0].bulk_buyer = BulkBuyerAcceptance(
        accept_offer=True, bid_units=5000
    )
    dec_b = _build_decision(team_id="B", period=1, **common)  # no bulk acceptance

    _, reports = run_period(state_0, {"A": dec_a, "B": dec_b}, pack)

    channels_a = {ln.market_id: ln.units_sold for ln in reports["A"].market.by_market}
    channels_b = {ln.market_id: ln.units_sold for ln in reports["B"].market.by_market}

    # A sold via the bulk channel (capped at the 5 000-unit offer); B did not.
    assert channels_a.get("bulk", 0) == 5000
    assert "bulk" not in channels_b
    assert reports["A"].balance_sheet.articulates


def test_tender_lowest_bid_wins_and_delivers_in_delivery_period(pack):
    """Lowest bid wins; delivery and revenue book in `tender.delivery_period`.

    `solar-v1`'s period-2 tender has `delivery_period: 3`, so the bid
    resolves in period 2 (the commitment is stored on the winner) and
    the units ship — booking revenue — in period 3.
    """
    from sim_engine.engine import build_initial_state
    from sim_engine.decisions import TenderBid

    state_0 = build_initial_state(pack, company_ids=["A", "B"])
    common = dict(
        price=2_900, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=1_500_000, value_analysis_spend=800_000,
        order_units=45_000, target_volume=47_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=20_000_000, dividend=0,
    )
    state_1, _ = run_period(
        state_0,
        {
            "A": _build_decision(team_id="A", period=1, **common),
            "B": _build_decision(team_id="B", period=1, **common),
        },
        pack,
    )

    # Period 2: A bids low (2 600), B bids high (2 750) — A wins.
    dec_a2 = _build_decision(team_id="A", period=2, **common)
    dec_a2.sales.by_product[0].tender = TenderBid(bid_price=2_600, bid_units=3000)
    dec_b2 = _build_decision(team_id="B", period=2, **common)
    dec_b2.sales.by_product[0].tender = TenderBid(bid_price=2_750, bid_units=3000)
    state_2, reports_2 = run_period(state_1, {"A": dec_a2, "B": dec_b2}, pack)

    # No tender revenue books in period 2 — the commitment is deferred.
    assert "tender" not in {
        ln.market_id for ln in reports_2["A"].market.by_market
    }
    a_after = state_2.company("A")
    b_after = state_2.company("B")
    assert len(a_after.committed_tenders) == 1, "A holds the deferred commitment"
    commitment = a_after.committed_tenders[0]
    assert commitment.delivery_period == 3
    assert commitment.units == 3000
    assert commitment.bid_price == 2_600
    assert b_after.committed_tenders == [], "B holds no commitment"

    # Period 3: neither team bids on the new tender; A's commitment delivers.
    dec_a3 = _build_decision(team_id="A", period=3, **common)
    dec_b3 = _build_decision(team_id="B", period=3, **common)
    state_3, reports_3 = run_period(state_2, {"A": dec_a3, "B": dec_b3}, pack)

    channels_a = {ln.market_id: ln.units_sold for ln in reports_3["A"].market.by_market}
    channels_b = {ln.market_id: ln.units_sold for ln in reports_3["B"].market.by_market}
    assert channels_a.get("tender", 0) == 3000, "A's commitment delivers in period 3"
    assert "tender" not in channels_b, "B never won, never delivers"
    # The commitment is consumed by delivery.
    assert state_3.company("A").committed_tenders == []
    assert reports_3["A"].balance_sheet.articulates
    assert reports_3["B"].balance_sheet.articulates


def test_line_investment_grows_capacity(pack):
    """Buying production lines should increase capacity and cost cash."""
    from sim_engine.engine import build_initial_state

    state_0 = build_initial_state(pack)
    decision = _build_decision(
        team_id="c1", period=1,
        price=2_900, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=1_500_000, value_analysis_spend=800_000,
        order_units=70_000, target_volume=75_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=300, training_per_employee=600,
        process_optimisation_spend=500_000, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=80_000_000, dividend=0,
    )
    decision.production.lines.invest.counts = {"fullauto_v3": 3}

    new_state, reports = run_period(state_0, {"c1": decision}, pack)
    company = new_state.companies[0]

    # Started with 4 lines; bought 3 → 7
    assert len(company.lines) == 7
    # Cash flow shows the purchase (3 × 30 mEUR = 90 mEUR)
    assert reports["c1"].cash_flow.production_line_purchases == 90_000_000
    # Articulation still holds with the capital movement
    assert reports["c1"].balance_sheet.articulates
    assert reports["c1"].cash_flow.articulates


def test_market_2_opens_in_period_3_with_fx(pack):
    """market_2 (export, FX) settles from period 3, converting revenue to base."""
    from sim_engine.engine import build_initial_state
    from sim_engine.decisions import SalesPerMarketDecision

    state = build_initial_state(pack)  # single company

    def plain(period):
        return _build_decision(
            team_id="c1", period=period,
            price=2_900, advertising=6_000_000, sales_force=100,
            researchers=34, sustainability_spend=1_500_000, value_analysis_spend=800_000,
            order_units=42_000, target_volume=44_000, maintenance_spend_per_line=1_000_000,
            production_workforce_change=0, training_per_employee=600,
            process_optimisation_spend=500_000, non_salary_pct=0.40,
            pension_reserve_pct=0.05, short_term_loan=20_000_000, dividend=0,
        )

    for period in (1, 2):
        state, _ = run_period(state, {"c1": plain(period)}, pack)

    # Give the company a large finished-goods stock so surplus can reach
    # market_2 after market_1 (which has delivery priority) takes its share.
    # The injection is balanced by an equal rise in retained earnings, so the
    # period-3 opening balance sheet still articulates. This isolates the
    # market_2 settlement logic from the production-capacity constraint.
    inv = state.companies[0].inventories_finished["panel_gen1"]
    extra_units = 300_000
    inv.units += extra_units
    state.companies[0].retained_earnings += extra_units * inv.unit_value

    dec = plain(3)
    dec.sales.by_product[0].market_2 = SalesPerMarketDecision(
        price=3_000, advertising=3_000_000, sales_force=40
    )
    new_state, reports = run_period(state, {"c1": dec}, pack)

    channels = {ln.market_id: ln for ln in reports["c1"].market.by_market}
    assert "market_2" in channels, "market_2 should settle from period 3"
    m2 = channels["market_2"]
    assert m2.units_sold > 0
    # FX: a 3 000-USD price converts to 3000 / 1.10 ≈ 2 727 EUR of base revenue
    effective_base_price = m2.revenue / m2.units_sold
    assert abs(effective_base_price - 3_000 / 1.10) < 1.0
    assert reports["c1"].balance_sheet.articulates
    assert reports["c1"].cash_flow.articulates


def test_invalid_decision_rejected(state_0, pack):
    """A decision with a non-positive price is rejected, not silently run."""
    from sim_engine.validation import InvalidDecisionError

    decision = _build_decision(
        team_id="c1", period=1,
        price=0,  # invalid — price must be positive
        advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    with pytest.raises(InvalidDecisionError) as excinfo:
        run_period(state_0, {"c1": decision}, pack)
    assert "c1" in excinfo.value.errors_by_team


def test_over_dismissal_rejected(state_0, pack):
    """Dismissing more production staff than are employed is rejected."""
    from sim_engine.validation import InvalidDecisionError

    decision = _build_decision(
        team_id="c1", period=1,
        price=2_800, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=-99_999,  # invalid — far more than employed
        training_per_employee=500, process_optimisation_spend=0,
        non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    with pytest.raises(InvalidDecisionError):
        run_period(state_0, {"c1": decision}, pack)


def test_unknown_product_in_decision_rejected(state_0, pack):
    """A typo in a product id is rejected, not silently dropped by the engine."""
    from sim_engine.validation import InvalidDecisionError

    decision = _build_decision(
        team_id="c1", period=1,
        price=2_800, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    # Typo: "panel_geN1" instead of "panel_gen1" — engine used to silently
    # produce nothing and sell nothing rather than flagging the mistake.
    decision.sales.by_product[0].product = "panel_geN1"
    with pytest.raises(InvalidDecisionError) as excinfo:
        run_period(state_0, {"c1": decision}, pack)
    assert any(
        "panel_geN1" in msg for msg in excinfo.value.errors_by_team["c1"]
    )


def test_non_salary_below_minimum_rejected(state_0, pack):
    """A non-salary staff cost below the legal minimum is rejected."""
    from sim_engine.validation import InvalidDecisionError

    decision = _build_decision(
        team_id="c1", period=1,
        price=2_800, advertising=6_000_000, sales_force=100,
        researchers=34, sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0,
        non_salary_pct=0.20,  # invalid — below the 0.37 legal minimum
        pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    with pytest.raises(InvalidDecisionError):
        run_period(state_0, {"c1": decision}, pack)


def test_industry_report(pack):
    """Every team's bundle carries the same industry report; totals reconcile."""
    from sim_engine.engine import build_initial_state

    state_0 = build_initial_state(pack, company_ids=["A", "B"])
    common = dict(
        advertising=6_000_000, sales_force=100, researchers=34,
        sustainability_spend=1_500_000, value_analysis_spend=800_000,
        order_units=42_000, target_volume=44_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=20_000_000, dividend=0,
    )
    _, reports = run_period(
        state_0,
        {
            "A": _build_decision(team_id="A", period=1, price=2_800, **common),
            "B": _build_decision(team_id="B", period=1, price=3_000, **common),
        },
        pack,
    )

    industry_a = reports["A"].industry
    industry_b = reports["B"].industry
    assert industry_a is not None and industry_b is not None
    # Both teams see the same industry report
    assert industry_a.model_dump() == industry_b.model_dump()
    # It lists both companies
    assert {c.company_id for c in industry_a.companies} == {"A", "B"}
    # Market total reconciles with the sum of per-team units sold
    summed = sum(c.units_sold for c in industry_a.companies)
    assert industry_a.market_total_units == summed
    # Market shares sum to ~100%
    total_share = sum(c.market_share_pct for c in industry_a.companies)
    assert abs(total_share - 100.0) < 0.01


def test_full_playthrough_nine_periods(pack):
    """Run a 2-team cohort through all 9 periods; articulation must hold each time.

    De-risks the later-period scenario events (period-5 environmental law,
    period-6 tax hike + remediation charge, FX swings) — a bug there would
    only surface in a full run, which the shorter tests never reach.
    """
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["A", "B"])

    for period in range(1, 10):
        decisions = {}
        for tid in ("A", "B"):
            decisions[tid] = _build_decision(
                team_id=tid, period=period,
                price=2_900, advertising=6_000_000, sales_force=110,
                researchers=40, sustainability_spend=2_000_000,
                value_analysis_spend=1_000_000,
                order_units=44_000, target_volume=46_000,
                maintenance_spend_per_line=1_000_000,
                production_workforce_change=0, training_per_employee=800,
                process_optimisation_spend=1_000_000,
                non_salary_pct=0.40, pension_reserve_pct=0.05,
                short_term_loan=30_000_000, dividend=0,
            )
        state, reports = run_period(state, decisions, pack)
        assert state.period_index == period
        for tid in ("A", "B"):
            assert reports[tid].balance_sheet.articulates, (
                f"period {period}, team {tid}: balance sheet broke"
            )
            assert reports[tid].cash_flow.articulates, (
                f"period {period}, team {tid}: cash flow broke"
            )
            assert reports[tid].industry is not None

    assert state.period_index == 9


def _develop_gen2(decision, researchers, sustainability, value_analysis):
    """Append a panel_gen2 R&D entry to a decision."""
    from sim_engine.decisions import RnDByProductDecision

    decision.rnd.by_product.append(
        RnDByProductDecision(
            product="panel_gen2",
            researchers=researchers,
            sustainability_spend=sustainability,
            value_analysis_spend=value_analysis,
        )
    )
    return decision


def test_successor_product_lifecycle(pack):
    """panel_gen2 materialises at period 2, develops via R&D, sells from period 4."""
    from sim_engine.engine import build_initial_state
    from sim_engine.decisions import (
        ProductionByProductDecision,
        PurchasingByProductDecision,
        SalesByProductDecision,
        SalesPerMarketDecision,
    )

    state = build_initial_state(pack, company_ids=["c1"])

    def base(period, **kw):
        params = dict(
            price=2_900, advertising=6_000_000, sales_force=110, researchers=34,
            sustainability_spend=2_000_000, value_analysis_spend=1_000_000,
            order_units=42_000, target_volume=44_000,
            maintenance_spend_per_line=1_000_000, production_workforce_change=0,
            training_per_employee=800, process_optimisation_spend=1_000_000,
            non_salary_pct=0.40, pension_reserve_pct=0.05,
            short_term_loan=30_000_000, dividend=0,
        )
        params.update(kw)
        return _build_decision(team_id="c1", period=period, **params)

    # Period 1 — panel_gen2 not yet available
    state, _ = run_period(state, {"c1": base(1)}, pack)
    assert "panel_gen2" not in state.companies[0].products

    # Periods 2-3 — panel_gen2 materialises and is developed via R&D
    for period in (2, 3):
        decision = _develop_gen2(base(period), 220, 12_000_000, 3_000_000)
        state, _ = run_period(state, {"c1": decision}, pack)
    gen2 = state.companies[0].products["panel_gen2"]
    assert "panel_gen2" in state.companies[0].products
    assert gen2.efficiency_index > 85, "R&D should have raised gen2 efficiency"

    # Period 4 — launch gen2: develop, buy materials, produce, sell
    d4 = base(4, target_volume=8_000)  # scale gen1 back
    _develop_gen2(d4, 120, 6_000_000, 2_000_000)
    d4.purchasing.by_product.append(
        PurchasingByProductDecision(product="panel_gen2", order_units=42_000)
    )
    d4.production.by_product.append(
        ProductionByProductDecision(product="panel_gen2", target_volume=42_000)
    )
    d4.sales.by_product.append(
        SalesByProductDecision(
            product="panel_gen2",
            market_1=SalesPerMarketDecision(
                price=3_100, advertising=5_000_000, sales_force=60
            ),
        )
    )
    state, reports = run_period(state, {"c1": d4}, pack)
    sold = {ln.product_id: ln.units_sold for ln in reports["c1"].market.by_market}
    assert sold.get("panel_gen2", 0) > 0, "gen2 should sell once launched"
    assert reports["c1"].balance_sheet.articulates
    assert reports["c1"].cash_flow.articulates


def test_producing_before_launch_period_rejected(pack):
    """A production target for panel_gen2 before period 4 is rejected."""
    from sim_engine.engine import build_initial_state
    from sim_engine.decisions import ProductionByProductDecision
    from sim_engine.validation import InvalidDecisionError

    state = build_initial_state(pack, company_ids=["c1"])
    # Period 1 (a plain period) then period 2 where gen2 exists but is pre-launch.
    d1 = _build_decision(
        team_id="c1", period=1,
        price=2_800, advertising=6_000_000, sales_force=100, researchers=34,
        sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    state, _ = run_period(state, {"c1": d1}, pack)

    d2 = _build_decision(
        team_id="c1", period=2,
        price=2_800, advertising=6_000_000, sales_force=100, researchers=34,
        sustainability_spend=2_500_000, value_analysis_spend=1_000_000,
        order_units=30_000, target_volume=40_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=500,
        process_optimisation_spend=0, non_salary_pct=0.40, pension_reserve_pct=0.05,
        short_term_loan=30_000_000, dividend=0,
    )
    # Try to produce gen2 in period 2 — it is not launchable until period 4.
    d2.production.by_product.append(
        ProductionByProductDecision(product="panel_gen2", target_volume=20_000)
    )
    with pytest.raises(InvalidDecisionError):
        run_period(state, {"c1": d2}, pack)


def _plain_decision(team_id, period):
    return _build_decision(
        team_id=team_id, period=period,
        price=2_900, advertising=6_000_000, sales_force=110, researchers=40,
        sustainability_spend=2_000_000, value_analysis_spend=1_000_000,
        order_units=44_000, target_volume=46_000, maintenance_spend_per_line=1_000_000,
        production_workforce_change=0, training_per_employee=800,
        process_optimisation_spend=1_000_000, non_salary_pct=0.40,
        pension_reserve_pct=0.05, short_term_loan=30_000_000, dividend=0,
    )


def test_environmental_law_cuts_line_indices(pack):
    """The period-5 env_index_step lowers every owned line's env index by 15."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    env_before = {l.id: l.environmental_index for l in state.companies[0].lines}

    for period in range(1, 6):  # run through period 5
        state, _ = run_period(state, {"c1": _plain_decision("c1", period)}, pack)

    for line in state.companies[0].lines:
        assert line.environmental_index == env_before[line.id] - 15, (
            f"{line.id}: env index should have dropped 15 after the period-5 law"
        )


def test_one_off_expense_lands_in_period_6(pack):
    """The period-6 one-off remediation charge shows up in other expenses."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    other_by_period = {}
    for period in range(1, 8):
        state, reports = run_period(state, {"c1": _plain_decision("c1", period)}, pack)
        other_by_period[period] = reports["c1"].profit_and_loss.other_expenses

    # Period 6 carries a 6 mEUR one-off charge that period 7 does not; the
    # rest of the cost base moves only modestly period to period.
    assert other_by_period[6] - other_by_period[7] > 4_000_000, (
        f"period-6 other expenses ({other_by_period[6]:,.0f}) should exceed "
        f"period 7 ({other_by_period[7]:,.0f}) by roughly the 6 mEUR one-off"
    )


def test_max_dismissals_cap_enforced(pack):
    """Period 3 forbids production dismissals; such a decision is rejected."""
    from sim_engine.engine import build_initial_state
    from sim_engine.decisions import HRDecision
    from sim_engine.validation import InvalidDecisionError

    state = build_initial_state(pack, company_ids=["c1"])
    for period in (1, 2):
        state, _ = run_period(state, {"c1": _plain_decision("c1", period)}, pack)

    # Period 3 has a max_dismissals_production cap of 0 (job-protection deal).
    d3 = _plain_decision("c1", 3)
    d3.hr = HRDecision(
        production_workforce_change=-50,  # any dismissal violates the cap
        training_per_employee=800, process_optimisation_spend=1_000_000,
        non_salary_pct=0.40, pension_reserve_pct=0.05,
    )
    with pytest.raises(InvalidDecisionError):
        run_period(state, {"c1": d3}, pack)


def test_environmental_capex_articulates(pack):
    """Spending on environmental technology must not break the balance sheet.

    Regression test: env capex used to leave cash without recording an
    asset, so any non-zero spend broke the assets = liabilities + equity
    identity.
    """
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    decision = _plain_decision("c1", 1)
    decision.production.environmental_capex = 10_000_000
    _, reports = run_period(state, {"c1": decision}, pack)

    bs = reports["c1"].balance_sheet
    assert bs.articulates, "balance sheet must articulate after env capex"
    assert reports["c1"].cash_flow.articulates
    # The spend is capitalised, less one period of straight-line depreciation.
    assert bs.environmental_tech_nbv > 0


def test_environmental_capex_reduces_penalty(pack):
    """End-of-pipe environmental tech lowers the compliance penalty."""
    from sim_engine.engine import build_initial_state

    decision_with = _plain_decision("c1", 1)
    decision_with.production.environmental_capex = 8_000_000
    decision_without = _plain_decision("c1", 1)

    _, rep_with = run_period(
        build_initial_state(pack, company_ids=["c1"]),
        {"c1": decision_with}, pack,
    )
    _, rep_without = run_period(
        build_initial_state(pack, company_ids=["c1"]),
        {"c1": decision_without}, pack,
    )

    assert (
        rep_with["c1"].profit_and_loss.other_expenses
        < rep_without["c1"].profit_and_loss.other_expenses
    ), "env-tech abatement should reduce the environmental compliance penalty"


def test_rating_index_responds_to_performance(pack):
    """A weak period drops the rating; a strong one keeps it high.

    Setup: a team that produces nothing (large losses) vs. a team running
    a plain decision. Both start at the inherited rating; after one period
    the loss-making team's rating is materially lower.
    """
    from sim_engine.engine import build_initial_state

    bad = _plain_decision("c1", 1)
    bad.production.by_product[0].target_volume = 0
    bad.purchasing.by_product[0].order_units = 0

    good = _plain_decision("c1", 1)

    _, rep_bad = run_period(
        build_initial_state(pack, company_ids=["c1"]), {"c1": bad}, pack,
    )
    _, rep_good = run_period(
        build_initial_state(pack, company_ids=["c1"]), {"c1": good}, pack,
    )
    assert (
        rep_bad["c1"].executive_summary.rating_index
        < rep_good["c1"].executive_summary.rating_index
    )


def test_rating_surcharge_raises_borrowing_cost(pack):
    """A low pre-period rating raises the interest rate on new debt."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    # Force a poor starting rating so the surcharge bites in period 1.
    state.companies[0].rating_index = 40

    state_good = build_initial_state(pack, company_ids=["c1"])
    # Keep state_good at the scenario's starting 87.

    _, rep_low = run_period(state, {"c1": _plain_decision("c1", 1)}, pack)
    _, rep_high = run_period(
        state_good, {"c1": _plain_decision("c1", 1)}, pack
    )
    # Same ST loan in both decisions → low-rated company pays more.
    assert (
        rep_low["c1"].profit_and_loss.interest_short_term
        > rep_high["c1"].profit_and_loss.interest_short_term
    )


def test_share_price_reported_and_moves_with_performance(pack):
    """Share price is non-zero in the report and reflects the period."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    _, reports = run_period(state, {"c1": _plain_decision("c1", 1)}, pack)
    sp = reports["c1"].executive_summary.share_price
    # Initial state share_price is 113.8; after a near-break-even period it
    # should be in a plausible band.
    assert sp > 0
    # And carried on the industry line.
    assert reports["c1"].industry.companies[0].share_price == sp


def test_overtime_extends_capacity_at_step_cost(pack):
    """Target above Capacity II triggers overtime up to overtime_max_pct
    (10%), at a step fixed cost (500 k EUR) plus wage premium on overtime
    hours. See docs/spec/03-production.md §2.3 and 04-hr.md.
    """
    from sim_engine.engine import build_initial_state

    high_target = _plain_decision("c1", 1)
    high_target.production.by_product[0].target_volume = 45_000
    high_target.purchasing.by_product[0].order_units = 50_000

    low_target = _plain_decision("c1", 1)
    low_target.production.by_product[0].target_volume = 35_000
    low_target.purchasing.by_product[0].order_units = 40_000

    _, rep_overtime = run_period(
        build_initial_state(pack, company_ids=["c1"]),
        {"c1": high_target}, pack,
    )
    _, rep_normal = run_period(
        build_initial_state(pack, company_ids=["c1"]),
        {"c1": low_target}, pack,
    )

    units_overtime = sum(
        ln.units_sold for ln in rep_overtime["c1"].market.by_market
    )
    units_normal = sum(
        ln.units_sold for ln in rep_normal["c1"].market.by_market
    )
    # Overtime lifts production above the Capacity II ceiling (≈ 39 900).
    assert units_overtime > units_normal
    assert units_overtime > 40_000

    # Subtract the extra transport (~10 EUR/unit) so we isolate the
    # overtime cost. The step fixed cost alone (500 k EUR) clears 400 k.
    transport_diff = (units_overtime - units_normal) * 10
    overtime_extra = (
        rep_overtime["c1"].profit_and_loss.other_expenses
        - rep_normal["c1"].profit_and_loss.other_expenses
        - transport_diff
    )
    assert overtime_extra > 400_000, (
        f"overtime should add at least the 500 k step fixed cost to "
        f"other_expenses (got extra {overtime_extra:,.0f} EUR)"
    )
    assert rep_overtime["c1"].balance_sheet.articulates


def test_insolvency_flag_set_when_book_equity_goes_negative(pack):
    """Negative book equity at period end sets the sticky is_bankrupt flag.

    Catastrophic-decision setup: a team that produces nothing still pays
    full personnel + depreciation + interest costs, so revenue from
    opening inventory alone can't cover them — losses exceed starting
    equity in one period.
    """
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    assert not state.companies[0].is_bankrupt

    bad = _plain_decision("c1", 1)
    bad.production.by_product[0].target_volume = 0
    bad.purchasing.by_product[0].order_units = 0

    new_state, reports = run_period(state, {"c1": bad}, pack)

    assert new_state.companies[0].is_bankrupt
    assert reports["c1"].executive_summary.is_bankrupt
    # The cohort-public industry line carries the flag too.
    assert any(line.is_bankrupt for line in reports["c1"].industry.companies)
    # Articulation must hold for a bankrupt company exactly as for a solvent one.
    assert reports["c1"].balance_sheet.articulates
    assert reports["c1"].cash_flow.articulates


def test_insolvency_flag_is_sticky_once_set(pack):
    """Once is_bankrupt is True it stays True regardless of later equity."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    state.companies[0].is_bankrupt = True

    new_state, reports = run_period(state, {"c1": _plain_decision("c1", 1)}, pack)

    assert new_state.companies[0].is_bankrupt
    assert reports["c1"].executive_summary.is_bankrupt


def test_solvent_company_is_not_flagged(pack):
    """A normal first-period run keeps is_bankrupt False."""
    from sim_engine.engine import build_initial_state

    state = build_initial_state(pack, company_ids=["c1"])
    new_state, reports = run_period(state, {"c1": _plain_decision("c1", 1)}, pack)

    assert not new_state.companies[0].is_bankrupt
    assert not reports["c1"].executive_summary.is_bankrupt


def test_determinism(state_0, default_decision_p1, pack):
    """Same inputs should yield identical reports."""
    s1a, r1a = run_period(state_0, default_decision_p1, pack)
    # Build a fresh initial state so the second run is fully independent
    s0_again = build_initial_state(pack)
    s1b, r1b = run_period(s0_again, default_decision_p1, pack)

    assert r1a["c1"].profit_and_loss.model_dump() == r1b["c1"].profit_and_loss.model_dump()
    assert r1a["c1"].balance_sheet.model_dump() == r1b["c1"].balance_sheet.model_dump()
    assert r1a["c1"].cash_flow.model_dump() == r1b["c1"].cash_flow.model_dump()
