"""Engine orchestrator and rule modules.

v0.2 (multi-team, full attraction model):

  Period loop has three phases:

  1. Pre-market — per-company: R&D, HR, capacity, purchasing, production.
     Updates finished-goods inventory but does not yet sell anything.

  2. Market settlement — across the cohort: gather attractiveness from each
     company, allocate each market's total demand proportionally to each
     company's share of total attractiveness, then cap by each company's
     available finished inventory. Spillover from under-supply is
     redistributed once.

  3. Post-market — per-company: deduct sales from inventory, compute COGS,
     overhead, depreciation; produce P&L → balance sheet → cash flow with
     all articulation identities holding.

What's still stubbed in v0.2 (TODO markers in code):
  - Bulk buyer / tender channels (sales is retail-only)
  - Multi-market support (sales uses market_1; market_2 logic deferred)
  - Productivity Index I (motivation × competence × adaptation × process_opt)
  - Productivity Index II (learning curve) — cumulative units tracked, factor
    placeholder
  - Auto-scaled purchasing/admin headcount
  - Successor product launch logic
  - Environmental tech investment / damage indicator
  - Slow-moving image / satisfaction / motivation dynamics
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sim_engine.context import ResolvedPeriodContext, resolve_period_context
from sim_engine.decisions import SalesPerMarketDecision, TeamDecision
from sim_engine.reports import (
    BalanceSheetReport,
    CashFlowStatement,
    ExecutiveSummary,
    MarketLine,
    MarketReport,
    ProfitLossStatement,
    ReportBundle,
)
from sim_engine.scenario import (
    LoadedScenarioPack,
    PeriodEvent,
    ProductSpec,
    PurchaseTier,
    ScenarioPack,
)
from sim_engine.state import (
    BalanceSheet,
    CompanyState,
    CostCentreState,
    InventoryRecord,
    LoanState,
    PeriodState,
    ProductState,
    ProductionLineState,
)


# ---------------------------------------------------------------------------
# Helper data structures used between sub-stages of one period.
# ---------------------------------------------------------------------------


@dataclass
class _PeriodScratch:
    """Mutable workspace within one period — not part of the public state."""

    # Per-product computed values
    units_produced: Dict[str, float]
    cgm_per_unit: Dict[str, float]                  # cost of goods manufactured
    units_sold: Dict[str, Dict[str, int]]            # product_id -> market_id -> units
    revenue: Dict[str, Dict[str, float]]
    material_units_consumed: Dict[str, float]
    material_cost_consumed: Dict[str, float]
    factory_material_cost: Dict[str, float]
    transport_cost: Dict[str, Dict[str, float]]

    # Aggregates
    total_revenue: float = 0
    total_cogs: float = 0
    total_other_expenses: float = 0
    total_other_income: float = 0
    total_extraordinary_income: float = 0
    total_extraordinary_expense: float = 0
    total_wages: float = 0
    total_non_salary: float = 0
    total_pension_contribution: float = 0
    total_hiring_costs: float = 0
    total_dismissal_costs: float = 0
    total_training: float = 0
    total_depreciation: float = 0
    total_overhead_other: float = 0  # CI, advertising, market research, R&D consulting, env. compliance, rework, maintenance, etc.

    # Production-line capital movements (investing cash flows)
    line_purchases: float = 0
    disinvestment_proceeds: float = 0

    # Inventory changes
    change_in_finished_inventory: float = 0


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
    _settle_market(
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

    new_state = PeriodState(
        period_index=next_period,
        scenario_id=state.scenario_id,
        scenario_version=state.scenario_version,
        cohort_id=state.cohort_id,
        rng_seed=state.rng_seed,
        companies=new_companies,
    )
    return new_state, reports


# ---------------------------------------------------------------------------
# Per-company orchestration — split into pre-market and post-market
# ---------------------------------------------------------------------------


def _pre_market_phase(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
) -> Tuple[CompanyState, "_PeriodScratch"]:
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

    # 1. R&D — index dynamics
    _apply_rnd(new_company, decision, pack, ctx)

    # 2. HR — workforce + period-event wage updates
    _apply_hr(new_company, decision, pack, ctx, scratch)

    # 3. Production-line investment / disinvestment
    _apply_line_changes(new_company, decision, pack, ctx, scratch)

    # 4. Capacity laddering (includes any lines just bought)
    available_capacity = _compute_available_capacity(new_company, decision, pack)

    # 5. Material purchasing
    _apply_purchasing(new_company, decision, pack, ctx, scratch)

    # 6. Production
    _apply_production(new_company, decision, pack, ctx, scratch, available_capacity)

    # 7. Roll up finished-goods inventory (newly produced units enter at CGM)
    _apply_inventory_post_production(new_company, decision, pack, scratch)

    return new_company, scratch


def _post_market_phase(
    company_before: CompanyState,
    company_mid: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: "_PeriodScratch",
    next_period: int,
) -> Tuple[CompanyState, ReportBundle]:
    """Apply the market settlement output, then close the books."""

    new_company = company_mid  # model_copy was already done in pre-market

    # 7. Apply settlement: deduct sold units from finished inventory, compute COGS
    _apply_sales_allocation_and_finished_inventory(new_company, decision, pack, scratch)

    # 8. Costing — depreciation, overhead, period totals
    _apply_depreciation_and_overhead(new_company, decision, pack, scratch)

    # 9. Finance — interest, tax, dividend; build P&L, BS, CF
    pl, bs, cf = _articulate(
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


# ---------------------------------------------------------------------------
# Rule modules — v0.1 simplified
# ---------------------------------------------------------------------------


def _apply_rnd(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
) -> None:
    """Index dynamics: see `docs/spec/02-rnd.md`.

    Implements the gain function for efficiency/sustainability/value-analysis
    and applies the per-period decay.
    """

    decay = pack.pack.index_decay
    # K and ref values — eventually scenario-set; for v0.2 use sensible defaults.
    K_EFF, REF_EFF = 7.0, 7_000_000
    K_SUS, REF_SUS = 6.0, 4_000_000
    K_VAL, REF_VAL = 4.0, 2_000_000

    for rnd_dec in decision.rnd.by_product:
        if rnd_dec.product not in company.products:
            continue
        ps = company.products[rnd_dec.product]

        # Approximate researcher spend (used only for efficiency index gain)
        rnd_cc = company.cost_centres.get("rnd")
        salary_rnd = rnd_cc.salary_per_capita if rnd_cc else 50_000
        # The non-salary multiplier matches what HR will charge
        researcher_loaded = salary_rnd * (1 + decision.hr.non_salary_pct)
        eff_spend = rnd_dec.researchers * researcher_loaded

        ps.efficiency_index = (
            ps.efficiency_index * (1 - decay.efficiency_per_period)
            + K_EFF * math.log1p(eff_spend / REF_EFF)
        )
        ps.sustainability_index = (
            ps.sustainability_index * (1 - decay.sustainability_per_period)
            + K_SUS * math.log1p(rnd_dec.sustainability_spend / REF_SUS)
        )
        ps.value_analysis_index = (
            ps.value_analysis_index * (1 - decay.value_analysis_per_period)
            + K_VAL * math.log1p(rnd_dec.value_analysis_spend / REF_VAL)
        )


# --- HR coefficients (see docs/spec/04-hr.md §4-§5) -----------------------
# Competence index — gain from training, slow decay otherwise.
_C_K, _C_REF, _DECAY_C = 0.04, 1_600.0, 0.02
# Process-optimisation index — gain from process-opt spend, slow decay.
_P_K, _P_REF, _DECAY_P = 0.05, 2_500_000.0, 0.02
# Adaptation index — orientation drag from a hiring wave.
_A_K = 0.5
# Learning curve — Productivity Index II gain coefficient (Wright's law).
_L_K = 0.07
# Auto-scaled cost centres: headcount ≈ slope · revenue_in_mEUR, clamped.
_PURCHASING_SLOPE, _PURCHASING_MIN, _PURCHASING_MAX = 0.138, 6, 25
_ADMIN_SLOPE, _ADMIN_MIN, _ADMIN_MAX = 1.55, 40, 280


def _apply_hr(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
) -> None:
    """Workforce roll-forward and productivity indices.

    v0.2.x: hires/dismissals on production; auto-scaled purchasing and
    administration headcount (from last period's revenue); period-event wage
    updates; Productivity Index I recomputed from competence, process
    optimisation, adaptation, and motivation.
    """

    world = ctx.world

    # Period-event wage overrides come from the context (already resolved).
    for cc_id, new_salary in ctx.wages_by_cost_centre.items():
        if cc_id in company.cost_centres:
            company.cost_centres[cc_id].salary_per_capita = new_salary

    # --- Production workforce change (team decision) -----------------------
    prod_cc = company.cost_centres["production"]
    opening_production = prod_cc.headcount
    change = decision.hr.production_workforce_change
    hires = max(0, change)
    if change > 0:
        scratch.total_hiring_costs += change * world.hr.hiring_cost_per_head
        prod_cc.headcount += change
    else:
        dismissed = -change
        scratch.total_dismissal_costs += dismissed * world.hr.dismissal_cost_per_head
        prod_cc.headcount = max(0, prod_cc.headcount - dismissed)

    # --- Auto-scaled purchasing & administration ---------------------------
    # Headcount tracks the *previous* period's revenue (avoids a circular
    # dependency on this period's not-yet-settled revenue).
    revenue_m = company.last_period_revenue / 1_000_000.0
    _auto_scale_cost_centre(
        company, "purchasing", revenue_m,
        _PURCHASING_SLOPE, _PURCHASING_MIN, _PURCHASING_MAX, world, scratch,
    )
    _auto_scale_cost_centre(
        company, "administration", revenue_m,
        _ADMIN_SLOPE, _ADMIN_MIN, _ADMIN_MAX, world, scratch,
    )

    # --- Wages for the period ----------------------------------------------
    total_wages = sum(
        cc.headcount * cc.salary_per_capita for cc in company.cost_centres.values()
    )
    scratch.total_wages = total_wages
    scratch.total_non_salary = total_wages * decision.hr.non_salary_pct
    scratch.total_pension_contribution = total_wages * decision.hr.pension_reserve_pct

    # Training cost (production only in v0.2.x).
    scratch.total_training = decision.hr.training_per_employee * prod_cc.headcount
    scratch.total_overhead_other += scratch.total_training

    # Pension reserve accumulates on the balance sheet.
    company.pension_reserve += scratch.total_pension_contribution

    # --- Productivity Index I components -----------------------------------
    # Competence — gain from training, decay otherwise.
    company.competence_index = max(
        0.80,
        company.competence_index * (1 - _DECAY_C)
        + _C_K * math.log1p(decision.hr.training_per_employee / _C_REF),
    )
    # Process optimisation — gain from process-opt spend, decay otherwise.
    company.process_optimisation_index = max(
        0.80,
        company.process_optimisation_index * (1 - _DECAY_P)
        + _P_K * math.log1p(decision.hr.process_optimisation_spend / _P_REF),
    )
    # Adaptation — a hiring wave temporarily drags productivity.
    hire_ratio = hires / opening_production if opening_production > 0 else 0.0
    company.adaptation_index = max(0.5, 1.0 - _A_K * hire_ratio)

    # Motivation — slow drift toward a target set by pay, training and churn.
    churn_ratio = abs(change) / opening_production if opening_production > 0 else 0.0
    target_motivation = (
        80.0
        + 400.0 * (decision.hr.non_salary_pct - world.hr.non_salary_pct_minimum)
        + 30.0 * (company.competence_index - 1.0)
        - 120.0 * churn_ratio
    )
    company.motivation_index = _clip(
        company.motivation_index + 0.30 * (target_motivation - company.motivation_index),
        50.0,
        150.0,
    )

    # Productivity Index I = competence × process-opt × adaptation × motivation.
    # Motivation (100-scale) contributes via a gentle 0.6 + 0.4·(m/100) factor,
    # bounding its effect to roughly [0.8, 1.2].
    motivation_factor = 0.6 + 0.4 * (company.motivation_index / 100.0)
    company.productivity_index_i = (
        company.competence_index
        * company.process_optimisation_index
        * company.adaptation_index
        * motivation_factor
    )


def _auto_scale_cost_centre(
    company: CompanyState,
    cc_id: str,
    revenue_m: float,
    slope: float,
    floor: int,
    cap: int,
    world,
    scratch: _PeriodScratch,
) -> None:
    """Adjust a cost centre's headcount to track revenue; bill hire/fire costs."""
    cc = company.cost_centres.get(cc_id)
    if cc is None:
        return
    target = int(round(slope * revenue_m))
    target = max(floor, min(cap, target))
    delta = target - cc.headcount
    if delta > 0:
        scratch.total_hiring_costs += delta * world.hr.hiring_cost_per_head
    elif delta < 0:
        scratch.total_dismissal_costs += (-delta) * world.hr.dismissal_cost_per_head
    cc.headcount = target


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _apply_line_changes(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
) -> None:
    """Process production-line investment and disinvestment decisions.

    Investment: new lines of a catalog type are appended and are available
    for production in the same period (cash paid in full).

    Disinvestment: a named line is removed; its remaining net book value is
    written off as an extraordinary expense, and a type-specific fraction of
    that book value is recovered as extraordinary income (and cash).

    See docs/spec/03-production.md §1.
    """
    catalog = {item.type_id: item for item in pack.pack.production_line_catalog}

    # --- Disinvestment -----------------------------------------------------
    for line_id in decision.production.lines.disinvest:
        line = next((l for l in company.lines if l.id == line_id), None)
        if line is None:
            continue
        if line.useful_life > 0:
            nbv = line.purchase_value * (line.remaining_life / line.useful_life)
        else:
            nbv = 0.0
        item = catalog.get(line.type)
        residual_pct = item.residual_revenue_pct if item is not None else 0.20
        proceeds = nbv * residual_pct
        scratch.total_extraordinary_income += proceeds
        scratch.total_extraordinary_expense += nbv
        scratch.disinvestment_proceeds += proceeds
        company.lines.remove(line)

    # --- Investment --------------------------------------------------------
    for type_id, count in decision.production.lines.invest.counts.items():
        if count <= 0:
            continue
        item = catalog.get(type_id)
        if item is None:
            continue
        for k in range(count):
            company.lines.append(
                ProductionLineState(
                    id=f"{company.id}-{type_id}-p{ctx.period}-{k + 1}",
                    type=type_id,
                    acquisition_period=ctx.period,
                    purchase_value=item.purchase_price,
                    normal_capacity=item.normal_capacity,
                    useful_life=item.useful_life,
                    remaining_life=item.useful_life,
                    other_fixed_cost=item.other_fixed_cost,
                    environmental_index=item.environmental_index,
                )
            )
        scratch.line_purchases += count * item.purchase_price


def _compute_available_capacity(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
) -> Dict[str, float]:
    """Compute Available Capacity I, II for each line type.

    v0.1: no overtime; we use Available Capacity II as the binding figure.
    Maintenance table from the scenario gives the availability factor.
    """

    # Build a maintenance lookup function from the scenario table.
    table = pack.pack.maintenance_table
    if not table:
        # Sensible default
        availability_fn = lambda spend: 1.0
    else:
        def availability_fn(spend: float) -> float:
            sorted_entries = sorted(table, key=lambda e: e.spend_per_line)
            if spend <= sorted_entries[0].spend_per_line:
                return sorted_entries[0].availability
            if spend >= sorted_entries[-1].spend_per_line:
                return sorted_entries[-1].availability
            for i in range(len(sorted_entries) - 1):
                a, b = sorted_entries[i], sorted_entries[i + 1]
                if a.spend_per_line <= spend <= b.spend_per_line:
                    # linear interpolation
                    t = (spend - a.spend_per_line) / (b.spend_per_line - a.spend_per_line)
                    return a.availability + t * (b.availability - a.availability)
            return sorted_entries[-1].availability

    # Group lines by type, then compute capacity
    capacity_by_type: Dict[str, float] = {}
    maintenance_dec = decision.production.lines.maintenance.spend_per_line

    for line in company.lines:
        spend = maintenance_dec.get(line.type, 100_000)  # minimum if not specified
        avail_factor = availability_fn(spend)
        capacity_by_type[line.type] = capacity_by_type.get(line.type, 0) + line.normal_capacity * avail_factor

    return capacity_by_type


def _apply_purchasing(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
) -> None:
    """Update materials inventory with this period's purchases.

    v0.2: reads product specs from ctx, so event-driven price changes are
    automatically applied.
    """

    spec_by_id = {p.id: p for p in ctx.products}

    for pur_dec in decision.purchasing.by_product:
        if pur_dec.product not in company.inventories_materials:
            continue
        inv = company.inventories_materials[pur_dec.product]
        spec = spec_by_id[pur_dec.product]

        unit_price = _tier_price(spec.purchase_tiers, pur_dec.order_units)
        opening_value = inv.units * inv.unit_value
        purchase_value = pur_dec.order_units * unit_price
        new_units = inv.units + pur_dec.order_units
        if new_units > 0:
            inv.unit_value = (opening_value + purchase_value) / new_units
        inv.units = new_units


def _tier_price(tiers: List[PurchaseTier], units: int) -> float:
    """Look up the EUR/unit price for `units` against the tiered schedule."""
    if not tiers:
        return 0
    for t in tiers:
        if t.max_units is None or units < t.max_units:
            return t.unit_price
    return tiers[-1].unit_price


def _apply_production(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
    capacity_by_type: Dict[str, float],
) -> None:
    """Decide how much to actually produce, respecting capacity and staff.

    v0.2.x: actual per-person productivity = base capacity × Productivity
    Index I (company-wide) × Productivity Index II (per-product learning
    curve). Production-line capacity is shared across products in proportion
    to each product's target volume weighted by its capacity-per-line-unit.
    """

    total_capacity = sum(capacity_by_type.values())
    prod_cc = company.cost_centres["production"]
    spec_by_id = {p.id: p for p in ctx.products}

    # Capacity-weighted shares so multiple products split the line capacity.
    weighted_targets: Dict[str, float] = {}
    for p_dec in decision.production.by_product:
        spec = spec_by_id[p_dec.product]
        weighted_targets[p_dec.product] = (
            p_dec.target_volume * spec.capacity_per_line_unit
        )
    total_weighted = sum(weighted_targets.values())

    for p_dec in decision.production.by_product:
        spec = spec_by_id[p_dec.product]
        product_state = company.products[p_dec.product]

        # Staff-bound: actual productivity = base × Index I × Index II.
        per_person = (
            spec.production_capacity_per_person
            * company.productivity_index_i
            * product_state.productivity_index_ii
        )
        staff_capacity = prod_cc.headcount * per_person

        # Line-bound: this product's slice of the shared production capacity.
        if total_weighted > 0:
            share = weighted_targets[p_dec.product] / total_weighted
        else:
            share = 0.0
        line_capacity = (total_capacity * share) / spec.capacity_per_line_unit

        # Material-bound: how much can current materials inventory support?
        inv = company.inventories_materials[p_dec.product]
        value_analysis_factor = product_state.value_analysis_index / 100.0
        material_capacity = (
            inv.units * value_analysis_factor / spec.input_material_units_per_product
        )

        producible = min(
            p_dec.target_volume,
            line_capacity,
            staff_capacity,
            material_capacity,
        )
        units = max(0.0, producible)
        scratch.units_produced[p_dec.product] = units

        # Materials consumed (value analysis reduces material per unit).
        material_units_used = (
            units * spec.input_material_units_per_product / value_analysis_factor
        )
        material_cost = material_units_used * inv.unit_value
        scratch.material_units_consumed[p_dec.product] = material_units_used
        scratch.material_cost_consumed[p_dec.product] = material_cost

        # Factory materials.
        factory_cost = units * spec.factory_material_cost_per_unit
        scratch.factory_material_cost[p_dec.product] = factory_cost

        # Consume materials inventory (moving-average unit_value unchanged).
        inv.units = max(0.0, inv.units - material_units_used)

        # Learning curve — update Productivity Index II from cumulative output.
        prev_cumulative = product_state.cumulative_units_produced
        if prev_cumulative > 0 and units > 0:
            product_state.productivity_index_ii *= 1 + _L_K * math.log1p(
                units / prev_cumulative
            )
        product_state.cumulative_units_produced += units


def _apply_inventory_post_production(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    scratch: _PeriodScratch,
) -> None:
    """Roll the finished-goods inventory forward with produced units.

    Computes cost-of-goods-manufactured per unit (a simplified version for
    v0.1: direct materials + factory materials + an allocation of production
    wages by produced-volume share + production-line depreciation).
    """

    # Production cost centre wages allocated to all produced units
    prod_cc = company.cost_centres["production"]
    prod_wages_total = prod_cc.headcount * prod_cc.salary_per_capita
    prod_non_salary = prod_wages_total * decision.hr.non_salary_pct
    prod_pension = prod_wages_total * decision.hr.pension_reserve_pct

    # All production-line depreciation (computed at line-by-line below)
    line_depreciation_total = sum(
        line.purchase_value / max(line.useful_life, 1)
        if line.remaining_life > 0 else 0
        for line in company.lines
    )

    total_production_overhead = (
        prod_wages_total + prod_non_salary + prod_pension + line_depreciation_total
    )
    total_units_produced = sum(scratch.units_produced.values())

    for product_id, units in scratch.units_produced.items():
        if units == 0:
            scratch.cgm_per_unit[product_id] = 0
            continue
        share = units / total_units_produced if total_units_produced else 0
        cogm_total = (
            scratch.material_cost_consumed[product_id]
            + scratch.factory_material_cost[product_id]
            + share * total_production_overhead
        )
        cgm_per_unit = cogm_total / units
        scratch.cgm_per_unit[product_id] = cgm_per_unit

        # Update finished-goods inventory (moving average)
        inv = company.inventories_finished[product_id]
        opening_value = inv.units * inv.unit_value
        new_units = inv.units + units
        new_value = opening_value + cogm_total
        if new_units > 0:
            inv.unit_value = new_value / new_units
        inv.units = new_units


def _settle_market(
    companies: Dict[str, CompanyState],
    decisions: Dict[str, TeamDecision],
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratches: Dict[str, _PeriodScratch],
) -> None:
    """Cohort-wide market settlement.

    Finished-goods inventory is allocated across channels in priority order
    (see docs/spec/01-sales.md §3):

      1. Won tenders   — lowest valid bid wins; winner supplies units_required
      2. Bulk buyers   — every accepting team buys up to the per-company cap
      3. Retail        — multinomial attraction model splits the market

    A `committed` ledger tracks how much of each team's inventory the
    priority channels have already consumed, so retail never oversells.
    """

    market_by_id = {m.id: m for m in ctx.markets}

    # Initialise per-company scratch entries.
    for cid in companies:
        scratches[cid].units_sold = {}
        scratches[cid].revenue = {}
        scratches[cid].transport_cost = {}

    active_product_ids = [
        p.id for p in ctx.products if p.available_from_period <= ctx.period
    ]

    # committed[cid][product_id] = units already sold via tender + bulk.
    committed: Dict[str, Dict[str, int]] = {cid: {} for cid in companies}

    # --- Channel 1: tenders (priority 1) -----------------------------------
    for tender in ctx.tenders:
        if tender.product in active_product_ids:
            _resolve_tender(tender, companies, decisions, scratches, committed)

    # --- Channel 2: bulk buyers (priority 2) -------------------------------
    for bulk in ctx.bulk_buyers:
        if bulk.product in active_product_ids:
            _resolve_bulk(bulk, companies, decisions, scratches, committed)

    # --- Channel 3: retail (priority 3) ------------------------------------
    # Settle market_1 before market_2: the domestic market has delivery
    # priority, so it consumes inventory first (tracked via `committed`).
    for market_id in ("market_1", "market_2"):
        market = market_by_id.get(market_id)
        if market is None or market.open_from_period > ctx.period:
            continue
        for product_id in active_product_ids:
            _settle_retail(
                market, product_id, companies, decisions, ctx, scratches, committed
            )


def _record_sale(
    scratch: "_PeriodScratch",
    product_id: str,
    channel: str,
    units: int,
    revenue: float,
    transport: float,
) -> None:
    """Record a sale in one channel into a company's scratch."""
    scratch.units_sold.setdefault(product_id, {})[channel] = units
    scratch.revenue.setdefault(product_id, {})[channel] = revenue
    scratch.transport_cost.setdefault(product_id, {})[channel] = transport
    scratch.total_revenue += revenue


def _available_inventory(
    company: CompanyState, product_id: str, committed: Dict[str, Dict[str, int]]
) -> int:
    """Finished-goods units still available after priority-channel commitments."""
    inv = company.inventories_finished.get(product_id)
    if inv is None:
        return 0
    already = committed[company.id].get(product_id, 0)
    return max(0, int(inv.units) - already)


def _resolve_tender(
    tender,
    companies: Dict[str, CompanyState],
    decisions: Dict[str, TeamDecision],
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
) -> None:
    """Award a tender to the lowest valid bidder; deliver in the current period.

    TODO(v0.3): honour tender.delivery_period — won tenders should be carried
    as a commitment and delivered in a later period.
    """
    # Collect valid bids; iterate sorted by company id for deterministic ties.
    bids: List[Tuple[float, str]] = []
    for cid in sorted(companies):
        company = companies[cid]
        if tender.product not in company.products:
            continue
        sd = next(
            (s for s in decisions[cid].sales.by_product if s.product == tender.product),
            None,
        )
        if sd is None or sd.tender is None or sd.tender.bid_price <= 0:
            continue
        if (
            tender.max_acceptable_price is not None
            and sd.tender.bid_price > tender.max_acceptable_price
        ):
            continue
        bids.append((sd.tender.bid_price, cid))

    if not bids:
        return

    bids.sort()  # lowest price first; ties already broken by sorted cid
    winning_price, winner = bids[0]
    available = _available_inventory(companies[winner], tender.product, committed)
    units = min(tender.units_required, available)
    committed[winner][tender.product] = (
        committed[winner].get(tender.product, 0) + units
    )
    # Tenders carry no transport cost (see docs/spec/01-sales.md §3).
    _record_sale(
        scratches[winner], tender.product, "tender", units, units * winning_price, 0.0
    )


def _resolve_bulk(
    bulk,
    companies: Dict[str, CompanyState],
    decisions: Dict[str, TeamDecision],
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
) -> None:
    """Every team that accepts the bulk offer buys up to the per-company cap."""
    for cid in sorted(companies):
        company = companies[cid]
        if bulk.product not in company.products:
            continue
        sd = next(
            (s for s in decisions[cid].sales.by_product if s.product == bulk.product),
            None,
        )
        if sd is None or sd.bulk_buyer is None or not sd.bulk_buyer.accept_offer:
            continue
        available = _available_inventory(company, bulk.product, committed)
        units = min(sd.bulk_buyer.bid_units, bulk.max_units_per_company, available)
        committed[cid][bulk.product] = committed[cid].get(bulk.product, 0) + units
        # Bulk sales carry no transport cost.
        _record_sale(
            scratches[cid], bulk.product, "bulk", units, units * bulk.price, 0.0
        )


def _settle_retail(
    market,
    product_id: str,
    companies: Dict[str, CompanyState],
    decisions: Dict[str, TeamDecision],
    ctx: ResolvedPeriodContext,
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
) -> None:
    """Multinomial attraction model for one retail market and product.

    Works for both the domestic market (`market_1`, base currency) and the
    export market (`market_2`, foreign currency). For an export market, the
    team's price is quoted in the foreign currency; revenue is converted to
    base currency via the period's FX rate before it enters accounting.
    """
    market_potential = market.market_potential_period_0.get(product_id, 0)
    if market_potential <= 0:
        return

    # FX: units of market currency per 1 base unit (1.0 for the home market).
    fx = market.fx_per_base_at_start or 1.0

    contestants: List[Tuple[str, float, "SalesPerMarketDecision"]] = []
    for cid, company in companies.items():
        if product_id not in company.products:
            continue
        sales_dec = next(
            (s for s in decisions[cid].sales.by_product if s.product == product_id),
            None,
        )
        if sales_dec is None:
            continue
        m_dec = sales_dec.market_1 if market.id == "market_1" else sales_dec.market_2
        if m_dec is None:
            continue
        a = _company_attractiveness(company, product_id, m_dec, market, fx)
        contestants.append((cid, a, m_dec))

    if not contestants:
        return
    total_attractiveness = sum(a for _, a, _ in contestants)
    if total_attractiveness <= 0:
        return

    team_demand: Dict[str, int] = {}
    team_share: Dict[str, float] = {}
    for cid, a, _ in contestants:
        share = a / total_attractiveness
        team_share[cid] = share
        team_demand[cid] = int(round(market_potential * share))

    # Sell up to inventory still available after the priority channels.
    team_sold: Dict[str, int] = {}
    team_unmet: Dict[str, int] = {}
    for cid, _, _ in contestants:
        available = _available_inventory(companies[cid], product_id, committed)
        sold = min(team_demand[cid], available)
        team_sold[cid] = sold
        team_unmet[cid] = team_demand[cid] - sold

    # Spillover: redistribute a fraction of unmet demand to teams that met
    # theirs, once, in proportion to share and capped by remaining supply.
    spillover_fraction = market.spillover_fraction
    total_unmet = sum(team_unmet.values())
    if total_unmet > 0 and spillover_fraction > 0:
        available_to_spillover = int(round(total_unmet * spillover_fraction))
        remaining = available_to_spillover
        recipients = [
            (cid, team_share[cid])
            for cid, _, _ in contestants
            if team_unmet[cid] == 0
        ]
        total_recipient_share = sum(s for _, s in recipients)
        if total_recipient_share > 0:
            for cid, s in recipients:
                extra_demand = int(
                    round(available_to_spillover * (s / total_recipient_share))
                )
                available = _available_inventory(
                    companies[cid], product_id, committed
                )
                extra_sold = min(
                    extra_demand,
                    max(0, available - team_sold[cid]),
                    remaining,
                )
                team_sold[cid] += extra_sold
                remaining -= extra_sold
                if remaining <= 0:
                    break

    for cid, _, m_dec in contestants:
        sold = team_sold[cid]
        # Revenue is recorded in base currency: an export-market price quoted
        # in foreign currency is divided by the FX rate.
        revenue_base = sold * m_dec.price / fx
        # Mark these units committed so a later market sees reduced inventory.
        committed[cid][product_id] = committed[cid].get(product_id, 0) + sold
        _record_sale(
            scratches[cid],
            product_id,
            market.id,
            sold,
            revenue_base,
            sold * market.transport_cost_per_unit,
        )


def _company_attractiveness(
    company: CompanyState,
    product_id: str,
    m_dec,
    market,
    fx: float = 1.0,
) -> float:
    """Multinomial attraction score for one company on one product/market.

    Implements `docs/spec/01-sales.md` §2.1, scored against the cohort.
    Returns a positive float; the caller normalises by the sum across teams.

    `fx` is the market's currency rate (units of market currency per base
    unit). The team's price is converted to base currency before it is
    compared with the base-currency anchor, so the home and export markets
    are scored on the same scale.
    """

    coeffs = market.coefficients
    product_state = company.products[product_id]

    # We score factors against neutral reference values: price uses a
    # scenario-set anchor, advertising/sf use the saturation references,
    # indices use 100.
    # TODO(v0.3): move PRICE_ANCHOR into the market/product spec rather
    # than hard-coding it here.
    PRICE_ANCHOR = 2_800.0  # solar-v1 panel_gen1 retail anchor (base currency)
    REF_INDEX = 100.0

    price_in_base = m_dec.price / fx if fx else m_dec.price
    price_factor = (
        (PRICE_ANCHOR / price_in_base) ** coeffs.beta_price
        if price_in_base > 0
        else 1.0
    )
    ads_eff = (
        1 - math.exp(-m_dec.advertising / coeffs.ads_ref)
        if coeffs.ads_ref > 0
        else 0.0
    )
    ad_factor = ads_eff ** coeffs.beta_ad if ads_eff > 0 else 1e-6
    sf_eff = (
        1 - math.exp(-m_dec.sales_force / coeffs.sf_ref)
        if coeffs.sf_ref > 0
        else 0.0
    )
    sf_factor = sf_eff ** coeffs.beta_sf if sf_eff > 0 else 1e-6

    product_score_raw = (
        coeffs.product_weights.get("efficiency", 0.5)
        * (product_state.efficiency_index / REF_INDEX)
        + coeffs.product_weights.get("sustainability", 0.3)
        * (product_state.sustainability_index / REF_INDEX)
        + coeffs.product_weights.get("value_analysis", 0.2)
        * (product_state.value_analysis_index / REF_INDEX)
    )
    product_score = product_score_raw ** coeffs.beta_prod if product_score_raw > 0 else 1e-6

    image_factor = (company.image_index / 100.0) ** coeffs.beta_img
    sat_factor = (company.satisfaction_index / 100.0) ** coeffs.beta_sat

    return (
        price_factor
        * ad_factor
        * sf_factor
        * product_score
        * image_factor
        * sat_factor
    )


def _apply_sales_allocation_and_finished_inventory(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    scratch: _PeriodScratch,
) -> None:
    """Remove sold units from finished-goods inventory and compute COGS."""

    for product_id, by_market in scratch.units_sold.items():
        total_sold = sum(by_market.values())
        if total_sold == 0:
            continue
        inv = company.inventories_finished[product_id]
        opening_units = inv.units
        opening_value = opening_units * inv.unit_value
        # Sell at the current weighted-average value
        cogs_value = total_sold * inv.unit_value
        new_units = opening_units - total_sold
        if new_units < 0:
            # Should not happen given the supply cap in _apply_sales
            new_units = 0
        new_value = opening_value - cogs_value
        # unit_value stays constant under moving average on a sale
        inv.units = new_units
        # inv.unit_value unchanged

        scratch.total_cogs += cogs_value


def _apply_depreciation_and_overhead(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    scratch: _PeriodScratch,
) -> None:
    """Compute depreciation and roll up overhead expenses for the period.

    v0.1: straight-line depreciation on production lines and a flat
    building depreciation from world defaults. Other overhead includes
    advertising, CI, market research fee, maintenance/rationalisation,
    transport, R&D consulting spend (sustainability + value-analysis).
    """

    world = pack.pack.world

    # Building depreciation
    building_dep = world.production.building_depreciation_per_period

    # Production line depreciation (and decrement remaining_life)
    line_dep = 0.0
    for line in company.lines:
        if line.remaining_life > 0 and line.useful_life > 0:
            per_period = line.purchase_value / line.useful_life
            line_dep += per_period
            line.remaining_life = max(0, line.remaining_life - 1)

    scratch.total_depreciation = building_dep + line_dep

    # Advertising + CI + market research fee + R&D consulting + maintenance
    for sales_dec in decision.sales.by_product:
        if sales_dec.market_1:
            scratch.total_overhead_other += sales_dec.market_1.advertising
        if sales_dec.market_2:
            scratch.total_overhead_other += sales_dec.market_2.advertising
    scratch.total_overhead_other += decision.sales.corporate_identity
    if decision.sales.market_research_report:
        scratch.total_overhead_other += 100_000  # MR_cost default

    for rnd_dec in decision.rnd.by_product:
        scratch.total_overhead_other += (
            rnd_dec.sustainability_spend + rnd_dec.value_analysis_spend
        )

    # Maintenance + rationalisation + process optimisation
    maintenance_total = 0.0
    for line_type, spend in decision.production.lines.maintenance.spend_per_line.items():
        # one spend value × number of lines of that type
        n_lines = sum(1 for line in company.lines if line.type == line_type)
        maintenance_total += spend * n_lines
    scratch.total_overhead_other += maintenance_total

    for line_type, spend in decision.production.lines.rationalisation.spend_per_line.items():
        scratch.total_overhead_other += spend

    scratch.total_overhead_other += decision.hr.process_optimisation_spend

    # Transport costs (already accumulated per (product, market))
    for product_id, by_market in scratch.transport_cost.items():
        scratch.total_overhead_other += sum(by_market.values())

    # Storage costs (post-production inventory levels)
    storage_input = (
        sum(inv.units for inv in company.inventories_materials.values()) / 1000.0
    ) * pack.pack.storage.input_material_cost_per_1000_units
    storage_finished = (
        sum(inv.units for inv in company.inventories_finished.values()) / 1000.0
    ) * pack.pack.storage.finished_goods_cost_per_1000_units
    scratch.total_overhead_other += storage_input + storage_finished

    # Other line fixed costs
    for line in company.lines:
        scratch.total_overhead_other += line.other_fixed_cost


def _articulate(
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
    interest_short = company_after.short_term_loan.amount * (
        decision.finance.short_term_loan or 0
    ) * 0  # placeholder: interest is on the NEW short-term loan or the carried one
    # For MVP: interest on short_term = scheduled new draw × scenario rate
    interest_short_term = decision.finance.short_term_loan * fin_world.short_term_loan_rate
    interest_long_term = (
        company_before.long_term_loan.amount * company_before.long_term_loan.rate
        + decision.finance.long_term_loan * fin_world.long_term_loan_rate
    )
    interest_overdraft = company_before.overdraft.amount * company_before.overdraft.rate

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

    return pl, bs, cf


def _update_slow_indices(
    company: CompanyState,
    decision: TeamDecision,
    scratch: _PeriodScratch,
) -> None:
    """Placeholder for v0.1 — image, satisfaction, motivation evolve here in full spec."""
    # v0.2: implement motivation/image/satisfaction dynamics from spec §4.
    pass


def _build_executive_summary(
    company: CompanyState,
    pl: ProfitLossStatement,
    cf: CashFlowStatement,
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
        share_price=0,  # v0.2 — full share price model
        net_income=pl.net_income,
        revenue=pl.sales_revenue,
        operating_income=pl.operating_income,
        return_on_equity=roe,
        return_on_sales=ros,
        cash_balance=cf.cash_end,
        rating_index=company.rating_index,
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
