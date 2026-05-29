"""HR rule module: workforce roll-forward and productivity indices.

Covers hires/dismissals on production, auto-scaled purchasing and admin
headcount (from prior-period revenue), period-event wage updates, and
Productivity Index I (competence × process-opt × adaptation × motivation).

See `docs/spec/04-hr.md`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import TeamDecision
from sim_engine.rules._scratch import _PeriodScratch
from sim_engine.scenario import LoadedScenarioPack
from sim_engine.state import CompanyState

if TYPE_CHECKING:
    from sim_engine.scenario import WorldDefaults


# --- HR coefficients (see docs/spec/04-hr.md §4-§5) -----------------------
# Competence index — gain from training, slow decay otherwise.
_C_K, _C_REF, _DECAY_C = 0.04, 1_600.0, 0.02
# Process-optimisation index — gain from process-opt spend, slow decay.
_P_K, _P_REF, _DECAY_P = 0.05, 2_500_000.0, 0.02
# Adaptation index — orientation drag from a hiring wave.
_A_K = 0.5
# Auto-scaled cost centres: headcount ≈ slope · revenue_in_mEUR, clamped.
_PURCHASING_SLOPE, _PURCHASING_MIN, _PURCHASING_MAX = 0.138, 6, 25
_ADMIN_SLOPE, _ADMIN_MIN, _ADMIN_MAX = 1.55, 40, 280


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def apply_hr(
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
    world: "WorldDefaults",
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
