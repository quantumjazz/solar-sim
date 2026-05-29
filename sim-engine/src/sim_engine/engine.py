"""Engine orchestrator.

`run_period` advances the cohort by one period in three phases:

  1. Pre-market — per-company: materialise newly available products, apply
     notable events, R&D, HR, line investment, capacity, purchasing,
     production. Updates finished-goods inventory but does not yet sell.

  2. Market settlement — across the cohort: tenders and bulk buyers settle
     first (priority channels), then retail in each open market via the
     multinomial attraction model. Each market's demand is allocated to
     companies in proportion to attractiveness and capped by available
     inventory; under-supply spillover is redistributed once.

  3. Post-market — per-company: deduct sales from inventory, compute COGS,
     overhead, depreciation; produce P&L → balance sheet → cash flow with
     all articulation identities holding.

The rule modules under `sim_engine.rules` implement each phase's logic;
this file is the orchestrator that wires them together, plus the
report-bundle builders and `build_initial_state` (cohort setup).

Still simplified:
  - Rationalisation spend is booked as cost but does not raise capacity
  - image_index / satisfaction_index are inert (`_update_slow_indices` is
    a no-op); once dynamic, satisfaction feeds back into the rating
  - Rating uses 7 of 11 spec components; share price uses 4 of 14
    drivers — pilot calibration pending (see docs/spec/05-finance.md §11)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sim_engine.context import ResolvedPeriodContext, resolve_period_context
from sim_engine.decisions import TeamDecision
from sim_engine.reports import (
    ExecutiveSummary,
    IndustryCompanyLine,
    IndustryReport,
    MarketLine,
    MarketReport,
    ProfitLossStatement,
    ReportBundle,
)
from sim_engine.rules._scratch import _PeriodScratch
from sim_engine.rules import accounting as _accounting
from sim_engine.rules import finance as _finance
from sim_engine.rules import hr as _hr
from sim_engine.rules import production as _production
from sim_engine.rules import rnd as _rnd
from sim_engine.rules import sales as _sales
from sim_engine.scenario import LoadedScenarioPack
from sim_engine.state import (
    CommittedTender,  # noqa: F401  (re-exported for engine consumers)
    CompanyState,
    CostCentreState,
    InventoryRecord,
    LoanState,
    PeriodState,
    ProductionLineState,
    ProductState,
)
from sim_engine.validation import InvalidDecisionError, validate_decision


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_period(
    state: PeriodState,
    decisions: Dict[str, TeamDecision],
    pack: LoadedScenarioPack,
) -> Tuple[PeriodState, Dict[str, ReportBundle]]:
    """Run one period for the cohort.

    The flow has three phases (see module docstring):
      1. pre-market   — per company
      2. settlement   — across cohort
      3. post-market  — per company

    Returns:
      (new_state, reports_by_team_id)
    """

    next_period = state.period_index + 1
    ctx = resolve_period_context(pack, next_period)

    # Validate that every company has a corresponding decision.
    for company in state.companies:
        if company.id not in decisions:
            raise ValueError(
                f"No decision provided for team {company.id!r}. "
                f"Have decisions for: {list(decisions.keys())}"
            )

    # Validate every decision against hard constraints; reject the whole
    # period if any team's decision is invalid (never silently clamp).
    errors_by_team: Dict[str, List[str]] = {}
    for company in state.companies:
        errs = validate_decision(decisions[company.id], company, ctx)
        if errs:
            errors_by_team[company.id] = errs
    if errors_by_team:
        raise InvalidDecisionError(errors_by_team)

    # ---- Phase 1: pre-market per company ----------------------------------
    mid_companies: Dict[str, CompanyState] = {}
    scratches: Dict[str, _PeriodScratch] = {}
    for company in state.companies:
        decision = decisions[company.id]
        mid_company, scratch = _pre_market_phase(
            company=company,
            decision=decision,
            pack=pack,
            ctx=ctx,
        )
        mid_companies[company.id] = mid_company
        scratches[company.id] = scratch

    # ---- Phase 2: market settlement across cohort -------------------------
    _sales.settle_market(
        companies=mid_companies,
        decisions=decisions,
        pack=pack,
        ctx=ctx,
        scratches=scratches,
    )

    # ---- Phase 3: post-market per company ---------------------------------
    new_companies: List[CompanyState] = []
    reports: Dict[str, ReportBundle] = {}
    for company in state.companies:
        decision = decisions[company.id]
        mid = mid_companies[company.id]
        scratch = scratches[company.id]
        after, bundle = _post_market_phase(
            company_before=company,
            company_mid=mid,
            decision=decision,
            pack=pack,
            ctx=ctx,
            scratch=scratch,
            next_period=next_period,
        )
        new_companies.append(after)
        reports[company.id] = bundle

    # ---- Industry report: the cohort-public competitor view ---------------
    industry = _build_industry_report(reports, next_period)
    for bundle in reports.values():
        bundle.industry = industry

    new_state = PeriodState(
        period_index=next_period,
        scenario_id=state.scenario_id,
        scenario_version=state.scenario_version,
        cohort_id=state.cohort_id,
        rng_seed=state.rng_seed,
        companies=new_companies,
    )
    return new_state, reports


def _build_industry_report(
    reports: Dict[str, ReportBundle], period: int
) -> IndustryReport:
    """Aggregate per-team reports into the cohort-public industry report."""
    total_units = sum(r.market.total_units_sold for r in reports.values())
    total_revenue = sum(r.profit_and_loss.sales_revenue for r in reports.values())

    lines: List[IndustryCompanyLine] = []
    for cid, r in reports.items():
        pl = r.profit_and_loss
        bs = r.balance_sheet
        units = r.market.total_units_sold
        lines.append(
            IndustryCompanyLine(
                company_id=cid,
                company_name=r.executive_summary.company_name,
                revenue=pl.sales_revenue,
                operating_income=pl.operating_income,
                net_income=pl.net_income,
                total_assets=bs.total_assets,
                equity=(
                    bs.subscribed_capital
                    + bs.capital_reserves
                    + bs.retained_earnings
                    + bs.net_income_for_period
                ),
                total_debt=bs.long_term_loan + bs.short_term_loan + bs.overdraft_loan,
                cash=bs.cash,
                units_sold=units,
                market_share_pct=(
                    100.0 * units / total_units if total_units > 0 else 0.0
                ),
                share_price=r.executive_summary.share_price,
                is_bankrupt=r.executive_summary.is_bankrupt,
            )
        )

    return IndustryReport(
        period=period,
        companies=lines,
        market_total_units=total_units,
        market_total_revenue=total_revenue,
    )


# ---------------------------------------------------------------------------
# Per-company orchestration — split into pre-market and post-market
# ---------------------------------------------------------------------------


def _pre_market_phase(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
) -> Tuple[CompanyState, _PeriodScratch]:
    """R&D + HR + capacity + purchasing + production + production-inventory.

    Produces the intermediate company state (post-production, pre-sales) and
    fills in the produce-side fields of the scratch.
    """

    scratch = _PeriodScratch(
        units_produced={},
        cgm_per_unit={},
        units_sold={},
        revenue={},
        material_units_consumed={},
        material_cost_consumed={},
        factory_material_cost={},
        transport_cost={},
    )

    new_company = company.model_copy(deep=True)

    # 0. Materialise any products that have just become available
    _production.materialise_products(new_company, ctx)

    # 0b. Apply scenario notable events (env-index step, one-off expense, …).
    #     Runs before line investment so a one-off env shock hits only the
    #     lines the company already owns, not lines bought this period.
    _production.apply_notable_events(new_company, ctx, scratch)

    # 1. R&D — index dynamics
    _rnd.apply_rnd(new_company, decision, pack, ctx)

    # 2. HR — workforce + period-event wage updates
    _hr.apply_hr(new_company, decision, pack, ctx, scratch)

    # 3. Production-line investment / disinvestment
    _production.apply_line_changes(new_company, decision, pack, ctx, scratch)

    # 4. Capacity laddering (includes any lines just bought)
    available_capacity = _production.compute_available_capacity(new_company, decision, pack)

    # 5. Material purchasing
    _production.apply_purchasing(new_company, decision, pack, ctx, scratch)

    # 6. Production
    _production.apply_production(new_company, decision, pack, ctx, scratch, available_capacity)

    # 7. Roll up finished-goods inventory (newly produced units enter at CGM)
    _production.apply_inventory_post_production(new_company, decision, pack, scratch)

    return new_company, scratch


def _post_market_phase(
    company_before: CompanyState,
    company_mid: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
    next_period: int,
) -> Tuple[CompanyState, ReportBundle]:
    """Apply the market settlement output, then close the books."""

    new_company = company_mid  # model_copy was already done in pre-market

    # 7. Apply settlement: deduct sold units from finished inventory, compute COGS
    _sales.apply_sales_allocation_and_finished_inventory(new_company, decision, pack, scratch)

    # 8. Costing — depreciation, overhead, period totals
    _accounting.apply_depreciation_and_overhead(new_company, decision, pack, ctx, scratch)

    # 9. Finance — interest, tax, dividend; build P&L, BS, CF
    pl, bs, cf = _finance.articulate(
        company_before=company_before,
        company_after=new_company,
        decision=decision,
        pack=pack,
        ctx=ctx,
        scratch=scratch,
        period=next_period,
    )

    # 10. Slow indices (image, satisfaction) — placeholder
    _update_slow_indices(new_company, decision, scratch)

    # Carry this period's revenue forward so next period's purchasing and
    # administration headcounts can auto-scale to it.
    new_company.last_period_revenue = scratch.total_revenue

    # 11. Build report bundle
    exec_sum = _build_executive_summary(
        new_company, pl, cf, scratch, period=next_period
    )
    market_rep = _build_market_report(decision, scratch, period=next_period)

    bundle = ReportBundle(
        period=next_period,
        company_id=company_before.id,
        executive_summary=exec_sum,
        market=market_rep,
        profit_and_loss=pl,
        balance_sheet=bs,
        cash_flow=cf,
    )

    return new_company, bundle


def _update_slow_indices(
    company: CompanyState,
    decision: TeamDecision,
    scratch: _PeriodScratch,
) -> None:
    """No-op stub: image_index and satisfaction_index are not yet dynamic.

    Motivation is already updated inside `rules.hr.apply_hr`. Once image/
    satisfaction dynamics land (docs/spec/04-hr.md §4 and the customer-
    satisfaction component of `rules.finance._compute_rating`), they will
    be computed here.
    """
    pass


def _build_executive_summary(
    company: CompanyState,
    pl: ProfitLossStatement,
    cf,
    scratch: _PeriodScratch,
    period: int,
) -> ExecutiveSummary:
    equity_start = (
        company.subscribed_capital
        + company.capital_reserves
        + company.retained_earnings
    )
    roe = pl.net_income / equity_start if equity_start > 0 else 0
    ros = pl.operating_income / pl.sales_revenue if pl.sales_revenue > 0 else 0

    return ExecutiveSummary(
        period=period,
        company_id=company.id,
        company_name=company.name,
        share_price=company.share_price,
        net_income=pl.net_income,
        revenue=pl.sales_revenue,
        operating_income=pl.operating_income,
        return_on_equity=roe,
        return_on_sales=ros,
        cash_balance=cf.cash_end,
        rating_index=company.rating_index,
        is_bankrupt=company.is_bankrupt,
    )


def _build_market_report(
    decision: TeamDecision,
    scratch: _PeriodScratch,
    period: int,
) -> MarketReport:
    lines: List[MarketLine] = []
    total_units = 0
    total_revenue = 0.0
    for product_id, by_market in scratch.units_sold.items():
        for market_id, units in by_market.items():
            price_per_unit = (
                scratch.revenue[product_id][market_id] / units if units > 0 else 0
            )
            lines.append(
                MarketLine(
                    product_id=product_id,
                    market_id=market_id,
                    units_sold=units,
                    revenue=scratch.revenue[product_id][market_id],
                    price_per_unit=price_per_unit,
                )
            )
            total_units += units
            total_revenue += scratch.revenue[product_id][market_id]
    return MarketReport(
        period=period,
        by_market=lines,
        total_units_sold=total_units,
        total_revenue=total_revenue,
    )


# ---------------------------------------------------------------------------
# Initial-state construction (called once at cohort setup)
# ---------------------------------------------------------------------------


def build_initial_state(
    pack: LoadedScenarioPack,
    cohort_id: str = "default",
    company_ids: Optional[List[str]] = None,
) -> PeriodState:
    """Construct the Period-0 PeriodState from a loaded scenario pack."""

    cs0 = pack.pack.company_state_period_0

    if company_ids is None:
        company_ids = ["c1"]  # MVP: single company

    cost_centres = {
        cc_id: CostCentreState(
            headcount=cc.headcount,
            salary_per_capita=cc.salary_per_capita,
        )
        for cc_id, cc in cs0.cost_centres.items()
    }

    products = {}
    inventories_materials = {}
    inventories_finished = {}
    for product_spec in pack.pack.products:
        if product_spec.available_from_period > 0:
            continue  # not yet active
        products[product_spec.id] = ProductState(
            product_id=product_spec.id,
            efficiency_index=product_spec.indices.efficiency,
            sustainability_index=product_spec.indices.sustainability,
            value_analysis_index=product_spec.indices.value_analysis,
        )
        inventories_materials[product_spec.id] = InventoryRecord(
            units=product_spec.initial_inventory.input_material_units,
            unit_value=product_spec.initial_inventory.input_material_unit_value,
        )
        inventories_finished[product_spec.id] = InventoryRecord(
            units=product_spec.initial_inventory.finished_goods_units,
            unit_value=product_spec.initial_inventory.finished_goods_unit_value,
        )

    lines = [
        ProductionLineState(
            id=line.id,
            type=line.type,
            acquisition_period=line.acquired_period_offset,
            purchase_value=line.purchase_value,
            normal_capacity=line.normal_capacity,
            useful_life=10,  # all v1 line types in catalog have useful_life 10 or 15;
                              # MVP reads remaining_life directly
            remaining_life=line.remaining_life,
            other_fixed_cost=line.other_fixed_cost,
            environmental_index=line.environmental_index,
        )
        for line in pack.pack.existing_lines_period_0
    ]

    # If land_and_buildings is not set in the scenario, compute it as the
    # residual that makes the period-0 balance sheet articulate.
    lines_nbv_p0 = sum(
        line.purchase_value * (line.remaining_life / 10.0)  # all v1 line types: 10-year life
        for line in pack.pack.existing_lines_period_0
    )
    current_assets_p0 = (
        cs0.cash
        + cs0.securities
        + cs0.trade_receivables_from_prior
        + sum(
            ps.initial_inventory.input_material_units * ps.initial_inventory.input_material_unit_value
            for ps in pack.pack.products
            if ps.available_from_period == 0
        )
        + sum(
            ps.initial_inventory.finished_goods_units * ps.initial_inventory.finished_goods_unit_value
            for ps in pack.pack.products
            if ps.available_from_period == 0
        )
    )
    total_lep_p0 = (
        cs0.equity.subscribed_capital
        + cs0.equity.capital_reserves
        + cs0.equity.retained_earnings
        + cs0.equity.prior_period_net_income
        + cs0.pension_reserve
        + cs0.long_term_loan.amount
        + cs0.short_term_loan.amount
        + cs0.overdraft.amount
    )
    if cs0.land_and_buildings is None:
        land_and_buildings_nbv = total_lep_p0 - current_assets_p0 - lines_nbv_p0
        if land_and_buildings_nbv < 0:
            raise ValueError(
                f"Scenario {pack.pack.scenario.id} would require negative land_and_buildings "
                f"({land_and_buildings_nbv}) to balance. Set scenario.company_state_period_0."
                f"land_and_buildings explicitly, or reduce liabilities/equity."
            )
    else:
        land_and_buildings_nbv = cs0.land_and_buildings

    companies: List[CompanyState] = []
    for cid in company_ids:
        company = CompanyState(
            id=cid,
            name=cs0.name,
            cash=cs0.cash,
            securities=cs0.securities,
            short_term_loan=LoanState(
                amount=cs0.short_term_loan.amount,
                rate=cs0.short_term_loan.rate,
                remaining_periods=cs0.short_term_loan.remaining_periods,
            ),
            long_term_loan=LoanState(
                amount=cs0.long_term_loan.amount,
                rate=cs0.long_term_loan.rate,
                remaining_periods=cs0.long_term_loan.remaining_periods,
            ),
            overdraft=LoanState(
                amount=cs0.overdraft.amount,
                rate=cs0.overdraft.rate,
                remaining_periods=cs0.overdraft.remaining_periods,
            ),
            trade_receivables=cs0.trade_receivables_from_prior,
            subscribed_capital=cs0.equity.subscribed_capital,
            capital_reserves=cs0.equity.capital_reserves,
            retained_earnings=cs0.equity.retained_earnings,
            last_period_net_income=cs0.equity.prior_period_net_income,
            last_dividend_declared=cs0.equity.last_dividend,
            pension_reserve=cs0.pension_reserve,
            cost_centres={k: v.model_copy() for k, v in cost_centres.items()},
            products={k: v.model_copy() for k, v in products.items()},
            inventories_materials={k: v.model_copy() for k, v in inventories_materials.items()},
            inventories_finished={k: v.model_copy() for k, v in inventories_finished.items()},
            lines=[l.model_copy() for l in lines],
            motivation_index=cs0.motivation_index,
            competence_index=cs0.competence_index,
            process_optimisation_index=cs0.process_optimisation_index,
            adaptation_index=1.0,
            image_index=cs0.image_index,
            satisfaction_index=cs0.satisfaction_index,
            rating_index=cs0.rating_index,
            productivity_index_i=1.0,
            last_period_revenue=cs0.last_period_revenue,
            land_and_buildings_nbv=land_and_buildings_nbv,
        )
        companies.append(company)

    return PeriodState(
        period_index=pack.pack.scenario.starting_period,
        scenario_id=pack.pack.scenario.id,
        scenario_version=pack.pack.scenario.version,
        cohort_id=cohort_id,
        rng_seed=pack.pack.scenario.random_seed,
        companies=companies,
    )
