"""Finance rule module: articulation, credit rating, share price.

`articulate` builds the period's P&L, balance sheet, and cash-flow
statement, and enforces the three articulation identities (see
docs/spec/06-accounting.md §9). It also updates the dynamic credit
rating (which surcharges next period's interest) and the share-price
proxy.

MVP simplifications (rating uses 7 of 11 components, share price uses
4 of 14 drivers) are documented in docs/spec/05-finance.md §11.x; the
β coefficients here are pilot-calibration placeholders.
"""

from __future__ import annotations

import math
from typing import Tuple

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import TeamDecision
from sim_engine.reports import (
    BalanceSheetReport,
    CashFlowStatement,
    ProfitLossStatement,
)
from sim_engine.rules._scratch import _PeriodScratch
from sim_engine.scenario import LoadedScenarioPack
from sim_engine.state import CompanyState, LoanState


# ---------------------------------------------------------------------------
# Credit rating, interest-rate surcharge, and share price
# ---------------------------------------------------------------------------
#
# Implements `docs/spec/05-finance.md` §4 (rating) and §5 (share price)
# with the MVP simplifications noted in 05-finance.md §11.x:
#
# - Rating uses 7 of the spec's 11 components — the ones computable from
#   single-period engine state without time-series history. Components
#   that need EMAs (net-income trend, planning-quality trend) and ones
#   sourced from inactive indices (customer satisfaction is currently a
#   no-op) are deferred. Weights are renormalised to 1.0 over the
#   included components.
#
# - Share price uses 4 drivers (ROE, ROS, equity level, debt/equity)
#   instead of the spec's 14. The β coefficients are initial values and
#   need pilot calibration to reproduce the "baseline ≈ flat / breakout
#   ≈ ±20-30 %" target in 05-finance.md §5.
#
# - The rating index at period end takes effect on next period's
#   interest rates (we apply `_rating_surcharge(company_before.rating)`
#   when computing interest). This matches the "floating LT rate" intent
#   in §1.2.


def _score_component(value: float, low: float, high: float) -> float:
    """Linear 0-100 score with `low` mapped to 0 and `high` to 100, clamped."""
    if high == low:
        return 50.0
    return max(0.0, min(100.0, (value - low) / (high - low) * 100.0))


def _score_inverted(value: float, good_at: float, bad_at: float) -> float:
    """As above but inverted — `good_at` → 100, `bad_at` → 0."""
    if bad_at == good_at:
        return 50.0
    return max(0.0, min(100.0, (bad_at - value) / (bad_at - good_at) * 100.0))


#: Rating-table entries (`(score, surcharge)`) from `05-finance.md` §4.2.
#: The function interpolates linearly between them.
_RATING_SURCHARGE_TABLE = (
    (0, 0.100),
    (20, 0.070),
    (30, 0.050),
    (40, 0.035),
    (50, 0.020),
    (60, 0.010),
    (70, 0.000),
    (80, -0.005),
    (90, -0.010),
    (100, -0.010),
)


def _rating_surcharge(rating: float) -> float:
    """Map a rating in [0, 100] to an interest-rate surcharge (e.g. +2 %).

    See `docs/spec/05-finance.md` §4.2 for the table.
    """
    rating = max(0.0, min(100.0, rating))
    for i in range(len(_RATING_SURCHARGE_TABLE) - 1):
        r0, s0 = _RATING_SURCHARGE_TABLE[i]
        r1, s1 = _RATING_SURCHARGE_TABLE[i + 1]
        if r0 <= rating <= r1:
            if r1 == r0:
                return s0
            t = (rating - r0) / (r1 - r0)
            return s0 + t * (s1 - s0)
    return 0.0


def _compute_rating(
    *,
    book_equity: float,
    total_assets: float,
    total_debt: float,
    overdraft_amount: float,
    operating_cash_flow: float,
    net_income: float,
    motivation_index: float,
    productivity_index_i: float,
) -> float:
    """Composite credit-rating score in [0, 100].

    MVP — uses the seven components that are computable from a single
    period's engine state, with weights renormalised to 1.0. See
    `docs/spec/05-finance.md` §4.1 for the spec's full 11-component
    composite; the remaining four need history (EMA-style) or inputs
    from indices that are presently inert in the engine.
    """
    equity_ratio = book_equity / total_assets if total_assets > 0 else 0.0
    overdraft_ratio = (
        overdraft_amount / book_equity
        if book_equity > 0
        else (1.0 if overdraft_amount > 0 else 0.0)
    )
    ocf_over_debt = (
        operating_cash_flow / total_debt if total_debt > 0 else 1.0
    )

    return (
        0.25 * _score_component(equity_ratio, 0.0, 0.5)
        + 0.15 * _score_component(book_equity / 1_000_000.0, 0.0, 50.0)
        + 0.15 * _score_inverted(overdraft_ratio, 0.0, 0.30)
        + 0.15 * _score_component(ocf_over_debt, 0.0, 0.30)
        + 0.15 * _score_component(net_income / 1_000_000.0, -5.0, 10.0)
        + 0.10 * _score_component(motivation_index, 50.0, 150.0)
        + 0.05 * _score_component(productivity_index_i, 0.5, 1.5)
    )


# Share-price model — initial constants per `05-finance.md` §5; pilot
# calibration will replace these with values that reproduce the §5
# acceptance criteria (baseline ≈ flat, breakout ≈ +20-30%, failing ≈
# -20-30%).
_SHARE_PRICE_BASE = 100.0      # EUR/share — a low starting reference
_SP_BETA_ROE = 100.0           # EUR per 100% ROE
_SP_BETA_ROS = 50.0            # EUR per 100% ROS
_SP_BETA_EQ_MILLION = 0.7      # EUR per 1m EUR of book equity
_SP_BETA_DEBT_EQUITY = 30.0    # EUR per 100% of debt-to-equity


def _compute_share_price(
    *,
    return_on_equity: float,
    return_on_sales: float,
    book_equity: float,
    total_debt: float,
) -> float:
    """Share-price proxy from a few core drivers. Returns EUR/share, ≥ 0."""
    debt_equity = total_debt / book_equity if book_equity > 0 else 0.0
    return max(
        0.0,
        _SHARE_PRICE_BASE
        + _SP_BETA_ROE * return_on_equity
        + _SP_BETA_ROS * return_on_sales
        + _SP_BETA_EQ_MILLION * (book_equity / 1_000_000.0)
        - _SP_BETA_DEBT_EQUITY * debt_equity,
    )


def articulate(
    company_before: CompanyState,
    company_after: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
    period: int,
) -> Tuple[ProfitLossStatement, BalanceSheetReport, CashFlowStatement]:
    """Build P&L, balance sheet, and cash-flow statement.

    This is where the articulation identities are enforced.
    """

    world = ctx.world

    # ---- Inventory change ----
    fg_opening = sum(
        inv.total_value for inv in company_before.inventories_finished.values()
    )
    fg_closing = sum(
        inv.total_value for inv in company_after.inventories_finished.values()
    )
    scratch.change_in_finished_inventory = fg_closing - fg_opening

    # ---- Material expenses (for P&L: cost of materials consumed in production) ----
    material_expenses = sum(scratch.material_cost_consumed.values()) + sum(
        scratch.factory_material_cost.values()
    )

    # ---- Personnel costs ----
    personnel_wages = scratch.total_wages
    personnel_non_salary = scratch.total_non_salary
    personnel_pension = scratch.total_pension_contribution
    personnel_hires_fires = scratch.total_hiring_costs + scratch.total_dismissal_costs

    # ---- Operating income ----
    # Cost-of-sales P&L:
    # Revenue + ΔFG inventory + Other income
    #  - Material expenses
    #  - Personnel (wages + non-salary + pension + hires/fires)
    #  - Depreciation
    #  - Other expenses
    operating_income = (
        scratch.total_revenue
        + scratch.change_in_finished_inventory
        + scratch.total_other_income
        - material_expenses
        - personnel_wages
        - personnel_non_salary
        - personnel_pension
        - personnel_hires_fires
        - scratch.total_depreciation
        - scratch.total_overhead_other
    )

    # ---- Interest ----
    fin_world = world.finance
    # Rating-based surcharge uses last period's rating (see 05-finance.md §1.2
    # — "floating" LT rate re-prices each period to the company's current
    # rating). At period 1 this is the inherited starting rating.
    rating_surcharge = _rating_surcharge(company_before.rating_index)
    interest_short_term = decision.finance.short_term_loan * (
        fin_world.short_term_loan_rate + rating_surcharge
    )
    interest_long_term = (
        company_before.long_term_loan.amount
        * (fin_world.long_term_loan_rate + rating_surcharge)
        + decision.finance.long_term_loan
        * (fin_world.long_term_loan_rate + rating_surcharge)
    )
    interest_overdraft = company_before.overdraft.amount * (
        fin_world.overdraft_rate + rating_surcharge
    )

    investment_income = company_before.securities * fin_world.securities_rate

    # ---- EBT regular ----
    ebt_regular = operating_income + investment_income - (
        interest_short_term + interest_long_term + interest_overdraft
    )

    extraordinary_income = scratch.total_extraordinary_income
    extraordinary_expense = scratch.total_extraordinary_expense
    ebt_total = ebt_regular + extraordinary_income - extraordinary_expense

    # ---- Tax with loss carryforward ----
    new_loss_carry = company_after.loss_carryforward
    tax_rate = fin_world.tax_rate
    # ctx.world.finance.tax_rate already reflects any period-event override.

    if ebt_total >= 0:
        taxable = max(0.0, ebt_total - new_loss_carry)
        income_tax = taxable * tax_rate
        new_loss_carry = max(0.0, new_loss_carry - ebt_total)
    else:
        income_tax = 0
        new_loss_carry += -ebt_total
    company_after.loss_carryforward = new_loss_carry

    net_income = ebt_total - income_tax

    # ---- Build P&L ----
    pl = ProfitLossStatement(
        period=period,
        sales_revenue=scratch.total_revenue,
        change_in_finished_inventory=scratch.change_in_finished_inventory,
        other_operating_income=scratch.total_other_income,
        material_expenses=material_expenses,
        wages_and_salaries=personnel_wages,
        hiring_and_dismissal_costs=personnel_hires_fires,
        pension_reserve_contribution=personnel_pension,
        non_salary_staff_costs=personnel_non_salary,
        depreciation=scratch.total_depreciation,
        other_expenses=scratch.total_overhead_other,
        operating_income=operating_income,
        investment_income=investment_income,
        interest_short_term=interest_short_term,
        interest_long_term=interest_long_term,
        interest_overdraft=interest_overdraft,
        earnings_before_tax=ebt_regular,
        extraordinary_income=extraordinary_income,
        extraordinary_expense=extraordinary_expense,
        earnings_before_tax_total=ebt_total,
        income_tax=income_tax,
        net_income=net_income,
    )

    # ---- Cash flow (indirect method) ----
    # Operating
    inventory_change = (
        fg_closing - fg_opening
        + sum(inv.total_value for inv in company_after.inventories_materials.values())
        - sum(inv.total_value for inv in company_before.inventories_materials.values())
    )

    receivables_period_t = scratch.total_revenue * (1 - fin_world.payment_in_period_pct)
    receivables_period_t_minus_1_collected = company_before.trade_receivables
    receivables_change = receivables_period_t - receivables_period_t_minus_1_collected

    operating_cf = (
        net_income
        + scratch.total_depreciation
        + scratch.total_pension_contribution
        - inventory_change
        - receivables_change
    )

    # Investing
    line_purchases = scratch.line_purchases
    env_tech_purchases = decision.production.environmental_capex
    disinvestment_proceeds = scratch.disinvestment_proceeds
    securities_purchases = decision.finance.securities_purchase
    securities_maturities = company_before.securities

    investing_cf = (
        -line_purchases
        - env_tech_purchases
        + disinvestment_proceeds
        - securities_purchases
        + securities_maturities
    )

    # Financing
    st_drawn = decision.finance.short_term_loan
    st_repaid = company_before.short_term_loan.amount
    lt_drawn = decision.finance.long_term_loan
    lt_repaid = 0  # LT loans don't amortize early
    overdraft_repaid = company_before.overdraft.amount
    dividend_paid = company_before.last_dividend_declared

    financing_cf = (
        st_drawn - st_repaid + lt_drawn - lt_repaid - overdraft_repaid - dividend_paid
    )

    # ---- Now wire the cash and balance through ----
    # Cash flows
    cash_start = company_before.cash
    cash_end = cash_start + operating_cf + investing_cf + financing_cf

    # Auto-overdraft if cash would go negative or below min_cash
    overdraft_drawn = 0.0
    if cash_end < fin_world.min_cash:
        overdraft_drawn = fin_world.min_cash - cash_end
        cash_end = fin_world.min_cash
        financing_cf += overdraft_drawn

    # ---- Update company_after with closing cash and loan balances ----
    company_after.cash = cash_end
    company_after.securities = decision.finance.securities_purchase
    company_after.short_term_loan = LoanState(
        amount=st_drawn, rate=fin_world.short_term_loan_rate, remaining_periods=1
    )
    company_after.long_term_loan = LoanState(
        amount=company_before.long_term_loan.amount + lt_drawn,
        rate=fin_world.long_term_loan_rate,
        remaining_periods=max(0, company_before.long_term_loan.remaining_periods - 1)
        if company_before.long_term_loan.amount > 0
        else fin_world.long_term_loan_term,
    )
    company_after.overdraft = LoanState(
        amount=overdraft_drawn, rate=fin_world.overdraft_rate, remaining_periods=1
    )
    company_after.trade_receivables = receivables_period_t

    # Retained earnings: prior retained + (last period's net income − last dividend declared)
    new_retained = (
        company_before.retained_earnings
        + company_before.last_period_net_income
        - company_before.last_dividend_declared
    )
    company_after.retained_earnings = new_retained
    company_after.last_period_net_income = net_income
    company_after.last_dividend_declared = decision.finance.dividend

    # Insolvency check (docs/spec/05-finance.md §11): if book equity is
    # negative at period end, set the sticky `is_bankrupt` flag. A bankrupt
    # company keeps playing — the flag is a pedagogical signal, not a
    # game-over.
    book_equity_end = (
        company_after.subscribed_capital
        + company_after.capital_reserves
        + company_after.retained_earnings
        + net_income
    )
    company_after.is_bankrupt = (
        company_before.is_bankrupt or book_equity_end < 0
    )

    # ---- Production-line NBV ----
    production_lines_nbv = sum(
        line.purchase_value * (line.remaining_life / line.useful_life)
        if line.useful_life > 0
        else 0
        for line in company_after.lines
    )

    # Depreciate buildings (250 000 EUR / period by default — from scenario world).
    building_dep_per_period = ctx.world.production.building_depreciation_per_period
    company_after.land_and_buildings_nbv = max(
        0, company_after.land_and_buildings_nbv - building_dep_per_period
    )

    bs = BalanceSheetReport(
        period=period,
        # assets
        land_and_buildings=company_after.land_and_buildings_nbv,
        production_lines_nbv=production_lines_nbv,
        environmental_tech_nbv=company_after.environmental_tech_nbv,
        input_material_value=sum(
            inv.total_value for inv in company_after.inventories_materials.values()
        ),
        finished_goods_value=sum(
            inv.total_value for inv in company_after.inventories_finished.values()
        ),
        trade_receivables=company_after.trade_receivables,
        securities=company_after.securities,
        cash=company_after.cash,
        # equity
        subscribed_capital=company_after.subscribed_capital,
        capital_reserves=company_after.capital_reserves,
        retained_earnings=company_after.retained_earnings,
        net_income_for_period=net_income,
        # reserves and liabilities
        pension_reserve=company_after.pension_reserve,
        long_term_loan=company_after.long_term_loan.amount,
        short_term_loan=company_after.short_term_loan.amount,
        overdraft_loan=company_after.overdraft.amount,
        total_assets=0,  # filled below
        total_liabilities_and_equity=0,
        articulates=False,
    )

    bs.total_assets = (
        bs.land_and_buildings
        + bs.production_lines_nbv
        + bs.environmental_tech_nbv
        + bs.input_material_value
        + bs.finished_goods_value
        + bs.trade_receivables
        + bs.securities
        + bs.cash
    )
    bs.total_liabilities_and_equity = (
        bs.subscribed_capital
        + bs.capital_reserves
        + bs.retained_earnings
        + bs.net_income_for_period
        + bs.pension_reserve
        + bs.long_term_loan
        + bs.short_term_loan
        + bs.overdraft_loan
    )
    bs.articulates = math.isclose(bs.total_assets, bs.total_liabilities_and_equity, rel_tol=1e-6, abs_tol=1.0)

    # ---- Cash flow statement ----
    cf = CashFlowStatement(
        period=period,
        net_income=net_income,
        depreciation_added_back=scratch.total_depreciation,
        pension_reserve_change=scratch.total_pension_contribution,
        inventory_change=inventory_change,
        receivables_change=receivables_change,
        operating_cash_flow=operating_cf,
        production_line_purchases=line_purchases,
        environmental_tech_purchases=env_tech_purchases,
        disinvestment_proceeds=disinvestment_proceeds,
        securities_purchases=securities_purchases,
        securities_maturities=securities_maturities,
        investing_cash_flow=investing_cf,
        short_term_loan_drawn=st_drawn,
        short_term_loan_repaid=st_repaid,
        long_term_loan_drawn=lt_drawn,
        long_term_loan_repaid=lt_repaid,
        overdraft_change=overdraft_drawn - overdraft_repaid,
        dividend_paid=dividend_paid,
        financing_cash_flow=financing_cf,
        cash_start=cash_start,
        cash_end=cash_end,
        articulates=math.isclose(
            cash_end - cash_start, operating_cf + investing_cf + financing_cf,
            rel_tol=1e-6, abs_tol=1.0
        ),
    )

    # ---- Update dynamic indices: credit rating and share price ----
    # Rating uses end-of-period numbers; it takes effect on *next* period's
    # interest rates (this period already priced its loans using
    # `company_before.rating_index`, see §1.2 floating-rate intent).
    equity_start_for_roe = (
        company_before.subscribed_capital
        + company_before.capital_reserves
        + company_before.retained_earnings
    )
    total_debt_end = (
        company_after.short_term_loan.amount
        + company_after.long_term_loan.amount
        + company_after.overdraft.amount
    )
    company_after.rating_index = _compute_rating(
        book_equity=book_equity_end,
        total_assets=bs.total_assets,
        total_debt=total_debt_end,
        overdraft_amount=company_after.overdraft.amount,
        operating_cash_flow=operating_cf,
        net_income=net_income,
        motivation_index=company_after.motivation_index,
        productivity_index_i=company_after.productivity_index_i,
    )
    company_after.share_price = _compute_share_price(
        return_on_equity=(
            net_income / equity_start_for_roe if equity_start_for_roe > 0 else 0.0
        ),
        return_on_sales=(
            pl.operating_income / pl.sales_revenue if pl.sales_revenue > 0 else 0.0
        ),
        book_equity=book_equity_end,
        total_debt=total_debt_end,
    )

    return pl, bs, cf
