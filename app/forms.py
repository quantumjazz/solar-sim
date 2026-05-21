"""Streamlit decision-entry forms for the instructor console.

`default_decision` builds a sensible starting decision used to pre-fill the
form. `team_decision_form` renders the inputs for one team and returns a
fully constructed `TeamDecision`.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

from sim_engine.decisions import (
    BulkBuyerAcceptance,
    FinanceDecision,
    HRDecision,
    LineInvestDecision,
    LineMaintenanceDecision,
    LineRationalisationDecision,
    PlannedKPIs,
    ProductionByProductDecision,
    ProductionDecision,
    ProductionLinesDecision,
    PurchasingByProductDecision,
    PurchasingDecision,
    RnDByProductDecision,
    RnDDecision,
    SalesByProductDecision,
    SalesDecision,
    SalesPerMarketDecision,
    TeamDecision,
    TenderBid,
)


def default_decision(
    team_id: str, period: int, product_ids: List[str]
) -> TeamDecision:
    """A sensible starting decision, used to pre-fill the form for period 1."""
    return TeamDecision(
        team_id=team_id,
        period=period,
        sales=SalesDecision(
            by_product=[
                SalesByProductDecision(
                    product=pid,
                    market_1=SalesPerMarketDecision(
                        price=2_800.0, advertising=6_000_000, sales_force=100
                    ),
                )
                for pid in product_ids
            ],
            corporate_identity=2_000_000,
            market_research_report=True,
        ),
        rnd=RnDDecision(
            by_product=[
                RnDByProductDecision(
                    product=pid,
                    researchers=34,
                    sustainability_spend=2_000_000,
                    value_analysis_spend=1_000_000,
                )
                for pid in product_ids
            ]
        ),
        purchasing=PurchasingDecision(
            by_product=[
                PurchasingByProductDecision(product=pid, order_units=42_000)
                for pid in product_ids
            ]
        ),
        production=ProductionDecision(
            by_product=[
                ProductionByProductDecision(product=pid, target_volume=44_000)
                for pid in product_ids
            ],
        ),
        hr=HRDecision(
            production_workforce_change=0,
            training_per_employee=800,
            process_optimisation_spend=1_000_000,
            non_salary_pct=0.40,
            pension_reserve_pct=0.05,
        ),
        finance=FinanceDecision(short_term_loan=20_000_000),
    )


def team_decision_form(
    team_id: str,
    period: int,
    product_ids: List[str],
    catalog_types: List[str],
    defaults: TeamDecision,
    market_2_open: bool,
    bulk_offer_products: List[str],
    tender_products: List[str],
) -> TeamDecision:
    """Render the decision inputs for one team; return a TeamDecision.

    `defaults` pre-fills every field (the team's previous decision, or a
    `default_decision` for period 1). `bulk_offer_products` / `tender_products`
    list the products with an active offer this period — the bulk / tender
    inputs are only shown for those.
    """

    def k(name: str) -> str:
        return f"{team_id}_p{period}_{name}"

    sales_def = {s.product: s for s in defaults.sales.by_product}
    rnd_def = {r.product: r for r in defaults.rnd.by_product}
    pur_def = {p.product: p for p in defaults.purchasing.by_product}
    prod_def = {p.product: p for p in defaults.production.by_product}

    sales_by_product: List[SalesByProductDecision] = []
    rnd_by_product: List[RnDByProductDecision] = []
    pur_by_product: List[PurchasingByProductDecision] = []
    prod_by_product: List[ProductionByProductDecision] = []

    for pid in product_ids:
        st.markdown(f"##### Product — {pid}")
        sd = sales_def.get(pid)
        rd = rnd_def.get(pid)
        pd = pur_def.get(pid)
        ppd = prod_def.get(pid)

        # --- Sales: market 1 ---
        c1, c2, c3 = st.columns(3)
        price = c1.number_input(
            "Price M1 (€)", min_value=0.0, step=50.0,
            value=float(sd.market_1.price) if sd and sd.market_1 else 2_800.0,
            key=k(f"{pid}_price1"),
        )
        adv = c2.number_input(
            "Advertising M1 (€)", min_value=0.0, step=500_000.0,
            value=float(sd.market_1.advertising) if sd and sd.market_1 else 6_000_000.0,
            key=k(f"{pid}_adv1"),
        )
        sf = c3.number_input(
            "Sales force M1", min_value=0, step=10,
            value=int(sd.market_1.sales_force) if sd and sd.market_1 else 100,
            key=k(f"{pid}_sf1"),
        )
        market_1 = SalesPerMarketDecision(price=price, advertising=adv, sales_force=sf)

        # --- Sales: market 2 (only if open) ---
        market_2: Optional[SalesPerMarketDecision] = None
        if market_2_open:
            d1, d2, d3 = st.columns(3)
            existing_m2 = sd.market_2 if sd else None
            price2 = d1.number_input(
                "Price M2 (FCU)", min_value=0.0, step=50.0,
                value=float(existing_m2.price) if existing_m2 else 3_000.0,
                key=k(f"{pid}_price2"),
            )
            adv2 = d2.number_input(
                "Advertising M2 (€)", min_value=0.0, step=250_000.0,
                value=float(existing_m2.advertising) if existing_m2 else 3_000_000.0,
                key=k(f"{pid}_adv2"),
            )
            sf2 = d3.number_input(
                "Sales force M2", min_value=0, step=10,
                value=int(existing_m2.sales_force) if existing_m2 else 40,
                key=k(f"{pid}_sf2"),
            )
            if price2 > 0:
                market_2 = SalesPerMarketDecision(
                    price=price2, advertising=adv2, sales_force=sf2
                )

        # --- Bulk buyer (only if there is an offer) ---
        bulk: Optional[BulkBuyerAcceptance] = None
        if pid in bulk_offer_products:
            b1, b2 = st.columns(2)
            accept = b1.checkbox(
                "Accept bulk-buyer offer", key=k(f"{pid}_bulk_accept")
            )
            bulk_units = b2.number_input(
                "Bulk units", min_value=0, step=500, value=5_000,
                key=k(f"{pid}_bulk_units"),
            )
            bulk = BulkBuyerAcceptance(accept_offer=accept, bid_units=bulk_units)

        # --- Tender bid (only if there is a tender) ---
        tender: Optional[TenderBid] = None
        if pid in tender_products:
            t1, t2 = st.columns(2)
            bid_price = t1.number_input(
                "Tender bid price (€) — 0 to skip", min_value=0.0, step=50.0,
                value=0.0, key=k(f"{pid}_tender_price"),
            )
            bid_units = t2.number_input(
                "Tender bid units", min_value=0, step=500, value=0,
                key=k(f"{pid}_tender_units"),
            )
            if bid_price > 0:
                tender = TenderBid(bid_price=bid_price, bid_units=bid_units)

        sales_by_product.append(
            SalesByProductDecision(
                product=pid,
                market_1=market_1,
                market_2=market_2,
                bulk_buyer=bulk,
                tender=tender,
            )
        )

        # --- R&D ---
        e1, e2, e3 = st.columns(3)
        researchers = e1.number_input(
            "R&D headcount", min_value=0, step=5,
            value=int(rd.researchers) if rd else 34, key=k(f"{pid}_rnd_staff"),
        )
        sus = e2.number_input(
            "Sustainability spend (€)", min_value=0.0, step=500_000.0,
            value=float(rd.sustainability_spend) if rd else 2_000_000.0,
            key=k(f"{pid}_rnd_sus"),
        )
        val = e3.number_input(
            "Value-analysis spend (€)", min_value=0.0, step=250_000.0,
            value=float(rd.value_analysis_spend) if rd else 1_000_000.0,
            key=k(f"{pid}_rnd_val"),
        )
        rnd_by_product.append(
            RnDByProductDecision(
                product=pid, researchers=researchers,
                sustainability_spend=sus, value_analysis_spend=val,
            )
        )

        # --- Purchasing & production ---
        f1, f2 = st.columns(2)
        order_units = f1.number_input(
            "Input material to order (units)", min_value=0, step=1_000,
            value=int(pd.order_units) if pd else 42_000, key=k(f"{pid}_order"),
        )
        target = f2.number_input(
            "Production target (units)", min_value=0, step=1_000,
            value=int(ppd.target_volume) if ppd else 44_000, key=k(f"{pid}_target"),
        )
        pur_by_product.append(
            PurchasingByProductDecision(product=pid, order_units=order_units)
        )
        prod_by_product.append(
            ProductionByProductDecision(product=pid, target_volume=target)
        )

    # --- Company-wide sales spend ---
    st.markdown("##### Marketing & company decisions")
    g1, g2 = st.columns(2)
    corp_id = g1.number_input(
        "Corporate identity spend (€)", min_value=0.0, step=500_000.0,
        value=float(defaults.sales.corporate_identity), key=k("corp_id"),
    )
    mr = g2.checkbox(
        "Buy market-research report",
        value=defaults.sales.market_research_report, key=k("mr"),
    )

    # --- Production lines ---
    st.markdown("##### Production lines")
    invest_counts: Dict[str, int] = {}
    maintenance: Dict[str, float] = {}
    inv_cols = st.columns(len(catalog_types))
    for i, type_id in enumerate(catalog_types):
        inv_cols[i].caption(type_id)
        invest_counts[type_id] = inv_cols[i].number_input(
            "buy", min_value=0, max_value=9, step=1, value=0,
            key=k(f"invest_{type_id}"),
        )
        maintenance[type_id] = inv_cols[i].number_input(
            "maint €/line", min_value=0.0, step=100_000.0, value=1_000_000.0,
            key=k(f"maint_{type_id}"),
        )
    env_capex = st.number_input(
        "Environmental capex (€)", min_value=0.0, step=500_000.0, value=0.0,
        key=k("env_capex"),
    )

    # --- HR ---
    st.markdown("##### Human resources")
    h1, h2, h3 = st.columns(3)
    workforce_change = h1.number_input(
        "Production workforce change (+hire / −dismiss)", step=10,
        value=int(defaults.hr.production_workforce_change), key=k("wf"),
    )
    training = h2.number_input(
        "Training per employee (€)", min_value=0.0, step=200.0,
        value=float(defaults.hr.training_per_employee), key=k("train"),
    )
    process_opt = h3.number_input(
        "Process-optimisation spend (€)", min_value=0.0, step=500_000.0,
        value=float(defaults.hr.process_optimisation_spend), key=k("proc"),
    )
    h4, h5 = st.columns(2)
    non_salary = h4.number_input(
        "Non-salary staff cost (%)", min_value=0.0, max_value=100.0, step=1.0,
        value=float(defaults.hr.non_salary_pct * 100), key=k("nsc"),
    ) / 100.0
    pension = h5.number_input(
        "Pension reserve (%)", min_value=0.0, max_value=50.0, step=1.0,
        value=float(defaults.hr.pension_reserve_pct * 100), key=k("pension"),
    ) / 100.0

    # --- Finance ---
    st.markdown("##### Finance")
    i1, i2, i3, i4 = st.columns(4)
    st_loan = i1.number_input(
        "Short-term loan (€)", min_value=0.0, step=1_000_000.0,
        value=float(defaults.finance.short_term_loan), key=k("stloan"),
    )
    lt_loan = i2.number_input(
        "Long-term loan (€)", min_value=0.0, step=1_000_000.0,
        value=float(defaults.finance.long_term_loan), key=k("ltloan"),
    )
    securities = i3.number_input(
        "Securities purchase (€)", min_value=0.0, step=1_000_000.0,
        value=float(defaults.finance.securities_purchase), key=k("sec"),
    )
    dividend = i4.number_input(
        "Dividend (€)", min_value=0.0, step=500_000.0,
        value=float(defaults.finance.dividend), key=k("div"),
    )

    return TeamDecision(
        team_id=team_id,
        period=period,
        sales=SalesDecision(
            by_product=sales_by_product,
            corporate_identity=corp_id,
            market_research_report=mr,
        ),
        rnd=RnDDecision(by_product=rnd_by_product),
        purchasing=PurchasingDecision(by_product=pur_by_product),
        production=ProductionDecision(
            by_product=prod_by_product,
            lines=ProductionLinesDecision(
                invest=LineInvestDecision(counts=invest_counts),
                maintenance=LineMaintenanceDecision(spend_per_line=maintenance),
                rationalisation=LineRationalisationDecision(),
            ),
            environmental_capex=env_capex,
        ),
        hr=HRDecision(
            production_workforce_change=int(workforce_change),
            training_per_employee=training,
            process_optimisation_spend=process_opt,
            non_salary_pct=non_salary,
            pension_reserve_pct=pension,
        ),
        finance=FinanceDecision(
            short_term_loan=st_loan,
            long_term_loan=lt_loan,
            securities_purchase=securities,
            dividend=dividend,
            planned_kpis=PlannedKPIs(),
        ),
    )
