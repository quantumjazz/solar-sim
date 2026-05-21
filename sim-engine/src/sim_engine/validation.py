"""Decision validation.

A team's decision is checked against hard constraints before a period runs.
Invalid decisions are rejected with human-readable messages rather than
silently clamped (see docs/spec/00-overview.md §3.1) — silent clamping makes
planning-quality scoring unreliable and produces post-hoc surprises.

v1 scope — hard nonsense only:
  - negative monetary or count values
  - a non-positive price on a market the team is selling in
  - dismissing more production staff than are employed
  - non-salary staff cost below the legal minimum or above 100%
  - a pension-reserve percentage outside [0%, 50%]
  - disinvesting a production line the company does not own
  - malformed tender / bulk bids

Cash affordability is deliberately NOT enforced here: the engine's
auto-overdraft absorbs shortfalls, and the resulting rating and interest
penalty is the intended consequence, not an invalid decision.
"""

from __future__ import annotations

from typing import Dict, List

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import TeamDecision
from sim_engine.state import CompanyState


class InvalidDecisionError(ValueError):
    """Raised when one or more teams submit a decision violating a hard rule.

    `errors_by_team` maps a team id to its list of validation messages.
    """

    def __init__(self, errors_by_team: Dict[str, List[str]]):
        self.errors_by_team = errors_by_team
        lines: List[str] = []
        for team_id, errs in errors_by_team.items():
            for e in errs:
                lines.append(f"[{team_id}] {e}")
        super().__init__("Invalid decision(s):\n  - " + "\n  - ".join(lines))


def validate_decision(
    decision: TeamDecision,
    company: CompanyState,
    ctx: ResolvedPeriodContext,
) -> List[str]:
    """Validate one team's decision. Returns a list of messages; empty == valid."""

    errors: List[str] = []

    def non_negative(value: float, label: str) -> None:
        if value < 0:
            errors.append(f"{label} must be non-negative (got {value})")

    # --- Sales -------------------------------------------------------------
    for sd in decision.sales.by_product:
        for market_label, m in (
            ("market 1", sd.market_1),
            ("market 2", sd.market_2),
        ):
            if m is None:
                continue
            if m.price <= 0:
                errors.append(
                    f"{sd.product} {market_label}: price must be positive "
                    f"(got {m.price})"
                )
            non_negative(m.advertising, f"{sd.product} {market_label} advertising")
            non_negative(m.sales_force, f"{sd.product} {market_label} sales force")
        if sd.tender is not None and sd.tender.bid_price > 0:
            non_negative(sd.tender.bid_units, f"{sd.product} tender bid units")
        if sd.bulk_buyer is not None:
            non_negative(sd.bulk_buyer.bid_units, f"{sd.product} bulk bid units")
    non_negative(decision.sales.corporate_identity, "corporate identity spend")

    # --- R&D ---------------------------------------------------------------
    for rd in decision.rnd.by_product:
        non_negative(rd.researchers, f"{rd.product} researchers")
        non_negative(rd.sustainability_spend, f"{rd.product} sustainability spend")
        non_negative(rd.value_analysis_spend, f"{rd.product} value-analysis spend")

    # --- Purchasing --------------------------------------------------------
    for pd in decision.purchasing.by_product:
        non_negative(pd.order_units, f"{pd.product} input-material order")

    # --- Production --------------------------------------------------------
    for pp in decision.production.by_product:
        non_negative(pp.target_volume, f"{pp.product} target volume")
    for type_id, count in decision.production.lines.invest.counts.items():
        non_negative(count, f"line investment count for {type_id}")
    for type_id, spend in decision.production.lines.maintenance.spend_per_line.items():
        non_negative(spend, f"maintenance spend for {type_id}")
    for type_id, spend in decision.production.lines.rationalisation.spend_per_line.items():
        non_negative(spend, f"rationalisation spend for {type_id}")
    non_negative(decision.production.environmental_capex, "environmental capex")
    owned_line_ids = {line.id for line in company.lines}
    for line_id in decision.production.lines.disinvest:
        if line_id not in owned_line_ids:
            errors.append(f"cannot disinvest unknown production line {line_id!r}")

    # --- HR ----------------------------------------------------------------
    prod_cc = company.cost_centres.get("production")
    prod_headcount = prod_cc.headcount if prod_cc is not None else 0
    change = decision.hr.production_workforce_change
    if change < 0 and -change > prod_headcount:
        errors.append(
            f"cannot dismiss {-change} production staff; "
            f"only {prod_headcount} are employed"
        )
    non_negative(decision.hr.training_per_employee, "training per employee")
    non_negative(
        decision.hr.process_optimisation_spend, "process-optimisation spend"
    )
    nsc_min = ctx.world.hr.non_salary_pct_minimum
    if decision.hr.non_salary_pct < nsc_min:
        errors.append(
            f"non-salary staff cost {decision.hr.non_salary_pct:.0%} is below "
            f"the legal minimum {nsc_min:.0%}"
        )
    if decision.hr.non_salary_pct > 1.0:
        errors.append(
            f"non-salary staff cost {decision.hr.non_salary_pct:.0%} exceeds 100%"
        )
    if not 0.0 <= decision.hr.pension_reserve_pct <= 0.5:
        errors.append(
            f"pension reserve {decision.hr.pension_reserve_pct:.0%} must be "
            f"between 0% and 50%"
        )

    # --- Finance -----------------------------------------------------------
    non_negative(decision.finance.short_term_loan, "short-term loan")
    non_negative(decision.finance.long_term_loan, "long-term loan")
    non_negative(decision.finance.securities_purchase, "securities purchase")
    non_negative(decision.finance.dividend, "dividend")

    # --- Product launch gates ---------------------------------------------
    # A product may exist for R&D before its launch period, but cannot be
    # produced or sold until then.
    launch_period = {p.id: p.first_launch_period for p in ctx.products}
    for sd in decision.sales.by_product:
        lp = launch_period.get(sd.product)
        if lp is not None and lp > ctx.period and (sd.market_1 or sd.market_2):
            errors.append(
                f"{sd.product} cannot be sold before period {lp} "
                f"(pre-launch development only)"
            )
    for pp in decision.production.by_product:
        lp = launch_period.get(pp.product)
        if lp is not None and lp > ctx.period and pp.target_volume > 0:
            errors.append(
                f"{pp.product} cannot be produced before period {lp} "
                f"(pre-launch development only)"
            )

    return errors
