"""Period-state and company-state models.

A `PeriodState` is the engine's canonical persistent object: everything you
need to run the next period is in one of these. The engine's `run_period`
function maps `(PeriodState, decisions) -> (PeriodState, reports)`.

Period states are immutable once produced (Pydantic models with frozen=False
but engine code never mutates a state — it always builds a fresh one).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InventoryRecord(BaseModel):
    """Units and unit value of an inventory line (moving-average valuation)."""

    units: float = 0
    unit_value: float = 0

    @property
    def total_value(self) -> float:
        return self.units * self.unit_value


class CostCentreState(BaseModel):
    """Workforce in one cost centre."""

    headcount: int
    salary_per_capita: float


class LoanState(BaseModel):
    """An outstanding loan."""

    amount: float = 0
    rate: float = 0
    remaining_periods: int = 0


class ProductionLineState(BaseModel):
    """One production line owned by the company."""

    id: str
    type: str
    acquisition_period: int
    purchase_value: float
    normal_capacity: int
    useful_life: int
    remaining_life: int
    other_fixed_cost: float
    environmental_index: float
    cumulative_rationalisation: float = 0


class ProductState(BaseModel):
    """Per-product state for a company.

    Indices are stored alongside cumulative production for the learning-curve
    multiplier (productivity index II). The product's static spec lives in
    the scenario; this is the live, mutable view.
    """

    product_id: str
    efficiency_index: float
    sustainability_index: float
    value_analysis_index: float
    cumulative_units_produced: float = 0
    # Productivity Index II — the learning-curve multiplier. Starts at 1.00
    # and rises as cumulative production grows (see docs/spec/04-hr.md §4.2).
    productivity_index_ii: float = 1.0


class BalanceSheet(BaseModel):
    """A balance sheet at one moment in time.

    The model exposes both detailed line items and aggregate totals; the engine
    is responsible for keeping them consistent (the `total_*` properties).
    """

    # Assets
    land_and_buildings: float = 0
    production_lines_nbv: float = 0
    environmental_tech_nbv: float = 0
    input_material_value: float = 0
    finished_goods_value: float = 0
    trade_receivables: float = 0
    securities: float = 0
    cash: float = 0

    # Equity
    subscribed_capital: float = 0
    capital_reserves: float = 0
    retained_earnings: float = 0
    net_income_for_period: float = 0

    # Reserves and liabilities
    pension_reserve: float = 0
    long_term_loan: float = 0
    short_term_loan: float = 0
    overdraft_loan: float = 0

    @property
    def total_fixed_assets(self) -> float:
        return self.land_and_buildings + self.production_lines_nbv + self.environmental_tech_nbv

    @property
    def total_current_assets(self) -> float:
        return (
            self.input_material_value
            + self.finished_goods_value
            + self.trade_receivables
            + self.securities
            + self.cash
        )

    @property
    def total_assets(self) -> float:
        return self.total_fixed_assets + self.total_current_assets

    @property
    def total_equity(self) -> float:
        return (
            self.subscribed_capital
            + self.capital_reserves
            + self.retained_earnings
            + self.net_income_for_period
        )

    @property
    def total_liabilities(self) -> float:
        return self.long_term_loan + self.short_term_loan + self.overdraft_loan

    @property
    def total_liabilities_and_equity(self) -> float:
        return self.total_equity + self.pension_reserve + self.total_liabilities


class CompanyState(BaseModel):
    """Everything about one company at one moment in time."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str

    # Cash and financial instruments
    cash: float
    securities: float
    short_term_loan: LoanState
    long_term_loan: LoanState
    overdraft: LoanState
    trade_receivables: float = 0

    # Equity / pension
    subscribed_capital: float
    capital_reserves: float
    retained_earnings: float          # cumulative, not including current period
    last_period_net_income: float = 0 # the previous period's net income (for the BS line)
    last_dividend_declared: float = 0 # declared in t-1, payable in t
    pension_reserve: float

    # Operational state
    cost_centres: Dict[str, CostCentreState]
    products: Dict[str, ProductState]
    inventories_materials: Dict[str, InventoryRecord]  # keyed by product_id
    inventories_finished: Dict[str, InventoryRecord]   # keyed by product_id
    lines: List[ProductionLineState]

    # Slow-moving indices.
    #   motivation_index: 100-scale (period 0 typically 80; clipped [50, 150])
    #   competence_index, process_optimisation_index, adaptation_index:
    #     factor-scale, centred at 1.00
    motivation_index: float
    competence_index: float
    process_optimisation_index: float
    adaptation_index: float = 1.0
    image_index: float
    satisfaction_index: float
    rating_index: float

    # Productivity Index I — the within-period productivity multiplier,
    # recomputed each period from the four indices above.
    productivity_index_i: float = 1.0

    # Revenue realised in the previous period — drives auto-scaled headcount
    # for the purchasing and administration cost centres.
    last_period_revenue: float = 0

    # Tax loss carryforward (separate ledger)
    loss_carryforward: float = 0

    # Property, plant and equipment that doesn't sit on a production line
    land_and_buildings_nbv: float = 0

    # Cumulative spend trackers
    cumulative_env_capex: float = 0
    environmental_tech_nbv: float = 0


class PeriodState(BaseModel):
    """The engine's canonical between-periods snapshot.

    A `PeriodState(period_index=t)` represents the *end of period t*, i.e.
    the state that goes into period t+1.
    """

    model_config = ConfigDict(extra="allow")

    period_index: int
    scenario_id: str
    scenario_version: str
    cohort_id: str = "default"
    rng_seed: int = 0
    companies: List[CompanyState]

    def company(self, company_id: str) -> CompanyState:
        for c in self.companies:
            if c.id == company_id:
                return c
        raise KeyError(f"No company with id {company_id!r}")
