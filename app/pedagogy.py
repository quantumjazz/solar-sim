"""Pedagogy-layer models.

Three pieces in one module, all pure (no database or UI dependency):

  - **Planning quality** — symmetric MAPE scoring of a team's forecast
    against the actuals it realises each period (`09-pedagogy.md` §1).
  - **Strategy map** — a Pydantic model for a team's balanced-scorecard
    statement (four freeform perspectives; `09-pedagogy.md` §2).
  - **Peer assessment** — per-(rater, ratee) rating across four
    dimensions on a 1–5 Likert scale, with aggregation
    (`09-pedagogy.md` §3).

The service layer reads decisions, reports, and database rows from
SQLite and asks this module to score / aggregate them, so the formulas
stay unit-testable on their own.
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from sim_engine.decisions import PlannedKPIs
from sim_engine.reports import ReportBundle


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------


def smape(planned: float, actual: float) -> float:
    """Symmetric mean absolute percentage error of one forecast.

    sMAPE = |planned - actual| / (|planned| + |actual|), in [0, 1] by the
    triangle inequality. The both-zero case is defined to be 0 (a perfect
    forecast of zero).
    """
    denom = abs(planned) + abs(actual)
    if denom == 0:
        return 0.0
    return abs(planned - actual) / denom


def kpi_score(planned: float, actual: float) -> float:
    """`1 - sMAPE(planned, actual)`, in [0, 1]. 1 is a perfect forecast."""
    return 1.0 - smape(planned, actual)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class KPILine(BaseModel):
    """One KPI's planned, actual, and score for a single period."""

    model_config = ConfigDict(extra="forbid")

    name: str
    planned: float
    actual: float
    score: float  # in [0, 1]


class PeriodPlanningQuality(BaseModel):
    """Planning quality for one team in one completed period."""

    model_config = ConfigDict(extra="forbid")

    period: int
    is_real_period: bool
    kpis: List[KPILine] = Field(default_factory=list)
    period_score: float  # unweighted mean of kpi scores

    @classmethod
    def from_planned_and_actual(
        cls,
        period: int,
        is_real_period: bool,
        planned: PlannedKPIs,
        actual: ReportBundle,
    ) -> "PeriodPlanningQuality":
        """Score a team's planned KPIs against the realised report bundle."""
        revenue_actual = actual.profit_and_loss.sales_revenue
        roe_actual = actual.executive_summary.return_on_equity
        ocf_actual = actual.cash_flow.operating_cash_flow

        kpis = [
            KPILine(
                name="Revenue",
                planned=planned.revenue,
                actual=revenue_actual,
                score=kpi_score(planned.revenue, revenue_actual),
            ),
            KPILine(
                name="Return on equity",
                planned=planned.return_on_equity,
                actual=roe_actual,
                score=kpi_score(planned.return_on_equity, roe_actual),
            ),
            KPILine(
                name="Operating cash flow",
                planned=planned.operating_cash_flow,
                actual=ocf_actual,
                score=kpi_score(planned.operating_cash_flow, ocf_actual),
            ),
        ]
        avg = sum(line.score for line in kpis) / len(kpis)
        return cls(
            period=period,
            is_real_period=is_real_period,
            kpis=kpis,
            period_score=avg,
        )


class TeamPlanningQuality(BaseModel):
    """Planning quality for one team across the periods that have been run.

    The headline score is the mean of `period_score` across **real**
    periods only, matching `docs/spec/09-pedagogy.md` §1.3. It is `None`
    until at least one real period has been run.
    """

    model_config = ConfigDict(extra="forbid")

    team_id: int
    periods: List[PeriodPlanningQuality] = Field(default_factory=list)
    real_period_count: int = 0
    headline_score: Optional[float] = None

    @classmethod
    def from_periods(
        cls, team_id: int, periods: List[PeriodPlanningQuality]
    ) -> "TeamPlanningQuality":
        real = [p for p in periods if p.is_real_period]
        headline = (
            sum(p.period_score for p in real) / len(real) if real else None
        )
        return cls(
            team_id=team_id,
            periods=periods,
            real_period_count=len(real),
            headline_score=headline,
        )


# ---------------------------------------------------------------------------
# Strategy map
# ---------------------------------------------------------------------------


class StrategyMap(BaseModel):
    """A team's balanced-scorecard strategy map.

    Each perspective is freeform Markdown. Missing or unset perspectives
    default to the empty string, so the UI can render a never-edited map
    without special-casing it.
    """

    model_config = ConfigDict(extra="forbid")

    cohort_id: int
    team_id: int
    financial: str = ""
    customer: str = ""
    internal_process: str = ""
    learning_growth: str = ""
    updated_by: Optional[int] = None
    updated_at: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        """True if no perspective has any non-whitespace content."""
        return not (
            self.financial.strip()
            or self.customer.strip()
            or self.internal_process.strip()
            or self.learning_growth.strip()
        )


# ---------------------------------------------------------------------------
# Peer assessment
# ---------------------------------------------------------------------------


#: The four dimensions, in the order shown to students and the order used by
#: the database columns. Keep these in sync with `peer_ratings` in `db.py`
#: and with `09-pedagogy.md` §3.1.
PEER_DIMENSIONS = (
    "contribution",
    "collaboration",
    "reliability",
    "communication",
)


class PeerRating(BaseModel):
    """One rater's rating of one teammate in one cohort.

    Dimension scores are bounded to the 1-5 Likert scale at the model
    boundary; the database also enforces this with CHECK constraints.
    """

    model_config = ConfigDict(extra="forbid")

    cohort_id: int
    rater_id: int
    ratee_id: int
    contribution: int = Field(ge=1, le=5)
    collaboration: int = Field(ge=1, le=5)
    reliability: int = Field(ge=1, le=5)
    communication: int = Field(ge=1, le=5)
    comments: str = ""
    updated_at: Optional[str] = None

    @property
    def overall(self) -> float:
        """Unweighted mean of the four dimension scores, in [1, 5]."""
        return (
            self.contribution
            + self.collaboration
            + self.reliability
            + self.communication
        ) / 4.0


class AggregatedRating(BaseModel):
    """One ratee's aggregated peer-rating view across raters.

    Means are `None` when nobody has rated the ratee yet — the UI shows
    "—". The overall mean is the average of the four dimension means
    (also `None` if no raters).
    """

    model_config = ConfigDict(extra="forbid")

    ratee_id: int
    n_raters: int = 0
    contribution_mean: Optional[float] = None
    collaboration_mean: Optional[float] = None
    reliability_mean: Optional[float] = None
    communication_mean: Optional[float] = None
    overall_mean: Optional[float] = None


def aggregate_ratings(
    ratee_id: int, ratings: Iterable[PeerRating]
) -> AggregatedRating:
    """Mean per dimension across `ratings`; an empty `ratings` yields a zero
    `AggregatedRating` with all means `None`."""
    rs = [r for r in ratings if r.ratee_id == ratee_id]
    if not rs:
        return AggregatedRating(ratee_id=ratee_id)
    n = len(rs)
    means = {
        dim: sum(getattr(r, dim) for r in rs) / n for dim in PEER_DIMENSIONS
    }
    overall = sum(means.values()) / len(means)
    return AggregatedRating(
        ratee_id=ratee_id,
        n_raters=n,
        contribution_mean=means["contribution"],
        collaboration_mean=means["collaboration"],
        reliability_mean=means["reliability"],
        communication_mean=means["communication"],
        overall_mean=overall,
    )
