"""SQLite persistence for the multi-user solar-sim app.

This module is the only place that talks to SQLite. It exposes a `Database`
class with low-level CRUD methods; the game logic that bridges the database
to the simulation engine lives in `service.py`.

Design notes:
  - One connection per operation. `sqlite3.connect` is cheap, and a fresh
    connection per call sidesteps the thread-safety pitfalls of sharing one
    connection across Streamlit's per-session script threads.
  - WAL journal mode (set once, persisted on the file) lets readers run
    without blocking on the writer — fine for a classroom-scale cohort.
  - JSON-serialised engine models (PeriodState, TeamDecision, ReportBundle)
    are stored as TEXT; serialisation is the caller's responsibility.

There is no schema-migration system: the schema is created with
`CREATE TABLE IF NOT EXISTS` and is append-only by convention.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    display_name  TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'student',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cohorts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    scenario_path  TEXT NOT NULL,
    instructor_id  INTEGER NOT NULL REFERENCES users(id),
    current_period INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'active',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cohort_id  INTEGER NOT NULL REFERENCES cohorts(id),
    company_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    UNIQUE (cohort_id, company_id)
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id INTEGER NOT NULL REFERENCES teams(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE IF NOT EXISTS period_states (
    cohort_id    INTEGER NOT NULL REFERENCES cohorts(id),
    period_index INTEGER NOT NULL,
    state_json   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (cohort_id, period_index)
);

CREATE TABLE IF NOT EXISTS decisions (
    cohort_id     INTEGER NOT NULL REFERENCES cohorts(id),
    team_id       INTEGER NOT NULL REFERENCES teams(id),
    period_index  INTEGER NOT NULL,
    decision_json TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft',
    updated_by    INTEGER REFERENCES users(id),
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (cohort_id, team_id, period_index)
);

CREATE TABLE IF NOT EXISTS reports (
    cohort_id    INTEGER NOT NULL REFERENCES cohorts(id),
    team_id      INTEGER NOT NULL REFERENCES teams(id),
    period_index INTEGER NOT NULL,
    report_json  TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (cohort_id, team_id, period_index)
);

-- Pedagogy layer: one balanced-scorecard strategy map per (cohort, team).
-- Each perspective is freeform Markdown; see docs/spec/09-pedagogy.md §2.
CREATE TABLE IF NOT EXISTS strategy_maps (
    cohort_id        INTEGER NOT NULL REFERENCES cohorts(id),
    team_id          INTEGER NOT NULL REFERENCES teams(id),
    financial        TEXT NOT NULL DEFAULT '',
    customer         TEXT NOT NULL DEFAULT '',
    internal_process TEXT NOT NULL DEFAULT '',
    learning_growth  TEXT NOT NULL DEFAULT '',
    updated_by       INTEGER REFERENCES users(id),
    updated_at       TEXT NOT NULL,
    PRIMARY KEY (cohort_id, team_id)
);
"""


def _now() -> str:
    """An ISO-8601 UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


class Database:
    """A SQLite-backed store. Construct once per process with a file path."""

    def __init__(self, path: Union[str, Path]):
        self.path = str(path)
        self._init()

    # -- connection plumbing -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """A short-lived connection that commits on success, always closes."""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # -- users ---------------------------------------------------------------

    def create_user(
        self, email: str, display_name: str, password_hash: str, role: str
    ) -> int:
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT INTO users (email, display_name, password_hash, role, "
                "created_at) VALUES (?, ?, ?, ?, ?)",
                (email, display_name, password_hash, role, _now()),
            )
            return int(cur.lastrowid)

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    def get_user_by_email(self, email: str) -> Optional[sqlite3.Row]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()

    def list_users(self, role: Optional[str] = None) -> List[sqlite3.Row]:
        with self._tx() as conn:
            if role is None:
                rows = conn.execute(
                    "SELECT * FROM users ORDER BY display_name"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM users WHERE role = ? ORDER BY display_name",
                    (role,),
                ).fetchall()
            return list(rows)

    # -- cohorts -------------------------------------------------------------

    def create_cohort(
        self, name: str, scenario_path: str, instructor_id: int
    ) -> int:
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT INTO cohorts (name, scenario_path, instructor_id, "
                "current_period, status, created_at) VALUES (?, ?, ?, 0, "
                "'active', ?)",
                (name, scenario_path, instructor_id, _now()),
            )
            return int(cur.lastrowid)

    def get_cohort(self, cohort_id: int) -> Optional[sqlite3.Row]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT * FROM cohorts WHERE id = ?", (cohort_id,)
            ).fetchone()

    def list_cohorts(
        self, instructor_id: Optional[int] = None
    ) -> List[sqlite3.Row]:
        with self._tx() as conn:
            if instructor_id is None:
                rows = conn.execute(
                    "SELECT * FROM cohorts ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cohorts WHERE instructor_id = ? "
                    "ORDER BY created_at DESC",
                    (instructor_id,),
                ).fetchall()
            return list(rows)

    def list_cohorts_for_user(self, user_id: int) -> List[sqlite3.Row]:
        """Cohorts in which `user_id` is a member of some team."""
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT DISTINCT c.* FROM cohorts c "
                "JOIN teams t ON t.cohort_id = c.id "
                "JOIN team_members tm ON tm.team_id = t.id "
                "WHERE tm.user_id = ? ORDER BY c.created_at DESC",
                (user_id,),
            ).fetchall()
            return list(rows)

    def set_cohort_period(self, cohort_id: int, current_period: int) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE cohorts SET current_period = ? WHERE id = ?",
                (current_period, cohort_id),
            )

    def set_cohort_status(self, cohort_id: int, status: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE cohorts SET status = ? WHERE id = ?",
                (status, cohort_id),
            )

    # -- teams ---------------------------------------------------------------

    def create_team(self, cohort_id: int, company_id: str, name: str) -> int:
        with self._tx() as conn:
            cur = conn.execute(
                "INSERT INTO teams (cohort_id, company_id, name) "
                "VALUES (?, ?, ?)",
                (cohort_id, company_id, name),
            )
            return int(cur.lastrowid)

    def get_team(self, team_id: int) -> Optional[sqlite3.Row]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT * FROM teams WHERE id = ?", (team_id,)
            ).fetchone()

    def list_teams(self, cohort_id: int) -> List[sqlite3.Row]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT * FROM teams WHERE cohort_id = ? ORDER BY id",
                (cohort_id,),
            ).fetchall()
            return list(rows)

    # -- team membership -----------------------------------------------------

    def add_team_member(self, team_id: int, user_id: int) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO team_members (team_id, user_id) "
                "VALUES (?, ?)",
                (team_id, user_id),
            )

    def remove_team_member(self, team_id: int, user_id: int) -> None:
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
                (team_id, user_id),
            )

    def list_team_members(self, team_id: int) -> List[sqlite3.Row]:
        """Users on a team, with their user columns."""
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT u.* FROM users u "
                "JOIN team_members tm ON tm.user_id = u.id "
                "WHERE tm.team_id = ? ORDER BY u.display_name",
                (team_id,),
            ).fetchall()
            return list(rows)

    def get_user_team(
        self, cohort_id: int, user_id: int
    ) -> Optional[sqlite3.Row]:
        """The team a user belongs to within one cohort, or None."""
        with self._tx() as conn:
            return conn.execute(
                "SELECT t.* FROM teams t "
                "JOIN team_members tm ON tm.team_id = t.id "
                "WHERE t.cohort_id = ? AND tm.user_id = ?",
                (cohort_id, user_id),
            ).fetchone()

    # -- period states -------------------------------------------------------

    def save_period_state(
        self, cohort_id: int, period_index: int, state_json: str
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO period_states (cohort_id, period_index, "
                "state_json, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(cohort_id, period_index) DO UPDATE SET "
                "state_json = excluded.state_json, "
                "created_at = excluded.created_at",
                (cohort_id, period_index, state_json, _now()),
            )

    def get_period_state(
        self, cohort_id: int, period_index: int
    ) -> Optional[str]:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT state_json FROM period_states "
                "WHERE cohort_id = ? AND period_index = ?",
                (cohort_id, period_index),
            ).fetchone()
            return row["state_json"] if row is not None else None

    def latest_period_state(
        self, cohort_id: int
    ) -> Optional[Tuple[int, str]]:
        """The (period_index, state_json) of the most recent stored state."""
        with self._tx() as conn:
            row = conn.execute(
                "SELECT period_index, state_json FROM period_states "
                "WHERE cohort_id = ? ORDER BY period_index DESC LIMIT 1",
                (cohort_id,),
            ).fetchone()
            if row is None:
                return None
            return int(row["period_index"]), row["state_json"]

    # -- decisions -----------------------------------------------------------

    def upsert_decision(
        self,
        cohort_id: int,
        team_id: int,
        period_index: int,
        decision_json: str,
        status: str,
        updated_by: Optional[int],
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO decisions (cohort_id, team_id, period_index, "
                "decision_json, status, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(cohort_id, team_id, period_index) DO UPDATE SET "
                "decision_json = excluded.decision_json, "
                "status = excluded.status, "
                "updated_by = excluded.updated_by, "
                "updated_at = excluded.updated_at",
                (
                    cohort_id,
                    team_id,
                    period_index,
                    decision_json,
                    status,
                    updated_by,
                    _now(),
                ),
            )

    def get_decision(
        self, cohort_id: int, team_id: int, period_index: int
    ) -> Optional[sqlite3.Row]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT * FROM decisions WHERE cohort_id = ? AND team_id = ? "
                "AND period_index = ?",
                (cohort_id, team_id, period_index),
            ).fetchone()

    def list_decisions(
        self, cohort_id: int, period_index: int
    ) -> List[sqlite3.Row]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE cohort_id = ? "
                "AND period_index = ? ORDER BY team_id",
                (cohort_id, period_index),
            ).fetchall()
            return list(rows)

    # -- reports -------------------------------------------------------------

    def save_report(
        self, cohort_id: int, team_id: int, period_index: int, report_json: str
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO reports (cohort_id, team_id, period_index, "
                "report_json, created_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(cohort_id, team_id, period_index) DO UPDATE SET "
                "report_json = excluded.report_json, "
                "created_at = excluded.created_at",
                (cohort_id, team_id, period_index, report_json, _now()),
            )

    def get_report(
        self, cohort_id: int, team_id: int, period_index: int
    ) -> Optional[str]:
        with self._tx() as conn:
            row = conn.execute(
                "SELECT report_json FROM reports WHERE cohort_id = ? "
                "AND team_id = ? AND period_index = ?",
                (cohort_id, team_id, period_index),
            ).fetchone()
            return row["report_json"] if row is not None else None

    def list_reports(
        self, cohort_id: int, period_index: int
    ) -> List[sqlite3.Row]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE cohort_id = ? "
                "AND period_index = ? ORDER BY team_id",
                (cohort_id, period_index),
            ).fetchall()
            return list(rows)

    # -- strategy maps -------------------------------------------------------

    def get_strategy_map(
        self, cohort_id: int, team_id: int
    ) -> Optional[sqlite3.Row]:
        with self._tx() as conn:
            return conn.execute(
                "SELECT * FROM strategy_maps WHERE cohort_id = ? "
                "AND team_id = ?",
                (cohort_id, team_id),
            ).fetchone()

    def upsert_strategy_map(
        self,
        cohort_id: int,
        team_id: int,
        financial: str,
        customer: str,
        internal_process: str,
        learning_growth: str,
        updated_by: Optional[int],
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO strategy_maps (cohort_id, team_id, financial, "
                "customer, internal_process, learning_growth, updated_by, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(cohort_id, team_id) DO UPDATE SET "
                "financial = excluded.financial, "
                "customer = excluded.customer, "
                "internal_process = excluded.internal_process, "
                "learning_growth = excluded.learning_growth, "
                "updated_by = excluded.updated_by, "
                "updated_at = excluded.updated_at",
                (
                    cohort_id,
                    team_id,
                    financial,
                    customer,
                    internal_process,
                    learning_growth,
                    updated_by,
                    _now(),
                ),
            )

    def list_strategy_maps(self, cohort_id: int) -> List[sqlite3.Row]:
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT * FROM strategy_maps WHERE cohort_id = ? "
                "ORDER BY team_id",
                (cohort_id,),
            ).fetchall()
            return list(rows)
