"""Production rule module.

Materialise newly-available products and apply scenario notable events;
production-line invest/disinvest; Available Capacity (I/II/III) including
overtime; material purchasing (tiered pricing); the production step
itself (staff/line/material bounds, learning curve, factory materials);
post-production roll-forward into finished-goods inventory at the COGM.

See `docs/spec/03-production.md`.
"""

from __future__ import annotations

import math
from typing import Dict, List

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import TeamDecision
from sim_engine.rules._scratch import _PeriodScratch
from sim_engine.scenario import LoadedScenarioPack, PurchaseTier
from sim_engine.state import (
    CompanyState,
    InventoryRecord,
    ProductionLineState,
    ProductState,
)


# Learning curve — Productivity Index II gain coefficient (Wright's law).
_L_K = 0.07


def materialise_products(
    company: CompanyState, ctx: ResolvedPeriodContext
) -> None:
    """Add ProductState + inventories for products that have become available.

    A product appears in a company's state from its `available_from_period`,
    seeded with the scenario's pre-launch index values. From that period R&D
    can develop it; it becomes producible / sellable from its launch period
    (see docs/spec/02-rnd.md §5).
    """
    for spec in ctx.products:
        if spec.available_from_period > ctx.period:
            continue
        if spec.id in company.products:
            continue
        company.products[spec.id] = ProductState(
            product_id=spec.id,
            efficiency_index=spec.indices.efficiency,
            sustainability_index=spec.indices.sustainability,
            value_analysis_index=spec.indices.value_analysis,
        )
        company.inventories_materials[spec.id] = InventoryRecord(
            units=spec.initial_inventory.input_material_units,
            unit_value=spec.initial_inventory.input_material_unit_value,
        )
        company.inventories_finished[spec.id] = InventoryRecord(
            units=spec.initial_inventory.finished_goods_units,
            unit_value=spec.initial_inventory.finished_goods_unit_value,
        )


def apply_notable_events(
    company: CompanyState,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
) -> None:
    """Apply this period's typed scenario notable events.

    Handled here:
      - `env_index_step`     a permanent change to every owned line's
                             environmental index (e.g. a stricter law)
      - `one_off_other_expense`  a one-off cost booked into other expenses

    Other event types are consumed elsewhere: `production_line_offer` via
    `ctx.line_price_offers` in `apply_line_changes`, `max_dismissals` via
    `ctx.max_dismissals_production` in decision validation. `scoring_period`
    is informational only.
    """
    for ne in ctx.notable_events:
        etype = ne.get("type")
        if etype == "env_index_step":
            delta = ne.get("delta", 0)
            for line in company.lines:
                line.environmental_index = max(0.0, line.environmental_index + delta)
        elif etype == "one_off_other_expense":
            scratch.total_overhead_other += float(ne.get("amount", 0))


def apply_line_changes(
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
        # A one-period production-line offer overrides the catalog price.
        unit_price = ctx.line_price_offers.get(type_id, item.purchase_price)
        for k in range(count):
            company.lines.append(
                ProductionLineState(
                    id=f"{company.id}-{type_id}-p{ctx.period}-{k + 1}",
                    type=type_id,
                    acquisition_period=ctx.period,
                    purchase_value=unit_price,
                    normal_capacity=item.normal_capacity,
                    useful_life=item.useful_life,
                    remaining_life=item.useful_life,
                    other_fixed_cost=item.other_fixed_cost,
                    environmental_index=item.environmental_index,
                )
            )
        scratch.line_purchases += count * unit_price


def compute_available_capacity(
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


def apply_purchasing(
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


def apply_production(
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

    total_capacity_ii = sum(capacity_by_type.values())
    prod_cc = company.cost_centres["production"]
    spec_by_id = {p.id: p for p in ctx.products}

    # A product can only be produced from its launch period.
    def _producible(product_id: str) -> bool:
        spec = spec_by_id.get(product_id)
        return spec is not None and spec.first_launch_period <= ctx.period

    # Capacity-weighted shares so multiple products split the line capacity.
    weighted_targets: Dict[str, float] = {}
    for p_dec in decision.production.by_product:
        if not _producible(p_dec.product):
            continue
        spec = spec_by_id[p_dec.product]
        weighted_targets[p_dec.product] = (
            p_dec.target_volume * spec.capacity_per_line_unit
        )
    total_weighted = sum(weighted_targets.values())

    # Available Capacity III — overtime (docs/spec/03-production.md §2.3).
    # If aggregate target exceeds Capacity II, the engine schedules overtime
    # automatically up to `overtime_max_pct`; both line and staff hours
    # scale by the same overtime_factor (workers operate the lines for the
    # extra hours).
    overtime_max_pct = ctx.world.hr.overtime_max_pct
    if total_capacity_ii > 0 and total_weighted > total_capacity_ii:
        shortfall_ratio = (total_weighted - total_capacity_ii) / total_capacity_ii
        overtime_factor = 1.0 + min(overtime_max_pct, shortfall_ratio)
    else:
        overtime_factor = 1.0
    total_capacity_iii = total_capacity_ii * overtime_factor

    for p_dec in decision.production.by_product:
        if not _producible(p_dec.product):
            scratch.units_produced[p_dec.product] = 0.0
            continue
        spec = spec_by_id[p_dec.product]
        product_state = company.products[p_dec.product]

        # Staff-bound: actual productivity = base × Index I × Index II, with
        # overtime hours extending the per-person capacity.
        per_person = (
            spec.production_capacity_per_person
            * company.productivity_index_i
            * product_state.productivity_index_ii
            * overtime_factor
        )
        staff_capacity = prod_cc.headcount * per_person

        # Line-bound: this product's slice of the shared (Capacity III) pool.
        if total_weighted > 0:
            share = weighted_targets[p_dec.product] / total_weighted
        else:
            share = 0.0
        line_capacity = (total_capacity_iii * share) / spec.capacity_per_line_unit

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

    # Overtime costs (docs/spec/03-production.md §2.3, 04-hr.md). When any
    # overtime is scheduled the team incurs a one-off step fixed cost and a
    # wage premium on the overtime hours only.
    if overtime_factor > 1.0:
        scratch.total_overhead_other += ctx.world.hr.overtime_step_fixed_cost
        regular_production_wages = prod_cc.headcount * prod_cc.salary_per_capita
        scratch.total_overhead_other += (
            regular_production_wages
            * ctx.world.hr.overtime_wage_premium_pct
            * (overtime_factor - 1.0)
        )


def line_depreciation_per_period(line: ProductionLineState) -> float:
    """Straight-line depreciation for one production line, per period.

    Used both in COGM allocation (`apply_inventory_post_production`) and in
    the P&L depreciation line (`apply_depreciation_and_overhead` in
    `rules.accounting`); keeping one formula avoids the two sites silently
    drifting apart.
    """
    if line.remaining_life <= 0 or line.useful_life <= 0:
        return 0.0
    return line.purchase_value / line.useful_life


def apply_inventory_post_production(
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

    line_depreciation_total = sum(
        line_depreciation_per_period(line) for line in company.lines
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
