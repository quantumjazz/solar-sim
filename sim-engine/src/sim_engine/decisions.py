"""Team decision schema.

A team submits one `TeamDecision` per period. The schema mirrors the six
decision areas defined in `docs/spec/00-overview.md` §3.

For the v0.1 MVP, several sub-sections are stubbed (sales tender, multi-product
R&D, multi-market sales). Their fields are present so callers can begin
populating them, but the engine ignores them until v0.2.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SalesPerMarketDecision(BaseModel):
    price: float
    advertising: float = 0
    sales_force: int = 0


class BulkBuyerAcceptance(BaseModel):
    accept_offer: bool = False
    bid_units: int = 0


class TenderBid(BaseModel):
    bid_price: float = 0
    bid_units: int = 0


class SalesByProductDecision(BaseModel):
    product: str
    market_1: SalesPerMarketDecision
    market_2: Optional[SalesPerMarketDecision] = None
    bulk_buyer: Optional[BulkBuyerAcceptance] = None
    tender: Optional[TenderBid] = None


class SalesDecision(BaseModel):
    by_product: List[SalesByProductDecision]
    corporate_identity: float = 0
    market_research_report: bool = False


class RnDByProductDecision(BaseModel):
    product: str
    researchers: int = 0
    sustainability_spend: float = 0
    value_analysis_spend: float = 0


class RnDDecision(BaseModel):
    by_product: List[RnDByProductDecision]


class PurchasingByProductDecision(BaseModel):
    product: str
    order_units: int = 0


class PurchasingDecision(BaseModel):
    by_product: List[PurchasingByProductDecision]


class ProductionByProductDecision(BaseModel):
    product: str
    target_volume: int = 0


class LineInvestDecision(BaseModel):
    """How many lines of each catalog type to buy this period."""

    model_config = ConfigDict(extra="allow")
    # keys are catalog type_ids, values are counts; we use a Dict for flexibility
    counts: Dict[str, int] = Field(default_factory=dict)


class LineMaintenanceDecision(BaseModel):
    model_config = ConfigDict(extra="allow")
    # keys are catalog type_ids, values are EUR per line per period
    spend_per_line: Dict[str, float] = Field(default_factory=dict)


class LineRationalisationDecision(BaseModel):
    model_config = ConfigDict(extra="allow")
    spend_per_line: Dict[str, float] = Field(default_factory=dict)


class ProductionLinesDecision(BaseModel):
    invest: LineInvestDecision = Field(default_factory=LineInvestDecision)
    disinvest: List[str] = Field(default_factory=list)
    maintenance: LineMaintenanceDecision = Field(default_factory=LineMaintenanceDecision)
    rationalisation: LineRationalisationDecision = Field(default_factory=LineRationalisationDecision)


class ProductionDecision(BaseModel):
    by_product: List[ProductionByProductDecision]
    lines: ProductionLinesDecision = Field(default_factory=ProductionLinesDecision)
    environmental_capex: float = 0


class HRDecision(BaseModel):
    production_workforce_change: int = 0
    training_per_employee: float = 0
    process_optimisation_spend: float = 0
    non_salary_pct: float = 0.40
    pension_reserve_pct: float = 0.05


class PlannedKPIs(BaseModel):
    """Planned values teams declare, used by the planning-quality index."""

    revenue: float = 0
    return_on_equity: float = 0
    operating_cash_flow: float = 0


class FinanceDecision(BaseModel):
    short_term_loan: float = 0
    long_term_loan: float = 0
    securities_purchase: float = 0
    dividend: float = 0
    planned_kpis: PlannedKPIs = Field(default_factory=PlannedKPIs)


class TeamDecision(BaseModel):
    """One team's full decision for one period."""

    model_config = ConfigDict(extra="allow")

    team_id: str
    period: int
    sales: SalesDecision
    rnd: RnDDecision
    purchasing: PurchasingDecision
    production: ProductionDecision
    hr: HRDecision
    finance: FinanceDecision
