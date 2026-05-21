"""Scenario-pack models and loader.

A scenario pack lives under `scenarios/<id>/` and contains:

  - `scenario.yaml`       starting state (Period 0) and world defaults
  - `period-events.yaml`  per-period parameter changes and events
  - `narrative/`          per-period news clippings (Markdown; ignored here)

This module models both YAML files as typed Pydantic objects and provides
`load_scenario_pack(path)` to read them from disk.

See docs/spec/07-scenario-format.md for the schema authoring contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# scenario.yaml
# ---------------------------------------------------------------------------


class ScenarioMeta(BaseModel):
    """Top-level scenario metadata."""

    model_config = ConfigDict(extra="allow")

    id: str
    version: str
    display_name: str
    description: str = ""
    language: str = "en"
    base_currency: str = "EUR"
    starting_period: int = 0
    trial_periods: List[int] = Field(default_factory=list)
    real_periods: List[int]
    random_seed: int = 0


class FinanceWorld(BaseModel):
    model_config = ConfigDict(extra="allow")

    short_term_loan_rate: float = 0.08
    long_term_loan_rate: float = 0.07
    long_term_loan_term: int = 10
    overdraft_rate: float = 0.13
    securities_rate: float = 0.03
    tax_rate: float = 0.30
    payment_in_period_pct: float = 0.80
    min_cash: float = 100_000


class SocialPlanThreshold(BaseModel):
    threshold: float
    extra_per_dismissal: float


class HRWorld(BaseModel):
    model_config = ConfigDict(extra="allow")

    hiring_cost_per_head: float = 12_500
    dismissal_cost_per_head: float = 10_000
    social_plan_thresholds: List[SocialPlanThreshold] = Field(default_factory=list)
    overtime_max_pct: float = 0.10
    overtime_step_fixed_cost: float = 500_000
    overtime_wage_premium_pct: float = 0.25
    non_salary_pct_minimum: float = 0.37
    non_salary_pct_default: float = 0.40
    pension_reserve_pct_default: float = 0.05


class BuildingDistributionKey(BaseModel):
    purchasing: float = 0.05
    production: float = 0.70
    rnd: float = 0.05
    sales: float = 0.05
    administration: float = 0.15


class ProductionWorld(BaseModel):
    model_config = ConfigDict(extra="allow")

    factory_material_cost_per_unit: float = 5
    building_depreciation_per_period: float = 250_000
    building_distribution_key: BuildingDistributionKey = Field(
        default_factory=BuildingDistributionKey
    )
    environmental_compliance_baseline: float = 100
    environmental_penalty_per_index_point: float = 150_000


class WorldDefaults(BaseModel):
    model_config = ConfigDict(extra="allow")

    finance: FinanceWorld = Field(default_factory=FinanceWorld)
    hr: HRWorld = Field(default_factory=HRWorld)
    production: ProductionWorld = Field(default_factory=ProductionWorld)


class CostCentreInitial(BaseModel):
    headcount: int
    salary_per_capita: float


class CompanyEquityInitial(BaseModel):
    subscribed_capital: float
    capital_reserves: float
    retained_earnings: float
    prior_period_net_income: float = 0
    last_dividend: float = 0


class LoanInitial(BaseModel):
    amount: float = 0
    rate: float = 0
    remaining_periods: int = 0


class CompanyStateInitial(BaseModel):
    """The state a team inherits at Period 0."""

    model_config = ConfigDict(extra="allow")

    name: str = "(player-renamed-each-cohort)"
    cash: float = 0
    securities: float = 0
    short_term_loan: LoanInitial = Field(default_factory=LoanInitial)
    long_term_loan: LoanInitial = Field(default_factory=LoanInitial)
    overdraft: LoanInitial = Field(default_factory=LoanInitial)
    pension_reserve: float = 0
    equity: CompanyEquityInitial
    trade_receivables_from_prior: float = 0
    cost_centres: Dict[str, CostCentreInitial]
    motivation_index: float = 80          # 100-scale; companies often start low
    competence_index: float = 1.0         # factor-scale, centred at 1.00
    process_optimisation_index: float = 1.0
    image_index: float = 100
    satisfaction_index: float = 100
    rating_index: float = 70
    # Revenue the inherited company achieved in its last fiscal year — used
    # to auto-scale the purchasing and administration cost centres in period 1.
    last_period_revenue: float = 0
    # Land and buildings (net book value at period 0). Manufacturing companies
    # of this scale typically have significant property/plant on the balance
    # sheet; we set this explicitly to keep the inherited balance sheet
    # consistent. If left at None, build_initial_state computes it as the
    # residual that makes assets == liabilities + equity at period 0.
    land_and_buildings: Optional[float] = None


class PurchaseTier(BaseModel):
    """A single quantity-discount tier for input materials.

    `max_units` is exclusive upper bound (i.e., this tier applies for orders
    *strictly less than* `max_units`). The last tier has `max_units = null`
    meaning "no upper bound".
    """

    max_units: Optional[int] = None
    unit_price: float


class ProductIndices(BaseModel):
    efficiency: float = 100
    sustainability: float = 100
    value_analysis: float = 100


class InitialInventory(BaseModel):
    input_material_units: float = 0
    input_material_unit_value: float = 0
    finished_goods_units: float = 0
    finished_goods_unit_value: float = 0


class ProductSpec(BaseModel):
    """A product available in the simulation."""

    model_config = ConfigDict(extra="allow")

    id: str
    display_name: str
    category: str = "panel"
    available_from_period: int = 0
    indices: ProductIndices = Field(default_factory=ProductIndices)
    input_material_units_per_product: float = 1.0
    factory_material_cost_per_unit: float = 5
    capacity_per_line_unit: float = 1.0
    production_capacity_per_person: float = 50
    initial_inventory: InitialInventory = Field(default_factory=InitialInventory)
    purchase_tiers: List[PurchaseTier] = Field(default_factory=list)


class MarketCoefficients(BaseModel):
    model_config = ConfigDict(extra="allow")

    alpha_market: float = 0.6
    beta_price: float = 2.5
    beta_ad: float = 0.7
    beta_sf: float = 0.5
    beta_prod: float = 1.2
    beta_img: float = 0.5
    beta_sat: float = 0.5
    product_weights: Dict[str, float] = Field(default_factory=dict)
    ads_ref: float = 12_000_000
    sf_ref: float = 200
    ci_ref: float = 3_000_000


class MarketSpec(BaseModel):
    """A market in the scenario (domestic, export, etc.)."""

    model_config = ConfigDict(extra="allow")

    id: str
    display_name: str
    currency: str = "EUR"
    open_from_period: int = 0
    transport_cost_per_unit: float = 0
    spillover_fraction: float = 0.80
    coefficients: MarketCoefficients = Field(default_factory=MarketCoefficients)
    market_potential_period_0: Dict[str, int] = Field(default_factory=dict)
    fx_per_base_at_start: Optional[float] = None


class LineCatalogItem(BaseModel):
    """A type of production line a team can buy throughout the game."""

    model_config = ConfigDict(extra="allow")

    type_id: str
    display_name: str
    purchase_price: float
    useful_life: int
    normal_capacity: int
    other_fixed_cost: float
    environmental_index: float
    residual_revenue_pct: float
    max_purchase_per_period: int = 9


class ExistingLineSpec(BaseModel):
    """A production line the company starts with at Period 0."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    acquired_period_offset: int
    normal_capacity: int
    purchase_value: float
    remaining_life: int
    other_fixed_cost: float
    environmental_index: float


class StorageCosts(BaseModel):
    input_material_cost_per_1000_units: float = 50_000
    finished_goods_cost_per_1000_units: float = 100_000


class MaintenanceTableEntry(BaseModel):
    spend_per_line: float
    availability: float


class IndexDecay(BaseModel):
    efficiency_per_period: float = 0.01
    sustainability_per_period: float = 0.01
    value_analysis_per_period: float = 0.01
    competence_per_period: float = 0.01


class ScenarioPack(BaseModel):
    """The full content of `scenario.yaml`."""

    model_config = ConfigDict(extra="allow")

    scenario: ScenarioMeta
    world: WorldDefaults
    company_state_period_0: CompanyStateInitial
    products: List[ProductSpec]
    markets: List[MarketSpec]
    production_line_catalog: List[LineCatalogItem]
    existing_lines_period_0: List[ExistingLineSpec] = Field(default_factory=list)
    storage: StorageCosts = Field(default_factory=StorageCosts)
    maintenance_table: List[MaintenanceTableEntry] = Field(default_factory=list)
    index_decay: IndexDecay = Field(default_factory=IndexDecay)
    period_0_decisions_narrative_only: Dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_consistency(self) -> "ScenarioPack":
        # The starting period must precede the first real period.
        if self.scenario.starting_period >= min(self.scenario.real_periods):
            raise ValueError(
                f"starting_period ({self.scenario.starting_period}) must be < "
                f"min(real_periods) ({min(self.scenario.real_periods)})"
            )
        # Every existing line type must be in the catalog.
        catalog_types = {item.type_id for item in self.production_line_catalog}
        for line in self.existing_lines_period_0:
            if line.type not in catalog_types:
                raise ValueError(
                    f"existing line {line.id} has unknown type '{line.type}' "
                    f"(catalog: {sorted(catalog_types)})"
                )
        return self


# ---------------------------------------------------------------------------
# period-events.yaml
# ---------------------------------------------------------------------------


class BulkBuyerOffer(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: str
    product: str
    max_units_per_company: int
    price: float
    note: Optional[str] = None
    prepayment_required: bool = False


class TenderOffer(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: str
    product: str
    units_required: int
    max_acceptable_price: Optional[float] = None
    delivery_period: int
    note: Optional[str] = None


class ProductUnlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: str
    development_required: bool = False
    available_for_production_from: Optional[int] = None
    available_for_sale_from: Optional[int] = None
    pre_launch_indices_at_unlock: Optional[Dict[str, float]] = None
    notes: Optional[str] = None


class NotableEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    # Other fields are event-type-specific; we allow extras.


class PeriodEvent(BaseModel):
    """One period's worth of changes from `period-events.yaml`."""

    model_config = ConfigDict(extra="allow")

    period: int
    phase: str = "real"
    headline: str = ""
    narrative_file: Optional[str] = None
    economy: Dict = Field(default_factory=dict)
    parameter_changes: Dict = Field(default_factory=dict)
    market_changes: Dict = Field(default_factory=dict)
    bulk_buyers: List[BulkBuyerOffer] = Field(default_factory=list)
    tenders: List[TenderOffer] = Field(default_factory=list)
    product_unlocks: List[ProductUnlock] = Field(default_factory=list)
    notable_events: List[NotableEvent] = Field(default_factory=list)


class PeriodEventsFile(BaseModel):
    events: List[PeriodEvent]


# ---------------------------------------------------------------------------
# The combined loaded pack
# ---------------------------------------------------------------------------


class LoadedScenarioPack(BaseModel):
    """Everything the engine needs from a scenario pack, after loading."""

    pack: ScenarioPack
    events: List[PeriodEvent]
    source_path: str

    def event_for_period(self, period: int) -> Optional[PeriodEvent]:
        for ev in self.events:
            if ev.period == period:
                return ev
        return None


def load_scenario_pack(path: Union[str, Path]) -> LoadedScenarioPack:
    """Load a scenario pack from `<path>/scenario.yaml` and `<path>/period-events.yaml`."""

    p = Path(path)
    scenario_file = p / "scenario.yaml"
    events_file = p / "period-events.yaml"

    if not scenario_file.exists():
        raise FileNotFoundError(f"scenario.yaml not found at {scenario_file}")
    if not events_file.exists():
        raise FileNotFoundError(f"period-events.yaml not found at {events_file}")

    with open(scenario_file) as f:
        pack_raw = yaml.safe_load(f)
    with open(events_file) as f:
        events_raw = yaml.safe_load(f)

    pack = ScenarioPack.model_validate(pack_raw)
    events_file_model = PeriodEventsFile.model_validate(events_raw)

    return LoadedScenarioPack(
        pack=pack,
        events=events_file_model.events,
        source_path=str(p.resolve()),
    )
