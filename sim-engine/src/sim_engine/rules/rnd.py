"""R&D rule module: index dynamics for efficiency, sustainability, and value analysis.

See `docs/spec/02-rnd.md`. Each period's R&D spend produces a gain on the
relevant product index, partially offsetting a constant per-period decay.
"""

from __future__ import annotations

import math

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import TeamDecision
from sim_engine.scenario import LoadedScenarioPack
from sim_engine.state import CompanyState


def apply_rnd(
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
