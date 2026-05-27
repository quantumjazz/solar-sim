"""Report bundle models.

These are the deterministic views over a `PeriodState` that get returned to
the team and to the cohort-wide industry report. They are *derived* from
state — the engine builds them in `engine.py` after a period transitions.

For v0.1, we ship the most pedagogically central reports:

  - ExecutiveSummary
  - ProfitLossStatement
  - BalanceSheetReport
  - CashFlowStatement
  - MarketReport

More reports (cost-type/centre/unit accounting, contribution margins, HR,
production, R&D, market-research, business-report-of-industry, planning
quality) are deferred to later versions. Their shapes are documented in
`docs/spec/00-overview.md` §6.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExecutiveSummary(BaseModel):
    """The first page of the team's report — headline numbers."""

    model_config = ConfigDict(extra="allow")

    period: int
    company_id: str
    company_name: str
    share_price: float
    net_income: float
    revenue: float
    operating_income: float
    return_on_equity: float
    return_on_sales: float
    cash_balance: float
    rating_index: float
    is_bankrupt: bool = False


class MarketLine(BaseModel):
    """One row of the market report — one product on one market."""

    product_id: str
    market_id: str
    units_sold: int
    revenue: float
    price_per_unit: float


class MarketReport(BaseModel):
    period: int
    by_market: List[MarketLine] = Field(default_factory=list)
    total_units_sold: int = 0
    total_revenue: float = 0


class ProfitLossStatement(BaseModel):
    """Cost-of-sales-method P&L (matches docs/spec/06-accounting.md §5)."""

    period: int

    sales_revenue: float
    change_in_finished_inventory: float
    other_operating_income: float

    material_expenses: float
    # Personnel components
    wages_and_salaries: float
    hiring_and_dismissal_costs: float
    pension_reserve_contribution: float
    non_salary_staff_costs: float

    depreciation: float
    other_expenses: float

    operating_income: float

    investment_income: float
    interest_short_term: float
    interest_long_term: float
    interest_overdraft: float

    earnings_before_tax: float
    extraordinary_income: float
    extraordinary_expense: float

    earnings_before_tax_total: float
    income_tax: float
    net_income: float


class BalanceSheetReport(BaseModel):
    """A balance sheet at end-of-period.

    The `_check` field is populated by the engine with True/False on the
    fundamental identity `total_assets == total_liabilities_and_equity`,
    so teams (and tests) can see at a glance that articulation holds.
    """

    period: int

    # Assets
    land_and_buildings: float
    production_lines_nbv: float
    environmental_tech_nbv: float
    input_material_value: float
    finished_goods_value: float
    trade_receivables: float
    securities: float
    cash: float

    # Equity
    subscribed_capital: float
    capital_reserves: float
    retained_earnings: float
    net_income_for_period: float

    # Reserves and liabilities
    pension_reserve: float
    long_term_loan: float
    short_term_loan: float
    overdraft_loan: float

    total_assets: float
    total_liabilities_and_equity: float
    articulates: bool


class CashFlowStatement(BaseModel):
    """Indirect-method cash flow (matches docs/spec/06-accounting.md §7)."""

    period: int

    # Operating
    net_income: float
    depreciation_added_back: float
    pension_reserve_change: float
    inventory_change: float
    receivables_change: float
    operating_cash_flow: float

    # Investing
    production_line_purchases: float
    environmental_tech_purchases: float
    disinvestment_proceeds: float
    securities_purchases: float
    securities_maturities: float
    investing_cash_flow: float

    # Financing
    short_term_loan_drawn: float
    short_term_loan_repaid: float
    long_term_loan_drawn: float
    long_term_loan_repaid: float
    overdraft_change: float
    dividend_paid: float
    financing_cash_flow: float

    # Totals
    cash_start: float
    cash_end: float
    articulates: bool


class IndustryCompanyLine(BaseModel):
    """One company's published figures, as seen by the whole cohort."""

    company_id: str
    company_name: str
    revenue: float
    operating_income: float
    net_income: float
    total_assets: float
    equity: float
    total_debt: float
    cash: float
    units_sold: int
    market_share_pct: float
    share_price: float
    is_bankrupt: bool = False


class IndustryReport(BaseModel):
    """The cohort-public competitor view (matches docs/spec/00-overview.md §6).

    Every team receives the same industry report each period. It contains the
    level of detail a competitor's published annual report would show, plus
    market-wide totals.
    """

    period: int
    companies: List[IndustryCompanyLine] = Field(default_factory=list)
    market_total_units: int = 0
    market_total_revenue: float = 0


class ReportBundle(BaseModel):
    """All reports for one company for one period."""

    period: int
    company_id: str
    executive_summary: ExecutiveSummary
    market: MarketReport
    profit_and_loss: ProfitLossStatement
    balance_sheet: BalanceSheetReport
    cash_flow: CashFlowStatement
    # The cohort-public competitor view. Set by run_period after every team
    # has settled; the same object is shared across all teams' bundles.
    industry: Optional[IndustryReport] = None
