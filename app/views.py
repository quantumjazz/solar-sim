"""Streamlit report-rendering helpers for the instructor console."""

from __future__ import annotations

from typing import List, Tuple

import streamlit as st

from sim_engine.reports import IndustryReport, ReportBundle


def _eur(value: float) -> str:
    """Format a euro amount compactly (millions for large values)."""
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:,.1f}k"
    return f"€{value:,.0f}"


def show_executive_summary(bundle: ReportBundle) -> None:
    es = bundle.executive_summary
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue", _eur(es.revenue))
    c2.metric("Operating income", _eur(es.operating_income))
    c3.metric("Net income", _eur(es.net_income))
    c4.metric("Cash", _eur(es.cash_balance))
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Return on equity", f"{es.return_on_equity:.1%}")
    c6.metric("Return on sales", f"{es.return_on_sales:.1%}")
    c7.metric("Units sold", f"{bundle.market.total_units_sold:,}")
    c8.metric("Rating index", f"{es.rating_index:.0f}")


def show_market(bundle: ReportBundle) -> None:
    rows = [
        {
            "Product": line.product_id,
            "Channel": line.market_id,
            "Units sold": f"{line.units_sold:,}",
            "Revenue": _eur(line.revenue),
            "Price/unit": _eur(line.price_per_unit),
        }
        for line in bundle.market.by_market
    ]
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.caption("No sales recorded this period.")


def _statement_table(rows: List[Tuple[str, float]]) -> None:
    st.dataframe(
        [{"Item": label, "Amount": _eur(value)} for label, value in rows],
        width="stretch",
        hide_index=True,
    )


def show_profit_and_loss(bundle: ReportBundle) -> None:
    pl = bundle.profit_and_loss
    _statement_table(
        [
            ("Sales revenue", pl.sales_revenue),
            ("± Change in finished inventory", pl.change_in_finished_inventory),
            ("+ Other operating income", pl.other_operating_income),
            ("− Material expenses", -pl.material_expenses),
            ("− Wages & salaries", -pl.wages_and_salaries),
            ("− Non-salary staff costs", -pl.non_salary_staff_costs),
            ("− Pension reserve", -pl.pension_reserve_contribution),
            ("− Hiring / dismissal costs", -pl.hiring_and_dismissal_costs),
            ("− Depreciation", -pl.depreciation),
            ("− Other expenses", -pl.other_expenses),
            ("= Operating income", pl.operating_income),
            ("+ Investment income", pl.investment_income),
            ("− Interest (ST+LT+overdraft)", -(
                pl.interest_short_term
                + pl.interest_long_term
                + pl.interest_overdraft
            )),
            ("± Extraordinary items", pl.extraordinary_income - pl.extraordinary_expense),
            ("= Earnings before tax", pl.earnings_before_tax_total),
            ("− Income tax", -pl.income_tax),
            ("= Net income", pl.net_income),
        ]
    )


def show_balance_sheet(bundle: ReportBundle) -> None:
    bs = bundle.balance_sheet
    left, right = st.columns(2)
    with left:
        st.caption("Assets")
        _statement_table(
            [
                ("Land & buildings", bs.land_and_buildings),
                ("Production lines (NBV)", bs.production_lines_nbv),
                ("Environmental tech (NBV)", bs.environmental_tech_nbv),
                ("Input materials", bs.input_material_value),
                ("Finished goods", bs.finished_goods_value),
                ("Trade receivables", bs.trade_receivables),
                ("Securities", bs.securities),
                ("Cash", bs.cash),
                ("TOTAL ASSETS", bs.total_assets),
            ]
        )
    with right:
        st.caption("Liabilities & equity")
        _statement_table(
            [
                ("Subscribed capital", bs.subscribed_capital),
                ("Capital reserves", bs.capital_reserves),
                ("Retained earnings", bs.retained_earnings),
                ("Net income for period", bs.net_income_for_period),
                ("Pension reserve", bs.pension_reserve),
                ("Long-term loan", bs.long_term_loan),
                ("Short-term loan", bs.short_term_loan),
                ("Overdraft loan", bs.overdraft_loan),
                ("TOTAL L + E", bs.total_liabilities_and_equity),
            ]
        )
    if bs.articulates:
        st.success("Balance sheet articulates (assets = liabilities + equity).")
    else:
        st.error(
            f"Balance sheet does NOT articulate — "
            f"assets {_eur(bs.total_assets)} vs L+E "
            f"{_eur(bs.total_liabilities_and_equity)}."
        )


def show_cash_flow(bundle: ReportBundle) -> None:
    cf = bundle.cash_flow
    _statement_table(
        [
            ("Net income", cf.net_income),
            ("+ Depreciation", cf.depreciation_added_back),
            ("+ Pension reserve change", cf.pension_reserve_change),
            ("− Inventory change", -cf.inventory_change),
            ("− Receivables change", -cf.receivables_change),
            ("= Operating cash flow", cf.operating_cash_flow),
            ("= Investing cash flow", cf.investing_cash_flow),
            ("= Financing cash flow", cf.financing_cash_flow),
            ("Cash at start", cf.cash_start),
            ("Cash at end", cf.cash_end),
        ]
    )
    if not cf.articulates:
        st.error("Cash-flow statement does not reconcile.")


def show_report_bundle(bundle: ReportBundle) -> None:
    """Render the full per-team report bundle in tabs."""
    show_executive_summary(bundle)
    tabs = st.tabs(
        ["Market", "Profit & Loss", "Balance Sheet", "Cash Flow"]
    )
    with tabs[0]:
        show_market(bundle)
    with tabs[1]:
        show_profit_and_loss(bundle)
    with tabs[2]:
        show_balance_sheet(bundle)
    with tabs[3]:
        show_cash_flow(bundle)


def show_industry_report(industry: IndustryReport) -> None:
    """Render the cohort-public competitor view."""
    st.caption(
        f"Market totals — {industry.market_total_units:,} units, "
        f"{_eur(industry.market_total_revenue)} revenue"
    )
    rows = []
    for c in sorted(industry.companies, key=lambda x: -x.net_income):
        rows.append(
            {
                "Company": c.company_name or c.company_id,
                "Revenue": _eur(c.revenue),
                "Operating income": _eur(c.operating_income),
                "Net income": _eur(c.net_income),
                "Equity": _eur(c.equity),
                "Total debt": _eur(c.total_debt),
                "Cash": _eur(c.cash),
                "Units sold": f"{c.units_sold:,}",
                "Market share": f"{c.market_share_pct:.1f}%",
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)
