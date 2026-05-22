"""Per-period resolved context.

A `ResolvedPeriodContext` is the scenario's view *as it applies to one period*,
with all relevant period-event overrides already merged in. Rule functions
read from the context, not directly from `pack.pack.world` — that way they
see the period's actual values without each function needing to know about
the override mechanism.

Construction is deterministic from `(LoadedScenarioPack, period)`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from sim_engine.scenario import (
    BulkBuyerOffer,
    LoadedScenarioPack,
    MarketSpec,
    PeriodEvent,
    ProductSpec,
    TenderOffer,
    WorldDefaults,
)


class ResolvedPeriodContext(BaseModel):
    """The scenario world as it applies to one period."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    period: int
    world: WorldDefaults
    products: List[ProductSpec]
    markets: List[MarketSpec]
    wages_by_cost_centre: Dict[str, float] = Field(default_factory=dict)
    bulk_buyers: List[BulkBuyerOffer] = Field(default_factory=list)
    tenders: List[TenderOffer] = Field(default_factory=list)
    notable_events: List[Dict] = Field(default_factory=list)
    # Maximum production-staff dismissals allowed this period (None = no cap).
    max_dismissals_production: Optional[int] = None
    # type_id -> discounted purchase price, for one-period production-line offers.
    line_price_offers: Dict[str, float] = Field(default_factory=dict)
    event: Optional[PeriodEvent] = None

    def product(self, product_id: str) -> ProductSpec:
        for p in self.products:
            if p.id == product_id:
                return p
        raise KeyError(f"No product {product_id!r}")

    def market(self, market_id: str) -> MarketSpec:
        for m in self.markets:
            if m.id == market_id:
                return m
        raise KeyError(f"No market {market_id!r}")


def resolve_period_context(
    pack: LoadedScenarioPack, period: int
) -> ResolvedPeriodContext:
    """Build the period context: world, products, markets with overrides applied."""

    event = pack.event_for_period(period)
    world = pack.pack.world.model_copy(deep=True)
    products = [p.model_copy(deep=True) for p in pack.pack.products]
    markets = [m.model_copy(deep=True) for m in pack.pack.markets]

    wages_by_cc: Dict[str, float] = {}
    bulk_buyers: List[BulkBuyerOffer] = []
    tenders: List[TenderOffer] = []
    notable_events: List[Dict] = []
    max_dismissals_production: Optional[int] = None
    line_price_offers: Dict[str, float] = {}

    if event is not None:
        params = event.parameter_changes or {}

        # ---- Wages (per cost centre) -------------------------------------
        wage_overrides = params.get("wages", {}) or {}
        for cc, salary in wage_overrides.items():
            wages_by_cc[cc] = salary

        # ---- World defaults overrides --------------------------------------
        # Plain top-level keys
        for key, attr_path in [
            ("hiring_cost_per_head", "hr.hiring_cost_per_head"),
            ("dismissal_cost_per_head", "hr.dismissal_cost_per_head"),
            ("factory_material_cost_per_unit", "production.factory_material_cost_per_unit"),
        ]:
            if key in params:
                _set_dotted(world, attr_path, params[key])

        # Dot-notated keys like "finance.short_term_loan_rate" or
        # "world.finance.tax_rate" — both treated the same.
        for key, value in params.items():
            if key in ("wages",):
                continue
            normalised = key
            if normalised.startswith("world."):
                normalised = normalised[len("world."):]
            if "." in normalised:
                try:
                    _set_dotted(world, normalised, value)
                except AttributeError:
                    pass  # silently ignore unknown keys; future-compatible

        # Apply per-product factory_material override globally
        if "factory_material_cost_per_unit" in params:
            new_fmc = params["factory_material_cost_per_unit"]
            for p in products:
                p.factory_material_cost_per_unit = new_fmc

        # ---- Market changes ---------------------------------------------
        market_changes = event.market_changes or {}
        for mid, changes in market_changes.items():
            m = next((mm for mm in markets if mm.id == mid), None)
            if m is None:
                continue
            mc = changes or {}
            if "market_potential_units" in mc:
                m.market_potential_period_0.update(mc["market_potential_units"])
            if "fx_per_base" in mc:
                m.fx_per_base_at_start = mc["fx_per_base"]
            if "open_from_period" in mc and mc["open_from_period"] is not None:
                m.open_from_period = mc["open_from_period"]
            if "transport_cost_per_unit" in mc:
                m.transport_cost_per_unit = mc["transport_cost_per_unit"]

        # ---- Transport-cost overrides (flat dict form) ---------------------
        transport_overrides = params.get("transport_cost_per_unit", None)
        if isinstance(transport_overrides, dict):
            for mid, cost in transport_overrides.items():
                m = next((mm for mm in markets if mm.id == mid), None)
                if m is not None:
                    m.transport_cost_per_unit = cost

        # ---- Input-material price change percent (per product) -------------
        material_pct = params.get("input_material_price_change_pct", {}) or {}
        for prod_id, pct in material_pct.items():
            p = next((pp for pp in products if pp.id == prod_id), None)
            if p is not None:
                for tier in p.purchase_tiers:
                    tier.unit_price = round(tier.unit_price * (1 + pct), 2)

        # ---- Production-capacity-per-person override (per product) ---------
        pcpp_override = params.get("production_capacity_per_person", {}) or {}
        for prod_id, capacity in pcpp_override.items():
            p = next((pp for pp in products if pp.id == prod_id), None)
            if p is not None:
                p.production_capacity_per_person = capacity

        bulk_buyers = list(event.bulk_buyers)
        tenders = list(event.tenders)
        notable_events = [ne.model_dump() for ne in event.notable_events]

        # ---- Max production dismissals (parameter or notable-event form) ---
        if "max_dismissals_production" in params:
            max_dismissals_production = params["max_dismissals_production"]
        for ne in notable_events:
            if ne.get("type") == "max_dismissals" and "limit" in ne:
                max_dismissals_production = ne["limit"]

        # ---- One-period production-line price offers -----------------------
        for ne in notable_events:
            if ne.get("type") == "production_line_offer":
                type_id = ne.get("type_id")
                price = ne.get("discounted_price")
                if type_id is not None and price is not None:
                    line_price_offers[type_id] = price

    return ResolvedPeriodContext(
        period=period,
        world=world,
        products=products,
        markets=markets,
        wages_by_cost_centre=wages_by_cc,
        bulk_buyers=bulk_buyers,
        tenders=tenders,
        notable_events=notable_events,
        max_dismissals_production=max_dismissals_production,
        line_price_offers=line_price_offers,
        event=event,
    )


def _set_dotted(obj, dotted_path: str, value) -> None:
    """Set `obj.a.b.c = value` from a 'a.b.c' string."""
    parts = dotted_path.split(".")
    cursor = obj
    for p in parts[:-1]:
        cursor = getattr(cursor, p)
    setattr(cursor, parts[-1], value)
