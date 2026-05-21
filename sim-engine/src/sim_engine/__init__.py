"""sim-engine — a scenario-driven business simulation engine.

Public surface:

    from sim_engine import load_scenario_pack, run_period
    from sim_engine.decisions import TeamDecision
    from sim_engine.state import PeriodState

See README.md for the v0.1 MVP scope. See ../../docs/spec/ for the full
mechanics specification.
"""

from sim_engine.engine import build_initial_state, run_period
from sim_engine.scenario import load_scenario_pack
from sim_engine.state import PeriodState
from sim_engine.validation import InvalidDecisionError, validate_decision

__version__ = "0.2.0"
__all__ = [
    "run_period",
    "build_initial_state",
    "load_scenario_pack",
    "PeriodState",
    "validate_decision",
    "InvalidDecisionError",
]
