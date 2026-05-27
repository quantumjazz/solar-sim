"""Board-meeting document renderer (pedagogy layer).

A pure module: takes a `TeamBoardData` bundle and returns a Markdown
string. The service layer (`service.py`) is responsible for fetching
state, reports, planning quality, strategy map, and peer aggregates from
SQLite and applying the viewer-role visibility rules before calling
`render_document`. See `docs/spec/09-pedagogy.md` §4.

No database, no Streamlit, no third-party dependency. Markdown is chosen
for portability — it renders natively in Streamlit, downloads as a
plain `.md`, and converts to PDF / DOCX via pandoc downstream.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from sim_engine.reports import IndustryReport, ReportBundle
from pedagogy import (
    AggregatedRating,
    PeerRating,
    StrategyMap,
    TeamPlanningQuality,
)


# ---------------------------------------------------------------------------
# Data bundle
# ---------------------------------------------------------------------------


class PeerRatingWithNames(BaseModel):
    """A peer rating enriched with the rater's and ratee's display names."""

    model_config = ConfigDict(extra="forbid")

    rater_name: str
    ratee_name: str
    rating: PeerRating


class TeamBoardData(BaseModel):
    """Everything `render_document` needs to render one team's deliverable.

    The service layer composes one of these per export, filtering the
    peer-assessment fields according to the viewer's role.
    """

    model_config = ConfigDict(extra="forbid")

    cohort_name: str
    cohort_status: str
    scenario_id: str
    team_name: str
    team_company_id: str
    member_names: List[str] = []
    final_industry_report: Optional[IndustryReport] = None
    period_bundles: List[ReportBundle] = []
    planning_quality: Optional[TeamPlanningQuality] = None
    strategy_map: StrategyMap
    # Peer assessment — viewer-role-gated.
    own_peer_aggregate: Optional[AggregatedRating] = None  # student-only field
    team_peer_aggregates: List[AggregatedRating] = []      # instructor-only
    detailed_peer_ratings: List[PeerRatingWithNames] = []  # instructor-only
    viewer_role: str   # "student" or "instructor"
    generated_at: str  # ISO-8601 date


# ---------------------------------------------------------------------------
# Top-level renderer
# ---------------------------------------------------------------------------


def render_document(data: TeamBoardData) -> str:
    """Render the full board-meeting document for one team as Markdown."""
    parts = [
        _render_cover(data),
        _render_cohort_standing(data),
        _render_periods(data),
        _render_planning_quality(data),
        _render_strategy_map(data),
        _render_peer_assessment(data),
    ]
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_cover(data: TeamBoardData) -> str:
    members = ", ".join(data.member_names) if data.member_names else "(none listed)"
    return (
        f"# Board-meeting document — {data.team_name}\n\n"
        f"**Cohort:** {data.cohort_name}  \n"
        f"**Scenario:** `{data.scenario_id}`  \n"
        f"**Team members:** {members}  \n"
        f"**Cohort status:** {data.cohort_status}  \n"
        f"**Generated:** {data.generated_at}"
    )


def _render_cohort_standing(data: TeamBoardData) -> str:
    if data.final_industry_report is None:
        return "## Cohort standing\n\n_No periods have been run yet._"
    ir = data.final_industry_report
    rows = []
    for line in sorted(ir.companies, key=lambda c: -c.net_income):
        marker = " ←" if line.company_id == data.team_company_id else ""
        rows.append(
            [
                f"{line.company_name}{marker}",
                _eur(line.revenue),
                _eur(line.operating_income),
                _eur(line.net_income),
                _eur(line.equity),
                f"{line.market_share_pct:.1f}%",
            ]
        )
    return (
        f"## Cohort standing — period {ir.period}\n\n"
        + _md_table(
            ["Company", "Revenue", "Operating income", "Net income",
             "Equity", "Market share"],
            rows,
        )
    )


def _render_periods(data: TeamBoardData) -> str:
    if not data.period_bundles:
        return ""
    sections = ["## Period-by-period reports"]
    for bundle in data.period_bundles:
        sections.append(_render_period(bundle))
    return "\n\n".join(sections)


def _render_period(b: ReportBundle) -> str:
    es = b.executive_summary
    market = b.market
    pl = b.profit_and_loss
    bs = b.balance_sheet
    cf = b.cash_flow

    parts = [f"### Period {b.period}"]
    parts.append(
        f"- **Revenue:** {_eur(es.revenue)}  \n"
        f"- **Operating income:** {_eur(es.operating_income)}  \n"
        f"- **Net income:** {_eur(es.net_income)}  \n"
        f"- **Return on equity:** {_pct(es.return_on_equity)}  \n"
        f"- **Cash:** {_eur(es.cash_balance)}  \n"
        f"- **Units sold:** {market.total_units_sold:,}"
    )

    if market.by_market:
        parts.append("**Market lines**")
        parts.append(
            _md_table(
                ["Product", "Channel", "Units", "Revenue", "Price/unit"],
                [
                    [m.product_id, m.market_id, f"{m.units_sold:,}",
                     _eur(m.revenue), _eur(m.price_per_unit)]
                    for m in market.by_market
                ],
            )
        )

    personnel = (
        pl.wages_and_salaries
        + pl.non_salary_staff_costs
        + pl.pension_reserve_contribution
        + pl.hiring_and_dismissal_costs
    )
    parts.append("**Profit & loss (summary)**")
    parts.append(
        _md_table(
            ["Item", "Amount"],
            [
                ["Sales revenue", _eur(pl.sales_revenue)],
                ["± Change in finished inventory",
                 _eur(pl.change_in_finished_inventory)],
                ["− Material expenses", _eur(-pl.material_expenses)],
                ["− Personnel (wages, non-salary, pension, hires/fires)",
                 _eur(-personnel)],
                ["− Depreciation", _eur(-pl.depreciation)],
                ["− Other expenses", _eur(-pl.other_expenses)],
                ["= Operating income", _eur(pl.operating_income)],
                ["− Interest (ST + LT + overdraft)",
                 _eur(-(pl.interest_short_term + pl.interest_long_term
                        + pl.interest_overdraft))],
                ["± Extraordinary items",
                 _eur(pl.extraordinary_income - pl.extraordinary_expense)],
                ["− Income tax", _eur(-pl.income_tax)],
                ["= Net income", _eur(pl.net_income)],
            ],
        )
    )

    bs_check = "✓ balances" if bs.articulates else "✗ DOES NOT BALANCE"
    cf_check = "✓ reconciles" if cf.articulates else "✗ DOES NOT RECONCILE"
    net_change = (
        cf.operating_cash_flow + cf.investing_cash_flow + cf.financing_cash_flow
    )
    parts.append(
        f"**Balance sheet** — total assets {_eur(bs.total_assets)} "
        f"vs total L+E {_eur(bs.total_liabilities_and_equity)} "
        f"({bs_check})  \n"
        f"**Cash flow** — opening {_eur(cf.cash_start)} → closing "
        f"{_eur(cf.cash_end)}; net change {_eur(net_change)} "
        f"({cf_check})"
    )
    return "\n\n".join(parts)


def _render_planning_quality(data: TeamBoardData) -> str:
    tpq = data.planning_quality
    if tpq is None or not tpq.periods:
        return "## Planning quality\n\n_No periods scored yet._"

    parts = ["## Planning quality"]
    if tpq.headline_score is not None:
        parts.append(
            f"**Headline (real periods):** {_pct(tpq.headline_score)} "
            f"across {tpq.real_period_count} real period(s)."
        )
    else:
        parts.append(
            "_The headline score appears once the first real period has "
            f"run; {len(tpq.periods)} trial period(s) scored below._"
        )
    rows = []
    for p in tpq.periods:
        kpi = {k.name: k for k in p.kpis}
        rev = kpi["Revenue"]
        roe = kpi["Return on equity"]
        ocf = kpi["Operating cash flow"]
        rows.append(
            [
                str(p.period),
                "Real" if p.is_real_period else "Trial",
                _pct(p.period_score),
                f"{_eur(rev.planned)} → {_eur(rev.actual)} "
                f"({_pct(rev.score)})",
                f"{_pct(roe.planned)} → {_pct(roe.actual)} "
                f"({_pct(roe.score)})",
                f"{_eur(ocf.planned)} → {_eur(ocf.actual)} "
                f"({_pct(ocf.score)})",
            ]
        )
    parts.append(
        _md_table(
            ["Period", "Type", "Score", "Revenue (planned → actual)",
             "ROE (planned → actual)",
             "Operating cash flow (planned → actual)"],
            rows,
        )
    )
    return "\n\n".join(parts)


def _render_strategy_map(data: TeamBoardData) -> str:
    sm = data.strategy_map
    if sm.is_empty:
        return "## Strategy map\n\n_This team has not authored a strategy map._"
    parts = ["## Strategy map"]
    for label, text in (
        ("Financial", sm.financial),
        ("Customer", sm.customer),
        ("Internal process", sm.internal_process),
        ("Learning & growth", sm.learning_growth),
    ):
        parts.append(f"### {label}")
        parts.append(text.strip() if text.strip() else "_(empty)_")
    if sm.updated_at:
        parts.append(f"_Last updated: {sm.updated_at}_")
    return "\n\n".join(parts)


def _render_peer_assessment(data: TeamBoardData) -> str:
    if data.viewer_role == "student":
        return _render_peer_student(data)
    return _render_peer_instructor(data)


def _render_peer_student(data: TeamBoardData) -> str:
    parts = ["## Peer assessment"]
    agg = data.own_peer_aggregate
    if agg is None:
        parts.append(
            "_Peer-assessment results are released once the cohort is "
            "finished._"
        )
        return "\n\n".join(parts)
    if agg.n_raters == 0:
        parts.append("_No peer ratings were recorded for you._")
        return "\n\n".join(parts)
    parts.append(f"Aggregated across **{agg.n_raters}** rater(s):")
    parts.append(
        _md_table(
            ["Dimension", "Mean (1–5)"],
            [
                ["Contribution", _fmt_mean(agg.contribution_mean)],
                ["Collaboration", _fmt_mean(agg.collaboration_mean)],
                ["Reliability", _fmt_mean(agg.reliability_mean)],
                ["Communication", _fmt_mean(agg.communication_mean)],
                [
                    "Overall",
                    f"{agg.overall_mean:.2f}"
                    if agg.overall_mean is not None
                    else "—",
                ],
            ],
        )
    )
    return "\n\n".join(parts)


def _render_peer_instructor(data: TeamBoardData) -> str:
    parts = ["## Peer assessment"]
    if not data.team_peer_aggregates and not data.detailed_peer_ratings:
        parts.append("_No peer ratings recorded for this team._")
        return "\n\n".join(parts)

    name_by_id = {}
    for r in data.detailed_peer_ratings:
        name_by_id[r.rating.rater_id] = r.rater_name
        name_by_id[r.rating.ratee_id] = r.ratee_name

    parts.append("### Per-member aggregates")
    parts.append(
        _md_table(
            ["Ratee", "n raters", "Contribution", "Collaboration",
             "Reliability", "Communication", "Overall"],
            [
                [
                    name_by_id.get(a.ratee_id, f"user #{a.ratee_id}"),
                    str(a.n_raters),
                    _fmt_mean(a.contribution_mean),
                    _fmt_mean(a.collaboration_mean),
                    _fmt_mean(a.reliability_mean),
                    _fmt_mean(a.communication_mean),
                    f"{a.overall_mean:.2f}" if a.overall_mean is not None else "—",
                ]
                for a in data.team_peer_aggregates
            ],
        )
    )
    if data.detailed_peer_ratings:
        parts.append("### Detailed ratings")
        parts.append(
            _md_table(
                ["Rater", "Ratee", "Contrib", "Collab", "Reli", "Comm",
                 "Overall", "Comments"],
                [
                    [
                        r.rater_name,
                        r.ratee_name,
                        str(r.rating.contribution),
                        str(r.rating.collaboration),
                        str(r.rating.reliability),
                        str(r.rating.communication),
                        f"{r.rating.overall:.2f}",
                        r.rating.comments or "",
                    ]
                    for r in data.detailed_peer_ratings
                ],
            )
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _eur(value: float) -> str:
    """Compact EUR formatting matching the in-app reports."""
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:,.1f}k"
    return f"€{value:,.0f}"


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _fmt_mean(value: Optional[float]) -> str:
    return f"{value:.1f}" if value is not None else "—"


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a Markdown table; returns "" if `rows` is empty."""
    if not rows:
        return ""
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = [
        "| " + " | ".join(_escape_cell(c) for c in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator] + row_lines)


def _escape_cell(s: str) -> str:
    """Escape pipes and newlines so a cell stays on one row."""
    return s.replace("|", "\\|").replace("\n", " / ")
