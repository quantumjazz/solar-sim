"""Accounting rule module: period depreciation + overhead aggregation.

Computes building/line/env-tech depreciation, end-of-pipe environmental
abatement and the compliance penalty, and rolls up overhead expenses
(advertising, CI, market research, R&D consulting, maintenance,
rationalisation, transport, storage, line fixed costs, env penalty).

See `docs/spec/03-production.md` §6 (environmental compliance) and
`docs/spec/06-accounting.md`.
"""

from __future__ import annotations

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import TeamDecision
from sim_engine.rules._scratch import _PeriodScratch
from sim_engine.rules.production import line_depreciation_per_period
from sim_engine.scenario import LoadedScenarioPack
from sim_engine.state import CompanyState


# Env-tech investment is capitalised and depreciated straight-line. Its net
# book value buys "abatement" index points that offset the environmental
# compliance penalty, so the spend is a genuine lever (see 03-production.md §6).
_ENV_TECH_USEFUL_LIFE = 10                    # periods
_ENV_ABATEMENT_COST_PER_POINT = 1_000_000.0   # EUR of NBV per index point
_ENV_ABATEMENT_CAP = 20.0                     # max index points from abatement


def apply_depreciation_and_overhead(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratch: _PeriodScratch,
) -> None:
    """Compute depreciation and roll up overhead expenses for the period.

    Straight-line depreciation on production lines and buildings. Other
    overhead includes advertising, CI, market-research fee,
    maintenance/rationalisation, transport, R&D consulting spend, storage,
    and the environmental compliance penalty.
    """

    world = ctx.world

    # Building depreciation
    building_dep = world.production.building_depreciation_per_period

    # Production line depreciation (and decrement remaining_life)
    line_dep = 0.0
    for line in company.lines:
        per_period = line_depreciation_per_period(line)
        if per_period > 0:
            line_dep += per_period
            line.remaining_life = max(0, line.remaining_life - 1)

    # Environmental technology — capitalise this period's end-of-pipe spend,
    # then depreciate the pool straight-line over its useful life. The cash
    # outflow is handled in _articulate; recording the asset and its
    # depreciation here is what keeps the balance sheet articulating.
    env_capex = decision.production.environmental_capex
    company.cumulative_env_capex += env_capex
    company.environmental_tech_nbv += env_capex
    env_tech_dep = min(
        company.cumulative_env_capex / _ENV_TECH_USEFUL_LIFE,
        company.environmental_tech_nbv,
    )
    company.environmental_tech_nbv -= env_tech_dep

    scratch.total_depreciation = building_dep + line_dep + env_tech_dep

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

    # Environmental compliance penalty: the company's production fleet
    # (capacity-weighted average environmental index), lifted by any
    # end-of-pipe environmental technology, is compared with the legal
    # baseline. If it still falls short, a per-index-point penalty is
    # charged. The baseline can rise via a period event (e.g. the period-5
    # environmental law).
    if company.lines:
        total_capacity = sum(line.normal_capacity for line in company.lines)
        if total_capacity > 0:
            avg_env_index = (
                sum(
                    line.environmental_index * line.normal_capacity
                    for line in company.lines
                )
                / total_capacity
            )
            # End-of-pipe abatement: env-tech net book value buys index
            # points (up to a cap), making the investment a real lever.
            abatement = min(
                _ENV_ABATEMENT_CAP,
                company.environmental_tech_nbv / _ENV_ABATEMENT_COST_PER_POINT,
            )
            effective_env_index = avg_env_index + abatement
            baseline = world.production.environmental_compliance_baseline
            if effective_env_index < baseline:
                penalty = (baseline - effective_env_index) * (
                    world.production.environmental_penalty_per_index_point
                )
                scratch.total_overhead_other += penalty
