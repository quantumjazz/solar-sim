"""Game service — the bridge between the SQLite store and the engine.

`db.py` is dumb storage; `sim_engine` is a pure function. This module is
where the two meet: it loads scenario packs, deserialises stored state and
decisions into engine models, calls `run_period`, and writes the results
back.

The UI (`app.py`) only ever calls `GameService` and `db.Database`; it never
imports the engine directly. Engine models are persisted as JSON via
Pydantic's `model_dump_json` / `model_validate_json`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

from sim_engine.context import resolve_period_context
from sim_engine.decisions import TeamDecision
from sim_engine.engine import build_initial_state, run_period
from sim_engine.reports import IndustryReport, ReportBundle
from sim_engine.scenario import (
    BulkBuyerOffer,
    LoadedScenarioPack,
    PeriodEvent,
    TenderOffer,
    load_scenario_pack,
)
from sim_engine.state import PeriodState
from sim_engine.validation import validate_decision

from board_export import (
    PeerRatingWithNames,
    TeamBoardData,
    render_document,
)
from db import Database
from forms import default_decision
from pedagogy import (
    PEER_DIMENSIONS,
    AggregatedRating,
    PeerRating,
    PeriodPlanningQuality,
    StrategyMap,
    TeamPlanningQuality,
    aggregate_ratings,
)


class ServiceError(Exception):
    """A game-flow problem with a message safe to show a user."""


# ---------------------------------------------------------------------------
# Period form context — what the decision form needs to render for a period
# ---------------------------------------------------------------------------


@dataclass
class PeriodForms:
    """Everything `forms.team_decision_form` needs for one period."""

    period: int
    event: Optional[PeriodEvent]
    is_final: bool
    product_ids: List[str] = field(default_factory=list)
    launchable_product_ids: List[str] = field(default_factory=list)
    catalog_types: List[str] = field(default_factory=list)
    market_2_open: bool = False
    bulk_products: List[str] = field(default_factory=list)
    tender_products: List[str] = field(default_factory=list)
    bulk_buyers: List[BulkBuyerOffer] = field(default_factory=list)
    tenders: List[TenderOffer] = field(default_factory=list)


def form_context(pack: LoadedScenarioPack, period: int) -> PeriodForms:
    """Resolve the products / markets / offers in play for `period`.

    Mirrors the decision-context block of the instructor console so the
    multi-user app and the console stay behaviourally identical.
    """
    ctx = resolve_period_context(pack, period)
    event = pack.event_for_period(period)
    real_periods = pack.pack.scenario.real_periods
    is_final = bool(real_periods) and period >= max(real_periods)

    return PeriodForms(
        period=period,
        event=event,
        is_final=is_final,
        product_ids=[
            p.id for p in ctx.products if p.available_from_period <= period
        ],
        launchable_product_ids=[
            p.id for p in ctx.products if p.first_launch_period <= period
        ],
        catalog_types=[t.type_id for t in pack.pack.production_line_catalog],
        market_2_open=any(
            m.id == "market_2" and m.open_from_period <= period
            for m in ctx.markets
        ),
        bulk_products=[b.product for b in ctx.bulk_buyers],
        tender_products=[t.product for t in ctx.tenders],
        bulk_buyers=list(ctx.bulk_buyers),
        tenders=list(ctx.tenders),
    )


def load_narrative(scenario_path: str, event: Optional[PeriodEvent]) -> str:
    """Return the period's Markdown briefing, or "" if there is none."""
    if event is None or not getattr(event, "narrative_file", None):
        return ""
    try:
        return (Path(scenario_path) / event.narrative_file).read_text(
            encoding="utf-8"
        )
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Game service
# ---------------------------------------------------------------------------


class GameService:
    """Stateless service object; all persistent state lives in the database."""

    def __init__(self, db: Database):
        self.db = db

    # -- scenario pack -------------------------------------------------------

    def load_pack(self, cohort_id: int) -> LoadedScenarioPack:
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None:
            raise ServiceError(f"Cohort {cohort_id} does not exist.")
        return load_scenario_pack(cohort["scenario_path"])

    # -- cohort lifecycle ----------------------------------------------------

    def create_cohort(
        self,
        instructor_id: int,
        name: str,
        scenario_path: str,
        team_names: List[str],
    ) -> int:
        """Create a cohort: build period-0 state, teams, and period-1 drafts."""
        team_names = [n.strip() for n in team_names if n.strip()]
        if not team_names:
            raise ServiceError("A cohort needs at least one team.")

        try:
            pack = load_scenario_pack(scenario_path)
        except Exception as exc:  # noqa: BLE001 — surface a readable message
            raise ServiceError(f"Could not load scenario: {exc}")

        cohort_id = self.db.create_cohort(name, scenario_path, instructor_id)
        company_ids = [f"c{i + 1}" for i in range(len(team_names))]

        state = build_initial_state(
            pack, cohort_id=str(cohort_id), company_ids=company_ids
        )
        # build_initial_state names every company from the scenario's
        # placeholder; give each the team's chosen display name.
        for company, team_name in zip(state.companies, team_names):
            company.name = team_name

        team_id_by_company: Dict[str, int] = {}
        for company_id, team_name in zip(company_ids, team_names):
            team_id_by_company[company_id] = self.db.create_team(
                cohort_id, company_id, team_name
            )

        self.db.save_period_state(cohort_id, 0, state.model_dump_json())

        # Seed each team's period-1 decision with a sensible default draft.
        product_ids_p1 = [
            p.id for p in pack.pack.products if p.available_from_period <= 1
        ]
        for company_id, team_id in team_id_by_company.items():
            seed = default_decision(company_id, 1, product_ids_p1)
            self.db.upsert_decision(
                cohort_id, team_id, 1, seed.model_dump_json(), "draft", None
            )

        return cohort_id

    # -- state accessors -----------------------------------------------------

    def get_state(self, cohort_id: int) -> PeriodState:
        """The most recent persisted period state for a cohort."""
        latest = self.db.latest_period_state(cohort_id)
        if latest is None:
            raise ServiceError(f"Cohort {cohort_id} has no state.")
        return PeriodState.model_validate_json(latest[1])

    def upcoming_period(self, cohort_id: int) -> int:
        """The period the teams are currently deciding for."""
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None:
            raise ServiceError(f"Cohort {cohort_id} does not exist.")
        return int(cohort["current_period"]) + 1

    def company_id_for_team(self, team_id: int) -> str:
        team = self.db.get_team(team_id)
        if team is None:
            raise ServiceError(f"Team {team_id} does not exist.")
        return team["company_id"]

    # -- team membership -----------------------------------------------------

    def assign_student(
        self, cohort_id: int, team_id: int, user_id: int
    ) -> None:
        """Place a student on a team, moving them off any other team here."""
        existing = self.db.get_user_team(cohort_id, user_id)
        if existing is not None and existing["id"] != team_id:
            self.db.remove_team_member(existing["id"], user_id)
        self.db.add_team_member(team_id, user_id)

    def unassign_student(self, cohort_id: int, user_id: int) -> None:
        """Remove a student from whatever team they are on in this cohort."""
        existing = self.db.get_user_team(cohort_id, user_id)
        if existing is not None:
            self.db.remove_team_member(existing["id"], user_id)

    # -- decisions -----------------------------------------------------------

    def get_decision(
        self, cohort_id: int, team_id: int, period: int
    ) -> Optional[TeamDecision]:
        row = self.db.get_decision(cohort_id, team_id, period)
        if row is None:
            return None
        return TeamDecision.model_validate_json(row["decision_json"])

    def decision_status(
        self, cohort_id: int, team_id: int, period: int
    ) -> str:
        """'submitted', 'draft', or 'none' for one team's period decision."""
        row = self.db.get_decision(cohort_id, team_id, period)
        return row["status"] if row is not None else "none"

    def submission_status(
        self, cohort_id: int, period: int
    ) -> Dict[int, str]:
        """team_id -> 'submitted' / 'draft' / 'none' for the period."""
        status = {t["id"]: "none" for t in self.db.list_teams(cohort_id)}
        for row in self.db.list_decisions(cohort_id, period):
            status[row["team_id"]] = row["status"]
        return status

    def validate(
        self, cohort_id: int, team_id: int, period: int, decision: TeamDecision
    ) -> List[str]:
        """Hard-constraint check for one team's decision; [] means valid."""
        pack = self.load_pack(cohort_id)
        state = self.get_state(cohort_id)
        company_id = self.company_id_for_team(team_id)
        ctx = resolve_period_context(pack, period)
        return validate_decision(decision, state.company(company_id), ctx)

    def save_draft(
        self,
        cohort_id: int,
        team_id: int,
        period: int,
        decision: TeamDecision,
        user_id: int,
    ) -> None:
        """Store a team's in-progress decision; no validation (it is a draft)."""
        self.db.upsert_decision(
            cohort_id,
            team_id,
            period,
            decision.model_dump_json(),
            "draft",
            user_id,
        )

    def submit_decision(
        self,
        cohort_id: int,
        team_id: int,
        period: int,
        decision: TeamDecision,
        user_id: int,
    ) -> None:
        """Validate and lock a team's decision for the period.

        Refuses to submit an invalid decision so a submitted decision is
        always runnable.
        """
        errors = self.validate(cohort_id, team_id, period, decision)
        if errors:
            raise ServiceError(
                "Decision cannot be submitted — fix these first: "
                + "; ".join(errors)
            )
        self.db.upsert_decision(
            cohort_id,
            team_id,
            period,
            decision.model_dump_json(),
            "submitted",
            user_id,
        )

    def reopen_decision(
        self, cohort_id: int, team_id: int, period: int
    ) -> None:
        """Instructor action: unlock a submitted decision back to a draft."""
        row = self.db.get_decision(cohort_id, team_id, period)
        if row is None:
            return
        self.db.upsert_decision(
            cohort_id,
            team_id,
            period,
            row["decision_json"],
            "draft",
            row["updated_by"],
        )

    # -- running a period ----------------------------------------------------

    def run_next_period(
        self, cohort_id: int, require_all_submitted: bool = True
    ) -> int:
        """Advance the cohort by one period; return the new period index.

        Loads the latest state and every team's decision for the upcoming
        period, runs the engine, and persists the new state, the per-team
        reports, and the next period's seed drafts.
        """
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None:
            raise ServiceError(f"Cohort {cohort_id} does not exist.")
        if cohort["status"] == "finished":
            raise ServiceError("This cohort has already finished.")

        pack = load_scenario_pack(cohort["scenario_path"])
        state = self.get_state(cohort_id)
        upcoming = state.period_index + 1

        teams = self.db.list_teams(cohort_id)
        team_id_by_company = {t["company_id"]: t["id"] for t in teams}

        if require_all_submitted:
            pending = [
                t["name"]
                for t in teams
                if self.decision_status(cohort_id, t["id"], upcoming)
                != "submitted"
            ]
            if pending:
                raise ServiceError(
                    "These teams have not submitted yet: "
                    + ", ".join(pending)
                )

        # Assemble decisions keyed by engine company id.
        decisions: Dict[str, TeamDecision] = {}
        for company_id, team_id in team_id_by_company.items():
            decision = self.get_decision(cohort_id, team_id, upcoming)
            if decision is None:
                raise ServiceError(
                    f"Team {company_id} has no decision for period {upcoming}."
                )
            decisions[company_id] = decision

        # run_period validates every decision and raises InvalidDecisionError
        # if any team's is invalid; let that propagate to the caller.
        new_state, reports = run_period(state, decisions, pack)

        # Persist the new state and each team's report bundle.
        self.db.save_period_state(
            cohort_id, new_state.period_index, new_state.model_dump_json()
        )
        for company_id, team_id in team_id_by_company.items():
            bundle = reports[company_id]
            self.db.save_report(
                cohort_id,
                team_id,
                new_state.period_index,
                bundle.model_dump_json(),
            )
        self.db.set_cohort_period(cohort_id, new_state.period_index)

        # Seed the next period's drafts (carry each team's decision forward)
        # unless the cohort has reached its final period.
        real_periods = pack.pack.scenario.real_periods
        final_period = max(real_periods) if real_periods else new_state.period_index
        if new_state.period_index >= final_period:
            self.db.set_cohort_status(cohort_id, "finished")
        else:
            next_upcoming = new_state.period_index + 1
            for company_id, team_id in team_id_by_company.items():
                carried = decisions[company_id].model_copy(deep=True)
                carried.period = next_upcoming
                self.db.upsert_decision(
                    cohort_id,
                    team_id,
                    next_upcoming,
                    carried.model_dump_json(),
                    "draft",
                    None,
                )

        return new_state.period_index

    # -- reports -------------------------------------------------------------

    def get_report(
        self, cohort_id: int, team_id: int, period: int
    ) -> Optional[ReportBundle]:
        raw = self.db.get_report(cohort_id, team_id, period)
        if raw is None:
            return None
        return ReportBundle.model_validate_json(raw)

    def get_industry_report(
        self, cohort_id: int, period: int
    ) -> Optional[IndustryReport]:
        """The cohort-public competitor view for a completed period.

        Every team's bundle embeds the same industry report; return it from
        whichever team's report is available.
        """
        for row in self.db.list_reports(cohort_id, period):
            bundle = ReportBundle.model_validate_json(row["report_json"])
            if bundle.industry is not None:
                return bundle.industry
        return None

    # -- pedagogy: planning quality -----------------------------------------

    def team_planning_quality(
        self, cohort_id: int, team_id: int
    ) -> TeamPlanningQuality:
        """Compute one team's planning quality across all completed periods.

        Reads the stored decisions for planned KPIs and the stored reports
        for actuals; skips periods missing either side (none should be
        missing for a normally-progressed cohort). The headline score is
        the mean over real periods only (see `09-pedagogy.md` §1.3).
        """
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None:
            raise ServiceError(f"Cohort {cohort_id} does not exist.")
        completed = int(cohort["current_period"])
        if completed < 1:
            return TeamPlanningQuality(team_id=team_id, periods=[])

        pack = load_scenario_pack(cohort["scenario_path"])
        real_periods = set(pack.pack.scenario.real_periods)

        periods: List[PeriodPlanningQuality] = []
        for period in range(1, completed + 1):
            decision_row = self.db.get_decision(cohort_id, team_id, period)
            report_raw = self.db.get_report(cohort_id, team_id, period)
            if decision_row is None or report_raw is None:
                continue
            decision = TeamDecision.model_validate_json(
                decision_row["decision_json"]
            )
            report = ReportBundle.model_validate_json(report_raw)
            periods.append(
                PeriodPlanningQuality.from_planned_and_actual(
                    period=period,
                    is_real_period=period in real_periods,
                    planned=decision.finance.planned_kpis,
                    actual=report,
                )
            )
        return TeamPlanningQuality.from_periods(team_id, periods)

    # -- pedagogy: strategy map ---------------------------------------------

    def get_strategy_map(
        self, cohort_id: int, team_id: int
    ) -> StrategyMap:
        """The team's balanced-scorecard map; an empty one if never edited."""
        row = self.db.get_strategy_map(cohort_id, team_id)
        if row is None:
            return StrategyMap(cohort_id=cohort_id, team_id=team_id)
        return StrategyMap(
            cohort_id=cohort_id,
            team_id=team_id,
            financial=row["financial"],
            customer=row["customer"],
            internal_process=row["internal_process"],
            learning_growth=row["learning_growth"],
            updated_by=row["updated_by"],
            updated_at=row["updated_at"],
        )

    def save_strategy_map(
        self,
        cohort_id: int,
        team_id: int,
        financial: str,
        customer: str,
        internal_process: str,
        learning_growth: str,
        user_id: int,
    ) -> None:
        """Upsert the team's balanced-scorecard strategy map."""
        self.db.upsert_strategy_map(
            cohort_id,
            team_id,
            financial,
            customer,
            internal_process,
            learning_growth,
            user_id,
        )

    # -- pedagogy: peer assessment ------------------------------------------

    def team_peer_targets(
        self, cohort_id: int, user_id: int
    ) -> List:
        """Teammates of `user_id` in `cohort_id`, excluding the user.

        Returns the user-row list; empty if the user isn't on a team here.
        """
        team = self.db.get_user_team(cohort_id, user_id)
        if team is None:
            return []
        return [
            m for m in self.db.list_team_members(team["id"]) if m["id"] != user_id
        ]

    def get_my_rating(
        self, cohort_id: int, rater_id: int, ratee_id: int
    ) -> Optional[PeerRating]:
        row = self.db.get_peer_rating(cohort_id, rater_id, ratee_id)
        return self._row_to_peer_rating(row) if row is not None else None

    def save_peer_rating(
        self,
        cohort_id: int,
        rater_id: int,
        ratee_id: int,
        contribution: int,
        collaboration: int,
        reliability: int,
        communication: int,
        comments: str,
    ) -> None:
        """Validate and persist one (rater, ratee) rating.

        Enforces the three rules from `09-pedagogy.md` §3.4 that the schema
        cannot: rater ≠ ratee, both on the same team in this cohort, and
        the cohort is still active.
        """
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None:
            raise ServiceError(f"Cohort {cohort_id} does not exist.")
        if cohort["status"] == "finished":
            raise ServiceError(
                "This cohort has finished — peer ratings are locked."
            )
        if rater_id == ratee_id:
            raise ServiceError("You cannot rate yourself.")
        rater_team = self.db.get_user_team(cohort_id, rater_id)
        ratee_team = self.db.get_user_team(cohort_id, ratee_id)
        if (
            rater_team is None
            or ratee_team is None
            or rater_team["id"] != ratee_team["id"]
        ):
            raise ServiceError(
                "Rater and ratee must be on the same team in this cohort."
            )
        for dim, value in (
            ("contribution", contribution),
            ("collaboration", collaboration),
            ("reliability", reliability),
            ("communication", communication),
        ):
            if not isinstance(value, int) or not 1 <= value <= 5:
                raise ServiceError(f"{dim} must be an integer in 1-5 (got {value!r}).")
        self.db.upsert_peer_rating(
            cohort_id,
            rater_id,
            ratee_id,
            contribution,
            collaboration,
            reliability,
            communication,
            comments,
        )

    def my_aggregated_rating(
        self, cohort_id: int, user_id: int
    ) -> Optional[AggregatedRating]:
        """The user's own aggregated rating, **only after the cohort closes**.

        Returns `None` while the cohort is still active — per
        `09-pedagogy.md` §3.3 the ratee does not see their ratings until
        the cohort is finished.
        """
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None or cohort["status"] != "finished":
            return None
        rows = self.db.list_peer_ratings_by_ratee(cohort_id, user_id)
        return aggregate_ratings(
            user_id, [self._row_to_peer_rating(r) for r in rows]
        )

    def team_peer_aggregates(
        self, cohort_id: int, team_id: int
    ) -> List[AggregatedRating]:
        """Per-ratee aggregated ratings within one team — for instructors."""
        aggs: List[AggregatedRating] = []
        for member in self.db.list_team_members(team_id):
            rows = self.db.list_peer_ratings_by_ratee(cohort_id, member["id"])
            aggs.append(
                aggregate_ratings(
                    member["id"],
                    [self._row_to_peer_rating(r) for r in rows],
                )
            )
        return aggs

    def peer_ratings_for_team(
        self, cohort_id: int, team_id: int
    ) -> List[PeerRating]:
        """Every rating whose rater and ratee are both members of this team."""
        members = {m["id"] for m in self.db.list_team_members(team_id)}
        return [
            self._row_to_peer_rating(r)
            for r in self.db.list_peer_ratings(cohort_id)
            if r["rater_id"] in members and r["ratee_id"] in members
        ]

    @staticmethod
    def _row_to_peer_rating(row) -> PeerRating:
        return PeerRating(
            cohort_id=row["cohort_id"],
            rater_id=row["rater_id"],
            ratee_id=row["ratee_id"],
            contribution=row["contribution"],
            collaboration=row["collaboration"],
            reliability=row["reliability"],
            communication=row["communication"],
            comments=row["comments"],
            updated_at=row["updated_at"],
        )

    # -- pedagogy: board-meeting export -------------------------------------

    def build_board_document(
        self,
        cohort_id: int,
        team_id: int,
        viewer_role: str,
        viewer_user_id: Optional[int] = None,
    ) -> str:
        """Render the full board-meeting Markdown document for one team.

        Fetches per-period reports, planning quality, strategy map, and
        peer aggregates from the database, applies the viewer-role
        visibility rules from `09-pedagogy.md` §4.3, and calls
        `board_export.render_document`.
        """
        cohort = self.db.get_cohort(cohort_id)
        if cohort is None:
            raise ServiceError(f"Cohort {cohort_id} does not exist.")
        team = self.db.get_team(team_id)
        if team is None or team["cohort_id"] != cohort_id:
            raise ServiceError(
                f"Team {team_id} is not in cohort {cohort_id}."
            )

        pack = load_scenario_pack(cohort["scenario_path"])
        members = self.db.list_team_members(team_id)
        member_names = [m["display_name"] for m in members]
        name_by_id = {m["id"]: m["display_name"] for m in members}

        completed = int(cohort["current_period"])
        period_bundles: List[ReportBundle] = []
        for period in range(1, completed + 1):
            raw = self.db.get_report(cohort_id, team_id, period)
            if raw is not None:
                period_bundles.append(ReportBundle.model_validate_json(raw))

        final_industry = (
            self.get_industry_report(cohort_id, completed)
            if completed >= 1
            else None
        )
        tpq = (
            self.team_planning_quality(cohort_id, team_id)
            if completed >= 1
            else None
        )
        strategy = self.get_strategy_map(cohort_id, team_id)

        own_aggregate: Optional[AggregatedRating] = None
        team_aggs: List[AggregatedRating] = []
        detailed: List[PeerRatingWithNames] = []
        if viewer_role == "student" and viewer_user_id is not None:
            own_aggregate = self.my_aggregated_rating(cohort_id, viewer_user_id)
        elif viewer_role == "instructor":
            team_aggs = self.team_peer_aggregates(cohort_id, team_id)
            for rating in self.peer_ratings_for_team(cohort_id, team_id):
                detailed.append(
                    PeerRatingWithNames(
                        rater_name=name_by_id.get(
                            rating.rater_id, f"user #{rating.rater_id}"
                        ),
                        ratee_name=name_by_id.get(
                            rating.ratee_id, f"user #{rating.ratee_id}"
                        ),
                        rating=rating,
                    )
                )

        data = TeamBoardData(
            cohort_name=cohort["name"],
            cohort_status=cohort["status"],
            scenario_id=pack.pack.scenario.id,
            team_name=team["name"],
            team_company_id=team["company_id"],
            member_names=member_names,
            final_industry_report=final_industry,
            period_bundles=period_bundles,
            planning_quality=tpq,
            strategy_map=strategy,
            own_peer_aggregate=own_aggregate,
            team_peer_aggregates=team_aggs,
            detailed_peer_ratings=detailed,
            viewer_role=viewer_role,
            generated_at=date.today().isoformat(),
        )
        return render_document(data)
