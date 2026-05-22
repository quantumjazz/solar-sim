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

from db import Database
from forms import default_decision


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
