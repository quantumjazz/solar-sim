"""Sales / market-settlement rule module.

Cohort-wide settlement runs three priority channels — tenders, bulk
buyers, then retail — against finished-goods inventory; retail uses the
multinomial attraction model in each open market. Also covers the
post-settlement step that turns sold units into COGS.

See `docs/spec/01-sales.md`.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from sim_engine.context import ResolvedPeriodContext
from sim_engine.decisions import (
    SalesByProductDecision,
    SalesPerMarketDecision,
    TeamDecision,
)
from sim_engine.rules._scratch import _PeriodScratch
from sim_engine.scenario import LoadedScenarioPack
from sim_engine.state import CommittedTender, CompanyState


def settle_market(
    companies: Dict[str, CompanyState],
    decisions: Dict[str, TeamDecision],
    pack: LoadedScenarioPack,
    ctx: ResolvedPeriodContext,
    scratches: Dict[str, _PeriodScratch],
) -> None:
    """Cohort-wide market settlement.

    Finished-goods inventory is allocated across channels in priority order
    (see docs/spec/01-sales.md §3):

      1. Won tenders   — lowest valid bid wins; winner supplies units_required
      2. Bulk buyers   — every accepting team buys up to the per-company cap
      3. Retail        — multinomial attraction model splits the market

    A `committed` ledger tracks how much of each team's inventory the
    priority channels have already consumed, so retail never oversells.
    """

    market_by_id = {m.id: m for m in ctx.markets}

    # Initialise per-company scratch entries.
    for cid in companies:
        scratches[cid].units_sold = {}
        scratches[cid].revenue = {}
        scratches[cid].transport_cost = {}

    # Per-team {product_id -> SalesByProductDecision} lookup, built once so
    # the per-channel resolvers don't each rescan `decisions[cid].sales`.
    sales_lookup: Dict[str, Dict[str, SalesByProductDecision]] = {
        cid: {s.product: s for s in decisions[cid].sales.by_product}
        for cid in companies
    }

    # Only launchable products can be sold (a product may exist for R&D from
    # an earlier period but not yet be sellable).
    active_product_ids = [
        p.id for p in ctx.products if p.first_launch_period <= ctx.period
    ]

    # committed[cid][product_id] = units already sold via tender + bulk.
    committed: Dict[str, Dict[str, int]] = {cid: {} for cid in companies}

    # --- Channel 1a: deferred tenders won in earlier periods --------------
    # Settled before current-period tenders so newly-deferred ones (whose
    # delivery_period > ctx.period) don't get picked up here in the same run.
    _settle_committed_tenders(companies, ctx, scratches, committed)

    # --- Channel 1b: current-period tenders --------------------------------
    for tender in ctx.tenders:
        if tender.product in active_product_ids:
            _resolve_tender(tender, companies, sales_lookup, scratches, committed, ctx)

    # --- Channel 2: bulk buyers (priority 2) -------------------------------
    for bulk in ctx.bulk_buyers:
        if bulk.product in active_product_ids:
            _resolve_bulk(bulk, companies, sales_lookup, scratches, committed)

    # --- Channel 3: retail (priority 3) ------------------------------------
    # Settle market_1 before market_2: the domestic market has delivery
    # priority, so it consumes inventory first (tracked via `committed`).
    for market_id in ("market_1", "market_2"):
        market = market_by_id.get(market_id)
        if market is None or market.open_from_period > ctx.period:
            continue
        for product_id in active_product_ids:
            _settle_retail(
                market, product_id, companies, sales_lookup, ctx, scratches, committed
            )


def _record_sale(
    scratch: _PeriodScratch,
    product_id: str,
    channel: str,
    units: int,
    revenue: float,
    transport: float,
) -> None:
    """Record a sale in one channel into a company's scratch."""
    scratch.units_sold.setdefault(product_id, {})[channel] = units
    scratch.revenue.setdefault(product_id, {})[channel] = revenue
    scratch.transport_cost.setdefault(product_id, {})[channel] = transport
    scratch.total_revenue += revenue


def _available_inventory(
    company: CompanyState, product_id: str, committed: Dict[str, Dict[str, int]]
) -> int:
    """Finished-goods units still available after priority-channel commitments."""
    inv = company.inventories_finished.get(product_id)
    if inv is None:
        return 0
    already = committed[company.id].get(product_id, 0)
    return max(0, int(inv.units) - already)


def _resolve_tender(
    tender,
    companies: Dict[str, CompanyState],
    sales_lookup: Dict[str, Dict[str, SalesByProductDecision]],
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
    ctx: ResolvedPeriodContext,
) -> None:
    """Award a tender to the lowest valid bidder.

    Delivery and revenue book in `tender.delivery_period`. If that is the
    current period, settle immediately (the historical behaviour). If it
    is later, store the obligation on the winner's `committed_tenders`
    ledger and settle in the delivery period via
    `_settle_committed_tenders` (docs/spec/01-sales.md §3.1).
    """
    # Collect valid bids; iterate sorted by company id for deterministic ties.
    bids: List[Tuple[float, str]] = []
    for cid in sorted(companies):
        company = companies[cid]
        if tender.product not in company.products:
            continue
        sd = sales_lookup[cid].get(tender.product)
        if sd is None or sd.tender is None or sd.tender.bid_price <= 0:
            continue
        if (
            tender.max_acceptable_price is not None
            and sd.tender.bid_price > tender.max_acceptable_price
        ):
            continue
        bids.append((sd.tender.bid_price, cid))

    if not bids:
        return

    bids.sort()  # lowest price first; ties already broken by sorted cid
    winning_price, winner = bids[0]

    # Deferred delivery: store the commitment, do not settle now. Inventory
    # is reserved at delivery time, not at bid time.
    if tender.delivery_period > ctx.period:
        companies[winner].committed_tenders.append(
            CommittedTender(
                won_in_period=ctx.period,
                product=tender.product,
                market=tender.market,
                units=tender.units_required,
                bid_price=winning_price,
                delivery_period=tender.delivery_period,
            )
        )
        return

    # Same-period delivery: settle now.
    available = _available_inventory(companies[winner], tender.product, committed)
    units = min(tender.units_required, available)
    committed[winner][tender.product] = (
        committed[winner].get(tender.product, 0) + units
    )
    # Tenders carry no transport cost (see docs/spec/01-sales.md §3).
    _record_sale(
        scratches[winner], tender.product, "tender", units, units * winning_price, 0.0
    )


def _settle_committed_tenders(
    companies: Dict[str, CompanyState],
    ctx: ResolvedPeriodContext,
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
) -> None:
    """Ship and book any committed tenders whose `delivery_period` is now.

    A team that won a tender in period *t* with `delivery_period = t + 1`
    has its inventory tapped here in period *t + 1*, before any current-
    period tender or retail allocation. If inventory falls short of the
    committed units the team ships what it has — the MVP does not model a
    non-delivery penalty (a future refinement; see 01-sales.md §3.1).
    """
    for cid in sorted(companies):
        company = companies[cid]
        if not company.committed_tenders:
            continue
        remaining: List[CommittedTender] = []
        for tender in company.committed_tenders:
            if tender.delivery_period != ctx.period:
                remaining.append(tender)
                continue
            available = _available_inventory(company, tender.product, committed)
            units = min(tender.units, available)
            committed[cid][tender.product] = (
                committed[cid].get(tender.product, 0) + units
            )
            _record_sale(
                scratches[cid],
                tender.product,
                "tender",
                units,
                units * tender.bid_price,
                0.0,
            )
        company.committed_tenders = remaining


def _resolve_bulk(
    bulk,
    companies: Dict[str, CompanyState],
    sales_lookup: Dict[str, Dict[str, SalesByProductDecision]],
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
) -> None:
    """Every team that accepts the bulk offer buys up to the per-company cap."""
    for cid in sorted(companies):
        company = companies[cid]
        if bulk.product not in company.products:
            continue
        sd = sales_lookup[cid].get(bulk.product)
        if sd is None or sd.bulk_buyer is None or not sd.bulk_buyer.accept_offer:
            continue
        available = _available_inventory(company, bulk.product, committed)
        units = min(sd.bulk_buyer.bid_units, bulk.max_units_per_company, available)
        committed[cid][bulk.product] = committed[cid].get(bulk.product, 0) + units
        # Bulk sales carry no transport cost.
        _record_sale(
            scratches[cid], bulk.product, "bulk", units, units * bulk.price, 0.0
        )


def _settle_retail(
    market,
    product_id: str,
    companies: Dict[str, CompanyState],
    sales_lookup: Dict[str, Dict[str, SalesByProductDecision]],
    ctx: ResolvedPeriodContext,
    scratches: Dict[str, _PeriodScratch],
    committed: Dict[str, Dict[str, int]],
) -> None:
    """Multinomial attraction model for one retail market and product.

    Works for both the domestic market (`market_1`, base currency) and the
    export market (`market_2`, foreign currency). For an export market, the
    team's price is quoted in the foreign currency; revenue is converted to
    base currency via the period's FX rate before it enters accounting.
    """
    market_potential = market.market_potential_period_0.get(product_id, 0)
    if market_potential <= 0:
        return

    # FX: units of market currency per 1 base unit (1.0 for the home market).
    fx = market.fx_per_base_at_start or 1.0

    contestants: List[Tuple[str, float, "SalesPerMarketDecision"]] = []
    for cid, company in companies.items():
        if product_id not in company.products:
            continue
        sales_dec = sales_lookup[cid].get(product_id)
        if sales_dec is None:
            continue
        m_dec = sales_dec.market_1 if market.id == "market_1" else sales_dec.market_2
        if m_dec is None:
            continue
        a = _company_attractiveness(company, product_id, m_dec, market, fx)
        contestants.append((cid, a, m_dec))

    if not contestants:
        return
    total_attractiveness = sum(a for _, a, _ in contestants)
    if total_attractiveness <= 0:
        return

    team_demand: Dict[str, int] = {}
    team_share: Dict[str, float] = {}
    for cid, a, _ in contestants:
        share = a / total_attractiveness
        team_share[cid] = share
        team_demand[cid] = int(round(market_potential * share))

    # Sell up to inventory still available after the priority channels.
    team_sold: Dict[str, int] = {}
    team_unmet: Dict[str, int] = {}
    for cid, _, _ in contestants:
        available = _available_inventory(companies[cid], product_id, committed)
        sold = min(team_demand[cid], available)
        team_sold[cid] = sold
        team_unmet[cid] = team_demand[cid] - sold

    # Spillover: redistribute a fraction of unmet demand to teams that met
    # theirs, once, in proportion to share and capped by remaining supply.
    spillover_fraction = market.spillover_fraction
    total_unmet = sum(team_unmet.values())
    if total_unmet > 0 and spillover_fraction > 0:
        available_to_spillover = int(round(total_unmet * spillover_fraction))
        remaining = available_to_spillover
        recipients = [
            (cid, team_share[cid])
            for cid, _, _ in contestants
            if team_unmet[cid] == 0
        ]
        total_recipient_share = sum(s for _, s in recipients)
        if total_recipient_share > 0:
            for cid, s in recipients:
                extra_demand = int(
                    round(available_to_spillover * (s / total_recipient_share))
                )
                available = _available_inventory(
                    companies[cid], product_id, committed
                )
                extra_sold = min(
                    extra_demand,
                    max(0, available - team_sold[cid]),
                    remaining,
                )
                team_sold[cid] += extra_sold
                remaining -= extra_sold
                if remaining <= 0:
                    break

    for cid, _, m_dec in contestants:
        sold = team_sold[cid]
        # Revenue is recorded in base currency: an export-market price quoted
        # in foreign currency is divided by the FX rate.
        revenue_base = sold * m_dec.price / fx
        # Mark these units committed so a later market sees reduced inventory.
        committed[cid][product_id] = committed[cid].get(product_id, 0) + sold
        _record_sale(
            scratches[cid],
            product_id,
            market.id,
            sold,
            revenue_base,
            sold * market.transport_cost_per_unit,
        )


def _company_attractiveness(
    company: CompanyState,
    product_id: str,
    m_dec,
    market,
    fx: float = 1.0,
) -> float:
    """Multinomial attraction score for one company on one product/market.

    Implements `docs/spec/01-sales.md` §2.1, scored against the cohort.
    Returns a positive float; the caller normalises by the sum across teams.

    `fx` is the market's currency rate (units of market currency per base
    unit). The team's price is converted to base currency before it is
    compared with the base-currency anchor, so the home and export markets
    are scored on the same scale.
    """

    coeffs = market.coefficients
    product_state = company.products[product_id]

    # We score factors against neutral reference values: price uses the
    # scenario-set anchor on the market's coefficients, advertising/sf use
    # the saturation references, indices use 100.
    REF_INDEX = 100.0

    price_in_base = m_dec.price / fx if fx else m_dec.price
    price_factor = (
        (coeffs.price_anchor / price_in_base) ** coeffs.beta_price
        if price_in_base > 0
        else 1.0
    )
    ads_eff = (
        1 - math.exp(-m_dec.advertising / coeffs.ads_ref)
        if coeffs.ads_ref > 0
        else 0.0
    )
    ad_factor = ads_eff ** coeffs.beta_ad if ads_eff > 0 else 1e-6
    sf_eff = (
        1 - math.exp(-m_dec.sales_force / coeffs.sf_ref)
        if coeffs.sf_ref > 0
        else 0.0
    )
    sf_factor = sf_eff ** coeffs.beta_sf if sf_eff > 0 else 1e-6

    product_score_raw = (
        coeffs.product_weights.get("efficiency", 0.5)
        * (product_state.efficiency_index / REF_INDEX)
        + coeffs.product_weights.get("sustainability", 0.3)
        * (product_state.sustainability_index / REF_INDEX)
        + coeffs.product_weights.get("value_analysis", 0.2)
        * (product_state.value_analysis_index / REF_INDEX)
    )
    product_score = product_score_raw ** coeffs.beta_prod if product_score_raw > 0 else 1e-6

    image_factor = (company.image_index / 100.0) ** coeffs.beta_img
    sat_factor = (company.satisfaction_index / 100.0) ** coeffs.beta_sat

    return (
        price_factor
        * ad_factor
        * sf_factor
        * product_score
        * image_factor
        * sat_factor
    )


def apply_sales_allocation_and_finished_inventory(
    company: CompanyState,
    decision: TeamDecision,
    pack: LoadedScenarioPack,
    scratch: _PeriodScratch,
) -> None:
    """Remove sold units from finished-goods inventory and compute COGS."""

    for product_id, by_market in scratch.units_sold.items():
        total_sold = sum(by_market.values())
        if total_sold == 0:
            continue
        inv = company.inventories_finished[product_id]
        opening_units = inv.units
        opening_value = opening_units * inv.unit_value
        # Sell at the current weighted-average value
        cogs_value = total_sold * inv.unit_value
        new_units = opening_units - total_sold
        if new_units < 0:
            # Should not happen given the supply cap in apply_sales
            new_units = 0
        new_value = opening_value - cogs_value
        # unit_value stays constant under moving average on a sale
        inv.units = new_units
        # inv.unit_value unchanged

        scratch.total_cogs += cogs_value
